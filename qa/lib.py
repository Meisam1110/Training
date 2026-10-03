"""Tiny QA HTTP client: cookie login + CSRF handling. Usage: from lib import Client"""
import os, httpx
BASE = os.environ.get("QA_BASE", "http://127.0.0.1:18700")
PW = os.environ.get("QA_DEMO_PW", "")

class Client:
    def __init__(self, base=BASE, headers=None):
        self.c = httpx.Client(base_url=base, timeout=60, headers=headers or {})
        self.csrf = ""
        self.user = None
    def login(self, u, p):
        r = self.c.post("/api/v1/auth/login", json={"username": u, "password": p})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]; self.user = u
        return r
    def req(self, m, path, csrf=True, **kw):
        h = kw.pop("headers", {}) or {}
        if csrf and self.csrf and m.upper() in ("POST","PUT","PATCH","DELETE"):
            h["X-CSRF-Token"] = self.csrf
        return self.c.request(m, "/api/v1" + path if not path.startswith("/api") and not path.startswith("/health") and not path.startswith("/ready") else path, headers=h, **kw)
    def get(self, p, **k): return self.req("GET", p, **k)
    def post(self, p, **k): return self.req("POST", p, **k)
    def put(self, p, **k): return self.req("PUT", p, **k)
    def patch(self, p, **k): return self.req("PATCH", p, **k)
