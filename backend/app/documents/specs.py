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

def _sign_fa(unit: str) -> tuple[F, ...]:
    """Persian signature block (all optional; defaults are Persian). Feed from the admin settings."""
    return (
        F("signer_name_fa", "نام امضاکننده", "علی نمونه", required=False, default="", hide_if_empty=True),
        F("signer_title_fa", "سمت امضاکننده", "کارشناس توسعه استعدادها", required=False, default="", hide_if_empty=True),
        F("unit_fa", "واحد فرستنده", unit, required=False, default=unit),
        F("department_fa", "معاونت/حوزه", "منابع انسانی", required=False, default="منابع انسانی", hide_if_empty=True),
        F("signer_email", "ایمیل امضاکننده", "training@example.test", required=False, default="", hide_if_empty=True),
        F("signer_phone", "تلفن امضاکننده", "+98-21-00000000", required=False, default="", hide_if_empty=True),
    )


_SIGN_ALIASES = {"signer_name": "signer_name_fa", "signer_title": "signer_title_fa"}

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
        ) + _sign_fa("تیم تعلق خاطر کارکنان"), aliases=_SIGN_ALIASES),
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
        ) + _sign_fa("تیم توسعه استعدادها"),
        (ListSpec("participants", "Participants table", (
            F("name", "Full name", "علی نمونه"), F("national_id", "National ID", "0000000000"),
            F("phone", "Phone", "09120000000"), F("email", "E-mail", "ali@example.test"))),),
        aliases=_SIGN_ALIASES, template="institute_letter.docx"),
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
        ) + _sign_fa("تیم توسعه استعدادها"), aliases=_SIGN_ALIASES, template="level3_request.docx"),
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
        ) + _sign_fa("تیم توسعه استعدادها"),
        aliases={"Reporter_F_title": "Reporter_F_tilte", **_SIGN_ALIASES}, template="level3_manager_check.docx"),
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


