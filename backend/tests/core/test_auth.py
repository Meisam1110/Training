import pytest
from fastapi.testclient import TestClient

from app.main import bootstrap_admin
from app.models import AuditLog, LoginAttempt, User
from tests.core.conftest import PW, Api


def test_login_sets_httponly_lax_cookie_and_csrf(app, users):
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "hr", "password": PW})
    assert r.status_code == 200
    sc = r.headers["set-cookie"].lower()
    assert "tms_session=" in sc and "httponly" in sc and "samesite=lax" in sc
    assert r.headers["x-csrf-token"] == r.json()["csrf_token"]
    assert r.json()["user"]["role"] == "hr" and "password" not in r.text
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == "hr"


def test_login_wrong_password_generic_and_unknown_user_same(app, users):
    c = TestClient(app)
    a = c.post("/api/v1/auth/login", json={"username": "hr", "password": "nope-nope-nope"})
    b = c.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    assert a.json()["error"]["code"] == "unauthorized"


def test_login_validation(app, users):
    r = TestClient(app).post("/api/v1/auth/login", json={"username": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert "password" in r.json()["error"]["fields"]


def test_lockout_after_failures_then_correct_password_still_blocked(app, users, sf):
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/v1/auth/login", json={"username": "viewer", "password": "bad-bad-bad-bad"}).status_code == 401
    r = c.post("/api/v1/auth/login", json={"username": "viewer", "password": PW})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers
    with sf() as s:
        assert s.query(LoginAttempt).filter_by(username="viewer", ok=False).count() == 5   # blocked attempts not recorded


def test_lockout_applies_to_unknown_usernames_too(app, users):
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/v1/auth/login", json={"username": "ghost", "password": "x" * 12})
    assert c.post("/api/v1/auth/login", json={"username": "ghost", "password": "x" * 12}).status_code == 429


def test_success_resets_failure_count(app, users):
    c = TestClient(app)
    for _ in range(4):
        c.post("/api/v1/auth/login", json={"username": "viewer", "password": "bad-bad-bad-bad"})
    assert c.post("/api/v1/auth/login", json={"username": "viewer", "password": PW}).status_code == 200
    for _ in range(4):
        assert c.post("/api/v1/auth/login", json={"username": "viewer", "password": "bad-bad-bad-bad"}).status_code == 401


def test_ip_rate_limit(app, users, settings):
    from dataclasses import replace
    app.state.settings = replace(settings, login_ip_max_failures=3, login_max_failures=99)
    c = TestClient(app)
    for i in range(3):
        c.post("/api/v1/auth/login", json={"username": f"u{i}", "password": "x" * 12})
    assert c.post("/api/v1/auth/login", json={"username": "viewer", "password": PW}).status_code == 429


def test_unauthenticated_is_401(app, users):
    r = TestClient(app).get("/api/v1/courses")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_csrf_required_for_unsafe_methods(app, users):
    a = Api(app, "hr")
    r = a.post("/courses", json={"name": "X"}, csrf=False)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = a.post("/courses", json={"name": "X"}, headers={"X-CSRF-Token": "wrong"}, csrf=False)
    assert r.status_code == 403
    assert a.post("/courses", json={"name": "X"}).status_code == 201
    assert a.get("/courses", csrf=False).status_code == 200      # safe methods need no token


def test_origin_check_blocks_cross_site_post(app, users):
    a = Api(app, "hr")
    r = a.post("/courses", json={"name": "Y"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = a.post("/courses", json={"name": "Y"}, headers={"Origin": "http://testserver"})
    assert r.status_code == 201


def test_logout_revokes_session(app, users):
    a = Api(app, "hr")
    assert a.post("/auth/logout").status_code == 200
    assert a.get("/auth/me").status_code == 401


def test_inactive_user_session_rejected(app, users, sf):
    a = Api(app, "viewer")
    with sf() as s:
        s.query(User).filter_by(username="viewer").one().is_active = False
        s.commit()
    assert a.get("/auth/me").status_code == 401


def test_password_hash_is_scrypt_and_verifies():
    from app.auth.passwords import hash_password, verify_password
    h = hash_password("abc-DEF-12345", n=2**4)
    assert h.startswith("scrypt$16$") and verify_password("abc-DEF-12345", h) and not verify_password("x", h)
    assert not verify_password("x", "garbage")


def test_bootstrap_admin_only_on_empty_table(sf, settings):
    from dataclasses import replace
    s2 = replace(settings, bootstrap_admin_user="root", bootstrap_admin_password="Zx9-long-bootstrap-pw")
    assert bootstrap_admin(sf, s2) is True
    assert bootstrap_admin(sf, s2) is False
    with sf() as s:
        assert s.query(User).count() == 1
    assert bootstrap_admin(sf, settings) is False


def test_login_audited_without_password(app, users, sf):
    Api(app, "hr")
    TestClient(app).post("/api/v1/auth/login", json={"username": "hr", "password": "wrong-wrong-1"})
    with sf() as s:
        rows = s.query(AuditLog).all()
        assert {"login", "login.failed"} <= {r.action for r in rows}
        assert "wrong-wrong-1" not in str([r.detail for r in rows])


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health(app, path):
    r = TestClient(app).get(path)
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ready_ok_and_pending_migrations(app, sf):
    c = TestClient(app)
    assert c.get("/ready").json()["migrations"] is True
    with sf() as s:
        s.execute(__import__("sqlalchemy").text("UPDATE alembic_version SET version_num='old'"))
        s.commit()
    r = c.get("/ready")
    assert r.status_code == 503 and r.json()["status"] == "migrations_pending"


def test_security_headers_and_no_cors_by_default(app):
    r = TestClient(app).get("/health", headers={"Origin": "https://evil.example"})
    h = r.headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "access-control-allow-origin" not in h and "strict-transport-security" not in h
    assert h["cache-control"] == "no-store" and h["x-request-id"]


def test_hsts_and_cors_when_configured(settings, factory):
    from dataclasses import replace

    from app.main import create_app
    a = create_app(replace(settings, hsts=True, cors_origins=("https://ui.example",)))
    r = TestClient(a).get("/health", headers={"Origin": "https://ui.example"})
    assert "max-age" in r.headers["strict-transport-security"]
    assert r.headers["access-control-allow-origin"] == "https://ui.example"


def test_request_body_limit(app, users):
    a = Api(app, "hr")
    r = a.post("/courses", content=b"x" * 2_000_000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "validation"


def test_unknown_route_and_method_use_envelope(app):
    c = TestClient(app)
    assert c.get("/api/v1/nope").json()["error"]["code"] == "not_found"
    assert c.delete("/api/v1/courses").status_code == 405


def test_unhandled_error_is_generic_500_envelope(app, users):
    @app.get("/api/v1/_boom")
    def boom():
        raise RuntimeError("row for national code 0012345678")

    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/_boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "upstream"
    assert "0012345678" not in r.text
