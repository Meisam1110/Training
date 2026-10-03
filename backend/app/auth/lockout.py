"""Login rate limiting and account lockout, backed by the DB so it holds across workers.

* per username (existing or not -- no user enumeration): ``login_max_failures`` consecutive
  failures inside the lock window lock that username for ``login_lock_minutes``;
* per client IP: ``login_ip_max_failures`` failures inside the window block the IP.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import LoginAttempt, utcnow


def _recent_failures(db: Session, col, value: str, since) -> int:
    # failures since the last success (or window start)
    last_ok = db.scalar(select(func.max(LoginAttempt.ts)).where(col == value, LoginAttempt.ok.is_(True)))
    start = max(since, last_ok) if last_ok else since
    return db.scalar(select(func.count()).select_from(LoginAttempt)
                     .where(col == value, LoginAttempt.ok.is_(False), LoginAttempt.ts > start)) or 0


def is_locked(db: Session, s: Settings, username: str, ip: str) -> bool:
    since = utcnow() - timedelta(minutes=s.login_lock_minutes)
    if _recent_failures(db, LoginAttempt.username, username.lower(), since) >= s.login_max_failures:
        return True
    return bool(ip) and _recent_failures(db, LoginAttempt.ip, ip, since) >= s.login_ip_max_failures


def record(db: Session, username: str, ip: str, ok: bool) -> None:
    db.add(LoginAttempt(username=username.lower()[:64], ip=ip[:64], ok=ok))
    db.execute(delete(LoginAttempt).where(LoginAttempt.ts < utcnow() - timedelta(days=2)))
