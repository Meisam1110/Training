from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.automation import batch_by_manager, compute_due, invoice_total, split_invoice
from app.contracts import EnrollmentFact

TODAY = date(2026, 9, 30)


def fact(i=1, **kw):
    d = dict(enrollment_id=i, run_id=1, ticket=f"LMS-{i}", course_name="C", category="Soft Skill",
             current_status="Evaluation Level 3", end_date=TODAY - timedelta(days=60), run_start_date=None,
             registration_deadline=None, motivation="Yes", payment_started=True, level3_sent=False)
    d.update(kw)
    return EnrollmentFact(**d)


def kinds(facts, **kw):
    return [i.kind for i in compute_due(facts, TODAY, **kw)]


@pytest.mark.parametrize("days,due", [(59, False), (60, True), (61, True), (400, True)])
def test_level3_boundary(days, due):
    assert (kinds([fact(end_date=TODAY - timedelta(days=days))]) == ["level3_due"]) is due


def test_level3_custom_days_and_filters():
    assert kinds([fact(end_date=TODAY - timedelta(days=30))], level3_after_days=30) == ["level3_due"]
    assert kinds([fact(category="Development")]) == []
    assert kinds([fact(category=" soft-skill ")]) == ["level3_due"]
    assert kinds([fact(current_status="Approved motivation")]) == []
    assert kinds([fact(current_status="evaluation level 3")]) == ["level3_due"]
    assert kinds([fact(level3_sent=True)]) == []
    assert kinds([fact(end_date=None)]) == []
    assert kinds([fact(end_date=TODAY + timedelta(days=5))]) == []           # future end


def test_level3_leap_day_math():
    assert compute_due([fact(end_date=date(2024, 1, 1))], date(2024, 3, 1))[0].kind == "level3_due"   # 60 days
    assert compute_due([fact(end_date=date(2024, 1, 2))], date(2024, 3, 1)) == []                     # 59 days
    assert compute_due([fact(end_date=date(2023, 1, 1))], date(2023, 3, 2))[0].kind == "level3_due"   # 60, non-leap


@pytest.mark.parametrize("delta,due", [(-1, False), (0, True), (1, True), (2, True), (3, False)])
def test_deadline_reminder_boundaries(delta, due):
    f = fact(end_date=None, registration_deadline=TODAY + timedelta(days=delta), motivation="")
    assert (kinds([f]) == ["deadline_reminder"]) is due


def test_deadline_reminder_filters():
    d = TODAY + timedelta(days=1)
    assert kinds([fact(end_date=None, registration_deadline=d, motivation="Yes")]) == []
    assert kinds([fact(end_date=None, registration_deadline=d, motivation="No")]) == []
    assert kinds([fact(end_date=None, registration_deadline=None, motivation="")]) == []
    assert kinds([fact(end_date=None, registration_deadline=TODAY + timedelta(days=5), motivation="")],
                 reminder_days=5) == ["deadline_reminder"]


def test_over3_motivations_per_ticket_legacy_countifs():
    def group(ticket, n_non_yes, n_yes=0, start=1):
        return ([fact(start + i, ticket=ticket, end_date=None, motivation="No" if i % 2 else "")
                 for i in range(n_non_yes)]
                + [fact(start + 100 + j, ticket=ticket, end_date=None, motivation="Yes") for j in range(n_yes)])
    assert kinds(group("LMS-9", 2, 5)) == []                                   # 2 < 3
    r = compute_due(group("LMS-9", 3, 2), TODAY)                               # exactly 3 -> due (>= 3)
    assert [i.kind for i in r] == ["over3_motivations"] and r[0].enrollment_id == 1 and "3" in r[0].detail
    assert kinds(group("LMS-9", 5)) == ["over3_motivations"]                   # still one item per ticket
    assert kinds(group("LMS-9", 2), over3_threshold=2) == ["over3_motivations"]
    assert kinds(group("LMS-9", 3), over3_threshold=4) == []
    # counts are per ticket, not global: 2 + 2 across two tickets never fires
    assert kinds(group("LMS-1", 2) + group("LMS-2", 2, start=50)) == []
    both = compute_due(group("LMS-1", 3) + group("LMS-2", 3, start=50), TODAY)
    assert [i.detail.split(":")[0] for i in both] == ["LMS-1", "LMS-2"]
    assert kinds([fact(i, ticket="", end_date=None, motivation="No") for i in range(1, 9)]) == []   # no ticket


