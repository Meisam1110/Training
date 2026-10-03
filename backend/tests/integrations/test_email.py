import base64
import email as stdemail
import email.policy
import json
import shutil
import subprocess

import httpx
import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword

from app.contracts import OutgoingEmail, SendResult
from app.integrations.email import GraphSender, InMemoryIdempotencyStore, MessageValidationError, SmtpSender
from app.integrations.email.common import RateLimiter, fingerprint, hash_key, html_to_text

PASSWORD = "smtp-secret-pw-123"


class Handler:
    def __init__(self):
        self.messages = []

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address.startswith("refuse"):
            return "550 no such user"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        self.messages.append((envelope.mail_from, list(envelope.rcpt_tos), envelope.content))
        return "250 OK"


def authenticator(server, session, envelope, mechanism, auth_data):
    ok = isinstance(auth_data, LoginPassword) and auth_data.login == b"user" and auth_data.password == PASSWORD.encode()
    return AuthResult(success=ok)


@pytest.fixture()
def smtpd():
    h = Handler()
    c = Controller(h, hostname="127.0.0.1", port=free_port(), authenticator=authenticator, auth_required=False,
                   auth_require_tls=False)
    c.start()
    yield h, c
    c.stop()


def free_port():
    import socket
    k = socket.socket()
    k.bind(("127.0.0.1", 0))
    p = k.getsockname()[1]
    k.close()
    return p


def cfg(c, **kw):
    d = {"host": "127.0.0.1", "port": c.port, "starttls": False,
         "username": "user", "password": PASSWORD, "from_addr": "tms@example.test", "from_name": "TMS مرکز"}
    d.update(kw)
    return d


def mail(**kw):
    d = dict(to=["a@example.test", "b@example.test"], subject="سلام Test", html_body="<p dir='rtl'>متن <b>x</b></p>",
             cc=["c@example.test"], attachments=[("l.docx", b"PKdata", "application/vnd.x")], idempotency_key="")
    d.update(kw)
    return OutgoingEmail(**d)


def test_smtp_send_and_message_content(smtpd):
    h, c = smtpd
    s = SmtpSender(cfg(c))
    ok, msg = s.test_connection()
    assert ok and "authenticated" in msg
    res = s.send(mail())
    assert [r.recipient for r in res] == ["a@example.test", "b@example.test", "c@example.test"]
    assert all(r.ok and r.message_id for r in res)
    assert len(h.messages) == 2                      # one message per To recipient (QA-L10)
    (frm, rcpts, content), (_, rcpts_b, content_b) = h.messages
    assert frm == "tms@example.test"
    assert set(rcpts) == {"a@example.test", "c@example.test"} and set(rcpts_b) == {"b@example.test", "c@example.test"}
    mb = stdemail.message_from_bytes(content_b, policy=stdemail.policy.default)
    assert "a@example.test" not in str(mb["To"]) and str(mb["To"]) == "b@example.test" and str(mb["Cc"]) == "c@example.test"
    m = stdemail.message_from_bytes(content, policy=stdemail.policy.default)
    assert "=?utf-8?" in m["Subject"].lower() or m["Subject"]
    assert m.get_body(("html",)).get_content().startswith("<p dir='rtl'>")
    assert "متن" in m.get_body(("plain",)).get_content()
    assert [p.get_filename() for p in m.iter_attachments()] == ["l.docx"]


def test_smtp_per_recipient_failure(smtpd):
    h, c = smtpd
    res = SmtpSender(cfg(c)).send(mail(to=["a@example.test", "refuse1@example.test"], cc=[]))
    by = {r.recipient: r for r in res}
    assert by["a@example.test"].ok
    assert not by["refuse1@example.test"].ok and "550" in by["refuse1@example.test"].error
    res = SmtpSender(cfg(c)).send(mail(to=["refuse1@example.test"], cc=[]))
    assert not res[0].ok


def test_smtp_bad_password_sanitized(smtpd):
    h, c = smtpd
    s = SmtpSender(cfg(c, password="wrong-password-abc"))
    ok, msg = s.test_connection()
    assert not ok and "wrong-password-abc" not in msg
    res = s.send(mail())
    assert not any(r.ok for r in res)
    assert all("wrong-password-abc" not in r.error and r.error for r in res)


def test_smtp_connection_refused_error_clean():
    s = SmtpSender({"host": "127.0.0.1", "port": 1, "starttls": False, "password": PASSWORD,
                    "from_addr": "x@example.test"})
    ok, msg = s.test_connection()
    assert not ok and PASSWORD not in msg
    assert all(not r.ok for r in s.send(mail()))


def test_dry_run_sends_nothing(smtpd):
    h, c = smtpd
    res = SmtpSender(cfg(c)).send(mail(), dry_run=True)
    assert all(r.ok and r.message_id == "dry-run" for r in res) and h.messages == []


