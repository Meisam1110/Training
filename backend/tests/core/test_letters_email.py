import threading
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.services import numbering, rules
from app.models import AuditLog, Enrollment, Letter, LetterCounter, MessageLog
from tests.core import fakes


def assign_all(hr, seed, n=3):
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:n], "run_id": seed["run_id"], "motivation": "Yes"})


# ---- invoice math --------------------------------------------------------------------------------
@pytest.mark.parametrize("amount,mot,att", [(1000, 3, 3), (1000, 3, 7), (999999, 5, 4), (1, 1, 3), (0, 4, 2), ("2500000.50", 3, 7), (7, 0, 5)])
def test_invoice_split_sums_exactly(amount, mot, att):
    s = rules.invoice_split(amount, mot, att)
    assert sum(s.shares) == s.total and len(s.shares) == att
    assert max(s.shares) - min(s.shares) <= 1
    assert s.total == (Decimal(str(amount)) * mot).quantize(Decimal(1), rounding="ROUND_HALF_UP")


def test_invoice_split_rejects_bad_input():
    with pytest.raises(ValueError):
        rules.invoice_split(1, 1, 0)
    with pytest.raises(ValueError):
        rules.invoice_split(1, -1, 2)


def test_line_manager_batches_max_nine():
    class E:  # minimal stand-in
        def __init__(self, i, sup): self.id, self.employee = i, type("X", (), {"supervisor_emp_no": sup})()
    es = [E(i, "M1") for i in range(20)] + [E(100, "M2"), E(101, "")]
    batches, orphans = rules.line_manager_batches(es)
    assert [(s, len(b)) for s, b in batches] == [("M1", 9), ("M1", 9), ("M1", 2), ("M2", 1)]
    assert [o.id for o in orphans] == [101]


# ---- letters -------------------------------------------------------------------------------------
def test_letter_preview_create_download(hr, viewer, seed, factory, sf):
    assign_all(hr, seed)
    body = {"kind": "institute_letter", "run_id": seed["run_id"], "lang": "fa"}
    p = hr.post("/letters/preview", json=body).json()
    assert p["kind"] == "institute_letter" and "—" in p["html"] and p["count"] == 1
    with sf() as s:
        assert s.query(Letter).count() == 0 and s.query(LetterCounter).count() == 0        # preview consumes no number
    r = hr.post("/letters", json=body)
    assert r.status_code == 201, r.text
    L = r.json()
    assert L["number"] == "1" and L["state"] == "final" and L["items"][0]["id"] == L["id"]
    fields = dict(factory.renderer.calls[-1][1])
    assert fields["Letter_No"] == "1" and len(fields["participants"]) == 3 and fields["To"] == "مؤسسه نمونه"
    assert set(fields["participants"][0]) == {"name", "national_id", "phone", "email"} and "company_address" in fields
    assert hr.post("/letters", json=body).json()["number"] == "2"
    d = hr.get(f"/letters/{L['id']}/download")
    assert d.status_code == 200 and d.content[:2] == b"PK" and "attachment" in d.headers["content-disposition"]
    assert viewer.get("/letters/1/download").status_code == 403
    assert viewer.get("/letters?kind=institute_letter&sort=-number").json()["items"][0]["number"] == "2"
    assert viewer.get("/letters?run_id=%d&state=final&q=2" % seed["run_id"]).json()["total"] == 1
    assert hr.get("/letters/999/download").status_code == 404
    with sf() as s:
        assert s.query(AuditLog).filter_by(action="letter.create").count() == 2


def test_letter_prefix_and_start_come_from_settings_not_code(admin, hr, seed):
    assign_all(hr, seed)
    admin.put("/automation/settings", json={"letter_number_prefix": "TD/", "letter_number_start": 500})
    n = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).json()["number"]
    assert n == "TD/501"


