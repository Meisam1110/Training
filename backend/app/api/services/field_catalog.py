"""The ONE catalogue of template fields (the editor's field picker, preview, validation).

Names, examples and "required for kind" come from Dev-B's ``app.documents.specs`` (single source of truth for the six
letter kinds); this module only adds what the editor needs on top: a Persian label, where the value comes from and its type.
A key missing from the maps below still appears (label = the spec's label, source "system", type "text") and the test
``test_field_catalog_labels_cover_every_spec_field`` fails, so a new spec field cannot silently lack a Persian label.
"""
from __future__ import annotations

from typing import Any

# key -> (label_fa, source, type)
META: dict[str, tuple[str, str, str]] = {
    "Farsi_Course_Name": ("عنوان دوره (فارسی)", "course", "text"), "Course_Name": ("عنوان دوره (انگلیسی)", "course", "text"),
    "Farsi_Type": ("نوع برگزاری (فارسی)", "course", "text"), "Type": ("نوع برگزاری (انگلیسی)", "course", "text"),
    "Time_Farsi": ("مدت دوره با واحد (فارسی)", "course", "text"), "Duration": ("مدت دوره با واحد", "course", "text"),
    "Day_Farsi": ("روزهای برگزاری (فارسی)", "course", "text"), "Day": ("روزهای برگزاری (انگلیسی)", "course", "text"),
    "Days": ("روزهای برگزاری", "course", "text"), "Time": ("ساعت برگزاری", "course", "text"),
    "Sessions_Count": ("تعداد جلسات", "course", "number"), "Summary": ("نام دوره (تیکت)", "course", "text"),
    "purpose": ("موضوع فاکتور (نام دوره)", "course", "text"), "Method": ("روش برگزاری", "run", "text"),
    "jStart_Date": ("تاریخ شروع (شمسی)", "run", "date_jalali"), "Jstart_Date": ("تاریخ شروع (شمسی)", "run", "date_jalali"),
    "Date_Horoof": ("تاریخ شروع به حروف", "run", "text"), "deadline_farsi": ("مهلت ثبت‌نام (شمسی)", "run", "date_jalali"),
    "Deadline": ("مهلت ثبت‌نام (انگلیسی)", "run", "text"), "start_Date": ("تاریخ شروع (میلادی)", "run", "date"),
    "start_date_gregorian": ("تاریخ شروع (میلادی)", "run", "date"), "start_date_jalali": ("تاریخ شروع (شمسی)", "run", "date_jalali"),
    "mtc_no": ("شمارهٔ MTC (بخش B)", "run", "text"), "attendee_count": ("تعداد شرکت‌کنندگان", "run", "number"),
    "invoice_total": ("مبلغ کل فاکتور (ریال)", "run", "money"), "per_attendee": ("سهم هر نفر (ریال)", "run", "money"),
    "invoice_no": ("شمارهٔ فاکتور", "run", "text"),
    "Ftitle": ("عنوان کارمند (فارسی)", "employee", "text"), "Fname": ("نام کارمند (فارسی)", "employee", "text"),
    "En_title": ("عنوان کارمند (انگلیسی)", "employee", "text"), "Reporter__Name": ("نام کارمند (انگلیسی)", "employee", "text"),
    "Reporter_F_tilte": ("عنوان کارمند (فارسی)", "employee", "text"), "Reporter_Fname": ("نام کارمند (فارسی)", "employee", "text"),
    "Reporter_title": ("عنوان کارمند (انگلیسی)", "employee", "text"),
    "participants": ("جدول شرکت‌کنندگان", "employee", "list"), "attendees": ("ردیف‌های تسویه", "employee", "list"),
    "Manager_fTitle": ("عنوان مدیر (فارسی)", "manager", "text"), "Manager_Fname": ("نام مدیر (فارسی)", "manager", "text"),
    "Manager_Title": ("عنوان مدیر (انگلیسی)", "manager", "text"), "Manager_Name": ("نام مدیر (انگلیسی)", "manager", "text"),
    "Title": ("عنوان مدیر", "manager", "text"), "Mg_name": ("نام مدیر", "manager", "text"),
    "employees": ("فهرست کارمندان مدیر", "manager", "list"),
    "To": ("مؤسسهٔ گیرنده", "institute", "text"), "supplier": ("نام تأمین‌کننده", "institute", "text"),
    "supplier_code": ("کد تأمین‌کننده", "institute", "text"),
    "company_economic_code": ("کد اقتصادی شرکت", "company", "text"), "company_national_id": ("شناسه ملی شرکت", "company", "text"),
    "company_postal_code": ("کد پستی شرکت", "company", "text"), "company_address": ("نشانی شرکت", "company", "text"),
    "signer_name": ("نام امضاکننده", "company", "text"), "signer_title": ("سمت امضاکننده", "company", "text"),
    "signer_email": ("ایمیل امضاکننده", "company", "text"), "signer_phone": ("تلفن امضاکننده", "company", "text"),
    "sender_name": ("نام فرستنده", "company", "text"), "addressee": ("گیرندهٔ نامه تسویه", "company", "text"),
    "Attachment": ("سطر پیوست‌ها", "company", "text"),
    "department_fa": ("نام دپارتمان (فارسی)", "company", "text"), "unit_fa": ("نام واحد (فارسی)", "company", "text"),
    "signer_name_fa": ("نام امضاکننده (فارسی)", "company", "text"), "signer_title_fa": ("سمت امضاکننده (فارسی)", "company", "text"),
    "link": ("پیوند (تیکت/دوره)", "links", "url"), "guide_link": ("پیوند راهنمای ثبت‌نام", "links", "url"),
    "Letter_No": ("شمارهٔ نامه", "system", "text"), "date": ("تاریخ نامه (شمسی)", "system", "date_jalali"),
}

