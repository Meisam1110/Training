"""Automation: build EnrollmentFacts from the DB, call compute_due, run daily under a lease."""
from __future__ import annotations

import asyncio
import html
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.api.services import gateway, leases
from app.api.services import settings_store as rt
from app.audit import record as audit
from app.config import Settings
from app.contracts import DueItem, EnrollmentFact
from app.models import ConnectorConfig, Enrollment, EnrollmentOffer, Letter, SyncRun, utcnow

log = logging.getLogger("tms.automation")
LEASE = "automation"


def build_facts(db: Session, only_ids: list[int] | None = None, level3_only: bool = False) -> list[EnrollmentFact]:
    """DB -> Dev-B's flat facts. Per ticket the scheduler counts facts whose motivation is not "Yes"
    (legacy IDP!R), so a ticket yields:
      * one PRIMARY fact (its current run) that drives level3 / deadline / payment rules;
      * one HISTORY fact per earlier offer (run other than the current one) with neutral status/dates,
        so it only feeds the per-ticket motivation count.
    A ticket not offered in any run has a neutral placeholder motivation "Yes" (no offer = no Record row
    = nothing to count; it has no deadline or start date so no other rule can fire on it)."""
    facts: list[EnrollmentFact] = []
    offers: dict[int, list[EnrollmentOffer]] = {}
    oq = select(EnrollmentOffer).order_by(EnrollmentOffer.id)
    q = select(Enrollment).options(joinedload(Enrollment.run)).where(Enrollment.status != "cancelled")
    if only_ids is not None:
        oq, q = oq.where(EnrollmentOffer.enrollment_id.in_(only_ids)), q.where(Enrollment.id.in_(only_ids))
    if level3_only:            # Level-3 candidates only: skip the offer history (it only feeds the over-3 count)
        q = q.where(func.lower(Enrollment.current_status) == "evaluation level 3", Enrollment.level3_sent.is_(False))
        oq = oq.where(EnrollmentOffer.id < 0)
    for o in db.scalars(oq):
        offers.setdefault(o.enrollment_id, []).append(o)
    for e in db.scalars(q).unique():
        r = e.run
        paid = bool(r and (r.payment_process or r.pr_process_start_date))
        facts.append(EnrollmentFact(
            enrollment_id=e.id, run_id=r.id if r else 0, ticket=e.ticket, course_name=e.course_name, category=e.category,
            current_status=e.current_status, end_date=e.end_date or (r.end_date if r else None),
            run_start_date=r.start_date if r else None, registration_deadline=r.deadline if r else None,
            motivation=e.motivation if r else "Yes", payment_started=paid, level3_sent=e.level3_sent))
        for o in offers.get(e.id, []):
            if o.run_id == e.run_id:
                continue
            facts.append(EnrollmentFact(
                enrollment_id=e.id, run_id=o.run_id or 0, ticket=e.ticket, course_name=e.course_name, category="",
                current_status="", end_date=None, run_start_date=None, registration_deadline=None,
                motivation=o.motivation, payment_started=True, level3_sent=True))
    return facts


def due(db: Session, today: date) -> list[DueItem]:
    c = rt.get_all(db)
    return _dedupe(gateway.compute_due(build_facts(db), today, level3_after_days=int(c["level3_after_days"]),
                               reminder_days=int(c["reminder_days"]),
                               over3_threshold=int(c["over3_threshold"])))    # both sides: count >= threshold


def _dedupe(items: list[DueItem]) -> list[DueItem]:
    seen, out = set(), []
    for i in items:
        k = (i.kind, i.enrollment_id, i.run_id)
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def item_dict(i: DueItem) -> dict:
    return {"kind": i.kind, "enrollment_id": i.enrollment_id, "run_id": i.run_id or None, "detail": i.detail}


def summarize(items: list[DueItem]) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i.kind] = out.get(i.kind, 0) + 1
    return out


def _employee_of(db: Session, enrollment_id: int) -> Enrollment | None:
    return db.scalar(select(Enrollment).options(joinedload(Enrollment.employee), joinedload(Enrollment.run))
                     .where(Enrollment.id == enrollment_id))


