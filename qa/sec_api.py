"""Injection / mass-assignment / IDOR / session probes against the running app (scratch DB)."""
import os, json, re, httpx
from lib import Client, BASE
pw = os.environ["QA_DEMO_PW"]
hr = Client(); hr.login("demo_hr", pw)
adm = Client(); adm.login("demo_admin", pw)
vw = Client(); vw.login("demo_viewer", pw)
out = []
def rec(name, ok, detail=""):
    out.append((name, ok)); print(("PASS " if ok else "FAIL ") + name, detail)

# --- SQLi in q / sort / filters on every list endpoint
lists = ["/employees", "/courses", "/runs", "/enrollments", "/letters", "/messages", "/sync/runs", "/institutes", "/users", "/audit", "/connectors"]
payloads = ["' OR '1'='1", "'; DROP TABLE users;--", "%", "_", "\\", "a' UNION SELECT password_hash FROM users--", "\x00", "𝕏" * 50, "%' AND 1=(SELECT count(*) FROM users) AND '%'='"]
for l in lists:
    cl = adm
    base_total = cl.get(l + "?page_size=1").json().get("total")
    for p in payloads:
        for prm in ("q",):
            r = cl.get(l, params={prm: p, "page_size": 5})
            if r.status_code >= 500: rec(f"SQLi q {l}", False, f"{r.status_code} {p!r}")
            elif r.status_code == 200 and p in ("' OR '1'='1",) and r.json().get("total") not in (0,) and l not in ("/connectors", "/sync/runs"):
                rec(f"SQLi tautology {l}", False, f"total={r.json().get('total')}")
    for s in ["id;select 1", "-id,(select 1)", "password_hash", "id desc", "-", "1", "id,,id", "case when 1=1 then id end"]:
        r = cl.get(l, params={"sort": s})
        if r.status_code >= 500: rec(f"sort {l}", False, f"{r.status_code} {s!r}")
    for f in ("division", "status", "supervisor", "kind", "state", "source", "run_id", "motivation", "actor", "action", "entity"):
        r = cl.get(l, params={f: "' OR 1=1--"})
        if r.status_code >= 500: rec(f"filter {f} {l}", False, str(r.status_code))
rec("SQLi sweep: no 5xx, no tautology on q/sort/filters", all(ok for _, ok in out) if out else True)
# LIKE wildcard escaping: q=% must not match everything
t_all = adm.get("/employees").json()["total"]; t_pct = adm.get("/employees", params={"q": "%"}).json()["total"]
rec("q=% is escaped (not wildcard)", t_pct < t_all, f"all={t_all} pct={t_pct}")
# pagination bounds
for prm in ({"page_size": 201}, {"page_size": 0}, {"page": 0}, {"page": -1}, {"page": 10**15}, {"page_size": "x"}):
    r = adm.get("/employees", params=prm)
    rec(f"paging {prm}", r.status_code in (200, 422), str(r.status_code))
# --- mass assignment / extra fields
r = hr.post("/courses", json={"name": "QA x", "id": 999, "active": True, "is_admin": True}); rec("extra field course rejected (422)", r.status_code == 422, r.text[:100])
r = adm.post("/users", json={"username": "qa_mass", "password": "Str0ng-Passw0rd!", "role": "viewer", "is_active": False, "id": 1}); rec("extra field user rejected", r.status_code == 422, r.text[:100])
r = hr.post("/users", json={"username": "qa_hr_esc", "password": "Str0ng-Passw0rd!x", "role": "admin"}); rec("hr cannot create admin user", r.status_code == 403)
r = hr.patch("/users/2", json={"role": "admin"}); rec("hr cannot self-escalate", r.status_code == 403)
r = adm.post("/users", json={"username": "qa_weak", "password": "short", "role": "viewer"}); rec("weak user password rejected", r.status_code == 422, r.text[:80])
r = adm.post("/users", json={"username": "qa_weak2", "password": "aaaaaaaaaaaaaaaa", "role": "viewer"}); rec("low-entropy password rejected", r.status_code == 422, str(r.status_code))
r = adm.post("/users", json={"username": "qa_weak3", "password": "Password1234", "role": "viewer"}); print("   common 'Password1234' ->", r.status_code)
r = adm.post("/users", json={"username": "qa_weak4", "password": "12345678901234", "role": "viewer"}); print("   digits-only 14 ->", r.status_code)
# --- sessions
c = Client(); c.login("demo_viewer", pw); tok = c.c.cookies.get("tms_session")
old = tok
r = httpx.post(BASE + "/api/v1/auth/login", json={"username": "demo_viewer", "password": pw}, cookies={"tms_session": "attacker-chosen-value"})
new = r.cookies.get("tms_session")
rec("login issues fresh token (no fixation)", new != "attacker-chosen-value" and new != old)
c.post("/auth/logout")
r = httpx.get(BASE + "/api/v1/auth/me", cookies={"tms_session": old}); rec("token dead after logout", r.status_code == 401)
r = httpx.get(BASE + "/api/v1/auth/me", cookies={"tms_session": tok + "x"}); rec("tampered token rejected", r.status_code == 401)
# CSRF token of session A used with session B's cookie
a = Client(); a.login("demo_hr", pw); b = Client(); b.login("demo_viewer", pw)
r = b.c.post("/api/v1/courses", json={"name": "x"}, headers={"X-CSRF-Token": a.csrf}); rec("csrf token is bound to its session", r.status_code == 403, str(r.status_code))
# Origin
r = hr.post("/courses", json={"name": "QA origin"}, headers={"Origin": "https://evil.example"}); rec("cross-origin unsafe request blocked", r.status_code == 403, str(r.status_code))
r = hr.post("/courses", json={"name": "QA origin"}, headers={"Origin": "null"}); rec("Origin: null blocked", r.status_code == 403)
# GET with side-effects? reveal is audited GET
r = hr.get("/employees/D00001?reveal=1"); rec("reveal works for hr (audited)", r.status_code == 200 and "*" not in r.json()["national_code"])
r = vw.get("/employees/D00001?reveal=1"); rec("viewer reveal denied", r.status_code == 403)
r = vw.get("/employees/D00001"); print("   viewer masked:", {k: r.json()[k] for k in ("national_code", "mobile", "date_of_birth")})
# ids of other resources / nonsense
for path in ["/runs/999999", "/courses/999999", "/employees/nope", "/letters/999999/download", "/runs/abc", "/runs/-1", "/runs/99999999999999999999"]:
    r = hr.get(path); rec(f"bad id {path}", r.status_code in (404, 422), str(r.status_code) + " " + r.text[:60])
# error body stack trace / leak
r = hr.post("/runs", json={"course_id": "1'; drop", "start_date": "2026-13-45"}); rec("validation error has no trace", "Traceback" not in r.text and "File \"" not in r.text)
r = httpx.post(BASE + "/api/v1/auth/login", content=b"\xff\xfe", headers={"content-type": "application/json"}); rec("binary login body no 500", r.status_code < 500, str(r.status_code))
r = hr.post("/courses", content=b'{"name": "' + b"A" * 2_000_000 + b'"}', headers={"content-type": "application/json"}); rec("2MB body -> 413", r.status_code == 413, str(r.status_code))
r = hr.post("/courses", content=b'{"name": ' * 20000 + b"1" , headers={"content-type": "application/json"}); rec("deeply nested json no 500", r.status_code < 500, str(r.status_code))
r = hr.post("/courses", json={"name": "\x00nul"}); print("   NUL in name ->", r.status_code)
open("logs/sec_api.json", "w").write(json.dumps(out))
