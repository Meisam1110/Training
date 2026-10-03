import base64
import os
import sqlite3

import pytest
from sqlalchemy import text

from app import db as dbm
from app.audit import AuditImmutableError, record
from app.config import ConfigError, Settings, decode_key, load_settings, weak_password
from app.models import AuditLog, Employee
from app.security import crypto
from app.security.logging import JsonFormatter
from app.security.masking import mask_date, mask_mobile, mask_national_code
from app.security.redact import redact_mapping, scrub

KEY = os.urandom(32)


def test_encryption_round_trip_and_randomized():
    c = crypto.Cipher([KEY])
    a, b = c.encrypt("0012345678", "employee.national_code"), c.encrypt("0012345678", "employee.national_code")
    assert a != b and a.startswith("v1.") and "0012345678" not in a
    assert c.decrypt(a, "employee.national_code") == "0012345678"
    assert c.decrypt_json(c.encrypt_json({"k": "é"}, "x"), "x") == {"k": "é"}


def test_encryption_context_binding_wrong_key_and_tamper():
    c = crypto.Cipher([KEY])
    t = c.encrypt("secret", "employee.mobile")
    with pytest.raises(crypto.DecryptionError):
        c.decrypt(t, "employee.national_code")             # ciphertext moved to another column
    with pytest.raises(crypto.DecryptionError):
        crypto.Cipher([os.urandom(32)]).decrypt(t, "employee.mobile")
    tampered = t[:-2] + ("AA" if not t.endswith("AA") else "BB")
    with pytest.raises(crypto.DecryptionError):
        c.decrypt(tampered, "employee.mobile")
    with pytest.raises(crypto.DecryptionError):
        c.decrypt("plain", "x")
    with pytest.raises(crypto.DecryptionError):
        c.decrypt("v1.!!!", "x")
    with pytest.raises(ValueError):
        crypto.Cipher([])
    with pytest.raises(ValueError):
        crypto.Cipher([b"short"])


def test_key_rotation_previous_key_still_decrypts():
    old, new = os.urandom(32), os.urandom(32)
    t = crypto.Cipher([old]).encrypt("v", "c")
    assert crypto.Cipher([new, old]).decrypt(t, "c") == "v"


@pytest.mark.sqlite_only
def test_pii_and_connector_secrets_encrypted_at_rest(sf, seed, admin, settings):
    admin.put("/connectors/smtp", json={"config": {"host": "smtp.test", "password": "S3cretPw!"}})
    path = settings.database_url.removeprefix("sqlite:///")
    raw = sqlite3.connect(path)
    row = raw.execute("SELECT mobile, national_code, date_of_birth FROM employees WHERE emp_no='E00001'").fetchone()
    assert all(v.startswith("v1.") for v in row)
    assert "9990000001" not in " ".join(row)
    secrets_col = raw.execute("SELECT secrets FROM connector_configs WHERE kind='smtp'").fetchone()[0]
    assert secrets_col.startswith("v1.") and "S3cretPw" not in secrets_col
    with sf() as s:
        assert s.query(Employee).filter_by(emp_no="E00001").one().national_code == "9990000001"


def test_masking_helpers():
    assert mask_national_code("0012345678").endswith("78") and "0012" not in mask_national_code("0012345678")
    assert mask_mobile("09121234567").endswith("67")
    assert mask_national_code("") == "" and mask_national_code("1") == "*" * 8
    assert mask_date("1990-01-01") == "****-**-**" and mask_date(None) == ""


def test_scrub_and_redact():
    s = scrub("fail for a.b@corp.test mobile 09121234567 nc 0012345678 password=hunter2 Bearer abc.def postgres://u:pw@h/db")
    for bad in ("a.b@corp.test", "09121234567", "0012345678", "hunter2", "abc.def", ":pw@"):
        assert bad not in s
    r = redact_mapping({"password": "x", "n": {"national_code": "1", "ok": "user@x.test"}, "l": ["09121234567"]})
    assert r["password"] == "***" and r["n"]["national_code"] == "***" and "user@x.test" not in str(r) and "0912" not in str(r)


