"""Per-TICKET over-3-motivations (legacy IDP!R) end to end: import -> counts -> dashboard -> scheduler facts."""
import io
from datetime import date, timedelta

from app.api.services import automation as auto
from app.api.services import rules
from app.contracts import LegacyData, RecordRow, RunRecord
from app.models import Enrollment, EnrollmentOffer
from tests.core import fakes
from tests.core.conftest import fake_xlsx_bytes
from tests.core.test_integrations_wiring import idp

D = date(2030, 1, 5)


def legacy_with_three_offers():
    runs = [RunRecord("Course A", "", "in_person", f"Inst {i}", 8, D + timedelta(days=30 * i), D + timedelta(days=30 * i + 1), "Sat", "09:00",
                      1, None, None, 100, f"MTC-{i}") for i in range(4)]
    recs = [RecordRow("E00001", "LMS-1", "Course A", f"Inst {i}", D + timedelta(days=30 * i), m, "", "", "")
            for i, m in enumerate(["No", "", "No", "Yes"])]
    recs.append(RecordRow("E00002", "LMS-2", "Course A", "Inst 0", D, "No", "", "", ""))
    return LegacyData(employees=[fakes.employee(1), fakes.employee(2)], idp=[idp("LMS-1", "E00001", "Course A"), idp("LMS-2", "E00002", "Course A")],
                      runs=runs, records=recs)


def test_legacy_records_become_offers_and_count_per_ticket(hr, viewer, factory, sf):
    factory.excel.legacy = legacy_with_three_offers()
    files = {"file": ("x.xlsx", io.BytesIO(fake_xlsx_bytes()), "application/octet-stream")}
    r1 = hr.post("/import/legacy-workbook", files=files).json()
    r2 = hr.post("/import/legacy-workbook", files={"file": ("x.xlsx", io.BytesIO(fake_xlsx_bytes()), "application/octet-stream")}).json()
    assert (r2["created"], r2["updated"]) == (0, 0), (r1, r2)             # idempotent
    with sf() as s:
        assert s.query(EnrollmentOffer).count() == 5
        e1 = s.query(Enrollment).filter_by(ticket="LMS-1").one()
        counts = rules.non_yes_counts(s)
        assert counts[e1.id] == 3 and counts[s.query(Enrollment).filter_by(ticket="LMS-2").one().id] == 1
        assert e1.run.run_key.startswith("course a|inst 3|") and e1.motivation == "Yes"     # latest run is current
    o3 = viewer.get("/dashboard").json()["over3_motivations"]
    assert [(x["ticket"], x["non_yes_count"]) for x in o3] == [("LMS-1", 3)]


def test_scheduler_facts_feed_real_rules_per_ticket(hr, factory, sf, monkeypatch):
    from app.api.services import gateway
    from app.automation import rules as real
    monkeypatch.setattr(gateway, "compute_due", real.compute_due)
    factory.excel.legacy = legacy_with_three_offers()
    hr.post("/import/legacy-workbook", files={"file": ("x.xlsx", io.BytesIO(fake_xlsx_bytes()), "application/octet-stream")})
    with sf() as s:
        facts = auto.build_facts(s)
        t1 = [f for f in facts if f.ticket == "LMS-1"]
        assert len(t1) == 4 and sum(1 for f in t1 if f.motivation != "Yes") == 3    # 1 primary + 3 history facts
        items = auto.due(s, date.today())
    over = [i for i in items if i.kind == "over3_motivations"]
    assert len(over) == 1 and "LMS-1" in over[0].detail
    assert len({(i.kind, i.enrollment_id, i.run_id) for i in items}) == len(items)   # deduped


def test_unoffered_tickets_do_not_count_and_threshold_is_at_least(sf, seed):
    from tests.core.conftest import add_offers
    eid = seed["en_ids"][0]
    with sf() as s:
        assert rules.non_yes_counts(s).get(eid, 0) == 0
        assert not any(f.motivation != "Yes" and f.ticket == "LMS-100" for f in auto.build_facts(s))
    add_offers(sf, eid, ["No", "No"])
    with sf() as s:
        from app.automation import rules as real
        gateway_due = real.compute_due(auto.build_facts(s), date.today(), over3_threshold=3)
        assert not [i for i in gateway_due if i.kind == "over3_motivations"]
    add_offers(sf, eid, ["No"], tag="y")
    with sf() as s:
        from app.automation import rules as real
        assert [i for i in real.compute_due(auto.build_facts(s), date.today(), over3_threshold=3) if i.kind == "over3_motivations"]
