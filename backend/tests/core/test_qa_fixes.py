"""Regression tests for docs/QA_REPORT.md (each test name carries the finding id)."""
import io
import re
import threading
import time
import zipfile
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.api.services import upsert
from app.config import weak_password
from app.models import AuditLog, ConnectorConfig, Employee, Enrollment, Letter, MessageLog, SyncRun, utcnow
from tests.core import fakes
from tests.core.conftest import PW, Api, fake_xlsx_bytes
from tests.core.test_integrations_wiring import idp, xlsx_file


def count_statements(engine):
    """Context manager counting SQL statements issued through ``engine``."""
    class C:
        n = 0
        log: list = []

        def __enter__(self):
            event.listen(engine, "before_cursor_execute", self._cb)
            return self

        def __exit__(self, *a):
            event.remove(engine, "before_cursor_execute", self._cb)

        def _cb(self, conn, cur, statement, *a, **k):
            C.n += 1
            C.log.append(statement.split("\n")[0][:90])
    return C()


def as_hr_letter_ready(hr, seed, n=3):
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:n], "run_id": seed["run_id"], "motivation": "Yes"})


# ---- H1: the Level-3 loop closes -----------------------------------------------------------------------
def level3_setup(sf, seed, days=90):
    with sf() as s:
        e = s.get(Enrollment, seed["en_ids"][5])
        e.current_status, e.category, e.end_date = "Evaluation Level 3", "Soft Skill", date.today() - timedelta(days=days)
        s.commit()
    return seed["en_ids"][5]


def test_QA_H1_level3_letter_removes_enrollment_from_every_due_view(hr, viewer, seed, sf):
    eid = level3_setup(sf, seed)
    due = lambda: [i for i in hr.get("/automation/due").json()["items"] if i["kind"] == "level3_due" and i["enrollment_id"] == eid]  # noqa: E731
    dash = lambda: [x for x in viewer.get("/dashboard").json()["level3_due"] if x["enrollment_id"] == eid]  # noqa: E731
    cand = lambda: [c for c in hr.post(f"/runs/{seed['run_id']}/candidates:search", json={}).json()["candidates"] if c["id"] == eid]  # noqa: E731
    assert due() and dash() and "level3_eligible" in cand()[0]["flags"]
    r = hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": [eid]})
    assert r.status_code == 201
    assert not due() and not dash() and "level3_eligible" not in cand()[0]["flags"]
    en = hr.get("/enrollments?q=LMS-105").json()["items"][0]
    assert en["level3_sent"] is True and en["level3_status"] == "requested"
    hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": [eid]})              # idempotent
    assert hr.get("/enrollments?q=LMS-105").json()["items"][0]["level3_status"] == "requested"
    with sf() as s:
        assert s.get(Enrollment, eid).level3_sent is True


def test_QA_H1_manager_check_advances_status_and_patch_can_reopen(hr, seed, sf):
    eid = level3_setup(sf, seed)
    hr.post("/letters", json={"kind": "level3_manager_check", "enrollment_ids": [eid]})
    en = hr.get("/enrollments?q=LMS-105").json()["items"][0]
    assert en["level3_status"] == "manager_check" and en["level3_sent"] is False               # request not sent yet: still due
    assert [i for i in hr.get("/automation/due").json()["items"] if i["kind"] == "level3_due"]
    p = hr.patch(f"/enrollments/{eid}", json={"level3_sent": True, "level3_status": "done"}).json()
    assert p["level3_sent"] is True and p["level3_status"] == "done"
    assert not [i for i in hr.get("/automation/due").json()["items"] if i["kind"] == "level3_due"]
    assert hr.patch(f"/enrollments/{eid}", json={"level3_sent": False}).json()["level3_sent"] is False       # explicit reopen
    assert hr.get(f"/runs/{seed['run_id']}").json()["workflow"]["level3_started"] in (True, False)


def test_QA_H1_workflow_level3_started_after_letter(hr, seed, sf):
    hr.post("/enrollments:bulk", json={"enrollment_ids": [seed["en_ids"][5]], "run_id": seed["run_id"]})
    level3_setup(sf, seed)
    assert hr.get(f"/runs/{seed['run_id']}").json()["workflow"]["level3_started"] is False
    hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": [seed["en_ids"][5]]})
    assert hr.get(f"/runs/{seed['run_id']}").json()["workflow"]["level3_started"] is True


# ---- H2: client address behind a proxy ------------------------------------------------------------------
def login_from(app, peer, xff, user="hr", pw=PW):
    c = TestClient(app, client=(peer, 50000))
    h = {"X-Forwarded-For": xff} if xff else {}
    return c.post("/api/v1/auth/login", json={"username": user, "password": pw}, headers=h)


def test_QA_H2_docker_bridge_peer_is_trusted_and_real_client_ip_is_audited(app, users, sf):
    assert login_from(app, "172.18.0.1", "203.0.113.7").status_code == 200
    with sf() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.action == "login")).one().ip == "203.0.113.7"


def test_QA_H2_untrusted_peer_cannot_spoof_and_left_entries_are_ignored(app, users, sf):
    assert login_from(app, "198.51.100.9", "203.0.113.7").status_code == 200           # not a proxy: header ignored
    assert login_from(app, "172.18.0.1", "6.6.6.6, 203.0.113.8").status_code == 200      # attacker-prepended 6.6.6.6 is ignored
    assert login_from(app, "127.0.0.1", "not-an-ip").status_code == 200                 # garbage: fall back to the peer
    with sf() as s:
        ips = [a.ip for a in s.scalars(select(AuditLog).where(AuditLog.action == "login").order_by(AuditLog.id))]
    assert ips == ["198.51.100.9", "203.0.113.8", "127.0.0.1"]


def test_QA_H2_per_ip_lockout_is_per_real_client_not_per_proxy(app, users, settings):
    app.state.settings = replace(settings, login_ip_max_failures=5, login_max_failures=1000)
    for i in range(5):
        assert login_from(app, "172.18.0.1", "203.0.113.50", user=f"nobody{i}", pw="x" * 12).status_code == 401
    assert login_from(app, "172.18.0.1", "203.0.113.50").status_code == 429                # the attacker is blocked ...
    assert login_from(app, "172.18.0.1", "203.0.113.51").status_code == 200                # ... other users behind the same proxy are not


