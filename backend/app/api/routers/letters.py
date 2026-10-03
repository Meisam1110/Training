from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.api.pagination import PageParams, apply_sort, like, paginate
from app.api.services import letters as svc
from app.api.services import serializers as ser
from app.audit import record as audit
from app.config import Settings
from app.deps import PathId, client_ip, get_db, get_settings, require
from app.models import Letter, User
from app.schemas.domain import INT_MAX, LetterIn

router = APIRouter(prefix="/letters", tags=["letters"])
SORT = {"id": Letter.id, "created_at": Letter.created_at, "number": Letter.seq, "kind": Letter.kind}


@router.get("")
def list_letters(p: PageParams = Depends(), kind: str = Query("", max_length=32), run_id: int | None = Query(None, ge=1, le=INT_MAX),
                 state: str = Query("", max_length=16), db: Session = Depends(get_db), _=Depends(require("viewer"))):
    stmt = select(Letter)
    if kind:
        stmt = stmt.where(Letter.kind == kind)
    if run_id:
        stmt = stmt.where(Letter.run_id == run_id)
    if state:
        stmt = stmt.where(Letter.state == state)
    if p.q:
        stmt = stmt.where(Letter.number.ilike(like(p.q), escape="\\") | Letter.subject.ilike(like(p.q), escape="\\"))
    return paginate(db, apply_sort(stmt, p.sort, SORT, "-id"), p, ser.letter)


@router.post("/preview")
def preview(body: LetterIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
            user: User = Depends(require("hr"))):
    out = svc.preview(db, settings, body, date.today())
    if body.kind in svc.PII_KINDS:            # the preview HTML carries participants' national IDs / phones
        audit(db, "letter.preview", user=user, entity="letter", ip=client_ip(request),
              detail={"kind": body.kind, "run_id": body.run_id, "pii_included": True})
        db.commit()
    return out


@router.post("", status_code=201)
def create(body: LetterIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
           user: User = Depends(require("hr"))):
    made, skipped = svc.create(db, request.app.state.session_factory, settings, user, body, date.today(), client_ip(request))
    items = [ser.letter(x) for x in made]
    return {**items[0], "items": items, "skipped": skipped}


@router.get("/{letter_id}/download")
def download(letter_id: PathId, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
             user: User = Depends(require("hr"))):
    x = db.get(Letter, letter_id)
    if not x:
        raise not_found("نامه")
    data = svc.read_letter_file(settings, x)
    audit(db, "letter.download", user=user, entity="letter", entity_id=x.id, ip=client_ip(request))
    db.commit()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(x.filename)}"})
