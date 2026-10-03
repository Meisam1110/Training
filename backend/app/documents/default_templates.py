"""Default SYSTEM templates (Persian) as data, for Dev-A to seed. Bodies use catalog tokens (see
``specs.field_catalog()``); ``{{key?}}`` marks an optional field. All content is synthetic-free text:
no names, numbers or addresses. Render with ``DocxLetterRenderer.render_custom(subject, body_html, fields)``.
Terminology: «موتیویشن» (Motivation Form), «ثبت‌نام», «تیم توسعه استعدادها», «منابع انسانی»."""
from __future__ import annotations

import copy
import re

_SIGN = ("<p>{{closing?}}<br>{{signer_name_fa?}}<br>{{signer_title_fa?}}<br>{{unit_fa?}}<br>{{department_fa?}}</p>")
_SIGN_PLAIN = lambda closing: _SIGN.replace("{{closing?}}", closing)  # noqa: E731

_TABLE_DETAILS = (
    "<table>"
    "<tr><th>عنوان دوره</th><td>{{course_name_fa}}</td></tr>"
    "<tr><th>مدت دوره</th><td>{{duration_fa}}</td></tr>"
    "<tr><th>تاریخ شروع</th><td>{{start_date_jalali}} ({{start_date_words?}})</td></tr>"
    "<tr><th>زمان برگزاری</th><td>{{days_fa}} | {{time|ltr}}</td></tr>"
    "<tr><th>تعداد جلسات</th><td>{{sessions_count}} جلسه</td></tr>"
    "</table>"
)