def _reminder_html(e: Enrollment) -> tuple[str, str]:
    course = html.escape(e.course_name)
    deadline = e.run.deadline.isoformat() if e.run and e.run.deadline else ""
    subject = f"یادآوری مهلت ثبت‌نام / Registration reminder: {e.course_name}"[:300]
    body = (f"<p dir='rtl'>همکار گرامی، مهلت ثبت‌نام دورهٔ «{course}» تا {html.escape(deadline)} است؛ لطفاً انگیزه‌نامه را تکمیل کنید.</p>"
            f"<p>Dear colleague, the registration deadline for &ldquo;{course}&rdquo; is {html.escape(deadline)}. "
            f"Please submit your motivation.</p>")
    return subject, body


def notify(db: Session, sf: sessionmaker[Session], settings: Settings, items: list[DueItem], today: date, *, send: bool) -> dict:
    """Level-3 requests and registration reminders. ``send=False`` (setting ``auto_send`` off, the default) only counts
    what WOULD go out. Idempotent: every e-mail has a fixed key (auto-l3-<enrollment>, auto-rem-<enrollment>-<deadline>),
    so a re-run or a second worker never sends twice, and a failed/partial send retries only what failed. A Level-3
    enrollment is marked level3_sent only AFTER its e-mail was accepted, so a failure keeps it due for the next run."""
    from app.api.services import letters, mailer
    from app.schemas.domain import EMAIL_RE, LetterIn
    stats: dict[str, int] = {"would_send": 0, "sent": 0, "failed": 0, "skipped_no_email": 0, "already_sent": 0}
    for it in items:
        if it.kind not in ("level3_due", "deadline_reminder") or it.enrollment_id is None:
            continue
        e = _employee_of(db, it.enrollment_id)
        to = (e.employee.email if e else "") or ""
        if e is None or not EMAIL_RE.match(to):
            stats["skipped_no_email"] += 1
            continue
        if not send:
            stats["would_send"] += 1
            continue
        try:
            if it.kind == "level3_due":
                key = f"auto-l3-{e.id}"
                letter = next((x for x in db.scalars(select(Letter).where(Letter.kind == "level3_request")
                                                     .order_by(Letter.id.desc()).limit(500)) if x.enrollment_ids == [e.id]), None)
                if letter is None:
                    made, _ = letters.create(db, sf, settings, None, LetterIn(kind="level3_request", enrollment_ids=[e.id]), today,
                                             mark=False)
                    letter = made[0]
                out = mailer.deliver(db, settings, None, key=key, request_hash=mailer._hash(kind="l3", enrollment=e.id),
                                     letter=letter, subject=letter.subject, html=letter.html_body,
                                     attachments=[(letter.filename, letters.read_letter_file(settings, letter), mailer.DOCX)],
                                     recipients=[to.lower()])
                if out["status"] == "sent":
                    letters.mark_level3(db, "level3_request", [e.id])
                    db.commit()
            else:
                subject, body = _reminder_html(e)
                dl = e.run.deadline.isoformat() if e.run and e.run.deadline else ""
                out = mailer.deliver(db, settings, None, key=f"auto-rem-{e.id}-{dl}", request_hash=mailer._hash(kind="rem", e=e.id, dl=dl),
                                     letter=None, subject=subject, html=body, attachments=[], recipients=[to.lower()])
            stats["already_sent" if out.get("replayed") else ("sent" if out["status"] == "sent" else "failed")] += 1
        except Exception:   # noqa: BLE001 - one bad enrollment never stops the run
            db.rollback()
            stats["failed"] += 1
            log.exception("auto notification failed")
    return stats


