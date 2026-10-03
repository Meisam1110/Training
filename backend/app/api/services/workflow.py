"""Derived, read-only progress of a course run, computed from real data (never stored)."""
from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import CourseRun, Enrollment, Letter

ANNOUNCED_STATUSES = ("announced", "open", "running", "completed")


def _sent(db: Session, run_id: int, kind: str) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Letter)
                          .where(Letter.run_id == run_id, Letter.kind == kind, Letter.state == "sent")))


def workflow(db: Session, r: CourseRun) -> dict[str, bool]:
    """
    announced              a course_announcement letter was e-mailed (state "sent") OR the run status is announced/open/running/completed
    motivations_collected  the run has participants and every one has answered (motivation Yes or No)
    institute_letter_sent  an institute_letter for the run was e-mailed successfully to all recipients
    invoice_received       the run has an invoice_receive_date
    settlement_sent        a settlement_letter for the run was e-mailed successfully
    level3_started         any participant has level3_sent or a non-empty level3_status
    """
    total, answered, l3 = db.execute(
        select(func.count(),
               func.coalesce(func.sum(case((Enrollment.motivation.in_(("Yes", "No")), 1), else_=0)), 0),
               func.coalesce(func.sum(case((or_(Enrollment.level3_sent.is_(True), Enrollment.level3_status != ""), 1), else_=0)), 0))
        .where(Enrollment.run_id == r.id)).one()
    return {
        "announced": r.status in ANNOUNCED_STATUSES or _sent(db, r.id, "course_announcement"),
        "motivations_collected": total > 0 and answered == total,
        "institute_letter_sent": _sent(db, r.id, "institute_letter"),
        "invoice_received": r.invoice_receive_date is not None,
        "settlement_sent": _sent(db, r.id, "settlement_letter"),
        "level3_started": int(l3) > 0,
    }
