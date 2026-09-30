"""Scheduler rules as a pure function of DB-free facts (``contracts.compute_due``).

All date math uses ``datetime.date`` only (no timezones, no clock): *today* is passed in.

Semantics (documented boundary choices)
* level3_due: category contains "soft skill" (case/space/hyphen-insensitive substring, like the legacy SEARCH and Core), status is exactly
  "Evaluation Level 3" (case-insensitive), level3 not yet sent, ``end_date`` known and
  ``(today - end_date).days >= level3_after_days`` -> due ON day N (end + 60 days), not day N+1.
* deadline_reminder: deadline known, motivation still empty, and
  ``0 <= (deadline - today).days <= reminder_days`` (deadline day itself still reminds).
* over3_motivations: legacy ``COUNTIFS(Record[Ticket]=ticket, Motivation<>"Yes") >= 3``: per non-empty
  TICKET (the same ticket appears on several enrollment facts), the number of facts whose motivation
  != "Yes" (blank counts) is ``>= over3_threshold`` (default 3). One item per ticket.
* payment_not_started: run has started (``run_start_date <= today``), the enrollment's motivation is
  "Yes" and payment not started. One item per run.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Sequence

from app.contracts import DueItem, EnrollmentFact

LEVEL3_STATUS = "evaluation level 3"
_ORDER = {"level3_due": 0, "deadline_reminder": 1, "over3_motivations": 2, "payment_not_started": 3}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", (s or "").strip().lower())


def is_soft_skill(category: str) -> bool:
    return "soft skill" in _norm(category)


def compute_due(facts: Sequence[EnrollmentFact], today: date, *, level3_after_days: int = 60,
                reminder_days: int = 2, over3_threshold: int = 3) -> list[DueItem]:
    items: list[DueItem] = []

    for f in facts:
        if (not f.level3_sent and f.end_date is not None and _norm(f.current_status) == LEVEL3_STATUS
                and is_soft_skill(f.category) and today >= f.end_date + timedelta(days=level3_after_days)):
            days = (today - f.end_date).days
            items.append(DueItem("level3_due", f.enrollment_id, f.run_id,
                                 f"{f.ticket}: course ended {days} days ago (>= {level3_after_days}), "
                                 f"Level 3 evaluation due"))

    for f in facts:
        if f.registration_deadline is not None and not f.motivation.strip():
            left = (f.registration_deadline - today).days
            if 0 <= left <= reminder_days:
                items.append(DueItem("deadline_reminder", f.enrollment_id, f.run_id,
                                     f"{f.ticket}: registration deadline in {left} day(s), no motivation yet"))

    by_ticket: dict[str, list[EnrollmentFact]] = defaultdict(list)
    for f in facts:
        if f.ticket.strip():
            by_ticket[f.ticket.strip()].append(f)
    for ticket, group in by_ticket.items():
        non_yes = [g for g in group if g.motivation.strip().lower() != "yes"]
        if len(non_yes) >= over3_threshold:
            first = min(non_yes, key=lambda g: g.enrollment_id)
            items.append(DueItem("over3_motivations", first.enrollment_id, None,
                                 f"{ticket}: {len(non_yes)} motivations are not 'Yes' (threshold {over3_threshold})"))

    seen_runs: set[int] = set()
    for f in sorted(facts, key=lambda x: (x.run_id, x.enrollment_id)):
        if (f.run_start_date is not None and f.run_start_date <= today and not f.payment_started
                and f.motivation.strip().lower() == "yes" and f.run_id not in seen_runs):
            seen_runs.add(f.run_id)
            items.append(DueItem("payment_not_started", None, f.run_id,
                                 f"run {f.run_id} ({f.course_name}): started on {f.run_start_date.isoformat()}, "
                                 f"payment process not started"))

    items.sort(key=lambda i: (_ORDER[i.kind], i.run_id or 0, i.enrollment_id or 0))
    return items