def test_json_log_redacts(caplog):
    import logging
    rec = logging.LogRecord("t", logging.INFO, "", 0, "user 09121234567 password=abc", (), None)
    rec.password = "zzz"
    rec.extra_ok = "fine"
    out = JsonFormatter().format(rec)
    assert "09121234567" not in out and "zzz" not in out and "abc" not in out and "fine" in out
    try:
        raise ValueError("row for 0012345678")
    except ValueError:
        import sys
        rec2 = logging.LogRecord("t", logging.ERROR, "", 0, "boom", (), sys.exc_info())
    assert "0012345678" not in JsonFormatter().format(rec2) and "ValueError" in JsonFormatter().format(rec2)


# ---- audit append-only -------------------------------------------------------------------------
def test_audit_orm_guard_blocks_update_and_delete(sf):
    with sf() as s:
        row = record(s, "t.one", actor="tester")
        s.commit()
        row.action = "changed"
        with pytest.raises(AuditImmutableError):
            s.commit()
        s.rollback()
        s.delete(s.get(AuditLog, row.id))
        with pytest.raises(AuditImmutableError):
            s.commit()


def test_audit_db_triggers_block_raw_sql(sf):
    with sf() as s:
        record(s, "t.two", actor="tester")
        s.commit()
        for stmt in ("UPDATE audit_log SET action='x'", "DELETE FROM audit_log"):
            with pytest.raises(Exception, match="append-only"):
                s.execute(text(stmt))
            s.rollback()
        assert s.query(AuditLog).count() >= 1


def test_no_audit_mutation_routes(app):
    from fastapi.routing import APIRoute

    import app.api.routers.admin as admin_mod
    for r in admin_mod.router.routes:
        if isinstance(r, APIRoute) and r.path == "/audit":
            assert r.methods == {"GET"}


# ---- config --------------------------------------------------------------------------------------
GOOD = dict(TMS_ENV="production", TMS_DATA_KEY=base64.b64encode(os.urandom(32)).decode(),
            TMS_SECRET_KEY=base64.urlsafe_b64encode(os.urandom(48)).decode())


def test_production_accepts_strong_config():
    load_settings(GOOD).validate()


@pytest.mark.parametrize("patch,needle", [
    ({"TMS_DATA_KEY": ""}, "TMS_DATA_KEY"),
    ({"TMS_SECRET_KEY": ""}, "TMS_SECRET_KEY"),
    ({"TMS_SECRET_KEY": "changeme-changeme-changeme-changeme-1234"}, "ضعیف"),
    ({"TMS_SECRET_KEY": "short"}, "ضعیف"),
    ({"TMS_DATA_KEY": base64.b64encode(b"\x00" * 32).decode()}, "ضعیف"),
    ({"TMS_BOOTSTRAP_ADMIN_PASSWORD": "abc"}, "گذرواژه"),
    ({"TMS_CORS_ORIGINS": "*"}, "CORS"),
])
def test_production_refuses_weak_config(patch, needle):
    with pytest.raises(ConfigError, match=needle):
        load_settings({**GOOD, **patch}).validate()


def test_bad_key_and_mode_rejected():
    with pytest.raises(ConfigError):
        decode_key("not-a-key")
    with pytest.raises(ConfigError):
        Settings(env="staging").validate()
    with pytest.raises(ConfigError):
        load_settings({"TMS_SESSION_HOURS": "abc"})
    assert decode_key(os.urandom(32).hex()).__len__() == 32


def test_prod_defaults_secure_cookie_and_dev_key_generated(tmp_path):
    assert load_settings(GOOD).cookie_secure is True
    from app.config import ensure_dev_key
    s = ensure_dev_key(Settings(storage_dir=str(tmp_path)))
    assert s.data_key and ensure_dev_key(Settings(storage_dir=str(tmp_path))).data_key == s.data_key
    assert oct((tmp_path / ".dev_data_key").stat().st_mode)[-3:] == "600"


