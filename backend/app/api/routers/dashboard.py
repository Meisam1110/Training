from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import validation
from app.api.services import dashboard as svc
from app.api.services import dashboard_widgets as dw
from app.deps import get_db, require
from app.models import User

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(require("viewer"))):
    return svc.build(db, date.today())


@router.get("/dashboard/widgets")
def widgets(user: User = Depends(require("viewer"))):
    """Catalogue of the widgets this role may use (id, title, kind, default/min/max size on a 12-column grid, roles)."""
    return {"grid_columns": dw.GRID_COLS, "items": dw.catalog_for(user.role), "ranges": list(dw.RANGES)}


@router.get("/dashboard/data")
def widget_data(widgets: str = Query(..., min_length=1, max_length=600, description="comma separated widget ids"),
                range: str = Query("12m", max_length=8), db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    ids = [w.strip() for w in widgets.split(",") if w.strip()]
    if not ids or len(ids) > 30:
        raise validation("فهرست ویجت‌ها نامعتبر است", widgets="۱ تا ۳۰ شناسه")
    return dw.data(db, user.role, ids, dw.parse_range(range))
