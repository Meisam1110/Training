"""QA fixtures: the REAL app with the REAL integrations (no fakes), scratch SQLite under tmp. Run: pytest qa/tests -o addopts="" -p no:cacheprovider"""
import base64, os, sys, io
from dataclasses import replace
import pytest
BACKEND = "/home/user/training/backend"
sys.path.insert(0, BACKEND)
from fastapi.testclient import TestClient
from app import db as dbm
from app.auth.passwords import hash_password
from app.config import Settings
from app.main import create_app
from app.models import User

PW = "Qa-Strong-Passw0rd-77"

@pytest.fixture()
def app(tmp_path):
    s = Settings(env="test", database_url=f"sqlite:///{tmp_path}/qa.db", data_key=base64.b64encode(bytes(range(9, 41))).decode(),
                 secret_key="qa-test-secret-key-0123456789-abcdefghijklmnopq", storage_dir=str(tmp_path / "storage"),
                 templates_dir="/home/user/training/templates", max_upload_bytes=25 * 1024 * 1024)
    dbm.upgrade_to_head(s.database_url)
    a = create_app(s)
    with a.state.session_factory() as db:
        for role in ("admin", "hr", "viewer"):
            db.add(User(username=f"qa_{role}", role=role, display_name=role, password_hash=hash_password(PW)))
        db.commit()
    return a

class Api:
    def __init__(self, app, user):
        self.c = TestClient(app, base_url="http://testserver")
        r = self.c.post("/api/v1/auth/login", json={"username": user, "password": PW}); assert r.status_code == 200, r.text
        self.h = {"X-CSRF-Token": r.json()["csrf_token"]}
    def get(self, p, **k): return self.c.get("/api/v1" + p, **k)
    def post(self, p, **k): return self.c.post("/api/v1" + p, headers=self.h, **k)
    def put(self, p, **k): return self.c.put("/api/v1" + p, headers=self.h, **k)
    def patch(self, p, **k): return self.c.patch("/api/v1" + p, headers=self.h, **k)

@pytest.fixture()
def hr(app): return Api(app, "qa_hr")
@pytest.fixture()
def admin(app): return Api(app, "qa_admin")

def workbook_bytes(build):
    import tempfile
    sys.path.insert(0, "/home/user/training/qa")
    import synth
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as f:
        build(synth, f.name); return open(f.name, "rb").read()

@pytest.fixture()
def seeded(app, hr, admin):
    """20 synthetic employees, 30 IDP requests, 3 runs."""
    data = workbook_bytes(lambda synth, p: synth.build(p, n_emp=20, n_idp=30, edge=False))
    r = hr.post("/import/legacy-workbook", files={"file": ("a.xlsx", data)}); assert r.status_code == 200, r.text
    admin.put("/automation/settings", json={"company_economic_code": "1", "company_national_id": "2", "company_postal_code": "3", "company_address": "A",
                                            "settlement_addressee": "Fin", "letter_signer_name": "S"})
    return {"data": data}
