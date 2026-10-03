"""Application factory: ``uvicorn app.main:app`` (factory in ``create_app``)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import db as dbm
from app.api import errors
from app.api.routers import (
    admin,
    auth,
    automation,
    connectors,
    courses,
    dashboard,
    email,
    employees,
    enrollments,
    importexport,
    institutes,
    letters,
    me,
    runs,
    sync,
    templates,
)
from app.api.services import automation as automation_svc
from app.api.services import sync as sync_svc
from app.auth.passwords import hash_password
from app.config import REQUIRED_TEMPLATES, Settings, ensure_dev_key, load_settings
from app.deps import get_db
from app.models import User
from app.security import crypto
from app.security.logging import configure_logging
from app.security.middleware import BodyLimitMiddleware, OriginCheckMiddleware, RequestLogMiddleware, SecurityHeadersMiddleware

log = logging.getLogger("tms")
API = "/api/v1"


def bootstrap_admin(sf, s: Settings) -> bool:
    """Create the first admin from env on an EMPTY user table only. No default password exists."""
    if not (s.bootstrap_admin_user and s.bootstrap_admin_password):
        return False
    with sf() as db:
        try:
            if db.scalar(select(User.id).limit(1)) is not None:
                return False
        except Exception:   # noqa: BLE001 - schema not migrated yet
            log.warning("bootstrap skipped: schema not migrated")
            return False
        db.add(User(username=s.bootstrap_admin_user, display_name="Administrator", role="admin",
                    password_hash=hash_password(s.bootstrap_admin_password)))
        db.commit()
        log.info("bootstrap admin created")
        return True


def recover_on_start(sf, s: Settings) -> None:
    """Close sync runs whose worker died (no heartbeat) so they neither show 'running' forever nor block new syncs."""
    try:
        with sf() as db:
            n = sync_svc.recover_stale(db, s)
            if n:
                log.warning("recovered stale sync runs", extra={"count": n})
    except Exception:   # noqa: BLE001 - schema not migrated yet
        log.warning("stale-run recovery skipped")


class SpaFiles(StaticFiles):
    """The SPA shell must never be cached (a stale index.html after an upgrade points at deleted hashed assets);
    hashed assets under /assets are immutable."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path in ("", ".", "index.html") or path.endswith(".html"):
            resp.headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or load_settings()
    s.validate()                       # production: refuse weak/missing secrets
    s = ensure_dev_key(s)
    crypto.configure(s.data_keys())
    configure_logging(s.log_level)
    if not s.is_production and not s.is_sqlite and s.env == "development":
        log.warning("TMS_ENV=development with a non-SQLite database: OpenAPI docs are exposed and cookies are not Secure. "
                    "Set TMS_ENV=production for a real deployment.")
    engine = dbm.make_engine(s.database_url)
    sf = dbm.make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if s.auto_migrate:
            await asyncio.to_thread(dbm.upgrade_to_head, s.database_url)
        await asyncio.to_thread(bootstrap_admin, sf, s)
        await asyncio.to_thread(recover_on_start, sf, s)
        task = None
        if s.automation_enabled and s.env != "test":
            task = asyncio.create_task(automation_svc.loop(sf, s))
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        sync_svc.shutdown()
        engine.dispose()

    app = FastAPI(title="TMS", version="1.0.0", lifespan=lifespan, docs_url=None if s.is_production else "/api/docs",
                  redoc_url=None, openapi_url=None if s.is_production else "/api/openapi.json")
    app.state.settings, app.state.engine, app.state.session_factory = s, engine, sf
    errors.install(app)

    for r in (auth, dashboard, employees, courses, runs, enrollments, letters, email, connectors, sync, automation,
              importexport, admin, institutes, templates, me):
        app.include_router(r.router, prefix=API)

    def _health():
        return {"status": "ok"}

    def _ready(request: Request, db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
            cur = dbm.current_revision(engine)
        except Exception:   # noqa: BLE001
            return JSONResponse({"status": "unavailable", "db": False, "migrations": False}, status_code=503)
        head = dbm.head_revision()
        ok = cur == head
        missing = [k for k in REQUIRED_TEMPLATES if not (Path(s.templates_dir) / f"{k}.docx").is_file()]
        body = {"status": "ok" if ok and not missing else ("migrations_pending" if not ok else "templates_missing"),
                "db": True, "migrations": ok, "templates": not missing}
        if missing:
            body["missing_templates"] = missing
        return JSONResponse(body, status_code=200 if ok and not missing else 503)

    for prefix in ("", API):
        app.get(f"{prefix}/health", tags=["admin"])(_health)
        app.get(f"{prefix}/ready", tags=["admin"])(_ready)

    static = Path(s.static_root) if s.static_root else None
    if static and (static / "index.html").is_file():
        app.mount("/", SpaFiles(directory=static, html=True), name="spa")

    # middleware: last added = outermost
    if s.trusted_hosts:
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(s.trusted_hosts))
    app.add_middleware(OriginCheckMiddleware, allowed=s.cors_origins)
    app.add_middleware(BodyLimitMiddleware, max_body=s.max_body_bytes, max_upload=s.max_upload_bytes)
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(s.cors_origins), allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])
    app.add_middleware(SecurityHeadersMiddleware, hsts=s.hsts)
    app.add_middleware(RequestLogMiddleware)
    return app


def app_factory() -> FastAPI:   # uvicorn --factory app.main:app_factory
    return create_app()


_app: FastAPI | None = None


def __getattr__(name: str):   # `uvicorn app.main:app` -- built lazily so importing this module has no side effects
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
