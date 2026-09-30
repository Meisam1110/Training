from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.services import automation as svc
from app.api.services import settings_store as rt
from app.audit import record as audit
from app.config import Settings
from app.deps import client_ip, get_db, get_settings, require
from app.models import User
from app.schemas.domain import AutomationSettingsIn

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/due")
def get_due(limit: int = Query(500, ge=1, le=5000), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    items = svc.due(db, date.today())
    return {"total": len(items), "counts": svc.summarize(items), "truncated": len(items) > limit,
            "items": [svc.item_dict(i) for i in items[:limit]]}


@router.post("/run")
def run(request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    return svc.run_now(db, date.today(), user.username, user, client_ip(request), settings=request.app.state.settings,
                       sf=request.app.state.session_factory)


def _settings_view(db: Session, s: Settings) -> dict:
    return {**rt.get_all(db), "interval_s": s.automation_interval_s, "loop_enabled": s.automation_enabled,
            "last_run": rt.get_raw(db, "automation.last_run")}


@router.get("/settings")
def get_settings_(db: Session = Depends(get_db), s: Settings = Depends(get_settings), _=Depends(require("viewer"))):
    return _settings_view(db, s)


@router.put("/settings")
def put_settings(body: AutomationSettingsIn, request: Request, db: Session = Depends(get_db),
                 s: Settings = Depends(get_settings), admin: User = Depends(require("admin"))):
    vals = body.model_dump(exclude_unset=True, exclude_none=True)
    rt.set_many(db, vals)
    audit(db, "automation.settings", user=admin, entity="settings", detail=vals, ip=client_ip(request))
    db.commit()
    return _settings_view(db, s)
