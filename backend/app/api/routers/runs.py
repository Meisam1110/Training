from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.errors import conflict, not_found, validation
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.routers.enrollments import _list_enrollments
from app.api.services import rules, upsert
from app.api.services import serializers as ser
from app.api.services import settings_store as rt
from app.api.services.dashboard import run_counts
from app.api.services.workflow import workflow
from app.audit import record as audit
from app.config import Settings
from app.deps import PathId, client_ip, get_db, get_settings, require
from app.models import Course, CourseRun, User
from app.schemas.domain import INT_MAX, CandidateSearchIn, RunIn, RunPatch

router = APIRouter(prefix="/runs", tags=["runs"])
MAX_CANDIDATES = 500
SORT = {"start_date": CourseRun.start_date, "end_date": CourseRun.end_date, "deadline": CourseRun.deadline,
        "status": CourseRun.status, "id": CourseRun.id, "amount": CourseRun.amount, "type": CourseRun.type}


def _load(db: Session, run_id: int) -> CourseRun:
    r = db.scalar(select(CourseRun).options(joinedload(CourseRun.course), joinedload(CourseRun.institute)).where(CourseRun.id == run_id))
    if not r:
        raise not_found("دوره برگزارشده")
    return r


def _counts(db: Session, r: CourseRun):
    return run_counts(db, [r.id])[r.id]


def _detail(db: Session, r: CourseRun) -> dict:
    return {**ser.run(r, date.today(), _counts(db, r)), "workflow": workflow(db, r)}


@router.get("")
def list_runs(p: PageParams = Depends(), status: str = Query("", max_length=16), course_id: int | None = Query(None, ge=1, le=INT_MAX),
              type: str = Query("", max_length=16), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(CourseRun).options(joinedload(CourseRun.course), joinedload(CourseRun.institute)).join(Course)
    if p.q:
        stmt = stmt.outerjoin(CourseRun.institute).where(Course.name.ilike(like(p.q), escape="\\") |
                                                         Course.name_fa.ilike(like(p.q), escape="\\") |
                                                         CourseRun.section_b.ilike(like(p.q), escape="\\"))
    if status:
        stmt = stmt.where(CourseRun.status == status)
    if course_id:
        stmt = stmt.where(CourseRun.course_id == course_id)
    if type:
        stmt = stmt.where(CourseRun.type == type)
    today = date.today()
    counts: dict = {}
    return paginate(db, apply_sort(stmt, p.sort, SORT, "-start_date"), p, lambda r: ser.run(r, today, counts.get(r.id)),
                    prepare=lambda rows: counts.update(run_counts(db, [r.id for r in rows])))


@router.post("", status_code=201)
def create_run(body: RunIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    course = db.get(Course, body.course_id)
    if not course:
        raise validation("دوره یافت نشد", course_id="ناشناخته است")
    inst = upsert.get_institute(db, body.institute)
    data = body.model_dump(exclude={"course_id", "institute"})
    key = upsert.make_run_key(course.name, body.institute, body.start_date)
    if db.scalar(select(CourseRun.id).where(CourseRun.run_key == key)):
        raise conflict("این دوره برگزارشده قبلاً ثبت شده است")
    r = CourseRun(run_key=key, course_id=course.id, institute_id=inst.id if inst else None, **data)
    db.add(r)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("این دوره برگزارشده قبلاً ثبت شده است") from None
    audit(db, "run.create", user=user, entity="run", entity_id=r.id, ip=client_ip(request))
    db.commit()
    return ser.run(_load(db, r.id), date.today(), run_counts(db, [r.id])[r.id])


@router.get("/{run_id}")
def get_run(run_id: PathId, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    r = _load(db, run_id)
    return _detail(db, r)


@router.patch("/{run_id}")
def patch_run(run_id: PathId, body: RunPatch, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    r = _load(db, run_id)
    data = body.model_dump(exclude_unset=True)
    inst_name = data.pop("institute", None) if "institute" in data else None
    for k in ("type", "status", "days", "time", "section_b", "link", "payment_process", "sessions"):
        if k in data and data[k] is None:
            data.pop(k)
    if "institute" in body.model_fields_set:
        inst = upsert.get_institute(db, inst_name or "")
        r.institute_id = inst.id if inst else None
        db.flush()
        db.refresh(r)
    for k, v in data.items():
        setattr(r, k, v)
    if "payment_process" in body.model_fields_set or "pr_process_start_date" in body.model_fields_set:
        # the payment path has two markers (PR process start date, payment_process text); the dashboard's
        # payment_not_started list needs neither set -> keep them consistent whichever one the UI writes
        if r.pr_process_start_date and not r.payment_process:
            r.payment_process = "started"
        elif r.payment_process and not r.pr_process_start_date and "pr_process_start_date" not in body.model_fields_set:
            r.pr_process_start_date = date.today()
    if r.start_date and r.end_date and r.end_date < r.start_date:
        db.rollback()
        raise validation("تاریخ پایان قبل از تاریخ شروع است", end_date="قبل از تاریخ شروع است")
    new_key = upsert.make_run_key(r.course.name, r.institute.name if r.institute else "", r.start_date)
    if new_key != r.run_key:
        if db.scalar(select(CourseRun.id).where(CourseRun.run_key == new_key, CourseRun.id != r.id)):
            db.rollback()
            raise conflict("این دوره برگزارشده قبلاً ثبت شده است")
        r.run_key = new_key
    audit(db, "run.update", user=user, entity="run", entity_id=r.id,
          detail={"fields": sorted(body.model_fields_set)}, ip=client_ip(request))
    db.commit()
    return _detail(db, _load(db, run_id))


@router.get("/{run_id}/enrollments")
def run_enrollments(run_id: PathId, p: PageParams = Depends(), db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings), _=Depends(require("viewer"))):
    _load(db, run_id)
    return _list_enrollments(db, p, settings, run_id=run_id)


@router.post("/{run_id}/candidates:search")
def candidates_search(run_id: PathId, body: CandidateSearchIn, db: Session = Depends(get_db),
                      settings: Settings = Depends(get_settings), _=Depends(require("hr"))):
    r = _load(db, run_id)
    conf = rt.get_all(db)
    res = rules.search_candidates(db, r, course_name=body.course_name, threshold=int(conf["over3_threshold"]),
                                  include_flagged=body.include_flagged, today=date.today(),
                                  after_days=int(conf["level3_after_days"]))
    sup = ser.SupervisorEmails(db)
    truncated = len(res.candidates) > MAX_CANDIDATES
    res.candidates = res.candidates[:MAX_CANDIDATES]                # bounded response (was unpaged: 425 KB for a 12k-row IDP)
    sup.prefetch(e.employee.supervisor_emp_no for e, _ in res.candidates)      # ONE query, not one per manager
    items = [{**ser.enrollment(e, settings.ticket_url_base, sup), "flags": flags, "flagged": bool([f for f in flags if f != "level3_eligible"])}
             for e, flags in res.candidates]
    excluded = [{"enrollment_id": e.id, "ticket": e.ticket, "reason": reason, "conflicting_ticket": other}
                for e, reason, other in res.excluded]
    return {"run_id": r.id, "course_name": body.course_name or r.course.name, "candidates": items, "excluded": excluded,
            "total": len(items), "truncated": truncated}
