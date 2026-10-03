"""Uniform list handling: ?page=1&page_size=50&q=&sort=-start_date."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from .errors import validation

MAX_PAGE_SIZE = 200


class PageParams:
    def __init__(self, page: int = Query(1, ge=1, le=10_000_000), page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
                 q: str = Query("", max_length=200), sort: str = Query("", max_length=100)):
        if "\x00" in q or "\x00" in sort:
            raise validation("کاراکتر نامعتبر در جستجو", q="کاراکتر NUL مجاز نیست")
        self.page, self.page_size, self.q, self.sort = page, page_size, q.strip(), sort.strip()


def _primary_key(stmt: Select):
    try:
        entity = stmt.column_descriptions[0]["entity"]
        return sa_inspect(entity).primary_key[0]
    except Exception:   # noqa: BLE001 - not an ORM entity select: nothing to add
        return None


def apply_sort(stmt: Select, sort: str, allowed: Mapping[str, Any], default: str) -> Select:
    keys = [k for k in (sort or default).split(",") if k]
    cols = []
    for k in keys:
        desc = k.startswith("-")
        name = k.lstrip("-+ ")
        if name not in allowed:
            raise validation("فیلد مرتب‌سازی نامعتبر", sort=f"مقادیر مجاز: {', '.join(sorted(allowed))}")
        c = allowed[name]
        cols.append(c.desc() if desc else c.asc())
    # every list has a TOTAL order: ties on the requested column(s) fall back to the primary key, so rows never reshuffle between polls
    pk = _primary_key(stmt)
    if pk is not None:
        cols.append(pk.asc())
    return stmt.order_by(*cols)


def like(q: str) -> str:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def paginate(db: Session, stmt: Select, p: PageParams, serialize: Callable[[Any], dict],
             *, scalars: bool = True, prepare: Callable[[list], None] | None = None) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(p.page_size).offset((p.page - 1) * p.page_size))
    rows = rows.scalars().unique().all() if scalars else rows.all()
    if prepare:
        prepare(list(rows))          # one batched look-up for the whole page instead of one per row
    return {"items": [serialize(r) for r in rows], "total": total, "page": p.page, "page_size": p.page_size}
