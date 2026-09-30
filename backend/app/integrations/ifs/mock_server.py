"""Mock IFS server for tests and demos (synthetic data only).

Supports the three auth modes, expiring tokens/sessions, OData-style pagination
(``$top``/``$skip`` or ``@odata.nextLink``), ``$filter=<field> ge <iso>`` and fault injection.

    python -m app.integrations.ifs.mock_server --port 8099

Control endpoint (no auth): POST /__control  {"fail_429": 2, "fail_500": 1, "token_ttl": 3600,
"session_ttl": 3600, "use_next_link": true, "expire_now": true}
"""
from __future__ import annotations

import base64
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

CLIENT_ID, CLIENT_SECRET = "mock-client", "mock-client-secret"
USERNAME, PASSWORD = "mock-user", "mock-password"


def synthetic_people(n: int = 25) -> list[dict[str, Any]]:
    out = []
    for i in range(1, n + 1):
        out.append({
            "EmpNo": f"MOCK{i:04d}", "FirstName": f"Test{i}", "LastName": f"Person{i}",
            "FarsiFirstName": "علي", "FarsiLastName": "كريمي", "Gender": "Male" if i % 2 else "Female",
            "Email": f"Test{i}@Example.Test", "Mobile": f"935000{i:04d}", "NationalCode": f"{i:09d}",
            "Division": "NWG", "CostCenter": "23700", "OrgCode": "NW-A", "PositionTitle": "Engineer",
            "SupEmpNo": "MOCK0001" if i > 1 else "", "EmployeeStatus": "Active" if i % 10 else "Terminated",
            "ModifiedDate": f"2024-0{1 + i % 9}-15T08:00:00Z",
        })
    return out


class MockIfsState:
    def __init__(self, people: list[dict[str, Any]] | None = None):
        self.people = people if people is not None else synthetic_people()
        self.lock = threading.Lock()
        self.tokens: dict[str, float] = {}
        self.sessions: dict[str, float] = {}
        self.token_ttl = 3600.0
        self.session_ttl = 3600.0
        self.fail_429 = 0
        self.fail_500 = 0
        self.use_next_link = False
        self.log: list[str] = []     # "METHOD path" only, never credentials

    def configure(self, **kw: Any) -> None:
        with self.lock:
            if kw.pop("expire_now", False):
                self.tokens.clear()
                self.sessions.clear()
            for k, v in kw.items():
                if hasattr(self, k) and k not in ("lock", "people", "log"):
                    setattr(self, k, v)


def create_app(state: MockIfsState | None = None, employees_path: str = "/PersonInfo") -> FastAPI:
    st = state or MockIfsState()
    app = FastAPI(title="Mock IFS")
    app.state.mock = st

    async def _form(request: Request) -> dict[str, str]:      # avoids the python-multipart dependency
        return {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}

    @app.post("/__control")
    async def control(request: Request):
        st.configure(**(await request.json()))
        return {"ok": True}

    @app.post("/oauth/token")
    async def token(request: Request):
        f = await _form(request)
        grant_type, client_id, client_secret = f.get("grant_type", ""), f.get("client_id", ""), f.get("client_secret", "")
        st.log.append("POST /oauth/token")
        if grant_type != "client_credentials" or client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        tok = secrets.token_urlsafe(24)
        with st.lock:
            st.tokens[tok] = time.time() + st.token_ttl
        return {"access_token": tok, "token_type": "Bearer", "expires_in": int(st.token_ttl)}

    @app.post("/login")
    async def login(request: Request):
        f = await _form(request)
        username, password = f.get("username", ""), f.get("password", "")
        st.log.append("POST /login")
        if username != USERNAME or password != PASSWORD:
            return JSONResponse({"error": "bad credentials"}, status_code=401)
        sid = secrets.token_urlsafe(24)
        with st.lock:
            st.sessions[sid] = time.time() + st.session_ttl
        r = JSONResponse({"ok": True})
        r.set_cookie("IFSSESSION", sid, httponly=True)
        return r

    def _authorized(request: Request) -> str | None:
        """Return None if authorised, else the failure kind: 'login' (redirect) or '401'."""
        h = request.headers.get("authorization", "")
        now = time.time()
        if h.lower().startswith("bearer "):
            exp = st.tokens.get(h[7:])
            return None if exp and exp > now else "401"
        if h.lower().startswith("basic "):
            try:
                u, _, p = base64.b64decode(h[6:]).decode().partition(":")
            except Exception:  # noqa: BLE001
                return "401"
            return None if (u, p) == (USERNAME, PASSWORD) else "401"
        sid = request.cookies.get("IFSSESSION")
        if sid:
            exp = st.sessions.get(sid)
            return None if exp and exp > now else "login"
        return "401"

    @app.get(employees_path)
    async def employees(request: Request):
        st.log.append(f"GET {employees_path}")
        with st.lock:
            if st.fail_429 > 0:
                st.fail_429 -= 1
                return Response(status_code=429, headers={"Retry-After": "0"})
            if st.fail_500 > 0:
                st.fail_500 -= 1
                return Response(status_code=500)
        bad = _authorized(request)
        if bad == "login":
            return Response(status_code=302, headers={"Location": "/login"})
        if bad:
            return Response(status_code=401)
        q = request.query_params
        top = int(q.get("$top", 10_000))
        skip = int(q.get("$skip", 0))
        rows = st.people
        flt = q.get("$filter")
        if flt:
            f, op, val = flt.split(" ", 2)
            if op != "ge":
                return JSONResponse({"error": "unsupported filter"}, status_code=400)
            rows = [r for r in rows if str(r.get(f, "")) >= val]
        page = rows[skip:skip + top]
        body: dict[str, Any] = {"value": page}
        if st.use_next_link and skip + top < len(rows):
            body["@odata.nextLink"] = f"{employees_path}?$top={top}&$skip={skip + top}" + \
                (f"&$filter={flt}" if flt else "")
        return body

    return app


class MockIfsServer:
    """Runs the mock on a random localhost port in a background thread (uvicorn)."""

    def __init__(self, state: MockIfsState | None = None, employees_path: str = "/PersonInfo"):
        import socket

        import uvicorn
        self.state = state or MockIfsState()
        self.app = create_app(self.state, employees_path)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self._server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port,
                                                     log_level="critical"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "MockIfsServer":
        self._thread.start()
        for _ in range(200):
            if self._server.started:
                return self
            time.sleep(0.02)
        raise RuntimeError("mock server did not start")

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()


if __name__ == "__main__":  # pragma: no cover
    import argparse

    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    uvicorn.run(create_app(), host="127.0.0.1", port=ap.parse_args().port)
