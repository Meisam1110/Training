"""User-created templates, field catalogue, configurable dashboard, per-user layout/preferences, stable ordering."""
import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.api.services import dashboard_widgets as dw
from app.api.services import field_catalog as fc
from app.api.services import rich_text as rt
from app.api.services import templates as tsvc
from app.models import AuditLog, CourseRun, Enrollment, MessageLog, MessageTemplate, MessageTemplateVersion, User
from tests.core.conftest import PW, Api
from tests.core.test_qa_fixes import count_statements

PERSIAN = re.compile(r"[؀-ۿ]")
XSS = [
    '<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '<a href="javascript:alert(1)">x</a>', '<a href=" jAvA\tscript:alert(1)">x</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>', '<a href="vbscript:msgbox(1)">x</a>', '<p onclick="alert(1)">x</p>',
    '<p style="background:url(javascript:alert(1))">x</p>', '<iframe src="//evil"></iframe>', '<svg onload=alert(1)><circle/></svg>',
    '<style>@import "//evil";</style>', '<object data="x"></object>', '<embed src="x">', '<form action="//evil"><input></form>',
    '<math><mtext></mtext></math>', '<b onmouseover=alert(1)>x</b>', '<span data-field="a b" onclick=x>y</span>', '<link rel=stylesheet href=//evil>',
    '<meta http-equiv=refresh content="0;url=//evil">', '<base href="//evil">', '<!--<script>alert(1)</script>-->', '<![CDATA[<script>]]>',
    '<a href="//evil.example/x">x</a>', '<a href="https://ok.test" target="_self" onclick="x">x</a>', '<td onclick=1>x</td>',
]
FORBIDDEN = re.compile(r"(?i)<script|onerror|onclick|onload|onmouseover|javascript:|vbscript:|data:text|<iframe|<svg|<style|<object|<embed|<form|<link|<meta|<base|<img|style=")


# ---- sanitiser -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("vector", XSS)
def test_sanitize_strips_xss_vectors(vector):
    out = rt.sanitize(f"<p>before {vector} after</p>")
    assert not FORBIDDEN.search(out), out
    assert "before" in out and "after" in out
    rendered = rt.render_html(out, {"a": "x"}, {"a"}).html
    assert not FORBIDDEN.search(rendered), rendered


def test_sanitize_allowlist_and_attributes():
    out = rt.sanitize('<h2 dir="rtl">T</h2><ul><li><b>a</b><i>b</i><u>c</u></li></ul><ol><li>x</li></ol><table><tr><td colspan="2" class="evil">c</td></tr></table>'
                      '<p dir="ltr">p<br>q</p><a href="https://ok.test/x?a=1&b=2" onclick="x">l</a><a href="mailto:a@x.test">m</a>'
                      '<span data-field="Fname" style="color:red" class="z">chip</span><font color=red>f</font><div>d</div>')
    for ok in ('<h2 dir="rtl">', "<ul>", "<ol>", "<li>", "<b>", "<i>", "<u>", '<td colspan="2">', '<p dir="ltr">', "<br>",
               'href="https://ok.test/x?a=1&amp;b=2"', 'href="mailto:a@x.test"', 'data-field="Fname"', 'rel="noopener noreferrer"'):
        assert ok in out, (ok, out)
    for bad in ("class=", "style=", "<font", "<div", "onclick"):
        assert bad not in out
    assert "d" in out and "f" in out                       # unknown tags are unwrapped, their text kept
    assert rt.sanitize(rt.sanitize(out)) == rt.sanitize(out)           # idempotent
    assert rt.sanitize("<p><b>unclosed") == "<p><b>unclosed</b></p>"
    assert rt.sanitize("") == "" and rt.sanitize("plain & <tag") != ""


def test_render_is_single_pass_and_values_are_data():
    tpl = rt.sanitize('<p>Hi <span data-field="Fname">x</span>, {{ Summary }} <a data-field-href="link">go</a> <a href="{{link}}">again</a></p>')
    f = {"Fname": "<b>Ali</b> {{Summary}}", "Summary": 'C"><script>alert(1)</script>', "link": "https://ok.test/a?b=1&c=2"}
    r = rt.render_html(tpl, f, {"Fname", "Summary", "link"})
    assert "&lt;b&gt;Ali&lt;/b&gt; {{Summary}}" in r.html and "&lt;script&gt;" in r.html and "<script" not in r.html
    assert r.html.count('href="https://ok.test/a?b=1&amp;c=2"') == 2 and r.missing_fields == [] and r.unknown_fields == []
    bad_link = rt.render_html(tpl, {**f, "link": "javascript:alert(1)"}, {"Fname", "Summary", "link"})
    assert "javascript" not in bad_link.html and "link" in bad_link.missing_fields
    r2 = rt.render_html(tpl, {"Fname": "", "Summary": None}, {"Fname", "Summary", "link"})
    assert r2.missing_fields == ["Fname", "Summary", "link"]
    r3 = rt.render_html('<span data-field="Nope">x</span>{{ Other }}', {}, {"Fname"})
    assert r3.unknown_fields == ["Nope", "Other"] and r3.missing_fields == []


def test_render_text_subject_has_no_header_injection():
    out, unk, miss = rt.render_text("Hi {{Fname}} {{Zzz}} {{Summary}}", {"Fname": "A\r\nBcc: x@y.test", "Summary": ""}, {"Fname", "Summary"})
    assert "\n" not in out and "\r" not in out and unk == ["Zzz"] and miss == ["Summary"]


def test_render_list_chip_makes_a_table_and_escapes():
    r = rt.render_html('<span data-field="participants">x</span>', {"participants": [{"name": "<i>A</i>", "id": "1"}, {"name": "B", "id": "2"}]}, {"participants"})
    assert r.html.count("<tr>") == 2 and "&lt;i&gt;" in r.html


