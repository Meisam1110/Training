"""Letter numbering under concurrency: N parallel POST /letters (institute_letter). Numbers must be unique and gapless-ish."""
import os, sys, threading, collections
from lib import Client
BASE = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
adm = Client(BASE); adm.login("demo_admin", os.environ["QA_DEMO_PW"]); hr = Client(BASE); hr.login("demo_hr", os.environ["QA_DEMO_PW"])
adm.put("/automation/settings", json={"company_economic_code": "1", "company_national_id": "2", "company_postal_code": "3", "company_address": "A", "settlement_addressee": "F", "letter_signer_name": "S"})
res = []; lock = threading.Lock()
def go():
    c = Client(BASE); c.login("demo_hr", os.environ["QA_DEMO_PW"])
    r = c.post("/letters", json={"kind": "institute_letter", "run_id": 3})
    with lock: res.append((r.status_code, r.json().get("number") if r.status_code == 201 else r.text[:100]))
ts = [threading.Thread(target=go) for _ in range(N)]; [t.start() for t in ts]; [t.join() for t in ts]
codes = collections.Counter(c for c, _ in res); nums = [n for c, n in res if c == 201]
print("statuses:", dict(codes), "| unique numbers:", len(set(nums)), "of", len(nums), "| range:", min(map(int, nums)) if nums else None, max(map(int, nums)) if nums else None)
bad = [x for x in res if x[0] != 201][:3]; print("non-201 samples:", bad)
