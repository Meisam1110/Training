"""Synthetic field sets for every letter kind (no real data)."""
from datetime import date

TEMPLATES_DIR = str(__import__("pathlib").Path(__file__).resolve().parents[3] / "templates")

SIGN = {"signer_name": "Sample Sender", "signer_title": "Talent Development Specialist",
        "signer_email": "sender@example.test", "signer_phone": "+98-21-00000000"}

SAMPLES = {
    "course_announcement": {
        "Farsi_Course_Name": "گفتگو در میدان مین", "Farsi_Type": "حضوری", "Day_Farsi": "یکشنبه و دوشنبه",
        "Time": "10:00-16:00", "Sessions_Count": 2, "Course_Name": "Crucial Conversation", "Type": "In-Person",
        "Day": "Every Sunday & Monday", "link": "https://lms.example.test/course/1",
        "start_date": date(2023, 5, 30), "deadline_date": date(2023, 5, 26), "duration_hours": 12},
    "institute_letter": {
        "Letter_No": "1403/0001", "letter_date": date(2024, 8, 8), "To": "موسسه نمونه", "Course_Name": "مدیریت پروژه",
        "start_date": date(2024, 8, 13), "Days": "شنبه", "Time": "17:00-21:00", "duration_hours": 24,
        "Method": "آنلاین", "company_economic_code": "0000-0000-0000", "company_national_id": "00000000000",
        "company_postal_code": "0000000000", "company_address": "تهران، خیابان نمونه، کوچه آزمایشی، پلاک ۱",
        "participants": [
            {"name": "علی نمونه", "national_id": "0000000001", "phone": "09120000001", "email": "ali@example.test"},
            {"name": "سارا آزمایشی", "national_id": "0000000002", "phone": "09120000002", "email": "sara@example.test"}],
        **SIGN},
    "settlement_letter": {
        "addressee": "Finance Team", "supplier": "Example Supplier Co.", "invoice_no": "INV-0001",
        "purpose": "Example Course (EX100)", "mtc_no": "MTC-000001", "start_date": date(2024, 12, 6),
        "supplier_code": "SUP-001", "invoice_total": 202500000,
        "attendees": [{"staff_id": f"EMP{i:04d}", "full_name": f"Test Person{i}", "division_cost_center": "NWG-23700"}
                      for i in range(1, 6)]},
    "level3_request": {"gender": "male", "Fname": "علی نمونه", "Reporter__Name": "Ali Sample", "Summary": "PMBOK V6",
                       "link": "https://icare.example.test/browse/LMS-000001"},
    "level3_manager_check": {"manager_gender": "male", "Manager_Fname": "رضا نمونه", "Manager_Name": "Reza Sample",
                             "reporter_gender": "female", "Reporter_Fname": "سارا آزمایشی",
                             "Reporter__Name": "Sara Sample", "Summary": "Paging and Common Channel Optimization",
                             "link": "https://icare.example.test/browse/LMS-000002"},
    "line_manager_approval": {"Title": "Mr.", "Mg_name": "Sample Manager", **SIGN,
                              "employees": [{"name": f"Test Person{i}", "summary": f"Example Course {i}",
                                             "ticket": f"https://icare.example.test/browse/LMS-00000{i}"}
                                            for i in range(1, 4)]},
}