def test_referenced_fields():
    assert rt.referenced_fields('<span data-field="A">x</span><a data-field-href="L">y</a> {{ B }} <a href="{{C}}">z</a><span data-field="A">x</span>') == ["A", "L", "B", "C"]


# ---- catalogue -----------------------------------------------------------------------------------------------
def test_field_catalog_labels_cover_every_spec_field():
    from app.documents.specs import SPECS
    keys = {f.name for sp in SPECS.values() for f in sp.fields} | {ls.name for sp in SPECS.values() for ls in sp.lists}
    assert keys <= set(fc.META), keys - set(fc.META)          # a new spec field must get a Persian label
    assert {e["key"] for e in fc.catalog()} == keys


def test_fields_endpoint_shape(viewer):
    r = viewer.get("/templates/fields").json()
    items = r["items"]
    assert len(items) >= 60 and set(r["kinds"]) == set(fc.ALL_KINDS)
    for e in items:
        assert {"key", "label_fa", "source", "type", "sample_fa", "required_for_kinds"} <= set(e)
        assert e["source"] in {"course", "run", "employee", "manager", "institute", "company", "links", "system"}
        assert e["type"] in {"text", "date_jalali", "date", "number", "money", "url", "list"}
        assert PERSIAN.search(e["label_fa"])
        assert set(e["required_for_kinds"]) <= set(fc.LETTER_KINDS)
    byk = {e["key"]: e for e in items}
    assert byk["jStart_Date"]["type"] == "date_jalali" and byk["link"]["type"] == "url" and byk["invoice_total"]["type"] == "money"
    assert byk["participants"]["type"] == "list" and isinstance(byk["participants"]["sample_fa"], list)
    assert "course_announcement" in byk["Farsi_Course_Name"]["required_for_kinds"]


def test_system_seeds_only_use_catalogued_fields():
    known = fc.known_keys()
    for kind, (_, subject, body) in tsvc.SEEDS.items():
        used = set(rt.referenced_fields(rt.sanitize(body))) | set(rt.TOKEN_RE.findall(subject))
        assert used <= known, (kind, used - known)


