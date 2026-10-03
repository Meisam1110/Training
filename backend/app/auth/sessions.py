"""Server-side sessions: an opaque 256-bit token in an HttpOnly cookie; only an HMAC of it is
stored. Each session carries its own CSRF token."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import User, UserSession, utcnow

COOKIE = "tms_session"


def _digest(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def create(db: Session, user: User, pepper: str, hours: int) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    s = UserSession(token_hash=_digest(token, pepper), csrf_token=secrets.token_urlsafe(32),
                    user_id=user.id, expires_at=utcnow() + timedelta(hours=hours))
    db.add(s)
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    return token, s


def lookup(db: Session, token: str | None, pepper: str) -> UserSession | None:
    if not token:
        return None
    s = db.scalar(select(UserSession).options(joinedload(UserSession.user))
                  .where(UserSession.token_hash == _digest(token, pepper)))
    if not s or s.expires_at < utcnow() or not s.user.is_active:
        return None
    return s


def revoke(db: Session, token: str | None, pepper: str) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == _digest(token, pepper)))
