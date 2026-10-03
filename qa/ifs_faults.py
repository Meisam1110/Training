import os, time, threading, subprocess
from lib import Client
BASE = os.environ.get("QA_BASE", "http://127.0.0.1:18700")
adm = Client(BASE); adm.login("demo_admin", os.environ["QA_DEMO_PW"]); hr = Client(BASE); hr.login("demo_hr", os.environ["QA_DEMO_PW"])
def cfg(port, scheme="http", **k): return {"enabled": True, "config": {"base_url": f"{scheme}://127.0.0.1:{port}", "auth_mode": "basic", "username": "u", "password": "p", "timeout_s": 2, **k}}
def rss(): return subprocess.run("ps -eo rss,args | grep 'uvicorn app.main:app --host 127.0.0.1 --port 18700' | grep -v grep | awk '{s+=$1} END {print int(s/1024)}'", shell=True, capture_output=True, text=True).stdout.strip()
for name, port, scheme, extra in (("slow response (8s) with timeout_s=2", 18110, "http", {}), ("malformed JSON", 18111, "http", {}), ("HTTPS self-signed cert (verify on)", 18113, "https", {}), ("redirect to internal host", 18114, "http", {}), ("huge 60k-record page", 18115, "http", {})):
    pr = adm.put("/connectors/ifs", json=cfg(port, scheme, **extra)); assert pr.status_code == 200, pr.text; t = time.time()
    tr = adm.post("/connectors/ifs:test").json(); print(f"{name:40s} test -> ok={tr['ok']} msg={tr['message'][:90]!r} ({time.time()-t:.1f}s)")
    t = time.time(); m0 = rss(); r = hr.post("/sync/ifs:run", json={"full": True}); print(f"{'':40s} sync -> HTTP {r.status_code} {r.json().get('status') or r.json().get('error',{}).get('code')} {r.json().get('message','')[:70]!r} ({time.time()-t:.1f}s) rss {m0}->{rss()}MB")
# endless pagination: abort client after 30s and look at server progress
assert adm.put("/connectors/ifs", json=cfg(18112, "http", timeout_s=5)).status_code == 200; t = time.time()
try:
    r = hr.c.post("/api/v1/sync/ifs:run", json={"full": True}, headers={"X-CSRF-Token": hr.csrf}, timeout=40); print("endless pagination finished:", r.status_code, r.text[:100], round(time.time() - t))
except Exception as e:
    print(f"endless pagination: no answer after 40s ({type(e).__name__}); server rss {rss()}MB; 2nd sync attempt while first is running ->", end=" ")
    r = hr.post("/sync/ifs:run", json={"full": True}); print(r.status_code, r.text[:80])
