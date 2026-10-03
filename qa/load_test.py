"""50 parallel clients hammering list/detail/send endpoints; p50/p95/max latency and error counts; SQL statement counts via /proc RSS."""
import os, sys, time, threading, statistics, random, collections, glob
from lib import Client
BASE = sys.argv[1]; CLIENTS = int(sys.argv[2]) if len(sys.argv) > 2 else 50; SECS = int(sys.argv[3]) if len(sys.argv) > 3 else 20
PIDS = [int(x) for x in open(sys.argv[4]).read().split()] if len(sys.argv) > 4 else []
pw = os.environ["QA_DEMO_PW"]
def rss():
    import subprocess
    out = subprocess.run("ps -eo rss,args | grep 'uvicorn app.main' | grep -v grep | grep -v 'ps -eo' | awk '{s+=$1} END {print s/1024}'", shell=True, capture_output=True, text=True).stdout.strip()
    return out
hr0 = Client(BASE); hr0.login("demo_hr", pw)
run_ids = [r["id"] for r in hr0.get("/runs", params={"page_size": 50}).json()["items"]]
emp_nos = [e["emp_no"] for e in hr0.get("/employees", params={"page_size": 50}).json()["items"]]
def mk(c):
    rid = random.choice(run_ids); en = random.choice(emp_nos)
    return random.choice([
        ("GET /employees?page_size=200", lambda: c.get("/employees", params={"page_size": 200})),
        ("GET /employees?q=", lambda: c.get("/employees", params={"q": "Sample", "page_size": 50})),
        ("GET /employees/{id}", lambda: c.get(f"/employees/{en}")),
        ("GET /runs", lambda: c.get("/runs", params={"page_size": 200})),
        ("GET /runs/{id}", lambda: c.get(f"/runs/{rid}")),
        ("GET /runs/{id}/enrollments", lambda: c.get(f"/runs/{rid}/enrollments", params={"page_size": 200})),
        ("GET /enrollments", lambda: c.get("/enrollments", params={"page_size": 200, "sort": "-id"})),
        ("GET /dashboard", lambda: c.get("/dashboard")),
        ("GET /automation/due", lambda: c.get("/automation/due")),
        ("POST candidates:search", lambda: c.post(f"/runs/{rid}/candidates:search", json={})),
        ("POST /email/send dry", lambda: c.post("/email/send", json={"template": "level3_request", "fields": {"Ftitle": "x", "Fname": "y", "En_title": "z", "Reporter__Name": "n", "Summary": "s", "link": "https://x.test"}, "recipients": ["a@example.test"], "dry_run": True})),
    ])
lat = collections.defaultdict(list); errs = collections.Counter(); stop = time.time() + SECS
def worker(i):
    c = Client(BASE); r = c.login("demo_hr" if i % 5 else "demo_viewer", pw)
    if r.status_code != 200: errs["login " + str(r.status_code)] += 1; return
    while time.time() < stop:
        name, fn = mk(c)
        if c.user == "demo_viewer" and name.startswith("POST"): continue
        t = time.perf_counter()
        try:
            resp = fn(); dt = time.perf_counter() - t; lat[name].append(dt)
            if resp.status_code >= 400: errs[f"{name} -> {resp.status_code}"] += 1
        except Exception as e:
            errs[f"{name} EXC {type(e).__name__}"] += 1
m0 = rss()
ts = [threading.Thread(target=worker, args=(i,)) for i in range(CLIENTS)]; [t.start() for t in ts]; [t.join() for t in ts]
allv = [x for v in lat.values() for x in v]
print(f"clients={CLIENTS} secs={SECS} requests={len(allv)} rps={len(allv)/SECS:.0f} errors={sum(errs.values())}  RSS(all uvicorn procs) before={m0}MB after={rss()}MB")
print(f"ALL  p50={statistics.median(allv)*1000:.0f}ms p95={sorted(allv)[int(len(allv)*.95)]*1000:.0f}ms max={max(allv)*1000:.0f}ms")
for k, v in sorted(lat.items()):
    v.sort(); print(f"{k:32s} n={len(v):5d} p50={statistics.median(v)*1000:6.0f}ms p95={v[int(len(v)*.95)]*1000:6.0f}ms max={max(v)*1000:6.0f}ms")
print("errors:", dict(errs))