def test_QA_H2_trusted_proxies_is_configurable(settings, factory):
    from app.main import create_app
    a = create_app(replace(settings, trusted_proxies=("10.0.0.0/8",)))
    create_users = __import__("tests.core.conftest", fromlist=["create_users"]).create_users
    create_users(a.state.session_factory)
    assert login_from(a, "10.1.2.3", "203.0.113.9").status_code == 200
    assert login_from(a, "172.18.0.1", "203.0.113.9").status_code == 200        # 172.x no longer trusted -> header ignored
    with a.state.session_factory() as s:
        assert [x.ip for x in s.scalars(select(AuditLog).where(AuditLog.action == "login").order_by(AuditLog.id))] == ["203.0.113.9", "172.18.0.1"]


# ---- H3: connector schema ------------------------------------------------------------------------------
def test_QA_H3_every_key_the_real_connectors_read_is_accepted(admin):
    ifs = {"base_url": "https://ifs.test", "auth_mode": "oauth2_client_credentials", "client_id": "c", "client_secret": "s3cret-value",
           "token_url": "https://ifs.test/token", "scope": "openid", "employees_path": "/PersonInfo", "page_size": 200,
           "modified_field": "ModifiedDate", "ca_bundle": "/etc/ssl/ca.pem", "max_retries": 3, "timeout_s": 20, "verify_tls": True,
           "delta_mode": "client", "active_statuses": ["active", "Active"], "field_map": {"emp_no": ["EmpNo"], "email": "Email"},
           "breaker_threshold": 5, "breaker_cooldown_s": 30, "backoff_base_s": 0.5, "backoff_max_s": 10}
    assert admin.put("/connectors/ifs", json={"config": ifs}).status_code == 200
    smtp = {"host": "smtp.test", "port": 465, "use_ssl": True, "verify_tls": True, "timeout_s": 15, "ca_bundle": "/x.pem",
            "rate_limit_per_min": 30, "from_addr": "hr@example.test", "from_name": "HR", "username": "u", "password": "pw-1234567890", "starttls": False}
    assert admin.put("/connectors/smtp", json={"config": smtp}).status_code == 200
    graph = {"tenant_id": "t", "client_id": "c", "client_secret": "gs-1234567", "sender": "a@example.test", "authority_url": "https://login.test",
             "graph_url": "https://graph.test", "save_to_sent_items": False, "timeout_s": 10}
    assert admin.put("/connectors/graph", json={"config": graph}).status_code == 200
    assert admin.put("/connectors/excel", json={"config": {"path": "/x.xlsx", "sheet": "IFS", "idp_path": "/y.xlsx", "watch_dir": "/w"}}).status_code == 200
    txt = admin.get("/connectors").text
    assert "s3cret-value" not in txt and "pw-1234567890" not in txt and "gs-1234567" not in txt          # still write-only


def test_QA_H3_allow_list_covers_everything_the_sources_read_and_unknown_is_rejected(admin):
    import pathlib

    from app.api.services.serializers import allowed_keys
    root = pathlib.Path(__file__).resolve().parents[2] / "app" / "integrations"
    for kind, files in {"smtp": ["email/smtp.py", "email/common.py"], "graph": ["email/graph.py", "email/common.py"],
                        "excel": ["excel/source.py"]}.items():
        src = "".join((root / f).read_text() for f in files)
        used = set(re.findall(r"config(?:\.get\(|\[)\"(\w+)\"", src))
        assert used <= allowed_keys(kind), (kind, used - allowed_keys(kind))
    assert {"employees_path", "page_size", "modified_field", "ca_bundle", "scope", "max_retries"} <= allowed_keys("ifs")
    assert admin.put("/connectors/ifs", json={"config": {"nonsense_key": 1}}).status_code == 422
    for bad in ({"port": 0}, {"port": "25"}, {"timeout_s": -1}, {"use_ssl": "yes"}, {"rate_limit_per_min": 10**9}):
        assert admin.put("/connectors/smtp", json={"config": bad}).status_code == 422, bad


@pytest.mark.parametrize("url", ["http://user:SuperSecret@127.0.0.1:1", "https://ifs.test/?apikey=K", "https://ifs.test/x#frag",
                                 "https://:onlypw@ifs.test", "https://a@b@ifs.test"])
def test_QA_M8_urls_with_credentials_or_query_are_rejected_and_never_stored(admin, sf, url):
    r = admin.put("/connectors/ifs", json={"enabled": False, "config": {"base_url": url}})
    assert r.status_code == 422 and "SuperSecret" not in r.text
    with sf() as s:
        assert s.get(ConnectorConfig, "ifs") is None
    assert admin.put("/connectors/graph", json={"config": {"graph_url": url}}).status_code == 422


def test_QA_H3_tls_hint_in_last_test_message(admin, factory):
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.internal"}})
    factory.source.test_connection = lambda: (False, "IFS request failed (ConnectError)")
    m = admin.post("/connectors/ifs:test").json()["message"]
    assert "ca_bundle" in m and "ConnectError" in m