# ---------------------------------------------------------------------------------------------
# Field catalog: every merge field the six kinds use, with Persian labels and SYNTHETIC samples.
# `key` is the friendly snake_case token used in custom (user-created) templates; `legacy` lists the
# canonical names the six built-in kinds use for the same value (both spellings are accepted by
# render_custom). Dev-A's /templates/fields endpoint serves field_catalog().
# (key, legacy names, label_fa, source, type, sample_fa)
_CATALOG: tuple[tuple[str, tuple[str, ...], str, str, str, str], ...] = (
    ("course_name_fa", ("Farsi_Course_Name",), "عنوان دوره (فارسی)", "course", "text", "مدیریت زمان"),
    ("course_name", ("Course_Name",), "عنوان دوره (انگلیسی)", "course", "text", "Time Management"),
    ("course_title", ("Summary",), "نام دوره در iCare", "course", "text", "مدیریت پروژه PMBOK"),
    ("course_type_fa", ("Farsi_Type",), "نوع برگزاری (فارسی)", "course", "text", "حضوری"),
    ("course_type", ("Type",), "نوع برگزاری (انگلیسی)", "course", "text", "In-Person"),
    ("delivery_method", ("Method",), "روش برگزاری", "course", "text", "آنلاین"),
    ("duration_fa", ("Time_Farsi",), "مدت دوره (فارسی، با واحد)", "course", "text", "۱۲ ساعت"),
    ("duration_en", ("Duration",), "مدت دوره (با واحد)", "course", "text", "12 Hours"),
    ("start_date_jalali", ("jStart_Date", "Jstart_Date", "start_date_jalali"), "تاریخ شروع (شمسی)", "run", "date_jalali",
     "1405/07/25"),
    ("start_date_words", ("Date_Horoof",), "تاریخ شروع (به حروف)", "run", "text", "بیست و پنجم مهر یک هزار و چهارصد و پنج"),
    ("start_date_greg", ("start_Date", "start_date_gregorian"), "تاریخ شروع (میلادی)", "run", "date", "2026/10/17"),
    ("days_fa", ("Day_Farsi", "Days"), "روزهای برگزاری", "run", "text", "شنبه و یکشنبه"),
    ("days_en", ("Day",), "روزهای برگزاری (انگلیسی)", "run", "text", "Every Saturday & Sunday"),
    ("time", ("Time",), "ساعت برگزاری", "run", "text", "09:00-16:00"),
    ("sessions_count", ("Sessions_Count",), "تعداد جلسات", "run", "number", "2"),
    ("deadline_fa", ("deadline_farsi",), "مهلت ثبت‌نام (فارسی)", "run", "date_jalali", "5 آبان 1405"),
    ("deadline_en", ("Deadline",), "مهلت ثبت‌نام (انگلیسی)", "run", "date", "Friday-23-Oct-2026"),
    ("section_b", ("mtc_no",), "شماره Section B (MTC)", "run", "text", "MTC-000123"),
    ("employee_name_fa", ("Fname", "Reporter_Fname"), "نام و نام خانوادگی همکار (فارسی)", "employee", "text", "علی نمونه"),
    ("employee_name_en", ("Reporter__Name",), "نام و نام خانوادگی همکار (انگلیسی)", "employee", "text", "Ali Sample"),
    ("employee_title_fa", ("Ftitle", "Reporter_F_tilte"), "عنوان خطاب همکار (فارسی)", "employee", "text", "جناب آقای"),
    ("employee_title_en", ("En_title", "Reporter_title"), "عنوان خطاب همکار (انگلیسی)", "employee", "text", "Mr."),
    ("manager_name_fa", ("Manager_Fname",), "نام مدیر (فارسی)", "manager", "text", "رضا نمونه"),
    ("manager_name_en", ("Manager_Name", "Mg_name"), "نام مدیر (انگلیسی)", "manager", "text", "Reza Sample"),
    ("manager_title_fa", ("Manager_fTitle",), "عنوان خطاب مدیر (فارسی)", "manager", "text", "جناب آقای"),
    ("manager_title_en", ("Manager_Title", "Title"), "عنوان خطاب مدیر (انگلیسی)", "manager", "text", "Mr."),
    ("institute_name", ("To", "supplier"), "نام موسسه آموزشی", "institute", "text", "موسسه نمونه"),
    ("supplier_code", ("supplier_code",), "کد تامین‌کننده", "institute", "text", "SUP-001"),
    ("invoice_no", ("invoice_no",), "شماره فاکتور", "institute", "text", "INV-0001"),
    ("purpose", ("purpose",), "موضوع فاکتور (نام دوره)", "institute", "text", "دوره نمونه"),
    ("invoice_total", ("invoice_total",), "مبلغ کل فاکتور", "institute", "money", "202,500,000"),
    ("per_attendee", ("per_attendee",), "سهم هر نفر", "institute", "money", "40,500,000"),
    ("attendee_count", ("attendee_count",), "تعداد شرکت‌کنندگان", "institute", "number", "5"),
    ("addressee", ("addressee",), "گیرنده نامه", "institute", "text", "واحد مالی"),
    ("company_economic_code", ("company_economic_code",), "کد اقتصادی شرکت", "company", "text", "0000-0000-0000"),
    ("company_national_id", ("company_national_id",), "شناسه ملی شرکت", "company", "text", "00000000000"),
    ("company_postal_code", ("company_postal_code",), "کد پستی شرکت", "company", "text", "0000000000"),
    ("company_address", ("company_address",), "نشانی دفتر مرکزی", "company", "text", "تهران، خیابان نمونه، پلاک ۱"),
    ("signer_name_fa", ("signer_name_fa",), "نام امضاکننده", "company", "text", "علی نمونه"),
    ("signer_title_fa", ("signer_title_fa",), "سمت امضاکننده", "company", "text", "کارشناس توسعه استعدادها"),
    ("unit_fa", ("unit_fa",), "واحد فرستنده", "company", "text", "تیم توسعه استعدادها"),
    ("department_fa", ("department_fa",), "معاونت / حوزه", "company", "text", "منابع انسانی"),
    ("signer_email", ("signer_email",), "ایمیل امضاکننده", "company", "text", "training@example.test"),
    ("signer_phone", ("signer_phone",), "تلفن امضاکننده", "company", "text", "+98-21-00000000"),
    ("signer_name", ("signer_name", "sender_name"), "نام امضاکننده (انگلیسی)", "company", "text", "Talent Development Team"),
    ("signer_title", ("signer_title",), "سمت امضاکننده (انگلیسی)", "company", "text", "Human Resources"),
    ("link", ("link",), "پیوند اصلی (دوره / تیکت)", "links", "url", "https://lms.example.test/course/1"),
    ("guide_link", ("guide_link",), "پیوند راهنمای ثبت", "links", "url", "https://lms.example.test/guide"),
    ("letter_no", ("Letter_No",), "شماره نامه", "system", "text", "1405/0001"),
    ("letter_date_jalali", ("date",), "تاریخ نامه (شمسی)", "system", "date_jalali", "1405/07/12"),
    ("attachment", ("Attachment",), "پیوست", "system", "text", "ندارد"),
    ("today_jalali", (), "تاریخ امروز (شمسی)", "system", "date_jalali", "1405/07/12"),
    ("participants", ("participants",), "جدول شرکت‌کنندگان (موسسه)", "employee", "list", "علی نمونه، سارا آزمایشی"),
    ("attendees", ("attendees",), "جدول شرکت‌کنندگان (تسویه)", "employee", "list", "EMP0001، EMP0002"),
    ("employees", ("employees",), "جدول درخواست‌های همکاران (تأیید مدیر)", "employee", "list", "علی نمونه، سارا آزمایشی"),
    ("participant_name", ("participants.name",), "نام شرکت‌کننده", "employee", "text", "علی نمونه"),
    ("participant_national_id", ("participants.national_id",), "کد ملی شرکت‌کننده", "employee", "text", "0000000001"),
    ("participant_phone", ("participants.phone",), "تلفن شرکت‌کننده", "employee", "text", "09120000001"),
    ("participant_email", ("participants.email",), "ایمیل شرکت‌کننده", "employee", "text", "ali@example.test"),
    ("attendee_staff_id", ("attendees.staff_id",), "شماره پرسنلی", "employee", "text", "EMP0001"),
    ("attendee_label", ("attendees.label",), "شرح ردیف (دوره-MTC-نام)", "employee", "text", "دوره نمونه-MTC-000123-Ali Sample"),
    ("attendee_full_name", ("attendees.full_name",), "نام کامل (انگلیسی)", "employee", "text", "Ali Sample"),
    ("attendee_division_cost_center", ("attendees.division_cost_center",), "واحد-مرکز هزینه", "employee", "text", "NWG-23700"),
    ("attendee_row", ("attendees.row",), "شماره ردیف", "employee", "number", "1"),
    ("attendee_amount", ("attendees.amount",), "سهم دقیق هر نفر", "employee", "money", "40,500,000"),
    ("employee_row_name", ("employees.name",), "نام همکار (ردیف)", "employee", "text", "Ali Sample"),
    ("employee_row_course", ("employees.summary",), "نام دوره (ردیف)", "employee", "text", "دوره نمونه"),
    ("employee_row_ticket", ("employees.ticket",), "پیوند تیکت (ردیف)", "employee", "url", "https://icare.example.test/browse/LMS-000003"),
)


