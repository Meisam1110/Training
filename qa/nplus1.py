"""SQL statement counts + single-client latency per endpoint against the load DB (in-process TestClient)."""
import os, sys, time
sys.path.insert(0, "/home/user/training/backend")
os.environ.update(DATABASE_URL="sqlite:////tmp/qa/load.db", TMS_STORAGE_DIR="/tmp/qa/load-storage", TMS_ENV="development")
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.main import create_app
app = create_app(); eng = app.state.engine
cnt = {"n": 0}
@event.listens_for(eng, "before_cursor_execute")
def _c(*a, **k): cnt["n"] += 1
c = TestClient(app, base_url="http://testserver")
r = c.post("/api/v1/auth/login", json={"username": "demo_hr", "password": os.environ["QA_DEMO_PW"]}); h = {"X-CSRF-Token": r.json()["csrf_token"]}
eps = [("GET", "/api/v1/employees?page_size=200"), ("GET", "/api/v1/employees?page_size=200&q=Sample"), ("GET", "/api/v1/runs?page_size=200"), ("GET", "/api/v1/runs/3"),
       ("GET", "/api/v1/runs/3/enrollments?page_size=200"), ("GET", "/api/v1/enrollments?page_size=200"), ("GET", "/api/v1/enrollments?page_size=200&q=Sample"), ("GET", "/api/v1/letters?page_size=200"), ("GET", "/api/v1/messages?page_size=200"),
       ("GET", "/api/v1/dashboard"), ("GET", "/api/v1/automation/due"), ("POST", "/api/v1/runs/3/candidates:search"), ("GET", "/api/v1/audit?page_size=200"), ("GET", "/api/v1/institutes?page_size=200")]
print(f"{'endpoint':52s} {'sql':>5s} {'ms':>7s} {'bytes':>8s}")
for m, p in eps:
    cnt["n"] = 0; t = time.perf_counter()
    r = c.request(m, p, headers=h, json={} if m == "POST" else None); dt = (time.perf_counter() - t) * 1000
    print(f"{m+' '+p:52s} {cnt['n']:5d} {dt:7.0f} {len(r.content):8d}  {r.status_code}")
