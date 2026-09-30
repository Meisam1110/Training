"""Scrubbing of PII / secrets from text that is logged, stored (SyncRun.errors) or returned."""
from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "password", "passwd", "secret", "client_secret", "token", "authorization", "cookie",
    "set-cookie", "national_code", "mobile", "date_of_birth", "dob", "data_key", "api_key",
    "x-csrf-token", "secret_key", "secrets", "nationalcode",
}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONGNUM = re.compile(r"(?<![\w-])(?:\+?98|0)?9\d{9}(?!\d)|(?<!\d)\d{10}(?!\d)")
_KV = re.compile(r"(?i)\b(password|passwd|secret|client_secret|token|authorization|api[_-]?key)\b\s*[=:]\s*\S+")
_BEARER = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+")
_URLCRED = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")


def scrub(text: Any, limit: int = 300) -> str:
    s = str(text)
    s = _URLCRED.sub(r"\1***:***@", s)
    s = _BEARER.sub("Bearer ***", s)
    s = _KV.sub(lambda m: m.group(1) + "=***", s)
    s = _EMAIL.sub("***@***", s)
    s = _LONGNUM.sub("***", s)
    return s[:limit]


def redact_mapping(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "..."
    if isinstance(obj, dict):
        return {k: ("***" if str(k).lower() in SENSITIVE_KEYS else redact_mapping(v, depth + 1)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_mapping(v, depth + 1) for v in obj]
    if isinstance(obj, str):
        return scrub(obj, 2000)
    return obj
