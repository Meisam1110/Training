from __future__ import annotations

import base64
import json
import os
import shutil
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import db as dbm
from app.api.services import gateway
from app.auth.passwords import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Course, CourseRun, Employee, Enrollment, Institute, User
from tests.core import fakes

DATA_KEY = base64.b64encode(bytes(range(7, 39))).decode()
SECRET = "k3j9x-Zq81mVb7Tn2Lp0Wd5Rs6Yc4Hf1Gu8Ae3Ko9Xi2Qw"
PW = "Correct-Horse-9-Battery"
os.environ.setdefault("TMS_ENV", "test")


PG_ADMIN_URL = os.environ.get("TMS_TEST_PG_URL", "")      # e.g. postgresql+psycopg://postgres:pw@localhost:5432/postgres
ON_PG = bool(PG_ADMIN_URL)


def pytest_configure(config):
    config.addinivalue_line("markers", "sqlite_only: test reads the SQLite file / sqlite_master directly; skipped when TMS_TEST_PG_URL is set")


def pytest_collection_modifyitems(config, items):
    if ON_PG:
        skip = pytest.mark.skip(reason="SQLite-specific (PostgreSQL run)")
        for it in items:
            if "sqlite_only" in it.keywords:
                it.add_marker(skip)


def _pg_url(dbname: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(PG_ADMIN_URL).set(database=dbname).render_as_string(hide_password=False)


def _pg_admin():
    from sqlalchemy import create_engine
    return create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def template_db(tmp_path_factory):
    from app.security import crypto
    crypto.configure([base64.b64decode(DATA_KEY)])
    if ON_PG:
        from sqlalchemy import text
        adm = _pg_admin()
        with adm.connect() as c:
            c.execute(text("DROP DATABASE IF EXISTS tms_tpl WITH (FORCE)"))
            c.execute(text("CREATE DATABASE tms_tpl"))
        dbm.upgrade_to_head(_pg_url("tms_tpl"))
        return "tms_tpl"
    d = tmp_path_factory.mktemp("tpl")
    path = d / "tpl.db"
    dbm.upgrade_to_head(f"sqlite:///{path}")
    return path


@pytest.fixture
def settings(tmp_path, template_db):
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    for k in ("course_announcement", "institute_letter", "settlement_letter", "level3_request", "level3_manager_check",
              "line_manager_approval"):
        (tpl / f"{k}.docx").write_bytes(b"PK")          # presence only (/ready); rendering uses the fake renderer
    (tpl / "letter_defaults.json").write_text(json.dumps({
        "company_economic_code": "0000-TEST", "company_national_id": "1111", "company_postal_code": "2222",
        "company_address": "Sample Street 1", "settlement_addressee": "Finance Team", "signer_name": "Talent Team"}))
    name = None
    if ON_PG:
        import uuid

        from sqlalchemy import text
        name = f"tms_t_{uuid.uuid4().hex[:12]}"
        with _pg_admin().connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template_db}"'))
        url = _pg_url(name)
    else:
        db = tmp_path / "t.db"
        shutil.copy(template_db, db)
        url = f"sqlite:///{db}"
    yield Settings(env="test", database_url=url, data_key=DATA_KEY, secret_key=SECRET, storage_dir=str(tmp_path / "data"),
                   templates_dir=str(tmp_path / "tpl"), automation_interval_s=3600, sync_wait_s=30)
    if name:
        from sqlalchemy import text
        with _pg_admin().connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def factory(monkeypatch) -> fakes.FakeFactory:
    f = fakes.FakeFactory()
    monkeypatch.setattr(gateway, "get_factory", lambda: f)
    monkeypatch.setattr(gateway, "compute_due", fakes.fake_compute_due)
    return f


@pytest.fixture
def app(settings, factory):
    a = create_app(settings)
    yield a
    a.state.engine.dispose()


@pytest.fixture
def sf(app):
    return app.state.session_factory


@pytest.fixture
def db(sf):
    with sf() as s:
        yield s


def create_users(sf) -> None:
    with sf() as s:
        for role in ("admin", "hr", "viewer"):
            s.add(User(username=role, role=role, display_name=role, password_hash=hash_password(PW, n=2**4)))
        s.commit()


@pytest.fixture
def users(sf):
    create_users(sf)


