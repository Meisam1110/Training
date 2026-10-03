"""Dashboard aggregates -- the four workbook Dashboard lists, computed server-side.

* over3_motivations: per TICKET (legacy IDP!R = COUNTIFS(Record[Ticket]=t, Record[Motivation]<>"Yes")):
  tickets offered in at least `over3_threshold` (default 3) runs without a "Yes" motivation.
* level3_due: computed by Dev-B's compute_due (the single Level-3 implementation): status "Evaluation Level 3", soft
  skill, due from end + N days (N default 60), not yet marked level3_sent.
* not_started_courses: runs not cancelled/completed whose start date is today or later (or unset).
* payment_not_started: runs already started with an amount, but no payment process / PR start date.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.services import automation, gateway, rules
from app.api.services import serializers as ser
from app.api.services import settings_store as rt
from app.models import Course, CourseRun, Employee, Enrollment, EnrollmentOffer, Letter, MessageLog, SyncRun

LIMIT = 200


def run_counts(db: Session, ids: list[int]) -> dict[int, dict[str, int]]:
    """Per-run progress numbers for a whole page of runs in TWO queries (never one per run)."""
    if not ids:
        return {}
    out = {i: {"participants": 0, "motivations_yes": 0, "letters_sent": 0, "level3_started": 0} for i in ids}
    q = (select(Enrollment.run_id, func.count(),
                func.sum(case((Enrollment.motivation == "Yes", 1), else_=0)),
                func.sum(case((or_(Enrollment.level3_sent.is_(True), Enrollment.level3_status != ""), 1), else_=0)))
         .where(Enrollment.run_id.in_(ids)).group_by(Enrollment.run_id))
    for rid, n, y, l3 in db.execute(q):
        out[rid].update(participants=n, motivations_yes=int(y or 0), level3_started=int(l3 or 0))
    for rid, n in db.execute(select(Letter.run_id, func.count()).where(Letter.run_id.in_(ids), Letter.state == "sent")
                             .group_by(Letter.run_id)):
        out[rid]["letters_sent"] = n
    return out


def over3_list(db: Session, conf: dict, limit: int = LIMIT) -> list[dict]:
    """Per TICKET (legacy IDP!R): offered in >= over3_threshold runs without a "Yes"."""
    counts = rules.non_yes_counts(db)
    over = {e: n for e, n in counts.items() if n >= int(conf["over3_threshold"])}
    o3: list[dict] = []
    if over:
        ens = {e.id: e for e in db.scalars(select(Enrollment).options(joinedload(Enrollment.employee))
                                           .where(Enrollment.id.in_(list(over))))}
        runs_of: dict[int, list[int]] = {}
        for eid, rid in db.execute(select(EnrollmentOffer.enrollment_id, EnrollmentOffer.run_id)
                                   .where(EnrollmentOffer.enrollment_id.in_(list(over)), EnrollmentOffer.motivation != "Yes")
                                   .order_by(EnrollmentOffer.id)):
            runs_of.setdefault(eid, []).append(rid)
        for eid, n in sorted(over.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]:
            e = ens[eid]
            o3.append({"enrollment_id": e.id, "ticket": e.ticket, "emp_no": e.employee.emp_no,
                       "employee_name": f"{e.employee.first_name_en} {e.employee.last_name_en}".strip(),
                       "division": e.employee.division, "course_name": e.course_name, "non_yes_count": n,
                       "run_ids": runs_of.get(eid, [])})
    return o3


def level3_list(db: Session, today: date, conf: dict, limit: int = LIMIT) -> list[dict]:
    """Level-3 due, from Dev-B's compute_due (the single implementation)."""
    l3 = []
    facts = automation.build_facts(db, level3_only=True)
    by_id = {f.enrollment_id: f for f in facts}
    due_ids = {i.enrollment_id: by_id[i.enrollment_id] for i in
               gateway.compute_due(facts, today, level3_after_days=int(conf["level3_after_days"])) if i.kind == "level3_due"}
    if due_ids:
        for e in db.scalars(select(Enrollment).options(joinedload(Enrollment.employee)).where(Enrollment.id.in_(list(due_ids)))
                            .order_by(Enrollment.end_date, Enrollment.id)).unique():
            end = due_ids[e.id].end_date
            l3.append({"enrollment_id": e.id, "ticket": e.ticket, "emp_no": e.employee.emp_no,
                       "employee_name": f"{e.employee.first_name_en} {e.employee.last_name_en}".strip(),
                       "course_name": e.course_name, "end_date": end.isoformat(), "days_since_end": (today - end).days})
            if len(l3) >= limit:
                break

    return l3


def build(db: Session, today: date) -> dict:
    conf = rt.get_all(db)
    runs_q = select(CourseRun).options(joinedload(CourseRun.course), joinedload(CourseRun.institute))
    not_started = list(db.scalars(runs_q.where(CourseRun.status.notin_(("cancelled", "completed")),
                                               or_(CourseRun.start_date.is_(None), CourseRun.start_date >= today))
                                  .order_by(CourseRun.start_date, CourseRun.id).limit(LIMIT)).unique())
    unpaid = list(db.scalars(runs_q.where(CourseRun.status != "cancelled", CourseRun.start_date <= today,
                                          CourseRun.amount.is_not(None), CourseRun.payment_process == "",
                                          CourseRun.pr_process_start_date.is_(None))
                             .order_by(CourseRun.start_date, CourseRun.id).limit(LIMIT)).unique())
    cnt = run_counts(db, [r.id for r in not_started + unpaid])
    ns = [ser.run(r, today, cnt.get(r.id)) for r in not_started]
    pn = [{**ser.run(r, today, cnt.get(r.id)), "days_since_start": (today - r.start_date).days} for r in unpaid]

    o3 = over3_list(db, conf)
    l3 = level3_list(db, today, conf)

    def n(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    last = {}
    for src in ("excel", "ifs"):
        s = db.scalar(select(SyncRun).where(SyncRun.source == src).order_by(SyncRun.started_at.desc()).limit(1))
        last[src] = ser.sync_run(s) if s else None
    return {
        "not_started_courses": ns, "payment_not_started": pn, "over3_motivations": o3, "level3_due": l3,
        "counts": {"employees": n(Employee), "courses": n(Course), "runs": n(CourseRun), "enrollments": n(Enrollment),
                   "unassigned_enrollments": db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.run_id.is_(None))) or 0,
                   "letters": n(Letter), "messages": n(MessageLog), "not_started_courses": len(ns),
                   "payment_not_started": len(pn), "over3_motivations": len(o3), "level3_due": len(l3)},
        "last_sync": last,
    }
