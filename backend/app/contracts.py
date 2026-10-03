"""Frozen interfaces between Core (Dev-A) and Integrations (Dev-B).

Core calls these Protocols; Integrations implements them. Do not edit — file a request in
docs/CONTRACT_REQUESTS.md. Pure stdlib on purpose (offline install).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Literal, Mapping, Protocol, Sequence

LetterKind = Literal[
    "course_announcement", "institute_letter", "settlement_letter",
    "level3_request", "level3_manager_check", "line_manager_approval",
]


@dataclass(frozen=True)
class EmployeeRecord:
    emp_no: str
    first_name_en: str
    last_name_en: str
    first_name_fa: str = ""
    last_name_fa: str = ""
    gender: Literal["male", "female", ""] = ""
    email: str = ""
    mobile: str = ""
    national_code: str = ""
    division: str = ""
    cost_center: str = ""
    org_code: str = ""
    position_title: str = ""
    supervisor_emp_no: str = ""
    status: str = "Active"


@dataclass(frozen=True)
class IdpRow:
    """One row of the iCare IDP export (see docs/ANALYSIS.md, sheet IDP)."""
    emp_no: str
    reporter_name: str
    job_level: str
    department: str
    summary: str            # course name
    delivery_method: str
    current_status: str
    idp_type: str
    course_category: str
    attendance_status: str
    start_date: date | None
    end_date: date | None
    ticket: str             # LMS-123456
    section_b: str          # MTC-123456 or "-"


@dataclass
class SyncReport:
    source: str
    started_at: datetime
    finished_at: datetime | None = None
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)   # never contains PII values


class EmployeeSource(Protocol):
    """IFS or an Excel 'IFS' sheet."""
    def test_connection(self) -> tuple[bool, str]: ...
    def fetch_employees(self, modified_since: datetime | None = None) -> Iterable[EmployeeRecord]: ...


class IdpSource(Protocol):
    def fetch_idp(self) -> Iterable[IdpRow]: ...


@dataclass(frozen=True)
class RenderedLetter:
    kind: LetterKind
    filename: str
    docx_bytes: bytes
    html_body: str          # inline-safe HTML used as the email body
    subject: str
    fields: Mapping[str, Any]


class LetterRenderer(Protocol):
    def render(self, kind: LetterKind, fields: Mapping[str, Any], lang: Literal["fa", "en", "both"] = "both") -> RenderedLetter: ...
    def required_fields(self, kind: LetterKind, lang: Literal["fa", "en", "both"] = "both") -> Sequence[str]: ...


@dataclass(frozen=True)
class OutgoingEmail:
    to: Sequence[str]
    subject: str
    html_body: str
    cc: Sequence[str] = ()
    attachments: Sequence[tuple[str, bytes, str]] = ()   # (filename, bytes, mime)
    idempotency_key: str = ""


@dataclass(frozen=True)
class SendResult:
    recipient: str
    ok: bool
    message_id: str = ""
    error: str = ""          # sanitized, no credentials


class EmailSender(Protocol):
    def send(self, msg: OutgoingEmail, *, dry_run: bool = False) -> list[SendResult]: ...
    def test_connection(self) -> tuple[bool, str]: ...


class JalaliCalendar(Protocol):
    def to_jalali(self, d: date) -> tuple[int, int, int]: ...
    def to_gregorian(self, y: int, m: int, d: int) -> date: ...
    def format(self, d: date, style: Literal["short", "words", "weekday"] = "short") -> str: ...
    def add_days(self, d: date, n: int) -> date: ...
    def number_to_words_fa(self, n: int) -> str: ...
    def to_persian_digits(self, s: str) -> str: ...
    def to_latin_digits(self, s: str) -> str: ...


@dataclass(frozen=True)
class DueItem:
    kind: Literal["level3_due", "deadline_reminder", "over3_motivations", "payment_not_started"]
    enrollment_id: int | None
    run_id: int | None
    detail: str


@dataclass(frozen=True)
class EnrollmentFact:
    """Flat, DB-free snapshot Core builds from its tables; Integrations' scheduler is a pure function of it."""
    enrollment_id: int
    run_id: int
    ticket: str
    course_name: str
    category: str
    current_status: str
    end_date: date | None
    run_start_date: date | None
    registration_deadline: date | None
    motivation: str                 # "Yes" | "No" | ""
    payment_started: bool
    level3_sent: bool = False


def compute_due(facts: Sequence[EnrollmentFact], today: date, *, level3_after_days: int = 60,
                reminder_days: int = 2, over3_threshold: int = 3) -> list[DueItem]:
    """Implemented in app/automation/rules.py (Dev-B). Signature is the contract."""
    raise NotImplementedError


@dataclass(frozen=True)
class RunRecord:          # legacy CHistory row
    course_name: str
    course_name_fa: str
    type: Literal["online", "in_person"]
    institute: str
    duration_h: float
    start_date: date | None
    end_date: date | None
    days: str
    time: str
    sessions: int
    send_date: date | None
    deadline: date | None
    amount: float | None
    section_b: str
    link: str = ""


@dataclass(frozen=True)
class RecordRow:          # legacy Record row (person + run)
    emp_no: str
    ticket: str
    course_name: str
    institute: str
    start_date: date | None
    motivation: str
    registration: str
    calendar: str
    payment: str
    comment: str = ""


@dataclass
class LegacyData:
    employees: list[EmployeeRecord] = field(default_factory=list)
    idp: list[IdpRow] = field(default_factory=list)
    runs: list[RunRecord] = field(default_factory=list)
    records: list[RecordRow] = field(default_factory=list)


class ExcelGateway(Protocol):
    def read_idp(self, path: str) -> list[IdpRow]: ...
    def read_employees(self, path: str) -> list[EmployeeRecord]: ...
    def read_legacy(self, path: str) -> LegacyData: ...
    def write_legacy(self, data: LegacyData, path: str) -> None: ...


# ---- Factories: Dev-B provides these in app/integrations/factory.py (exact names/signatures) ----
#   build_calendar() -> JalaliCalendar
#   build_excel_gateway() -> ExcelGateway
#   build_employee_source(kind: Literal["excel","ifs"], config: dict) -> EmployeeSource
#   build_email_sender(kind: Literal["smtp","graph"], config: dict) -> EmailSender
#   build_letter_renderer(templates_dir: str) -> LetterRenderer
# `config` is the decrypted ConnectorConfig JSON (secrets included, never logged).
# Excel config: {"path"|"watch_dir": str}. IFS: {"base_url","auth_mode","client_id","client_secret",
#   "token_url","username","password","login_url","verify_tls","timeout_s","field_map":{...}}.
# SMTP: {"host","port","username","password","starttls","from_addr","from_name"}.
# Graph: {"tenant_id","client_id","client_secret","sender"}.