class Api:
    """TestClient wrapper that logs in and attaches the CSRF header to unsafe methods."""

    def __init__(self, app, role: str | None):
        self.c = TestClient(app, raise_server_exceptions=False)
        self.csrf = ""
        if role:
            r = self.c.post("/api/v1/auth/login", json={"username": role, "password": PW})
            assert r.status_code == 200, r.text
            self.csrf = r.json()["csrf_token"]

    def req(self, method, url, csrf=True, **kw):
        h = dict(kw.pop("headers", {}) or {})
        if csrf and self.csrf and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            h["X-CSRF-Token"] = self.csrf
        return self.c.request(method, "/api/v1" + url, headers=h, **kw)

    def get(self, url, **kw): return self.req("GET", url, **kw)
    def post(self, url, **kw): return self.req("POST", url, **kw)
    def put(self, url, **kw): return self.req("PUT", url, **kw)
    def patch(self, url, **kw): return self.req("PATCH", url, **kw)
    def delete(self, url, **kw): return self.req("DELETE", url, **kw)


@pytest.fixture
def api(app, users):
    cache: dict = {}

    def get(role: str | None) -> Api:
        if role not in cache:
            cache[role] = Api(app, role)
        return cache[role]

    return get


@pytest.fixture
def admin(api): return api("admin")
@pytest.fixture
def hr(api): return api("hr")
@pytest.fixture
def viewer(api): return api("viewer")


@pytest.fixture
def seed(sf):
    return seed_data(sf)


def seed_data(sf):
    """Synthetic data: 6 employees (E1 manages E2..E6), 1 course, 1 institute, 1 run, 6 enrollments."""
    today = date.today()
    with sf() as s:
        emps = []
        for n in range(1, 7):
            r = fakes.employee(n, supervisor_emp_no="" if n == 1 else "E00001")
            e = Employee(emp_no=r.emp_no, first_name_en=r.first_name_en, last_name_en=r.last_name_en, first_name_fa=r.first_name_fa,
                         last_name_fa=r.last_name_fa, gender=r.gender, email=r.email, mobile=r.mobile, national_code=r.national_code,
                         date_of_birth="1990-01-01", division=r.division, cost_center="CC1", supervisor_emp_no=r.supervisor_emp_no)
            s.add(e)
            emps.append(e)
        inst = Institute(name="Acme Institute", name_fa="مؤسسه نمونه", supplier_code="S-1")
        course = Course(name="Leadership Basics", name_fa="مبانی رهبری", category="Soft Skill")
        s.add_all([inst, course])
        s.flush()
        run = CourseRun(run_key=f"leadership basics|acme institute|{today + timedelta(days=20)}", course_id=course.id,
                        institute_id=inst.id, type="in_person", duration_h=16, start_date=today + timedelta(days=20),
                        end_date=today + timedelta(days=21), days="Sat", time="09:00", sessions=2,
                        deadline=today + timedelta(days=10), amount=1000, section_b="MTC-1",
                        link="https://lms.example.test/course/1")
        s.add(run)
        s.flush()
        ens = []
        for i, e in enumerate(emps):
            en = Enrollment(ticket=f"LMS-{100 + i}", employee_id=e.id, course_name="Leadership Basics - Cohort", category="Soft Skill",
                            current_status="Approved", department="Div A", motivation="Yes" if i < 3 else "")
            s.add(en)
            ens.append(en)
        s.commit()
        return {"run_id": run.id, "course_id": course.id, "emp_ids": [e.id for e in emps], "en_ids": [x.id for x in ens],
                "emp_nos": [e.emp_no for e in emps]}


def add_offers(sf, enrollment_id: int, motivations: list[str], tag: str = "x") -> None:
    """Record that a ticket was offered in len(motivations) other runs (legacy Record rows)."""
    from app.models import EnrollmentOffer
    with sf() as s:
        course = s.query(Course).first()
        for i, m in enumerate(motivations):
            run = CourseRun(run_key=f"{tag}-{enrollment_id}-{i}", course_id=course.id, start_date=date.today() - timedelta(days=200 + i),
                            end_date=date.today() - timedelta(days=199 + i), status="completed")
            s.add(run)
            s.flush()
            s.add(EnrollmentOffer(enrollment_id=enrollment_id, run_id=run.id, offer_key=run.run_key, motivation=m))
        s.commit()


def fake_xlsx_bytes() -> bytes:
    """A structurally valid (but empty) .xlsx zip: passes the upload guard; the fake gateway ignores its content."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


@pytest.fixture
def real_app(settings, monkeypatch):
    """The app wired to Dev-B's REAL factory, renderer, calendar and rules: no fakes, no monkeypatching of gateway."""
    from dataclasses import replace

    from app.config import default_templates_dir
    a = create_app(replace(settings, templates_dir=default_templates_dir()))
    assert not isinstance(gateway.get_factory(), fakes.FakeFactory)
    create_users(a.state.session_factory)
    yield a
    a.state.engine.dispose()
