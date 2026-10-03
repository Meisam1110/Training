"""Single source of wording for every letter: a small block model interpreted by BOTH
templates/build_templates.py (-> .docx with {{placeholders}}) and documents/html.py (-> e-mail body).
One wording per template (the legacy had diverging copies). Placeholders: {{name}} or {{name|fa}}
(`|fa` = convert digits to Persian when the renderer's persian_digits option is on).

Block types (tuples):
  ("banner", asset)                    full-width image
  ("title", text)                      heading
  ("p", text)                          paragraph
  ("bullets", [text, ...])
  ("meta", [(label, value), ...])      'label: value' lines (letter number / date / attachment)
  ("kv", [(label, value), ...])        2-column details table
  ("grid", list_name, [(header, cell), ...])   repeating-row table; cell may use {{list.field}} and {{list._n}}
  ("link", label, url_template)
  ("image", asset, width_cm)
  ("sign", [line, ...])                sign-off lines (lines may be a single hide-if-empty placeholder)
  ("note", text)                       small print
"""
from __future__ import annotations

FA, EN = "fa", "en"

DOCS: dict[str, dict[str, list[tuple]]] = {
    "course_announcement": {
        FA: [
            ("banner", "banner_engagement_fa.png"),
            ("title", "ثبت‌نام در دوره آموزشی | {{Farsi_Course_Name}} ({{Farsi_Type}})"),
            ("p", "همکاران گرامی،"),
            ("p", "با سلام،"),
            ("p", "خرسندیم به اطلاع برسانیم دوره آموزشی {{Farsi_Type}} «{{Farsi_Course_Name}}» به زودی توسط تیم "
                  "تعلق خاطر کارکنان برگزار خواهد شد."),
            ("p", "از آنجایی که در فرآیند نیازسنجی برای حضور در این دوره درخواست داده‌اید، خواهشمندیم حداکثر تا "
                  "پایان روز {{deadline_farsi|fa}} نسبت به ثبت و تکمیل فرم موتیویشن (Motivation Form) در پورتال LMS "
                  "اقدام نمایید."),
            ("kv", [("عنوان دوره", "{{Farsi_Course_Name}}"), ("مدت دوره", "{{Time_Farsi|fa}}"),
                    ("تاریخ شروع", "{{jStart_Date|fa}} ({{Date_Horoof}})"),
                    ("زمان برگزاری", "{{Day_Farsi}} | {{Time|fa}}"),
                    ("تعداد جلسات", "{{Sessions_Count|fa}} جلسه")]),
            ("p", "برای اطلاعات بیشتر از لینک‌های زیر استفاده نمایید:"),
            ("link", "محتوای دوره آموزشی", "{{link}}"),
            ("link", "راهنمای ثبت موتیویشن", "{{guide_link}}"),
            ("p", "نکات قابل توجه:"),
            ("bullets", ["قبل از ثبت موتیویشن، محتوای دوره را بررسی نمایید که مطابق با نیاز آموزشی شما باشد و با "
                         "مدیر مستقیم خود در مورد انتظاراتی که پس از گذراندن این دوره خواهند داشت صحبت نمایید.",
                         "حضور در دوره‌های آموزشی شامل پرداخت اضافه‌کار نمی‌شود؛ در صورت عدم حضور در شرکت در "
                         "ساعات اداری، شما می‌توانید به جای ثبت مرخصی در سیستم محاسبه کارکرد، «مأموریت ساعتی "
                         "درون‌شهری» ثبت نمایید."]),
            ("sign", ["با سپاس", "[[SIGNATURE_IMAGE]]", "{{signer_name_fa}}", "{{signer_title_fa}}", "{{unit_fa}}", "{{department_fa}}"]),
        ],
        EN: [
            ("banner", "banner_engagement_en.png"),
            ("title", "Training Course Registration | {{Course_Name}} ({{Type}})"),
            ("p", "Dear Colleagues,"),
            ("p", "We are pleased to inform you that the {{Type}} training program “{{Course_Name}}” is being "
                  "planned by the Employee Engagement Team."),
            ("p", "Since you have already identified this course as a training need in your IDP, please submit "
                  "your “Motivation Form” in LMS after studying the course details and the notes below."),
            ("p", "Registration deadline: due to capacity limits, please submit your Motivation Form by "
                  "{{Deadline}}."),
            ("kv", [("Course title", "{{Course_Name}} ({{Type}})"), ("Duration", "{{Duration}}"),
                    ("Start date", "{{start_Date}} ({{jStart_Date}})"),
                    ("Time", "{{Day|iso}} | {{Time|ltr}}"), ("Number of sessions", "{{Sessions_Count}}")]),
            ("p", "For further information please use the links below:"),
            ("link", "Course content", "{{link}}"),
            ("link", "Motivation submission guide", "{{guide_link}}"),
            ("p", "Notes:"),
            ("bullets", ["Before submitting your motivation, please review the course content completely and "
                         "discuss with your line manager what he/she expects from you after this course.",
                         "Training courses are excluded from overtime pay; instead of taking hourly leave "
                         "during working hours you can submit a “Local Hourly Mission”."]),
            ("sign", ["Regards,", "Employee Engagement Team", "Human Resources"]),
        ],
    },
    "institute_letter": {
        FA: [
            ("meta", [("شماره", "{{Letter_No|fa}}"), ("تاریخ", "{{date|fa}}"), ("پیوست", "{{Attachment}}")]),
            ("p", "به: {{To}}"),
            ("p", "از: شرکت خدمات ارتباطی ایرانسل"),
            ("p", "با سلام"),
            ("p", "بدین وسیله همکاران ذیل جهت حضور در دوره آموزشی «{{Course_Name}}» که از تاریخ {{Jstart_Date|fa}} "
                  "در روزهای {{Days}} از ساعت {{Time|fa}} به مدت {{Duration|fa}} به صورت {{Method}} برگزار "
                  "خواهد شد، معرفی می‌گردند."),
            ("p", "ضمناً موارد ذیل در خصوص برگزاری دوره مذکور مورد درخواست است:"),
            ("bullets", ["ارائه فرم حضور و غیاب", "برگزاری آزمون پایان دوره در صورت برگزاری برای عموم",
                         "صدور مدرک حضور در دوره", "کتاب مرجع دوره"]),
            ("p", "اطلاعات شرکت‌کنندگان:"),
            ("grid", "participants", [("نام و نام خانوادگی", "{{participants.name}}"),
                                      ("شماره ملی", "{{participants.national_id}}"),
                                      ("شماره تلفن", "{{participants.phone}}"),
                                      ("ایمیل", "{{participants.email}}")]),
            ("p", "مشخصات اقتصادی شرکت خدمات ارتباطی ایرانسل به شرح زیر است:"),
            ("bullets", ["کد اقتصادی: {{company_economic_code|fa}}", "شناسه ملی: {{company_national_id|fa}}",
                         "کد پستی: {{company_postal_code|fa}}", "آدرس دفتر مرکزی: {{company_address}}"]),
            ("sign_formal", ["با احترام", "[[SIGNATURE_IMAGE]]", "{{signer_name_fa}}", "{{signer_title_fa}}", "{{unit_fa}}",
                             "{{department_fa}}", "{{signer_phone|ltr}}", "{{signer_email|ltr}}"]),
        ],
    },
    "settlement_letter": {
        EN: [
            ("p", "Dear {{addressee}},"),
            ("p", "Would you please approve the attached invoice based on the details below."),
            ("kv", [("Supplier name", "{{supplier}}"), ("Invoice No.", "{{invoice_no}}"),
                    ("Purpose of invoice", "{{purpose}}"), ("Section B / MTC No.", "{{mtc_no}}"),
                    ("Start date", "{{start_date_gregorian}} ({{start_date_jalali}})"),
                    ("Attendee count", "{{attendee_count}}"), ("Supplier code", "{{supplier_code}}"),
                    ("Invoice total cost", "{{invoice_total}}"), ("Per-attendee cost (base share)", "{{per_attendee}}")]),
            ("grid", "attendees", [("Row", "{{attendees._n}}"), ("Staff ID", "{{attendees.staff_id}}"),
                                   ("Employee full name", "{{attendees.label}}"),
                                   ("Division-Cost center", "{{attendees.division_cost_center}}"),
                                   ("Amount", "{{attendees.amount}}")]),
            ("sign", ["Regards,", "{{sender_name}}"]),
        ],
    },
    "level3_request": {
        FA: [
            ("banner", "banner_talent_fa.png"),
            ("title", "ارزیابی اثربخشی دوره آموزشی"),
            ("p", "{{Ftitle}} {{Fname}}"),
            ("p", "با سلام،"),
            ("p", "از آنجا که شما در ماه‌های اخیر در دوره آموزشی «{{Summary}}» حضور داشته‌اید، خواهشمند است با "
                  "تکمیل فرم ارزیابی اثربخشی این دوره آموزشی، ما را در ارائه خدمات درخشان یاری نمایید."),
            ("p", "برای ورود بر روی لینک کلیک کنید:"),
            ("link", "{{link}}", "{{link}}"),
            ("p", "بر روی Submit Evaluation Level 3 کلیک کنید و سپس فرم مربوطه را تکمیل نمایید و پس از تکمیل، "
                  "مجدداً بر روی Submit Evaluation Level 3 کلیک نمایید."),
            ("image", "howto_ticket.png", 6.5),
            ("image", "howto_level3_form.png", 4.2),
            ("sign", ["با احترام", "[[SIGNATURE_IMAGE]]", "{{signer_name_fa}}", "{{signer_title_fa}}", "{{unit_fa}}", "{{department_fa}}"]),
        ],
        EN: [
            ("banner", "banner_talent_en.png"),
            ("title", "Training Effectiveness Evaluation"),
            ("p", "Dear {{En_title}} {{Reporter__Name}},"),
            ("p", "Since you have been attending the “{{Summary}}” training course in recent months, please help "
                  "us provide better services by completing the effectiveness evaluation form of this course."),
            ("p", "Click on the link to enter:"),
            ("link", "{{link}}", "{{link}}"),
            ("p", "Click on Submit Evaluation Level 3, complete the form, and after completing it click on "
                  "Submit Evaluation Level 3 again."),
            ("sign", ["Best regards,", "Talent Development Team", "Human Resources"]),
        ],
    },
    "level3_manager_check": {
        FA: [
            ("banner", "banner_talent_fa.png"),
            ("title", "سنجش اثربخشی دوره آموزشی"),
            ("p", "{{Manager_fTitle}} {{Manager_Fname}}"),
            ("p", "با سلام،"),
            ("p", "از آنجایی که {{Reporter_F_tilte}} {{Reporter_Fname}} دوره آموزشی «{{Summary}}» را در "
                  "ماه‌های اخیر گذرانده است، خواهشمند است با تأیید یا رد نظر ثبت‌شده از طرف ایشان، موافقت یا "
                  "مخالفت خود را در مورد میزان اثربخشی این دوره ثبت بفرمایید و ما را در ارائه خدمات بهتر یاری "
                  "نمایید."),
            ("p", "جهت این کار بر روی لینک تیکت کلیک نموده و مطابق با تصویر عمل نمایید:"),
            ("link", "{{link}}", "{{link}}"),
            ("image", "howto_manager_agree.png", 9.0),
            ("note", "در صورت عدم موافقت با نظر کارمند که در صفحه قبل درج شده بود، می‌توانید با انتخاب گزینه "
                     "«خیر» نظر خود را جایگزین نظر ایشان نمایید."),
            ("sign", ["با احترام", "[[SIGNATURE_IMAGE]]", "{{signer_name_fa}}", "{{signer_title_fa}}", "{{unit_fa}}", "{{department_fa}}"]),
        ],
        EN: [
            ("banner", "banner_talent_en.png"),
            ("title", "Training Effectiveness Evaluation"),
            ("p", "Dear {{Manager_Title}} {{Manager_Name}},"),
            ("p", "{{Reporter_title}} {{Reporter__Name}} has attended the “{{Summary}}” training course in recent "
                  "months. Please help us provide better services by agreeing or disagreeing with the "
                  "employee’s comment on the effectiveness evaluation form of this training."),
            ("p", "To do this, click on the ticket link and proceed as shown in the image:"),
            ("link", "{{link}}", "{{link}}"),
            ("note", "If you do not agree with the employee’s comment shown on the previous page, you can select "
                     "“No” to replace it with your own comment."),
            ("sign", ["Best regards,", "Talent Development Team", "Human Resources"]),
        ],
    },
    "line_manager_approval": {
        EN: [
            ("p", "Dear {{Title}} {{Mg_name}},"),
            ("p", "The requests below need your attention and approval. Please click on each ticket and then "
                  "click on the Approve button."),
            ("grid", "employees", [("Employee", "{{employees.name}}"), ("Course name", "{{employees.summary}}"),
                                   ("Ticket link", "{{employees.ticket}}")]),
            ("sign", ["Best regards,", "{{signer_name}}", "{{signer_title}}", "{{signer_phone|ltr}}",
                      "{{signer_email|ltr}}"]),
        ],
    },
}

SUBJECTS = {
    "course_announcement": {FA: "ثبت‌نام در دوره آموزشی | {{Farsi_Course_Name}} ({{Farsi_Type}})",
                            EN: "Training Course Registration | {{Course_Name}} ({{Type}})"},
    "institute_letter": {FA: "معرفی شرکت‌کنندگان دوره {{Course_Name}} - نامه شماره {{Letter_No}}"},
    "settlement_letter": {EN: "Invoice approval request - {{supplier}} - {{invoice_no}}"},
    "level3_request": {FA: "ارزیابی اثربخشی دوره آموزشی", EN: "Training Effectiveness Evaluation"},
    "level3_manager_check": {FA: "سنجش اثربخشی دوره آموزشی", EN: "Training Effectiveness Evaluation"},
    "line_manager_approval": {EN: "Approval request - training requests"},
}
