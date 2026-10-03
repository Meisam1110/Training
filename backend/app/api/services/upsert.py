"""Idempotent upserts used by sync, imports and the legacy workbook loader.

Keys: Employee.emp_no, Enrollment.ticket, CourseRun.run_key (course|institute|start).
Running the same input twice yields created=0, updated=0 the second time.
Error strings are built from row numbers and field names only -- never values (no PII).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from itertools import islice
from typing import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import EmployeeRecord, IdpRow, LegacyData, RecordRow, RunRecord, SyncReport
from app.models import Course, CourseRun, Employee, Enrollment, EnrollmentOffer, Institute, utcnow

MAX_ERRORS = 100
_BRACKET = re.compile(r"\s*\[.*?\]\s*")


def _err(rep: SyncReport, sheet: str, row: int | None, column: str, code: str, reason: str) -> None:
    """Row-level problem: position + column + fixed reason text. Never a cell value (no PII)."""
    if len(rep.errors) < MAX_ERRORS:
        rep.errors.append({"sheet": sheet, "row": row, "column": column, "code": code, "reason": reason})  # type: ignore[arg-type]


def new_report(source: str) -> SyncReport:
    return SyncReport(source=source, started_at=utcnow())


def make_run_key(course: str, institute: str, start: date | None) -> str:
    parts = (" ".join((course or "").casefold().split()), " ".join((institute or "").casefold().split()),
             start.isoformat() if start else "")
    return "|".join(parts)[:600]


def get_course(db: Session, name: str, name_fa: str = "", category: str = "") -> Course:
    name = name.strip()
    c = db.scalar(select(Course).where(Course.name == name))
    if not c:
        c = Course(name=name[:300], name_fa=name_fa[:300], category=category[:100])
        db.add(c)
        db.flush()
    elif name_fa and not c.name_fa:
        c.name_fa = name_fa[:300]
    return c


def get_institute(db: Session, name: str) -> Institute | None:
    name = (name or "").strip()
    if not name:
        return None
    i = db.scalar(select(Institute).where(Institute.name == name))
    if not i:
        i = Institute(name=name[:200])
        db.add(i)
        db.flush()
    return i


MANUAL_ATTR = {"motivation": "motivation", "registration": "registration", "calendar": "calendar", "attendance": "attendance_status",
               "payment": "payment", "comment": "comment"}
EMP_LIMITS = {"first_name_en": 100, "last_name_en": 100, "first_name_fa": 100, "last_name_fa": 100, "gender": 8, "email": 200,
              "mobile": 64, "national_code": 64, "division": 200, "cost_center": 64, "org_code": 64, "position_title": 200,
              "supervisor_emp_no": 32, "status": 32}


def manual_attrs(e: Enrollment) -> set[str]:
    """Columns a person edited by hand. Precedence: manual edit > import (until released via PATCH release_fields)."""
    return {MANUAL_ATTR[k] for k in (e.manual_fields or []) if k in MANUAL_ATTR}


def _apply(obj, values: dict, skip: set[str] | frozenset[str] = frozenset()) -> bool:
    changed = False
    for k, v in values.items():
        if k in skip:
            continue
        if getattr(obj, k) != v:
            setattr(obj, k, v)
            changed = True
    return changed


def _chunks(it: Iterable, n: int) -> Iterator[list]:
    iterator = iter(it)
    while batch := list(islice(iterator, n)):
        yield batch


def _size(rep: SyncReport) -> int:
    return int(getattr(rep, "chunk", 500) or 500)


def _end_chunk(db: Session, rep: SyncReport) -> None:
    """Bounded memory + durable progress: commit, drop every loaded object, tell the job (heartbeat)."""
    db.commit()
    db.expunge_all()
    hook = getattr(rep, "hook", None)
    if hook:
        hook(rep)


def _emp_lookup(db: Session, emp_nos: Iterable[str]) -> dict[str, Employee]:
    nos = set(emp_nos)
    return {e.emp_no: e for e in db.scalars(select(Employee).where(Employee.emp_no.in_(nos)))} if nos else {}


# ---- employees ---------------------------------------------------------------------------------------------------
def _prep_employee(r: EmployeeRecord):
    emp_no = (r.emp_no or "").strip()
    if not emp_no or len(emp_no) > 32:
        return None, ("emp_no", "invalid_emp_no", "شماره پرسنلی خالی یا نامعتبر است")
    vals = {
        "first_name_en": r.first_name_en, "last_name_en": r.last_name_en, "first_name_fa": r.first_name_fa,
        "last_name_fa": r.last_name_fa, "gender": r.gender, "email": r.email.strip().lower(),
        "mobile": r.mobile, "national_code": r.national_code, "division": r.division,
        "cost_center": r.cost_center, "org_code": r.org_code, "position_title": r.position_title,
        "supervisor_emp_no": r.supervisor_emp_no,
    }
    # a blank incoming value means "the source has no info", never "erase"
    vals = {k: (v or "").strip() if isinstance(v, str) else v for k, v in vals.items()}
    vals = {k: v for k, v in vals.items() if v != ""}
    vals["status"] = (r.status or "Active").strip() or "Active"
    for k, v in vals.items():
        if len(str(v)) > EMP_LIMITS[k]:
            return None, (k, "too_long", "طول مقدار بیش از حد مجاز ستون است")
    return (emp_no, vals), None


def _upsert_employee_one(db: Session, local: dict[str, Employee], emp_no: str, vals: dict, source: str, made: list[str]) -> str:
    e = local.get(emp_no)
    if e is None:
        e = Employee(emp_no=emp_no, source=source, **vals)
        db.add(e)
        local[emp_no] = e
        made.append(emp_no)
        return "created"
    vals = {**vals, "source": source if e.source in ("idp", "manual") else e.source}
    return "updated" if _apply(e, vals) else "unchanged"


def _employee_batch(db: Session, rows: list[tuple[int, str, dict]], source: str, rep: SyncReport) -> None:
    if not rows:
        return
    counts: Counter = Counter()
    local = _emp_lookup(db, [no for _, no, _ in rows])
    made: list[str] = []
    try:
        with db.begin_nested():
            for _, no, vals in rows:
                counts[_upsert_employee_one(db, local, no, vals, source, made)] += 1
            db.flush()
    except Exception:   # noqa: BLE001 - one bad row (e.g. a DB constraint) must not abort the whole import
        counts = Counter()
        local = _emp_lookup(db, [no for _, no, _ in rows])
        for i, no, vals in rows:
            try:
                with db.begin_nested():
                    counts[_upsert_employee_one(db, local, no, vals, source, [])] += 1
                    db.flush()
            except Exception:   # noqa: BLE001
                local = _emp_lookup(db, [n for _, n, _ in rows])
                rep.skipped += 1
                _err(rep, "employees", i, "", "db_error", "ردیف توسط پایگاه داده پذیرفته نشد")
    rep.created += counts["created"]
    rep.updated += counts["updated"]
    rep.unchanged += counts["unchanged"]


def upsert_employees(db: Session, records: Iterable[EmployeeRecord], source: str, rep: SyncReport) -> None:
    """Streaming: fixed-size chunks, one commit per chunk, so 60,000 records never sit in memory together."""
    idx = 0
    for batch in _chunks(records, _size(rep)):
        rows = []
        for r in batch:
            idx += 1
            prepared, err = _prep_employee(r)
            if err:
                rep.skipped += 1
                _err(rep, "employees", idx, err[0], err[1], err[2])
            else:
                rows.append((idx, *prepared))
        _employee_batch(db, rows, source, rep)
        _end_chunk(db, rep)


def _stub_employee(db: Session, cache: dict[str, Employee], emp_no: str, name: str, dept: str, rep: SyncReport) -> Employee:
    clean = _BRACKET.sub(" ", name or "").strip()
    first, _, last = clean.partition(" ")
    e = Employee(emp_no=emp_no, first_name_en=first[:100], last_name_en=last.strip()[:100], division=dept[:200],
                 status="Unknown", source="idp")
    db.add(e)
    db.flush()
    cache[emp_no] = e
    rep.created += 1
    return e


def _sec_b(v: str) -> str:
    v = (v or "").strip()
    return "" if v == "-" else v


# ---- IDP -----------------------------------------------------------------------------------------------------------
def upsert_idp(db: Session, rows: Iterable[IdpRow], rep: SyncReport) -> None:
    idx = 0
    for batch in _chunks(rows, _size(rep)):
        prepared = []
        for r in batch:
            idx += 1
            ticket, emp_no = (r.ticket or "").strip(), (r.emp_no or "").strip()
            if not ticket or not emp_no or len(ticket) > 32 or len(emp_no) > 32:
                rep.skipped += 1
                _err(rep, "idp", idx, "ticket/emp_no", "invalid_key", "تیکت یا شماره پرسنلی خالی یا نامعتبر است")
            elif not (r.summary or "").strip():
                rep.skipped += 1
                _err(rep, "idp", idx, "summary", "missing_course_name", "نام دوره خالی است")
            else:
                prepared.append((idx, ticket, emp_no, r))
        emps = _emp_lookup(db, [p[2] for p in prepared])
        ens = ({e.ticket: e for e in db.scalars(select(Enrollment).where(Enrollment.ticket.in_({p[1] for p in prepared})))}
               if prepared else {})
        for i, ticket, emp_no, r in prepared:
            e = ens.get(ticket)
            emp = emps.get(emp_no)
            if e is not None and emp is not None and e.employee_id != emp.id:
                rep.skipped += 1          # a ticket never silently changes owner
                _err(rep, "idp", i, "emp_no", "ticket_owner_conflict", "تیکت قبلاً به کارمند دیگری اختصاص یافته است؛ ردیف نادیده گرفته شد")
                continue
            if e is not None and emp is None:
                emp = db.get(Employee, e.employee_id)
                if emp is None or emp.emp_no != emp_no:
                    rep.skipped += 1
                    _err(rep, "idp", i, "emp_no", "ticket_owner_conflict", "تیکت قبلاً به کارمند دیگری اختصاص یافته است؛ ردیف نادیده گرفته شد")
                    continue
            emp = emp or _stub_employee(db, emps, emp_no, r.reporter_name, r.department, rep)
            vals = {
                "employee_id": emp.id, "course_name": r.summary.strip()[:300], "category": (r.course_category or "")[:100],
                "delivery_method": (r.delivery_method or "")[:50], "idp_type": (r.idp_type or "")[:50],
                "job_level": (r.job_level or "")[:50], "department": (r.department or "")[:200],
                "current_status": (r.current_status or "")[:100], "attendance_status": (r.attendance_status or "-")[:50],
                "start_date": r.start_date, "end_date": r.end_date, "section_b": _sec_b(r.section_b)[:64],
            }
            if e is None:
                e = Enrollment(ticket=ticket, **vals)
                db.add(e)
                ens[ticket] = e
                rep.created += 1
            elif _apply(e, vals, manual_attrs(e)):
                rep.updated += 1
            else:
                rep.unchanged += 1
        db.flush()
        _end_chunk(db, rep)


def upsert_run_record(db: Session, r: RunRecord, rep: SyncReport, runs: dict[str, CourseRun], row: int | None = None) -> CourseRun | None:
    if not (r.course_name or "").strip():
        rep.skipped += 1
        _err(rep, "runs", row, "course_name", "missing_course_name", "نام دوره خالی است")
        return None
    course = get_course(db, r.course_name, r.course_name_fa)
    inst = get_institute(db, r.institute)
    key = make_run_key(r.course_name, r.institute, r.start_date)
    vals = {
        "course_id": course.id, "institute_id": inst.id if inst else None,
        "type": r.type if r.type in ("online", "in_person") else "in_person",
        "duration_h": r.duration_h, "start_date": r.start_date, "end_date": r.end_date, "days": r.days[:100],
        "time": r.time[:50], "sessions": int(r.sessions or 0), "send_date": r.send_date, "deadline": r.deadline,
        "amount": r.amount, "section_b": _sec_b(r.section_b)[:64], "link": (r.link or "")[:500],
    }
    run = runs.get(key)
    if run is None:
        run = CourseRun(run_key=key, **vals)
        db.add(run)
        db.flush()
        runs[key] = run
        rep.created += 1
    else:
        # Decimal vs float from the source: compare numerically
        cur_amt = float(run.amount) if run.amount is not None else None
        if cur_amt == (float(vals["amount"]) if vals["amount"] is not None else None):
            vals["amount"] = run.amount
        cur_dur = float(run.duration_h) if run.duration_h is not None else None
        if cur_dur == (float(vals["duration_h"]) if vals["duration_h"] is not None else None):
            vals["duration_h"] = run.duration_h
        if _apply(run, vals):
            rep.updated += 1
        else:
            rep.unchanged += 1
    return run


def upsert_record_row(db: Session, r: RecordRow, rep: SyncReport, emps: dict[str, Employee],
                      existing: dict[str, Enrollment], runs: dict[str, CourseRun],
                      offers: dict[tuple[int, str], EnrollmentOffer], is_current: bool, row: int | None = None) -> None:
    """One legacy Record row = one offer of the ticket. Every row is kept as an EnrollmentOffer (so the
    per-ticket count of non-"Yes" motivations is exact); the enrollment itself follows the row whose run
    starts last. Manual edits win; a blank incoming value never erases a stored one."""
    ticket = (r.ticket or "").strip()
    if not ticket:
        rep.skipped += 1
        _err(rep, "records", row, "ticket", "missing_ticket", "تیکت خالی است")
        return
    e = existing.get(ticket)
    emp = emps.get((r.emp_no or "").strip())
    run = runs.get(make_run_key(r.course_name, r.institute, r.start_date))
    mot = (r.motivation or "").strip()
    mot = "Yes" if mot.casefold() == "yes" else ("No" if mot.casefold() == "no" else "")
    vals = {"motivation": mot, "registration": (r.registration or "")[:50], "calendar": (r.calendar or "")[:50],
            "payment": (r.payment or "")[:100], "comment": r.comment or ""}
    created = False
    if e is None:
        if not emp:
            rep.skipped += 1
            _err(rep, "records", row, "emp_no", "unknown_employee", "کارمند در فهرست کارکنان نیست")
            return
        e = Enrollment(ticket=ticket, employee_id=emp.id, course_name=r.course_name[:300], start_date=r.start_date)
        db.add(e)
        db.flush()
        existing[ticket] = e
        created = True
    elif emp is not None and e.employee_id != emp.id:
        rep.skipped += 1
        _err(rep, "records", row, "emp_no", "ticket_owner_conflict", "تیکت قبلاً به کارمند دیگری اختصاص یافته است؛ ردیف نادیده گرفته شد")
        return
    else:
        vals = {k: v for k, v in vals.items() if v != "" or not getattr(e, k)}
    changed = False
    if is_current:
        changed = _apply(e, {**vals, **({"run_id": run.id} if run is not None else {})}, manual_attrs(e))
    key = run.run_key if run else f"legacy|{r.start_date}|{make_run_key(r.course_name, r.institute, r.start_date)}"
    o = offers.get((e.id, key))
    if o is None:
        o = EnrollmentOffer(enrollment_id=e.id, run_id=run.id if run else None, offer_key=key[:600], motivation=mot)
        db.add(o)
        offers[(e.id, key)] = o
        changed = True
    elif o.motivation != mot or o.run_id != (run.id if run else None):
        o.motivation, o.run_id = mot, (run.id if run else None)
        changed = True
    if created:
        rep.created += 1
    elif changed:
        rep.updated += 1
    else:
        rep.unchanged += 1


def upsert_legacy(db: Session, data: LegacyData, rep: SyncReport) -> None:
    upsert_employees(db, data.employees, "excel", rep)
    upsert_idp(db, data.idp, rep)
    runs = {r.run_key: r for r in db.scalars(select(CourseRun))}
    for n, rr in enumerate(data.runs, 1):
        upsert_run_record(db, rr, rep, runs, n)
    db.flush()
    winner: dict[str, int] = {}          # the ticket's CURRENT row = the one whose run starts last (later row wins ties)
    for i, rec in enumerate(data.records):
        t = (rec.ticket or "").strip()
        if t and (t not in winner or (rec.start_date or date.min) >= (data.records[winner[t]].start_date or date.min)):
            winner[t] = i
    for start in range(0, len(data.records), _size(rep)):
        batch = data.records[start:start + _size(rep)]
        emps = _emp_lookup(db, [(r.emp_no or "").strip() for r in batch])
        existing = ({e.ticket: e for e in db.scalars(select(Enrollment).where(Enrollment.ticket.in_({(r.ticket or "").strip() for r in batch})))})
        offers = ({(o.enrollment_id, o.offer_key): o
                   for o in db.scalars(select(EnrollmentOffer).where(EnrollmentOffer.enrollment_id.in_([e.id for e in existing.values()])))}
                  if existing else {})
        for j, rec in enumerate(batch):
            i = start + j
            upsert_record_row(db, rec, rep, emps, existing, runs, offers, winner.get((rec.ticket or "").strip()) == i, i + 1)
        db.flush()
        _end_chunk(db, rep)


def finish(rep: SyncReport) -> SyncReport:
    rep.finished_at = utcnow()
    return rep


def to_datetime(x: date | datetime | None) -> datetime | None:
    if isinstance(x, datetime):
        return x
    return datetime(x.year, x.month, x.day) if x else None