def test_idempotency_no_double_send_and_partial_retry(smtpd):
    h, c = smtpd
    s = SmtpSender(cfg(c))
    m = mail(to=["a@example.test"], cc=[], idempotency_key="k1")
    assert s.send(m)[0].ok and s.send(m)[0].ok
    assert len(h.messages) == 1
    # partial failure then retry: only the failed recipient is re-attempted
    m2 = mail(to=["a@example.test", "refuse2@example.test"], cc=[], idempotency_key="k2")
    r1 = s.send(m2)
    assert [r.ok for r in r1] == [True, False] and len(h.messages) == 2
    s.send(m2)
    assert len(h.messages) == 2      # refused one produced no delivery, ok one not re-sent
    # a different key sends again
    s.send(mail(to=["a@example.test"], cc=[], idempotency_key="k3"))
    assert len(h.messages) == 3
    # pluggable store
    st = InMemoryIdempotencyStore(max_keys=1)
    st.claim("x", "f", 0.0, 10)
    st.claim("y", "f", 0.0, 10)                      # evicts the oldest key
    assert st.claim("x", "other", 0.0, 10)           # x was evicted -> fresh entry, no conflict


@pytest.mark.parametrize("kw", [
    {"subject": "hi\r\nBcc: evil@example.test"}, {"subject": "a\nb"},
    {"to": ["a@example.test\r\nBcc: e@example.test"]}, {"to": ["not-an-address"]}, {"to": []},
    {"cc": ["x@y\n.test"]}, {"subject": "x" * 1000},
    {"attachments": [("a\r\n.docx", b"1", "application/x")]}, {"attachments": [("a.docx", b"1", "bad")]},
])
def test_header_injection_and_validation(smtpd, kw):
    h, c = smtpd
    res = SmtpSender(cfg(c)).send(mail(**kw))
    assert res and all(not r.ok and r.error for r in res) and h.messages == []
    assert all("\n" not in r.recipient for r in res)


def test_smtp_config_validation():
    with pytest.raises(MessageValidationError):
        SmtpSender({"host": "", "from_addr": "a@b.co"})
    with pytest.raises(MessageValidationError):
        SmtpSender({"host": "h", "from_addr": "bad\r\n@x.co"})
    with pytest.raises(MessageValidationError):
        SmtpSender({"host": "h", "from_addr": "a@b.co", "from_name": "x\r\nBcc: y"})
    assert SmtpSender({"host": "h", "use_ssl": True, "from_addr": "a@b.co"}).port == 465
    assert SmtpSender({"host": "h", "from_addr": "a@b.co"}).port == 587
    assert SmtpSender({"host": "h", "starttls": False, "from_addr": "a@b.co"}).port == 25


def test_rate_limit():
    t = [0.0]
    sl = []
    rl = RateLimiter(60, clock=lambda: t[0], sleep=lambda d: (sl.append(d), t.__setitem__(0, t[0] + d)))
    rl.wait()
    rl.wait()
    rl.wait()
    assert sl == [1.0, 1.0]
    RateLimiter(0).wait()


def test_smtp_rate_limit_used(smtpd):
    h, c = smtpd
    sl = []
    s = SmtpSender(cfg(c, rate_limit_per_min=6000), sleep=sl.append, clock=lambda: 0.0)
    s.send(mail(to=["a@example.test"], cc=[]))
    s.send(mail(to=["b@example.test"], cc=[]))
    assert sl and len(h.messages) == 2


def test_cc_only_promoted(smtpd):
    h, c = smtpd
    s = SmtpSender(cfg(c))
    m = mail(to=["a@example.test"], cc=["b@example.test"], idempotency_key="k9-idempotency")
    assert [r.ok for r in s.send(m)] == [True, True]
    n = len(h.messages)
    assert [r.ok for r in s.send(m)] == [True, True] and len(h.messages) == n       # full replay, nothing sent
    # To already delivered under this key, cc failed earlier: only cc is re-attempted (promoted to To)
    kh = hash_key("k10-idempotency")
    fp = fingerprint(mail(to=["a@example.test"], cc=["b@example.test"], idempotency_key="k10-idempotency"))
    s.store.claim(kh, fp, 0.0, 1.0)
    s.store.complete(kh, {"a@example.test": SendResult("a@example.test", True, "x")})
    res = s.send(mail(to=["a@example.test"], cc=["b@example.test"], idempotency_key="k10-idempotency"))
    assert len(h.messages) == n + 1 and res[-1].recipient == "b@example.test"


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl needed for a test certificate")
def test_starttls(tmp_path):
    import ssl
    key, crt = tmp_path / "k.pem", tmp_path / "c.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, capture_output=True)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(str(crt), str(key))
    h = Handler()
    c = Controller(h, hostname="127.0.0.1", port=free_port(), tls_context=sctx, authenticator=authenticator,
                   auth_required=True)
    c.start()
    try:
        port = c.port
        base = {"host": "127.0.0.1", "port": port, "starttls": True, "username": "user", "password": PASSWORD,
                "from_addr": "tms@example.test"}
        ok, msg = SmtpSender(base).test_connection()      # default verification rejects self-signed cert
        assert not ok and PASSWORD not in msg
        ok, msg = SmtpSender({**base, "ca_bundle": str(crt)}).test_connection()
        assert ok, msg
        assert SmtpSender({**base, "verify_tls": False}).send(mail(to=["a@example.test"], cc=[]))[0].ok
    finally:
        c.stop()


