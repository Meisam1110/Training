"""Per-user dashboard layout and small UI preferences (size-capped JSON)."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.services import dashboard_widgets as dw
from app.models import User, UserPrefs

MAX_PREFS_BYTES = 8192
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
DEFAULT_PREFS: dict[str, Any] = {"theme": "system", "density": "comfortable",
                                 "tutorial": {"completed_steps": [], "dismissed": False, "last_step": None}}


def _row(db: Session, user: User) -> UserPrefs:
    r = db.get(UserPrefs, user.id)
    if r is None:
        r = UserPrefs(user_id=user.id, layout=None, layout_version=0, preferences={})
        db.add(r)
        db.flush()
    return r


def get_layout(db: Session, user: User) -> dict:
    r = db.get(UserPrefs, user.id)
    if r is None or r.layout is None:
        return {"version": r.layout_version if r else 0, "widgets": dw.default_layout(user.role), "is_default": True}
    # widgets the role may no longer use (demoted user) are dropped on read, never shown
    return {"version": r.layout_version, "widgets": [w for w in r.layout["widgets"] if w["id"] in dw.BY_ID and dw.allowed(w["id"], user.role)],
            "is_default": False}


def put_layout(db: Session, user: User, widgets: list[dict]) -> dict:
    clean = dw.validate_layout(widgets, user.role)
    r = _row(db, user)
    r.layout = {"widgets": clean}
    r.layout_version = (r.layout_version or 0) + 1
    db.commit()
    return get_layout(db, user)


def reset_layout(db: Session, user: User) -> dict:
    r = db.get(UserPrefs, user.id)
    if r is not None:
        r.layout = None
        r.layout_version = (r.layout_version or 0) + 1
        db.commit()
    return get_layout(db, user)


def _depth(x: Any, d: int = 0) -> int:
    if isinstance(x, dict):
        return max([d, *(_depth(v, d + 1) for v in x.values())])
    if isinstance(x, list):
        return max([d, *(_depth(v, d + 1) for v in x)])
    return d


def validate_prefs(p: dict) -> dict[str, str]:
    errs: dict[str, str] = {}
    for k, v in p.items():
        if not KEY_RE.match(k):
            errs[k] = "نام کلید نامعتبر است"
        elif k == "theme" and v is not None and v not in ("light", "dark", "system"):
            errs[k] = "مقدار مجاز: light, dark, system"
        elif k == "density" and v is not None and v not in ("comfortable", "compact"):
            errs[k] = "مقدار مجاز: comfortable, compact"
        elif k == "tutorial" and v is not None:
            ok = (isinstance(v, dict) and set(v) <= {"completed_steps", "dismissed", "last_step"}
                  and isinstance(v.get("completed_steps", []), list) and len(v.get("completed_steps", [])) <= 50
                  and all(isinstance(s, str) and 0 < len(s) <= 64 for s in v.get("completed_steps", []))
                  and isinstance(v.get("dismissed", False), bool)
                  and (v.get("last_step") is None or (isinstance(v.get("last_step"), str) and len(v["last_step"]) <= 64)))
            if not ok:
                errs[k] = "ساختار tutorial نامعتبر است"
    if _depth(p) > 4:
        errs["_"] = "عمق JSON بیش از حد است"
    return errs


def get_prefs(db: Session, user: User) -> dict:
    r = db.get(UserPrefs, user.id)
    return {**DEFAULT_PREFS, **((r.preferences or {}) if r else {})}


def put_prefs(db: Session, user: User, incoming: dict) -> dict:
    """Top-level merge: given keys replace, ``null`` removes a key (back to its default)."""
    errs = validate_prefs(incoming)
    if errs:
        raise ApiError("validation", "تنظیمات نامعتبر است", errs)
    r = _row(db, user)
    merged = dict(r.preferences or {})
    for k, v in incoming.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    if len(json.dumps(merged, ensure_ascii=False)) > MAX_PREFS_BYTES:
        raise ApiError("validation", "اندازهٔ تنظیمات از حد مجاز (۸ کیلوبایت) بیشتر است", {"_": "حجم زیاد"})
    r.preferences = merged
    db.commit()
    return get_prefs(db, user)