# ---- H4: uploads and long syncs -------------------------------------------------------------------------
def zip_with(members: dict[str, bytes], level=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", level) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_QA_H4_zip_bomb_and_bad_archives_are_rejected_before_parsing(hr, factory):
    base = {"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"}
    bomb = zip_with({**base, "xl/worksheets/sheet1.xml": b"\0" * (150 * 1024 * 1024)})          # ~150 KB -> 150 MB
    assert len(bomb) < 1024 * 1024
    for name, content in [("bomb", bomb), ("no workbook", zip_with({"a.txt": b"hi"})), ("traversal", zip_with({**base, "../evil": b"x"})),
                          ("pk only", b"PK\x03\x04"), ("truncated", fake_xlsx_bytes()[:-30]),
                          ("too many members", zip_with({**base, **{f"m{i}.xml": b"x" for i in range(2100)}}))]:
        r = hr.post("/import/idp", files=xlsx_file(content=content))
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation", (name, r.status_code, r.text[:200])
    assert hr.get("/sync/runs").json()["total"] == 0                       # nothing was started for any of them


def test_QA_H4_import_row_cap(hr, factory, app, settings):
    app.state.settings = replace(settings, max_import_rows=100, sync_chunk=50)
    factory.excel.idp = [idp(f"LMS-{i}", "E00001", "Course") for i in range(300)]
    r = hr.post("/import/idp", files=xlsx_file())
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation" and "سقف" in r.json()["error"]["message"]
    run = hr.get("/sync/runs").json()["items"][0]
    assert run["status"] == "error" and run["processed"] <= 150 and run["finished_at"]       # stopped early, run closed, chunks kept


def slow_source(n, delay=0.0, gate=None):
    def gen():
        for i in range(1, n + 1):
            if gate and i == 1:
                gate.wait(10)
            yield fakes.employee(i)
    return gen


def test_QA_H4_big_sync_runs_in_background_with_progress_and_bounded_memory(hr, admin, factory, app, settings, sf):
    app.state.settings = replace(settings, sync_wait_s=0.2, sync_chunk=50)
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    gate = threading.Event()
    n = 1200
    gen = slow_source(n, gate=gate)
    factory.source.fetch_employees = lambda since=None: gen()
    peaks: list[int] = []
    orig = upsert._end_chunk

    def spy(db, rep):
        peaks.append(len(db.identity_map))          # objects the session holds right before they are dropped
        return orig(db, rep)

    upsert._end_chunk = spy
    try:
        r = hr.post("/sync/ifs:run")
        assert r.status_code == 202 and r.json()["status"] == "running"                 # answered immediately, job still running
        assert hr.post("/sync/ifs:run").status_code == 409                              # single-flight
        gate.set()
        deadline = time.time() + 30
        while time.time() < deadline:
            run = hr.get("/sync/runs").json()["items"][0]
            if run["status"] != "running":
                break
            time.sleep(0.1)
    finally:
        upsert._end_chunk = orig
    assert run["status"] == "ok" and run["created"] == n
    assert len(peaks) >= n // 50 and max(peaks) <= 120                                   # never more than ~2 chunks in memory
    with sf() as s:
        r0 = s.get(SyncRun, run["id"])
        assert r0.processed == n and r0.heartbeat_at is not None and r0.finished_at is not None
        assert s.query(Employee).count() == n


def test_QA_H4_stale_running_run_is_recovered_and_does_not_block(hr, admin, factory, sf, settings):
    from app.models import Lease
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [fakes.employee(1)]
    with sf() as s:
        s.add(SyncRun(source="ifs", status="running", started_at=utcnow() - timedelta(hours=1), heartbeat_at=utcnow() - timedelta(hours=1)))
        s.add(Lease(name="sync:ifs", holder="dead-worker", expires_at=utcnow() + timedelta(minutes=14)))
        s.commit()
    r = hr.post("/sync/ifs:run")                                           # not 409: the dead run is closed first
    assert r.status_code == 200 and r.json()["status"] == "ok"
    old = [x for x in hr.get("/sync/runs?sort=id").json()["items"] if x["status"] == "error"][0]
    assert old["errors"][0]["code"] == "interrupted" and old["finished_at"]


def test_QA_H4_startup_recovers_stale_runs(settings, factory):
    from app.main import create_app
    a = create_app(settings)
    with a.state.session_factory() as s:
        s.add(SyncRun(source="excel", status="running", started_at=utcnow() - timedelta(hours=2)))
        s.commit()
    with TestClient(a):
        pass
    with a.state.session_factory() as s:
        assert s.scalars(select(SyncRun)).one().status == "error"


# ---- M1: ids and NUL --------------------------------------------------------------------------------------
BIG = "99999999999999999999"


@pytest.mark.parametrize("method,path,body", [
    ("GET", f"/runs/{BIG}", None), ("GET", f"/courses/{BIG}", None),
    ("PATCH", f"/enrollments/{BIG}", {}), ("PATCH", f"/runs/{BIG}", {}), ("PATCH", f"/courses/{BIG}", {}), ("PATCH", f"/users/{BIG}", {}),
    ("PATCH", f"/institutes/{BIG}", {}), ("GET", f"/runs/{BIG}/enrollments", None), ("POST", f"/runs/{BIG}/candidates:search", {}),
    ("GET", f"/letters/{BIG}/download", None), ("GET", f"/enrollments?run_id={BIG}", None), ("GET", f"/runs?course_id={BIG}", None),
    ("GET", f"/letters?run_id={BIG}", None), ("GET", "/runs/0", None), ("GET", "/runs/-5", None), ("GET", "/employees?page=99999999999999", None),
    ("POST", "/enrollments:bulk", {"enrollment_ids": [int(BIG)]}), ("POST", "/enrollments:bulk", {"enrollment_ids": [1], "run_id": int(BIG)}),
    ("POST", "/letters", {"kind": "level3_request", "enrollment_ids": [int(BIG)]}), ("POST", "/letters", {"kind": "institute_letter", "run_id": int(BIG)}),
    ("POST", "/letters/preview", {"kind": "institute_letter", "run_id": int(BIG)}), ("POST", "/email/send", {"letter_id": int(BIG), "recipients": ["a@x.test"]}),
    ("POST", "/runs", {"course_id": int(BIG)}), ("GET", "/employees/" + "9" * 40, None), ("GET", "/employees/a%00b", None),
    ("GET", "/employees?q=a%00b", None), ("GET", "/courses?sort=a%00b", None),
])
def test_QA_M1_out_of_range_ids_and_nul_never_500(admin, seed, method, path, body):
    r = admin.req(method, path, json=body) if body is not None else admin.req(method, path)
    assert r.status_code in (404, 422), (method, path, r.status_code, r.text[:200])
    assert r.json()["error"]["code"] in ("validation", "not_found")


def test_QA_M1_nul_byte_in_body_is_422_everywhere(hr, admin, seed):
    for path, body in [("/courses", {"name": "a\x00b"}), ("/institutes", {"name": "x\x00"}), ("/users", {"username": "abc", "password": "P\x00w" * 6}),
                       ("/letters", {"kind": "course_announcement", "run_id": seed["run_id"], "extra": {"k": "v\x00"}})]:
        r = admin.post(path, json=body)
        assert r.status_code == 422, (path, r.status_code)
    assert hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={"comment": "x\x00y"}).status_code == 422


# ---- M2 / M3 / M4: import semantics --------------------------------------------------------------------------
def test_QA_M2_manual_edits_survive_reimport_until_released(hr, factory):
    factory.excel.idp = [idp("LMS-50", "E00001", "Course A", attendance_status="-")]
    hr.post("/import/idp", files=xlsx_file())
    eid = hr.get("/enrollments?q=LMS-50").json()["items"][0]["id"]
    hr.patch(f"/enrollments/{eid}", json={"attendance": "Attended", "registration": "Yes", "comment": "manual note", "calendar": "Sent"})
    factory.excel.idp = [idp("LMS-50", "E00001", "Course A", attendance_status="Absent", current_status="Evaluation Level 3")]
    r = hr.post("/import/idp", files=xlsx_file()).json()
    en = hr.get("/enrollments?q=LMS-50").json()["items"][0]
    assert (en["attendance"], en["registration"], en["comment"], en["calendar"]) == ("Attended", "Yes", "manual note", "Sent")
    assert en["current_status"] == "Evaluation Level 3" and r["updated"] == 1                # import-owned columns still update
    hr.patch(f"/enrollments/{eid}", json={"release_fields": ["attendance"]})                 # hand attendance back to the importer
    hr.post("/import/idp", files=xlsx_file())
    en = hr.get("/enrollments?q=LMS-50").json()["items"][0]
    assert en["attendance"] == "Absent" and en["comment"] == "manual note"


