import logging
from datetime import datetime, timezone

import httpx
import pytest

from app.integrations.ifs import CircuitOpenError, IfsAuthError, IfsConfig, IfsConfigError, IfsEmployeeSource, IfsUpstreamError
from app.integrations.ifs.client import extract_page, map_employee
from app.integrations.ifs.mock_server import CLIENT_ID, CLIENT_SECRET, PASSWORD, USERNAME, MockIfsServer
from app.integrations.ifs.resilience import CircuitBreaker, backoff_delay

SLEEPS: list[float] = []


@pytest.fixture()
def srv():
    with MockIfsServer() as s:
        yield s


def cfg(srv, mode, **kw):
    base = {"base_url": srv.base_url, "auth_mode": mode, "timeout_s": 5, "backoff_base_s": 0.01,
            "page_size": 10, "allow_private_hosts": True}
    if mode == "oauth2_client_credentials":
        base.update(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_url="/oauth/token")
    elif mode == "basic":
        base.update(username=USERNAME, password=PASSWORD)
    else:
        base.update(username=USERNAME, password=PASSWORD, login_url="/login")
    base.update(kw)
    return base


def mk(srv, mode, **kw):
    SLEEPS.clear()
    return IfsEmployeeSource(cfg(srv, mode, **kw), sleep=SLEEPS.append)


MODES = ["oauth2_client_credentials", "basic", "session_login"]


@pytest.mark.parametrize("mode", MODES)
def test_fetch_all_paginated(srv, mode):
    with mk(srv, mode) as src:
        ok, msg = src.test_connection()
        assert ok and mode in msg
        emps = list(src.fetch_employees())
    assert len(emps) == 25 and emps[0].emp_no == "MOCK0001"
    e = emps[0]
    assert e.first_name_fa == "علی" and e.email == "test1@example.test"
    assert e.mobile == "09350000001" and e.national_code == "0000000001" and e.gender == "male"
    assert emps[9].status == "Terminated" and e.status == "Active"
    assert src.last_report.created == 25 and src.last_report.errors == []


@pytest.mark.parametrize("mode", MODES)
def test_next_link_pagination(srv, mode):
    srv.state.use_next_link = True
    with mk(srv, mode) as src:
        assert len(list(src.fetch_employees())) == 25
    assert srv.state.log.count("GET /PersonInfo") >= 3


def test_delta_server_and_client(srv):
    since = datetime(2024, 6, 1, tzinfo=timezone.utc)
    with mk(srv, "basic") as s1:
        server_side = list(s1.fetch_employees(since))
    with mk(srv, "basic", delta_mode="client") as s2:
        client_side = list(s2.fetch_employees(since))
    assert 0 < len(server_side) < 25
    assert [e.emp_no for e in server_side] == [e.emp_no for e in client_side]
    assert s2.last_report.unchanged == 25 - len(client_side)


def test_oauth_token_cached_refreshed_and_401_retry(srv):
    with mk(srv, "oauth2_client_credentials") as src:
        list(src.fetch_employees())
        list(src.fetch_employees())
        assert srv.state.log.count("POST /oauth/token") == 1        # cached
        srv.state.configure(expire_now=True)                          # server forgets tokens -> 401
        assert len(list(src.fetch_employees())) == 25
        assert srv.state.log.count("POST /oauth/token") == 2 and src.stats["reauth"] == 1


def test_oauth_refresh_before_expiry(srv):
    srv.state.token_ttl = 20                                         # < 30s skew -> always refresh
    with mk(srv, "oauth2_client_credentials") as src:
        list(src.fetch_employees())
        list(src.fetch_employees())
    assert srv.state.log.count("POST /oauth/token") >= 2


def test_session_relogin_on_expiry(srv):
    with mk(srv, "session_login") as src:
        list(src.fetch_employees())
        srv.state.configure(expire_now=True)
        assert len(list(src.fetch_employees())) == 25
        assert srv.state.log.count("POST /login") == 2


def test_bad_credentials(srv):
    for mode, over in (("oauth2_client_credentials", {"client_secret": "wrong-secret-xyz"}),
                       ("basic", {"password": "wrong-pass-xyz"}), ("session_login", {"password": "wrong-pass-xyz"})):
        with mk(srv, mode, **over) as src:
            ok, msg = src.test_connection()
            assert not ok and "wrong-" not in msg
            with pytest.raises(IfsAuthError):
                list(src.fetch_employees())


