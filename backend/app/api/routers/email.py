from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import mailer
from app.api.services import serializers as ser
from app.config import Settings
from app.deps import client_ip, get_db, get_settings, require
from app.models import MessageLog, User
from app.schemas.domain import EmailSendIn

router = APIRouter(tags=["email"])
SORT = {"id": MessageLog.id, "created_at": MessageLog.created_at, "status": MessageLog.status}


@router.post("/email/send")
def send(body: EmailSendIn, request: Request, idempotency_key: str | None = Header(None, max_length=100),
         db: Session = Depends(get_db), settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    return mailer.send(db, settings, user, body, idempotency_key, client_ip(request))


@router.get("/messages")
def messages(p: PageParams = Depends(), status: str = "", db: Session = Depends(get_db), _=Depends(require("hr"))):
    stmt = select(MessageLog)
    if status:
        stmt = stmt.where(MessageLog.status == status)
    if p.q:
        stmt = stmt.where(MessageLog.subject.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, SORT, "-id"), p, ser.message)
