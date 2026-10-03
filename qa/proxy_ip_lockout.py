"""Simulates the compose topology: the app sees the proxy/bridge address (NOT in FORWARDED_ALLOW_IPS=127.0.0.1), so X-Forwarded-For is ignored
and every user shares one IP. Source address 127.0.0.2 stands in for the docker bridge gateway. Needs the scratch server on 18700."""
import httpx, os
B = "http://127.0.0.1:18700"; pw = os.environ["QA_DEMO_PW"]
p = httpx.Client(base_url=B, transport=httpx.HTTPTransport(local_address="127.0.0.2"), timeout=20)
codes = [p.post("/api/v1/auth/login", json={"username": f"nobody{i}", "password": "x"}, headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(35)]
print({c: codes.count(c) for c in set(codes)})
r = p.post("/api/v1/auth/login", json={"username": "demo_viewer", "password": pw}, headers={"X-Forwarded-For": "198.51.100.77"})
print("valid login from a different client behind the same proxy:", r.status_code, "(429 = locked out by someone else's failures)")