def test_settlement_letter_math(hr, seed, factory, sf):
    assign_all(hr, seed)                        # 3 attendees with motivation, amount 1000 -> total 3000
    hr.post("/letters", json={"kind": "settlement_letter", "run_id": seed["run_id"], "extra": {"invoice_no": "INV-1"}})
    f = factory.renderer.calls[-1][1]
    assert f["total"] == "3,000" and f["per_attendee"] == "1,000" and f["attendee_count"] == "3" and f["invoice_no"] == "INV-1"
    assert len(f["rows"]) == 3 and f["rows"][0]["description"].startswith("Leadership Basics-MTC-1-")
    assert f["start_date_greg"].count("/") == 2 and f["mtc_no"] == "MTC-1"
    assert "invoice_total" not in f and "attendees" not in f and "start_date_gregorian" not in f
    # 2 attendees selected out of 3 motivations, odd amount: total = amount x motivations, split over attendees
    hr.patch(f"/runs/{seed['run_id']}", json={"amount": "1001"})
    hr.post("/letters", json={"kind": "settlement_letter", "run_id": seed["run_id"], "enrollment_ids": seed["en_ids"][:2]})
    f = factory.renderer.calls[-1][1]
    assert f["total"] == "3,003" and f["per_attendee"] == "1,502" and f["attendee_count"] == "2"
    assert [r["amount"] for r in f["rows"]] == ["1,502", "1,501"]        # exact shares: they sum to the total


def test_course_announcement_fields(hr, seed, factory):
    r = hr.post("/letters", json={"kind": "course_announcement", "run_id": seed["run_id"]})
    assert r.status_code == 201
    f = factory.renderer.calls[-1][1]
    assert f["Farsi_Course_Name"] == "مبانی رهبری" and f["Course_Name"] == "Leadership Basics" and f["Sessions_Count"] == "2"
    assert f["Type"] == "In-Person" and f["Duration"] == "16 Hours" and f["Time_Farsi"] == "۱۶ ساعت" and f["Day"] == "Sat"
    assert f["Deadline"].count("-") == 3 and f["start_Date"].count("/") == 2


def test_per_enrollment_and_manager_batches(hr, seed, factory, sf):
    ids = seed["en_ids"]
    r = hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": ids[1:3]}).json()
    assert len(r["items"]) == 2 and {i["number"] for i in r["items"]} == {"1", "2"}
    assert factory.renderer.calls[-1][1]["link"].endswith("LMS-102")
    assert hr.post("/letters", json={"kind": "level3_manager_check", "enrollment_ids": ids[1:2]}).status_code == 201
    assert hr.post("/letters", json={"kind": "level3_manager_check", "enrollment_ids": ids[:1]}).status_code == 422   # E1 has no supervisor
    # 5 employees under manager E1 -> one letter, tickets filled, slots 6-9 empty
    lm = hr.post("/letters", json={"kind": "line_manager_approval", "enrollment_ids": ids[1:]}).json()
    assert len(lm["items"]) == 1
    f = factory.renderer.calls[-1][1]
    assert len(f["employees"]) == 5 and f["employees"][4]["ticket"].endswith("LMS-105") and f["Mg_name"] == "Test1 Person1"
    assert hr.post("/letters", json={"kind": "line_manager_approval", "enrollment_ids": ids[:1]}).status_code == 422


def test_line_manager_letters_split_over_nine(hr, seed, factory, sf):
    from app.models import Employee
    with sf() as s:
        mgr = s.query(Employee).filter_by(emp_no="E00001").one()
        ids = []
        for i in range(11):
            e = Employee(emp_no=f"X{i:03d}", first_name_en="A", last_name_en=f"B{i}", supervisor_emp_no=mgr.emp_no)
            s.add(e)
            s.flush()
            en = Enrollment(ticket=f"LMS-9{i:02d}", employee_id=e.id, course_name="C")
            s.add(en)
            s.flush()
            ids.append(en.id)
        s.commit()
    r = hr.post("/letters", json={"kind": "line_manager_approval", "enrollment_ids": ids}).json()
    assert [len(i["enrollment_ids"]) for i in r["items"]] == [9, 2]


