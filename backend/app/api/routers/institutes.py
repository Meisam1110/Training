from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.audit import record as audit
from app.deps import PathId, client_ip, get_db, require
from app.models import Institute, User
from app.schemas.domain import InstituteIn, InstitutePatch

router = APIRouter(prefix="/institutes", tags=["institutes"])
SORT = {"name": Institute.name, "id": Institute.id, "supplier_code": Institute.supplier_code}


def ser_institute(i: Institute) -> dict:
    return {"id": i.id, "name": i.name, "name_fa": i.name_fa, "supplier_code": i.supplier_code, "contact_email": i.contact_email}


@router.get("")
def list_institutes(p: PageParams = Depends(), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(Institute)
    if p.q:
        stmt = stmt.where(Institute.name.ilike(like(p.q), escape="\\") | Institute.name_fa.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, SORT, "name"), p, ser_institute)


@router.post("", status_code=201)
def create_institute(body: InstituteIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    i = Institute(**body.model_dump())
    db.add(i)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("مؤسسه‌ای با این نام وجود دارد") from None
    audit(db, "institute.create", user=user, entity="institute", entity_id=i.id, ip=client_ip(request))
    db.commit()
    return ser_institute(i)


@router.patch("/{institute_id}")
def patch_institute(institute_id: PathId, body: InstitutePatch, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require("hr"))):
    i = db.get(Institute, institute_id)
    if not i:
        raise not_found("مؤسسه")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        setattr(i, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("مؤسسه‌ای با این نام وجود دارد") from None
    audit(db, "institute.update", user=user, entity="institute", entity_id=i.id, detail={"fields": sorted(data)}, ip=client_ip(request))
    db.commit()
    return ser_institute(i)
