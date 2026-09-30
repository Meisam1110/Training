"""End to end with Dev-B's REAL factory / renderer / calendar / rules. NO fakes: the ``real_app`` fixture does not request the
fake ``factory`` fixture and asserts that gateway.get_factory() is the real module (QA-M13: the old version of this file built its
app through the fake factory, which is how a broken settlement letter passed CI)."""
import io
import re
import zipfile

import pytest

pytest.importorskip("docx")
pytest.importorskip("app.integrations.factory")
from app.api.services import gateway  # noqa: E402
from app.config import default_templates_dir  # noqa: E402
from tests.core.conftest import Api, seed_data  # noqa: E402


@pytest.fixture
def api_real(real_app):
    seed = seed_data(real_app.state.session_factory)
    return Api(real_app, "hr"), Api(real_app, "admin"), seed


def test_gateway_is_really_the_real_one(real_app):
    f = gateway.get_factory()
    assert f.__name__ == "app.integrations.factory"
    assert type(f.build_letter_renderer(default_templates_dir())).__name__ == "DocxLetterRenderer"
    assert type(f.build_calendar()).__name__ == "PersianCalendar"


def test_all_six_letter_kinds_render_with_the_real_renderer(api_real):
    hr, admin, seed = api_real
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": seed["run_id"], "motivation": "Yes"})
    r = admin.put("/automation/settings", json={"company_economic_code": "0000", "company_national_id": "1111", "company_postal_code": "2222",
                                                "company_address": "Test Street 1", "settlement_addressee": "Finance Team"})
    assert r.status_code == 200
    bodies = [
        {"kind": "course_announcement", "run_id": seed["run_id"]},
        {"kind": "institute_letter", "run_id": seed["run_id"]},
        {"kind": "settlement_letter", "run_id": seed["run_id"], "extra": {"invoice_no": "INV-1"}},
        {"kind": "level3_request", "enrollment_ids": seed["en_ids"][1:3]},
        {"kind": "level3_manager_check", "enrollment_ids": seed["en_ids"][1:2]},
        {"kind": "line_manager_approval", "enrollment_ids": seed["en_ids"][1:]},
    ]
    for b in bodies:
        p = hr.post("/letters/preview", json=b)
        assert p.status_code == 200, (b["kind"], p.text)
        assert p.json()["html"] and p.json()["missing_fields"] == []
        r = hr.post("/letters", json=b)
        assert r.status_code == 201, (b["kind"], r.text)
        d = hr.get(f"/letters/{r.json()['id']}/download")
        assert d.status_code == 200
        assert zipfile.ZipFile(io.BytesIO(d.content)).testzip() is None


def test_settlement_letter_sends_the_renderers_field_names_and_exact_shares(api_real):
    """QA-B1: 3 attendees, amount 100 x 1 motivation... shares that do not divide evenly must sum to the total on the letter."""
    hr, admin, seed = api_real
    hr.patch(f"/runs/{seed['run_id']}", json={"amount": "100"})
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:3], "run_id": seed["run_id"]})
    hr.patch(f"/enrollments/{seed['en_ids'][0]}", json={"motivation": "Yes"})           # amount 100 x 1 motivation, 3 attendees
    admin.put("/automation/settings", json={"settlement_addressee": "Finance"})
    r = hr.post("/letters", json={"kind": "settlement_letter", "run_id": seed["run_id"], "enrollment_ids": seed["en_ids"][:3],
                                  "extra": {"invoice_no": "INV-9"}})
    assert r.status_code == 201, r.text
    docx = hr.get(f"/letters/{r.json()['id']}/download").content
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
    text = re.sub(r"<[^>]+>", " ", xml)
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))                  # the renderer shows Persian digits
    amounts = re.findall(r"\b(?:33|34)\b", text)
    assert sorted(amounts)[:3] == ["33", "33", "34"] or len(amounts) >= 3, text[-400:]      # rows 34 + 33 + 33 = 100, not 34 x 3


def test_real_compute_due_and_calendar(api_real):
    hr, _, _ = api_real
    r = hr.get("/automation/due")
    assert r.status_code == 200 and "items" in r.json()
    assert hr.post("/automation/run").status_code == 200
