from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.errors import conflict, not_found, validation
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import rules
from app.api.services import serializers as ser
from app.audit import record as audit
from app.config import Settings
from app.deps import PathId, client_ip, get_db, get_settings, require
from app.models import CourseRun, Employee, Enrollment, User
from app.schemas.domain import INT_MAX, BulkIn, EnrollmentPatch

router = APIRouter(tags=["enrollments"])
SORT = {"id": Enrollment.id, "ticket": Enrollment.ticket, "course_name": Enrollment.course_name,
        "end_date": Enrollment.end_date, "start_date": Enrollment.start_date, "motivation": Enrollment.motivation,
        "current_status": Enrollment.current_status}


def _base():
    return select(Enrollment).options(joinedload(Enrollment.employee), joinedload(Enrollment.run))


def _list_enrollments(db: Session, p: PageParams, settings: Settings, *, run_id: int | None = None, emp_no: str = "",
                      motivation: str | None = None, unassigned: bool = False, status: str = "", attendance: str = ""):
    stmt = _base().join(Employee)
    if run_id is not None:
        stmt = stmt.where(Enrollment.run_id == run_id)
    if unassigned:
        stmt = stmt.where(Enrollment.run_id.is_(None))
    if emp_no:
        stmt = stmt.where(Employee.emp_no == emp_no)
    if motivation is not None:
        stmt = stmt.where(Enrollment.motivation == ("" if motivation in ("none", "") else motivation))
    if status:
        stmt = stmt.where(Enrollment.current_status == status)
    if attendance:
        stmt = stmt.where(Enrollment.attendance_status == attendance)
    if p.q:
        k = like(p.q)
        stmt = stmt.where(Enrollment.ticket.ilike(k, escape="\\") | Enrollment.course_name.ilike(k, escape="\\") |
                          Employee.emp_no.ilike(k, escape="\\") | Employee.last_name_en.ilike(k, escape="\\") |
                          Employee.first_name_en.ilike(k, escape="\\"))
    sup = ser.SupervisorEmails(db)
    return paginate(db, apply_sort(stmt, p.sort, SORT, "id"), p, lambda e: ser.enrollment(e, settings.ticket_url_base, sup),
                    prepare=lambda rows: sup.prefetch(e.employee.supervisor_emp_no for e in rows))


@router.get("/enrollments")
def list_enrollments(p: PageParams = Depends(), run_id: int | None = Query(None, ge=1, le=INT_MAX), emp_no: str = Query("", max_length=32),
                     motivation: str | None = Query(None, pattern="^(Yes|No|none)?$"), unassigned: bool = False,
                     status: str = Query("", max_length=100), attendance: str = Query("", max_length=50),
                     db: Session = Depends(get_db), settings: Settings = Depends(get_settings), _=Depends(require("viewer"))):
    return _list_enrollments(db, p, settings, run_id=run_id, emp_no=emp_no, motivation=motivation,
                             unassigned=unassigned, status=status, attendance=attendance)


def _apply(db: Session, e: Enrollment, data: dict, run: CourseRun | None) -> None:
    if data.get("unassign"):
        e.run_id = None
    elif data.get("run_id") is not None:
        cand_dates = (run.start_date, run.end_date or run.start_date)
        for o in db.scalars(_base().where(Enrollment.employee_id == e.employee_id, Enrollment.id != e.id,
                                          Enrollment.status != "cancelled", Enrollment.run_id.is_not(None))).unique():
            if o.run_id != run.id and rules.overlaps(cand_dates, rules.eff_dates(o)):
                raise conflict("تاریخ این دوره با دورهٔ دیگری از همین کارمند هم‌پوشانی دارد")
        if e.run_id != run.id and data.get("motivation") is None:
            e.motivation = ""            # a new offer starts without a motivation answer
        e.run_id = run.id
        e.run = run
    manual = set(e.manual_fields or [])
    for k, attr in (("motivation", "motivation"), ("registration", "registration"), ("calendar", "calendar"),
                    ("attendance", "attendance_status"), ("payment", "payment"), ("comment", "comment")):
        if data.get(k) is not None:
            setattr(e, attr, data[k])
            manual.add(k)                    # a person set it: imports must not overwrite it (docs: precedence)
    for k in data.get("release_fields") or []:
        manual.discard(k)
    if manual != set(e.manual_fields or []):
        e.manual_fields = sorted(manual)
    if data.get("level3_status") is not None:
        e.level3_status = data["level3_status"]
    if data.get("level3_sent") is not None:
        e.level3_sent = data["level3_sent"]
    db.flush()
    rules.sync_offer(db, e)


def _run_for(db: Session, run_id: int | None) -> CourseRun | None:
    if run_id is None:
        return None
    r = db.get(CourseRun, run_id)
    if not r:
        raise validation("دوره برگزارشده یافت نشد", run_id="ناشناخته است")
    return r


@router.patch("/enrollments/{enrollment_id}")
def patch_enrollment(enrollment_id: PathId, body: EnrollmentPatch, request: Request, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    e = db.scalar(_base().where(Enrollment.id == enrollment_id))
    if not e:
        raise not_found("ثبت‌نام")
    data = body.model_dump(exclude_unset=True)
    _apply(db, e, data, _run_for(db, data.get("run_id")))
    audit(db, "enrollment.update", user=user, entity="enrollment", entity_id=e.id,
          detail={"fields": sorted(data), "ticket": e.ticket}, ip=client_ip(request))
    db.commit()
    db.refresh(e)
    return ser.enrollment(db.scalar(_base().where(Enrollment.id == e.id)), settings.ticket_url_base, ser.SupervisorEmails(db))


@router.post("/enrollments:bulk")
def bulk(body: BulkIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    data = body.model_dump(exclude_unset=True, exclude={"enrollment_ids"})
    run = _run_for(db, body.run_id)
    found = {e.id: e for e in db.scalars(_base().where(Enrollment.id.in_(body.enrollment_ids))).unique()}
    updated, failed = [], []
    for i in dict.fromkeys(body.enrollment_ids):
        e = found.get(i)
        if not e:
            failed.append({"id": i, "reason": "not_found"})
            continue
        try:
            with db.begin_nested():
                _apply(db, e, data, run)
            updated.append(i)
        except Exception as exc:   # noqa: BLE001 - ApiError conflict only in practice
            failed.append({"id": i, "reason": getattr(exc, "code", "error")})
    audit(db, "enrollment.bulk", user=user, entity="enrollment", detail={"fields": sorted(data), "updated": len(updated),
                                                                         "failed": len(failed)}, ip=client_ip(request))
    db.commit()
    return {"updated": updated, "failed": failed}
