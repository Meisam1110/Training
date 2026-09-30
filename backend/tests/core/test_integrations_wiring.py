import io
import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.api.services import automation as auto_svc
from app.api.services import gateway
from app.contracts import IdpRow, LegacyData, RecordRow, RunRecord
from app.models import AuditLog, ConnectorConfig, Employee, Enrollment, Lease, SyncRun
from tests.core import fakes
from tests.core.conftest import fake_xlsx_bytes


# ---- connectors ----------------------------------------------------------------------------------
def test_connector_list_default_and_secrets_write_only(admin, hr, viewer, sf):
    j = hr.get("/connectors").json()["items"]
    assert [c["kind"] for c in j] == ["excel", "ifs", "smtp", "graph"] and not any(c["configured"] for c in j)
    r = admin.put("/connectors/ifs", json={"enabled": True, "config": {
        "base_url": "https://ifs.test", "auth_mode": "oauth2_client_credentials", "client_id": "cid",
        "client_secret": "TOP-SECRET-VALUE", "password": "PW-VALUE-123", "field_map": {"emp_no": "EmpId"}}})
    assert r.status_code == 200
    for who in (admin, hr):
        txt = who.get("/connectors").text
        assert "TOP-SECRET-VALUE" not in txt and "PW-VALUE-123" not in txt
    ifs = admin.get("/connectors").json()["items"][1]
    assert ifs["secrets_set"] == ["client_secret", "password"] and ifs["config"]["client_id"] == "cid"
    assert "client_secret" not in ifs["config"] and "password" not in ifs["config"]
    assert not any(len(v) > 0 and "*" in v for v in ifs["config"].values() if isinstance(v, str))          # no masks either
    assert "TOP-SECRET" not in r.text
    # omitted secret keeps value, empty string keeps, null clears
    admin.put("/connectors/ifs", json={"config": {"client_id": "cid2", "password": ""}})
    with sf() as s:
        c = s.get(ConnectorConfig, "ifs")
        assert c.secrets == {"client_secret": "TOP-SECRET-VALUE", "password": "PW-VALUE-123"} and c.public["client_id"] == "cid2"
    admin.put("/connectors/ifs", json={"config": {"password": None}})
    assert admin.get("/connectors").json()["items"][1]["secrets_set"] == ["client_secret"]
    with sf() as s:
        a = s.scalars(select(AuditLog).where(AuditLog.action == "connector.update")).all()
        assert "TOP-SECRET" not in str([x.detail for x in a])


@pytest.mark.parametrize("kind,cfg", [
    ("smtp", {"bogus": 1}), ("nope", {}), ("ifs", {"base_url": "ftp://x"}), ("ifs", {"field_map": "str"}),
    ("smtp", {"host": {"a": 1}}), ("smtp", {"host": "x" * 3000}),
])
def test_connector_put_validation(admin, kind, cfg):
    r = admin.put(f"/connectors/{kind}", json={"config": cfg})
    assert r.status_code in (404, 422)


def test_connector_test_endpoint(admin, factory):
    assert admin.post("/connectors/smtp:test").status_code == 409
    admin.put("/connectors/smtp", json={"config": {"host": "h", "password": "pw-1234567"}})
    r = admin.post("/connectors/smtp:test").json()
    assert r["ok"] is True and "hunter2" not in r["message"]
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.ok = False
    assert admin.post("/connectors/ifs:test").json() == {"ok": False, "message": "refused"}
    assert admin.get("/connectors").json()["items"][1]["last_test_ok"] is False
    factory.source.boom = True
    factory.source.test_connection = lambda: (_ for _ in ()).throw(RuntimeError("bad 09121234567"))
    assert "09121234567" not in admin.post("/connectors/ifs:test").json()["message"]
    assert admin.post("/connectors/nope:test").status_code == 404


def test_factory_missing_yields_upstream_not_crash(admin, monkeypatch):
    import sys
    monkeypatch.undo()   # drop the fake factory: use the real lazy import
    monkeypatch.setitem(sys.modules, "app.integrations.factory", None)     # simulate "module not there yet"
    monkeypatch.delattr("app.integrations.factory", raising=False)
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    r = admin.post("/connectors/smtp:test")
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream"


# ---- sync ----------------------------------------------------------------------------------------
def setup_ifs(admin, factory, n=5):
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test", "client_secret": "sec-123456"}})
    factory.source.records = [fakes.employee(i) for i in range(1, n + 1)]


