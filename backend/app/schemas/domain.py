"""Request schemas (Pydantic v2). Responses are built by api/services/serializers.py."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LetterKindT = Literal["course_announcement", "institute_letter", "settlement_letter",
                      "level3_request", "level3_manager_check", "line_manager_approval"]
_PERSIAN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
INT_MAX = 2**31 - 1
Id = Annotated[int, Field(ge=1, le=INT_MAX)]     # ids beyond the DB integer range are a 422, never a 500


def has_nul(x: Any, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(x, str):
        return "\x00" in x
    if isinstance(x, dict):
        return any(has_nul(k, depth + 1) or has_nul(v, depth + 1) for k, v in x.items())
    if isinstance(x, (list, tuple)):
        return any(has_nul(v, depth + 1) for v in x)
    return False


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def _no_nul(self):
        if any(has_nul(v) for v in self.__dict__.values()):
            raise ValueError("کاراکتر NUL مجاز نیست")
        return self


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=1, max_length=256)
    role: Literal["admin", "hr", "viewer"] = "viewer"
    display_name: str = Field("", max_length=128)


class UserPatch(Strict):
    is_active: bool | None = None
    role: Literal["admin", "hr", "viewer"] | None = None
    password: str | None = Field(None, min_length=1, max_length=256)
    display_name: str | None = Field(None, max_length=128)


class InstituteIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    name_fa: str = Field("", max_length=200)
    supplier_code: str = Field("", max_length=64)
    contact_email: str = Field("", max_length=200)

    @field_validator("contact_email")
    @classmethod
    def _mail(cls, v):
        if v and not EMAIL_RE.match(v):
            raise ValueError("نشانی ایمیل نامعتبر")
        return v.lower()


class InstitutePatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=200)
    name_fa: str | None = Field(None, max_length=200)
    supplier_code: str | None = Field(None, max_length=64)
    contact_email: str | None = Field(None, max_length=200)

    @field_validator("contact_email")
    @classmethod
    def _mail(cls, v):
        if v and not EMAIL_RE.match(v):
            raise ValueError("نشانی ایمیل نامعتبر")
        return v.lower() if v else v


class CourseIn(Strict):
    name: str = Field(min_length=1, max_length=300)
    name_fa: str = Field("", max_length=300)
    category: str = Field("", max_length=100)
    default_duration_h: float | None = Field(None, gt=0, le=10_000)
    active: bool = True


class CoursePatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=300)
    name_fa: str | None = Field(None, max_length=300)
    category: str | None = Field(None, max_length=100)
    default_duration_h: float | None = Field(None, gt=0, le=10_000)
    active: bool | None = None


RunType = Literal["online", "in_person"]
RunStatus = Literal["planned", "announced", "open", "running", "completed", "cancelled"]


class RunBase(Strict):
    type: RunType = "in_person"
    institute: str = Field("", max_length=200)
    duration_h: float | None = Field(None, gt=0, le=10_000)
    start_date: date | None = None
    end_date: date | None = None
    days: str = Field("", max_length=100)
    time: str = Field("", max_length=50)
    sessions: int = Field(0, ge=0, le=1000)
    send_date: date | None = None
    deadline: date | None = None
    amount: Decimal | None = Field(None, ge=0, le=Decimal("1e15"))
    section_b: str = Field("", max_length=64)
    status: RunStatus = "planned"
    link: str = Field("", max_length=500)
    payment_process: str = Field("", max_length=100)
    pr_process_start_date: date | None = None
    invoice_receive_date: date | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("تاریخ پایان قبل از تاریخ شروع است")
        return self


class RunIn(RunBase):
    course_id: Id


class RunPatch(Strict):
    type: RunType | None = None
    institute: str | None = Field(None, max_length=200)
    duration_h: float | None = Field(None, gt=0, le=10_000)
    start_date: date | None = None
    end_date: date | None = None
    days: str | None = Field(None, max_length=100)
    time: str | None = Field(None, max_length=50)
    sessions: int | None = Field(None, ge=0, le=1000)
    send_date: date | None = None
    deadline: date | None = None
    amount: Decimal | None = Field(None, ge=0, le=Decimal("1e15"))
    section_b: str | None = Field(None, max_length=64)
    status: RunStatus | None = None
    link: str | None = Field(None, max_length=500)
    payment_process: str | None = Field(None, max_length=100)
    pr_process_start_date: date | None = None
    invoice_receive_date: date | None = None


class CandidateSearchIn(Strict):
    course_name: str | None = Field(None, max_length=300)   # default: the run's course
    include_flagged: bool = True


class EnrollmentPatch(Strict):
    motivation: Literal["Yes", "No", ""] | None = None
    registration: str | None = Field(None, max_length=50)
    calendar: str | None = Field(None, max_length=50)
    attendance: str | None = Field(None, max_length=50)
    payment: str | None = Field(None, max_length=100)
    comment: str | None = Field(None, max_length=2000)
    run_id: Id | None = None
    unassign: bool = False
    level3_status: str | None = Field(None, max_length=32)
    level3_sent: bool | None = None
    # hand a field back to the importer (see docs: manual edits win over imports until released)
    release_fields: list[Literal["motivation", "registration", "calendar", "attendance", "payment", "comment"]] = Field(default_factory=list)


class BulkIn(Strict):
    enrollment_ids: list[Id] = Field(min_length=1, max_length=500)
    run_id: Id | None = None
    unassign: bool = False
    motivation: Literal["Yes", "No", ""] | None = None
    registration: str | None = Field(None, max_length=50)
    calendar: str | None = Field(None, max_length=50)
    attendance: str | None = Field(None, max_length=50)


class LetterIn(Strict):
    kind: LetterKindT
    run_id: Id | None = None
    enrollment_ids: list[Id] = Field(default_factory=list, max_length=500)
    lang: Literal["fa", "en", "both"] = "both"
    extra: dict[str, Any] = Field(default_factory=dict)   # invoice_no, supplier, addressee, purpose...

    @field_validator("extra")
    @classmethod
    def _extra(cls, v):
        if len(v) > 30 or any(not isinstance(k, str) or len(k) > 64 for k in v):
            raise ValueError("extra بیش از حد بزرگ است")
        for x in v.values():
            if isinstance(x, (dict, list)) or (isinstance(x, str) and len(x) > 500):
                raise ValueError("مقادیر extra باید متن کوتاه یا عدد باشند")
        return v


class EmailSendIn(Strict):
    letter_id: Id | None = None
    template: LetterKindT | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    lang: Literal["fa", "en", "both"] = "both"
    subject: str | None = Field(None, max_length=300, pattern=r"^[^\r\n]*$")
    recipients: list[str] = Field(min_length=1, max_length=200)
    cc: list[str] = Field(default_factory=list, max_length=50)
    dry_run: bool = False
    idempotency_key: str | None = Field(None, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    channel: Literal["smtp", "graph"] | None = None

    @field_validator("recipients", "cc")
    @classmethod
    def _emails(cls, v):
        out = []
        for e in v:
            e = e.strip()
            if not EMAIL_RE.match(e):
                raise ValueError("نشانی ایمیل نامعتبر")
            if e.lower() not in out:
                out.append(e.lower())
        return out

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.letter_id) == bool(self.template):
            raise ValueError("دقیقاً یکی از letter_id یا template لازم است")
        return self


class ConnectorPut(Strict):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class SyncIn(Strict):
    full: bool = False


class AutomationSettingsIn(Strict):
    enabled: bool | None = None
    level3_after_days: int | None = Field(None, ge=1, le=365)
    reminder_days: int | None = Field(None, ge=0, le=60)
    over3_threshold: int | None = Field(None, ge=1, le=50)
    auto_send: bool | None = None
    watch_excel: bool | None = None
    ifs_sync_interval_min: int | None = Field(None, ge=0, le=10_080)
    letter_number_prefix: str | None = Field(None, max_length=20, pattern=r"^[A-Za-z0-9/_.-]*$")
    letter_number_start: int | None = Field(None, ge=0, le=10**9)
    company_economic_code: str | None = Field(None, max_length=64)
    company_national_id: str | None = Field(None, max_length=64)
    company_postal_code: str | None = Field(None, max_length=32)
    company_address: str | None = Field(None, max_length=300)
    settlement_addressee: str | None = Field(None, max_length=100)
    letter_signer_name: str | None = Field(None, max_length=100)
    letter_signer_title: str | None = Field(None, max_length=100)
    letter_signer_email: str | None = Field(None, max_length=200)
    letter_signer_phone: str | None = Field(None, max_length=50)


def to_latin_digits(s: str) -> str:
    return s.translate(_PERSIAN)
