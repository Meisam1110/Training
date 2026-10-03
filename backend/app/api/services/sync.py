"""Sync / import orchestration: lease guard, SyncRun bookkeeping, idempotent upsert."""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import ApiError, conflict, upstream, validation
from app.api.services import gateway, leases, upsert
from app.config import Settings
from app.contracts import SyncReport
from app.models import ConnectorConfig, SyncRun, utcnow
from app.security.redact import scrub

log = logging.getLogger("tms.sync")
LEASE_TTL_S = 900


def connector_config(db: Session, kind: str, *, require_enabled: bool = True) -> dict:
    c = db.get(ConnectorConfig, kind)
    if c is None or (require_enabled and not c.enabled):
        raise conflict(f"رابط «{kind}» پیکربندی یا فعال نشده است")
    return {**(c.public or {}), **(c.secrets or {})}


Work = Callable[[Session, SyncReport], None]
_pool: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tms-job")
    return _pool


def shutdown() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def recover_stale(db: Session, settings: Settings) -> int:
    """A run still 'running' whose heartbeat stopped (worker killed) is closed as an error and its lease freed,
    so the next sync is not blocked until the lease would have expired."""
    cutoff = utcnow() - timedelta(seconds=settings.sync_stale_s)
    n = 0
    for run in db.scalars(select(SyncRun).where(SyncRun.status == "running",
                                                or_(SyncRun.heartbeat_at < cutoff,
                                                    and_(SyncRun.heartbeat_at.is_(None), SyncRun.started_at < cutoff)))):
        run.status, run.finished_at = "error", utcnow()
        run.message = "متوقف شد: ضربان کار قطع شده بود (پردازش ناتمام)"
        run.errors = [*(run.errors or []), {"sheet": "", "row": None, "column": "", "code": "interrupted",
                                            "reason": "worker stopped before the job finished; rows committed so far are kept, run again"}]
        leases.expire(db, f"sync:{run.source}")
        n += 1
    if n:
        db.commit()
    return n


def _job(sf: sessionmaker[Session], settings: Settings, run_id: int, source: str, work: Work, holder: str,
         cleanup: Callable[[], None] | None) -> Exception | None:
    failure: Exception | None = None
    lease = f"sync:{source}"
    with sf() as db:
        rep = upsert.new_report(source)
        rep.chunk = settings.sync_chunk          # type: ignore[attr-defined]

        def hook(r: SyncReport) -> None:      # called after every committed chunk: heartbeat + progress + lease renewal
            done = r.created + r.updated + r.unchanged + r.skipped
            if done > settings.max_import_rows:
                raise validation("تعداد ردیف‌ها از سقف مجاز بیشتر است", rows=f"حداکثر {settings.max_import_rows}")
            run = db.get(SyncRun, run_id)
            run.heartbeat_at, run.processed = utcnow(), done
            db.commit()
            leases.acquire(db, lease, holder, settings.sync_stale_s)

        rep.hook = hook                           # type: ignore[attr-defined]
        try:
            work(db, rep)
            upsert.finish(rep)
            db.commit()
            status, msg = ("partial" if rep.errors else "ok"), None
        except Exception as exc:   # noqa: BLE001 - every failure is recorded, then handed back sanitized
            db.rollback()
            msg = scrub(f"{type(exc).__name__}: {exc}", 200)
            rep.errors.append({"sheet": "", "row": None, "column": "", "code": "source_error", "reason": msg})  # type: ignore[arg-type]
            failure = exc if isinstance(exc, ApiError) else upstream("همگام‌سازی ناموفق بود")
            status = "error"
            log.warning("sync failed", extra={"source": source, "exc_type": type(exc).__name__})
        db.expunge_all()
        run = db.get(SyncRun, run_id)
        run.status, run.finished_at, run.heartbeat_at = status, utcnow(), utcnow()
        run.created, run.updated, run.unchanged, run.skipped = rep.created, rep.updated, rep.unchanged, rep.skipped
        run.processed = rep.created + rep.updated + rep.unchanged + rep.skipped
        run.errors = [e if isinstance(e, dict) else {"sheet": "", "row": None, "column": "", "code": "note", "reason": scrub(e, 200)}
                      for e in rep.errors[:upsert.MAX_ERRORS]]
        run.message = msg or (f"created={rep.created} updated={rep.updated} unchanged={rep.unchanged} skipped={rep.skipped}"
                              + (f" errors={len(rep.errors)}" if rep.errors else ""))
        db.commit()
        leases.release(db, lease, holder)
    if cleanup:
        cleanup()
    return failure


def execute(db: Session, sf: sessionmaker[Session], settings: Settings, source: str, work: Work, triggered_by: str,
            cleanup: Callable[[], None] | None = None) -> SyncRun:
    """Start ``work`` as a background job (own DB session, chunked commits, heartbeat) and wait up to
    ``TMS_SYNC_WAIT_S`` for it: a small import still answers with the finished run, a big one answers
    immediately with status 'running' and the client polls GET /sync/runs. One run per source (lease);
    a crashed run is recovered as stale."""
    recover_stale(db, settings)
    holder = uuid.uuid4().hex
    if not leases.acquire(db, f"sync:{source}", holder, settings.sync_stale_s):
        if cleanup:
            cleanup()
        raise conflict("همگام‌سازی دیگری در حال اجراست")
    run = SyncRun(source=source, triggered_by=triggered_by[:64], heartbeat_at=utcnow())
    db.add(run)
    db.commit()
    run_id = run.id
    fut = _get_pool().submit(_job, sf, settings, run_id, source, work, holder, cleanup)
    try:
        failure = fut.result(timeout=settings.sync_wait_s)
    except FutureTimeout:
        db.expire_all()
        return db.get(SyncRun, run_id)
    db.expire_all()
    if failure:
        raise failure
    return db.get(SyncRun, run_id)


def last_ok_start(db: Session, source: str) -> datetime | None:
    return db.scalar(select(SyncRun.started_at).where(SyncRun.source == source, SyncRun.status.in_(("ok", "partial")))
                     .order_by(SyncRun.started_at.desc()).limit(1))


def run_source(db: Session, sf: sessionmaker[Session], settings: Settings, source: str, *, full: bool, triggered_by: str) -> SyncRun:
    if source not in ("excel", "ifs"):
        raise conflict("منبع نامعتبر")
    cfg = connector_config(db, source)
    factory = gateway.get_factory()
    since = None if (full or source == "excel") else last_ok_start(db, "ifs")
    if since:
        since = since - timedelta(minutes=5)   # clock-skew safety; upsert is idempotent anyway

    def work(wdb: Session, rep: SyncReport) -> None:
        src = factory.build_employee_source(source, cfg)
        upsert.upsert_employees(wdb, src.fetch_employees(since), source, rep)      # streamed, committed per chunk
        if source == "excel" and cfg.get("idp_path"):
            upsert.upsert_idp(wdb, factory.build_excel_gateway().read_idp(cfg["idp_path"]), rep)

    return execute(db, sf, settings, source, work, triggered_by)