def test_ifs_sync_is_idempotent_and_reports(hr, admin, factory, sf):
    setup_ifs(admin, factory)
    r1 = hr.post("/sync/ifs:run").json()
    assert (r1["created"], r1["updated"], r1["unchanged"], r1["status"]) == (5, 0, 0, "ok")
    r2 = hr.post("/sync/ifs:run").json()
    assert (r2["created"], r2["updated"], r2["unchanged"]) == (0, 0, 5)
    factory.source.records[0] = fakes.employee(1, division="New Div", mobile="09990000000")
    r3 = hr.post("/sync/ifs:run").json()
    assert (r3["created"], r3["updated"], r3["unchanged"]) == (0, 1, 4)
    with sf() as s:
        assert s.query(Employee).count() == 5
        e = s.query(Employee).filter_by(emp_no="E00001").one()
        assert e.division == "New Div" and e.mobile == "09990000000"
    assert factory.source.since_seen[0] is None and factory.source.since_seen[1] is not None      # delta after first run
    hr.post("/sync/ifs:run", json={"full": True})
    assert factory.source.since_seen[-1] is None
    assert hr.get("/sync/runs?source=ifs&sort=-id").json()["total"] == 4
    assert hr.get("/dashboard").json()["last_sync"]["ifs"]["status"] == "ok"
    assert factory.built[0][2]["client_secret"] == "sec-123456"          # decrypted config reaches the factory


def test_sync_blank_incoming_does_not_erase_and_bad_rows_skipped_without_pii(hr, admin, factory):
    setup_ifs(admin, factory, 2)
    hr.post("/sync/ifs:run")
    factory.source.records = [fakes.employee(1, mobile="", national_code="", division=""), fakes.employee(2, emp_no=""),
                              fakes.employee(3, emp_no="E" + "9" * 40)]
    r = hr.post("/sync/ifs:run").json()
    assert r["status"] == "partial" and r["skipped"] == 2 and r["unchanged"] == 1
    assert {(e["sheet"], e["row"], e["column"], e["code"]) for e in r["errors"]} == {
        ("employees", 2, "emp_no", "invalid_emp_no"), ("employees", 3, "emp_no", "invalid_emp_no")}
    assert all(set(e) == {"sheet", "row", "column", "code", "reason"} and "Test" not in str(e) and "@" not in str(e) for e in r["errors"])
    assert hr.get("/employees/E00001?reveal=1").json()["mobile"] == "09900000001"


def test_sync_failure_rolls_back_and_hides_pii(hr, admin, factory, sf):
    setup_ifs(admin, factory)
    factory.source.boom = True
    r = hr.post("/sync/ifs:run")
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream"
    runs = hr.get("/sync/runs").json()["items"]
    assert runs[0]["status"] == "error" and runs[0]["finished_at"]
    assert "0912345678" not in str(runs) and "abc" not in str(runs)
    with sf() as s:
        assert s.query(Employee).count() == 0
        assert s.get(Lease, "sync:ifs").expires_at <= __import__("app.models", fromlist=["utcnow"]).utcnow()   # lease released


def test_sync_requires_configured_connector_and_known_source(hr, factory, sf):
    assert hr.post("/sync/ifs:run").status_code == 409
    assert hr.post("/sync/nope:run").status_code == 404
    from datetime import datetime, timedelta
    with sf() as s:
        s.add(ConnectorConfig(kind="ifs", public={}, secrets={}))
        s.add(Lease(name="sync:ifs", holder="other", expires_at=datetime.utcnow() + timedelta(minutes=5)))
        s.commit()
    assert hr.post("/sync/ifs:run").status_code == 409                  # already running elsewhere


def test_excel_sync_with_idp(hr, admin, factory, sf):
    admin.put("/connectors/excel", json={"config": {"path": "/x/ifs.xlsx", "idp_path": "/x/idp.xlsx"}})
    factory.source.records = [fakes.employee(1)]
    factory.excel.idp = [idp("LMS-1", "E00001", "Course A"), idp("LMS-2", "E00099", "Course B", name="Zed Ghost [ MTNIrancell - CR ]")]
    r = hr.post("/sync/excel:run").json()
    assert r["created"] == 4          # 1 employee + 1 stub employee + 2 enrollments
    with sf() as s:
        stub = s.query(Employee).filter_by(emp_no="E00099").one()
        assert (stub.first_name_en, stub.last_name_en, stub.status) == ("Zed", "Ghost", "Unknown")


def idp(ticket, emp, summary, name="Test1 Person1", **kw):
    d = dict(emp_no=emp, reporter_name=name, job_level="L1", department="Div A", summary=summary, delivery_method="Online",
             current_status="Approved", idp_type="Yearly", course_category="Soft Skill", attendance_status="-",
             start_date=date(2030, 1, 5), end_date=date(2030, 1, 6), ticket=ticket, section_b="-")
    d.update(kw)
    return IdpRow(**d)


# ---- import / export -----------------------------------------------------------------------------
def xlsx_file(name="x.xlsx", content=None):
    content = fake_xlsx_bytes() if content is None else content
    return {"file": (name, io.BytesIO(content), "application/octet-stream")}


