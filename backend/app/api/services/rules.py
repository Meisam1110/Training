"""Business rules from docs/ANALYSIS.md as server-side logic. No hardcoded years, budgets,
paths or letter numbers -- every threshold is a parameter fed from runtime settings."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import CourseRun, Employee, Enrollment, EnrollmentOffer

MAX_TICKETS_PER_MANAGER = 9
LEVEL3_STATUS = "evaluation level 3"


def norm(s: str | None) -> str:
    return " ".join((s or "").casefold().split())


def level3_due_ids(db: Session, enrollment_ids: Iterable[int], today: date, after_days: int) -> set[int]:
    """Level-3 eligibility has ONE implementation: Dev-B's ``app.automation.rules.compute_due`` (due on day
    ``end + N``, i.e. >= N days, soft-skill category, status "Evaluation Level 3", not yet sent). Core only
    builds the facts and asks, so dashboard, candidate flags and scheduler can never disagree."""
    from app.api.services import automation, gateway
    ids = list(enrollment_ids)
    if not ids:
        return set()
    facts = automation.build_facts(db, only_ids=ids)
    items = gateway.compute_due(facts, today, level3_after_days=after_days)
    return {i.enrollment_id for i in items if i.kind == "level3_due" and i.enrollment_id is not None}


def non_yes_counts(db: Session, enrollment_ids: Iterable[int] | None = None) -> dict[int, int]:
    """Legacy IDP!R, per TICKET: COUNTIFS(Record[Ticket]=this ticket, Record[Motivation]<>"Yes").
    Each offer (= Record row) of the ticket in a run counts once; cancelled tickets are ignored."""
    stmt = (select(EnrollmentOffer.enrollment_id, func.sum(case((EnrollmentOffer.motivation != "Yes", 1), else_=0)))
            .join(Enrollment, Enrollment.id == EnrollmentOffer.enrollment_id)
            .where(Enrollment.status != "cancelled").group_by(EnrollmentOffer.enrollment_id))
    if enrollment_ids is not None:
        stmt = stmt.where(EnrollmentOffer.enrollment_id.in_(list(enrollment_ids)))
    return {eid: int(n or 0) for eid, n in db.execute(stmt)}


def sync_offer(db: Session, e: Enrollment) -> None:
    """Keep the offer row of the enrollment's CURRENT run in step with run assignment/motivation."""
    if not e.run_id:
        return
    key = e.run.run_key if e.run else db.get(CourseRun, e.run_id).run_key
    o = db.scalar(select(EnrollmentOffer).where(EnrollmentOffer.enrollment_id == e.id, EnrollmentOffer.offer_key == key))
    if o is None:
        db.add(EnrollmentOffer(enrollment_id=e.id, run_id=e.run_id, offer_key=key, motivation=e.motivation))
    else:
        o.run_id, o.motivation = e.run_id, e.motivation


def eff_dates(e: Enrollment) -> tuple[date | None, date | None]:
    if e.run and (e.run.start_date or e.run.end_date):
        return e.run.start_date, e.run.end_date or e.run.start_date
    return e.start_date, e.end_date or e.start_date


def overlaps(a: tuple[date | None, date | None], b: tuple[date | None, date | None]) -> bool:
    if not (a[0] and a[1] and b[0] and b[1]):
        return False
    return a[0] <= b[1] and b[0] <= a[1]


def division_changed(e: Enrollment) -> bool:
    return bool(norm(e.employee.division) and norm(e.department) and norm(e.employee.division) != norm(e.department))


def not_active(emp: Employee) -> bool:
    return norm(emp.status) != "active"


@dataclass
class CandidateResult:
    candidates: list[tuple[Enrollment, list[str]]] = field(default_factory=list)
    excluded: list[tuple[Enrollment, str, str]] = field(default_factory=list)   # (enrollment, reason, other ticket)


