"""User-editable message templates: seeds, versioning, defaults, strict rendering, real/sample context."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, forbidden, not_found, validation
from app.api.services import field_catalog as fc
from app.api.services import letters as letters_svc
from app.api.services import rich_text
from app.audit import record as audit
from app.config import Settings
from app.models import MessageTemplate, MessageTemplateVersion, User
from app.schemas.domain import LetterIn

LANGS = ("fa", "en", "both")


def chip(key: str, sample: str = "") -> str:
    return f'<span data-field="{key}">{sample or key}</span>'


def _p(*parts: str, rtl: bool = True) -> str:
    return f'<p dir="{"rtl" if rtl else "ltr"}">' + "".join(parts) + "</p>"


# kind -> (name, subject, body). Every key must exist in the field catalogue (tests check it).
SEEDS: dict[str, tuple[str, str, str]] = {
    "email_announcement": ("اطلاعیهٔ دوره", "اطلاعیه دورهٔ {{Farsi_Course_Name}} / Course announcement: {{Course_Name}}",
                           _p("همکار گرامی، دورهٔ «", chip("Farsi_Course_Name"), "» از تاریخ ", chip("jStart_Date"), " (", chip("Day_Farsi"),
                              ") برگزار می‌شود. مهلت ثبت‌نام: ", chip("deadline_farsi"), ". پیوند: ", chip("link")) +
                           _p("Dear colleague, the course ", chip("Course_Name"), " starts on ", chip("start_Date"), " (", chip("Day"),
                              "). Registration deadline: ", chip("Deadline"), ". Link: ", chip("link"), rtl=False)),
    "email_reminder": ("یادآوری مهلت ثبت‌نام", "یادآوری مهلت ثبت‌نام — {{Farsi_Course_Name}}",
                       _p("همکار گرامی، مهلت ثبت‌نام دورهٔ «", chip("Farsi_Course_Name"), "» تا ", chip("deadline_farsi"),
                          " است؛ لطفاً موتیویشن خود را تکمیل کنید. ", chip("link"))),
    "email_level3": ("درخواست ارزیابی سطح ۳", "ارزیابی سطح ۳ — {{Summary}}",
                     _p(chip("Ftitle"), " ", chip("Fname"), "، لطفاً ارزیابی سطح ۳ دورهٔ «", chip("Summary"), "» را از طریق این پیوند تکمیل کنید: ",
                        chip("link"))),
    "email_manager_check": ("تأیید مدیر برای ارزیابی سطح ۳", "تأیید مدیر — {{Reporter__Name}}",
                            _p(chip("Manager_fTitle"), " ", chip("Manager_Fname"), "، لطفاً ارزیابی ", chip("Reporter_F_tilte"), " ",
                               chip("Reporter_Fname"), " دربارهٔ دورهٔ «", chip("Summary"), "» را تأیید کنید: ", chip("link"))),
    "email_institute": ("نامه به مؤسسه", "ثبت‌نام در دورهٔ {{Course_Name}}",
                        _p("به: ", chip("To"), ". پیرو هماهنگی، فهرست شرکت‌کنندگان دورهٔ «", chip("Course_Name"), "» از تاریخ ", chip("Jstart_Date"),
                           " به شرح زیر است:") + _p(chip("participants"))),
    "email_settlement": ("نامهٔ تسویه", "تسویه فاکتور {{invoice_no}} — {{supplier}}",
                         _p(chip("addressee"), " گرامی، تسویهٔ فاکتور ", chip("invoice_no"), " ", chip("supplier"), " برای «", chip("purpose"),
                            "» (", chip("mtc_no"), ") به مبلغ ", chip("invoice_total"), " ریال، سهم هر نفر ", chip("per_attendee"), " ریال.",
                            rtl=True)),
    "email_generic": ("پیام عمومی", "{{Farsi_Course_Name}}", _p("همکار گرامی، دربارهٔ دورهٔ «", chip("Farsi_Course_Name"), "»: ", chip("link"))),
}
# the six letter kinds get a system e-mail body too (the text that travels with the letter)
LETTER_SEED_FROM = {"course_announcement": "email_announcement", "institute_letter": "email_institute", "settlement_letter": "email_settlement",
                    "level3_request": "email_level3", "level3_manager_check": "email_manager_check", "line_manager_approval": "email_generic"}


def ensure_system(db: Session) -> None:
    """Idempotent: one default system template per kind (fa+en body, lang 'both')."""
    have = {k for (k,) in db.execute(select(MessageTemplate.kind).where(MessageTemplate.is_system.is_(True)))}
    for kind in fc.ALL_KINDS:
        if kind in have:
            continue
        name, subject, body = SEEDS.get(kind) or SEEDS[LETTER_SEED_FROM[kind]]
        t = MessageTemplate(kind=kind, name=f"{name} (پیش‌فرض سیستم)" if kind in fc.EMAIL_KINDS else f"متن ایمیل نامه — {name}",
                            lang="both", subject=subject, body_html=rich_text.sanitize(body), is_system=True,
                            is_default=not db.scalar(select(func.count()).select_from(MessageTemplate)
                                                     .where(MessageTemplate.kind == kind, MessageTemplate.lang == "both",
                                                            MessageTemplate.is_default.is_(True))))
        db.add(t)
        db.flush()
        _snapshot(db, t, None)
    db.commit()


def _snapshot(db: Session, t: MessageTemplate, user: User | None) -> None:
    db.add(MessageTemplateVersion(template_id=t.id, version=t.version, name=t.name, lang=t.lang, subject=t.subject, body_html=t.body_html,
                                  created_by=user.id if user else None))


def clean_subject(subject: str) -> str:
    if "\n" in subject or "\r" in subject or "\x00" in subject:
        raise validation("موضوع نباید شامل خط جدید باشد", subject="خط جدید مجاز نیست")
    return subject.strip()


def load(db: Session, tid: int) -> MessageTemplate:
    t = db.get(MessageTemplate, tid)
    if not t:
        raise not_found("قالب")
    return t


def writable(t: MessageTemplate) -> None:
    if t.is_system:
        raise forbidden("قالب سیستمی فقط‌خواندنی است؛ برای شخصی‌سازی از «نسخه‌برداری» استفاده کنید")


def make_default(db: Session, t: MessageTemplate) -> None:
    db.execute(update(MessageTemplate).where(MessageTemplate.kind == t.kind, MessageTemplate.lang == t.lang, MessageTemplate.id != t.id)
               .values(is_default=False))
    t.is_default = True


def create(db: Session, user: User, kind: str, name: str, lang: str, subject: str, body_html: str, ip: str = "") -> MessageTemplate:
    if kind not in fc.ALL_KINDS:
        raise validation("نوع قالب نامعتبر است", kind="نوع مجاز نیست")
    t = MessageTemplate(kind=kind, name=name.strip(), lang=lang, subject=clean_subject(subject), body_html=rich_text.sanitize(body_html),
                        created_by=user.id)
    db.add(t)
    db.flush()
    _snapshot(db, t, user)
    if not db.scalar(select(func.count()).select_from(MessageTemplate).where(MessageTemplate.kind == kind, MessageTemplate.lang == lang,
                                                                          MessageTemplate.is_default.is_(True))):
        t.is_default = True
    audit(db, "template.create", user=user, entity="template", entity_id=t.id, ip=ip, detail={"kind": kind, "lang": lang})
    return t


def update_fields(db: Session, user: User, t: MessageTemplate, data: dict, ip: str = "") -> MessageTemplate:
    writable(t)
    changed = False
    new = {"name": t.name, "lang": t.lang, "subject": t.subject, "body_html": t.body_html}
    for k in ("name", "lang", "subject", "body_html"):
        if k in data and data[k] is not None:
            v = data[k]
            v = rich_text.sanitize(v) if k == "body_html" else (clean_subject(v) if k == "subject" else v.strip())
            if v != new[k]:
                new[k], changed = v, True
    if not changed:
        return t
    if new["lang"] != t.lang:
        t.is_default = False
    t.name, t.lang, t.subject, t.body_html = new["name"], new["lang"], new["subject"], new["body_html"]
    t.version += 1
    db.flush()
    _snapshot(db, t, user)
    audit(db, "template.update", user=user, entity="template", entity_id=t.id, ip=ip, detail={"version": t.version, "fields": sorted(data)})
    return t


def restore(db: Session, user: User, t: MessageTemplate, version: int, ip: str = "") -> MessageTemplate:
    writable(t)
    v = db.scalar(select(MessageTemplateVersion).where(MessageTemplateVersion.template_id == t.id, MessageTemplateVersion.version == version))
    if not v:
        raise not_found("نسخهٔ قالب")
    t.name, t.lang, t.subject, t.body_html = v.name, v.lang, v.subject, v.body_html
    t.version += 1
    db.flush()
    _snapshot(db, t, user)
    audit(db, "template.restore", user=user, entity="template", entity_id=t.id, ip=ip, detail={"from_version": version, "version": t.version})
    return t


def duplicate(db: Session, user: User, t: MessageTemplate, ip: str = "") -> MessageTemplate:
    c = MessageTemplate(kind=t.kind, name=f"{t.name} (کپی)"[:200], lang=t.lang, subject=t.subject, body_html=t.body_html, created_by=user.id)
    db.add(c)
    db.flush()
    _snapshot(db, c, user)
    audit(db, "template.duplicate", user=user, entity="template", entity_id=c.id, ip=ip, detail={"from": t.id})
    return c


def delete(db: Session, user: User, t: MessageTemplate, ip: str = "") -> None:
    writable(t)
    if t.is_default:
        raise conflict("این قالب پیش‌فرض است؛ ابتدا قالب دیگری را پیش‌فرض کنید")
    audit(db, "template.delete", user=user, entity="template", entity_id=t.id, ip=ip, detail={"kind": t.kind})
    db.delete(t)


# ---- rendering ------------------------------------------------------------------------------------------------------
def context_fields(db: Session, settings: Settings, kind: str, run_id: int | None, enrollment_id: int | None,
                   today: date | None = None) -> tuple[dict, str]:
    """(fields, 'sample'|'real'). Real data comes from the code that builds a letter: a preview shows exactly what a letter gets."""
    if not run_id and not enrollment_id:
        return fc.sample_fields(), "sample"
    from app.api.services import gateway
    sk = fc.source_kind(kind)
    body = LetterIn(kind=sk, run_id=run_id, enrollment_ids=[enrollment_id] if enrollment_id else [])
    if sk not in letters_svc.RUN_KINDS and not enrollment_id:
        raise validation("شناسهٔ ثبت‌نام لازم است", enrollment_id="الزامی است")
    plans, _ = letters_svc.build_plans(db, settings, gateway.get_factory().build_calendar(), body, today or date.today())
    f = fc.with_aliases(plans[0].fields)
    return f, "real"


def render(t_subject: str, t_body: str, fields: dict) -> dict:
    known = fc.known_keys()
    body = rich_text.render_html(t_body, fields, known)
    subject, u2, m2 = rich_text.render_text(t_subject, fields, known)
    return {"subject": subject, "html": body.html, "used_fields": body.used,
            "unknown_fields": sorted(set(body.unknown_fields) | set(u2)), "missing_fields": sorted(set(body.missing_fields) | set(m2))}


def render_strict(t: MessageTemplate, fields: dict) -> dict:
    """For letters / e-mail: unknown or blank fields are a 422 naming every one (never a half-empty message)."""
    out = render(t.subject, t.body_html, fields)
    bad = {k: "ناشناخته است" for k in out["unknown_fields"]} | {k: "مقدار ندارد" for k in out["missing_fields"]}
    if bad:
        raise ApiError("validation", "قالب به فیلدهایی اشاره می‌کند که ناشناخته‌اند یا مقدار ندارند", bad)
    return out


def load_for_use(db: Session, tid: int, kind: str) -> MessageTemplate:
    t = load(db, tid)
    if t.kind != kind and fc.EMAIL_SOURCE.get(t.kind) != kind:
        raise validation("این قالب برای این نوع نامه نیست", template_id="نوع قالب با نوع نامه سازگار نیست")
    return t
