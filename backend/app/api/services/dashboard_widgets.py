"""Widget catalogue + per-widget data for the configurable dashboard (GET /dashboard/widgets, GET /dashboard/data).

Every widget is computed from the real tables with a fixed, small number of queries (no per-row look-ups); lists are bounded and
have a total order (tie-break on id). Money is an integer number of rials. Shapes are documented in CONTRACT_REQUESTS.md.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.api.errors import ApiError, forbidden, validation
from app.api.services import dashboard as dash
from app.api.services import gateway
from app.api.services import settings_store as rt
from app.models import ConnectorConfig, Course, CourseRun, Employee, Enrollment, Institute, SyncRun, utcnow

INST = aliased(Institute)

RANK = {"viewer": 1, "hr": 2, "admin": 3}
GRID_COLS = 12
ACTIVE = ("announced", "open", "running")
STAGES = (("planned", "برنامه‌ریزی‌شده"), ("announced", "اطلاع‌رسانی‌شده"), ("open", "ثبت‌نام باز"), ("running", "در حال برگزاری"),
          ("completed", "تکمیل‌شده"))
MONTHS_FA = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
RANGES = {"30d": (30, 6), "90d": (90, 12), "6m": (183, 6), "12m": (365, 12), "all": (3650, 12)}     # -> (timeline days, trend months)


def _w(id_: str, title: str, kind: str, size: tuple[int, int], lo: tuple[int, int], hi: tuple[int, int], min_role: str = "viewer") -> dict:
    roles = [r for r, k in RANK.items() if k >= RANK[min_role]]
    return {"id": id_, "title_fa": title, "kind": kind, "default_size": {"w": size[0], "h": size[1]},
            "min_size": {"w": lo[0], "h": lo[1]}, "max_size": {"w": hi[0], "h": hi[1]}, "roles": roles}


WIDGETS: list[dict] = [
    _w("kpi_runs_active", "دوره‌های فعال", "kpi", (3, 2), (2, 2), (6, 3)),
    _w("kpi_enrollments", "ثبت‌نام‌ها", "kpi", (3, 2), (2, 2), (6, 3)),
    _w("kpi_motivation_rate", "نرخ موتیویشن", "kpi", (3, 2), (2, 2), (6, 3)),
    _w("kpi_budget", "بودجه (ریال)", "kpi", (3, 2), (2, 2), (6, 3), "hr"),
    _w("funnel_run_stages", "قیف مراحل دوره‌ها", "chart", (4, 4), (3, 3), (12, 8)),
    _w("runs_timeline_upcoming", "دوره‌های پیش‌رو", "list", (8, 4), (4, 3), (12, 8)),
    _w("motivation_progress_by_run", "پیشرفت موتیویشن هر دوره", "chart", (6, 4), (4, 3), (12, 8)),
    _w("enrollments_by_division", "ثبت‌نام به تفکیک واحد", "chart", (6, 4), (4, 3), (12, 8)),
    _w("trend_monthly", "روند ماهانه", "chart", (8, 4), (4, 3), (12, 8)),
    _w("invoices_status", "وضعیت فاکتورها", "chart", (4, 4), (3, 3), (12, 8), "hr"),
    _w("level3_due", "ارزیابی سطح ۳ سررسید", "list", (6, 4), (4, 3), (12, 8)),
    _w("alerts_over3", "هشدار موتیویشن بیش از حد", "list", (6, 4), (4, 3), (12, 8)),
    _w("sync_health", "سلامت همگام‌سازی", "status", (12, 3), (4, 2), (12, 6), "hr"),
]
BY_ID = {w["id"]: w for w in WIDGETS}

DEFAULT_POSITIONS: list[tuple[str, int, int, int, int]] = [
    ("kpi_runs_active", 0, 0, 3, 2), ("kpi_enrollments", 3, 0, 3, 2), ("kpi_motivation_rate", 6, 0, 3, 2), ("kpi_budget", 9, 0, 3, 2),
    ("funnel_run_stages", 0, 2, 4, 4), ("runs_timeline_upcoming", 4, 2, 8, 4),
    ("motivation_progress_by_run", 0, 6, 6, 4), ("enrollments_by_division", 6, 6, 6, 4),
    ("trend_monthly", 0, 10, 8, 4), ("invoices_status", 8, 10, 4, 4),
    ("level3_due", 0, 14, 6, 4), ("alerts_over3", 6, 14, 6, 4), ("sync_health", 0, 18, 12, 3),
]


def allowed(widget_id: str, role: str) -> bool:
    return RANK.get(role, 0) >= RANK[BY_ID[widget_id]["roles"][0]]


def catalog_for(role: str) -> list[dict]:
    return [w for w in WIDGETS if role in w["roles"]]


def default_layout(role: str) -> list[dict]:
    return [{"id": i, "x": x, "y": y, "w": w, "h": h, "config": {}} for i, x, y, w, h in DEFAULT_POSITIONS if allowed(i, role)]


def validate_layout(widgets: list[dict], role: str) -> list[dict]:
    """Unknown ids, ids the role may not use, duplicates, sizes outside the widget's min/max and cells outside the 12-column grid are 422."""
    seen: set[str] = set()
    out: list[dict] = []
    errs: dict[str, str] = {}
    for n, w in enumerate(widgets):
        wid = w["id"]
        key = f"widgets.{n}"
        if wid not in BY_ID:
            errs[key] = f"ویجت «{wid}» ناشناخته است"
            continue
        if not allowed(wid, role):
            errs[key] = f"ویجت «{wid}» برای نقش شما مجاز نیست"
            continue
        if wid in seen:
            errs[key] = f"ویجت «{wid}» تکراری است"
            continue
        seen.add(wid)
        spec = BY_ID[wid]
        if not (spec["min_size"]["w"] <= w["w"] <= spec["max_size"]["w"] and spec["min_size"]["h"] <= w["h"] <= spec["max_size"]["h"]):
            errs[key] = (f"اندازهٔ «{wid}» باید بین {spec['min_size']['w']}×{spec['min_size']['h']} و "
                         f"{spec['max_size']['w']}×{spec['max_size']['h']} باشد")
            continue
        if w["x"] + w["w"] > GRID_COLS:
            errs[key] = f"ویجت «{wid}» از شبکهٔ {GRID_COLS} ستونی بیرون می‌زند"
            continue
        out.append({"id": wid, "x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"], "config": w.get("config") or {}})
    if errs:
        raise ApiError("validation", "چیدمان داشبورد نامعتبر است", errs)
    return out


