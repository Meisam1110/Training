from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import serializers as ser
from app.audit import record as audit
from app.deps import PathId, client_ip, get_db, require
from app.models import Course, User
from app.schemas.domain import CourseIn, CoursePatch

router = APIRouter(prefix="/courses", tags=["courses"])
SORT = {"name": Course.name, "category": Course.category, "id": Course.id}


@router.get("")
def list_courses(p: PageParams = Depends(), active: bool | None = Query(None), db: Session = Depends(get_db),
                 _=Depends(require("viewer"))):
    stmt = select(Course)
    if p.q:
        stmt = stmt.where(Course.name.ilike(like(p.q), escape="\\") | Course.name_fa.ilike(like(p.q), escape="\\"))
    if active is not None:
        stmt = stmt.where(Course.active == active)
    return paginate(db, apply_sort(stmt, p.sort, SORT, "name"), p, ser.course)


@router.post("", status_code=201)
def create_course(body: CourseIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    c = Course(**body.model_dump())
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("دوره‌ای با این نام وجود دارد") from None
    audit(db, "course.create", user=user, entity="course", entity_id=c.id, ip=client_ip(request))
    db.commit()
    return ser.course(c)


@router.get("/{course_id}")
def get_course(course_id: PathId, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    c = db.get(Course, course_id)
    if not c:
        raise not_found("دوره")
    return ser.course(c)


@router.patch("/{course_id}")
def patch_course(course_id: PathId, body: CoursePatch, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    c = db.get(Course, course_id)
    if not c:
        raise not_found("دوره")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("name",) and v is None:
            continue
        setattr(c, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("دوره‌ای با این نام وجود دارد") from None
    audit(db, "course.update", user=user, entity="course", entity_id=c.id, detail={"fields": sorted(data)}, ip=client_ip(request))
    db.commit()
    return ser.course(c)