def test_payment_not_started_once_per_run():
    fs = [fact(1, run_id=7, end_date=None, run_start_date=TODAY - timedelta(days=1), payment_started=False),
          fact(2, run_id=7, end_date=None, run_start_date=TODAY - timedelta(days=1), payment_started=False),
          fact(3, run_id=8, end_date=None, run_start_date=TODAY, payment_started=False),
          fact(4, run_id=9, end_date=None, run_start_date=TODAY + timedelta(days=1), payment_started=False),
          fact(5, run_id=10, end_date=None, run_start_date=TODAY - timedelta(days=3), payment_started=True),
          fact(6, run_id=11, end_date=None, run_start_date=TODAY - timedelta(days=3), payment_started=False,
               motivation="No"),
          fact(7, run_id=12, end_date=None, run_start_date=None, payment_started=False)]
    r = compute_due(fs, TODAY)
    assert [(i.kind, i.run_id, i.enrollment_id) for i in r] == [("payment_not_started", 7, None),
                                                                ("payment_not_started", 8, None)]


def test_ordering_purity_and_empty():
    fs = [fact(1, run_id=2, run_start_date=TODAY - timedelta(days=100), payment_started=False),
          fact(2, run_id=1)]
    a = compute_due(fs, TODAY)
    assert a == compute_due(list(reversed(fs)), TODAY)
    assert [i.kind for i in a] == ["level3_due", "level3_due", "payment_not_started"]
    assert compute_due([], TODAY) == []
    assert fs[0].enrollment_id == 1                      # inputs untouched (frozen dataclass)


def test_batching():
    items = [(f"E{i}", "M1" if i < 12 else "M2") for i in range(15)]
    b = batch_by_manager(items, lambda x: x[1])
    assert [(k, len(v)) for k, v in b] == [("M1", 9), ("M1", 3), ("M2", 3)]
    assert all(len(v) <= 9 for _, v in b)
    assert [x for _, v in b for x in v] == sorted(items, key=lambda x: x[1])   # nothing lost/duplicated
    assert batch_by_manager([], lambda x: x) == []
    assert [len(v) for _, v in batch_by_manager(list(range(9)), lambda x: "m")] == [9]
    assert [len(v) for _, v in batch_by_manager(list(range(10)), lambda x: "m", 3)] == [3, 3, 3, 1]
    with pytest.raises(ValueError):
        batch_by_manager([1], lambda x: "")
    with pytest.raises(ValueError):
        batch_by_manager([1], lambda x: "m", 0)


@pytest.mark.parametrize("total,n", [("202500000", 5), ("100", 3), ("1", 3), ("0", 4), ("999999999999", 7),
                                     (10, 1), ("1,000", 3)])
def test_split_invoice_exact(total, n):
    parts = split_invoice(total, n)
    assert len(parts) == n and sum(parts) == Decimal(str(total).replace(",", ""))
    assert max(parts) - min(parts) <= 1 and parts == sorted(parts, reverse=True)


def test_split_invoice_decimals_and_errors():
    p = split_invoice("100.00", 3, places=2)
    assert p == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")] and sum(p) == Decimal("100.00")
    assert sum(split_invoice(0.3, 3, places=1)) == Decimal("0.3")     # float input, no drift
    assert split_invoice("202500000", 5) == [Decimal(40500000)] * 5
    with pytest.raises(ValueError):
        split_invoice("100.5", 3)
    with pytest.raises(ValueError):
        split_invoice(100, 0)
    with pytest.raises(ValueError):
        split_invoice(-1, 2)


def test_invoice_total():
    assert invoice_total("40500000", 5) == Decimal("202500000")
    assert invoice_total(Decimal("0.1"), 3) == Decimal("0.3")
    with pytest.raises(ValueError):
        invoice_total(1, -1)
