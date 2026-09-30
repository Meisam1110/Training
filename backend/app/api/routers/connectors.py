from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import validation
from app.api.services import gateway
from app.api.services import serializers as ser
from app.audit import record as audit
from app.deps import client_ip, get_db, require
from app.models import CONNECTOR_KINDS, ConnectorConfig, User, utcnow
from app.schemas.domain import ConnectorPut
from app.security.redact import scrub

router = APIRouter(tags=["connectors"])


def _kind(kind: str) -> str:
    if kind not in CONNECTOR_KINDS:
        from app.api.errors import not_found
        raise not_found("رابط")
    return kind


@router.get("/connectors")
def list_connectors(db: Session = Depends(get_db), _=Depends(require("hr"))):
    return {"items": [ser.connector(k, db.get(ConnectorConfig, k)) for k in CONNECTOR_KINDS]}


URL_KEYS = ("base_url", "token_url", "login_url", "authority_url", "graph_url")
BOOL_KEYS = ("verify_tls", "starttls", "use_ssl", "save_to_sent_items", "allow_private_hosts")
NUM_RANGES = {"port": (1, 65535, True), "page_size": (1, 10_000, True), "max_retries": (0, 20, True), "breaker_threshold": (1, 1000, True),
              "timeout_s": (0.1, 600, False), "backoff_base_s": (0, 600, False), "backoff_max_s": (0, 3600, False),
              "breaker_cooldown_s": (0, 3600, False), "rate_limit_per_min": (0, 100_000, False)}


def _check_types(cfg: dict) -> None:
    for k, v in cfg.items():
        if v is None:
            continue
        if k == "field_map":
            if not isinstance(v, dict) or len(v) > 100 or not all(isinstance(x, (str, list)) for x in v.values()):
                raise validation("field_map نامعتبر است", config="ساختار field_map نامعتبر است")
        elif k == "active_statuses":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v) or len(v) > 50:
                raise validation("active_statuses باید فهرستی از متن باشد", config=k)
        elif k in BOOL_KEYS:
            if not isinstance(v, bool):
                raise validation("مقدار باید true یا false باشد", config=k)
        elif k in NUM_RANGES:
            lo, hi, integer = NUM_RANGES[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and int(v) != v) or not lo <= v <= hi:
                raise validation(f"مقدار عددی باید بین {lo} و {hi} باشد", config=k)
        elif not isinstance(v, (str, int, float, bool)):
            raise validation("مقدار پیکربندی نامعتبر", config=k)
        elif isinstance(v, str) and (len(v) > 2000 or "\x00" in v):
            raise validation("مقدار پیکربندی نامعتبر یا بیش از حد طولانی است", config=k)
    for k in URL_KEYS:
        v = cfg.get(k)
        if v:
            u = urlsplit(str(v))
            if u.scheme not in ("http", "https") or not u.hostname:
                raise validation("نشانی باید با http یا https شروع شود", config=k)
            if u.username is not None or u.password is not None or "@" in u.netloc:
                raise validation("نشانی نباید شامل نام کاربری/گذرواژه باشد؛ آن‌ها را در فیلدهای جداگانهٔ رمز وارد کنید", config=k)
            if u.query or u.fragment:
                raise validation("نشانی نباید شامل پارامتر (?…) یا #… باشد؛ کلید/توکن را در فیلد رمز وارد کنید", config=k)


@router.put("/connectors/{kind}")
def put_connector(kind: str, body: ConnectorPut, request: Request, db: Session = Depends(get_db),
                  admin: User = Depends(require("admin"))):
    _kind(kind)
    unknown = sorted(set(body.config) - ser.allowed_keys(kind))
    if unknown:
        raise validation("کلیدهای پیکربندی نامعتبر", config=", ".join(unknown))
    _check_types(body.config)
    secret_keys = ser.SECRET_KEYS_BY_KIND[kind]
    c = db.get(ConnectorConfig, kind)
    if c is None:
        c = ConnectorConfig(kind=kind, public={}, secrets={})
        db.add(c)
    public, secrets = dict(c.public or {}), dict(c.secrets or {})
    for k, v in body.config.items():
        target = secrets if k in secret_keys else public
        if v is None:
            target.pop(k, None)     # null clears
        elif k in secret_keys and v == "":
            continue                 # an empty secret field never wipes the stored one
        else:
            target[k] = v
    c.public, c.secrets, c.enabled, c.updated_by = public, secrets, body.enabled, admin.id
    c.updated_at = utcnow()
    audit(db, "connector.update", user=admin, entity="connector", entity_id=kind, ip=client_ip(request),
          detail={"keys": sorted(body.config), "enabled": body.enabled})
    db.commit()
    return ser.connector(kind, c)


@router.post("/connectors/{kind}:test")
def test_connector(kind: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require("admin"))):
    _kind(kind)
    c = db.get(ConnectorConfig, kind)
    if c is None:
        from app.api.errors import conflict
        raise conflict("رابط هنوز پیکربندی نشده است")
    cfg = {**(c.public or {}), **(c.secrets or {})}
    factory = gateway.get_factory()
    try:
        obj = factory.build_email_sender(kind, cfg) if kind in ("smtp", "graph") else factory.build_employee_source(kind, cfg)
        ok, msg = obj.test_connection()
    except Exception as exc:   # noqa: BLE001
        ok, msg = False, f"{type(exc).__name__}: {scrub(exc, 150)}"
    msg = scrub(msg, 300)
    if not ok and cfg.get("verify_tls", True) is not False and any(str(cfg.get(k, "")).startswith("https") for k in URL_KEYS) or \
            (not ok and kind == "smtp" and (cfg.get("use_ssl") or cfg.get("starttls", True))):
        if re.search(r"(?i)ssl|tls|certificate|ConnectError", msg):
            msg = (msg + " | راهنما: اگر سرور گواهی داخلی/خودامضا دارد، مسیر ca_bundle را تنظیم کنید (verify_tls را خاموش نکنید)")[:300]
    c.last_test_ok, c.last_test_at = bool(ok), utcnow()
    c.last_test_message = msg
    audit(db, "connector.test", user=admin, entity="connector", entity_id=kind, ip=client_ip(request), detail={"ok": bool(ok)})
    db.commit()
    return {"ok": bool(ok), "message": msg}
