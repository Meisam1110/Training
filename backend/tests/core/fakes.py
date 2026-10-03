"""Fakes implementing the contracts.py Protocols -- all data is synthetic."""
from __future__ import annotations

import io
import threading
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from app.contracts import DueItem, EmployeeRecord, EnrollmentFact, IdpRow, LegacyData, OutgoingEmail, RenderedLetter, SendResult

WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


class FakeCalendar:
    def to_jalali(self, d): return (d.year - 621, d.month, d.day)
    def to_gregorian(self, y, m, d): return date(y + 621, m, d)
    def format(self, d, style="short"):
        return {"short": f"{d.year - 621}/{d.month:02d}/{d.day:02d}", "words": f"روز {d.day}", "weekday": WEEKDAYS[d.weekday()]}[style]
    def add_days(self, d, n): return d + timedelta(days=n)
    def number_to_words_fa(self, n): return str(n)
    def to_persian_digits(self, s): return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    def to_latin_digits(self, s): return str(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


# mirrors app/documents/specs.py (Dev-B) for the fields Core must supply
REQUIRED = {
    "course_announcement": ["Farsi_Course_Name", "Farsi_Type", "deadline_farsi", "Time_Farsi", "jStart_Date", "Date_Horoof", "Day_Farsi",
                            "Time", "Sessions_Count", "Course_Name", "Type", "Deadline", "Duration", "start_Date", "Day", "link"],
    "institute_letter": ["Letter_No", "date", "To", "Course_Name", "Jstart_Date", "Days", "Time", "Duration", "Method",
                         "company_economic_code", "company_national_id", "company_postal_code", "company_address", "participants"],
    "settlement_letter": ["addressee", "supplier", "invoice_no", "purpose", "mtc_no", "start_date_greg", "start_date_jalali",
                          "attendee_count", "supplier_code", "total", "per_attendee", "rows"],
    "level3_request": ["Ftitle", "Fname", "En_title", "Reporter__Name", "Summary", "link"],
    "level3_manager_check": ["Manager_fTitle", "Manager_Fname", "Manager_Title", "Manager_Name", "Reporter_F_tilte", "Reporter_Fname",
                             "Reporter_title", "Reporter__Name", "Summary", "link"],
    "line_manager_approval": ["Title", "Mg_name", "employees"],
}


class FakeRenderer:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def required_fields(self, kind, lang="both"): return REQUIRED[kind]

    def render(self, kind, fields: Mapping[str, Any], lang="both"):
        self.calls.append((kind, dict(fields)))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", f"<x>{kind}:{fields.get('Letter_No', '')}</x>")
        return RenderedLetter(kind=kind, filename=f"{kind}.docx", docx_bytes=buf.getvalue(),
                              html_body=f"<p>{kind} {fields.get('Letter_No', '')}</p>", subject=f"subject {kind}", fields=fields)


class FakeSender:
    def __init__(self, fail: set[str] | None = None, boom: bool = False):
        self.fail, self.boom = fail or set(), boom
        self.sent: list[OutgoingEmail] = []
        self.lock = threading.Lock()

    def test_connection(self): return (True, "ok password=hunter2")

    def send(self, msg: OutgoingEmail, *, dry_run=False):
        if self.boom:
            raise RuntimeError("smtp down password=hunter2")
        with self.lock:
            self.sent.append(msg)
        return [SendResult(r, r not in self.fail, message_id=f"m-{r}" if r not in self.fail else "",
                           error="rejected" if r in self.fail else "") for r in msg.to]


class FakeSource:
    def __init__(self, records: list[EmployeeRecord], ok=True, boom=False):
        self.records, self.ok, self.boom = records, ok, boom
        self.since_seen: list[datetime | None] = []

    def test_connection(self): return (self.ok, "connected" if self.ok else "refused")

    def fetch_employees(self, modified_since=None):
        self.since_seen.append(modified_since)
        if self.boom:
            raise RuntimeError("IFS unreachable for user 0912345678 secret=abc")
        return list(self.records)


class FakeExcel:
    def __init__(self):
        self.idp: list[IdpRow] = []
        self.legacy = LegacyData()
        self.written: LegacyData | None = None

    def read_idp(self, path): return list(self.idp)
    def read_employees(self, path): return list(self.legacy.employees)
    def read_legacy(self, path): return self.legacy

    def write_legacy(self, data, path):
        self.written = data
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("x", "y")


class FakeFactory:
    def __init__(self):
        self.calendar = FakeCalendar()
        self.excel = FakeExcel()
        self.renderer = FakeRenderer()
        self.sender = FakeSender()
        self.source = FakeSource([])
        self.built: list[tuple[str, str, dict]] = []

    def build_calendar(self): return self.calendar
    def build_excel_gateway(self): return self.excel
    def build_letter_renderer(self, templates_dir): return self.renderer

    def build_employee_source(self, kind, config):
        self.built.append(("source", kind, dict(config)))
        return self.source

    def build_email_sender(self, kind, config):
        self.built.append(("sender", kind, dict(config)))
        return self.sender


def fake_compute_due(facts: Sequence[EnrollmentFact], today: date, *, level3_after_days=60, reminder_days=2, over3_threshold=3):
    out = []
    for f in facts:
        if f.current_status.lower() == "evaluation level 3" and f.end_date and (today - f.end_date).days >= level3_after_days and not f.level3_sent:
            out.append(DueItem("level3_due", f.enrollment_id, f.run_id, f"ticket {f.ticket}"))
        if f.registration_deadline and 0 <= (f.registration_deadline - today).days <= reminder_days:
            out.append(DueItem("deadline_reminder", f.enrollment_id, f.run_id, "deadline"))
    return out


def employee(n: int, **kw) -> EmployeeRecord:
    base = dict(emp_no=f"E{n:05d}", first_name_en=f"Test{n}", last_name_en=f"Person{n}", first_name_fa=f"تست{n}", last_name_fa=f"نمونه{n}",
                gender="male" if n % 2 else "female", email=f"user{n}@example.test", mobile=f"0990000{n:04d}",
                national_code=f"999{n:07d}", division="Div A", cost_center="CC1", supervisor_emp_no="", status="Active")
    base.update(kw)
    return EmployeeRecord(**base)
