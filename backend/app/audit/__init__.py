"""Append-only audit trail.

Defence in depth: (1) there is no update/delete code path, (2) an ORM event guard raises on
any UPDATE/DELETE of an AuditLog object, (3) database triggers abort UPDATE/DELETE
(installed by the initial migration 0001, SQLite and PostgreSQL).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.security.redact import redact_mapping


class AuditImmutableError(RuntimeError):
    pass


@event.listens_for(AuditLog, "before_update")
def _no_update(mapper, connection, target):
    raise AuditImmutableError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete")
def _no_delete(mapper, connection, target):
    raise AuditImmutableError("audit_log is append-only")


def record(db: Session, action: str, *, user: User | None = None, entity: str = "",
           entity_id: Any = "", detail: dict | None = None, ip: str = "", actor: str = "") -> AuditLog:
    """Add an audit row to the current transaction (committed with the caller's work).

    ``detail`` is redacted defensively, but callers should never pass PII values."""
    row = AuditLog(
        actor_id=user.id if user else None,
        actor=(user.username if user else actor)[:64],
        action=action, entity=entity, entity_id=str(entity_id),
        detail=redact_mapping(detail or {}), ip=ip[:64],
    )
    db.add(row)
    return row
