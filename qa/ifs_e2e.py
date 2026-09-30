"""Core sync from the in-repo mock IFS through the real API in all three auth modes + fault injection."""
import os, json, time, httpx
from lib import Client
BASE = os.environ.get("QA_BASE", "http://127.0.0.1:18700")
adm = Client(BASE); adm.login("demo_admin", os.environ["QA_DEMO_PW"]); hr = Client(BASE); hr.login("demo_hr", os.environ["QA_DEMO_PW"])
MOCK = "http://127.0.0.1:18099"
ctl = lambda **k: httpx.post(MOCK + "/__control", json=k)
modes = {
 "oauth2_client_credentials": {"client_id": "mock-client", "client_secret": "mock-client-secret", "token_url": MOCK + "/oauth/token"},
 "basic": {"username": "mock-user", "password": "mock-password"},
 "session_login": {"username": "mock-user", "password": "mock-password", "login_url": MOCK + "/login"},
}
def cfg(mode, **extra):
    return {"enabled": True, "config": {"base_url": MOCK, "auth_mode": mode, "timeout_s": 5, **modes[mode], **extra}}
def sync(full=True):
    t = time.time(); r = hr.post("/sync/ifs:run", json={"full": full}); return r.status_code, (r.json().get("status"), r.json().get("created"), r.json().get("updated"), r.json().get("unchanged"), r.json().get("skipped"), r.json().get("message", "")[:80]) if r.status_code == 200 else r.text[:150], round(time.time() - t, 1)
ctl(fail_429=0, fail_500=0, token_ttl=3600, session_ttl=3600, use_next_link=False, expire_now=True)
for m in modes:
    r = adm.put("/connectors/ifs", json=cfg(m)); print(m, "PUT", r.status_code, r.text[:120] if r.status_code != 200 else "")
    print("  test:", adm.post("/connectors/ifs:test").json())
    print("  sync1:", sync(), " sync2:", sync())
print("--- token expiry mid-sync (ttl 1s, pages of 5)")
adm.put("/connectors/ifs", json=cfg("oauth2_client_credentials", timeout_s=5)); ctl(token_ttl=1, expire_now=True, use_next_link=True)
print("  ", sync())
ctl(token_ttl=3600, use_next_link=False)
print("--- 429 x3 then ok:"); ctl(fail_429=3); print("  ", sync())
print("--- 500 x2 then ok:"); ctl(fail_500=2); print("  ", sync())
print("--- persistent 500 (fail_500=50):"); ctl(fail_500=50); print("  ", sync()); ctl(fail_500=0)
print("--- 401 (bad secret):"); adm.put("/connectors/ifs", json=cfg("oauth2_client_credentials", client_secret="WRONG-SECRET-XYZ")); r = adm.post("/connectors/ifs:test"); print("  test:", r.json()); print("  sync:", sync())
ctl(fail_500=0); adm.put("/connectors/ifs", json=cfg("oauth2_client_credentials"))
print("--- last sync runs:", [(x["id"], x["status"], x["message"][:60]) for x in hr.get("/sync/runs", params={"source": "ifs", "page_size": 4}).json()["items"]])
print("--- config exposure:", json.dumps(hr.get("/connectors").json()["items"][1]))
# unsupported keys via API
for k, v in (("employees_path", "/Custom/Path"), ("page_size", 100), ("modified_field", "LastUpdated"), ("scope", "x"), ("ca_bundle", "/x")):
    r = adm.put("/connectors/ifs", json={"enabled": True, "config": {k: v}}); print(f"  ifs config key {k}: {r.status_code}")
for k, v in (("use_ssl", True), ("verify_tls", False), ("ca_bundle", "/x"), ("timeout_s", 5), ("rate_limit_per_min", 30)):
    r = adm.put("/connectors/smtp", json={"enabled": True, "config": {k: v}}); print(f"  smtp config key {k}: {r.status_code}")
