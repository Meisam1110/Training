"""Behaviour that differs on PostgreSQL (strict lengths, NUL, integer range). Run against QA_BASE=pg server."""
import os, json
os.environ["QA_BASE"] = "http://127.0.0.1:18702"
from lib import Client
import synth
hr = Client(os.environ["QA_BASE"]); assert hr.login("demo_hr", os.environ["QA_DEMO_PW"]).status_code == 200
r = hr.post("/courses", json={"name": "nul\x00byte"}); print("NUL in course name:", r.status_code, r.text[:120])
r = hr.post("/courses", json={"name": "x" * 300, "category": "y" * 100}); print("300-char course name:", r.status_code)
r = hr.post("/courses", json={"name": "x" * 301}); print("301-char name:", r.status_code)
r = hr.get("/runs/99999999999999999999"); print("overflow id:", r.status_code)
# import synth workbook with overlong names (SQLite ignores VARCHAR lengths, PG enforces)
synth.build("/tmp/qa/s_pg.xlsx", formula_names=False)
r = hr.post("/import/legacy-workbook", files={"file": ("s.xlsx", open("/tmp/qa/s_pg.xlsx", "rb").read())})
print("legacy import with 300-char names on PG:", r.status_code, r.text[:300])
r = hr.get("/employees", params={"q": "Synth"}); print("employees after:", r.json().get("total"))
# other long fields on IDP import: department / emp fields