def search_candidates(db: Session, run: CourseRun, *, course_name: str | None, threshold: int,
                      include_flagged: bool, today: date, after_days: int) -> CandidateResult:
    needle = norm(course_name or run.course.name)
    res = CandidateResult()
    if not needle:
        return res
    stmt = (select(Enrollment).options(joinedload(Enrollment.employee), joinedload(Enrollment.run))
            .where(Enrollment.run_id.is_(None), Enrollment.attendance_status == "-", Enrollment.status != "cancelled")
            .order_by(Enrollment.id))
    for token in needle.split():        # SQL pre-filter on every word; the exact normalised-substring test follows in Python
        stmt = stmt.where(func.lower(Enrollment.course_name).contains(token, autoescape=True))
    pool = [e for e in db.scalars(stmt).unique() if needle in norm(e.course_name)]
    if not pool:
        return res
    emp_ids = {e.employee_id for e in pool}
    counts = non_yes_counts(db, [e.id for e in pool])
    l3 = level3_due_ids(db, [e.id for e in pool], today, after_days)
    others: dict[int, list[Enrollment]] = {}
    # legacy: the overlap test is against BOOKED courses (assigned to a run), not other pending IDP requests
    for o in db.scalars(select(Enrollment).options(joinedload(Enrollment.run))
                        .where(Enrollment.employee_id.in_(emp_ids), Enrollment.run_id.is_not(None),
                               Enrollment.status != "cancelled")).unique():
        others.setdefault(o.employee_id, []).append(o)
    rd = (run.start_date, run.end_date or run.start_date)
    for e in pool:
        clash = next((o for o in others.get(e.employee_id, []) if o.id != e.id and o.run_id != run.id
                      and overlaps(rd, eff_dates(o))), None)
        if clash:
            res.excluded.append((e, "date_overlap", clash.ticket))
            continue
        flags: list[str] = []
        if counts.get(e.id, 0) >= threshold:
            flags.append("over_motivation_limit")
        if division_changed(e):
            flags.append("division_change")
        if not_active(e.employee):
            flags.append("non_active")
        if e.id in l3:
            flags.append("level3_eligible")
        blocking = [f for f in flags if f != "level3_eligible"]
        if blocking and not include_flagged:
            res.excluded.append((e, ",".join(blocking), ""))
        else:
            res.candidates.append((e, flags))
    return res


def line_manager_batches(enrollments: Sequence[Enrollment]) -> tuple[list[tuple[str, list[Enrollment]]], list[Enrollment]]:
    """Group by the employee's supervisor; at most 9 tickets per letter. Returns
    ([(supervisor_emp_no, batch)], enrollments without a supervisor)."""
    groups: dict[str, list[Enrollment]] = {}
    orphans: list[Enrollment] = []
    for e in enrollments:
        sup = (e.employee.supervisor_emp_no or "").strip()
        if not sup:
            orphans.append(e)
        else:
            groups.setdefault(sup, []).append(e)
    out = []
    for sup, items in groups.items():
        for i in range(0, len(items), MAX_TICKETS_PER_MANAGER):
            out.append((sup, items[i:i + MAX_TICKETS_PER_MANAGER]))
    return out, orphans


@dataclass(frozen=True)
class InvoiceSplit:
    total: Decimal
    per_attendee: Decimal
    shares: list[Decimal]
    motivations: int
    attendees: int


def invoice_split(amount: Decimal | float | int | str, motivations: int, attendees: int,
                  unit: Decimal = Decimal(1)) -> InvoiceSplit:
    """total = amount x motivations; each attendee pays total/attendees. Shares are integers of
    ``unit`` and sum EXACTLY to the total: the remainder is spread one unit at a time over the
    first attendees (largest-remainder), so no rial is created or lost."""
    if attendees <= 0:
        raise ValueError("attendees must be positive")
    if motivations < 0:
        raise ValueError("motivations must be >= 0")
    total_exact = Decimal(str(amount)) * motivations
    total_units = int((total_exact / unit).to_integral_value(ROUND_HALF_UP))
    base, rem = divmod(total_units, attendees)
    shares = [Decimal(base + (1 if i < rem else 0)) * unit for i in range(attendees)]
    return InvoiceSplit(total=Decimal(total_units) * unit, per_attendee=shares[0], shares=shares,
                        motivations=motivations, attendees=attendees)
