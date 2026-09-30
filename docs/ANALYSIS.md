# Analysis of the legacy system (no personal data in this file)

## Flow
IFS (employees) + iCare IDP export → Form (pick course) → Translator → announcement mail;
Record/CHistory log; Payment-Letter Maker → institute letter + settlement letter;
Level3 / Level3 Cheking / Line Manager Approval sheets → three merge letters.

## Workbook sheets
IFS (employee master, cols: Emp No, Employee Status, Employment Type, Org Code, Organization Name,
Cost Center, Fname, Lname, Gender, Mobile, Email, Farsi First/Last Name, Position Title, Job Level,
Company Office, Sup Emp No/Name/Mobile/Emaile, Education, Date Of Birth, Start Date, Position Code,
Job Id, Id No, National Code, Division).
IDP (iCare export; headers on row 5): Employee ID, Reporter:  Name ("Name [ MTNIrancell - CR ]"),
Job Level, Reporter Department, Summary(=course name), Delivery Method, Current Status, IDP Type,
Course Category, Attendance Status, Course Start Date, Course End Date, Ticket (LMS-n), Section B (MTC-n or "-").
Helper logic: course match by SEARCH(Form!B2, Summary) with Attendance "-"; date-overlap test between
run and other courses; >3 non-"Yes" motivations per ticket; Level 3 when Current Status="Evaluation Level 3"
and today-end>60d and category "soft skill"; Level 3 checking likewise; line-manager batches (max 9/manager);
division-change check vs IFS; non-active employee check.
CHistory (per run): Row, Course Name, Course NameFarsi, Type, Institute, Duration, jStart Date, End Date,
start Date, Time, Sessions Count, Day, Send Date, Deadline, Email Sent to, Motivation, Percent, SectionB,
Registration, Calendar, Payment Process, Invoice Receive Date, PR process Start Date, Amount, Certificate, Link,
Days To course, End date, Key(course+institute+start).
Record (per person+run): ID, Fullname, DIV, Email, sup Email, Ticket, Course…, Motivation, SectionB,
Registration, Calendar, Payment, Comment, link, Amount.
Payment: invoice total = Amount × #motivations; per-attendee = total / attendees; rows list Staff ID,
"course-SectionB-fullname", "division-costcenter".

## Templates and MERGEFIELDs
- course_announcement (Translator$): Farsi_Course_Name, Farsi_Type, deadline_farsi, Time_Farsi, jStart_Date,
  Date_Horoof, Day_Farsi, Time, Sessions_Count | Course_Name, Type, Deadline, Duration, start_Date, Day, link
- institute_letter (Letter Translator$): Letter_No, date(dd/mm/yy jalali), To, Course_Name, Jstart_Date, Days,
  Time, Duration, Method + participants table (name, national id, phone, email)
- settlement_letter: supplier, invoice no, purpose, MTC no, start date (greg+jalali), attendee count, supplier code,
  total, per-attendee, table (row, staff id, "course-MTC-name", division-costcenter). Addressee configurable.
- level3_request (Level3$): Ftitle, Fname, En_title, Reporter__Name, Summary, link
- level3_manager_check (Level3 Cheking$): Manager_fTitle, Manager_Fname, Manager_Title, Manager_Name,
  Reporter_F_tilte, Reporter_Fname, Reporter_title, Reporter__Name, Summary, link
- line_manager_approval: Title, Mg_name, Empname1..9, EmpSummary1..9, EmpTicket1..9
Ticket URL pattern: https://icare.mtnirancell.ir/browse/<KEY>. Sign-off: Talent Development Team, Human Resources.

## Known defects to NOT reproduce
IDP!Y6 has #REF!; hardcoded 240,000,000 budget unit and `*3` in Course Status; hardcoded drive paths (E:\, D:\);
typed-in letter counter; inconsistent deadline/day/typo between mail versions (single source of truth = CourseRun);
SendDocAsMail invalid statements masked by On Error Resume Next; Persian year hack SUBSTITUTE(…,1499,1399);
Form range capped at 225 rows; PII (national code, mobile, DOB) in plain cells.