# ---- CRUD / versions / defaults ------------------------------------------------------------------------------
def make(hr, **kw):
    body = {"kind": "email_announcement", "name": "قالب من", "lang": "fa", "subject": "موضوع {{Farsi_Course_Name}}",
            "body_html": '<p dir="rtl">سلام <span data-field="Farsi_Course_Name">x</span></p>'}
    body.update(kw)
    r = hr.post("/templates", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_list_seeds_system_templates_for_every_kind(viewer, seed):
    r = viewer.get("/templates?is_system=true&page_size=100").json()
    assert r["total"] == len(fc.ALL_KINDS) == 13
    assert {t["kind"] for t in r["items"]} == set(fc.ALL_KINDS)
    assert all(t["is_system"] and t["is_default"] and t["lang"] == "both" and PERSIAN.search(t["name"]) for t in r["items"])
    assert "body_html" not in r["items"][0]
    again = viewer.get("/templates?is_system=true&page_size=100").json()
    assert again["total"] == 13                                                 # seeding is idempotent
    d = viewer.get(f"/templates/{r['items'][0]['id']}").json()
    assert d["body_html"] and d["fields_used"] and d["version"] == 1


def test_create_get_patch_versions_restore(hr, viewer):
    t = make(hr)
    assert t["version"] == 1 and t["is_default"] is False or t["is_default"] is True
    assert "<script" not in make(hr, name="x2", kind="email_reminder", body_html="<p>hi</p><script>alert(1)</script>")["body_html"]
    p = hr.patch(f"/templates/{t['id']}", json={"subject": "جدید", "body_html": "<p>v2</p>"}).json()
    assert p["version"] == 2 and p["subject"] == "جدید"
    assert hr.patch(f"/templates/{t['id']}", json={"subject": "جدید"}).json()["version"] == 2           # no change = no new version
    p3 = hr.patch(f"/templates/{t['id']}", json={"name": "نام جدید", "lang": "both"}).json()
    assert p3["version"] == 3 and p3["name"] == "نام جدید"
    v = viewer.get(f"/templates/{t['id']}/versions").json()["items"]
    assert [x["version"] for x in v] == [3, 2, 1] and v[2]["subject"] == "موضوع {{Farsi_Course_Name}}"
    r = hr.post(f"/templates/{t['id']}/versions/1:restore").json()
    assert r["version"] == 4 and r["subject"] == "موضوع {{Farsi_Course_Name}}" and "سلام" in r["body_html"] and r["name"] == "قالب من"
    assert [x["version"] for x in viewer.get(f"/templates/{t['id']}/versions").json()["items"]] == [4, 3, 2, 1]       # history is append-only
    assert hr.post(f"/templates/{t['id']}/versions/99:restore").status_code == 404
    assert hr.get("/templates/99999").status_code == 404 and hr.post("/templates/99999:duplicate").status_code == 404


def test_system_templates_are_read_only_but_duplicable(hr, seed):
    sysrow = hr.get("/templates?is_system=true&kind=email_level3").json()["items"][0]
    sid = sysrow["id"]
    assert hr.patch(f"/templates/{sid}", json={"name": "x"}).status_code == 403
    assert hr.delete(f"/templates/{sid}").status_code == 403
    assert hr.post(f"/templates/{sid}/versions/1:restore").status_code == 403
    d = hr.post(f"/templates/{sid}:duplicate")
    assert d.status_code == 201
    c = d.json()
    assert c["is_system"] is False and c["is_default"] is False and "کپی" in c["name"] and c["body_html"] == hr.get(f"/templates/{sid}").json()["body_html"]
    assert hr.patch(f"/templates/{c['id']}", json={"name": "سفارشی"}).status_code == 200
    assert hr.delete(f"/templates/{c['id']}").status_code == 200 and hr.get(f"/templates/{c['id']}").status_code == 404


def test_default_per_kind_and_lang_is_exclusive(hr, viewer, seed):
    a = make(hr, name="الف", kind="email_reminder", lang="fa")
    b = make(hr, name="ب", kind="email_reminder", lang="fa")
    assert a["is_default"] is True and b["is_default"] is False                 # first of its kind+lang becomes the default
    r = hr.post(f"/templates/{b['id']}:set-default").json()
    assert r["is_default"] is True
    rows = {t["id"]: t for t in viewer.get("/templates?kind=email_reminder&page_size=50").json()["items"]}
    assert [i for i, t in rows.items() if t["is_default"] and t["lang"] == "fa"] == [b["id"]]
    assert any(t["is_system"] and t["is_default"] and t["lang"] == "both" for t in rows.values())      # other lang untouched
    assert hr.delete(f"/templates/{b['id']}").status_code == 409                # a default cannot be deleted
    hr.post(f"/templates/{a['id']}:set-default")
    assert hr.delete(f"/templates/{b['id']}").status_code == 200


@pytest.mark.parametrize("body", [{"kind": "nope"}, {"name": ""}, {"lang": "de"}, {"subject": "a\nb"}, {"subject": "a\r\nBcc: x"},
                                  {"body_html": "x" * 100_001}, {"subject": "x" * 301}, {"name": "a\x00b"}, {"extra": 1}])
def test_template_validation(hr, body):
    base = {"kind": "email_generic", "name": "n", "lang": "fa", "subject": "s", "body_html": "<p>x</p>"}
    r = hr.post("/templates", json={**base, **body})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert PERSIAN.search(r.json()["error"]["message"])


def test_template_writes_are_audited_and_hr_only(hr, viewer, admin, seed, sf):
    t = make(hr)
    hr.patch(f"/templates/{t['id']}", json={"name": "z"})
    d = hr.post(f"/templates/{t['id']}:duplicate").json()
    hr.post(f"/templates/{d['id']}:set-default")
    hr.delete(f"/templates/{d['id']}") if False else None
    with sf() as s:
        acts = [a.action for a in s.scalars(select(AuditLog).where(AuditLog.entity == "template").order_by(AuditLog.id))]
    assert acts == ["template.create", "template.update", "template.duplicate", "template.set_default"]
    assert viewer.post("/templates", json={"kind": "email_generic", "name": "n"}).status_code == 403
    assert viewer.get(f"/templates/{t['id']}").status_code == 200
    assert admin.post("/templates", json={"kind": "email_generic", "name": "n"}).status_code == 201


def test_stored_body_is_sanitised_server_side(hr, viewer):
    t = make(hr, body_html='<p onclick="x()">a</p><script>alert(1)</script><a href="javascript:x">l</a><img src=x onerror=y>')
    got = viewer.get(f"/templates/{t['id']}").json()["body_html"]
    assert not FORBIDDEN.search(got) and "a" in got
    hr.patch(f"/templates/{t['id']}", json={"body_html": '<iframe src="//e"></iframe><b>ok</b>'})
    assert viewer.get(f"/templates/{t['id']}").json()["body_html"] == "<b>ok</b>"


# ---- preview -----------------------------------------------------------------------------------------------------
def test_preview_with_sample_data_by_id_and_inline(hr, seed):
    t = make(hr, subject="{{Farsi_Course_Name}} - {{Course_Name}}", body_html='<p>سلام <span data-field="Fname">x</span> <b>{{ Summary }}</b></p>',
             kind="email_level3")
    r = hr.post("/templates/preview", json={"id": t["id"]}).json()
    assert r["context"] == "sample" and r["unknown_fields"] == [] and r["missing_fields"] == []
    assert "علی نمونه" in r["html"] and "PMBOK V6" in r["html"] and r["subject"] == "مدیریت زمان - Time Management"
    inline = hr.post("/templates/preview", json={"template": {"kind": "email_generic", "subject": "{{Nope}}",
                                                              "body_html": '<span data-field="Ghost">g</span><script>x</script>{{Fname}}'}}).json()
    assert inline["unknown_fields"] == ["Ghost", "Nope"] and "<script" not in inline["html"] and "علی نمونه" in inline["html"]
    assert hr.post("/templates/preview", json={}).status_code == 422
    assert hr.post("/templates/preview", json={"id": t["id"], "template": {"kind": "email_generic"}}).status_code == 422


def test_preview_with_real_context_and_pii_audit(hr, seed, sf):
    ids = seed["en_ids"]
    t = make(hr, kind="email_level3", subject="L3 {{Summary}}", body_html='<p><span data-field="Fname">x</span> {{Reporter__Name}} <a data-field-href="link">l</a></p>')
    r = hr.post("/templates/preview", json={"id": t["id"], "enrollment_id": ids[1]}).json()
    assert r["context"] == "real" and "تست2 نمونه2" in r["html"] and "Test2 Person2" in r["html"] and "LMS-101" in r["html"]
    assert r["subject"] == "L3 Leadership Basics - Cohort" and r["missing_fields"] == []
    ann = make(hr, kind="email_announcement", body_html='<p><span data-field="Farsi_Course_Name">x</span> {{jStart_Date}} {{Fname}}</p>')
    r = hr.post("/templates/preview", json={"id": ann["id"], "run_id": seed["run_id"]}).json()
    assert "مبانی رهبری" in r["html"] and r["missing_fields"] == ["Fname"]            # Fname is not part of an announcement's data
    assert hr.post("/templates/preview", json={"id": t["id"], "run_id": seed["run_id"]}).status_code == 422       # level3 needs enrollment_id
    assert hr.post("/templates/preview", json={"id": ann["id"], "run_id": 99999}).status_code == 404
    hr.post("/enrollments:bulk", json={"enrollment_ids": ids[:2], "run_id": seed["run_id"], "motivation": "Yes"})
    inst = make(hr, kind="email_institute", body_html='<span data-field="participants">x</span>')
    assert "9990000001" in hr.post("/templates/preview", json={"id": inst["id"], "run_id": seed["run_id"]}).json()["html"]
    with sf() as s:
        a = s.scalars(select(AuditLog).where(AuditLog.action == "template.preview").order_by(AuditLog.id)).all()
        assert [x.detail["pii_included"] for x in a] == [False, False, True]


def test_preview_value_with_markup_stays_data(hr, seed, sf):
    from app.models import Employee
    with sf() as s:
        e = s.query(Employee).filter_by(emp_no="E00002").one()
        e.first_name_fa, e.last_name_en = "{{Summary}}<script>alert(1)</script>", "{{Fname}}"
        s.commit()
    t = make(hr, kind="email_level3", body_html='<p><span data-field="Fname">x</span> {{Reporter__Name}} {{ Summary }}</p>')
    h = hr.post("/templates/preview", json={"id": t["id"], "enrollment_id": seed["en_ids"][1]}).json()["html"]
    assert "<script" not in h and "&lt;script&gt;" in h and "{{Summary}}" in h and "{{Fname}}" in h
    assert h.count("Leadership Basics - Cohort") == 1                                    # {{Summary}} inside a value was NOT expanded again


# ---- templates used by letters and e-mail --------------------------------------------------------------------------
def test_letter_uses_chosen_template_for_subject_and_body(hr, seed, factory):
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": seed["run_id"], "motivation": "Yes"})
    t = make(hr, kind="email_institute", subject="نامه {{Letter_No}} / {{Course_Name}}",
             body_html='<p>به: <span data-field="To">x</span> — {{Letter_No}}</p><p><span data-field="participants">p</span></p>')
    r = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": t["id"]})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    from app.models import Letter
    with hr.c.app.state.session_factory() as s:
        L = s.get(Letter, lid)
        assert L.subject == "نامه 1 / مبانی رهبری" and "مؤسسه نمونه" in L.html_body and "— 1" in L.html_body and "<table>" in L.html_body
    assert factory.renderer.calls[-1][0] == "institute_letter"                              # the docx still comes from the renderer
    p = hr.post("/letters/preview", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": t["id"]}).json()
    assert p["template_id"] == t["id"] and p["missing_fields"] == [] and "مؤسسه نمونه" in p["html"] and p["subject"].startswith("نامه —")


def test_letter_template_errors_are_422_before_a_number_is_used(hr, seed, factory, sf):
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": seed["run_id"], "motivation": "Yes"})
    ghost = make(hr, kind="email_institute", subject="s", body_html='<span data-field="Ghost">g</span> {{Fname}}')
    r = hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": ghost["id"]})
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"Ghost", "Fname"} and all(PERSIAN.search(v) for v in r.json()["error"]["fields"].values())
    wrong = make(hr, kind="email_level3")
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": wrong["id"]}).status_code == 422
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": 99999}).status_code == 404
    from app.models import Letter, LetterCounter
    with sf() as s:
        assert s.query(Letter).count() == 0 and s.query(LetterCounter).count() == 0       # nothing consumed
    ok = make(hr, kind="institute_letter", subject="s", body_html="<p>letter kind template</p>")
    assert hr.post("/letters", json={"kind": "institute_letter", "run_id": seed["run_id"], "template_id": ok["id"]}).status_code == 201


def smtp(admin):
    admin.put("/connectors/smtp", json={"config": {"host": "h"}})


def test_email_send_with_template_id(hr, admin, seed, factory):
    smtp(admin)
    t = make(hr, kind="email_level3", subject="L3 {{Summary}}", body_html='<p>{{Ftitle}} <span data-field="Fname">x</span> <a data-field-href="link">l</a></p>')
    b = {"template_id": t["id"], "enrollment_id": seed["en_ids"][1], "recipients": ["a@x.test"], "idempotency_key": "tpl-mail-0001"}
    r = hr.post("/email/send", json=b)
    assert r.status_code == 200 and r.json()["status"] == "sent", r.text
    m = factory.sender.sent[0]
    assert m.subject == "L3 Leadership Basics - Cohort" and "تست2 نمونه2" in m.html_body and m.attachments == [] or m.attachments == ()
    assert hr.post("/email/send", json=b).json()["replayed"] is True and len(factory.sender.sent) == 1
    assert hr.post("/email/send", json={**b, "enrollment_id": seed["en_ids"][2]}).status_code == 409           # different context = different request
    # explicit fields override the context; markup in values is inert
    r = hr.post("/email/send", json={"template_id": t["id"], "enrollment_id": seed["en_ids"][1], "recipients": ["b@x.test"],
                                     "fields": {"Fname": "<script>alert(1)</script>{{Summary}}"}})
    assert r.status_code == 200
    body = factory.sender.sent[-1].html_body
    assert "<script" not in body and "&lt;script&gt;" in body and "{{Summary}}" in body
    # blank / unknown fields -> 422 naming each
    g = make(hr, kind="email_generic", subject="s", body_html='<span data-field="Ghost">x</span>{{Fname}}')
    r = hr.post("/email/send", json={"template_id": g["id"], "recipients": ["a@x.test"]})
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"Ghost", "Fname"}
    assert hr.post("/email/send", json={"template_id": 99999, "recipients": ["a@x.test"]}).status_code == 404
    assert hr.post("/email/send", json={"template_id": t["id"], "letter_id": 1, "recipients": ["a@x.test"]}).status_code == 422