def test_import_idp_idempotent(hr, factory, sf):
    factory.excel.idp = [idp("LMS-10", "E00001", "Course A"), idp("LMS-11", "E00002", "Course B"), idp("", "E1", "x"), idp("LMS-12", "E1", "")]
    r = hr.post("/import/idp", files=xlsx_file()).json()
    assert (r["created"], r["skipped"], r["source"]) == (4, 2, "idp")     # 2 stub employees + 2 enrollments
    r = hr.post("/import/idp", files=xlsx_file()).json()
    assert (r["created"], r["updated"], r["unchanged"]) == (0, 0, 2)
    factory.excel.idp[0] = idp("LMS-10", "E00001", "Course A", attendance_status="Attended", section_b="MTC-5")
    assert hr.post("/import/idp", files=xlsx_file()).json()["updated"] == 1
    with sf() as s:
        en = s.query(Enrollment).filter_by(ticket="LMS-10").one()
        assert en.attendance_status == "Attended" and en.section_b == "MTC-5"
        assert s.query(Enrollment).filter_by(ticket="LMS-11").one().section_b == ""     # "-" means none


def test_import_preserves_manual_fields(hr, factory, sf):
    factory.excel.idp = [idp("LMS-10", "E00001", "Course A")]
    hr.post("/import/idp", files=xlsx_file())
    eid = hr.get("/enrollments?q=LMS-10").json()["items"][0]["id"]
    hr.patch(f"/enrollments/{eid}", json={"motivation": "Yes", "comment": "keep me"})
    factory.excel.idp = [idp("LMS-10", "E00001", "Course A", current_status="Evaluation Level 3")]
    hr.post("/import/idp", files=xlsx_file())
    j = hr.get("/enrollments?q=LMS-10").json()["items"][0]
    assert j["motivation"] == "Yes" and j["comment"] == "keep me" and j["current_status"] == "Evaluation Level 3"


@pytest.mark.parametrize("name,content,code", [("a.csv", b"PK..", 422), ("a.xlsx", b"", 422), ("a.xlsx", b"not a zip", 422)])
def test_import_file_validation(hr, name, content, code):
    assert hr.post("/import/idp", files=xlsx_file(name, content)).status_code == code
    assert hr.post("/import/idp").status_code == 422


def test_import_size_limit(hr, settings, app):
    from dataclasses import replace
    app.state.settings = replace(settings, max_upload_bytes=100)
    r = hr.post("/import/idp", files=xlsx_file(content=b"PK" + b"x" * 500))
    assert r.status_code in (413, 422)


def test_import_legacy_workbook_and_export_round_trip(hr, admin, factory, sf):
    factory.excel.legacy = LegacyData(
        employees=[fakes.employee(1), fakes.employee(2)],
        idp=[idp("LMS-1", "E00001", "Course A")],
        runs=[RunRecord("Course A", "دوره آ", "in_person", "Inst X", 8, date(2030, 1, 5), date(2030, 1, 6), "Sat", "09:00", 2,
                        None, date(2030, 1, 1), 5000, "MTC-3")],
        records=[RecordRow("E00001", "LMS-1", "Course A", "Inst X", date(2030, 1, 5), "Yes", "Done", "Sent", "Started", "note"),
                 RecordRow("E00002", "LMS-2", "Course A", "Inst X", date(2030, 1, 5), "No", "", "", "", ""),
                 RecordRow("E00077", "LMS-3", "Course A", "Inst X", date(2030, 1, 5), "Yes", "", "", "", "")])
    r = hr.post("/import/legacy-workbook", files=xlsx_file()).json()
    assert r["created"] == 2 + 1 + 1 + 1 and r["skipped"] == 1 and r["source"] == "legacy"
    r2 = hr.post("/import/legacy-workbook", files=xlsx_file()).json()
    assert (r2["created"], r2["updated"]) == (0, 0)
    en = hr.get("/enrollments?q=LMS-1").json()["items"]
    assert en[0]["motivation"] == "Yes" and en[0]["run_id"] is not None and en[0]["payment"] == "Started"
    assert [i["ticket"] for i in hr.get("/enrollments?q=LMS-2").json()["items"]] == ["LMS-2"]
    run = hr.get("/runs").json()["items"][0]
    assert run["institute"] == "Inst X" and run["amount"] == 5000 and run["course_name_fa"] == "دوره آ"
    e = hr.get("/export/legacy.xlsx")
    assert e.status_code == 200 and e.content[:2] == b"PK" and "legacy.xlsx" in e.headers["content-disposition"]
    w = factory.excel.written
    assert len(w.employees) == 2 and w.employees[0].national_code == "" and w.employees[0].mobile == "" and w.runs[0].institute == "Inst X"
    assert hr.get("/export/legacy.xlsx?include_pii=1").status_code == 403           # bulk PII export is admin-only
    assert admin.get("/export/legacy.xlsx?include_pii=1").status_code == 200
    assert factory.excel.written.employees[0].national_code == "9990000001"
    assert {x.ticket for x in w.records} == {"LMS-1", "LMS-2"}
    with sf() as s:
        assert s.query(AuditLog).filter_by(action="export.legacy").count() == 2


