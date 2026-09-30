"""Lease rows: a DB-level mutex that works across workers/processes (SQLite and PostgreSQL)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Lease, utcnow


def acquire(db: Session, name: str, holder: str, ttl_s: int) -> bool:
    now = utcnow()
    exp = now + timedelta(seconds=ttl_s)
    res = db.execute(update(Lease).where(Lease.name == name, or_(Lease.expires_at < now, Lease.holder == holder))
                     .values(holder=holder, expires_at=exp))
    if res.rowcount == 1:
        db.commit()
        return True
    if db.get(Lease, name) is not None:
        db.rollback()
        return False
    try:
        db.add(Lease(name=name, holder=holder, expires_at=exp))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def release(db: Session, name: str, holder: str) -> None:
    db.execute(update(Lease).where(Lease.name == name, Lease.holder == holder)
               .values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()


def expire(db: Session, name: str) -> None:
    db.execute(update(Lease).where(Lease.name == name).values(expires_at=utcnow() - timedelta(seconds=1)))