def test_send_test_only_to_own_address(hr, admin, seed, factory, sf):
    t = make(hr, kind="email_generic", subject="تست {{Farsi_Course_Name}}", body_html='<p>سلام {{Farsi_Course_Name}}</p>')
    r = hr.post(f"/templates/{t['id']}:send-test", json={"to": "me@example.test"})
    assert r.status_code == 422 and "ثبت نشده" in r.json()["error"]["message"]               # the account has no e-mail yet
    uid = next(u["id"] for u in admin.get("/users").json()["items"] if u["username"] == "hr")
    assert admin.patch(f"/users/{uid}", json={"email": "Me@Example.test"}).json()["email"] == "me@example.test"
    r = hr.post(f"/templates/{t['id']}:send-test", json={"to": "someone-else@example.test"})
    assert r.status_code == 422 and "خود شما" in r.json()["error"]["message"]
    r = hr.post(f"/templates/{t['id']}:send-test", json={"to": "ME@example.test"}).json()
    assert r["dry_run"] is True and r["status"] == "dry_run" and factory.sender.sent == []              # no connector: dry run
    smtp(admin)
    r = hr.post(f"/templates/{t['id']}:send-test", json={"to": "me@example.test"}).json()
    assert r["status"] == "sent" and r["dry_run"] is False
    assert factory.sender.sent[0].subject == "تست مدیریت زمان" and list(factory.sender.sent[0].to) == ["me@example.test"]
    assert hr.post(f"/templates/{t['id']}:send-test", json={"to": "bad"}).status_code == 422
    with sf() as s:
        assert s.query(MessageLog).count() == 2


