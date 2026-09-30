import os, json, glob, time, threading, email
from lib import Client
pw = os.environ["QA_DEMO_PW"]
adm = Client(); adm.login("demo_admin", pw); hr = Client(); hr.login("demo_hr", pw)
r = adm.put("/connectors/smtp", json={"enabled": True, "config": {"host": "127.0.0.1", "port": 18025, "starttls": False, "from_addr": "tms@example.test", "from_name": "TMS QA", "password": "S3cretPW-QA-77"}})
print("put smtp:", r.status_code, r.text[:300])
print("test smtp:", adm.post("/connectors/smtp:test").json())
runs = hr.get("/runs").json()["items"]; print("runs:", [(x["id"], x["course_name"], x["start_date"]) for x in runs])
run_id = runs[0]["id"]
print("patch link:", hr.patch(f"/runs/{run_id}", json={"link": "https://icare.example.test/course/1"}).status_code)
r = hr.post("/letters", json={"kind": "course_announcement", "run_id": run_id, "lang": "both"}); print("letter:", r.status_code, r.text[:200])
lid = r.json()["id"]
def sink(): return sorted(glob.glob("/tmp/qa/smtp_sink/*.eml"))
n0 = len(sink())
body = {"letter_id": lid, "recipients": ["a1@example.test", "a2@example.test"], "idempotency_key": "qa-key-0001"}
r1 = hr.post("/email/send", json=body); print("send1:", r1.status_code, r1.json())
r2 = hr.post("/email/send", json=body); print("send2 (replay):", r2.status_code, r2.json().get("replayed"), r2.json().get("status"))
time.sleep(0.5); print("sink messages after 2 identical POST:", len(sink()) - n0, "(expect 1)")
# same key different body
b2 = dict(body, subject="DIFFERENT SUBJECT"); r = hr.post("/email/send", json=b2); print("same key, different subject:", r.status_code, r.json().get("replayed"), "<- silently replays?" if r.status_code == 200 else "")
b3 = dict(body, cc=["cc1@example.test"]); r = hr.post("/email/send", json=b3); print("same key, different cc:", r.status_code, r.json().get("replayed"))
b4 = dict(body, recipients=["a1@example.test", "a3@example.test"]); r = hr.post("/email/send", json=b4); print("same key, different recipients:", r.status_code, r.text[:100])
# partial failure & retry
bp = {"letter_id": lid, "recipients": ["ok1@example.test", "reject1@example.test", "ok2@example.test"], "idempotency_key": "qa-key-0002"}
n1 = len(sink()); r = hr.post("/email/send", json=bp); print("partial:", r.status_code, r.json()["status"], [(x["recipient"], x["ok"], x["error"]) for x in r.json()["results"]])
r = hr.post("/email/send", json=bp); print("retry partial:", r.json()["status"], r.json()["replayed"], [(x["recipient"], x["ok"]) for x in r.json()["results"]])
time.sleep(0.5); print("messages delivered for partial+retry:", len(sink()) - n1, "(expect 1 initial + 1 retry(reject only) = 1 delivered; ok1/ok2 must not be re-sent)")
# connection drop
r = hr.post("/email/send", json={"letter_id": lid, "recipients": ["drop1@example.test"], "idempotency_key": "qa-key-0003"}); print("drop:", r.status_code, r.json()["status"], r.json()["results"])
# concurrent same key
res = []
def go(): res.append(hr.post("/email/send", json={"letter_id": lid, "recipients": ["conc@example.test"], "idempotency_key": "qa-key-0004"}).status_code)
n2 = len(sink()); ts = [threading.Thread(target=go) for _ in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
time.sleep(1); print("concurrent 8x same key: statuses", sorted(res), "delivered:", len(sink()) - n2, "(expect 1)")
# no key: auto key -> two sends
n3 = len(sink()); [hr.post("/email/send", json={"letter_id": lid, "recipients": ["nokey@example.test"]}) for _ in range(2)]; time.sleep(0.5)
print("no key double POST delivered:", len(sink()) - n3, "(2 = no protection without key; documented?)")
# dry run
n4 = len(sink()); r = hr.post("/email/send", json={"letter_id": lid, "recipients": ["dry@example.test"], "dry_run": True, "idempotency_key": "qa-key-0005"}); print("dry:", r.json()["status"], "delivered", len(sink()) - n4)
# inspect one delivered message
f = sink()[0]; m = email.message_from_binary_file(open(f, "rb")); print("headers:", {k: m[k] for k in ("From", "To", "Subject", "Cc")}); print("parts:", [(p.get_content_type(), p.get_filename()) for p in m.walk()])
# To header exposes all recipients to each other?
print("To header of first message:", m["To"])
