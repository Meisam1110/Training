"""Generate route x role matrix from OpenAPI, hit every route as anonymous/viewer/hr/admin,
and check (a) unauthenticated -> 401, (b) missing CSRF on unsafe -> 403, (c) role gating vs documented roles."""
import json, sys, os, itertools
from lib import Client, BASE
import httpx
pw = os.environ["QA_DEMO_PW"]
spec = httpx.get(BASE + "/api/openapi.json").json()
# documented minimum role (docs/SECURITY.md Roles section + docs/CONTRACT_REQUESTS.md)
DOC = {}
def doc(method, path):
    p = path.replace("/api/v1", "")
    admin = ["/users", "/audit", "/connectors/{kind}", "/connectors/{kind}:test", "/automation/settings:PUT"]
    if p.startswith("/users") or p.startswith("/audit"): return "admin"
    if p.startswith("/connectors/") and method in ("put", "post"): return "admin"
    if p == "/automation/settings" and method == "put": return "admin"
    if p in ("/health", "/ready"): return "anon"
    if p.startswith("/auth/login"): return "anon"
    hr_routes = [("post", "/letters"), ("post", "/letters/preview"), ("get", "/letters/{letter_id}/download"), ("post", "/email/send"),
                 ("get", "/messages"), ("get", "/connectors"), ("post", "/sync/{source}:run"), ("get", "/sync/runs"), ("post", "/import/idp"),
                 ("post", "/import/legacy-workbook"), ("get", "/export/legacy.xlsx"), ("post", "/automation/run")]
    if (method, p) in hr_routes: return "hr"
    if method in ("post", "put", "patch", "delete") and not p.startswith("/auth"): return "hr"
    return "viewer"
clients = {}
for role in ("viewer", "hr", "admin"):
    c = Client(); r = c.login(f"demo_{role}", pw); assert r.status_code == 200, r.text; clients[role] = c
anon = Client()
ids = {"emp_no": "D00001", "course_id": 1, "run_id": 1, "enrollment_id": 1, "letter_id": 1, "user_id": 1, "institute_id": 1, "kind": "smtp", "source": "excel"}
SAFE_BODIES = {}
rows = []; problems = []
for path, ops in spec["paths"].items():
    for method in ops:
        url = path
        for k, v in ids.items(): url = url.replace("{" + k + "}", str(v))
        if "{" in url: url = url  # unknown
        if path.endswith("/download") or "logout" in path or "login" in path: pass
        res = {}
        need = doc(method, path)
        for who, cl in [("anon", anon), ("viewer", clients["viewer"]), ("hr", clients["hr"]), ("admin", clients["admin"])]:
            if "logout" in path or "login" in path: continue
            kw = {}
            if method in ("post", "put", "patch"): kw["json"] = {}
            if "import/" in path: kw = {"files": {"file": ("x.txt", b"nope")}}
            if "email/send" in path: kw["json"] = {}
            # do not actually run destructive/expensive: sync/automation with admin role are ok on scratch DB
            r = cl.req(method.upper(), url, **kw)
            res[who] = r.status_code
        if not res: continue
        rows.append((method.upper(), path, need, res))
        # check
        rank = {"anon": 0, "viewer": 1, "hr": 2, "admin": 3}
        if need != "anon":
            if res["anon"] != 401: problems.append(f"{method.upper()} {path}: anonymous got {res['anon']} (expected 401)")
            for who in ("viewer", "hr", "admin"):
                st = res[who]
                if rank[who] < rank[need] and st != 403: problems.append(f"{method.upper()} {path}: {who} got {st}, expected 403 (needs {need})")
                if rank[who] >= rank[need] and st in (401, 403): problems.append(f"{method.upper()} {path}: {who} got {st}, expected allowed (needs {need})")
    # csrf
print(f"{'route':60s} need    anon viewer hr admin")
for m, p, n, r in rows:
    print(f"{m:6s} {p:52s} {n:7s} {r.get('anon','-'):>4} {r.get('viewer','-'):>6} {r.get('hr','-'):>4} {r.get('admin','-'):>5}")
print("\nPROBLEMS:", *problems, sep="\n  ") if problems else print("\nno RBAC deviations vs documented matrix")
# CSRF: every unsafe route with valid cookie but no token
print("\nCSRF check (authenticated admin, no X-CSRF-Token):")
bad = []
for path, ops in spec["paths"].items():
    for method in ops:
        if method in ("post", "put", "patch", "delete") and "login" not in path:
            url = path
            for k, v in ids.items(): url = url.replace("{" + k + "}", str(v))
            kw = {"json": {}} 
            if "import/" in path: kw = {"files": {"file": ("x.xlsx", b"PK")}}
            r = clients["admin"].req(method.upper(), url, csrf=False, **kw)
            if r.status_code != 403 or "CSRF" not in r.text and "توکن" not in r.text: bad.append((method, path, r.status_code, r.text[:80]))
            # wrong token
            r2 = clients["admin"].req(method.upper(), url, csrf=False, headers={"X-CSRF-Token": "x"*43}, **kw)
            if r2.status_code != 403: bad.append((method, path, "wrongtoken", r2.status_code))
print("CSRF exceptions:", bad or "none")