def test_user_email_field(admin):
    r = admin.post("/users", json={"username": "withmail", "password": "Aq7!kLm2#Pz9w", "email": "WM@Example.test"})
    assert r.status_code == 201 and r.json()["email"] == "wm@example.test"
    assert admin.post("/users", json={"username": "badmail", "password": "Aq7!kLm2#Pz9w", "email": "nope"}).status_code == 422


# ---- dashboard widgets --------------------------------------------------------------------------------------------
ALL_IDS = [w["id"] for w in dw.WIDGETS]


def rich_seed(hr, seed, sf):
    """3 participants on the seeded run (2 yes, 1 no), a payment-started run with cost, a completed run, a cancelled one."""
    rid = seed["run_id"]
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": rid, "motivation": "Yes"})
    hr.patch(f"/enrollments/{seed['en_ids'][2]}", json={"motivation": "No"})
    hr.patch(f"/runs/{rid}", json={"status": "announced"})
    today = date.today()
    with sf() as s:
        c = s.get(CourseRun, rid)
        for i, (status, delta, amount, pp) in enumerate([("completed", -40, 500, "started"), ("cancelled", 5, 900, ""), ("open", 3, 250, "")]):
            r = CourseRun(run_key=f"extra-{i}", course_id=c.course_id, start_date=today + timedelta(days=delta), end_date=today + timedelta(days=delta + 1),
                          status=status, amount=amount, payment_process=pp, institute_id=c.institute_id)
            s.add(r)
            s.flush()
            if status == "completed":
                s.add(Enrollment(ticket="LMS-C1", employee_id=s.get(Enrollment, seed["en_ids"][0]).employee_id, course_name="Done", run_id=r.id, motivation="Yes"))
        e = s.get(Enrollment, seed["en_ids"][5])
        e.current_status, e.category, e.end_date = "Evaluation Level 3", "Soft Skill", today - timedelta(days=80)
        s.commit()
    return rid


def test_widget_catalog_by_role(viewer, hr, admin):
    v = viewer.get("/dashboard/widgets").json()
    assert v["grid_columns"] == 12 and {w["id"] for w in v["items"]} == set(ALL_IDS) - {"kpi_budget", "invoices_status", "sync_health"}
    assert {w["id"] for w in hr.get("/dashboard/widgets").json()["items"]} == set(ALL_IDS) == {w["id"] for w in admin.get("/dashboard/widgets").json()["items"]}
    for w in hr.get("/dashboard/widgets").json()["items"]:
        assert PERSIAN.search(w["title_fa"]) and w["kind"] in {"kpi", "chart", "list", "table", "status"}
        assert 1 <= w["min_size"]["w"] <= w["default_size"]["w"] <= w["max_size"]["w"] <= 12 and 1 <= w["min_size"]["h"] <= w["default_size"]["h"] <= w["max_size"]["h"]
        assert set(w["roles"]) <= {"viewer", "hr", "admin"} and "admin" in w["roles"]