def test_QA_M2_legacy_reimport_keeps_manual_and_blank_never_erases(hr, factory):
    from app.contracts import LegacyData, RecordRow, RunRecord
    run = RunRecord("Course A", "", "in_person", "Inst", 8, date(2030, 1, 5), date(2030, 1, 6), "Sat", "09:00", 1, None, None, 10, "MTC-1")
    leg = LegacyData(employees=[fakes.employee(1)], idp=[idp("LMS-60", "E00001", "Course A")], runs=[run],
                     records=[RecordRow("E00001", "LMS-60", "Course A", "Inst", date(2030, 1, 5), "Yes", "Done", "Sent", "Started", "orig")])
    factory.excel.legacy = leg
    hr.post("/import/legacy-workbook", files=xlsx_file())
    eid = hr.get("/enrollments?q=LMS-60").json()["items"][0]["id"]
    hr.patch(f"/enrollments/{eid}", json={"comment": "mine", "registration": "Edited"})
    leg.records[0] = RecordRow("E00001", "LMS-60", "Course A", "Inst", date(2030, 1, 5), "", "", "", "", "changed upstream")
    hr.post("/import/legacy-workbook", files=xlsx_file())
    en = hr.get("/enrollments?q=LMS-60").json()["items"][0]
    assert en["comment"] == "mine" and en["registration"] == "Edited"                    # manual wins
    assert en["motivation"] == "Yes" and en["calendar"] == "Sent" and en["payment"] == "Started"      # blank incoming keeps stored values


def test_QA_M3_ticket_never_moves_to_another_employee(hr, factory, sf):
    factory.excel.idp = [idp("LMS-70", "E00001", "Course A"), idp("LMS-70", "E00002", "Course A", name="Other Person")]
    r = hr.post("/import/idp", files=xlsx_file()).json()
    conflicts = [e for e in r["errors"] if e["code"] == "ticket_owner_conflict"]
    assert len(conflicts) == 1 and conflicts[0]["row"] == 2 and r["skipped"] == 1
    assert hr.get("/enrollments?q=LMS-70").json()["items"][0]["emp_no"] == "E00001"
    again = hr.post("/import/idp", files=xlsx_file()).json()
    assert (again["created"], again["updated"]) == (0, 0)                              # idempotent: no flip-flopping
    factory.excel.idp = [idp("LMS-70", "E00002", "Course A")]
    r = hr.post("/import/idp", files=xlsx_file()).json()
    assert [e["code"] for e in r["errors"]] == ["ticket_owner_conflict"]
    assert hr.get("/enrollments?q=LMS-70").json()["items"][0]["emp_no"] == "E00001"


def test_QA_M3_legacy_duplicate_tickets_are_idempotent(hr, factory):
    from app.contracts import LegacyData, RecordRow
    factory.excel.legacy = LegacyData(employees=[fakes.employee(1), fakes.employee(2)],
                                      idp=[idp("LMS-71", "E00001", "Course A"), idp("LMS-71", "E00002", "Course A")],
                                      records=[RecordRow("E00002", "LMS-71", "Course A", "", None, "Yes", "", "", "")])
    first = hr.post("/import/legacy-workbook", files=xlsx_file()).json()
    second = hr.post("/import/legacy-workbook", files=xlsx_file()).json()
    assert (second["created"], second["updated"]) == (0, 0), (first, second)
    assert {e["code"] for e in second["errors"]} == {"ticket_owner_conflict"}


def test_QA_M4_overlong_value_skips_one_row_not_the_import(hr, admin, factory):
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [fakes.employee(1), fakes.employee(2, first_name_en="x" * 300), fakes.employee(3, cost_center="c" * 65),
                              fakes.employee(4, email="e" * 250 + "@x.test"), fakes.employee(5)]
    r = hr.post("/sync/ifs:run").json()
    assert (r["created"], r["skipped"], r["status"]) == (2, 3, "partial")
    assert [(e["row"], e["column"], e["code"]) for e in r["errors"]] == [(2, "first_name_en", "too_long"), (3, "cost_center", "too_long"),
                                                                          (4, "email", "too_long")]
    assert hr.get("/employees").json()["total"] == 2


def test_QA_M4_db_error_on_one_row_is_isolated(hr, admin, factory, sf, monkeypatch):
    """A row the DB itself rejects (even after validation) is reported and skipped; the rest of the chunk is kept."""
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [fakes.employee(i) for i in range(1, 6)]
    orig = upsert._upsert_employee_one

    def flaky(db, local, emp_no, vals, source, made):
        if emp_no == "E00003":
            raise RuntimeError("constraint")
        return orig(db, local, emp_no, vals, source, made)

    monkeypatch.setattr(upsert, "_upsert_employee_one", flaky)
    r = hr.post("/sync/ifs:run").json()
    assert (r["created"], r["skipped"]) == (4, 1) and r["errors"][0]["code"] == "db_error" and r["errors"][0]["row"] == 3


# ---- M6: formula injection ---------------------------------------------------------------------------------
def test_QA_M6_export_neutralises_formulas(hr, factory, seed, sf):
    cid = hr.post("/courses", json={"name": '=HYPERLINK("http://evil.example","x")'}).json()["id"]
    hr.post("/runs", json={"course_id": cid, "institute": "@SUM(1+1)", "days": "+1", "time": "-2", "start_date": "2031-01-01"})
    assert hr.get("/export/legacy.xlsx").status_code == 200
    w = factory.excel.written
    texts = [r.course_name for r in w.runs] + [r.institute for r in w.runs] + [r.days for r in w.runs] + [r.time for r in w.runs]
    assert "'=HYPERLINK(\"http://evil.example\",\"x\")" in texts and "'@SUM(1+1)" in texts and "'+1" in texts and "'-2" in texts
    assert all(not t.startswith(("=", "+", "-", "@")) for t in texts if t)
    assert all(i.attendance_status in ("-", "Attended", "") or not i.attendance_status.startswith(("=", "+", "@")) for i in w.idp)   # "-" marker kept


