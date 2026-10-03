"""Email sending with an idempotency key stored in MessageLog: a retry never double-sends."""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found, validation
from app.api.services import gateway, letters
from app.audit import record as audit
from app.config import Settings
from app.contracts import OutgoingEmail, SendResult
from app.models import ConnectorConfig, Letter, MessageLog, User, utcnow
from app.schemas.domain import EmailSendIn
from app.security.redact import scrub

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pick_channel(db: Session, want: str | None) -> tuple[str, dict]:
    kinds = [want] if want else ["graph", "smtp"]
    for k in kinds:
        c = db.get(ConnectorConfig, k)
        if c and c.enabled:
            return k, {**(c.public or {}), **(c.secrets or {})}
    raise conflict("هیچ رابط ایمیل فعالی پیکربندی نشده است")


def _summ(results: list[dict], dry: bool) -> str:
    oks = sum(1 for r in results if r["ok"])
    if oks == len(results):
        return "dry_run" if dry else "sent"
    return "partial" if oks else "failed"


def _payload(m: MessageLog, replayed: bool) -> dict:
    return {"id": m.id, "status": m.status, "dry_run": m.dry_run, "results": m.results, "replayed": replayed,
            "idempotency_key": m.idempotency_key.removesuffix(":dry"), "letter_id": m.letter_id}


def _hash(**parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def send(db: Session, settings: Settings, user: User | None, body: EmailSendIn, header_key: str | None = None, ip: str = "") -> dict:
    letter: Letter | None = None
    if body.letter_id:
        letter = db.get(Letter, body.letter_id)
        if not letter:
            raise not_found("نامه")
    tpl_extra: dict = {}
    if letter:
        subject, html = body.subject or letter.subject, letter.html_body
        attachments = [(letter.filename, letters.read_letter_file(settings, letter), DOCX)]
    elif body.template_id:
        from app.api.services import templates as tsvc
        tpl = tsvc.load(db, body.template_id)
        ctx = tsvc.context_fields(db, settings, tpl.kind, body.run_id, body.enrollment_id)[0] if (body.run_id or body.enrollment_id) else {}
        fields = {**ctx, **body.fields}
        res = tsvc.render_strict(tpl, fields)
        subject, html, attachments = body.subject or res["subject"], res["html"], []
        tpl_extra = {"template_id": tpl.id, "template_version": tpl.version, "run": body.run_id, "enr": body.enrollment_id}
    else:
        r = letters.render(letters.get_renderer(settings), body.template, body.fields, body.lang)
        subject, html = body.subject or r.subject, r.html_body
        attachments = [(r.filename, r.docx_bytes, DOCX)]
    if not subject:
        raise validation("موضوع ایمیل لازم است", subject="الزامی است")
    # the key is bound to the WHOLE request: same key + different subject/cc/recipients/content -> 409, never a silent replay
    rh = _hash(letter=body.letter_id, template=body.template, fields=body.fields if not letter else None, lang=body.lang,
               subject=subject, to=sorted(body.recipients), cc=sorted(body.cc), channel=body.channel, **tpl_extra)
    return deliver(db, settings, user, key=body.idempotency_key or header_key or f"auto-{uuid.uuid4().hex}", request_hash=rh,
                   letter=letter, subject=subject, html=html, attachments=attachments, recipients=body.recipients, cc=body.cc,
                   dry_run=body.dry_run, channel=body.channel, ip=ip)


def deliver(db: Session, settings: Settings, user: User | None, *, key: str, request_hash: str, letter: Letter | None, subject: str,
            html: str, attachments: list[tuple[str, bytes, str]], recipients: list[str], cc: list[str] | tuple = (), dry_run: bool = False,
            channel: str | None = None, ip: str = "") -> dict:
    store = key + (":dry" if dry_run else "")
    prior = db.scalar(select(MessageLog).where(MessageLog.idempotency_key == store))
    todo = list(recipients)
    kept: list[dict] = []
    if prior:
        same = (prior.request_hash == request_hash if prior.request_hash else
                set(prior.recipients) == set(recipients) and prior.letter_id == (letter.id if letter else None))
        if not same:
            raise conflict("این کلید idempotency با درخواست دیگری (گیرنده، موضوع، رونوشت یا محتوا) استفاده شده است")
        if prior.status == "pending":
            if (utcnow() - prior.updated_at).total_seconds() < settings.email_pending_ttl_s:
                raise conflict("درخواست قبلی با این کلید هنوز در حال پردازش است")
            # a crashed worker left it pending: after the TTL the key may be retried (a message that WAS accepted
            # right before the crash can be sent twice -- documented trade-off of at-least-once)
        elif prior.status in ("sent", "dry_run"):
            return _payload(prior, True)
        else:
            kept = [r for r in prior.results if r["ok"]]
            done = {r["recipient"] for r in kept}
            todo = [r for r in recipients if r not in done]

    sender = None
    chan = "none"
    if not (dry_run and not _has_connector(db, channel)):
        chan, cfg = _pick_channel(db, channel)
        sender = gateway.get_factory().build_email_sender(chan, cfg)

    if prior is None:
        log = MessageLog(idempotency_key=store, letter_id=letter.id if letter else None, subject=subject[:500],
                         recipients=list(recipients), dry_run=dry_run, status="pending", channel=chan,
                         created_by=user.id if user else None, request_hash=request_hash)
        db.add(log)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise conflict("درخواست هم‌زمان با همین کلید در حال پردازش است") from None
    else:
        log = prior
        log.status, log.request_hash, log.updated_at = "pending", request_hash, utcnow()
        db.commit()

    msg = OutgoingEmail(to=todo, subject=subject, html_body=html, cc=list(cc), attachments=attachments, idempotency_key=store)
    try:
        if not todo:
            res = []                      # everything to-recipients already got it; only a failed Cc could remain
        elif sender is None:
            res = [SendResult(recipient=r, ok=True, message_id="dry-run") for r in todo]
        else:
            res = list(sender.send(msg, dry_run=dry_run))
    except Exception as exc:   # noqa: BLE001
        res = [SendResult(recipient=r, ok=False, error=scrub(exc, 120)) for r in todo]
    new = [{"recipient": x.recipient, "ok": bool(x.ok), "message_id": x.message_id, "error": scrub(x.error, 200)} for x in res]
    have = {n["recipient"] for n in new}
    new += [{"recipient": r, "ok": False, "message_id": "", "error": "no result from sender"} for r in todo if r not in have]
    log.results = kept + new
    log.status = _summ(log.results, dry_run)
    log.updated_at = utcnow()
    if letter and log.status == "sent":
        letter.state = "sent"
    audit(db, "email.send", user=user, actor="" if user else "scheduler", entity="message", entity_id=log.id, ip=ip,
          detail={"status": log.status, "recipients": len(recipients), "dry_run": dry_run, "channel": chan})
    db.commit()
    return _payload(log, False)


def _has_connector(db: Session, want: str | None) -> bool:
    return any((c := db.get(ConnectorConfig, k)) and c.enabled for k in ([want] if want else ["graph", "smtp"]))


