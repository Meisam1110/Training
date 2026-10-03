"""Does sending a level3 letter/e-mail ever remove an enrollment from the due list? (level3_sent write path)"""
import os, sys, datetime as dt
sys.path.insert(0, "/home/user/training/backend")
from openpyxl import Workbook
from app.integrations.excel.gateway import LEGACY_IDP_COLS, LEGACY_IFS_COLS
import io
from lib import Client
B = "http://127.0.0.1:18701"
a = Client(B); a.login("qaadmin", "Qa-Admin-Pass-9137!x")
wb = Workbook(); ws = wb.active; ws.title = "IFS"; ws.append(LEGACY_IFS_COLS)
for n in (1, 2):
    r = [""] * len(LEGACY_IFS_COLS); c = LEGACY_IFS_COLS; r[c.index("Emp No")] = f"6000{n}"; r[c.index("Fname")] = "L3"; r[c.index("Lname")] = f"P{n}"; r[c.index("Gender")] = "Male"; r[c.index("Email")] = f"l3{n}@example.test"; ws.append(r)
w2 = wb.create_sheet("IDP")
for _ in range(3): w2.append([])
w2.append(LEGACY_IDP_COLS); w2.append(LEGACY_IDP_COLS)
end = dt.date.today() - dt.timedelta(days=61)
w2.append(["60001", "L3 P1", "", "D", "Comm Skills", "", "Evaluation Level 3", "", "Soft Skill", "Attended", (end - dt.timedelta(days=2)).isoformat(), end.isoformat(), "LMS-900001", "-"])
w2.append(["60002", "L3 P2", "", "D", "Comm Skills", "", "Evaluation Level 3", "", "Soft Skill", "Attended", (end - dt.timedelta(days=2)).isoformat(), (dt.date.today() - dt.timedelta(days=60)).isoformat(), "LMS-900002", "-"])  # exactly 60 days: not due (strict >)
buf = io.BytesIO(); wb.save(buf)
print("import:", a.post("/import/legacy-workbook", files={"file": ("l.xlsx", buf.getvalue())}).json()["status"])
due = lambda: [(i["kind"], i["enrollment_id"]) for i in a.get("/automation/due").json()["items"] if i["kind"].startswith("level3")]
d0 = due(); print("level3 due before:", d0)
ens = {e["ticket"]: e["id"] for e in a.get("/enrollments", params={"q": "LMS-9000"}).json()["items"]}
print("tickets:", ens)
eid = ens["LMS-900001"]
r = a.post("/letters", json={"kind": "level3_request", "enrollment_ids": [eid]}); print("letter:", r.status_code)
lid = r.json()["id"]
a.put("/connectors/smtp", json={"enabled": True, "config": {"host": "127.0.0.1", "port": 18025, "starttls": False, "from_addr": "t@example.test"}})
r = a.post("/email/send", json={"letter_id": lid, "recipients": ["l31@example.test"]}); print("email:", r.json()["status"])
print("level3 due after letter+email:", due())
print("enrollment level3_sent/status:", {k: v for k, v in a.get("/enrollments", params={"q": "LMS-900001"}).json()["items"][0].items() if k.startswith("level3")})
dash = a.get("/dashboard").json(); print("dashboard level3_due count:", len(dash["level3_due"]), "workflow:", a.get("/runs").json()["items"][0].get("id") and "n/a")
r = a.patch(f"/enrollments/{eid}", json={"level3_sent": True}); print("PATCH level3_sent:", r.status_code)