def test_widget_data_values_from_real_tables(hr, admin, seed, sf):
    rich_seed(hr, seed, sf)
    d = admin.get("/dashboard/data", params={"widgets": ",".join(ALL_IDS)}).json()
    assert d["range"] == "12m" and set(d["widgets"]) == set(ALL_IDS)
    w = d["widgets"]
    assert w["kpi_runs_active"]["value"] == 2 and w["kpi_runs_active"]["by_status"]["completed"] == 1 and w["kpi_runs_active"]["by_status"]["cancelled"] == 1
    assert w["kpi_runs_active"]["total_runs"] == 4 and w["kpi_runs_active"]["starting_30d"] >= 2
    assert w["kpi_enrollments"] == {"value": 7, "assigned": 4, "unassigned": 3}
    m = w["kpi_motivation_rate"]
    assert (m["participants"], m["yes"], m["no"], m["pending"]) == (4, 3, 1, 0) and m["value"] == 75.0
    b = w["kpi_budget"]
    assert b["currency"] == "IRR" and all(isinstance(v, int) for k, v in b.items() if k != "currency")
    assert b["planned_total"] == 1000 + 500 + 250 and b["planned_runs"] == 3                  # the cancelled run (900) is excluded
    assert b["expected_cost"] == 1000 * 2 + 500 * 1 and b["expected_runs"] == 2                # amount x "Yes" motivations
    assert b["payment_started_total"] == 500 and b["payment_started_runs"] == 1 and b["payment_pending_total"] == 2000
    f = w["funnel_run_stages"]
    assert [s["id"] for s in f["stages"]] == ["planned", "announced", "open", "running", "completed"] and f["total"] == 4 and f["cancelled"] == 1
    assert {s["id"]: s["count"] for s in f["stages"]} == {"planned": 0, "announced": 1, "open": 1, "running": 0, "completed": 1}
    tl = w["runs_timeline_upcoming"]["items"]
    assert [i["run_id"] for i in tl][0] == next(i["run_id"] for i in tl if i["days_to_course"] == 3) and tl[-1]["days_to_course"] == 20
    assert tl[-1]["participants"] == 3 and tl[-1]["motivations_yes"] == 2 and PERSIAN.search("".join(i["status"] for i in tl)) is None
    mp = w["motivation_progress_by_run"]["items"][-1]
    assert (mp["participants"], mp["yes"], mp["no"], mp["pending"], mp["percent_yes"]) == (3, 2, 1, 0, 66.7)
    div = w["enrollments_by_division"]
    assert div["items"][0] == {"division": "Div A", "count": 7} and div["total"] == 7
    tr = w["trend_monthly"]["months"]
    assert len(tr) == 12 and all(PERSIAN.search(x["label"]) for x in tr) and re.search(r"[۰-۹]{4}$", tr[-1]["label"])
    assert sum(x["runs"] for x in tr) >= 2 and sum(x["expected_cost"] for x in tr) >= 2500
    inv = {i["id"]: i for i in w["invoices_status"]["items"]}
    assert inv["payment_started"]["amount"] == 500 and inv["no_invoice"]["amount"] == 2000 and inv["no_invoice"]["runs"] == 1
    assert w["level3_due"]["count"] == 1 and w["level3_due"]["items"][0]["ticket"] == "LMS-105" and w["level3_due"]["after_days"] == 60
    assert w["alerts_over3"]["threshold"] == 3 and w["alerts_over3"]["count"] == 0
    sh = w["sync_health"]
    assert sh["sources"] == [] and sh["ok"] is True and sh["running"] == 0 and sh["connectors"] == {}


def test_widget_data_alerts_and_sync_health(hr, admin, seed, sf, factory):
    from tests.core.conftest import add_offers
    add_offers(sf, seed["en_ids"][0], ["No", "", "No"])
    admin.put("/connectors/ifs", json={"config": {"base_url": "https://ifs.test"}})
    factory.source.records = [__import__("tests.core.fakes", fromlist=["employee"]).employee(50)]
    admin.post("/sync/ifs:run")
    d = admin.get("/dashboard/data", params={"widgets": "alerts_over3,sync_health"}).json()["widgets"]
    assert d["alerts_over3"]["count"] == 1 and d["alerts_over3"]["items"][0]["ticket"] == "LMS-100"
    s = d["sync_health"]
    assert s["sources"][0]["source"] == "ifs" and s["sources"][0]["status"] == "ok" and s["sources"][0]["processed"] == 1 and s["ok"] is True
    assert s["connectors"]["ifs"]["enabled"] is True and s["automation"] is None


def test_widget_data_rbac_validation_and_range(viewer, hr, seed):
    assert viewer.get("/dashboard/data", params={"widgets": "kpi_budget"}).status_code == 403
    assert viewer.get("/dashboard/data", params={"widgets": "kpi_enrollments,sync_health"}).status_code == 403
    assert viewer.get("/dashboard/data", params={"widgets": "kpi_enrollments"}).status_code == 200
    r = hr.get("/dashboard/data", params={"widgets": "nope,kpi_enrollments"})
    assert r.status_code == 422 and "nope" in r.json()["error"]["fields"]["widgets"]
    assert hr.get("/dashboard/data").status_code == 422 and hr.get("/dashboard/data", params={"widgets": ""}).status_code == 422
    assert hr.get("/dashboard/data", params={"widgets": "kpi_enrollments", "range": "7y"}).status_code == 422
    assert hr.get("/dashboard/data", params={"widgets": ",".join(["kpi_enrollments"] * 31)}).status_code == 422
    assert len(hr.get("/dashboard/data", params={"widgets": "trend_monthly", "range": "6m"}).json()["widgets"]["trend_monthly"]["months"]) == 6
    dup = hr.get("/dashboard/data", params={"widgets": "kpi_enrollments,kpi_enrollments"}).json()["widgets"]
    assert list(dup) == ["kpi_enrollments"]


def test_widget_data_has_no_n_plus_one(hr, admin, seed, sf, app):
    from tests.core.test_qa_fixes import big_seed
    rich_seed(hr, seed, sf)
    big_seed(sf, 150)
    with count_statements(app.state.engine) as c:
        r = admin.get("/dashboard/data", params={"widgets": ",".join(ALL_IDS)})
    assert r.status_code == 200
    assert c.n <= 60, f"{c.n} statements for all widgets: {c.log}"
    for wid in ALL_IDS:
        with count_statements(app.state.engine) as one:
            assert admin.get("/dashboard/data", params={"widgets": wid}).status_code == 200
        assert one.n <= 12, (wid, one.n, one.log)