def parse_range(r: str) -> str:
    if r not in RANGES:
        raise validation("بازهٔ زمانی نامعتبر است", range=f"مقادیر مجاز: {', '.join(RANGES)}")
    return r


def to_rials(x: Any) -> int:
    return int(Decimal(str(x or 0)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class Ctx:
    """Per-request cache so widgets that share a query (budget + invoices) run it once."""

    def __init__(self, db: Session, today: date, rng: str):
        self.db, self.today, self.rng = db, today, rng
        self.days, self.months = RANGES[rng]
        self.conf = rt.get_all(db)
        self._money: list | None = None

    def money_rows(self) -> list[dict]:
        """One row per non-cancelled run with an amount: amount, yes-count, payment/invoice markers."""
        if self._money is None:
            yes = (select(Enrollment.run_id.label("rid"), func.sum(case((Enrollment.motivation == "Yes", 1), else_=0)).label("yes"))
                   .where(Enrollment.run_id.is_not(None)).group_by(Enrollment.run_id).subquery())
            q = (select(CourseRun.id, CourseRun.amount, CourseRun.payment_process, CourseRun.pr_process_start_date,
                        CourseRun.invoice_receive_date, func.coalesce(yes.c.yes, 0))
                 .outerjoin(yes, yes.c.rid == CourseRun.id)
                 .where(CourseRun.status != "cancelled", CourseRun.amount.is_not(None)).order_by(CourseRun.id))
            self._money = [{"id": i, "amount": to_rials(a), "yes": int(y or 0), "paid": bool(pp or prd), "invoice": inv is not None}
                           for i, a, pp, prd, inv, y in self.db.execute(q)]
        return self._money


# ---- widgets -----------------------------------------------------------------------------------------------------------
def kpi_runs_active(c: Ctx) -> dict:
    by = {s: n for s, n in c.db.execute(select(CourseRun.status, func.count()).group_by(CourseRun.status))}
    soon = c.db.scalar(select(func.count()).select_from(CourseRun).where(CourseRun.status != "cancelled", CourseRun.start_date >= c.today,
                                                                       CourseRun.start_date <= c.today + timedelta(days=30))) or 0
    return {"value": sum(by.get(s, 0) for s in ACTIVE), "total_runs": sum(by.values()), "starting_30d": soon,
            "by_status": {s: by.get(s, 0) for s, _ in STAGES} | {"cancelled": by.get("cancelled", 0)}}


def kpi_enrollments(c: Ctx) -> dict:
    total, assigned = c.db.execute(select(func.count(), func.sum(case((Enrollment.run_id.is_not(None), 1), else_=0)))
                                   .where(Enrollment.status != "cancelled")).one()
    assigned = int(assigned or 0)
    return {"value": total, "assigned": assigned, "unassigned": total - assigned}


def kpi_motivation_rate(c: Ctx) -> dict:
    n, yes, no = c.db.execute(select(func.count(), func.sum(case((Enrollment.motivation == "Yes", 1), else_=0)),
                                     func.sum(case((Enrollment.motivation == "No", 1), else_=0)))
                              .where(Enrollment.run_id.is_not(None), Enrollment.status != "cancelled")).one()
    yes, no = int(yes or 0), int(no or 0)
    return {"value": round(yes * 100 / n, 1) if n else None, "participants": n, "yes": yes, "no": no, "pending": n - yes - no}


def kpi_budget(c: Ctx) -> dict:
    rows = c.money_rows()
    exp = [r for r in rows if r["yes"] > 0]
    started = [r for r in exp if r["paid"]]
    pending = [r for r in exp if not r["paid"]]
    cost = lambda rs: sum(r["amount"] * r["yes"] for r in rs)  # noqa: E731
    return {"currency": "IRR", "planned_total": sum(r["amount"] for r in rows), "planned_runs": len(rows),
            "expected_cost": cost(exp), "expected_runs": len(exp), "payment_started_total": cost(started),
            "payment_started_runs": len(started), "payment_pending_total": cost(pending), "payment_pending_runs": len(pending)}


def funnel_run_stages(c: Ctx) -> dict:
    by = {s: n for s, n in c.db.execute(select(CourseRun.status, func.count()).group_by(CourseRun.status))}
    return {"stages": [{"id": s, "label_fa": lbl, "count": by.get(s, 0)} for s, lbl in STAGES], "cancelled": by.get("cancelled", 0),
            "total": sum(by.values())}


def runs_timeline_upcoming(c: Ctx) -> dict:
    q = (select(CourseRun.id, CourseRun.start_date, CourseRun.end_date, CourseRun.status, CourseRun.type,
                Course.name.label("course_name"), INST.name.label("institute_name"))
         .join_from(CourseRun, Course).outerjoin(INST, INST.id == CourseRun.institute_id)
         .where(CourseRun.status.notin_(("cancelled", "completed")), CourseRun.start_date.is_not(None),
                CourseRun.start_date >= c.today - timedelta(days=3), CourseRun.start_date <= c.today + timedelta(days=c.days))
         .order_by(CourseRun.start_date, CourseRun.id).limit(12))
    rows = c.db.execute(q).all()
    counts = dash.run_counts(c.db, [r[0] for r in rows])
    return {"items": [{"run_id": i, "course_name": cn, "institute": inst or "", "type": t, "start_date": sd.isoformat(),
                       "end_date": ed.isoformat() if ed else None, "status": st, "days_to_course": (sd - c.today).days,
                       "participants": counts[i]["participants"], "motivations_yes": counts[i]["motivations_yes"]}
                      for i, sd, ed, st, t, cn, inst in rows], "horizon_days": c.days}


def motivation_progress_by_run(c: Ctx) -> dict:
    q = (select(CourseRun.id, CourseRun.start_date, Course.name.label("course_name")).join_from(CourseRun, Course)
         .where(CourseRun.status.notin_(("cancelled", "completed")), CourseRun.start_date.is_not(None),
                CourseRun.start_date >= c.today - timedelta(days=30))
         .order_by(CourseRun.start_date, CourseRun.id).limit(10))
    rows = c.db.execute(q).all()
    ids = [r[0] for r in rows]
    agg = {rid: (n, int(y or 0), int(no or 0)) for rid, n, y, no in c.db.execute(
        select(Enrollment.run_id, func.count(), func.sum(case((Enrollment.motivation == "Yes", 1), else_=0)),
               func.sum(case((Enrollment.motivation == "No", 1), else_=0))).where(Enrollment.run_id.in_(ids or [0]))
        .group_by(Enrollment.run_id))}
    items = []
    for rid, sd, cn in rows:
        n, yes, no = agg.get(rid, (0, 0, 0))
        items.append({"run_id": rid, "course_name": cn, "start_date": sd.isoformat(), "participants": n, "yes": yes, "no": no,
                      "pending": n - yes - no, "percent_yes": round(yes * 100 / n, 1) if n else None})
    return {"items": items}


def enrollments_by_division(c: Ctx) -> dict:
    rows = c.db.execute(select(Employee.division, func.count()).join(Enrollment, Enrollment.employee_id == Employee.id)
                        .where(Enrollment.status != "cancelled").group_by(Employee.division)
                        .order_by(func.count().desc(), Employee.division)).all()
    items = [{"division": d or "نامشخص", "count": n} for d, n in rows[:12]]
    rest = sum(n for _, n in rows[12:])
    if rest:
        items.append({"division": "سایر", "count": rest})
    return {"items": items, "total": sum(n for _, n in rows)}


def _jalali_months(c: Ctx, n: int) -> list[tuple[str, date, date]]:
    """The last ``n`` Jalali months (oldest first) as (label, first day, first day of the next month)."""
    cal = gateway.get_factory().build_calendar()
    y, m, _ = cal.to_jalali(c.today)
    seq = []
    for k in range(n - 1, -1, -1):
        mm = m - k
        yy = y
        while mm < 1:
            mm += 12
            yy -= 1
        ny, nm = (yy, mm + 1) if mm < 12 else (yy + 1, 1)
        seq.append((f"{MONTHS_FA[mm - 1]} {cal.to_persian_digits(str(yy))}", cal.to_gregorian(yy, mm, 1), cal.to_gregorian(ny, nm, 1)))
    return seq


def trend_monthly(c: Ctx) -> dict:
    months = _jalali_months(c, c.months)
    lo, hi = months[0][1], months[-1][2]
    yes = (select(Enrollment.run_id.label("rid"), func.count().label("n"), func.sum(case((Enrollment.motivation == "Yes", 1), else_=0)).label("y"))
           .where(Enrollment.run_id.is_not(None), Enrollment.status != "cancelled").group_by(Enrollment.run_id).subquery())
    rows = c.db.execute(select(CourseRun.start_date, CourseRun.amount, func.coalesce(yes.c.n, 0), func.coalesce(yes.c.y, 0))
                        .outerjoin(yes, yes.c.rid == CourseRun.id)
                        .where(CourseRun.status != "cancelled", CourseRun.start_date >= lo, CourseRun.start_date < hi)).all()
    out = []
    for label, start, end in months:
        sel = [r for r in rows if start <= r[0] < end]
        out.append({"label": label, "start": start.isoformat(), "runs": len(sel), "participants": sum(int(r[2]) for r in sel),
                    "motivations_yes": sum(int(r[3]) for r in sel), "expected_cost": sum(to_rials(r[1]) * int(r[3]) for r in sel)})
    return {"months": out}


def invoices_status(c: Ctx) -> dict:
    rows = [r for r in c.money_rows() if r["yes"] > 0]
    groups = {"no_invoice": [], "invoice_received": [], "payment_started": []}
    for r in rows:
        groups["payment_started" if r["paid"] else ("invoice_received" if r["invoice"] else "no_invoice")].append(r)
    labels = {"no_invoice": "بدون فاکتور", "invoice_received": "فاکتور دریافت شده", "payment_started": "پرداخت آغاز شده"}
    return {"currency": "IRR", "items": [{"id": k, "label_fa": labels[k], "runs": len(v), "amount": sum(r["amount"] * r["yes"] for r in v)}
                                         for k, v in groups.items()]}


def level3_due(c: Ctx) -> dict:
    items = dash.level3_list(c.db, c.today, c.conf, 20)
    return {"items": items, "count": len(items), "after_days": int(c.conf["level3_after_days"])}


def alerts_over3(c: Ctx) -> dict:
    items = dash.over3_list(c.db, c.conf, 20)
    return {"items": items, "count": len(items), "threshold": int(c.conf["over3_threshold"])}


def sync_health(c: Ctx) -> dict:
    latest = select(func.max(SyncRun.id)).group_by(SyncRun.source).scalar_subquery()
    runs = c.db.scalars(select(SyncRun).where(SyncRun.id.in_(latest)).order_by(SyncRun.source)).all()
    now = utcnow()
    stale = timedelta(minutes=10)
    items = []
    for r in runs:
        ref = r.finished_at or r.heartbeat_at or r.started_at
        items.append({"source": r.source, "status": r.status, "started_at": r.started_at.isoformat(),
                      "finished_at": r.finished_at and r.finished_at.isoformat(),
                      "age_minutes": int((now - ref).total_seconds() // 60), "processed": r.processed or 0, "message": r.message or "",
                      "stale": r.status == "running" and (now - (r.heartbeat_at or r.started_at)) > stale})
    conns = {k.kind: {"configured": True, "enabled": k.enabled, "last_test_ok": k.last_test_ok}
             for k in c.db.scalars(select(ConnectorConfig).order_by(ConnectorConfig.kind))}
    return {"sources": items, "running": sum(1 for i in items if i["status"] == "running"), "connectors": conns,
            "automation": rt.get_raw(c.db, "automation.last_run"),
            "ok": all(i["status"] in ("ok", "partial", "running") and not i["stale"] for i in items)}


FUNCS = {f.__name__: f for f in (kpi_runs_active, kpi_enrollments, kpi_motivation_rate, kpi_budget, funnel_run_stages, runs_timeline_upcoming,
                                 motivation_progress_by_run, enrollments_by_division, trend_monthly, invoices_status, level3_due,
                                 alerts_over3, sync_health)}


def data(db: Session, role: str, ids: list[str], rng: str, today: date | None = None) -> dict:
    unknown = [i for i in ids if i not in BY_ID]
    if unknown:
        raise validation("ویجت ناشناخته", widgets=f"ناشناخته: {', '.join(unknown)}")
    bad = [i for i in ids if not allowed(i, role)]
    if bad:
        raise forbidden(f"دسترسی به ویجت‌های {', '.join(bad)} برای نقش شما مجاز نیست")
    c = Ctx(db, today or date.today(), rng)
    return {"range": rng, "generated_at": datetime.utcnow().isoformat(timespec="seconds"), "widgets": {i: FUNCS[i](c) for i in dict.fromkeys(ids)}}
