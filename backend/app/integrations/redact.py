"""Secret redaction helpers. Every place that logs or raises with upstream content goes through here."""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping

REDACTED = "***"
SECRET_KEYS = ("password", "passwd", "secret", "token", "authorization", "api_key", "apikey",
               "client_secret", "cookie", "set-cookie", "access_token", "refresh_token", "assertion")

_PATTERNS = [
    re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{6,}"),
    re.compile(r"(?i)((?:client_)?secret|password|passwd|token|access_token|refresh_token|api[_-]?key)"
               r"(\"?\s*[:=]\s*\"?)([^\s\"&,;}]+)"),
    re.compile(r"(?i)(set-cookie|cookie)(\s*:\s*)([^\r\n]+)"),
]


def is_secret_key(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in SECRET_KEYS)


def redact_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secret values and common secret-looking patterns from *text*."""
    out = str(text)
    for s in secrets:
        if s and len(s) >= 3:
            out = out.replace(s, REDACTED)
    out = _PATTERNS[0].sub(lambda m: f"{m.group(1)} {REDACTED}", out)
    out = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    out = _PATTERNS[2].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    return out


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of *data* with secret-valued keys masked (for logging config)."""
    return {k: (REDACTED if is_secret_key(str(k)) and v else v) for k, v in data.items()}


def config_secrets(config: Mapping[str, Any]) -> list[str]:
    """Collect the secret string values held in a connector config."""
    return [str(v) for k, v in config.items() if is_secret_key(str(k)) and isinstance(v, str) and v]


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs secrets from every record (message and args)."""

    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            msg = str(record.msg)
        record.msg = redact_text(msg, self.secrets)
        record.args = None
        return True


def sanitize_error(exc: BaseException, secrets: Iterable[str] = (), limit: int = 200) -> str:
    """Short, secret-free description of an exception: class name plus scrubbed message."""
    text = redact_text(str(exc), secrets)
    text = " ".join(text.split())
    return f"{type(exc).__name__}: {text[:limit]}" if text else type(exc).__name__