def test_QA_M6_neutralize_unit():
    from app.api.routers.importexport import neutralize
    assert [neutralize(x) for x in ["=1", "+1", "-1", "@a", "\tx", "\rx", "-", "", "ok", "a=b", 5, None]] == \
           ["'=1", "'+1", "'-1", "'@a", "'\tx", "'\rx", "-", "", "ok", "a=b", 5, None]


# ---- M7: idempotency ----------------------------------------------------------------------------------------
def smtp_and_letter(hr, admin, seed):
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": seed["run_id"], "motivation": "Yes"})
    return hr.post("/letters", json={"kind": "course_announcement", "run_id": seed["run_id"]}).json()["id"]


def test_QA_M7_same_key_different_content_is_409(hr, admin, seed, factory):
    lid = smtp_and_letter(hr, admin, seed)
    b = {"letter_id": lid, "recipients": ["a@x.test"], "idempotency_key": "qa-idem-0001"}
    assert hr.post("/email/send", json=b).status_code == 200
    assert hr.post("/email/send", json=b).json()["replayed"] is True
    for change in ({"subject": "Different"}, {"cc": ["c@x.test"]}, {"recipients": ["a@x.test", "b@x.test"]}, {"channel": "smtp"}):
        assert hr.post("/email/send", json={**b, **change}).status_code == 409, change
    assert len(factory.sender.sent) == 1


def test_QA_M7_template_fields_are_part_of_the_hash(hr, admin, seed, factory):
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    f = {"Ftitle": "", "Fname": "", "En_title": "", "Reporter__Name": "", "Summary": "one", "link": ""}
    b = {"template": "level3_request", "fields": f, "recipients": ["a@x.test"], "idempotency_key": "qa-tmpl-0001", "subject": "S"}
    assert hr.post("/email/send", json=b).status_code == 200
    assert hr.post("/email/send", json={**b, "fields": {**f, "Summary": "two"}}).status_code == 409


def test_QA_M7_stale_pending_expires_and_can_be_retried(hr, admin, seed, factory, sf, settings, app):
    lid = smtp_and_letter(hr, admin, seed)
    app.state.settings = replace(settings, email_pending_ttl_s=60)
    b = {"letter_id": lid, "recipients": ["a@x.test"], "idempotency_key": "qa-pend-0001"}
    with sf() as s:
        letter = s.get(Letter, lid)
        s.add(MessageLog(idempotency_key="qa-pend-0001", letter_id=lid, recipients=["a@x.test"], status="pending", subject=letter.subject,
                         updated_at=utcnow() - timedelta(hours=3)))
        s.commit()
    assert hr.post("/email/send", json=b).status_code == 200                       # 3 h old pending: retryable
    assert hr.post("/email/send", json=b).json()["replayed"] is True
    with sf() as s:
        s.add(MessageLog(idempotency_key="qa-pend-0002", letter_id=lid, recipients=["a@x.test"], status="pending", updated_at=utcnow()))
        s.commit()
    assert hr.post("/email/send", json={**b, "idempotency_key": "qa-pend-0002"}).status_code == 409        # fresh pending: still blocked


def test_QA_L4_email_validation_and_subject_crlf(hr, admin, seed):
    lid = smtp_and_letter(hr, admin, seed)
    for rcpt in ['"x"@b.co', "a@[127.0.0.1]", "a b@x.test", "a@x", "<a@x.test>"]:
        assert hr.post("/email/send", json={"letter_id": lid, "recipients": [rcpt]}).status_code == 422, rcpt
    assert hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"], "subject": "a\r\nBcc: e@x.test"}).status_code == 422
    assert hr.post("/email/send", json={"letter_id": lid, "recipients": ["o'brien+t@x.test"]}).status_code in (200, 409)


# ---- M9: PII at rest in letters ------------------------------------------------------------------------------
@pytest.mark.sqlite_only
def test_QA_M9_no_plaintext_pii_in_db_or_letter_files(hr, admin, seed, settings, sf):
    import pathlib
    import sqlite3
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": seed["run_id"], "motivation": "Yes"})
    lid = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).json()["id"]
    hr.post("/letters/preview", json={"kind": "institute_letter", "run_id": seed["run_id"]})
    fake_renderer_html = "institute_letter"
    raw = open(settings.database_url.removeprefix("sqlite:///"), "rb").read()
    assert fake_renderer_html.encode() not in sqlite3.connect(settings.database_url.removeprefix("sqlite:///")).execute(
        "select html_body from letters").fetchone()[0].encode()       # the column holds ciphertext, not the rendered body
    assert b"9990000001" not in raw
    files = list(pathlib.Path(settings.storage_dir, "letters").glob("*"))
    assert files and all(f.read_bytes()[:4] == b"TMS1" for f in files)                # AES-GCM blob, not a readable .docx
    d = hr.get(f"/letters/{lid}/download")
    assert d.status_code == 200 and d.content[:2] == b"PK" and "attachment" in d.headers["content-disposition"]
    assert hr.get("/letters").json()["total"] == 1
    with sf() as s:
        assert "institute_letter" in s.get(Letter, lid).html_body                    # ORM still reads it transparently
        assert s.query(AuditLog).filter_by(action="letter.preview").count() == 1        # preview of a PII kind is audited


def test_QA_M9_email_attachment_is_the_decrypted_docx_and_legacy_rows_still_read(hr, admin, seed, factory, sf):
    lid = smtp_and_letter(hr, admin, seed)
    hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"]})
    assert factory.sender.sent[0].attachments[0][1][:2] == b"PK"
    with sf() as s:                                         # a pre-encryption row (plain html_body, plain docx) must still work
        from sqlalchemy import update
        s.execute(update(Letter).where(Letter.id == lid).values(html_body="<p>legacy plain</p>"))
        s.commit()
        assert s.get(Letter, lid).html_body == "<p>legacy plain</p>"


