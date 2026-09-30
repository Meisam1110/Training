"""Field specifications for the six letter kinds (single source of truth for required_fields(),
validation, docs/TEMPLATES.md and the template builder). Field names are the legacy MERGEFIELD
names from docs/ANALYSIS.md; a few typo'd legacy names are kept as canonical with a corrected alias."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class F:
    name: str
    label: str
    example: str = ""
    required: bool = True
    default: str | None = None          # value used when optional and absent
    lang: Literal["fa", "en"] | None = None
    hide_if_empty: bool = False         # a paragraph holding only this placeholder disappears when empty
    derived_from: str = ""              # documentation only: which raw field can derive it


@dataclass(frozen=True)
class ListSpec:
    name: str
    label: str
    item_fields: tuple[F, ...]
    min_items: int = 1
    max_items: int | None = None
    item_aliases: dict[str, str] = field(default_factory=dict)   # item alias -> canonical


@dataclass(frozen=True)
class KindSpec:
    kind: str
    title: str
    bilingual: bool
    fields: tuple[F, ...]
    lists: tuple[ListSpec, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)      # alias -> canonical (top-level fields)
    template: str = ""


_SIGN = (
    F("signer_name", "Signer name", "Talent Development Team", required=False, default="Talent Development Team"),
    F("signer_title", "Signer title", "Human Resources", required=False, default="Human Resources",
      hide_if_empty=True),
    F("signer_email", "Signer e-mail", "training@example.test", required=False, default="", hide_if_empty=True),
    F("signer_phone", "Signer phone", "+98-21-00000000", required=False, default="", hide_if_empty=True),
)

SPECS: dict[str, KindSpec] = {
    "course_announcement": KindSpec(
        "course_announcement", "Course announcement (fa + en)", True, (
            F("Farsi_Course_Name", "Course title (Persian)", "مدیریت زمان", lang="fa"),
            F("Farsi_Type", "Delivery type (Persian)", "حضوری", lang="fa"),
            F("deadline_farsi", "Registration deadline, Persian text", "۵ خرداد ۱۴۰۲", lang="fa",
              derived_from="deadline_date"),
            F("Time_Farsi", "Duration incl. unit (Persian)", "۱۲ ساعت", lang="fa", derived_from="duration_hours"),
            F("jStart_Date", "Start date, Jalali yyyy/mm/dd", "1402/03/09", lang="fa", derived_from="start_date"),
            F("Date_Horoof", "Start date in words", "نهم خرداد یک هزار و چهارصد و دو", lang="fa",
              derived_from="start_date"),
            F("Day_Farsi", "Course days (Persian)", "یکشنبه و دوشنبه", lang="fa"),
            F("Time", "Time range", "10:00-16:00"),
            F("Sessions_Count", "Number of sessions", "2"),
            F("Course_Name", "Course title (English)", "Time Management", lang="en"),
            F("Type", "Delivery type (English)", "In-Person", lang="en"),
            F("Deadline", "Registration deadline, English text", "Friday-26-May-2023", lang="en",
              derived_from="deadline_date"),
            F("Duration", "Duration incl. unit (English)", "12 Hours", lang="en", derived_from="duration_hours"),
            F("start_Date", "Start date, Gregorian yyyy/mm/dd", "2023/05/30", lang="en", derived_from="start_date"),
            F("Day", "Course days (English)", "Every Sunday & Monday", lang="en"),
            F("link", "Course content link (URL)", "https://lms.example.test/course/1"),
            F("guide_link", "Registration guide link (URL); defaults to `link`", "https://lms.example.test/guide",
              required=False, default=None),
        )),
    "institute_letter": KindSpec(
        "institute_letter", "Letter to the training institute (fa)", False, (
            F("Letter_No", "Letter number", "1403/0001"),
            F("date", "Letter date, Jalali", "1403/05/18", derived_from="letter_date"),
            F("Attachment", "Attachments line", "ندارد", required=False, default="ندارد"),
            F("To", "Addressee institute", "موسسه نمونه"),
            F("Course_Name", "Course title", "مدیریت پروژه"),
            F("Jstart_Date", "Start date, Jalali", "1403/05/23", derived_from="start_date"),
            F("Days", "Course days", "شنبه"),
            F("Time", "Time range", "17:00-21:00"),
            F("Duration", "Duration incl. unit", "24 ساعت", derived_from="duration_hours"),
            F("Method", "Delivery method", "آنلاین"),
            F("company_economic_code", "Company economic code", "0000-0000-0000"),
            F("company_national_id", "Company national ID", "00000000000"),
            F("company_postal_code", "Company postal code", "0000000000"),
            F("company_address", "Company head-office address", "تهران، خیابان نمونه، پلاک ۱"),
        ) + _SIGN,
        (ListSpec("participants", "Participants table", (
            F("name", "Full name", "علی نمونه"), F("national_id", "National ID", "0000000000"),
            F("phone", "Phone", "09120000000"), F("email", "E-mail", "ali@example.test"))),),
        template="institute_letter.docx"),
    "settlement_letter": KindSpec(
        "settlement_letter", "Invoice settlement letter (en)", False, (
            F("addressee", "Addressee first name / title", "Finance Team"),
            F("supplier", "Supplier name", "Example Supplier Co."),
            F("invoice_no", "Invoice number", "INV-0001"),
            F("purpose", "Purpose of invoice (course name)", "Example Course"),
            F("mtc_no", "Section B / MTC number", "MTC-000001"),
            F("start_date_gregorian", "Start date, Gregorian", "2024/12/06", derived_from="start_date"),
            F("start_date_jalali", "Start date, Jalali", "1403/09/16", derived_from="start_date"),
            F("attendee_count", "Attendee count", "5", derived_from="len(attendees)"),
            F("supplier_code", "Supplier code (\"-\" when the supplier has none yet)", "SUP-001", required=False, default="-"),
            F("invoice_total", "Invoice total cost", "202,500,000"),
            F("per_attendee", "Per-attendee cost", "40,500,000", derived_from="invoice_total / attendees"),
            F("sender_name", "Sender first name", "Talent Development Team", required=False,
              default="Talent Development Team"),
        ),
        (ListSpec("attendees", "Attendee rows", (
            F("staff_id", "Staff ID", "EMP0001"),
            F("label", "Row label, normally purpose-MTC-full name (built from full_name if empty); alias: description",
              "Example Course-MTC-000001-Test Person"),
            F("full_name", "Full name (used when label is empty)", "Test Person", required=False),
            F("division_cost_center", "Division-Cost center", "NWG-23700"),
            F("row", "Row number (ignored; rows are numbered 1..n)", "1", required=False),
            F("amount", "This attendee's exact share (derived from the total when empty)", "40500000", required=False)),
            item_aliases={"description": "label"}),),
        aliases={"start_date_greg": "start_date_gregorian", "total": "invoice_total", "rows": "attendees"},
        template="settlement_letter.docx"),
    "level3_request": KindSpec(
        "level3_request", "Level 3 evaluation request to the employee (fa + en)", True, (
            F("Ftitle", "Persian honorific", "جناب آقای", lang="fa", derived_from="gender"),
            F("Fname", "Employee name (Persian)", "علی نمونه", lang="fa"),
            F("En_title", "English honorific", "Mr.", lang="en", derived_from="gender"),
            F("Reporter__Name", "Employee name (English)", "Ali Sample", lang="en"),
            F("Summary", "Course name", "PMBOK V6"),
            F("link", "Ticket URL", "https://icare.example.test/browse/LMS-000001"),
        ), template="level3_request.docx"),
    "level3_manager_check": KindSpec(
        "level3_manager_check", "Level 3 manager confirmation request (fa + en)", True, (
            F("Manager_fTitle", "Manager honorific (Persian)", "جناب آقای", lang="fa"),
            F("Manager_Fname", "Manager name (Persian)", "رضا نمونه", lang="fa"),
            F("Manager_Title", "Manager honorific (English)", "Mr.", lang="en"),
            F("Manager_Name", "Manager name (English)", "Reza Sample", lang="en"),
            F("Reporter_F_tilte", "Employee honorific (Persian) [legacy spelling; alias Reporter_F_title]",
              "جناب آقای", lang="fa"),
            F("Reporter_Fname", "Employee name (Persian)", "علی نمونه", lang="fa"),
            F("Reporter_title", "Employee honorific (English)", "Mr.", lang="en"),
            F("Reporter__Name", "Employee name (English)", "Ali Sample", lang="en"),
            F("Summary", "Course name", "Paging Optimization"),
            F("link", "Ticket URL", "https://icare.example.test/browse/LMS-000002"),
        ), aliases={"Reporter_F_title": "Reporter_F_tilte"}, template="level3_manager_check.docx"),
    "line_manager_approval": KindSpec(
        "line_manager_approval", "Line-manager approval batch (en)", False, (
            F("Title", "Manager honorific", "Mr."),
            F("Mg_name", "Manager name", "Sample Manager"),
        ) + _SIGN,
        (ListSpec("employees", "Employee rows (max 9 per letter)", (
            F("name", "Employee name", "Test Person"), F("summary", "Course name", "Example Course"),
            F("ticket", "Ticket URL", "https://icare.example.test/browse/LMS-000003")), max_items=9),),
        template="line_manager_approval.docx"),
}
SPECS["course_announcement"] = KindSpec(**{**SPECS["course_announcement"].__dict__,
                                           "template": "course_announcement.docx"})