@pytest.mark.parametrize("body", [
    {"kind": "institute_letter"},                                        # run missing
    {"kind": "institute_letter", "run_id": 999},
    {"kind": "level3_request"},                                          # enrollments missing
    {"kind": "level3_request", "enrollment_ids": [999]},
    {"kind": "nope", "run_id": 1},
    {"kind": "institute_letter", "run_id": 1, "extra": {"a": {"b": 1}}},
])
def test_letter_validation(hr, seed, body):
    assert hr.post("/letters", json=body).status_code in (404, 422)
    assert hr.post("/letters/preview", json=body).status_code in (404, 422)


def test_letter_needs_participants_and_amount(hr, seed):
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).status_code == 422   # nobody enrolled
    hr.post("/runs", json={"course_id": seed["course_id"], "institute": "NoAmt", "start_date": "2031-01-01"})
    assign_all(hr, seed)
    rid = hr.get("/runs?q=leadership&sort=-id").json()["items"][0]["id"]
    hr.patch(f"/enrollments/{seed['en_ids'][3]}", json={"run_id": rid})
    assert hr.post("/letters", json={"kind": "settlement_letter", "run_id": rid, "enrollment_ids": [seed["en_ids"][3]]}).status_code == 422


def test_missing_template_fields_and_renderer_failure(hr, seed, factory, monkeypatch):
    assign_all(hr, seed)
    monkeypatch.setitem(fakes.REQUIRED, "institute_letter", ["Letter_No", "does_not_exist"])
    r = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]})
    assert r.status_code == 422 and r.json()["error"]["fields"] == {"does_not_exist": "الزامی است"}
    monkeypatch.setitem(fakes.REQUIRED, "institute_letter", ["Letter_No"])
    monkeypatch.setattr(factory.renderer, "render", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("template missing at /srv/x")))
    r = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]})
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream"


def test_letter_numbers_unique_under_concurrency(sf):
    got, lock = [], threading.Lock()

    def worker():
        for _ in range(10):
            seq, _n = numbering.next_number(sf, "institute_letter")
            with lock:
                got.append(seq)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(got) == 80 and sorted(got) == list(range(1, 81))


def test_concurrent_letter_creation_over_http(hr, seed, app, sf):
    assign_all(hr, seed)
    codes, lock = [], threading.Lock()

    def go():
        r = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]})
        with lock:
            codes.append((r.status_code, r.json().get("number")))

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(c == 201 for c, _ in codes), codes
    with sf() as s:
        assert sorted(x.seq for x in s.scalars(select(Letter))) == list(range(1, 7))


def test_no_gap_reuse_and_files_cleaned_on_failure(hr, seed, factory, settings, monkeypatch):
    assign_all(hr, seed)
    orig = factory.renderer.render
    state = {"n": 0}

    def flaky(kind, fields, lang="both"):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("boom")
        return orig(kind, fields, lang)

    monkeypatch.setattr(factory.renderer, "render", flaky)
    ids = seed["en_ids"][1:4]
    r = hr.post("/letters", json={"kind": "level3_request", "enrollment_ids": ids})
    assert r.status_code == 502
    assert hr.get("/letters").json()["total"] == 0                         # whole batch rolled back
    import pathlib
    assert not list(pathlib.Path(settings.storage_dir, "letters").glob("*"))


# ---- email ---------------------------------------------------------------------------------------
def connect_smtp(admin):
    assert admin.put("/connectors/smtp", json={"config": {"host": "smtp.test", "port": 587, "password": "pw-secret-1"}}).status_code == 200


def make_letter(hr, seed):
    assign_all(hr, seed)
    return hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).json()["id"]


def test_email_requires_exactly_one_source_and_valid_recipients(hr, seed):
    assert hr.post("/email/send", json={"recipients": ["a@x.test"]}).status_code == 422
    assert hr.post("/email/send", json={"letter_id": 1, "template": "level3_request", "recipients": ["a@x.test"]}).status_code == 422
    assert hr.post("/email/send", json={"letter_id": 1, "recipients": ["not-an-email"]}).status_code == 422
    assert hr.post("/email/send", json={"letter_id": 1, "recipients": []}).status_code == 422
    assert hr.post("/email/send", json={"letter_id": 999, "recipients": ["a@x.test"]}).status_code == 404