LETTER_KINDS = ("course_announcement", "institute_letter", "settlement_letter", "level3_request", "level3_manager_check", "line_manager_approval")
EMAIL_KINDS = ("email_announcement", "email_reminder", "email_level3", "email_manager_check", "email_institute", "email_settlement", "email_generic")
ALL_KINDS = LETTER_KINDS + EMAIL_KINDS
# an e-mail kind draws its data from the letter kind it accompanies (reminder/generic: the announcement's course data)
EMAIL_SOURCE = {"email_announcement": "course_announcement", "email_reminder": "course_announcement", "email_generic": "course_announcement",
                "email_level3": "level3_request", "email_manager_check": "level3_manager_check", "email_institute": "institute_letter",
                "email_settlement": "settlement_letter"}


def source_kind(kind: str) -> str:
    return EMAIL_SOURCE.get(kind, kind)


def _specs() -> dict[str, Any]:
    from app.documents.specs import SPECS
    return SPECS


def _sample_list(spec_list) -> list[dict[str, str]]:
    return [{f.name: f.example for f in spec_list.item_fields} for _ in range(2)]


def catalog() -> list[dict[str, Any]]:
    specs = _specs()
    by_key: dict[str, dict[str, Any]] = {}
    for kind, sp in specs.items():
        entries = [(f.name, f.label, f.example, f.required, False, None) for f in sp.fields]
        entries += [(ls.name, ls.label, _sample_list(ls), True, True, ls) for ls in sp.lists]
        for key, label, sample, required, is_list, ls in entries:
            fa, src, typ = META.get(key, (label, "system", "list" if is_list else "text"))
            e = by_key.setdefault(key, {"key": key, "label_fa": fa, "source": src, "type": typ, "sample_fa": sample, "required_for_kinds": [],
                                        "item_keys": [f.name for f in ls.item_fields] if ls else []})
            if required and kind not in e["required_for_kinds"]:
                e["required_for_kinds"].append(kind)
    return sorted(by_key.values(), key=lambda e: (e["source"], e["key"]))


def known_keys() -> set[str]:
    return {e["key"] for e in catalog()}


def sample_fields() -> dict[str, Any]:
    """Sample value for every catalogued field -- used by preview / send-test when no real run or enrollment is given."""
    return {e["key"]: e["sample_fa"] for e in catalog()}


ALIASES = (("total", "invoice_total"), ("start_date_greg", "start_date_gregorian"), ("rows", "attendees"))


def with_aliases(fields: dict[str, Any]) -> dict[str, Any]:
    """Letters are built with the renderer's accepted names; the catalogue uses the specs' canonical ones -- expose both."""
    f = dict(fields)
    for alias, canonical in ALIASES:
        if alias in f and canonical not in f:
            f[canonical] = f[alias]
    return f
