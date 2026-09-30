"""EmployeeSource / IdpSource adapters over the Excel gateway (single file or a watched folder)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.contracts import EmployeeRecord, IdpRow
from app.integrations.redact import sanitize_error

from .gateway import ExcelFormatError, OpenpyxlExcelGateway


def resolve_path(config: Mapping[str, Any]) -> Path:
    """`path` wins; otherwise the newest .xlsx/.xlsm in `watch_dir` (temp/lock files ignored)."""
    if config.get("path"):
        return Path(str(config["path"]))
    wd = config.get("watch_dir")
    if not wd:
        raise ExcelFormatError("excel config needs 'path' or 'watch_dir'")
    files = [p for p in Path(str(wd)).glob("*") if p.suffix.lower() in (".xlsx", ".xlsm")
             and not p.name.startswith(("~$", "."))]
    if not files:
        raise FileNotFoundError("no .xlsx/.xlsm file in the watch directory")
    return max(files, key=lambda p: p.stat().st_mtime_ns)


class ExcelEmployeeSource:
    def __init__(self, config: Mapping[str, Any], gateway: OpenpyxlExcelGateway | None = None):
        self.config = dict(config)
        self.gw = gateway or OpenpyxlExcelGateway()
        self.last_report = None

    def test_connection(self) -> tuple[bool, str]:
        try:
            p = resolve_path(self.config)
            emps, rep = self.gw.read_employees_report(str(p), self.config.get("sheet"))
            return True, f"OK: {p.name} readable, {len(emps)} employee row(s)"
        except Exception as exc:  # noqa: BLE001 - messages carry no cell values
            return False, sanitize_error(exc)

    def fetch_employees(self, modified_since: datetime | None = None) -> Iterable[EmployeeRecord]:
        p = resolve_path(self.config)
        if modified_since is not None:
            ms = modified_since if modified_since.tzinfo else modified_since.replace(tzinfo=timezone.utc)
            if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) <= ms:
                return []
        emps, self.last_report = self.gw.read_employees_report(str(p), self.config.get("sheet"))
        return emps


class ExcelIdpSource:
    def __init__(self, config: Mapping[str, Any], gateway: OpenpyxlExcelGateway | None = None):
        self.config = dict(config)
        self.gw = gateway or OpenpyxlExcelGateway()

    def fetch_idp(self) -> Iterable[IdpRow]:
        return self.gw.read_idp(str(resolve_path(self.config)))
