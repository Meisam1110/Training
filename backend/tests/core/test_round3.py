import os
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import REQUIRED_TEMPLATES, Settings, default_templates_dir, load_settings
from tests.core import fakes
from tests.core.conftest import Api
from tests.core.test_integrations_wiring import idp, xlsx_file


# ---- templates dir ---------------------------------------------------------------------------------
def test_default_templates_dir_is_repo_templates_regardless_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TMS_TEMPLATES_DIR", raising=False)
    d = default_templates_dir()
    assert os.path.isabs(d) and d.endswith("templates") and os.path.isdir(d)
    assert load_settings({}).templates_dir == d and Settings().templates_dir == d
    assert load_settings({"TMS_TEMPLATES_DIR": "rel/tpl"}).templates_dir == str((tmp_path / "rel" / "tpl").resolve())


def test_app_from_other_cwd_previews_all_six_kinds_with_real_renderer(settings, users, seed, monkeypatch, tmp_path):
    pytest.importorskip("docx")
    from app.main import create_app
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    st = replace(settings, templates_dir=default_templates_dir())          # what an unconfigured deployment gets
    a = create_app(st)
    hr, admin = Api(a, "hr"), Api(a, "admin")
    assert TestClient(a).get("/ready").json()["templates"] is True
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": seed["run_id"], "motivation": "Yes"})
    admin.put("/automation/settings", json={"company_economic_code": "1", "company_national_id": "2", "company_postal_code": "3",
                                            "company_address": "Test Street", "settlement_addressee": "Finance"})
    ids = seed["en_ids"]
    for b in ({"kind": "course_announcement", "run_id": seed["run_id"]}, {"kind": "institute_letter", "run_id": seed["run_id"]},
              {"kind": "settlement_letter", "run_id": seed["run_id"]}, {"kind": "level3_request", "enrollment_ids": ids[1:2]},
              {"kind": "level3_manager_check", "enrollment_ids": ids[1:2]}, {"kind": "line_manager_approval", "enrollment_ids": ids[1:4]}):
        r = hr.post("/letters/preview", json=b)
        assert r.status_code == 200, (b["kind"], r.text)
        assert r.json()["missing_fields"] == [] and r.json()["html"]


def test_ready_reports_missing_templates(settings, app, tmp_path):
    os.remove(os.path.join(settings.templates_dir, "level3_request.docx"))
    r = TestClient(app).get("/ready")
    assert r.status_code == 503 and r.json()["status"] == "templates_missing" and r.json()["missing_templates"] == ["level3_request"]
    assert set(REQUIRED_TEMPLATES) >= {"level3_request"}


def test_dockerfile_ships_templates_and_sets_env():
    root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    text = open(os.path.join(root, "Dockerfile")).read()
    assert "COPY templates/ ./templates/" in text and "TMS_TEMPLATES_DIR=/app/templates" in text


# ---- import per-row errors -------------------------------------------------------------------------
def test_import_returns_row_errors_without_values(hr, factory):
    factory.excel.idp = [idp("LMS-1", "E00001", "Course A"), idp("", "E00002", "Course B", name="Secret Name"),
                         idp("LMS-3", "E00003", "  "), idp("LMS-4", "", "Course D")]
    r = hr.post("/import/idp", files=xlsx_file()).json()
    assert r["skipped"] == 3 and r["created"] == 2      # 1 stub employee + 1 enrollment
    got = [(e["sheet"], e["row"], e["column"], e["code"]) for e in r["errors"]]
    assert got == [("idp", 2, "ticket/emp_no", "invalid_key"), ("idp", 3, "summary", "missing_course_name"),
                   ("idp", 4, "ticket/emp_no", "invalid_key")]
    assert all(e["reason"] for e in r["errors"]) and "Secret" not in str(r) and "E0000" not in str(r["errors"])
    assert r["message"].startswith("created=2")


def test_legacy_import_row_errors(hr, factory):
    from app.contracts import LegacyData, RecordRow, RunRecord
    factory.excel.legacy = LegacyData(
        employees=[fakes.employee(1)], runs=[RunRecord("", "", "online", "I", 1, None, None, "", "", 0, None, None, None, "")],
        records=[RecordRow("E00077", "LMS-9", "C", "I", None, "Yes", "", "", ""), RecordRow("E00001", "", "C", "I", None, "", "", "", "")])
    r = hr.post("/import/legacy-workbook", files=xlsx_file()).json()
    assert [(e["sheet"], e["row"], e["column"]) for e in r["errors"]] == [("runs", 1, "course_name"), ("records", 1, "emp_no"),
                                                                            ("records", 2, "ticket")]


