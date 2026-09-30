"""The domain model (ARCHITECTURE §4). Personal data columns are EncryptedText."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from .types import EncryptedJSON, EncryptedText, EncryptedTextCompat


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)   # naive UTC everywhere


ROLES = ("viewer", "hr", "admin")
CONNECTOR_KINDS = ("excel", "ifs", "smtp", "graph")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    user: Mapped[User] = relationship()


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True, default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Institute(Base):
    __tablename__ = "institutes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    name_fa: Mapped[str] = mapped_column(String(200), default="")
    supplier_code: Mapped[str] = mapped_column(String(64), default="")
    contact_email: Mapped[str] = mapped_column(String(200), default="")


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    emp_no: Mapped[str] = mapped_column(String(32), unique=True)
    first_name_en: Mapped[str] = mapped_column(String(100), default="")
    last_name_en: Mapped[str] = mapped_column(String(100), default="", index=True)
    first_name_fa: Mapped[str] = mapped_column(String(100), default="")
    last_name_fa: Mapped[str] = mapped_column(String(100), default="")
    gender: Mapped[str] = mapped_column(String(8), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    mobile: Mapped[str | None] = mapped_column(EncryptedText("employee.mobile"))
    national_code: Mapped[str | None] = mapped_column(EncryptedText("employee.national_code"))
    date_of_birth: Mapped[str | None] = mapped_column(EncryptedText("employee.date_of_birth"))
    division: Mapped[str] = mapped_column(String(200), default="", index=True)
    cost_center: Mapped[str] = mapped_column(String(64), default="")
    org_code: Mapped[str] = mapped_column(String(64), default="")
    position_title: Mapped[str] = mapped_column(String(200), default="")
    supervisor_emp_no: Mapped[str] = mapped_column(String(32), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="Active")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    name_fa: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    default_duration_h: Mapped[float | None] = mapped_column(Numeric(8, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CourseRun(Base):
    __tablename__ = "course_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(600), unique=True)   # course|institute|start
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    institute_id: Mapped[int | None] = mapped_column(ForeignKey("institutes.id"))
    type: Mapped[str] = mapped_column(String(16), default="in_person")
    duration_h: Mapped[float | None] = mapped_column(Numeric(8, 2))
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    days: Mapped[str] = mapped_column(String(100), default="")
    time: Mapped[str] = mapped_column(String(50), default="")
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    send_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    section_b: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    link: Mapped[str] = mapped_column(String(500), default="")
    payment_process: Mapped[str] = mapped_column(String(100), default="")
    pr_process_start_date: Mapped[date | None] = mapped_column(Date)
    invoice_receive_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    course: Mapped[Course] = relationship()
    institute: Mapped[Institute | None] = relationship()


class Enrollment(Base):
    __tablename__ = "enrollments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket: Mapped[str] = mapped_column(String(32), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("course_runs.id"), index=True)
    course_name: Mapped[str] = mapped_column(String(300), default="", index=True)   # IDP "Summary"
    category: Mapped[str] = mapped_column(String(100), default="")
    delivery_method: Mapped[str] = mapped_column(String(50), default="")
    idp_type: Mapped[str] = mapped_column(String(50), default="")
    job_level: Mapped[str] = mapped_column(String(50), default="")
    department: Mapped[str] = mapped_column(String(200), default="")
    current_status: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(32), default="requested")
    motivation: Mapped[str] = mapped_column(String(8), default="")
    registration: Mapped[str] = mapped_column(String(50), default="")
    calendar: Mapped[str] = mapped_column(String(50), default="")
    attendance_status: Mapped[str] = mapped_column(String(50), default="-")
    payment: Mapped[str] = mapped_column(String(100), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    section_b: Mapped[str] = mapped_column(String(64), default="")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    level3_status: Mapped[str] = mapped_column(String(32), default="")
    level3_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_fields: Mapped[list[Any]] = mapped_column(JSON, default=list)   # columns edited by a person: imports never overwrite them
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    employee: Mapped[Employee] = relationship()
    run: Mapped[CourseRun | None] = relationship()


class EnrollmentOffer(Base):
    """One row per time an IDP request (ticket) was offered in a run = one legacy `Record` row.
    The per-TICKET "motivation not Yes" count (IDP!R) is a count over these rows."""
    __tablename__ = "enrollment_offers"
    __table_args__ = (UniqueConstraint("enrollment_id", "offer_key", name="uq_offer_enrollment_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("course_runs.id"))
    offer_key: Mapped[str] = mapped_column(String(600))      # run_key, or a legacy key when no run exists
    motivation: Mapped[str] = mapped_column(String(8), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LetterCounter(Base):
    __tablename__ = "letter_counters"
    series: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class Letter(Base):
    __tablename__ = "letters"
    __table_args__ = (UniqueConstraint("kind", "seq", name="uq_letter_kind_seq"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("course_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="final")   # final | sent
    lang: Mapped[str] = mapped_column(String(8), default="both")
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(500), default="")
    html_body: Mapped[str] = mapped_column(EncryptedTextCompat("letter.html_body"), default="")   # contains participant PII
    enrollment_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MessageLog(Base):
    __tablename__ = "message_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    letter_id: Mapped[int | None] = mapped_column(ForeignKey("letters.id"))
    subject: Mapped[str] = mapped_column(String(500), default="")
    recipients: Mapped[list[Any]] = mapped_column(JSON, default=list)
    results: Mapped[list[Any]] = mapped_column(JSON, default=list)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|sent|partial|failed|dry_run
    channel: Mapped[str] = mapped_column(String(16), default="")
    request_hash: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    public: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    secrets: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON("connector.secrets"))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_test_message: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)   # excel|ifs|idp|legacy|automation
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|error
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    triggered_by: Mapped[str] = mapped_column(String(64), default="")
    message: Mapped[str] = mapped_column(String(300), default="")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    processed: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    """Append-only. DB triggers (audit/triggers.py) and an ORM guard forbid UPDATE/DELETE."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), default="", index=True)
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Lease(Base):
    """Cross-worker lease (background loop, sync guard)."""
    __tablename__ = "leases"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


Index("ix_enrollment_run_emp", Enrollment.run_id, Enrollment.employee_id)
