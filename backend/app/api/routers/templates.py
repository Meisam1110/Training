from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import validation
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import field_catalog as fc
from app.api.services import mailer
from app.api.services import serializers as ser
from app.api.services import templates as svc
from app.audit import record as audit
from app.config import Settings
from app.deps import PathId, client_ip, get_db, get_settings, require
from app.models import MessageTemplate, MessageTemplateVersion, User
from app.schemas.domain import SendTestIn, TemplateIn, TemplatePatch, TemplatePreviewIn

router = APIRouter(prefix="/templates", tags=["templates"])
SORT = {"name": MessageTemplate.name, "kind": MessageTemplate.kind, "updated_at": MessageTemplate.updated_at, "id": MessageTemplate.id,
        "version": MessageTemplate.version}


@router.get("/fields")
def fields(_=Depends(require("viewer"))):
    """The single catalogue behind the editor's field picker (derived from documents/specs.py)."""
    return {"items": fc.catalog(), "kinds": list(fc.ALL_KINDS)}


@router.get("")
def list_templates(p: PageParams = Depends(), kind: str = Query("", max_length=32), lang: str = Query("", max_length=8),
                   is_system: bool | None = None, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    svc.ensure_system(db)
    stmt = select(MessageTemplate)
    if kind:
        stmt = stmt.where(MessageTemplate.kind == kind)
    if lang:
        stmt = stmt.where(MessageTemplate.lang == lang)
    if is_system is not None:
        stmt = stmt.where(MessageTemplate.is_system == is_system)
    if p.q:
        stmt = stmt.where(MessageTemplate.name.ilike(like(p.q), escape="\\") | MessageTemplate.subject.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, SORT, "kind,name"), p, ser.template)


@router.post("", status_code=201)
def create(body: TemplateIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    t = svc.create(db, user, body.kind, body.name, body.lang, body.subject, body.body_html, client_ip(request))
    db.commit()
    return ser.template(t, detail=True)


@router.post("/preview")
def preview(body: TemplatePreviewIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
            user: User = Depends(require("hr"))):
    """Rendered subject + html with SAMPLE data, or real data when run_id / enrollment_id is given. Never fails on unknown or
    blank fields: it lists them (``unknown_fields``, ``missing_fields``) so the editor can show them."""
    if body.id:
        t = svc.load(db, body.id)
        kind, subject, html = t.kind, t.subject, t.body_html
    else:
        kind, subject, html = body.template.kind, svc.clean_subject(body.template.subject), svc.rich_text.sanitize(body.template.body_html)
    f, ctx = svc.context_fields(db, settings, kind, body.run_id, body.enrollment_id)
    out = svc.render(subject, html, f)
    if ctx == "real":
        audit(db, "template.preview", user=user, entity="template", entity_id=body.id or "", ip=client_ip(request),
              detail={"kind": kind, "run_id": body.run_id, "enrollment_id": body.enrollment_id, "pii_included": kind_has_pii(kind)})
        db.commit()
    return {**out, "kind": kind, "context": ctx}


def kind_has_pii(kind: str) -> bool:
    return fc.source_kind(kind) == "institute_letter"


@router.get("/{template_id}")
def get_template(template_id: PathId, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    return ser.template(svc.load(db, template_id), detail=True)


@router.patch("/{template_id}")
def patch_template(template_id: PathId, body: TemplatePatch, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    t = svc.update_fields(db, user, svc.load(db, template_id), body.model_dump(exclude_unset=True), client_ip(request))
    db.commit()
    return ser.template(t, detail=True)


@router.delete("/{template_id}")
def delete_template(template_id: PathId, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    svc.delete(db, user, svc.load(db, template_id), client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/{template_id}:duplicate", status_code=201)
def duplicate(template_id: PathId, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    c = svc.duplicate(db, user, svc.load(db, template_id), client_ip(request))
    db.commit()
    return ser.template(c, detail=True)


@router.post("/{template_id}:set-default")
def set_default(template_id: PathId, request: Request, db: Session = Depends(get_db), user: User = Depends(require("hr"))):
    t = svc.load(db, template_id)
    svc.make_default(db, t)
    audit(db, "template.set_default", user=user, entity="template", entity_id=t.id, ip=client_ip(request), detail={"kind": t.kind, "lang": t.lang})
    db.commit()
    return ser.template(t, detail=True)


@router.get("/{template_id}/versions")
def versions(template_id: PathId, db: Session = Depends(get_db), _=Depends(require("viewer"))):
    svc.load(db, template_id)
    rows = db.scalars(select(MessageTemplateVersion).where(MessageTemplateVersion.template_id == template_id)
                      .order_by(MessageTemplateVersion.version.desc())).all()
    return {"items": [{"version": v.version, "name": v.name, "lang": v.lang, "subject": v.subject, "body_html": v.body_html,
                       "created_by": v.created_by, "created_at": ser.iso(v.created_at)} for v in rows]}


@router.post("/{template_id}/versions/{version}:restore")
def restore(template_id: PathId, version: int = Path(ge=1, le=1_000_000), request: Request = None, db: Session = Depends(get_db),
            user: User = Depends(require("hr"))):
    t = svc.restore(db, user, svc.load(db, template_id), version, client_ip(request))
    db.commit()
    return ser.template(t, detail=True)


@router.post("/{template_id}:send-test")
def send_test(template_id: PathId, body: SendTestIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
              user: User = Depends(require("hr"))):
    """Sends the template (SAMPLE data) to the caller's OWN address only. Dry run unless an e-mail connector is configured."""
    t = svc.load(db, template_id)
    own = (user.email or (user.username if "@" in user.username else "")).lower()
    if not own:
        raise validation("برای حساب شما ایمیلی ثبت نشده است؛ مدیر سامانه باید آن را در تنظیمات کاربران وارد کند", to="ایمیل حساب ثبت نشده")
    if body.to != own:
        raise validation("ایمیل آزمایشی فقط به نشانی خود شما ارسال می‌شود", to="فقط ایمیل خودتان")
    out = svc.render(t.subject, t.body_html, fc.sample_fields())
    res = mailer.deliver(db, settings, user, key=f"test-{t.id}-{uuid.uuid4().hex[:12]}", request_hash=mailer._hash(test=t.id, v=t.version),
                         letter=None, subject=out["subject"] or "پیام آزمایشی", html=out["html"], attachments=[], recipients=[own],
                         dry_run=not mailer._has_connector(db, None), ip=client_ip(request))
    return {**res, "unknown_fields": out["unknown_fields"], "to": own}