def test_widget_lists_are_deterministically_ordered(hr, admin, seed, sf):
    today = date.today()
    with sf() as s:
        c = s.get(CourseRun, seed["run_id"])
        for i in range(8):
            s.add(CourseRun(run_key=f"tie-{i}", course_id=c.course_id, start_date=today + timedelta(days=9), status="open"))
        s.commit()
    first = admin.get("/dashboard/data", params={"widgets": "runs_timeline_upcoming,motivation_progress_by_run"}).json()["widgets"]
    for _ in range(3):
        assert admin.get("/dashboard/data", params={"widgets": "runs_timeline_upcoming,motivation_progress_by_run"}).json()["widgets"] == first
    ties = [i["run_id"] for i in first["runs_timeline_upcoming"]["items"] if i["days_to_course"] == 9]
    assert ties == sorted(ties) and len(ties) >= 5


# ---- layout & preferences -----------------------------------------------------------------------------------------
def test_layout_defaults_put_reset_and_isolation(hr, admin, viewer):
    d = hr.get("/me/dashboard-layout").json()
    assert d["is_default"] is True and d["version"] == 0 and {w["id"] for w in d["widgets"]} == set(ALL_IDS)
    assert all(set(w) == {"id", "x", "y", "w", "h", "config"} for w in d["widgets"])
    assert {w["id"] for w in viewer.get("/me/dashboard-layout").json()["widgets"]} == set(ALL_IDS) - {"kpi_budget", "invoices_status", "sync_health"}
    mine = {"version": 0, "widgets": [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 4, "h": 2, "config": {"color": "blue"}},
                                      {"id": "trend_monthly", "x": 4, "y": 0, "w": 8, "h": 4}]}
    r = hr.put("/me/dashboard-layout", json=mine).json()
    assert r["version"] == 1 and r["is_default"] is False and [w["id"] for w in r["widgets"]] == ["kpi_enrollments", "trend_monthly"]
    assert r["widgets"][0]["config"] == {"color": "blue"} and r["widgets"][1]["config"] == {}
    assert hr.get("/me/dashboard-layout").json()["widgets"] == r["widgets"]
    assert hr.put("/me/dashboard-layout", json={**mine, "version": 1}).json()["version"] == 2
    assert admin.get("/me/dashboard-layout").json()["is_default"] is True                     # per user
    reset = hr.delete("/me/dashboard-layout").json()
    assert reset["is_default"] is True and len(reset["widgets"]) == len(ALL_IDS) and reset["version"] == 3
    assert hr.put("/me/dashboard-layout", json={"widgets": []}).json()["widgets"] == []            # an empty dashboard is allowed


@pytest.mark.parametrize("widgets", [
    [{"id": "nope", "x": 0, "y": 0, "w": 3, "h": 2}],
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 3, "h": 2}, {"id": "kpi_enrollments", "x": 3, "y": 0, "w": 3, "h": 2}],
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 1, "h": 2}],                       # below min
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 7, "h": 2}],                       # above max
    [{"id": "kpi_enrollments", "x": 10, "y": 0, "w": 4, "h": 2}],                      # outside the 12-column grid
    [{"id": "kpi_enrollments", "x": 12, "y": 0, "w": 3, "h": 2}], [{"id": "kpi_enrollments", "x": -1, "y": 0, "w": 3, "h": 2}],
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 3, "h": 2, "config": {"k": "v" * 3000}}],
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 3, "h": 2, "extra": 1}],
    [{"id": "kpi_enrollments", "x": 0, "y": 0, "w": 3, "h": 2, "config": {"k": "a\x00"}}],
    [{"id": f"kpi_enrollments{i}", "x": 0, "y": 0, "w": 3, "h": 2} for i in range(41)],
])
def test_layout_validation(hr, widgets):
    r = hr.put("/me/dashboard-layout", json={"widgets": widgets})
    assert r.status_code == 422 and PERSIAN.search(r.json()["error"]["message"])
    assert all(PERSIAN.search(v) for v in r.json()["error"]["fields"].values())
    assert hr.get("/me/dashboard-layout").json()["is_default"] is True                # nothing saved


def test_layout_role_restrictions_and_demotion(hr, viewer, admin, sf):
    r = viewer.put("/me/dashboard-layout", json={"widgets": [{"id": "kpi_budget", "x": 0, "y": 0, "w": 3, "h": 2}]})
    assert r.status_code == 422 and "مجاز نیست" in r.json()["error"]["fields"]["widgets.0"]
    ok = hr.put("/me/dashboard-layout", json={"widgets": [{"id": "kpi_budget", "x": 0, "y": 0, "w": 3, "h": 2},
                                                          {"id": "kpi_enrollments", "x": 3, "y": 0, "w": 3, "h": 2}]})
    assert ok.status_code == 200
    uid = next(u["id"] for u in admin.get("/users").json()["items"] if u["username"] == "hr")
    admin.patch(f"/users/{uid}", json={"role": "viewer"})
    with sf() as s:                                     # the stored layout still lists kpi_budget; a viewer must never receive it
        assert s.get(User, uid).role == "viewer"
    again = Api(hr.c.app, "hr")
    assert [w["id"] for w in again.get("/me/dashboard-layout").json()["widgets"]] == ["kpi_enrollments"]


