import sqlite3
from datetime import date

import pytest

from app import demo
from app.models import Employee, Enrollment, User

REAL_DATA_MARKERS = ("irancell", "mtn")


def test_demo_is_deterministic_and_synthetic(sf, settings):
    today = date(2030, 6, 1)
    a = demo.generate(sf, employees=40, seed=7, today=today)
    assert a["employees"] == 40 and a["runs"] == 6 and a["enrollments"] > 40
    with sf() as s:
        emps = s.query(Employee).order_by(Employee.emp_no).all()
        sig = [(e.emp_no, e.national_code, e.mobile, e.email) for e in emps]
        assert all(e.national_code.startswith("999") and e.mobile.startswith("0990") and e.email.endswith("@example.test") for e in emps)
        blob = " ".join(map(str, sig)).lower()
        assert not any(m in blob for m in REAL_DATA_MARKERS)
        n_en = s.query(Enrollment).count()
        assert any(x.current_status == "Evaluation Level 3" for x in s.query(Enrollment))
    again = demo.generate(sf, employees=40, seed=7, today=today)                # idempotent
    assert again == {"employees": 0, "runs": 0, "enrollments": 0}
    with sf() as s:
        assert s.query(Enrollment).count() == n_en


@pytest.mark.sqlite_only
def test_demo_same_seed_same_data(tmp_path, template_db):
    import shutil

    from app import db as dbm
    sigs = []
    for i in range(2):
        p = tmp_path / f"d{i}.db"
        shutil.copy(template_db, p)
        sf = dbm.make_session_factory(dbm.make_engine(f"sqlite:///{p}"))
        demo.generate(sf, employees=25, seed=3, today=date(2030, 1, 1))
        with sf() as s:
            sigs.append([(e.emp_no, e.national_code, e.division, e.first_name_en) for e in s.query(Employee).order_by(Employee.emp_no)])
    assert sigs[0] == sigs[1]


def test_demo_users_random_password_not_in_code(sf, monkeypatch):
    monkeypatch.delenv("TMS_DEMO_PASSWORD", raising=False)
    made = demo.ensure_users(sf)
    assert set(made) == {"demo_admin", "demo_hr", "demo_viewer"} and len(set(made.values())) == 1 and len(next(iter(made.values()))) >= 16
    assert demo.ensure_users(sf) == {}
    with sf() as s:
        assert s.query(User).count() == 3


@pytest.mark.sqlite_only
def test_demo_cli_and_production_refusal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("TMS_STORAGE_DIR", str(tmp_path / "st"))
    monkeypatch.delenv("TMS_DATA_KEY", raising=False)
    monkeypatch.setenv("TMS_ENV", "development")
    assert demo.main(["--employees", "10", "--reset"]) == 0
    assert "demo data" in capsys.readouterr().out
    assert sqlite3.connect(tmp_path / "cli.db").execute("select count(*) from employees").fetchone()[0] == 10
    monkeypatch.setenv("TMS_ENV", "production")
    assert demo.main([]) == 2
