"""Edge-case employees through all letter kinds on the scratch 'imp' server (18701); outputs docx to /tmp/qa/letters_edge."""
import os, sys, json, io
from openpyxl import Workbook
sys.path.insert(0, "/home/user/training/backend")
from app.integrations.excel.gateway import LEGACY_IFS_COLS, LEGACY_IDP_COLS
BASE = "http://127.0.0.1:18701"
from lib import Client
a = Client(BASE); assert a.login("qaadmin", "Qa-Admin-Pass-9137!x").status_code == 200
OUT = "/tmp/qa/letters_edge"; os.makedirs(OUT, exist_ok=True)
wb = Workbook(); ws = wb.active; ws.title = "IFS"; ws.append(LEGACY_IFS_COLS)
def emp(no, fn, ln, ffn="", fln="", g="", sup="", div="Div", mob="", nc=""):
    r = [""] * len(LEGACY_IFS_COLS); c = LEGACY_IFS_COLS
    for k, v in (("Emp No", no), ("Fname", fn), ("Lname", ln), ("Farsi First Name", ffn), ("Farsi Last Name", fln), ("Gender", g), ("Sup Emp No", sup), ("Division", div), ("Email", f"e{no}@example.test"), ("Mobile", mob), ("National Code", nc), ("Cost Center", "CC1")):
        r[c.index(k)] = v
    ws.append(r)
emp("7000001", "Manny", "Manager", "منیره", "مدیری", "Female", "", mob="9900000001", nc="9990000001")
emp("7000002", "Nofa", "Rsi", "", "", "", "7000001", mob="9900000002", nc="9990000002")                       # no Farsi name, no gender
emp("7000003", "Zwnj", "Test", "علیرضا", "کریمی‌نژاد", "Male", "7000001", mob="9900000003", nc="9990000003")  # ZWNJ
emp("7000004", "F" * 90, "L" * 90, "ف" * 90, "ل" * 90, "Male", "7000001", mob="9900000004", nc="9990000004")           # very long
emp("7000005", "Orphan", "Sup", "یتیم", "سرپرست", "Male", "7999999", mob="9900000005", nc="9990000005")                # supervisor not in IFS
emp("7000006", "Nosup", "Ervisor", "بدون", "سرپرست", "Female", "", mob="9900000006", nc="9990000006")
emp("7000007", "Html", "<b>Inject</b>&\"'", "{{Fname}}", "{{ Summary }}", "Male", "7000001", mob="9900000007", nc="9990000007")  # markup / template-injection in names
ws2 = wb.create_sheet("IDP")
for _ in range(3): ws2.append([])
ws2.append(LEGACY_IDP_COLS); ws2.append(LEGACY_IDP_COLS)
for i in range(1, 8):
    ws2.append([f"700000{i}", "X [ MTNIrancell - D ]", "", "D", "Clean Course", "", "Approved", "", "Soft Skill", "-", "2026-12-01", "2026-12-02", f"LMS-80000{i}", "-"])
ws2.append(["7000003", "X", "", "D", "Evil Course {{link}} <script>alert(1)</script>", "", "Approved", "", "Soft Skill", "-", "2026-12-01", "2026-12-02", "LMS-810001", "-"])
buf = io.BytesIO(); wb.save(buf)
r = a.post("/import/legacy-workbook", files={"file": ("e.xlsx", buf.getvalue())}); print("import:", r.status_code, r.json().get("status"), r.json().get("errors"))
c = a.post("/courses", json={"name": "Clean Course", "name_fa": "دوره تمیز"}); print("course", c.status_code)
cid = c.json()["id"] if c.status_code == 201 else a.get("/courses", params={"q": "Clean Course"}).json()["items"][0]["id"]
run = a.post("/runs", json={"course_id": cid, "institute": "Inst <b>&</b> {{To}}", "duration_h": 8, "start_date": "2026-12-01", "end_date": "2026-12-02", "days": "دوشنبه", "time": "09:00-17:00", "sessions": 2, "deadline": "2026-11-25", "amount": 100000000, "section_b": "MTC-5", "link": "https://icare.example.test/x?a=1&b=<2>", "type": "in_person"})
print("run", run.status_code, run.text[:120]); rid = run.json()["id"]
ens = a.get("/enrollments", params={"q": "Clean", "page_size": 50}).json()["items"]
ids = [e["id"] for e in ens]
print("bulk assign:", a.post("/enrollments:bulk", json={"enrollment_ids": ids, "run_id": rid, "motivation": "Yes"}).json())
a.put("/automation/settings", json={"company_economic_code": "1", "company_national_id": "2", "company_postal_code": "3", "company_address": "Addr", "settlement_addressee": "Fin", "letter_signer_name": "S"})
def by_emp(n): return next(e["id"] for e in ens if e["emp_no"] == n)
evil = a.get("/enrollments", params={"q": "Evil"}).json()["items"]; print("evil enrollment found:", len(evil))
tests = {
 "l3_EVILCOURSE": ("level3_request", {"enrollment_ids": [evil[0]["id"]]}),
 "institute_all": ("institute_letter", {"run_id": rid}),
 "announce": ("course_announcement", {"run_id": rid}),
 "l3_nofa": ("level3_request", {"enrollment_ids": [by_emp("7000002")]}),
 "l3_zwnj": ("level3_request", {"enrollment_ids": [by_emp("7000003")]}),
 "l3_long": ("level3_request", {"enrollment_ids": [by_emp("7000004")]}),
 "l3_inject": ("level3_request", {"enrollment_ids": [by_emp("7000007")]}),
 "mgr_ok": ("level3_manager_check", {"enrollment_ids": [by_emp("7000003")]}),
 "mgr_nosup": ("level3_manager_check", {"enrollment_ids": [by_emp("7000006")]}),
 "mgr_supmissing": ("level3_manager_check", {"enrollment_ids": [by_emp("7000005")]}),
 "lm_ok": ("line_manager_approval", {"enrollment_ids": [by_emp(n) for n in ("7000002", "7000003", "7000004", "7000007")]}),
 "lm_supmissing": ("line_manager_approval", {"enrollment_ids": [by_emp("7000005")]}),
 "lm_nosup": ("line_manager_approval", {"enrollment_ids": [by_emp("7000006")]}),
}
for name, (k, body) in tests.items():
    r = a.post("/letters", json={"kind": k, **body})
    if r.status_code != 201: print(f"{name:16s} {r.status_code} {r.json()['error']['message'][:60]} {r.json()['error']['fields']}"); continue
    for it in r.json()["items"]:
        d = a.get(f"/letters/{it['id']}/download"); open(f"{OUT}/{name}_{it['id']}.docx", "wb").write(d.content)
    print(f"{name:16s} 201 letters={len(r.json()['items'])}")
# settlement (expected to fail: contract mismatch)
r = a.post("/letters", json={"kind": "settlement_letter", "run_id": rid}); print("settlement:", r.status_code, r.json()["error"]["fields"])
# preview html escaping
p = a.post("/letters/preview", json={"kind": "level3_request", "enrollment_ids": [by_emp("7000007")]}); print("l3 inject preview status", p.status_code, p.text[:200]); p = p.json() if p.status_code == 200 else {"html": ""}; print("preview html contains raw <b>Inject:", "<b>Inject" in p["html"], "| escaped:", "&lt;b&gt;Inject" in p["html"], "| leftover {{:", "{{" in p["html"])
p = a.post("/letters/preview", json={"kind": "course_announcement", "run_id": rid}); print("announcement preview:", p.status_code, p.text[:200] if p.status_code != 200 else ("<script" in p.json()["html"]))