def test_weak_password_rules():
    assert weak_password("short") and weak_password("alicealicealice", "alice") and weak_password("aaaaaaaaaaaaaa")
    assert weak_password("Correct-Horse-9-Battery") is None


# ---- migrations ----------------------------------------------------------------------------------
@pytest.mark.sqlite_only
def test_migration_up_down_up_on_sqlite(tmp_path):
    from alembic import command
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = dbm.alembic_config(url)
    command.upgrade(cfg, "head")
    eng = dbm.make_engine(url)
    tables = {r[0] for r in eng.connect().execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"users", "employees", "course_runs", "enrollments", "letters", "message_logs", "connector_configs",
            "sync_runs", "audit_log", "letter_counters", "leases"} <= tables
    assert dbm.current_revision(eng) == dbm.head_revision()
    triggers = {r[0] for r in eng.connect().execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))}
    assert {"audit_log_no_update", "audit_log_no_delete"} <= triggers
    eng.dispose()
    command.downgrade(cfg, "base")
    eng = dbm.make_engine(url)
    left = {r[0] for r in eng.connect().execute(text("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')"))}
    assert left <= {"alembic_version"}
    eng.dispose()
    command.upgrade(cfg, "head")


@pytest.mark.sqlite_only
def test_models_match_migration(tmp_path):
    """Autogenerate finds no drift between models and the migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import app.models  # noqa: F401
    url = f"sqlite:///{tmp_path / 'd.db'}"
    dbm.upgrade_to_head(url)
    eng = dbm.make_engine(url)
    with eng.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), dbm.Base.metadata)
    eng.dispose()
    assert diff == [], diff


# ---- rekey CLI -----------------------------------------------------------------------------------
def _rotation_setup(settings, seed, admin):
    """DB written under OLD key (the fixtures' key); returns (old_b64, new_b64)."""
    admin.put("/connectors/smtp", json={"config": {"host": "h", "password": "pw-secret-1"}})
    return settings.data_key, base64.b64encode(os.urandom(32)).decode()


def test_targets_cover_every_encrypted_column():
    from app.security import rekey
    assert {(t, c) for t, _, c, _ in rekey.targets()} == {("employees", "mobile"), ("employees", "national_code"),
                                                          ("employees", "date_of_birth"), ("connector_configs", "secrets"),
                                                          ("letters", "html_body")}


@pytest.mark.sqlite_only
def test_rekey_dry_run_then_real_then_idempotent(settings, seed, admin, sf):
    from app.security import rekey
    old, new = _rotation_setup(settings, seed, admin)
    eng = dbm.make_engine(settings.database_url)
    keys = [decode_key(new), decode_key(old)]
    raw = lambda: sqlite3.connect(settings.database_url.removeprefix("sqlite:///")).execute(  # noqa: E731
        "SELECT mobile, national_code, date_of_birth FROM employees ORDER BY id").fetchall()
    before = raw()
    dry = rekey.rekey(eng, keys, dry_run=True)
    assert dry.rekeyed == 6 * 3 + 1 and dry.current == 0 and raw() == before            # nothing written
    real = rekey.rekey(eng, keys, batch=4)
    assert real.rekeyed == 19 and not real.failed and raw() != before
    again = rekey.rekey(eng, keys)
    assert again.rekeyed == 0 and again.current == 19                                    # idempotent
    # now only the NEW key is configured: everything still readable through the ORM
    crypto.configure([decode_key(new)])
    try:
        with sf() as s:
            e = s.query(Employee).filter_by(emp_no="E00001").one()
            assert (e.national_code, e.mobile, e.date_of_birth) == ("9990000001", "09900000001", "1990-01-01")
            from app.models import ConnectorConfig
            assert s.get(ConnectorConfig, "smtp").secrets == {"password": "pw-secret-1"}
    finally:
        crypto.configure([decode_key(old)])


def test_rekey_reports_undecryptable_and_needs_two_keys(settings, seed, admin):
    from app.security import rekey
    old, new = _rotation_setup(settings, seed, admin)
    eng = dbm.make_engine(settings.database_url)
    with pytest.raises(ValueError):
        rekey.rekey(eng, [decode_key(new)])
    stranger = base64.b64encode(os.urandom(32)).decode()
    rep = rekey.rekey(eng, [decode_key(new), decode_key(stranger)])         # old key missing from the list
    assert rep.rekeyed == 0 and len(rep.failed) == 19 and all("id=" in f and "Person" not in f for f in rep.failed)


@pytest.mark.sqlite_only
def test_rekey_cli(settings, seed, admin, monkeypatch, capsys):
    from app.security import rekey
    old, new = _rotation_setup(settings, seed, admin)
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("TMS_STORAGE_DIR", settings.storage_dir)
    monkeypatch.setenv("TMS_DATA_KEY", new)
    monkeypatch.setenv("TMS_DATA_KEY_PREVIOUS", old)
    try:
        assert rekey.main(["--dry-run"]) == 0 and "DRY RUN" in capsys.readouterr().out
        assert rekey.main([]) == 0 and "rekeyed=19" in capsys.readouterr().out
        monkeypatch.delenv("TMS_DATA_KEY_PREVIOUS")
        assert rekey.main([]) == 2 and "TMS_DATA_KEY_PREVIOUS" in capsys.readouterr().err
    finally:
        crypto.configure([decode_key(old)])


def test_rekey_covers_letter_files_and_legacy_plaintext_letter_rows(settings, seed, hr, admin, sf):
    """Encrypted letter files follow the key rotation; a pre-encryption plaintext file / html_body is encrypted by rekey."""
    import pathlib

    from sqlalchemy import text as sql

    from app.security import rekey
    hr.post("/enrollments:bulk", json={"enrollment_ids": seed["en_ids"][:2], "run_id": seed["run_id"], "motivation": "Yes"})
    lid = hr.post("/letters", json={"kind": "course_announcement", "run_id": seed["run_id"]}).json()["id"]
    hr.post("/letters", json={"kind": "course_announcement", "run_id": seed["run_id"]})
    files = sorted(pathlib.Path(settings.storage_dir, "letters").glob("*"))
    assert len(files) == 2 and all(f.read_bytes()[:4] == b"TMS1" for f in files)
    plain = b"PK\x03\x04legacy-docx"
    files[1].write_bytes(plain)                                            # a file written before at-rest encryption
    with sf() as s:
        s.execute(sql("UPDATE letters SET html_body = '<p>legacy</p>' WHERE id = :i"), {"i": lid})
        s.commit()
    old, new = settings.data_key, base64.b64encode(os.urandom(32)).decode()
    eng = dbm.make_engine(settings.database_url)
    keys = [decode_key(new), decode_key(old)]
    dry = rekey.rekey(eng, keys, dry_run=True, storage_dir=pathlib.Path(settings.storage_dir))
    assert files[1].read_bytes() == plain and dry.rekeyed >= 2
    rep = rekey.rekey(eng, keys, storage_dir=pathlib.Path(settings.storage_dir))
    assert not rep.failed and files[1].read_bytes()[:4] == b"TMS1"
    crypto.configure([decode_key(new)])
    try:
        c = crypto.get_cipher()
        assert c.decrypt_bytes(files[0].read_bytes(), "letter.file")[:2] == b"PK"
        assert c.decrypt_bytes(files[1].read_bytes(), "letter.file") == plain
        with sf() as s:
            assert s.get(__import__("app.models", fromlist=["Letter"]).Letter, lid).html_body == "<p>legacy</p>"
        again = rekey.rekey(eng, keys, storage_dir=pathlib.Path(settings.storage_dir))
        assert again.rekeyed == 0
    finally:
        crypto.configure([decode_key(old)])
    with pytest.raises(crypto.DecryptionError):
        c.decrypt_bytes(b"nope", "x")
