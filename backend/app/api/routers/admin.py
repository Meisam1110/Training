from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found, validation
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import serializers as ser
from app.audit import record as audit
from app.auth.passwords import hash_password
from app.config import weak_password
from app.deps import PathId, client_ip, get_db, require
from app.models import AuditLog, User, UserSession
from app.schemas.domain import UserCreate, UserPatch

router = APIRouter(tags=["admin"])
USER_SORT = {"username": User.username, "created_at": User.created_at, "role": User.role}
AUDIT_SORT = {"ts": AuditLog.ts, "action": AuditLog.action, "actor": AuditLog.actor, "id": AuditLog.id}


@router.get("/users")
def list_users(p: PageParams = Depends(), db: Session = Depends(get_db), _=Depends(require("admin"))):
    stmt = select(User)
    if p.q:
        stmt = stmt.where(User.username.ilike(like(p.q), escape="\\") | User.display_name.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, USER_SORT, "username"), p, ser.user)


@router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    why = weak_password(body.password, body.username)
    if why:
        raise validation(why, password=why)
    u = User(username=body.username, display_name=body.display_name, email=body.email, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("نام کاربری تکراری است") from None
    audit(db, "user.create", user=admin, entity="user", entity_id=u.id, detail={"role": u.role}, ip=client_ip(request))
    db.commit()
    return ser.user(u)


@router.patch("/users/{user_id}")
def patch_user(user_id: PathId, body: UserPatch, request: Request, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    u = db.get(User, user_id)
    if not u:
        raise not_found("کاربر")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    losing_admin = u.role == "admin" and u.is_active and (data.get("is_active") is False or ("role" in data and data["role"] != "admin"))
    if losing_admin:
        active_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise conflict("آخرین مدیر فعال سامانه را نمی‌توان غیرفعال یا تنزل داد")
    revoke = "role" in data and data["role"] != u.role
    if "password" in data:
        why = weak_password(data["password"], u.username)
        if why:
            raise validation(why, password=why)
        u.password_hash = hash_password(data.pop("password"))
        revoke = True
    for k, v in data.items():
        setattr(u, k, v)
    if data.get("is_active") is False:
        revoke = True                       # a demoted/disabled account must not keep its old privileges
    if revoke:
        db.execute(delete(UserSession).where(UserSession.user_id == u.id))
    audit(db, "user.update", user=admin, entity="user", entity_id=u.id, ip=client_ip(request),
          detail={"fields": sorted(body.model_fields_set), "sessions_revoked": revoke})
    db.commit()
    return ser.user(u)


@router.get("/audit")
def list_audit(p: PageParams = Depends(), action: str = Query("", max_length=64), entity: str = Query("", max_length=64),
               actor: str = Query("", max_length=64), since: datetime | None = None, until: datetime | None = None,
               db: Session = Depends(get_db), _=Depends(require("admin"))):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if since:
        stmt = stmt.where(AuditLog.ts >= since)
    if until:
        stmt = stmt.where(AuditLog.ts <= until)
    if p.q:
        stmt = stmt.where(AuditLog.action.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, AUDIT_SORT, "-id"), p, ser.audit)