def _used_by_kinds() -> dict[str, tuple[set[str], set[str]]]:
    """legacy name -> (kinds using it, kinds requiring it)."""
    used: dict[str, tuple[set[str], set[str]]] = {}
    for kind, sp in SPECS.items():
        entries = [(f.name, f.required) for f in sp.fields]
        for ls in sp.lists:
            entries.append((ls.name, ls.min_items > 0))
            entries += [(f"{ls.name}.{f.name}", f.required) for f in ls.item_fields]
        for name, req in entries:
            u, r = used.setdefault(name, (set(), set()))
            u.add(kind)
            if req:
                r.add(kind)
    return used


def field_catalog() -> list[dict]:
    """Merge-field catalog for the template editor: one dict per field with keys
    ``key, label_fa, source, type, sample_fa, required_for_kinds`` plus ``legacy`` (names used by the
    six built-in kinds), ``used_in_kinds`` and ``optional``. ``source`` is one of course|run|employee|
    manager|institute|company|links|system; ``type`` one of text|date_jalali|date|number|money|url|list.
    Samples are synthetic. Returns fresh copies (safe to mutate)."""
    used = _used_by_kinds()
    out = []
    for key, legacy, label, source, typ, sample in _CATALOG:
        kinds_used: set[str] = set()
        kinds_req: set[str] = set()
        for name in legacy:
            u, r = used.get(name, (set(), set()))
            kinds_used |= u
            kinds_req |= r
        out.append({"key": key, "label_fa": label, "source": source, "type": typ, "sample_fa": sample,
                    "required_for_kinds": sorted(kinds_req), "used_in_kinds": sorted(kinds_used),
                    "legacy": list(legacy), "optional": not kinds_req})
    return out


def catalog_index() -> dict[str, dict]:
    """token name (friendly key OR legacy name) -> catalog entry."""
    idx: dict[str, dict] = {}
    for e in field_catalog():
        idx[e["key"]] = e
        for name in e["legacy"]:
            idx.setdefault(name, e)
    return idx
