import os
from lib import Client
hr = Client(); hr.login("demo_hr", os.environ["QA_DEMO_PW"])
big = 99999999999999999999
tests = [("GET", f"/runs/{big}", None), ("GET", f"/courses/{big}", None), ("PATCH", f"/courses/{big}", {}), ("PATCH", f"/enrollments/{big}", {}),
 ("GET", f"/letters/{big}/download", None), ("GET", f"/runs/{big}/enrollments", None), ("POST", f"/runs/{big}/candidates:search", {}),
 ("GET", f"/enrollments?run_id={big}", None), ("GET", f"/letters?run_id={big}", None), ("POST", "/enrollments:bulk", {"enrollment_ids": [big]}),
 ("POST", "/letters", {"kind": "institute_letter", "run_id": big}), ("POST", "/letters/preview", {"kind": "level3_request", "enrollment_ids": [big]}),
 ("POST", "/email/send", {"letter_id": big, "recipients": ["a@b.co"]}), ("POST", "/runs", {"course_id": big}),
 ("PATCH", f"/institutes/{big}", {}), ("PATCH", f"/users/{big}", {})]
for m, p, b in tests:
    r = hr.req(m, p, **({"json": b} if b is not None else {}))
    print(r.status_code, m, p[:60], "" if r.status_code < 500 else "<-- 500")
