from datetime import date, timedelta

import pytest

from app.models import AuditLog, CourseRun, Enrollment


# ---- employees -----------------------------------------------------------------------------------
def test_employee_list_masks_pii_and_paginates_sorts(viewer, seed):
    r = viewer.get("/employees?page=1&page_size=4&sort=-emp_no")
    j = r.json()
    assert r.status_code == 200 and j["total"] == 6 and j["page"] == 1 and j["page_size"] == 4 and len(j["items"]) == 4
    assert [i["emp_no"] for i in j["items"]] == ["E00006", "E00005", "E00004", "E00003"]
    txt = r.text
    assert "9990000" not in txt and "0990000" not in txt
    assert j["items"][0]["national_code"].startswith("********") and j["items"][0]["revealed"] is False
    assert viewer.get("/employees?page=2&page_size=4").json()["items"][0]["emp_no"] == "E00005"


def test_employee_search_and_filters(viewer, seed):
    assert viewer.get("/employees?q=Person3").json()["total"] == 1
    assert viewer.get("/employees?supervisor=E00001").json()["total"] == 5
    assert viewer.get("/employees?status=Active&division=Div A").json()["total"] == 6
    assert viewer.get("/employees?q=9990000001").json()["total"] == 0        # national code is not searchable
    assert viewer.get("/employees?q=%25").json()["total"] == 0               # LIKE wildcards are escaped


@pytest.mark.parametrize("qs", ["page=0", "page_size=0", "page_size=1000", "sort=bogus", "sort=-national_code"])
def test_list_validation(viewer, seed, qs):
    r = viewer.get("/employees?" + qs)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"


def test_reveal_requires_hr_and_is_audited(hr, viewer, admin, seed, sf):
    assert viewer.get("/employees/E00001?reveal=1").status_code == 403
    d = viewer.get("/employees/E00001").json()
    assert d["national_code"].startswith("*") and d["date_of_birth"] == "****-**-**"
    for who in (hr, admin):
        r = who.get("/employees/E00001?reveal=1").json()
        assert r["national_code"] == "9990000001" and r["mobile"] == "09900000001" and r["date_of_birth"] == "1990-01-01"
    with sf() as s:
        rows = s.query(AuditLog).filter_by(action="employee.reveal").all()
        assert len(rows) == 2 and rows[0].entity_id == "E00001"
        assert "9990000001" not in str([r.detail for r in rows])
    assert hr.get("/employees/E00001?reveal=2").status_code == 422
    assert hr.get("/employees/NOPE").status_code == 404


# ---- courses -------------------------------------------------------------------------------------
def test_course_crud_and_validation(hr, viewer, seed):
    r = hr.post("/courses", json={"name": "Negotiation", "name_fa": "مذاکره", "category": "Soft Skill", "default_duration_h": 8})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert hr.post("/courses", json={"name": "Negotiation"}).status_code == 409
    assert hr.post("/courses", json={"name": ""}).status_code == 422
    assert hr.post("/courses", json={"name": "X", "bogus": 1}).status_code == 422
    assert hr.post("/courses", json={"name": "X", "default_duration_h": -1}).status_code == 422
    assert hr.patch(f"/courses/{cid}", json={"category": "Tech", "active": False}).json()["category"] == "Tech"
    assert hr.patch(f"/courses/{cid}", json={"name": "Leadership Basics"}).status_code == 409
    assert viewer.get(f"/courses/{cid}").json()["active"] is False
    assert viewer.get("/courses/9999").status_code == 404
    assert hr.patch("/courses/9999", json={}).status_code == 404
    j = viewer.get("/courses?q=lead&sort=-name").json()
    assert j["total"] == 1 and viewer.get("/courses?active=false").json()["total"] == 1


# ---- runs ----------------------------------------------------------------------------------------
def run_body(seed, **kw):
    base = {"course_id": seed["course_id"], "type": "online", "institute": "Beta Institute", "duration_h": 8,
            "start_date": str(date.today() + timedelta(days=40)), "end_date": str(date.today() + timedelta(days=41)),
            "amount": "2500000", "section_b": "MTC-9"}
    base.update(kw)
    return base


