"""The ONLY door to Dev-B's code. Everything is imported lazily so the app boots (and tests
run with fakes) even when app.integrations / app.automation are not installed yet.

Tests replace ``get_factory`` and ``compute_due`` with fakes (tests/core/fakes.py)."""
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from app import contracts
from app.api.errors import upstream


def get_factory() -> Any:
    try:
        from app.integrations import factory  # type: ignore[attr-defined]
    except ImportError:
        raise upstream("ماژول یکپارچه‌سازی نصب نشده است") from None
    return factory


def compute_due(facts: Sequence[contracts.EnrollmentFact], today: date, **kw) -> list[contracts.DueItem]:
    try:
        from app.automation import rules  # type: ignore[attr-defined]
        fn = rules.compute_due
    except ImportError:
        fn = contracts.compute_due
    try:
        return list(fn(facts, today, **kw))
    except NotImplementedError:
        raise upstream("موتور زمان‌بندی در دسترس نیست") from None
