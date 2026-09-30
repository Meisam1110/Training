"""Raw-bytes / SQL inspection of the scratch SQLite DB: PII encrypted at rest? secrets? audit append-only? logs clean?"""
import sqlite3, re, os, sys, glob
DB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/qa/main.db"
c = sqlite3.connect(DB)
c.execute("pragma wal_checkpoint(FULL)")
# 1. plaintext PII values (from decrypted API) must not be in file bytes
import httpx
sys.path.insert(0, ".")
from lib import Client
cl = Client(); cl.login("demo_hr", os.environ["QA_DEMO_PW"])
vals = []
for e in cl.get("/employees", params={"page_size": 30}).json()["items"][:30]:
    d = cl.get(f"/employees/{e['emp_no']}?reveal=1").json()
    vals += [d["national_code"], d["mobile"], d["date_of_birth"]]
raw = b"".join(open(f, "rb").read() for f in glob.glob(DB + "*"))
vals = [v for v in vals if v]
hits = [v for v in vals if v.encode() in raw]
print(f"revealed PII values checked: {len(vals)}; found in raw DB bytes: {len(hits)}")
print("connector secret 'S3cretPW-QA-77' in raw DB bytes:", b"S3cretPW-QA-77" in raw)
print("sample stored national_code cell:", c.execute("select national_code from employees limit 1").fetchone()[0][:40], "...")
print("password_hash sample prefix:", c.execute("select substr(password_hash,1,12) from users limit 1").fetchone())
print("session tokens stored hashed (64 hex):", all(len(r[0]) == 64 for r in c.execute("select token_hash from user_sessions")))
# 2. audit append-only
for sql in ("update audit_log set action='x' where id=1", "delete from audit_log where id=1", "delete from audit_log"):
    try:
        c.execute(sql); c.commit(); print("DIRECT SQL SUCCEEDED (bad):", sql)
    except Exception as e:
        print("blocked:", sql, "->", str(e)[:70])
print("triggers:", [r[0] for r in c.execute("select name from sqlite_master where type='trigger'")])
# a bypass: drop trigger (DB superuser) is documented residual
# 3. audit contents PII?
pat = re.compile(r"\b\d{10,11}\b")
rows = c.execute("select action, detail from audit_log").fetchall()
print("audit rows:", len(rows), "with 10/11-digit numbers:", sum(1 for a, d in rows if pat.search(d or "")))
import collections; print("audit actions:", dict(collections.Counter(a for a, _ in rows)))