# ---- enrollment recipients, filters ----------------------------------------------------------------
def test_enrollment_email_and_supervisor_email_and_motivation_none(hr, viewer, seed):
    j = viewer.get("/enrollments?emp_no=E00002").json()["items"][0]
    assert j["email"] == "user2@example.test" and j["supervisor_email"] == "user1@example.test" and j["supervisor_emp_no"] == "E00001"
    top = viewer.get("/enrollments?emp_no=E00001").json()["items"][0]
    assert top["supervisor_email"] == "" and top["email"] == "user1@example.test"
    assert viewer.get("/enrollments?motivation=none").json()["total"] == 3            # seed: 3 answered "Yes", 3 blank
    assert viewer.get("/enrollments?motivation=Yes").json()["total"] == 3
    p = hr.patch(f"/enrollments/{seed['en_ids'][1]}", json={"comment": "x"}).json()
    assert p["supervisor_email"] == "user1@example.test"
    cand = hr.post(f"/runs/{seed['run_id']}/candidates:search", json={}).json()["candidates"]
    assert all("email" in c and "supervisor_email" in c for c in cand)


# ---- messages --------------------------------------------------------------------------------------
def test_connector_last_test_message_and_sync_message(admin, hr, factory):
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    admin.post("/connectors/smtp:test")
    c = next(x for x in admin.get("/connectors").json()["items"] if x["kind"] == "smtp")
    assert c["last_test_ok"] is True and c["last_test_message"] == "ok password=***"
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [fakes.employee(1)]
    assert hr.post("/sync/ifs:run").json()["message"] == "created=1 updated=0 unchanged=0 skipped=0"
    factory.source.boom = True
    hr.post("/sync/ifs:run")
    last = hr.get("/sync/runs?sort=-id").json()["items"][0]
    assert last["status"] == "error" and "0912345678" not in last["message"] and last["message"].startswith("RuntimeError")
    assert last["errors"][0]["code"] == "source_error"


def test_run_delivery_type_alias(hr, seed):
    r = hr.get(f"/runs/{seed['run_id']}").json()
    assert r["type"] == r["delivery_type"] == "in_person"


# ---- workflow --------------------------------------------------------------------------------------
def test_run_workflow_flags_from_real_data(hr, admin, seed, factory, sf):
    rid = seed["run_id"]
    wf = lambda: hr.get(f"/runs/{rid}").json()["workflow"]  # noqa: E731
    assert wf() == dict(announced=False, motivations_collected=False, institute_letter_sent=False, invoice_received=False,
                        settlement_sent=False, level3_started=False)
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})
    # announcement e-mailed -> announced
    lid = hr.post("/letters", json={"kind": "course_announcement", "run_id": rid}).json()["id"]
    assert wf()["announced"] is False                                            # created but not sent
    hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"]})
    assert wf()["announced"] is True
    # motivations: everyone answered
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": rid})
    assert wf()["motivations_collected"] is False
    hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={"motivation": "Yes"})
    assert wf()["motivations_collected"] is False
    hr.patch(f"/enrollments/{seed['en_ids'][1]}", json={"motivation": "No"})
    assert wf()["motivations_collected"] is True
    # institute letter sent / settlement sent / invoice received / level3
    il = hr.post("/letters", json={"kind": "institute_letter", "run_id": rid}).json()["id"]
    assert wf()["institute_letter_sent"] is False
    hr.post("/email/send", json={"letter_id": il, "recipients": ["i@x.test"]})
    assert wf()["institute_letter_sent"] is True
    assert wf()["settlement_sent"] is False
    sl = hr.post("/letters", json={"kind": "settlement_letter", "run_id": rid}).json()["id"]
    factory.sender.fail = {"s@x.test"}
    hr.post("/email/send", json={"letter_id": sl, "recipients": ["s@x.test"]})
    assert wf()["settlement_sent"] is False                                      # failed send does not count
    factory.sender.fail = set()
    hr.post("/email/send", json={"letter_id": sl, "recipients": ["s@x.test"], "idempotency_key": "wf-settle-01"})
    assert wf()["settlement_sent"] is True
    assert wf()["invoice_received"] is False
    p = hr.patch(f"/runs/{rid}", json={"invoice_receive_date": str(date.today() - timedelta(days=1))}).json()
    assert p["workflow"]["invoice_received"] is True
    assert wf()["level3_started"] is False
    hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={})
    with sf() as s:
        from app.models import Enrollment
        s.get(Enrollment, seed["en_ids"][0]).level3_sent = True
        s.commit()
    assert wf()["level3_started"] is True


def test_run_workflow_announced_by_status_and_list_has_no_workflow(hr, seed):
    hr.patch(f"/runs/{seed['run_id']}", json={"status": "open"})
    assert hr.get(f"/runs/{seed['run_id']}").json()["workflow"]["announced"] is True
    assert "workflow" not in hr.get("/runs").json()["items"][0]
