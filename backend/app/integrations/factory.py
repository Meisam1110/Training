"""Factories with EXACTLY the names/signatures frozen in app/contracts.py."""
from __future__ import annotations

from typing import Literal

from app.contracts import EmailSender, EmployeeSource, ExcelGateway, JalaliCalendar, LetterRenderer


def build_calendar() -> JalaliCalendar:
    from app.persian import PersianCalendar
    return PersianCalendar()


def build_excel_gateway() -> ExcelGateway:
    from .excel.gateway import OpenpyxlExcelGateway
    return OpenpyxlExcelGateway()


def build_employee_source(kind: Literal["excel", "ifs"], config: dict) -> EmployeeSource:
    if kind == "excel":
        from .excel.source import ExcelEmployeeSource
        return ExcelEmployeeSource(config)
    if kind == "ifs":
        from .ifs.client import IfsEmployeeSource
        return IfsEmployeeSource(config)
    raise ValueError(f"unknown employee source kind: {kind!r}")


def build_email_sender(kind: Literal["smtp", "graph"], config: dict) -> EmailSender:
    if kind == "smtp":
        from .email.smtp import SmtpSender
        return SmtpSender(config)
    if kind == "graph":
        from .email.graph import GraphSender
        return GraphSender(config)
    raise ValueError(f"unknown email sender kind: {kind!r}")


def build_letter_renderer(templates_dir: str) -> LetterRenderer:
    from app.documents.renderer import DocxLetterRenderer
    return DocxLetterRenderer(templates_dir)
