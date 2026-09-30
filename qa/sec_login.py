"""Login brute force / lockout / XFF spoof / timing."""
import time, statistics, httpx, os
B = os.environ.get("QA_BASE", "http://127.0.0.1:18700")
def login(u, p, h=None):
    return httpx.post(B + "/api/v1/auth/login", json={"username": u, "password": p}, headers=h or {}, timeout=30)
print("== 1. per-username lockout, XFF rotation must not bypass")
codes = [login("demo_viewer", "wrong%d" % i, {"X-Forwarded-For": f"10.9.{i}.1"}).status_code for i in range(8)]
print("codes with rotating XFF:", codes)
r = login("demo_viewer", os.environ["QA_DEMO_PW"], {"X-Forwarded-For": "1.2.3.4"})
print("correct password while locked:", r.status_code, r.headers.get("retry-after"))
print("== 2. case / whitespace variants of a locked name")
for v in ("DEMO_VIEWER", " demo_viewer ", "demo_viewer​"):
    r = login(v, os.environ["QA_DEMO_PW"]); print(repr(v), r.status_code)
print("== 3. unknown user lockout parity (enumeration)")
c = [login("ghost_user_x", "bad").status_code for i in range(7)]
print("unknown user codes:", c)
print("== 4. per-IP window (30) with distinct usernames from one IP")
codes = [login(f"nouser{i}", "bad").status_code for i in range(40)]
print("codes:", codes.count(401), "x401", codes.count(429), "x429")
print("== 5. timing existing vs missing user (wrong pw), n=8 each, using a fresh IP each time")
def t(u):
    xs = []
    for i in range(8):
        a = time.perf_counter(); login(u, "x", {"X-Forwarded-For": f"172.16.{i}.{hash(u)%200}"}); xs.append(time.perf_counter() - a)
    return statistics.median(xs)
print("existing(demo_admin):", round(t("demo_admin"), 3), "missing:", round(t("zzz_missing_%d" % os.getpid()), 3))