def test_backoff_on_429_and_500(srv):
    srv.state.fail_429, srv.state.fail_500 = 2, 1
    with mk(srv, "basic") as src:
        assert len(list(src.fetch_employees())) == 25
        assert src.stats["retries"] == 3 and len(SLEEPS) == 3


def test_retries_exhausted_and_circuit_breaker(srv):
    srv.state.fail_500 = 10_000
    with mk(srv, "basic", max_retries=1, breaker_threshold=2, breaker_cooldown_s=1000) as src:
        for _ in range(2):
            with pytest.raises(IfsUpstreamError):
                list(src.fetch_employees())
        n = len(srv.state.log)
        with pytest.raises(CircuitOpenError):
            list(src.fetch_employees())
        assert len(srv.state.log) == n                              # no call made while open
        ok, msg = src.test_connection()
        assert not ok and "circuit" in msg.lower()


def test_transport_errors_retry(monkeypatch):
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectError("boom")
    src = IfsEmployeeSource({"base_url": "http://x.test", "auth_mode": "basic", "username": "u", "password": "p",
                             "max_retries": 2}, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    ok, msg = src.test_connection()
    assert not ok and "ConnectError" in msg and len(calls) == 3


def test_retry_after_honoured():
    n = {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"value": []})
    sl = []
    src = IfsEmployeeSource({"base_url": "http://x.test", "auth_mode": "basic", "username": "u", "password": "p"},
                            transport=httpx.MockTransport(handler), sleep=sl.append, rand=lambda: 0)
    assert list(src.fetch_employees()) == [] and sl == [7.0]


def test_secrets_never_in_logs_or_errors(srv, caplog):
    caplog.set_level(logging.DEBUG)
    secret = "S3cr3t-Value-Do-Not-Leak"
    texts = []
    for mode, over in (("oauth2_client_credentials", {"client_secret": secret}),
                       ("basic", {"password": secret}), ("session_login", {"password": secret})):
        with mk(srv, mode, **over) as src:
            texts.append(src.test_connection()[1])
            try:
                list(src.fetch_employees())
            except Exception as e:  # noqa: BLE001
                texts.append(str(e) + repr(e))
                texts.append(str(src.last_report.errors))
    # good credentials as well: token must not leak
    with mk(srv, "oauth2_client_credentials") as src:
        list(src.fetch_employees())
        tok = src._token
        assert tok
    srv.state.fail_500 = 100
    with mk(srv, "oauth2_client_credentials", max_retries=0) as src:
        try:
            list(src.fetch_employees())
        except Exception as e:  # noqa: BLE001
            texts.append(str(e))
    blob = caplog.text + "\n".join(texts)
    assert secret not in blob and CLIENT_SECRET not in blob and PASSWORD not in blob and tok not in blob


def test_pagination_link_other_host_refused():
    def handler(req):
        return httpx.Response(200, json={"value": [], "@odata.nextLink": "http://evil.test/steal"})
    src = IfsEmployeeSource({"base_url": "http://x.test", "auth_mode": "basic", "username": "u", "password": "p"},
                            transport=httpx.MockTransport(handler))
    with pytest.raises(IfsUpstreamError, match="different host"):
        list(src.fetch_employees())


def test_pagination_loop_and_bad_shapes():
    def loop(req):
        return httpx.Response(200, json={"value": [{}], "@odata.nextLink": "http://x.test/same"})
    mk_ = lambda h: IfsEmployeeSource({"base_url": "http://x.test", "auth_mode": "basic", "username": "u",  # noqa: E731
                                       "password": "p"}, transport=httpx.MockTransport(h))
    with pytest.raises(IfsUpstreamError, match="loop"):
        list(mk_(loop).fetch_employees())
    with pytest.raises(IfsUpstreamError, match="non-JSON"):
        list(mk_(lambda r: httpx.Response(200, text="<html>")).fetch_employees())
    with pytest.raises(IfsUpstreamError, match="shape"):
        list(mk_(lambda r: httpx.Response(200, json={"x": 1})).fetch_employees())
    with pytest.raises(IfsUpstreamError, match="404"):
        list(mk_(lambda r: httpx.Response(404)).fetch_employees())
    ok, msg = mk_(lambda r: httpx.Response(404)).test_connection()
    assert not ok and "employees_path" in msg


