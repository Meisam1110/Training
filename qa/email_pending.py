import os, sqlite3, time
from lib import Client
hr = Client(); hr.login("demo_hr", os.environ["QA_DEMO_PW"])
k = "qa-key-stuck1"
body = {"letter_id": 1, "recipients": ["stuck@example.test"], "idempotency_key": k}
r = hr.post("/email/send", json=dict(body, dry_run=True)); print("dry first:", r.json()["status"])
c = sqlite3.connect("/tmp/qa/main.db"); c.execute("insert into message_logs(idempotency_key,letter_id,subject,recipients,results,dry_run,status,channel,created_at,updated_at) values(?,?,?,?,?,?,?,?,datetime('now','-3 days'),datetime('now','-3 days'))", (k, 1, "s", '["stuck@example.test"]', "[]", 0, "pending", "smtp")); c.commit()
r = hr.post("/email/send", json=body); print("3-day-old pending row, retry:", r.status_code, r.text[:120])