def test_run_create_get_patch_list(hr, viewer, seed):
    r = hr.post("/runs", json=run_body(seed))
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["institute"] == "Beta Institute" and run["days_to_course"] == 40 and run["amount"] == 2500000
    assert hr.post("/runs", json=run_body(seed)).status_code == 409                     # same key
    assert hr.post("/runs", json=run_body(seed, course_id=999)).status_code == 422
    assert hr.post("/runs", json=run_body(seed, end_date=str(date.today()))).status_code == 422
    assert hr.post("/runs", json=run_body(seed, type="hybrid")).status_code == 422
    rid = run["id"]
    p = hr.patch(f"/runs/{rid}", json={"status": "announced", "deadline": str(date.today() + timedelta(days=30)), "institute": "Gamma"})
    assert p.status_code == 200 and p.json()["status"] == "announced" and p.json()["institute"] == "Gamma"
    assert hr.patch(f"/runs/{rid}", json={"end_date": "2000-01-01"}).status_code == 422
    clash = hr.post("/runs", json=run_body(seed, institute="Delta")).json()
    assert hr.patch(f"/runs/{clash['id']}", json={"institute": "Gamma"}).status_code == 409
    assert viewer.get(f"/runs/{rid}").json()["enrollment_count"] == 0
    assert viewer.get("/runs/9999").status_code == 404 and hr.patch("/runs/9999", json={}).status_code == 404
    j = viewer.get("/runs?sort=start_date&page_size=2").json()
    assert j["total"] == 3 and j["items"][0]["id"] == seed["run_id"]
    assert viewer.get("/runs?sort=-start_date").json()["items"][0]["start_date"] > j["items"][0]["start_date"]
    assert viewer.get("/runs?status=announced").json()["total"] == 1
    assert viewer.get("/runs?q=leadership&type=in_person").json()["total"] == 1


def test_run_enrollments_listing(viewer, seed):
    j = viewer.get(f"/runs/{seed['run_id']}/enrollments").json()
    assert j["total"] == 0
    assert viewer.get("/runs/9999/enrollments").status_code == 404


# ---- enrollments ---------------------------------------------------------------------------------
def test_enrollment_patch_and_filters(hr, viewer, seed):
    eid = seed["en_ids"][0]
    r = hr.patch(f"/enrollments/{eid}", json={"motivation": "No", "registration": "Done", "calendar": "Sent", "attendance": "Attended",
                                              "comment": "ok"})
    assert r.status_code == 200 and r.json()["motivation"] == "No" and r.json()["attendance"] == "Attended"
    assert r.json()["link"].endswith("LMS-100")
    assert hr.patch(f"/enrollments/{eid}", json={"motivation": "Maybe"}).status_code == 422
    assert hr.patch("/enrollments/9999", json={}).status_code == 404
    assert hr.patch(f"/enrollments/{eid}", json={"run_id": 9999}).status_code == 422
    assert viewer.get("/enrollments?unassigned=true").json()["total"] == 6
    assert viewer.get("/enrollments?motivation=Yes").json()["total"] == 2
    assert viewer.get("/enrollments?emp_no=E00001").json()["total"] == 1
    assert viewer.get("/enrollments?q=LMS-103&sort=-id").json()["total"] == 1
    assert viewer.get("/enrollments?attendance=Attended").json()["total"] == 1
    assert viewer.get("/enrollments?motivation=Perhaps").status_code == 422