def run_now(db: Session, today: date, triggered_by: str, user=None, ip: str = "", *, settings: Settings | None = None,
            sf: sessionmaker[Session] | None = None) -> dict:
    started = utcnow()
    items = due(db, today)
    summary = summarize(items)
    conf = rt.get_all(db)
    notified = notify(db, sf, settings, items, today, send=bool(conf["auto_send"])) if (settings and sf) else {}
    db.add(SyncRun(source="automation", status="ok", started_at=started, finished_at=utcnow(), created=len(items),
                   triggered_by=triggered_by[:64], message=f"auto_send={'on' if conf['auto_send'] else 'off (dry run)'} {notified}"[:300]))
    rt.set_raw(db, "automation.last_run", {"at": utcnow().isoformat(), "counts": summary, "total": len(items), "notify": notified,
                                           "auto_send": bool(conf["auto_send"])})
    audit(db, "automation.run", user=user, actor="scheduler" if not user else "", entity="automation",
          detail={"total": len(items), "counts": summary, "by": triggered_by, "auto_send": bool(conf["auto_send"]), "notify": notified}, ip=ip)
    db.commit()
    return {"total": len(items), "counts": summary, "notify": notified, "items": [item_dict(i) for i in items]}


def tick(sf: sessionmaker[Session], settings: Settings, holder: str, today: date | None = None) -> bool:
    """One scheduler pass; True if it ran. Safe with many workers: lease + last-run check."""
    today = today or date.today()
    with sf() as db:
        conf = rt.get_all(db)
        if not conf["enabled"]:
            return False
        if not leases.acquire(db, LEASE, holder, 600):
            return False
        try:
            last = rt.get_raw(db, "automation.last_run")
            if last and datetime.fromisoformat(last["at"]) > utcnow() - timedelta(seconds=settings.automation_interval_s):
                return False
            run_now(db, today, "scheduler", settings=settings, sf=sf)
            return True
        except Exception:   # noqa: BLE001
            db.rollback()
            log.exception("automation tick failed")
            return False
        finally:
            leases.release(db, LEASE, holder)


def periodic(sf: sessionmaker[Session], settings: Settings, holder: str, state: dict) -> dict:
    """Scheduled IFS sync (setting ifs_sync_interval_min, 0 = off) and Excel folder watcher (setting watch_excel, off by
    default). One worker at a time (lease); a re-import of an unchanged file is harmless (idempotent upsert)."""
    from app.api.services import sync
    from app.integrations.excel.watcher import FolderWatcher
    out: dict = {}
    with sf() as db:
        conf = rt.get_all(db)
        if not (conf["watch_excel"] or int(conf["ifs_sync_interval_min"]) > 0):
            state.pop("watcher", None)
            return out
        if not leases.acquire(db, "sched-sync", holder, 120):
            return out
        try:
            interval = int(conf["ifs_sync_interval_min"])
            if interval > 0:
                cfg = db.get(ConnectorConfig, "ifs")
                last = sync.last_ok_start(db, "ifs")
                if cfg and cfg.enabled and (last is None or last < utcnow() - timedelta(minutes=interval)):
                    r = sync.run_source(db, sf, settings, "ifs", full=False, triggered_by="scheduler")
                    out["ifs"] = r.status
            if conf["watch_excel"]:
                cfg = db.get(ConnectorConfig, "excel")
                wd = (cfg.public or {}).get("watch_dir") if cfg and cfg.enabled else None
                if wd:
                    w = state.get("watcher")
                    if w is None or str(w.directory) != wd:
                        w = state["watcher"] = FolderWatcher(wd)
                    if w.poll():
                        r = sync.run_source(db, sf, settings, "excel", full=False, triggered_by="watcher")
                        out["excel"] = r.status
        except Exception:   # noqa: BLE001
            db.rollback()
            log.exception("scheduled sync failed")
        finally:
            leases.release(db, "sched-sync", holder)
    return out


async def loop(sf: sessionmaker[Session], settings: Settings) -> None:
    holder = uuid.uuid4().hex
    poll = min(settings.automation_interval_s, 60)
    state: dict = {}
    while True:
        try:
            await asyncio.to_thread(tick, sf, settings, holder)
            await asyncio.to_thread(periodic, sf, settings, holder, state)
        except asyncio.CancelledError:
            raise
        except Exception:   # noqa: BLE001
            log.exception("automation loop error")
        await asyncio.sleep(poll)