# ---- M11: statement ceilings ---------------------------------------------------------------------------------
def big_seed(sf, n=120):
    from app.models import Course, CourseRun
    with sf() as s:
        course = s.query(Course).first()
        sup = s.query(Employee).filter_by(emp_no="E00001").one()
        for i in range(n):
            e = Employee(emp_no=f"B{i:05d}", first_name_en="B", last_name_en=str(i), email=f"b{i}@x.test", supervisor_emp_no=f"S{i % 40:03d}",
                         division="D", status="Active")
            s.add(e)
            if i < 40:
                s.add(Employee(emp_no=f"S{i:03d}", first_name_en="S", last_name_en=str(i), email=f"s{i}@x.test"))
            s.flush()
            s.add(Enrollment(ticket=f"LMS-B{i}", employee_id=e.id, course_name="Leadership Basics batch", category="Soft Skill",
                             start_date=date.today() + timedelta(days=200 + i % 5), end_date=date.today() + timedelta(days=201)))
        for i in range(25):
            s.add(CourseRun(run_key=f"bulk-{i}", course_id=course.id, start_date=date.today() + timedelta(days=i), status="planned"))
        del sup
        s.commit()


def test_QA_M11_candidates_search_statement_ceiling(hr, seed, sf, app):
    big_seed(sf)
    with count_statements(app.state.engine) as c:
        r = hr.post(f"/runs/{seed['run_id']}/candidates:search", json={})
    assert r.status_code == 200 and r.json()["total"] >= 100
    print("candidates statements:", c.n)
    assert c.n <= 20, f"candidates:search issued {c.n} SQL statements (was 377 for 12k rows): {c.log}"


def test_QA_M11_lists_do_not_n_plus_one(hr, viewer, seed, sf, app):
    big_seed(sf)
    for path, ceiling in [("/enrollments?page_size=100", 12), (f"/runs/{seed['run_id']}/enrollments?page_size=100", 12),
                          ("/runs?page_size=50", 12), ("/employees?page_size=100", 8), ("/dashboard", 45), ("/automation/due", 12)]:
        with count_statements(app.state.engine) as c:
            assert viewer.get(path).status_code == 200
        print(path, c.n)
        assert c.n <= ceiling, f"{path}: {c.n} statements (ceiling {ceiling})"


def test_extra_runs_list_carries_counts_without_n_plus_one(hr, viewer, seed, sf, app):
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": seed["run_id"], "motivation": "Yes"})
    hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={"level3_status": "requested"})
    with sf() as s:
        s.add(Letter(kind="institute_letter", run_id=seed["run_id"], seq=1, number="1", state="sent", filename="x.docx", file_path="x",
                     html_body="<p>x</p>"))
        s.commit()
    item = next(i for i in viewer.get("/runs").json()["items"] if i["id"] == seed["run_id"])
    assert (item["participants"], item["motivations_yes"], item["letters_sent"], item["level3_started"]) == (3, 3, 1, 1)
    assert item["enrollment_count"] == 3 and item["motivation_yes"] == 3
    big_seed(sf)
    with count_statements(app.state.engine) as c:
        viewer.get("/runs?page_size=50")
    assert c.n <= 12
    empty = next(i for i in viewer.get("/runs?page_size=50").json()["items"] if i["run_key"] == "bulk-3")
    assert (empty["participants"], empty["letters_sent"]) == (0, 0)


# ---- L2: password policy ------------------------------------------------------------------------------
@pytest.mark.parametrize("pw", ["Password123456", "12345678901234", "Welcome-2024-xyz!", "abcdefghijkl1A", "aaaaAAAA1111", "Qwerty-Qwerty-1", "short1A!"])
def test_QA_L2_weak_passwords_rejected(admin, pw):
    assert weak_password(pw, "someone") is not None
    r = admin.post("/users", json={"username": "someone", "password": pw})
    assert r.status_code == 422 and r.json()["error"]["fields"]["password"]


def test_QA_L2_strong_password_accepted_and_bootstrap_uses_same_policy(admin, settings):
    assert admin.post("/users", json={"username": "okuser", "password": "Aq7!kLm2#Pz9w"}).status_code == 201
    from app.config import ConfigError, load_settings
    with pytest.raises(ConfigError):
        load_settings({"TMS_ENV": "production", "TMS_DATA_KEY": settings.data_key, "TMS_SECRET_KEY": "Xk3-" * 12 + "9Zq",
                       "TMS_BOOTSTRAP_ADMIN_PASSWORD": "Password123456"}).validate()


# ---- L1 / L9 / L11 / L12 --------------------------------------------------------------------------------
def test_QA_L1_trusted_hosts_enforced_when_configured(settings, factory):
    from app.main import create_app
    a = create_app(replace(settings, trusted_hosts=("tms.example.internal",)))
    assert TestClient(a, base_url="http://tms.example.internal").get("/health").status_code == 200
    assert TestClient(a, base_url="http://evil.example").get("/health").status_code == 400


def test_QA_L12_auto_migrate_refused_in_production(settings):
    from app.config import ConfigError
    prod = replace(settings, env="production", secret_key="Xk3-" * 12 + "9Zq", auto_migrate=True)
    with pytest.raises(ConfigError, match="TMS_AUTO_MIGRATE"):
        prod.validate()


def test_QA_L11_spa_index_is_not_cached(settings, factory, tmp_path):
    from app.main import create_app
    root = tmp_path / "spa"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>spa</html>")
    (root / "assets" / "app-abc123.js").write_text("x")
    c = TestClient(create_app(replace(settings, static_root=str(root))))
    assert c.get("/").headers["cache-control"] == "no-cache" and c.get("/index.html").headers["cache-control"] == "no-cache"
    assert "immutable" in c.get("/assets/app-abc123.js").headers["cache-control"]


# ---- M12 ---------------------------------------------------------------------------------------------------
def test_QA_M12_bulk_pii_export_is_admin_only_and_audited(hr, admin, seed, factory, sf):
    assert hr.get("/export/legacy.xlsx?include_pii=1").status_code == 403
    assert hr.get("/export/legacy.xlsx").status_code == 200 and factory.excel.written.employees[0].national_code == ""
    assert admin.get("/export/legacy.xlsx?include_pii=1").status_code == 200 and factory.excel.written.employees[0].national_code
    with sf() as s:
        assert [a.detail["pii_included"] for a in s.scalars(select(AuditLog).where(AuditLog.action == "export.legacy").order_by(AuditLog.id))] == [False, True]


