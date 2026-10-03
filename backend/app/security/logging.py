"""Structured JSON logging with PII/secret redaction."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from .redact import redact_mapping, scrub

_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage(), 2000),
        }
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                data[k] = redact_mapping({k: v})[k]
        if record.exc_info:
            # class + location only: exception messages can embed row values
            et, ev, tb = record.exc_info
            data["exc"] = et.__name__ if et else "Exception"
            last = tb
            while last and last.tb_next:
                last = last.tb_next
            if last:
                data["exc_at"] = f"{last.tb_frame.f_code.co_filename.rsplit('/', 1)[-1]}:{last.tb_lineno}"
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_tms", False):
            root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h._tms = True  # type: ignore[attr-defined]
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(level)
    for noisy in ("httpx", "alembic", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our request log (no query strings)