def test_html_to_text():
    assert "A" in html_to_text("<style>x{}</style><p>A</p><br>B &amp; C") and "&" in html_to_text("B &amp; C")


# ------------------------------------------------------------------ Graph against a local fake
class FakeGraph:
    def __init__(self):
        self.sent, self.tokens, self.fail = [], 0, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth2/v2.0/token"):
            body = req.content.decode()
            if "client_secret=good-secret" not in body:
                return httpx.Response(401, json={"error": "invalid_client", "echo": body})
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"tok{self.tokens}", "expires_in": 3600})
        if req.url.path.endswith("/sendMail"):
            if self.fail:
                return httpx.Response(self.fail.pop(0), headers={"Retry-After": "0"})
            if req.headers.get("authorization") != f"Bearer tok{self.tokens}":
                return httpx.Response(401)
            self.sent.append((str(req.url), json.loads(req.content)))
            return httpx.Response(202)
        return httpx.Response(404)


def gcfg(**kw):
    d = {"tenant_id": "tenant-1", "client_id": "cid", "client_secret": "good-secret", "sender": "tms@example.test",
         "authority_url": "http://fake", "graph_url": "http://fake"}
    d.update(kw)
    return d


def test_graph_send_payload():
    f = FakeGraph()
    g = GraphSender(gcfg(), transport=httpx.MockTransport(f))
    ok, _ = g.test_connection()
    assert ok
    res = g.send(mail())
    assert all(r.ok for r in res) and len(res) == 3
    assert len(f.sent) == 2                               # one sendMail per To recipient
    url, body = f.sent[0]
    assert url.endswith("/v1.0/users/tms@example.test/sendMail")
    msg = body["message"]
    assert msg["body"]["contentType"] == "HTML" and len(msg["toRecipients"]) == 1 and len(msg["ccRecipients"]) == 1
    assert [m_["message"]["toRecipients"][0]["emailAddress"]["address"] for _, m_ in f.sent] == ["a@example.test", "b@example.test"]
    assert base64.b64decode(msg["attachments"][0]["contentBytes"]) == b"PKdata"


def test_graph_retry_reauth_dryrun_idempotency():
    f = FakeGraph()
    g = GraphSender(gcfg(), transport=httpx.MockTransport(f), sleep=lambda s: None)
    f.fail = [429, 503]
    m = mail(to=["a@example.test"], idempotency_key="g1", cc=[])
    assert all(r.ok for r in g.send(m)) and len(f.sent) == 1
    g.send(m)
    assert len(f.sent) == 1                                   # idempotent
    g._token = "stale"
    g._expiry = 1e12                      # 401 -> token refresh -> retry
    assert all(r.ok for r in g.send(mail(to=["a@example.test"], idempotency_key="g2", cc=[])))
    assert all(r.message_id == "dry-run" for r in g.send(mail(), dry_run=True))
    f.fail = [500, 500, 500, 500, 500]
    res = g.send(mail(to=["a@example.test"], idempotency_key="g3", cc=[]))
    assert not any(r.ok for r in res) and "500" in res[0].error


def test_graph_bad_secret_not_leaked():
    f = FakeGraph()
    g = GraphSender(gcfg(client_secret="bad-secret-zzz"), transport=httpx.MockTransport(f))
    ok, msg = g.test_connection()
    assert not ok and "bad-secret-zzz" not in msg and "401" in msg
    res = g.send(mail())
    assert not any(r.ok for r in res) and all("bad-secret-zzz" not in r.error for r in res)


def test_graph_validation_and_injection():
    with pytest.raises(MessageValidationError):
        GraphSender(gcfg(tenant_id=""))
    with pytest.raises(MessageValidationError):
        GraphSender(gcfg(tenant_id="a/../b"))
    g = GraphSender(gcfg(), transport=httpx.MockTransport(FakeGraph()))
    assert not any(r.ok for r in g.send(mail(subject="x\r\nBcc: y@example.test")))