def test_email_without_connector_conflict_but_dry_run_ok(hr, seed):
    lid = make_letter(hr, seed)
    assert hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"]}).status_code == 409
    r = hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"], "dry_run": True})
    assert r.status_code == 200 and r.json()["status"] == "dry_run" and r.json()["results"][0]["ok"] is True


def test_email_send_results_and_letter_state(hr, admin, seed, factory):
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    r = hr.post("/email/send", json={"letter_id": lid, "recipients": ["A@x.test", "b@x.test"], "cc": ["c@x.test"]}).json()
    assert r["status"] == "sent" and [x["recipient"] for x in r["results"]] == ["a@x.test", "b@x.test"]
    m = factory.sender.sent[0]
    assert list(m.to) == ["a@x.test", "b@x.test"] and list(m.cc) == ["c@x.test"] and m.attachments[0][1][:2] == b"PK"
    assert factory.built[-1][:2] == ("sender", "smtp") and factory.built[-1][2]["password"] == "pw-secret-1"
    assert hr.get("/letters").json()["items"][0]["state"] == "sent"
    msgs = hr.get("/messages").json()
    assert msgs["total"] == 1 and msgs["items"][0]["status"] == "sent"


def test_email_idempotent_retry_never_double_sends(hr, admin, seed, factory):
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    body = {"letter_id": lid, "recipients": ["a@x.test", "b@x.test"], "idempotency_key": "retry-key-0001"}
    first = hr.post("/email/send", json=body).json()
    again = hr.post("/email/send", json=body).json()
    assert first["replayed"] is False and again["replayed"] is True and again["id"] == first["id"]
    assert len(factory.sender.sent) == 1
    assert hr.post("/email/send", json={**body, "recipients": ["z@x.test"]}).status_code == 409     # same key, different payload
    hdr = hr.post("/email/send", json={"letter_id": lid, "recipients": ["q@x.test"]}, headers={"Idempotency-Key": "hdr-key-000001"}).json()
    assert hr.post("/email/send", json={"letter_id": lid, "recipients": ["q@x.test"]}, headers={"Idempotency-Key": "hdr-key-000001"}).json()["id"] == hdr["id"]
    assert len(factory.sender.sent) == 2
    assert hr.get("/messages").json()["total"] == 2


def test_email_partial_failure_retry_sends_only_failed(hr, admin, seed, factory):
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    factory.sender.fail = {"b@x.test"}
    body = {"letter_id": lid, "recipients": ["a@x.test", "b@x.test"], "idempotency_key": "partial-key-01"}
    r1 = hr.post("/email/send", json=body).json()
    assert r1["status"] == "partial" and [x["ok"] for x in r1["results"]] == [True, False]
    factory.sender.fail = set()
    r2 = hr.post("/email/send", json=body).json()
    assert r2["status"] == "sent" and all(x["ok"] for x in r2["results"])
    assert [list(m.to) for m in factory.sender.sent] == [["a@x.test", "b@x.test"], ["b@x.test"]]
    assert hr.post("/email/send", json=body).json()["replayed"] is True


def test_email_sender_crash_is_recorded_sanitized_and_retryable(hr, admin, seed, factory):
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    factory.sender.boom = True
    body = {"letter_id": lid, "recipients": ["a@x.test"], "idempotency_key": "boom-key-00001"}
    r = hr.post("/email/send", json=body).json()
    assert r["status"] == "failed" and "hunter2" not in str(r)
    factory.sender.boom = False
    assert hr.post("/email/send", json=body).json()["status"] == "sent"


def test_email_pending_key_conflicts(hr, admin, seed, sf):
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    with sf() as s:
        s.add(MessageLog(idempotency_key="busy-key-00001", letter_id=lid, recipients=["a@x.test"], status="pending"))
        s.commit()
    assert hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"], "idempotency_key": "busy-key-00001"}).status_code == 409


