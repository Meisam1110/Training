from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import RootModel
from sqlalchemy.orm import Session

from app.api.errors import validation
from app.api.services import user_prefs as up
from app.deps import get_db, require
from app.models import User
from app.schemas.domain import LayoutIn, has_nul

router = APIRouter(prefix="/me", tags=["me"])


class PrefsIn(RootModel[dict[str, Any]]):
    pass


@router.get("/dashboard-layout")
def get_layout(db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    return up.get_layout(db, user)


@router.put("/dashboard-layout")
def put_layout(body: LayoutIn, db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    return up.put_layout(db, user, [w.model_dump() for w in body.widgets])


@router.delete("/dashboard-layout")
def reset_layout(db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    return up.reset_layout(db, user)


@router.get("/preferences")
def get_prefs(db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    return up.get_prefs(db, user)


@router.put("/preferences")
def put_prefs(body: PrefsIn, db: Session = Depends(get_db), user: User = Depends(require("viewer"))):
    if has_nul(body.root):
        raise validation("کاراکتر NUL مجاز نیست", preferences="کاراکتر NUL مجاز نیست")
    return up.put_prefs(db, user, body.root)
