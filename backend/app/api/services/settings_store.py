"""Runtime (DB-backed) settings edited via /automation/settings."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "level3_after_days": 60,
    "reminder_days": 2,
    "over3_threshold": 3,
    "auto_send": False,            # daily job e-mails due Level-3 requests / reminders (off = dry run only)
    "watch_excel": False,          # poll connectors.excel.watch_dir and import changed files
    "ifs_sync_interval_min": 0,    # scheduled IFS delta sync every N minutes (0 = off)
    "letter_number_prefix": "",
    "letter_number_start": 0,
    # letterhead / addressee data that no table holds (edit via PUT /automation/settings)
    "company_economic_code": "", "company_national_id": "", "company_postal_code": "", "company_address": "",
    "settlement_addressee": "", "letter_signer_name": "", "letter_signer_title": "", "letter_signer_email": "",
    "letter_signer_phone": "",
}


def get_all(db: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for s in db.query(Setting).filter(Setting.key.in_(list(DEFAULTS))).all():
        out[s.key] = s.value
    return out


def set_many(db: Session, values: dict[str, Any]) -> None:
    for k, v in values.items():
        if k not in DEFAULTS:
            continue
        row = db.get(Setting, k)
        if row:
            row.value = v
        else:
            db.add(Setting(key=k, value=v))


def get_raw(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return row.value if row else default


def set_raw(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