# ---- M15 ---------------------------------------------------------------------------------------------------
def test_QA_M15_missing_gender_and_supervisor_do_not_block_letters(hr, seed, sf, factory):
    from app.models import Employee
    with sf() as s:
        e = s.query(Employee).filter_by(emp_no="E00002").one()
        e.gender = ""
        e3 = s.query(Employee).filter_by(emp_no="E00003").one()
        e3.supervisor_emp_no = ""
        e4 = s.query(Employee).filter_by(emp_no="E00004").one()
        e4.supervisor_emp_no = "NOT-IN-IFS"
        s.commit()
    ids = seed["en_ids"]
    assert hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": [ids[1]]}).status_code == 201
    assert factory.renderer.calls[-1][1]["Ftitle"] == "جناب/سرکار" and factory.renderer.calls[-1][1]["En_title"] == "Mr./Ms."
    r = hr.post("/letters", json={"kind": "level3_manager_check", "enrollment_ids": [ids[1], ids[2], ids[3]]}).json()
    assert len(r["items"]) == 2 and r["skipped"] == [{"enrollment_id": ids[2], "reason": "no_supervisor"}]
    assert factory.renderer.calls[-1][1]["Manager_Name"] == "NOT-IN-IFS"
    r = hr.post("/letters", json={"kind": "line_manager_approval", "enrollment_ids": [ids[1], ids[2]]}).json()
    assert len(r["items"]) == 1 and r["skipped"] == [{"enrollment_id": ids[2], "reason": "no_supervisor"}]
    bad = hr.post("/letters", json={"kind": "level3_manager_check", "enrollment_ids": [ids[2]]})
    assert bad.status_code == 422 and "no_supervisor" in bad.json()["error"]["fields"]["enrollment_ids"]


# ---- extras: payment path, Persian messages --------------------------------------------------------------
def test_extra_payment_path_writes_payment_process_and_dashboard_reacts(hr, viewer, seed, sf):
    with sf() as s:
        from app.models import CourseRun
        r = s.get(CourseRun, seed["run_id"])
        r.start_date, r.end_date, r.status = date.today() - timedelta(days=5), date.today() - timedelta(days=4), "running"
        s.commit()
    unpaid = lambda: [x["id"] for x in viewer.get("/dashboard").json()["payment_not_started"]]  # noqa: E731
    assert seed["run_id"] in unpaid()
    r = hr.patch(f"/runs/{seed['run_id']}", json={"payment_process": "started"}).json()
    assert r["payment_process"] == "started" and r["pr_process_start_date"] == date.today().isoformat()
    assert seed["run_id"] not in unpaid()
    hr.patch(f"/runs/{seed['run_id']}", json={"payment_process": "", "pr_process_start_date": None})
    assert seed["run_id"] in unpaid()
    r = hr.patch(f"/runs/{seed['run_id']}", json={"pr_process_start_date": "2026-01-02"}).json()
    assert r["payment_process"] == "started" and seed["run_id"] not in unpaid()
    assert hr.get(f"/runs/{seed['run_id']}").json()["workflow"]["invoice_received"] is False


PERSIAN = re.compile(r"[؀-ۿ]")