DEFAULT_TEMPLATES: list[dict] = [
    {
        "key": "announcement", "kind": "course_announcement", "lang": "fa",
        "title_fa": "اطلاع‌رسانی دوره آموزشی",
        "description_fa": "اعلام برگزاری دوره و درخواست ثبت موتیویشن تا مهلت مقرر",
        "subject": "ثبت‌نام در دوره آموزشی | {{course_name_fa}} ({{course_type_fa}})",
        "body_html": (
            "<h2>ثبت‌نام در دوره آموزشی | {{course_name_fa}} ({{course_type_fa}})</h2>"
            "<p>همکاران گرامی،</p><p>با سلام،</p>"
            "<p>خرسندیم به اطلاع برسانیم دوره آموزشی {{course_type_fa}} «{{course_name_fa}}» به زودی برگزار خواهد شد.</p>"
            "<p>از آنجایی که در فرآیند نیازسنجی برای حضور در این دوره درخواست داده‌اید، خواهشمندیم حداکثر تا پایان روز "
            "{{deadline_fa}} نسبت به ثبت و تکمیل فرم موتیویشن (Motivation Form) در پورتال LMS اقدام نمایید.</p>"
            + _TABLE_DETAILS +
            "<p>برای اطلاعات بیشتر از پیوندهای زیر استفاده نمایید:</p>"
            '<ul><li><a href="{{link}}">محتوای دوره آموزشی</a></li>'
            '<li><a href="{{guide_link?}}">راهنمای ثبت موتیویشن</a></li></ul>'
            "<p><b>نکات قابل توجه:</b></p>"
            "<ul><li>قبل از ثبت موتیویشن، محتوای دوره را بررسی نمایید که مطابق با نیاز آموزشی شما باشد و با مدیر مستقیم "
            "خود درباره انتظاراتی که پس از گذراندن این دوره خواهند داشت گفتگو کنید.</li>"
            "<li>حضور در دوره‌های آموزشی شامل پرداخت اضافه‌کار نمی‌شود؛ در صورت عدم حضور در شرکت در ساعات اداری، شما "
            "می‌توانید به جای ثبت مرخصی در سیستم محاسبه کارکرد، «مأموریت ساعتی درون‌شهری» ثبت نمایید.</li></ul>"
            + _SIGN_PLAIN("با سپاس")),
    },
    {
        "key": "reminder", "kind": "course_announcement", "lang": "fa",
        "title_fa": "یادآوری مهلت ثبت موتیویشن",
        "description_fa": "یادآوری به همکارانی که تا نزدیکی مهلت، فرم موتیویشن را تکمیل نکرده‌اند",
        "subject": "یادآوری: مهلت ثبت موتیویشن دوره {{course_name_fa}}",
        "body_html": (
            "<h2>یادآوری مهلت ثبت موتیویشن</h2>"
            "<p>{{employee_title_fa?}} {{employee_name_fa?}}</p><p>با سلام،</p>"
            "<p>مهلت ثبت و تکمیل فرم موتیویشن (Motivation Form) برای دوره آموزشی «{{course_name_fa}}» "
            "تا پایان روز {{deadline_fa}} است. خواهشمندیم در صورت تمایل به حضور در این دوره، پیش از پایان مهلت اقدام "
            "نمایید؛ پس از آن امکان ثبت‌نام وجود نخواهد داشت.</p>"
            '<p><a href="{{link}}">محتوای دوره آموزشی</a></p>'
            + _SIGN_PLAIN("با سپاس")),
    },
    {
        "key": "level3", "kind": "level3_request", "lang": "fa",
        "title_fa": "ارزیابی اثربخشی دوره (سطح ۳) - همکار",
        "description_fa": "درخواست تکمیل فرم ارزیابی اثربخشی از شرکت‌کننده، پس از پایان دوره",
        "subject": "ارزیابی اثربخشی دوره آموزشی",
        "body_html": (
            "<h2>ارزیابی اثربخشی دوره آموزشی</h2>"
            "<p>{{employee_title_fa}} {{employee_name_fa}}</p><p>با سلام،</p>"
            "<p>از آنجا که شما در ماه‌های اخیر در دوره آموزشی «{{course_title}}» حضور داشته‌اید، خواهشمند است با تکمیل "
            "فرم ارزیابی اثربخشی این دوره آموزشی، ما را در ارائه خدمات بهتر یاری نمایید.</p>"
            '<p>برای ورود بر روی پیوند زیر کلیک کنید:<br><a href="{{link}}">{{link}}</a></p>'
            "<p>بر روی <b>Submit Evaluation Level 3</b> کلیک کنید، فرم را تکمیل نمایید و پس از تکمیل، مجدداً بر روی "
            "<b>Submit Evaluation Level 3</b> کلیک نمایید.</p>"
            + _SIGN_PLAIN("با احترام")),
    },
    {
        "key": "manager_check", "kind": "level3_manager_check", "lang": "fa",
        "title_fa": "سنجش اثربخشی دوره - مدیر مستقیم",
        "description_fa": "درخواست تأیید یا رد نظر ثبت‌شده همکار درباره اثربخشی دوره از مدیر مستقیم",
        "subject": "سنجش اثربخشی دوره آموزشی",
        "body_html": (
            "<h2>سنجش اثربخشی دوره آموزشی</h2>"
            "<p>{{manager_title_fa}} {{manager_name_fa}}</p><p>با سلام،</p>"
            "<p>از آنجایی که {{employee_title_fa}} {{employee_name_fa}} دوره آموزشی «{{course_title}}» را در ماه‌های اخیر "
            "گذرانده است، خواهشمند است با تأیید یا رد نظر ثبت‌شده از طرف ایشان، موافقت یا مخالفت خود را درباره میزان "
            "اثربخشی این دوره ثبت بفرمایید و ما را در ارائه خدمات بهتر یاری نمایید.</p>"
            '<p>برای این کار بر روی پیوند تیکت کلیک کنید:<br><a href="{{link}}">{{link}}</a></p>'
            "<p>در صورت عدم موافقت با نظر همکار، می‌توانید با انتخاب گزینه «خیر» نظر خود را جایگزین نظر ایشان نمایید.</p>"
            + _SIGN_PLAIN("با احترام")),
    },
    {
        "key": "institute", "kind": "institute_letter", "lang": "fa",
        "title_fa": "نامه رسمی به موسسه آموزشی",
        "description_fa": "معرفی شرکت‌کنندگان دوره به موسسه آموزشی (قابل تبدیل به نامه روی سربرگ)",
        "subject": "معرفی شرکت‌کنندگان دوره {{course_name_fa}} - نامه شماره {{letter_no}}",
        "body_html": (
            "<p>شماره: {{letter_no|fa}}<br>تاریخ: {{letter_date_jalali|fa}}<br>پیوست: {{attachment?}}</p>"
            "<p>به: {{institute_name}}<br>از: شرکت خدمات ارتباطی ایرانسل</p><p>با سلام</p>"
            "<p>بدین وسیله همکاران ذیل جهت حضور در دوره آموزشی «{{course_name_fa}}» که از تاریخ {{start_date_jalali|fa}} "
            "در روزهای {{days_fa}} از ساعت {{time|fa}} به مدت {{duration_fa}} به صورت {{delivery_method}} برگزار خواهد شد، "
            "معرفی می‌گردند.</p>"
            "<p>ضمناً موارد ذیل در خصوص برگزاری دوره مذکور مورد درخواست است:</p>"
            "<ul><li>ارائه فرم حضور و غیاب</li><li>برگزاری آزمون پایان دوره در صورت برگزاری برای عموم</li>"
            "<li>صدور مدرک حضور در دوره</li><li>کتاب مرجع دوره</li></ul>"
            "<p>اطلاعات شرکت‌کنندگان:</p><p>{{participants}}</p>"
            "<p>مشخصات اقتصادی شرکت خدمات ارتباطی ایرانسل به شرح زیر است:</p>"
            "<ul><li>کد اقتصادی: {{company_economic_code?|fa}}</li><li>شناسه ملی: {{company_national_id?|fa}}</li>"
            "<li>کد پستی: {{company_postal_code?|fa}}</li><li>آدرس دفتر مرکزی: {{company_address?}}</li></ul>"
            + _SIGN_PLAIN("با احترام")),
    },
    {
        "key": "settlement", "kind": "settlement_letter", "lang": "fa",
        "title_fa": "درخواست تأیید فاکتور (تسویه)",
        "description_fa": "ارسال اطلاعات فاکتور موسسه به واحد مالی برای تأیید و تسویه",
        "subject": "درخواست تأیید فاکتور - {{institute_name}} - {{invoice_no}}",
        "body_html": (
            "<p>{{addressee}} محترم،</p><p>با سلام،</p>"
            "<p>خواهشمند است فاکتور پیوست را بر اساس اطلاعات زیر تأیید فرمایید.</p>"
            "<table>"
            "<tr><th>نام موسسه (تأمین‌کننده)</th><td>{{institute_name}}</td></tr>"
            "<tr><th>شماره فاکتور</th><td>{{invoice_no}}</td></tr>"
            "<tr><th>موضوع فاکتور</th><td>{{purpose}}</td></tr>"
            "<tr><th>شماره Section B</th><td>{{section_b}}</td></tr>"
            "<tr><th>تاریخ شروع دوره</th><td>{{start_date_jalali|fa}}</td></tr>"
            "<tr><th>تعداد شرکت‌کنندگان</th><td>{{attendee_count|fa}}</td></tr>"
            "<tr><th>کد تأمین‌کننده</th><td>{{supplier_code?}}</td></tr>"
            "<tr><th>مبلغ کل فاکتور</th><td>{{invoice_total|fa}}</td></tr>"
            "<tr><th>سهم هر نفر</th><td>{{per_attendee|fa}}</td></tr></table>"
            "<p>{{attendees?}}</p>"
            + _SIGN_PLAIN("با تشکر")),
    },
    {
        "key": "generic", "kind": "generic", "lang": "fa",
        "title_fa": "پیام عمومی",
        "description_fa": "قالب ساده برای پیام‌های متفرقه؛ متن را ویرایش کنید",
        "subject": "{{course_name_fa?}}",
        "body_html": (
            "<p>{{employee_title_fa?}} {{employee_name_fa?}}</p><p>با سلام،</p>"
            "<p>متن پیام خود را در اینجا بنویسید.</p>"
            + _SIGN_PLAIN("با احترام")),
    },
]


def default_templates() -> list[dict]:
    """Fresh deep copies (with ``fields_used``: the sorted token names in subject and body)."""
    out = copy.deepcopy(DEFAULT_TEMPLATES)
    tok = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)")
    for t in out:
        t["fields_used"] = sorted(set(tok.findall(t["subject"] + t["body_html"])) - {"closing"})
    return out
