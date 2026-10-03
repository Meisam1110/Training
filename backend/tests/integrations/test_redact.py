import logging

from app.integrations.redact import REDACTED, RedactingFilter, config_secrets, is_secret_key, redact_mapping, redact_text, sanitize_error


def test_redact_text_patterns_and_values():
    s = "Authorization: Bearer abcdef123456 password=hunter22 client_secret: \"zzz999\" Set-Cookie: sid=abc; Path=/"
    out = redact_text(s, ["hunter22"])
    for leak in ("abcdef123456", "hunter22", "zzz999", "sid=abc"):
        assert leak not in out
    assert REDACTED in out
    assert redact_text("plain text") == "plain text"


def test_mapping_and_keys():
    m = {"host": "h", "password": "p", "client_secret": "s", "token_url": "u", "empty_secret": ""}
    r = redact_mapping(m)
    assert r["host"] == "h" and r["password"] == REDACTED and r["client_secret"] == REDACTED
    assert r["empty_secret"] == ""
    assert is_secret_key("Access_Token") and not is_secret_key("host")
    assert sorted(config_secrets(m)) == ["p", "s", "u"]


def test_logging_filter_and_sanitize_error(caplog):
    lg = logging.getLogger("redact-test")
    lg.addFilter(RedactingFilter(["topsecret"]))
    with caplog.at_level(logging.INFO, logger="redact-test"):
        lg.info("login with %s ok", "topsecret")
    assert "topsecret" not in caplog.text
    e = sanitize_error(ValueError("bad token=abc123 for topsecret"), ["topsecret"])
    assert "abc123" not in e and "topsecret" not in e and e.startswith("ValueError")
    assert sanitize_error(RuntimeError()) == "RuntimeError"
