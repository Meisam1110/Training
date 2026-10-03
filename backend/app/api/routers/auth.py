from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.services import serializers as ser
from app.audit import record as audit
from app.auth import lockout, sessions
from app.auth.passwords import DUMMY_HASH, verify_password
from app.config import Settings
from app.deps import client_ip, current_session, get_db, get_settings
from app.models import User, UserSession, utcnow
from app.schemas.domain import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])
BAD = "نام کاربری یا گذرواژه نادرست است"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    ip = client_ip(request)
    if lockout.is_locked(db, settings, body.username, ip):
        raise ApiError("rate_limited", "تلاش‌های ناموفق زیاد بود؛ چند دقیقه بعد دوباره تلاش کنید",
                       headers={"Retry-After": str(settings.login_lock_minutes * 60)})
    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    ok = bool(user and user.is_active and ok)
    lockout.record(db, body.username, ip, ok)
    if not ok:
        audit(db, "login.failed", actor="", ip=ip)
        db.commit()
        raise ApiError("unauthorized", BAD)
    token, sess = sessions.create(db, user, settings.secret_key, settings.session_hours)
    user.last_login_at = utcnow()
    audit(db, "login", user=user, entity="user", entity_id=user.id, ip=ip)
    db.commit()
    response.set_cookie(sessions.COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                        max_age=settings.session_hours * 3600, path="/")
    response.headers["X-CSRF-Token"] = sess.csrf_token
    return {"user": ser.user(user), "csrf_token": sess.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, s: UserSession = Depends(current_session), db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)):
    sessions.revoke(db, request.cookies.get(sessions.COOKIE), settings.secret_key)
    audit(db, "logout", user=s.user, entity="user", entity_id=s.user_id, ip=client_ip(request))
    db.commit()
    response.delete_cookie(sessions.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(response: Response, s: UserSession = Depends(current_session)):
    response.headers["X-CSRF-Token"] = s.csrf_token
    return {"user": ser.user(s.user), "csrf_token": s.csrf_token}