# ---- automation ----------------------------------------------------------------------------------
def test_automation_due_run_and_settings(hr, admin, viewer, seed, sf):
    today = date.today()
    with sf() as s:
        en = s.query(Enrollment).filter_by(ticket="LMS-105").one()
        en.current_status, en.end_date = "Evaluation Level 3", today - timedelta(days=70)
        s.commit()
    hr.patch(f"/runs/{seed['run_id']}", json={"deadline": str(today + timedelta(days=1))})
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": seed["run_id"]})
    d = viewer.get("/automation/due").json()
    assert d["counts"]["level3_due"] == 1 and d["counts"]["deadline_reminder"] == 2
    assert all(i["run_id"] in (None, seed["run_id"]) for i in d["items"])
    r = hr.post("/automation/run").json()
    assert r["total"] == 3
    s = viewer.get("/automation/settings").json()
    assert s["level3_after_days"] == 60 and s["last_run"]["total"] == 3
    assert admin.put("/automation/settings", json={"level3_after_days": 90, "over3_threshold": 5}).json()["level3_after_days"] == 90
    assert viewer.get("/automation/due").json()["counts"].get("level3_due", 0) == 0          # 70d < 90d now
    for bad in ({"level3_after_days": 0}, {"reminder_days": -1}, {"over3_threshold": 0}, {"letter_number_prefix": "a b"}, {"x": 1}):
        assert admin.put("/automation/settings", json=bad).status_code == 422


def test_automation_upstream_missing(hr, monkeypatch):
    monkeypatch.setattr(gateway, "compute_due", lambda *a, **k: (_ for _ in ()).throw(gateway.upstream("x")))
    assert hr.get("/automation/due").status_code == 502


def test_compute_due_not_implemented_maps_to_upstream(monkeypatch):
    import sys

    import app.contracts as c
    from app.api.errors import ApiError
    monkeypatch.setitem(sys.modules, "app.automation", None)               # Dev-B module absent
    monkeypatch.setattr(c, "compute_due", lambda *a, **k: (_ for _ in ()).throw(NotImplementedError()))
    with pytest.raises(ApiError) as e:
        gateway.compute_due([], date.today())
    assert e.value.code == "upstream"


def test_scheduler_tick_is_safe_with_many_workers(sf, settings, seed, factory):
    results, lock = [], threading.Lock()

    def worker(i):
        ok = auto_svc.tick(sf, settings, holder=f"w{i}")
        with lock:
            results.append(ok)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count(True) == 1
    with sf() as s:
        assert s.query(SyncRun).filter_by(source="automation").count() == 1
    assert auto_svc.tick(sf, settings, "w9") is False                       # interval not elapsed
    with sf() as s:
        from app.api.services import settings_store as rt
        rt.set_many(s, {"enabled": False})
        rt.set_raw(s, "automation.last_run", {"at": "2000-01-01T00:00:00", "total": 0})
        s.commit()
    assert auto_svc.tick(sf, settings, "w9") is False                       # disabled at runtime
    with sf() as s:
        rt.set_many(s, {"enabled": True})
        s.commit()
    assert auto_svc.tick(sf, settings, "w9") is True                        # overdue -> runs again


def test_lease_semantics(sf):
    from app.api.services import leases
    with sf() as s:
        assert leases.acquire(s, "x", "a", 60) and not leases.acquire(s, "x", "b", 60) and leases.acquire(s, "x", "a", 60)
        leases.release(s, "x", "a")
        assert leases.acquire(s, "x", "b", 60)


def test_background_loop_runs_and_cancels(sf, settings, factory):
    import asyncio
    from dataclasses import replace
    s2 = replace(settings, automation_interval_s=60)

    async def go():
        t = asyncio.create_task(auto_svc.loop(sf, s2))
        await asyncio.sleep(1.0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(go())
    with sf() as s:
        assert s.query(SyncRun).filter_by(source="automation").count() == 1


def test_lifespan_starts_loop_only_when_enabled_and_not_test(settings, factory):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app
    st = replace(settings, env="development", automation_enabled=True, automation_interval_s=60,
                 bootstrap_admin_user="boot", bootstrap_admin_password="Zx9-long-bootstrap-pw")
    with TestClient(create_app(st)) as c:
        assert c.get("/ready").status_code == 200
        import time
        time.sleep(0.8)
    a = create_app(st)
    with a.state.session_factory() as s:
        assert s.query(SyncRun).filter_by(source="automation").count() == 1
        from app.models import User
        assert s.query(User).filter_by(username="boot").count() == 1