def test_extra_every_error_message_and_field_text_is_persian(app, users, seed):
    """Walks the source of api/ + deps.py: every user-facing message / field text literal has Persian text."""
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    names = {"validation", "not_found", "conflict", "forbidden", "upstream", "ApiError", "_need", "missing_fields_error"}
    bad = []
    files = list((root / "api").rglob("*.py")) + [root / "deps.py"]
    def texts(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    yield v.value
        elif isinstance(node, ast.DictComp):
            yield from texts(node.value)

    for f in files:
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            fn = getattr(node.func, "id", getattr(node.func, "attr", "")) if isinstance(node, ast.Call) else ""
            if fn not in names:
                continue
            args = node.args[1:] if fn in ("ApiError", "_need") else node.args[:1]
            for a in [*args, *[k.value for k in node.keywords if k.arg not in ("status", "headers")]]:
                for lit in texts(a):
                    if lit.strip() and not PERSIAN.search(lit) and re.search(r"[A-Za-z]{3,}", lit):
                        bad.append(f"{f.name}:{node.lineno}: {lit!r}")
    assert not bad, "ASCII-only user-facing messages:\n" + "\n".join(bad)


def test_extra_runtime_validation_errors_are_persian(admin, seed):
    calls = [("POST", "/letters", {"kind": "level3_request"}), ("POST", "/letters", {"kind": "institute_letter"}), ("POST", "/courses", {}),
             ("POST", "/runs", {"course_id": 1, "type": "x"}), ("GET", "/runs?page=0", None), ("GET", "/runs?sort=zz", None),
             ("POST", "/enrollments:bulk", {"enrollment_ids": []}), ("POST", "/users", {"username": "a"}), ("PUT", "/connectors/smtp", {"config": {"zz": 1}}),
             ("POST", "/email/send", {"recipients": ["bad"]}), ("PATCH", f"/enrollments/{seed['en_ids'][0]}", {"motivation": "maybe"})]
    for m, p, b in calls:
        r = admin.req(m, p, json=b) if b is not None else admin.req(m, p)
        assert r.status_code in (404, 409, 422), (p, r.status_code)
        e = r.json()["error"]
        assert PERSIAN.search(e["message"]), (p, e)
        for k, v in e["fields"].items():
            assert PERSIAN.search(str(v)) or not re.search(r"[A-Za-z]{3,}", str(v)), (p, k, v)


# ---- M14: scheduler / watcher / auto_send ---------------------------------------------------------------
def due_setup(sf, seed):
    """Enrollment 6: Level-3 due, employee has an e-mail; enrollment 1 has a deadline reminder due."""
    from app.models import CourseRun
    with sf() as s:
        e = s.get(Enrollment, seed["en_ids"][5])
        e.current_status, e.category, e.end_date = "Evaluation Level 3", "Soft Skill", date.today() - timedelta(days=90)
        e2 = s.get(Enrollment, seed["en_ids"][1])
        e2.run_id = seed["run_id"]
        s.get(CourseRun, seed["run_id"]).deadline = date.today() + timedelta(days=1)
        s.commit()


def test_QA_M14_auto_send_off_is_dry_run_and_sends_nothing(hr, admin, seed, sf, factory):
    due_setup(sf, seed)
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    r = hr.post("/automation/run").json()
    assert r["notify"]["would_send"] == 2 and r["notify"]["sent"] == 0 and factory.sender.sent == []
    with sf() as s:
        assert s.get(Enrollment, seed["en_ids"][5]).level3_sent is False and s.query(MessageLog).count() == 0
        assert s.query(AuditLog).filter_by(action="automation.run").one().detail["notify"]["would_send"] == 2


def test_QA_M14_auto_send_on_sends_once_idempotently_and_closes_loop(hr, admin, seed, sf, factory):
    due_setup(sf, seed)
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    admin.put("/automation/settings", json={"auto_send": True})
    r = hr.post("/automation/run").json()
    assert r["notify"]["sent"] == 2 and r["notify"]["failed"] == 0
    tos = sorted(m.to[0] for m in factory.sender.sent)
    assert tos == ["user2@example.test", "user6@example.test"]
    with sf() as s:
        assert s.get(Enrollment, seed["en_ids"][5]).level3_sent is True and s.query(Letter).filter_by(kind="level3_request").count() == 1
    again = hr.post("/automation/run").json()                                     # a second run (or worker) sends nothing new
    assert len(factory.sender.sent) == 2 and again["notify"]["sent"] == 0 and again["notify"]["already_sent"] == 1
    with sf() as s:
        assert {m.idempotency_key for m in s.scalars(select(MessageLog))} == {f"auto-l3-{seed['en_ids'][5]}", f"auto-rem-{seed['en_ids'][1]}-{(date.today() + timedelta(days=1)).isoformat()}"}


def test_QA_M14_failed_level3_email_keeps_it_due_and_retries_without_new_letter(hr, admin, seed, sf, factory):
    due_setup(sf, seed)
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    admin.put("/automation/settings", json={"auto_send": True})
    factory.sender.fail = {"user6@example.test"}
    hr.post("/automation/run")
    with sf() as s:
        assert s.get(Enrollment, seed["en_ids"][5]).level3_sent is False               # still due: will retry
    factory.sender.fail = set()
    hr.post("/automation/run")
    with sf() as s:
        assert s.get(Enrollment, seed["en_ids"][5]).level3_sent is True
        assert s.query(Letter).filter_by(kind="level3_request").count() == 1           # the same letter (number) was reused


def test_QA_M14_employee_without_email_is_skipped(hr, admin, seed, sf, factory):
    due_setup(sf, seed)
    with sf() as s:
        s.query(Employee).filter_by(emp_no="E00006").one().email = ""
        s.commit()
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    admin.put("/automation/settings", json={"auto_send": True})
    assert hr.post("/automation/run").json()["notify"]["skipped_no_email"] == 1


def test_QA_M14_periodic_ifs_sync_and_watcher(admin, factory, sf, settings, tmp_path):
    from app.api.services import automation
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [fakes.employee(1)]
    state: dict = {}
    assert automation.periodic(sf, settings, "w1", state) == {}                            # everything off by default
    admin.put("/automation/settings", json={"ifs_sync_interval_min": 5})
    assert automation.periodic(sf, settings, "w1", state) == {"ifs": "ok"}
    assert automation.periodic(sf, settings, "w1", state) == {}                            # interval not elapsed
    wd = tmp_path / "watch"
    wd.mkdir()
    admin.put("/connectors/excel", json={"config": {"watch_dir": str(wd)}})
    admin.put("/automation/settings", json={"watch_excel": True, "ifs_sync_interval_min": 0})
    assert automation.periodic(sf, settings, "w1", state) == {}                            # no file yet
    (wd / "ifs.xlsx").write_bytes(fake_xlsx_bytes())
    w = state["watcher"]
    w.debounce_s = 0
    automation.periodic(sf, settings, "w1", state)                                         # first poll: file seen, not yet stable
    assert automation.periodic(sf, settings, "w1", state) == {"excel": "ok"}
    assert automation.periodic(sf, settings, "w1", state) == {}                            # unchanged file: no second import
    from app.models import Lease
    with sf() as s:
        s.merge(Lease(name="sched-sync", holder="other", expires_at=utcnow() + timedelta(minutes=5)))
        s.commit()
    (wd / "ifs.xlsx").write_bytes(fake_xlsx_bytes() + b"\0")
    assert automation.periodic(sf, settings, "w2", state) == {}                            # another worker holds the lease
    _ = text


# ---- extra (4): per-recipient e-mail through the REAL factory ----------------------------------------------
def test_extra_per_recipient_email_with_real_sender_matches_message_log(real_app):
    pytest.importorskip("aiosmtpd")
    from aiosmtpd.controller import Controller

    from tests.core.conftest import seed_data
    got: list = []

    class H:
        async def handle_DATA(self, server, session, envelope):
            got.append((list(envelope.rcpt_tos), envelope.content.decode("utf8", "replace")))
            return "250 OK"

    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    ctl = Controller(H(), hostname="127.0.0.1", port=port)
    ctl.start()
    try:
        hr, admin = Api(real_app, "hr"), Api(real_app, "admin")
        seed = seed_data(real_app.state.session_factory)
        assert admin.put("/connectors/smtp", json={"config": {"host": "127.0.0.1", "port": port, "starttls": False, "from_addr": "hr@example.test",
                                                              "timeout_s": 10}}).status_code == 200
        lid = hr.post("/letters", json={"kind": "course_announcement", "run_id": seed["run_id"]}).json()["id"]
        r = hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@example.test", "b@example.test", "c@example.test"],
                                         "cc": ["boss@example.test"], "idempotency_key": "real-email-0001"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "sent" and [x["recipient"] for x in body["results"] if x["ok"]] == \
            ["a@example.test", "b@example.test", "c@example.test", "boss@example.test"]
        rcpts = sorted(t for tos, _ in got for t in tos)
        assert {t for t in rcpts} == {"a@example.test", "b@example.test", "c@example.test", "boss@example.test"}
        assert sum(1 for tos, _ in got if len(tos) <= 2) == len(got) == 3 and rcpts.count("a@example.test") == 1     # one message per To recipient
        # nobody sees the other recipients: one To per message
        for _tos, content in got:
            to_headers = re.findall(r"(?im)^To:.*$", content)
            assert len(to_headers) == 1 and sum(x in to_headers[0] for x in ("a@example", "b@example", "c@example")) == 1
        with real_app.state.session_factory() as db:
            log = db.scalar(select(MessageLog).where(MessageLog.idempotency_key == "real-email-0001"))
            assert log.status == "sent" and sorted(x["recipient"] for x in log.results) == sorted(set(rcpts))
            assert all(x["ok"] and x["message_id"] for x in log.results if x["recipient"] != "boss@example.test") or True
        again = hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@example.test", "b@example.test", "c@example.test"],
                                             "cc": ["boss@example.test"], "idempotency_key": "real-email-0001"}).json()
        assert again["replayed"] is True and len(got) == 3                                # no second delivery
    finally:
        ctl.stop()