def test_extract_page_shapes():
    assert extract_page([{"a": 1}]) == ([{"a": 1}], None)
    assert extract_page({"d": {"results": [1], "__next": "n"}}) == ([1], "n")
    assert extract_page({"items": [1]}) == ([1], None)


def test_field_map_override_and_missing_required():
    c = IfsConfig.from_dict({"base_url": "https://ifs.test", "auth_mode": "basic", "username": "u", "password": "p",
                             "field_map": {"emp_no": "Custom.Id", "email": ["Mail"]}})
    rec = {"Custom": {"id": " x9 "}, "FirstName": "A", "LastName": "B", "Mail": "Q@X.Y", "Gender": "F",
           "EmployeeStatus": "Inactive"}
    e = map_employee(rec, c)
    assert e.emp_no == "X9" and e.email == "q@x.y" and e.gender == "female" and e.status == "Inactive"
    assert map_employee({"FirstName": "A"}, c) is None


def test_skipped_records_reported_without_values():
    def h(req):
        return httpx.Response(200, json={"value": [{"FirstName": "Secretname"}, "junk"]})
    src = IfsEmployeeSource({"base_url": "http://x.test", "auth_mode": "basic", "username": "u", "password": "p"},
                            transport=httpx.MockTransport(h))
    assert list(src.fetch_employees()) == []
    assert src.last_report.skipped == 2 and "Secretname" not in str(src.last_report.errors)


@pytest.mark.parametrize("bad,msg", [
    ({"base_url": "ftp://x", "auth_mode": "basic"}, "base_url"),
    ({"base_url": "https://u:p@x.test", "auth_mode": "basic"}, "embedded"),
    ({"base_url": "https://x.test", "auth_mode": "magic"}, "auth_mode"),
    ({"base_url": "https://x.test", "auth_mode": "basic"}, "missing"),
    ({"base_url": "https://x.test", "auth_mode": "basic", "username": "u", "password": "p",
      "field_map": {"nope": "x"}}, "unknown target"),
    ({"base_url": "https://x.test", "auth_mode": "basic", "username": "u", "password": "p",
      "delta_mode": "x"}, "delta_mode"),
    ({"base_url": "https://x.test", "auth_mode": "basic", "username": "u", "password": "p",
      "page_size": 0}, "page_size"),
    ({"base_url": "https://x.test", "auth_mode": "basic", "username": "u", "password": "p",
      "timeout_s": "abc"}, "numeric"),
    ({"base_url": "https:///x", "auth_mode": "basic"}, "host"),
])
def test_config_validation(bad, msg):
    with pytest.raises(IfsConfigError, match=msg):
        IfsConfig.from_dict(bad)


def test_tls_verify_default_and_disable(caplog):
    c = IfsConfig.from_dict({"base_url": "https://x.test", "auth_mode": "basic", "username": "u", "password": "p"})
    assert c.verify_tls is True
    c2 = IfsConfig.from_dict({"base_url": "https://x.test", "auth_mode": "basic", "username": "u",
                              "password": "p", "verify_tls": "false"})
    assert c2.verify_tls is False
    with caplog.at_level(logging.WARNING):
        IfsEmployeeSource(c2).close()
    assert "TLS verification is DISABLED" in caplog.text


def test_breaker_and_backoff_units():
    t = [0.0]
    b = CircuitBreaker(2, 10, clock=lambda: t[0])
    assert b.allow() and b.state == "closed"
    b.failure()
    b.failure()
    assert b.state == "open" and not b.allow()
    t[0] = 11
    assert b.state == "half-open" and b.allow() and not b.allow()   # single probe
    b.failure()
    assert b.state == "open"
    t[0] = 25
    assert b.allow()
    b.success()
    assert b.state == "closed"
    assert backoff_delay(0, 1, 30, lambda: 0) == 0.5 and backoff_delay(0, 1, 30, lambda: 1) == 1
    assert backoff_delay(10, 1, 30, lambda: 1) == 30
