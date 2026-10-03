"""Manual edits vs re-import; legacy re-import idempotency on a clean synthetic workbook (no dup tickets)."""
import os, sys, io, json
sys.path.insert(0, "/home/user/training/backend")
from lib import Client
import synth
B = "http://127.0.0.1:18701"
a = Client(B); a.login("qaadmin", "Qa-Admin-Pass-9137!x")
synth.build("/tmp/qa/clean_legacy.xlsx", n_emp=20, n_idp=30, edge=False)
data = open("/tmp/qa/clean_legacy.xlsx", "rb").read()
r1 = a.post("/import/legacy-workbook", files={"file": ("a.xlsx", data)}).json(); r2 = a.post("/import/legacy-workbook", files={"file": ("a.xlsx", data)}).json()
print("clean legacy import #1:", {k: r1[k] for k in ("created", "updated", "unchanged", "skipped", "status")}, "#2:", {k: r2[k] for k in ("created", "updated", "unchanged", "skipped", "status")})
en = a.get("/enrollments", params={"q": "Effective", "page_size": 5}).json()["items"][0]
print("before:", {k: en[k] for k in ("id", "ticket", "attendance", "motivation", "registration", "comment", "current_status")})
p = a.patch(f"/enrollments/{en['id']}", json={"attendance": "Attended", "motivation": "Yes", "comment": "manual note", "registration": "Yes"}); print("patch:", p.status_code)
idp = open("/tmp/qa/idp_ok.xlsx", "rb").read()
synth.build_idp_only("/tmp/qa/idp_re.xlsx")
# re-import the same legacy workbook (contains same tickets with attendance '-')
r3 = a.post("/import/legacy-workbook", files={"file": ("a.xlsx", data)}).json(); print("re-import #3:", {k: r3[k] for k in ("created", "updated", "unchanged")})
after = a.get(f"/runs/0/enrollments") if False else a.get("/enrollments", params={"q": en["ticket"]}).json()["items"][0]
print("after re-import:", {k: after[k] for k in ("attendance", "motivation", "registration", "comment", "current_status")})
r4 = a.post("/import/idp", files={"file": ("a.xlsx", data)}).json(); print("idp import of same legacy file:", r4.get("status"), {k: r4[k] for k in ("created", "updated", "unchanged")})
after = a.get("/enrollments", params={"q": en["ticket"]}).json()["items"][0]
print("after idp re-import:", {k: after[k] for k in ("attendance", "motivation", "registration", "comment")})
