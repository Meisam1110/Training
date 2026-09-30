"""Letter numbering: an atomic per-series counter.

The increment is a single UPDATE ... RETURNING in its own short transaction, so concurrent
requests (threads, workers, processes) get distinct values and the row lock (PostgreSQL) /
write lock (SQLite) is held for microseconds. The UNIQUE(kind, seq) on ``letters`` is the
backstop. A render failure after allocation leaves a gap, never a duplicate.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import LetterCounter


def next_number(factory: sessionmaker[Session], series: str, start: int = 0, prefix: str = "") -> tuple[int, str]:
    for _ in range(5):
        with factory() as db:
            val = db.execute(update(LetterCounter).where(LetterCounter.series == series)
                             .values(value=LetterCounter.value + 1).returning(LetterCounter.value)).scalar()
            if val is None:
                try:
                    db.add(LetterCounter(series=series, value=start + 1))
                    db.flush()
                    val = start + 1
                except IntegrityError:
                    db.rollback()
                    continue
            db.commit()
            return val, f"{prefix}{val}"
    raise RuntimeError("could not allocate a letter number")