def test_email_template_mode_and_dry_run_key_separate(hr, admin, seed, factory):
    connect_smtp(admin)
    r = hr.post("/email/send", json={"template": "level3_request", "recipients": ["a@x.test"], "subject": "Hi",
                                     "fields": {"Ftitle": "", "Fname": "", "En_title": "", "Reporter__Name": "", "Summary": "", "link": ""}})
    assert r.status_code == 200 and factory.sender.sent[0].subject == "Hi"
    assert hr.post("/email/send", json={"template": "level3_request", "recipients": ["a@x.test"], "fields": {}}).status_code == 422
    lid = make_letter(hr, seed)
    k = "shared-key-0001"
    d = hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"], "dry_run": True, "idempotency_key": k}).json()
    real = hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"], "idempotency_key": k}).json()
    assert d["status"] == "dry_run" and real["status"] == "sent" and real["replayed"] is False


def test_email_channel_selection(hr, admin, seed, factory):
    assert admin.put("/connectors/graph", json={"config": {"tenant_id": "t", "client_id": "c", "client_secret": "s3cr3t-graph", "sender": "a@b.test"}}).status_code == 200
    connect_smtp(admin)
    lid = make_letter(hr, seed)
    hr.post("/email/send", json={"letter_id": lid, "recipients": ["a@x.test"]})
    assert factory.built[-1][1] == "graph"
    hr.post("/email/send", json={"letter_id": lid, "recipients": ["b@x.test"], "channel": "smtp"})
    assert factory.built[-1][1] == "smtp"


# ---- letterhead constants: settings > templates/letter_defaults.json; clear 422 when missing -------
def test_company_fields_fall_back_to_defaults_file_and_settings_win(hr, admin, seed, factory):
    assign_all(hr, seed)
    hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]})
    f = factory.renderer.calls[-1][1]
    assert f["company_economic_code"] == "0000-TEST" and f["company_address"] == "Sample Street 1"
    assert f["signer_name"] == "Talent Team"
    admin.put("/automation/settings", json={"company_address": "Settings Street 9"})
    hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]})
    f = factory.renderer.calls[-1][1]
    assert f["company_address"] == "Settings Street 9" and f["company_national_id"] == "1111"
    hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "extra": {"company_address": "Per Request"}})
    assert factory.renderer.calls[-1][1]["company_address"] == "Per Request"


def test_missing_company_fields_give_clear_422(hr, seed, settings, app):
    import os
    os.remove(os.path.join(settings.templates_dir, "letter_defaults.json"))
    assign_all(hr, seed)
    for path in ("/letters", "/letters/preview"):
        r = hr.post(path, json={"kind": "institute_letter", "run_id": seed["run_id"]})
        e = r.json()["error"]
        assert r.status_code == 422 and e["code"] == "validation"
        assert set(e["fields"]) == {"company_economic_code", "company_national_id", "company_postal_code", "company_address"}
        assert "letter_defaults.json" in e["message"]
    r = hr.post("/letters", json={"kind": "settlement_letter", "run_id": seed["run_id"]})
    assert r.status_code == 422 and list(r.json()["error"]["fields"]) == ["addressee"]
    assert hr.post("/letters", json={"kind": "settlement_letter", "run_id": seed["run_id"], "extra": {"addressee": "X"}}).status_code == 201


def test_bad_defaults_file_is_ignored(hr, seed, settings):
    import os
    p = os.path.join(settings.templates_dir, "letter_defaults.json")
    open(p, "w").write("{not json")
    assign_all(hr, seed)
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).status_code == 422
    open(p, "w").write("[1,2]")
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"]}).status_code == 422


def test_renderer_missing_field_error_maps_to_422_fields(hr, seed, factory, monkeypatch):
    class MissingFieldError(ValueError):
        def __init__(self, fields):
            self.fields = fields
            super().__init__("missing")

    assign_all(hr, seed)
    monkeypatch.setattr(factory.renderer, "render", lambda *a, **k: (_ for _ in ()).throw(MissingFieldError(["Summary", "participants[2].name"])))
    for path in ("/letters", "/letters/preview"):
        r = hr.post(path, json={"kind": "institute_letter", "run_id": seed["run_id"]})
        assert r.status_code == 422 and r.json()["error"]["fields"] == {"Summary": "الزامی است", "participants[2].name": "الزامی است"}