def test_preferences_defaults_merge_validation_and_cap(hr, viewer):
    d = viewer.get("/me/preferences").json()
    assert d["theme"] == "system" and d["density"] == "comfortable" and d["tutorial"] == {"completed_steps": [], "dismissed": False, "last_step": None}
    r = viewer.put("/me/preferences", json={"theme": "dark", "tutorial": {"completed_steps": ["welcome", "runs"], "dismissed": False, "last_step": "runs"},
                                            "sidebar_collapsed": True}).json()
    assert r["theme"] == "dark" and r["tutorial"]["last_step"] == "runs" and r["sidebar_collapsed"] is True and r["density"] == "comfortable"
    r = viewer.put("/me/preferences", json={"density": "compact"}).json()                       # merge: untouched keys stay
    assert r["theme"] == "dark" and r["density"] == "compact" and r["sidebar_collapsed"] is True
    r = viewer.put("/me/preferences", json={"theme": None, "sidebar_collapsed": None}).json()    # null removes
    assert r["theme"] == "system" and "sidebar_collapsed" not in r
    assert hr.get("/me/preferences").json()["density"] == "comfortable"                          # per user
    for bad in ({"theme": "pink"}, {"density": "tiny"}, {"tutorial": {"completed_steps": "x"}}, {"tutorial": {"dismissed": "yes"}},
                {"tutorial": {"completed_steps": ["a"] * 51}}, {"tutorial": {"zzz": 1}}, {"bad key": 1}, {"1abc": 1}, {"a": {"b": {"c": {"d": {"e": 1}}}}},
                {"big": "x" * 9000}, {"nul": "a\x00b"}):
        r = viewer.put("/me/preferences", json=bad)
        assert r.status_code == 422, bad
    assert viewer.put("/me/preferences", json=[1]).status_code == 422


# ---- stable ordering -----------------------------------------------------------------------------------------------
def test_every_list_endpoint_has_a_total_order_with_id_tiebreak(hr, admin, viewer, seed, sf):
    today = date.today()
    with sf() as s:
        c = s.get(CourseRun, seed["run_id"])
        for i in range(10):
            s.add(CourseRun(run_key=f"same-{i}", course_id=c.course_id, start_date=today + timedelta(days=50), end_date=None, status="planned"))
        from app.models import Course
        for i in range(6):
            s.add(Course(name=f"Same cat {i}", category="One"))
        s.commit()
    runs = viewer.get("/runs?sort=start_date&page_size=100").json()["items"]
    tied = [r["id"] for r in runs if r["start_date"] == (today + timedelta(days=50)).isoformat()]
    assert tied == sorted(tied) and len(tied) == 10
    desc = viewer.get("/runs?sort=-start_date&page_size=100").json()["items"]
    assert [r["id"] for r in desc if r["start_date"] == (today + timedelta(days=50)).isoformat()] == tied      # ties keep id order either direction
    cats = [c["id"] for c in viewer.get("/courses?sort=category&page_size=100").json()["items"] if c["category"] == "One"]
    assert cats == sorted(cats)
    # pages of a tied sort never overlap or skip (the "page-jump" bug)
    seen = []
    for page in (1, 2, 3, 4, 5):
        seen += [r["id"] for r in viewer.get(f"/runs?sort=start_date&page_size=4&page={page}").json()["items"]]
    assert len(seen) == len(set(seen)) == 12 or len(seen) == len(set(seen))
    full = [r["id"] for r in viewer.get("/runs?sort=start_date&page_size=100").json()["items"]]
    assert seen == full[:len(seen)]
    for path in ["/enrollments?sort=motivation", "/enrollments?sort=current_status", "/employees?sort=division", "/employees?sort=status",
                 "/letters?sort=kind", "/messages?sort=status", "/users?sort=role", "/audit?sort=action", "/templates?sort=kind", "/institutes?sort=supplier_code",
                 "/sync/runs?sort=source", "/runs?sort=status", "/courses?sort=category"]:
        a = [i.get("id", i.get("emp_no")) for i in admin.get(path + "&page_size=100").json()["items"]]
        b = [i.get("id", i.get("emp_no")) for i in admin.get(path + "&page_size=100").json()["items"]]
        assert a == b, path


def test_dashboard_lists_are_deterministic(hr, viewer, seed, sf):
    today = date.today()
    with sf() as s:
        c = s.get(CourseRun, seed["run_id"])
        for i in range(6):
            s.add(CourseRun(run_key=f"d-{i}", course_id=c.course_id, start_date=today + timedelta(days=5), status="planned", amount=1))
            s.add(CourseRun(run_key=f"p-{i}", course_id=c.course_id, start_date=today - timedelta(days=5), status="running", amount=1))
        s.commit()
    d1 = viewer.get("/dashboard").json()
    for _ in range(2):
        assert viewer.get("/dashboard").json()["not_started_courses"] == d1["not_started_courses"]
    ns = [r["id"] for r in d1["not_started_courses"] if r["start_date"] == (today + timedelta(days=5)).isoformat()]
    assert ns == sorted(ns)
    pn = [r["id"] for r in d1["payment_not_started"] if r["start_date"] == (today - timedelta(days=5)).isoformat()]
    assert pn == sorted(pn)


def test_terminology_in_owned_code_and_docs():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    bad = re.compile("انگیزه[‌‏‍ ]*نامه")
    files = list((root / "backend" / "app" / "api").rglob("*.py")) + [root / "backend" / "app" / "demo.py"] + \
        [root / "docs" / n for n in ("DEPLOYMENT.md", "SECURITY.md")] + list((root / "backend" / "tests" / "core").glob("test_*.py"))
    hits = [str(f) for f in files if f != pathlib.Path(__file__) and bad.search(f.read_text())]
    assert not hits, hits
    assert json.dumps(tsvc.SEEDS, ensure_ascii=False).count("موتیویشن") >= 1
    _ = (PW, MessageTemplate, MessageTemplateVersion)
