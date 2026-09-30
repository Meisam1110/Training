from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.api.pagination import PageParams, apply_sort, paginate
from app.api.services import serializers as ser
from app.api.services import sync as svc
from app.audit import record as audit
from app.config import Settings
from app.deps import client_ip, get_db, get_settings, require
from app.models import SyncRun, User
from app.schemas.domain import SyncIn

router = APIRouter(prefix="/sync", tags=["sync"])
SORT = {"id": SyncRun.id, "started_at": SyncRun.started_at, "source": SyncRun.source}


@router.get("/runs")
def runs(p: PageParams = Depends(), source: str = "", db: Session = Depends(get_db), _=Depends(require("hr"))):
    stmt = select(SyncRun)
    if source:
        stmt = stmt.where(SyncRun.source == source)
    return paginate(db, apply_sort(stmt, p.sort, SORT, "-id"), p, ser.sync_run)


@router.post("/{source}:run")
def run(source: str, request: Request, response: Response, body: SyncIn | None = None, db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings), user: User = Depends(require("hr"))):
    if source not in ("excel", "ifs"):
        raise not_found("منبع همگام‌سازی")
    r = svc.run_source(db, request.app.state.session_factory, settings, source, full=bool(body and body.full), triggered_by=user.username)
    audit(db, "sync.run", user=user, entity="sync", entity_id=r.id, ip=client_ip(request),
          detail={"source": source, "created": r.created, "updated": r.updated})
    db.commit()
    if r.status == "running":
        response.status_code = 202       # still running in the background: poll GET /sync/runs
    return ser.sync_run(r)