def test_assign_and_overlap_rejection(hr, seed, sf):
    a, b = seed["en_ids"][0], seed["en_ids"][1]
    assert hr.patch(f"/enrollments/{a}", json={"run_id": seed["run_id"]}).json()["run_id"] == seed["run_id"]
    # employee 1 gets a second, overlapping run
    other = hr.post("/runs", json=run_body(seed, start_date=str(date.today() + timedelta(days=21)),
                                           end_date=str(date.today() + timedelta(days=22)))).json()
    with sf() as s:
        s.add(Enrollment(ticket="LMS-900", employee_id=s.get(Enrollment, a).employee_id, course_name="Leadership Basics 2"))
        s.commit()
        extra = s.query(Enrollment).filter_by(ticket="LMS-900").one().id
    r = hr.patch(f"/enrollments/{extra}", json={"run_id": other["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    bulk = hr.post("/enrollments:bulk", json={"enrollment_ids": [extra, b, 99999], "run_id": other["id"], "motivation": "Yes"}).json()
    assert bulk["updated"] == [b] and {f["reason"] for f in bulk["failed"]} == {"conflict", "not_found"}
    assert hr.patch(f"/enrollments/{a}", json={"unassign": True}).json()["run_id"] is None
    assert hr.post("/enrollments:bulk", json={"enrollment_ids": []}).status_code == 422


# ---- candidate search ----------------------------------------------------------------------------
def test_candidate_search_rules(hr, seed, sf):
    run = seed["run_id"]
    ids = seed["en_ids"]
    with sf() as s:
        e = {x.id: x for x in s.query(Enrollment).all()}
        e[ids[1]].attendance_status = "Attended"                         # attendance must be "-"
        e[ids[2]].course_name = "Other Course"                           # name does not match
        e[ids[3]].department = "Another Division"                        # division change
        s.get(type(e[ids[4]].employee), e[ids[4]].employee_id).status = "Terminated"     # non active
        e[ids[5]].current_status = "Evaluation Level 3"
        e[ids[5]].end_date = date.today() - timedelta(days=90)
        # employee 0 already attends an overlapping course -> excluded
        booked = CourseRun(run_key="booked-overlap", course_id=1, start_date=date.today() + timedelta(days=20),
                           end_date=date.today() + timedelta(days=22))
        s.add(booked)
        s.flush()
        s.add(Enrollment(ticket="LMS-777", employee_id=e[ids[0]].employee_id, course_name="Something Else", run_id=booked.id))
        s.commit()
    r = hr.post(f"/runs/{run}/candidates:search", json={}).json()
    tickets = {c["ticket"]: c for c in r["candidates"]}
    assert set(tickets) == {"LMS-103", "LMS-104", "LMS-105"}
    assert tickets["LMS-103"]["flags"] == ["division_change"]
    assert tickets["LMS-104"]["flags"] == ["non_active"]
    assert tickets["LMS-105"]["flags"] == ["level3_eligible"] and tickets["LMS-105"]["flagged"] is False
    assert r["excluded"] == [{"enrollment_id": ids[0], "ticket": "LMS-100", "reason": "date_overlap", "conflicting_ticket": "LMS-777"}]
    only_clean = hr.post(f"/runs/{run}/candidates:search", json={"include_flagged": False}).json()
    assert [c["ticket"] for c in only_clean["candidates"]] == ["LMS-105"]
    assert hr.post(f"/runs/{run}/candidates:search", json={"course_name": "nothing like it"}).json()["total"] == 0
    assert hr.post("/runs/9999/candidates:search", json={}).status_code == 404


def test_ticket_offered_three_times_without_yes_is_flagged(hr, admin, seed, sf):
    from tests.core.conftest import add_offers
    add_offers(sf, seed["en_ids"][0], ["No", "", "No"])          # LMS-100: 3 non-Yes offers -> flagged (>= 3)
    add_offers(sf, seed["en_ids"][1], ["No", "", "Yes"])         # LMS-101: only 2 non-Yes -> not flagged
    c = hr.post(f"/runs/{seed['run_id']}/candidates:search", json={}).json()["candidates"]
    assert "over_motivation_limit" in next(x for x in c if x["ticket"] == "LMS-100")["flags"]
    assert "over_motivation_limit" not in next(x for x in c if x["ticket"] == "LMS-101")["flags"]
    # another employee's tickets do not add up: the count is per ticket, not per person
    assert "over_motivation_limit" not in next(x for x in c if x["ticket"] == "LMS-102")["flags"]
    # threshold is configurable
    assert admin.put("/automation/settings", json={"over3_threshold": 2}).status_code == 200
    c = hr.post(f"/runs/{seed['run_id']}/candidates:search", json={}).json()["candidates"]
    assert "over_motivation_limit" in next(x for x in c if x["ticket"] == "LMS-101")["flags"]


def test_offers_follow_assignment_and_motivation(hr, seed, sf):
    from app.models import EnrollmentOffer
    eid = seed["en_ids"][0]
    hr.patch(f"/enrollments/{eid}", json={"run_id": seed["run_id"]})
    hr.patch(f"/enrollments/{eid}", json={"motivation": "No"})
    other = hr.post("/runs", json=run_body(seed, institute="Zeta", start_date=str(date.today() + timedelta(days=90)),
                                           end_date=str(date.today() + timedelta(days=91)))).json()["id"]
    r = hr.patch(f"/enrollments/{eid}", json={"run_id": other}).json()
    assert r["motivation"] == "" and r["run_id"] == other                      # new offer starts unanswered
    hr.patch(f"/enrollments/{eid}", json={"unassign": True})
    with sf() as s:
        rows = {(o.run_id, o.motivation) for o in s.query(EnrollmentOffer).filter_by(enrollment_id=eid)}
    assert rows == {(seed["run_id"], "No"), (other, "")}


# ---- dashboard -----------------------------------------------------------------------------------
def test_dashboard_lists_and_counts(viewer, hr, seed, sf):
    today = date.today()
    with sf() as s:
        s.query(Enrollment).filter_by(ticket="LMS-105").one().current_status = "Evaluation Level 3"
        en = s.query(Enrollment).filter_by(ticket="LMS-105").one()
        en.end_date = today - timedelta(days=61)
        s.commit()
    from tests.core.conftest import add_offers
    add_offers(sf, seed["en_ids"][0], ["No", "", "No", "Yes"])
    hr.post("/runs", json=run_body(seed, start_date=str(today - timedelta(days=5)), end_date=str(today - timedelta(days=4)), institute="Past"))
    d = viewer.get("/dashboard").json()
    assert set(d) >= {"not_started_courses", "payment_not_started", "over3_motivations", "level3_due", "counts", "last_sync"}
    assert [r["id"] for r in d["not_started_courses"]] == [seed["run_id"]]
    assert len(d["payment_not_started"]) == 1 and d["payment_not_started"][0]["institute"] == "Past"
    assert [x["ticket"] for x in d["over3_motivations"]] == ["LMS-100"] and d["over3_motivations"][0]["non_yes_count"] == 3
    assert len(d["over3_motivations"][0]["run_ids"]) == 3
    assert [x["ticket"] for x in d["level3_due"]] == ["LMS-105"] and d["level3_due"][0]["days_since_end"] == 61
    assert d["counts"]["employees"] == 6 and d["counts"]["level3_due"] == 1 and d["last_sync"] == {"excel": None, "ifs": None}
    assert "national_code" not in str(d)


def test_level3_boundary_is_ge_60_days_in_every_view(viewer, seed, sf):
    """Due ON day end+60 (>=), identically in dashboard, /automation/due and candidate flags (one implementation)."""
    with sf() as s:
        en = s.query(Enrollment).filter_by(ticket="LMS-105").one()
        en.current_status, en.end_date = "Evaluation Level 3", date.today() - timedelta(days=60)
        en2 = s.query(Enrollment).filter_by(ticket="LMS-104").one()
        en2.current_status, en2.end_date = "Evaluation Level 3", date.today() - timedelta(days=59)
        s.commit()
    assert [x["ticket"] for x in viewer.get("/dashboard").json()["level3_due"]] == ["LMS-105"]
    assert [i["enrollment_id"] for i in viewer.get("/automation/due").json()["items"] if i["kind"] == "level3_due"] == [seed["en_ids"][5]]


# ---- users & audit -------------------------------------------------------------------------------
def test_users_create_list_audit(admin, seed):
    r = admin.post("/users", json={"username": "newhr", "password": "Str0ng-Passphrase-1", "role": "hr", "display_name": "N"})
    assert r.status_code == 201 and "password" not in r.text
    assert admin.post("/users", json={"username": "newhr", "password": "Str0ng-Passphrase-1"}).status_code == 409
    assert admin.post("/users", json={"username": "weak1", "password": "short"}).status_code == 422
    assert admin.post("/users", json={"username": "x", "password": "Str0ng-Passphrase-1"}).status_code == 422
    assert admin.post("/users", json={"username": "okuser", "password": "Str0ng-Passphrase-1", "role": "root"}).status_code == 422
    j = admin.get("/users?sort=-username").json()
    assert j["total"] == 4 and j["items"][0]["username"] == "viewer"
    assert admin.get("/users?q=newhr").json()["total"] == 1
    a = admin.get("/audit?action=user.create").json()
    assert a["total"] == 1 and a["items"][0]["actor"] == "admin"
    assert admin.get("/audit?entity=user&actor=admin&sort=ts&q=user").json()["total"] >= 1
    assert admin.get("/audit?since=2999-01-01T00:00:00").json()["total"] == 0
    assert admin.get("/audit?until=2000-01-01T00:00:00").json()["total"] == 0
    assert admin.get("/audit?sort=bogus").status_code == 422


# ---- users PATCH ---------------------------------------------------------------------------------
def uid(admin, name):
    return next(u["id"] for u in admin.get("/users").json()["items"] if u["username"] == name)


def test_user_patch_role_active_and_session_revocation(admin, api, seed):
    viewer_id = uid(admin, "viewer")
    v = api("viewer")
    assert v.get("/auth/me").status_code == 200
    r = admin.patch(f"/users/{viewer_id}", json={"role": "hr", "display_name": "Vee"})
    assert r.status_code == 200 and r.json()["role"] == "hr" and r.json()["display_name"] == "Vee"
    assert v.get("/auth/me").status_code == 401                              # role change revoked the sessions
    from tests.core.conftest import Api
    v2 = Api(v.c.app, "viewer")
    assert v2.post("/courses", json={"name": "AsHr"}).status_code == 201
    assert admin.patch(f"/users/{viewer_id}", json={"is_active": False}).json()["is_active"] is False
    assert v2.get("/auth/me").status_code == 401
    assert v2.c.post("/api/v1/auth/login", json={"username": "viewer", "password": "Correct-Horse-9-Battery"}).status_code == 401


def test_user_patch_password_revokes_sessions_and_validates(admin, api):
    hr_id = uid(admin, "hr")
    h = api("hr")
    assert admin.patch(f"/users/{hr_id}", json={"password": "short"}).status_code == 422
    assert admin.patch(f"/users/{hr_id}", json={"password": "Another-Strong-Pass-42"}).status_code == 200
    assert h.get("/auth/me").status_code == 401
    r = h.c.post("/api/v1/auth/login", json={"username": "hr", "password": "Another-Strong-Pass-42"})
    assert r.status_code == 200 and "password" not in admin.get("/users").text


def test_cannot_remove_last_active_admin(admin):
    me = uid(admin, "admin")
    assert admin.patch(f"/users/{me}", json={"is_active": False}).status_code == 409
    assert admin.patch(f"/users/{me}", json={"role": "hr"}).status_code == 409
    admin.post("/users", json={"username": "admin2", "password": "Str0ng-Passphrase-1", "role": "admin"})
    assert admin.patch(f"/users/{uid(admin, 'admin2')}", json={"role": "viewer"}).status_code == 200      # a second admin exists
    assert admin.patch(f"/users/{me}", json={"role": "admin", "display_name": "x"}).status_code == 200      # no-op on role is fine
    assert admin.patch("/users/9999", json={"role": "hr"}).status_code == 404
    assert admin.patch(f"/users/{me}", json={"role": "root"}).status_code == 422


# ---- institutes ----------------------------------------------------------------------------------
def test_institutes_crud(hr, viewer, seed):
    r = hr.post("/institutes", json={"name": "New Inst", "name_fa": "جدید", "supplier_code": "S-9", "contact_email": "A@X.test"})
    assert r.status_code == 201 and r.json()["contact_email"] == "a@x.test"
    iid = r.json()["id"]
    assert hr.post("/institutes", json={"name": "New Inst"}).status_code == 409
    assert hr.post("/institutes", json={"name": "X", "contact_email": "bad"}).status_code == 422
    assert hr.patch(f"/institutes/{iid}", json={"supplier_code": "S-10"}).json()["supplier_code"] == "S-10"
    assert hr.patch(f"/institutes/{iid}", json={"name": "Acme Institute"}).status_code == 409
    assert hr.patch(f"/institutes/{iid}", json={"contact_email": "nope"}).status_code == 422
    assert hr.patch("/institutes/9999", json={}).status_code == 404
    j = viewer.get("/institutes?q=inst&sort=-name").json()
    assert j["total"] == 2 and j["items"][0]["name"] == "New Inst"


def test_unassigned_idp_requests_do_not_count_as_date_clashes(hr, seed, sf):
    """Legacy compared a run against BOOKED courses; an employee's other pending (unassigned) IDP request with
    overlapping iCare dates is not a clash (QA-M16)."""
    with sf() as s:
        e0 = s.get(Enrollment, seed["en_ids"][0])
        s.add(Enrollment(ticket="LMS-778", employee_id=e0.employee_id, course_name="Something Else",
                         start_date=date.today() + timedelta(days=20), end_date=date.today() + timedelta(days=22)))
        s.commit()
    r = hr.post(f"/runs/{seed['run_id']}/candidates:search", json={}).json()
    assert "LMS-100" in {c["ticket"] for c in r["candidates"]} and r["excluded"] == []
    assert hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={"run_id": seed["run_id"]}).status_code == 200
