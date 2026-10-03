"""Render all six letter kinds via the API, download docx, convert to PDF (soffice) and PNG (pymupdf) for visual inspection."""
import os, sys, json, subprocess, glob
from lib import Client
BASE = os.environ.get("QA_BASE", "http://127.0.0.1:18700")
OUT = os.environ.get("LOUT", "/tmp/qa/letters"); os.makedirs(OUT, exist_ok=True)
pw = os.environ["QA_DEMO_PW"]
adm = Client(BASE); adm.login("demo_admin", pw); hr = Client(BASE); hr.login("demo_hr", pw); vw = Client(BASE); vw.login("demo_viewer", pw)
r = adm.put("/automation/settings", json={"company_economic_code": "411000000000", "company_national_id": "10000000000", "company_postal_code": "1234567890",
    "company_address": "Synthetic Address, Test City", "settlement_addressee": "Finance Dept (Synthetic)", "letter_signer_name": "Sample Signer", "letter_signer_title": "Talent Development", "letter_signer_email": "signer@example.test", "letter_signer_phone": "02100000000"})
print("settings:", r.status_code, r.text[:150] if r.status_code != 200 else "")
run = 3
hr.patch(f"/runs/{run}", json={"link": "https://icare.example.test/c/3", "days": "شنبه و دوشنبه", "time": "10:00-16:00", "sessions": 4, "deadline": "2026-09-20", "section_b": "MTC-1234", "invoice_receive_date": None})
ens = hr.get(f"/runs/{run}/enrollments", params={"page_size": 200}).json()["items"]
yes = [e["id"] for e in ens if e["motivation"] == "Yes" and e["supervisor_emp_no"]]
yes_all = [e["id"] for e in ens if e["motivation"] == "Yes"]
print("run", run, "yes enrollments:", len(yes))
kinds = [("course_announcement", {"run_id": run}), ("institute_letter", {"run_id": run}), ("settlement_letter", {"run_id": run, "extra": {"invoice_no": "INV-9001", "purpose": "Project Management"}}),
         ("level3_request", {"enrollment_ids": yes[:3]}), ("level3_manager_check", {"enrollment_ids": yes[:3]}), ("line_manager_approval", {"enrollment_ids": yes})]
made = {}
for k, extra in kinds:
    p = hr.post("/letters/preview", json={"kind": k, **extra}); 
    print(f"{k:22s} preview {p.status_code}", (p.json().get("count") if p.status_code == 200 else p.text[:150]))
    r = hr.post("/letters", json={"kind": k, **extra})
    if r.status_code != 201: print("   create", r.status_code, r.text[:200]); continue
    items = r.json()["items"]; made[k] = items
    for it in items:
        d = hr.get(f"/letters/{it['id']}/download"); fn = f"{OUT}/{k}_{it['id']}.docx"; open(fn, "wb").write(d.content)
    print("   created", [ (i["id"], i["number"]) for i in items], "download", d.status_code, "viewer download:", vw.get(f"/letters/{items[0]['id']}/download").status_code)
json.dump({k: [i["id"] for i in v] for k, v in made.items()}, open(f"{OUT}/made.json", "w"))
