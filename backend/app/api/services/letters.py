"""Letter field building, numbering, rendering (via Dev-B's renderer Protocol) and storage."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.api.errors import not_found, upstream, validation
from app.api.services import gateway, numbering, rules
from app.api.services import settings_store as rt
from app.audit import record as audit
from app.config import Settings
from app.contracts import RenderedLetter
from app.models import CourseRun, Employee, Enrollment, Letter, User
from app.schemas.domain import LetterIn
from app.security.crypto import get_cipher

RUN_KINDS = {"course_announcement", "institute_letter", "settlement_letter"}
ENROLLMENT_KINDS = {"level3_request", "level3_manager_check", "line_manager_approval"}
PLACEHOLDER_NO = "—"
FA_TYPE = {"online": "آنلاین", "in_person": "حضوری"}
EN_TYPE = {"online": "Online", "in_person": "In-Person"}
COMPANY_KEYS = ("company_economic_code", "company_national_id", "company_postal_code", "company_address")


@dataclass
class Plan:
    fields: dict[str, Any]
    enrollment_ids: list[int] = field(default_factory=list)


def title_fa(g: str) -> str:
    return {"male": "جناب آقای", "female": "سرکار خانم"}.get(g, "جناب/سرکار")      # neutral when gender is unknown


def title_en(g: str) -> str:
    return {"male": "Mr.", "female": "Ms."}.get(g, "Mr./Ms.")


def name_fa(e: Employee) -> str:
    return f"{e.first_name_fa} {e.last_name_fa}".strip() or f"{e.first_name_en} {e.last_name_en}".strip()


def name_en(e: Employee) -> str:
    return f"{e.first_name_en} {e.last_name_en}".strip()


def money(x) -> str:
    return f"{int(x):,}"


def load_run(db: Session, run_id: int | None) -> CourseRun:
    if not run_id:
        raise validation("شناسهٔ دورهٔ برگزارشده لازم است", run_id="الزامی است")
    run = db.scalar(select(CourseRun).options(joinedload(CourseRun.course), joinedload(CourseRun.institute))
                    .where(CourseRun.id == run_id))
    if not run:
        raise not_found("دوره برگزارشده")
    return run


def load_enrollments(db: Session, ids: list[int]) -> list[Enrollment]:
    if not ids:
        return []
    rows = {e.id: e for e in db.scalars(select(Enrollment).options(joinedload(Enrollment.employee), joinedload(Enrollment.run))
                                        .where(Enrollment.id.in_(ids))).unique()}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise validation("ثبت‌نام نامعتبر", enrollment_ids=f"شناسه‌های ناشناخته: {missing[:5]}")
    return [rows[i] for i in dict.fromkeys(ids)]


def _run_enrollments(db: Session, run: CourseRun, ids: list[int]) -> list[Enrollment]:
    if ids:
        es = load_enrollments(db, ids)
        if any(e.run_id != run.id for e in es):
            raise validation("ثبت‌نام‌ها به این دوره تعلق ندارند", enrollment_ids="به این دوره تعلق ندارد")
        return es
    return list(db.scalars(select(Enrollment).options(joinedload(Enrollment.employee))
                           .where(Enrollment.run_id == run.id, Enrollment.motivation == "Yes")
                           .order_by(Enrollment.id)).unique())


Skipped = list[dict[str, Any]]


def _no_plans(skipped: Skipped) -> None:
    if skipped:
        raise validation("برای هیچ‌یک از ثبت‌نام‌های انتخاب‌شده نامه ساخته نشد", enrollment_ids=", ".join(
            f"{x['enrollment_id']}:{x['reason']}" for x in skipped[:10]))


def build_plans(db: Session, settings: Settings, cal: Any, body: LetterIn, today: date) -> tuple[list[Plan], Skipped]:
    """Returns (plans, skipped). Per-person kinds skip enrollments that cannot be served (no supervisor) and report
    them instead of failing the whole batch; a request where nothing can be built is a 422 naming the reasons."""
    kind, extra = body.kind, body.extra
    conf = effective_conf(db, settings)
    if kind in RUN_KINDS:
        run = load_run(db, body.run_id)
        return [_run_plan(db, cal, kind, run, body.enrollment_ids, extra, today, conf)], []
    ids = body.enrollment_ids
    if not ids:
        raise validation("فهرست ثبت‌نام‌ها لازم است؛ حداقل یک ثبت‌نام انتخاب کنید", enrollment_ids="الزامی است")
    ens = load_enrollments(db, ids)
    base = settings.ticket_url_base
    skipped: Skipped = []
    sups = {m.emp_no: m for m in db.scalars(select(Employee).where(Employee.emp_no.in_(
        {e.employee.supervisor_emp_no for e in ens if e.employee.supervisor_emp_no} or {""})))}
    if kind == "level3_request":
        return [Plan({
            "Ftitle": title_fa(e.employee.gender), "Fname": name_fa(e.employee),
            "En_title": title_en(e.employee.gender), "Reporter__Name": name_en(e.employee),
            "Summary": e.course_name, "link": f"{base}{e.ticket}",
        }, [e.id]) for e in ens], []
    if kind == "level3_manager_check":
        plans = []
        for e in ens:
            sup = e.employee.supervisor_emp_no
            if not sup:
                skipped.append({"enrollment_id": e.id, "reason": "no_supervisor"})
                continue
            mgr = sups.get(sup)
            plans.append(Plan({
                "Manager_fTitle": title_fa(mgr.gender if mgr else ""), "Manager_Fname": name_fa(mgr) if mgr else sup,
                "Manager_Title": title_en(mgr.gender if mgr else ""), "Manager_Name": name_en(mgr) if mgr else sup,
                "Reporter_F_tilte": title_fa(e.employee.gender), "Reporter_Fname": name_fa(e.employee),
                "Reporter_title": title_en(e.employee.gender), "Reporter__Name": name_en(e.employee),
                "Summary": e.course_name, "link": f"{base}{e.ticket}",
            }, [e.id]))
        _no_plans(skipped if not plans else [])
        return plans, skipped
    # line_manager_approval: batches of at most 9 tickets per manager
    batches, orphans = rules.line_manager_batches(ens)
    skipped = [{"enrollment_id": o.id, "reason": "no_supervisor"} for o in orphans]
    plans = []
    for sup, batch in batches:
        mgr = sups.get(sup)
        f: dict[str, Any] = {"Title": title_en(mgr.gender if mgr else ""), "Mg_name": name_en(mgr) if mgr else sup,
                             "employees": [{"name": name_en(e.employee), "summary": e.course_name, "ticket": f"{base}{e.ticket}"}
                                           for e in batch]}
        plans.append(Plan(f, [e.id for e in batch]))
    _no_plans(skipped if not plans else [])
    return plans, skipped


DEFAULTS_FILE = "letter_defaults.json"
_DEFAULT_KEY_MAP = {"signer_name": "letter_signer_name", "signer_title": "letter_signer_title",
                    "signer_email": "letter_signer_email", "signer_phone": "letter_signer_phone"}


def file_defaults(settings: Settings) -> dict[str, str]:
    """templates/letter_defaults.json (see letter_defaults.example.json): deployment-wide letterhead constants."""
    if not settings.templates_dir:
        return {}
    p = Path(settings.templates_dir) / DEFAULTS_FILE
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {_DEFAULT_KEY_MAP.get(k, k): str(v) for k, v in raw.items() if isinstance(v, (str, int)) and str(v).strip()}


def effective_conf(db: Session, settings: Settings) -> dict[str, Any]:
    """Runtime settings (UI) win over the defaults file; blanks in settings fall through to the file."""
    conf = rt.get_all(db)
    for k, v in file_defaults(settings).items():
        if conf.get(k) in ("", None):
            conf[k] = v
    return conf


def _need(values: dict[str, Any], what: str) -> None:
    missing = [k for k, v in values.items() if v in ("", None)]
    if missing:
        raise validation(f"{what} تنظیم نشده است؛ در تنظیمات یا فایل templates/letter_defaults.json مقدار دهید",
                         **{k: "الزامی است" for k in missing})


def _hours(run: CourseRun) -> float | None:
    return float(run.duration_h) if run.duration_h else None


def _sign(conf: dict) -> dict[str, Any]:
    return {k: conf[f"letter_{k}"] for k in ("signer_name", "signer_title", "signer_email", "signer_phone") if conf.get(f"letter_{k}")}


def _run_plan(db: Session, cal: Any, kind: str, run: CourseRun, ids: list[int], extra: dict, today: date, conf: dict) -> Plan:
    c, inst = run.course, run.institute
    ftype = FA_TYPE.get(run.type, run.type)
    h = _hours(run)
    if kind == "course_announcement":
        if not run.start_date:
            raise validation("تاریخ شروع دوره ثبت نشده است", run_id="تاریخ شروع ثبت نشده است")
        f = {
            "Farsi_Course_Name": c.name_fa or c.name, "Farsi_Type": ftype,
            "deadline_farsi": cal.format(run.deadline, "words") if run.deadline else "",
            "Time_Farsi": cal.to_persian_digits(f"{h:g} ساعت") if h else "", "jStart_Date": cal.format(run.start_date, "short"),
            "Date_Horoof": cal.format(run.start_date, "words"), "Day_Farsi": run.days,
            "Time": run.time, "Sessions_Count": str(run.sessions),
            "Course_Name": c.name, "Type": EN_TYPE.get(run.type, run.type),
            "Deadline": run.deadline.strftime("%A-%d-%B-%Y") if run.deadline else "",
            "Duration": f"{h:g} Hours" if h else "", "start_Date": run.start_date.strftime("%Y/%m/%d"),
            "Day": run.days, "link": run.link,
        }
        if extra.get("guide_link"):
            f["guide_link"] = extra["guide_link"]
        return Plan(f)
    ens = _run_enrollments(db, run, ids)
    if not ens:
        raise validation("هیچ شرکت‌کننده‌ای برای این دوره ثبت نشده است", enrollment_ids="خالی است")
    if kind == "institute_letter":
        company = {k: extra.get(k) or conf.get(k, "") for k in COMPANY_KEYS}
        _need(company, "اطلاعات سربرگ شرکت")
        f = {
            "Letter_No": PLACEHOLDER_NO, "date": cal.format(today, "short"), "To": (inst.name_fa or inst.name) if inst else "",
            "Course_Name": c.name_fa or c.name, "Jstart_Date": cal.format(run.start_date, "short") if run.start_date else "",
            "Days": run.days, "Time": run.time, "Duration": f"{h:g} ساعت" if h else "", "Method": ftype,
            "participants": [{"name": name_fa(e.employee), "national_id": e.employee.national_code or "",
                              "phone": e.employee.mobile or "", "email": e.employee.email} for e in ens],
            **company, **_sign(conf),
        }
        if extra.get("Attachment"):
            f["Attachment"] = extra["Attachment"]
        return Plan(f, [e.id for e in ens])
    # settlement_letter
    if run.amount is None:
        raise validation("مبلغ دوره ثبت نشده است", run_id="مبلغ ثبت نشده است")
    yes = db.scalar(select(func.count()).select_from(Enrollment)
                    .where(Enrollment.run_id == run.id, Enrollment.motivation == "Yes")) or 0
    split = rules.invoice_split(run.amount, yes, len(ens))
    purpose = extra.get("purpose", c.name)
    addressee = extra.get("addressee") or conf.get("settlement_addressee", "")
    _need({"addressee": addressee}, "گیرنده نامه تسویه")
    return Plan({
        "addressee": addressee,
        "supplier": (inst.name_fa or inst.name) if inst else "", "invoice_no": extra.get("invoice_no", ""),
        "purpose": purpose, "mtc_no": run.section_b,
        "start_date_greg": run.start_date.strftime("%Y/%m/%d") if run.start_date else "",
        "start_date_jalali": cal.format(run.start_date, "short") if run.start_date else "",
        "attendee_count": str(len(ens)), "supplier_code": inst.supplier_code if inst else "",
        "total": money(split.total), "per_attendee": money(split.per_attendee),
        # one row per attendee with THEIR exact share (shares differ by at most 1 unit and sum to the total exactly)
        "rows": [{"row": i, "staff_id": e.employee.emp_no, "description": f"{purpose}-{run.section_b}-{name_en(e.employee)}",
                  "full_name": name_en(e.employee), "division_cost_center": f"{e.employee.division}-{e.employee.cost_center}",
                  "amount": money(split.shares[i - 1])} for i, e in enumerate(ens, 1)],
        **({"sender_name": conf["letter_signer_name"]} if conf.get("letter_signer_name") else {}),
    }, [e.id for e in ens])


def missing_fields_error(names: list[str]):
    from app.api.errors import ApiError
    return ApiError("validation", "فیلدهای الزامی قالب نامه مقداردهی نشده‌اند", {n: "الزامی است" for n in names})


def check_required(renderer: Any, kind: str, fields: dict, lang: str = "both") -> None:
    missing = [k for k in renderer.required_fields(kind, lang) if k not in fields]
    if missing:
        raise missing_fields_error(missing)


def render(renderer: Any, kind: str, fields: dict, lang: str) -> RenderedLetter:
    check_required(renderer, kind, fields, lang)
    try:
        return renderer.render(kind, fields, lang)
    except Exception as exc:   # noqa: BLE001
        from app.security.redact import scrub
        if isinstance(exc, ValueError) and isinstance(getattr(exc, "fields", None), list):   # Dev-B MissingFieldError
            raise missing_fields_error([str(f) for f in exc.fields]) from None
        raise upstream(f"تولید نامه ناموفق بود: {scrub(exc, 120)}") from None


def safe_filename(name: str, fallback: str) -> str:
    name = re.sub(r"[^\w.\- ]", "_", Path(name or "").name, flags=re.UNICODE).strip(" .") or fallback
    if not name.lower().endswith(".docx"):
        name += ".docx"
    return name[:120]


def get_renderer(settings: Settings) -> Any:
    return gateway.get_factory().build_letter_renderer(settings.templates_dir)


PII_KINDS = {"institute_letter"}       # participants table: national ID, phone


def preview(db: Session, settings: Settings, body: LetterIn, today: date) -> dict:
    f = gateway.get_factory()
    plans, skipped = build_plans(db, settings, f.build_calendar(), body, today)
    r = render(get_renderer(settings), body.kind, plans[0].fields, body.lang)
    return {"kind": body.kind, "subject": r.subject, "html": r.html_body, "filename": r.filename, "count": len(plans),
            "skipped": skipped, "missing_fields": []}     # missing fields are a 422 naming them (see missing_fields_error)


def mark_level3(db: Session, kind: str, enrollment_ids: list[int]) -> None:
    """Closing the Level-3 loop: generating the request letter starts Level 3 (the enrollment leaves every due list and
    the dashboard); the manager check only advances the status. Idempotent -- repeating changes nothing."""
    if kind not in ("level3_request", "level3_manager_check") or not enrollment_ids:
        return
    for e in db.scalars(select(Enrollment).where(Enrollment.id.in_(enrollment_ids))):
        if kind == "level3_request":
            e.level3_sent = True
            if not e.level3_status or e.level3_status == "pending":
                e.level3_status = "requested"
        elif not e.level3_status or e.level3_status in ("pending", "requested"):
            e.level3_status = "manager_check"


def create(db: Session, sf: sessionmaker[Session], settings: Settings, user: User | None, body: LetterIn,
           today: date, ip: str = "", *, mark: bool = True) -> tuple[list[Letter], Skipped]:
    f = gateway.get_factory()
    plans, skipped = build_plans(db, settings, f.build_calendar(), body, today)
    renderer = get_renderer(settings)
    for p in plans:   # fail before consuming numbers
        check_required(renderer, body.kind, p.fields, body.lang)
    conf = rt.get_all(db)
    storage = settings.storage_path / "letters"
    storage.mkdir(parents=True, exist_ok=True)
    out: list[Letter] = []
    written: list[Path] = []
    try:
        # every number is allocated (own short transactions) BEFORE this session writes anything:
        # SQLite allows one writer, so interleaving would self-deadlock on a multi-letter batch.
        allocated = [numbering.next_number(sf, body.kind, int(conf["letter_number_start"]), str(conf["letter_number_prefix"]))
                     for _ in plans]
        for p, (seq, number) in zip(plans, allocated, strict=True):
            fields = dict(p.fields)
            if body.kind == "institute_letter":
                fields["Letter_No"] = number
            r = render(renderer, body.kind, fields, body.lang)
            fname = safe_filename(r.filename, f"{body.kind}-{seq}.docx")
            letter = Letter(kind=body.kind, run_id=body.run_id, seq=seq, number=number, lang=body.lang, filename=fname,
                            file_path="", subject=r.subject[:500], html_body=r.html_body, enrollment_ids=p.enrollment_ids,
                            created_by=user.id if user else None)      # html_body is stored encrypted (EncryptedTextCompat)
            db.add(letter)
            db.flush()
            path = storage / f"{letter.id}_{fname}"
            path.write_bytes(get_cipher().encrypt_bytes(r.docx_bytes, FILE_CONTEXT))     # at rest: AES-GCM, not a readable .docx
            written.append(path)
            letter.file_path = str(path.relative_to(settings.storage_path))
            if mark:
                mark_level3(db, body.kind, p.enrollment_ids)
            audit(db, "letter.create", user=user, actor="" if user else "scheduler", entity="letter", entity_id=letter.id, ip=ip,
                  detail={"kind": body.kind, "number": number, "run_id": body.run_id, "enrollments": len(p.enrollment_ids),
                          "pii_included": body.kind in PII_KINDS, "skipped": len(skipped)})
            out.append(letter)
        db.commit()
    except Exception:
        db.rollback()
        for w in written:
            w.unlink(missing_ok=True)
        raise
    return out, skipped


FILE_CONTEXT = "letter.file"


def file_for(settings: Settings, letter: Letter) -> Path:
    root = settings.storage_path
    p = (root / letter.file_path).resolve()
    if root not in p.parents or not p.is_file():
        raise not_found("فایل نامه")
    return p


def read_letter_file(settings: Settings, letter: Letter) -> bytes:
    """Decrypted .docx bytes. Files written before at-rest encryption (zip magic) are returned as they are."""
    blob = file_for(settings, letter).read_bytes()
    return blob if blob[:2] == b"PK" else get_cipher().decrypt_bytes(blob, FILE_CONTEXT)
