"""Runtime configuration, read once from the environment.

Every knob is an environment variable prefixed ``TMS_`` (plus ``DATABASE_URL``). Production
mode refuses to start with a weak or missing secret -- see :func:`Settings.validate`.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import os
import re
import secrets
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

_WEAK_WORDS = ("change", "example", "secret", "password", "default", "test", "tms", "admin", "12345")


class ConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe for the chosen mode."""


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(v: str | None, default: int) -> int:
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        raise ConfigError(f"مقدار عددی نامعتبر: {v!r}") from None


def _list(v: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (v or "").split(",") if x.strip())


def decode_key(raw: str) -> bytes:
    """A data key is 32 random bytes, base64 (standard or URL-safe) or 64 hex chars."""
    raw = raw.strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        return bytes.fromhex(raw)
    try:
        pad = "=" * (-len(raw) % 4)
        data = base64.urlsafe_b64decode(raw + pad)
    except (binascii.Error, ValueError):
        raise ConfigError("TMS_DATA_KEY باید ۳۲ بایت (base64 یا hex) باشد") from None
    if len(data) != 32:
        raise ConfigError("TMS_DATA_KEY باید دقیقاً ۳۲ بایت باشد (openssl rand -base64 32)")
    return data


def _weak_secret(s: str) -> bool:
    low = s.lower()
    return len(s) < 32 or len(set(s)) < 8 or any(w in low for w in _WEAK_WORDS)


def _weak_key(k: bytes) -> bool:
    return len(set(k)) < 8


_COMMON = ("password", "passw0rd", "admin", "administrator", "welcome", "qwerty", "letmein", "iloveyou", "changeme", "secret",
           "abc123", "iranian", "irancell", "training", "tms", "test", "default", "master", "login")


def _has_run(pw: str, n: int = 6) -> bool:
    """ascending/descending run of digits or letters (123456, 987654, abcdef) of length >= n."""
    for seq in (pw.lower(),):
        run_up = run_dn = 1
        for x, y in zip(seq, seq[1:], strict=False):
            run_up = run_up + 1 if ord(y) - ord(x) == 1 else 1
            run_dn = run_dn + 1 if ord(x) - ord(y) == 1 else 1
            if max(run_up, run_dn) >= n:
                return True
    return False


def weak_password(pw: str, username: str = "") -> str | None:
    """Return a reason (fa) when ``pw`` is too weak for an account, else None.
    Rules: >= 12 chars, >= 8 distinct chars, at least 3 of {lower, upper, digit, symbol}, no username, no common word
    (password, admin, welcome ...), no 6-long ascending/descending run (123456, abcdef), no 4+ repeated char."""
    if len(pw) < 12:
        return "گذرواژه باید حداقل ۱۲ نویسه باشد"
    if username and username.lower() in pw.lower():
        return "گذرواژه نباید شامل نام کاربری باشد"
    if len(set(pw)) < 8:
        return "گذرواژه بیش از حد ساده است (نویسه‌های متمایز کم)"
    classes = sum(bool(re.search(p, pw)) for p in ("[a-z]", "[A-Z]", "[0-9]", r"[^A-Za-z0-9]"))
    if classes < 3:
        return "گذرواژه باید ترکیبی از حداقل سه نوع نویسه (حروف کوچک، بزرگ، عدد، نماد) باشد"
    low = pw.lower()
    if any(w in low for w in _COMMON):
        return "گذرواژه شامل کلمهٔ رایج و قابل حدس است"
    if _has_run(pw) or re.search(r"(.)\1{3,}", pw):
        return "گذرواژه شامل الگوی ساده (دنبالهٔ اعداد/حروف یا تکرار) است"
    return None


REQUIRED_TEMPLATES = ("course_announcement", "institute_letter", "settlement_letter", "level3_request",
                      "level3_manager_check", "line_manager_approval")


def default_templates_dir() -> str:
    """<repo>/templates next to backend/ (dev, CI) or /app/templates (image: app package lives in /app/app).
    Independent of the working directory. TMS_TEMPLATES_DIR overrides."""
    here = Path(__file__).resolve()
    for base in (here.parents[1], here.parents[2]):
        if (base / "templates").is_dir():
            return str(base / "templates")
    return str(here.parents[2] / "templates")


@dataclass(frozen=True)
class Settings:
    env: str = "development"                  # development | test | production
    database_url: str = "sqlite:///./tms-dev.db"
    data_key: str = ""                        # TMS_DATA_KEY
    data_key_previous: tuple[str, ...] = ()   # TMS_DATA_KEY_PREVIOUS (decrypt only)
    secret_key: str = ""                      # TMS_SECRET_KEY (pepper for session tokens)
    bootstrap_admin_user: str = ""
    bootstrap_admin_password: str = ""
    cookie_secure: bool = False
    hsts: bool = False
    cors_origins: tuple[str, ...] = ()
    session_hours: int = 12
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    login_ip_max_failures: int = 100
    trusted_proxies: tuple[str, ...] = ("127.0.0.0/8", "::1/128", "172.16.0.0/12")
    max_body_bytes: int = 1_048_576
    max_upload_bytes: int = 25 * 1024 * 1024
    templates_dir: str = field(default_factory=default_templates_dir)
    storage_dir: str = "./data"
    static_root: str = ""
    ticket_url_base: str = "https://icare.mtnirancell.ir/browse/"
    automation_enabled: bool = False
    automation_interval_s: int = 86_400
    auto_migrate: bool = False
    log_level: str = "INFO"
    trusted_hosts: tuple[str, ...] = ()
    max_xlsx_uncompressed_bytes: int = 64 * 1024 * 1024
    max_xlsx_ratio: int = 120
    max_import_rows: int = 200_000
    sync_wait_s: float = 5.0
    sync_chunk: int = 500
    sync_stale_s: int = 600
    email_pending_ttl_s: int = 900
    extra: dict = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve()

    def data_keys(self) -> list[bytes]:
        keys = [decode_key(self.data_key)] if self.data_key else []
        keys += [decode_key(k) for k in self.data_key_previous]
        return keys

    def validate(self) -> None:
        """Refuse unsafe production configuration. Dev/test only warn via ensure_dev_key."""
        if self.env not in {"development", "test", "production"}:
            raise ConfigError("TMS_ENV باید development, test یا production باشد")
        if self.data_key:
            decode_key(self.data_key)
        if not self.is_production:
            return
        problems: list[str] = []
        if not self.data_key:
            problems.append("TMS_DATA_KEY تنظیم نشده است")
        elif _weak_key(decode_key(self.data_key)):
            problems.append("TMS_DATA_KEY ضعیف است (openssl rand -base64 32)")
        if not self.secret_key:
            problems.append("TMS_SECRET_KEY تنظیم نشده است")
        elif _weak_secret(self.secret_key):
            problems.append("TMS_SECRET_KEY ضعیف یا کوتاه است (حداقل ۳۲ نویسه تصادفی)")
        if self.bootstrap_admin_password:
            why = weak_password(self.bootstrap_admin_password, self.bootstrap_admin_user)
            if why:
                problems.append("TMS_BOOTSTRAP_ADMIN_PASSWORD: " + why)
        if self.auto_migrate:
            problems.append("TMS_AUTO_MIGRATE در production مجاز نیست (alembic upgrade head را صریح اجرا کنید)")
        for cidr in self.trusted_proxies:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                problems.append(f"TMS_TRUSTED_PROXIES نامعتبر: {cidr}")
        if "*" in self.cors_origins:
            problems.append("TMS_CORS_ORIGINS نباید * باشد")
        if problems:
            raise ConfigError("پیکربندی ناامن برای حالت production: " + "؛ ".join(problems))


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    e = os.environ if env is None else env
    mode = e.get("TMS_ENV", "development").strip().lower()
    prod = mode == "production"
    s = Settings(
        env=mode,
        database_url=e.get("DATABASE_URL") or e.get("TMS_DATABASE_URL") or "sqlite:///./tms-dev.db",
        data_key=e.get("TMS_DATA_KEY", ""),
        data_key_previous=_list(e.get("TMS_DATA_KEY_PREVIOUS")),
        secret_key=e.get("TMS_SECRET_KEY", ""),
        bootstrap_admin_user=e.get("TMS_BOOTSTRAP_ADMIN_USER", "admin" if e.get("TMS_BOOTSTRAP_ADMIN_PASSWORD") else ""),
        bootstrap_admin_password=e.get("TMS_BOOTSTRAP_ADMIN_PASSWORD", ""),
        cookie_secure=_bool(e.get("TMS_COOKIE_SECURE"), prod),
        hsts=_bool(e.get("TMS_HSTS"), False),
        cors_origins=_list(e.get("TMS_CORS_ORIGINS")),
        session_hours=_int(e.get("TMS_SESSION_HOURS"), 12),
        login_max_failures=_int(e.get("TMS_LOGIN_MAX_FAILURES"), 5),
        login_lock_minutes=_int(e.get("TMS_LOGIN_LOCK_MINUTES"), 15),
        login_ip_max_failures=_int(e.get("TMS_LOGIN_IP_MAX_FAILURES"), 100),
        trusted_proxies=_list(e.get("TMS_TRUSTED_PROXIES")) or ("127.0.0.0/8", "::1/128", "172.16.0.0/12"),
        max_body_bytes=_int(e.get("TMS_MAX_BODY_BYTES"), 1_048_576),
        max_upload_bytes=_int(e.get("TMS_MAX_UPLOAD_BYTES"), 25 * 1024 * 1024),
        templates_dir=str(Path(e["TMS_TEMPLATES_DIR"]).resolve()) if e.get("TMS_TEMPLATES_DIR") else default_templates_dir(),
        storage_dir=e.get("TMS_STORAGE_DIR", "./data"),
        static_root=e.get("TMS_STATIC_ROOT", ""),
        ticket_url_base=e.get("TMS_TICKET_URL_BASE", "https://icare.mtnirancell.ir/browse/"),
        automation_enabled=_bool(e.get("TMS_AUTOMATION_ENABLED"), False),
        automation_interval_s=max(60, _int(e.get("TMS_AUTOMATION_INTERVAL_S"), 86_400)),
        auto_migrate=_bool(e.get("TMS_AUTO_MIGRATE"), False),
        log_level=e.get("TMS_LOG_LEVEL", "INFO").upper(),
        trusted_hosts=_list(e.get("TMS_TRUSTED_HOSTS")),
        max_xlsx_uncompressed_bytes=_int(e.get("TMS_MAX_XLSX_UNCOMPRESSED_BYTES"), 64 * 1024 * 1024),
        max_xlsx_ratio=_int(e.get("TMS_MAX_XLSX_RATIO"), 120),
        max_import_rows=_int(e.get("TMS_MAX_IMPORT_ROWS"), 200_000),
        sync_wait_s=float(e.get("TMS_SYNC_WAIT_S") or 5),
        sync_chunk=max(50, _int(e.get("TMS_SYNC_CHUNK"), 500)),
        sync_stale_s=max(60, _int(e.get("TMS_SYNC_STALE_S"), 600)),
        email_pending_ttl_s=max(60, _int(e.get("TMS_EMAIL_PENDING_TTL_S"), 900)),
    )
    return s


def ensure_dev_key(s: Settings) -> Settings:
    """Non-production only: persist a generated data key next to the storage dir so dev data
    survives restarts. Never used in production (validate() refuses a missing key)."""
    if s.data_key or s.is_production:
        return s
    p = s.storage_path / ".dev_data_key"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
        p.chmod(0o600)
    return replace(s, data_key=p.read_text().strip())
