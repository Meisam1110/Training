"""Pure-ASGI middleware: security headers, request-size limit, request log, Origin check."""
from __future__ import annotations

import json
import logging
import time
import uuid
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("tms.request")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _envelope(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "fields": {}}}, ensure_ascii=False).encode()


async def _reply(send: Send, status: int, code: str, message: str) -> None:
    body = _envelope(code, message)
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool = False):
        self.app, self.hsts = app, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        api = scope["path"].startswith("/api/") or scope["path"] in ("/health", "/ready")

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                extra = {
                    "content-security-policy": CSP,
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                    "referrer-policy": "no-referrer",
                    "permissions-policy": "geolocation=(), camera=(), microphone=()",
                    "cross-origin-opener-policy": "same-origin",
                }
                if api:
                    extra["cache-control"] = "no-store"
                if self.hsts:
                    extra["strict-transport-security"] = "max-age=31536000; includeSubDomains"
                have = {k.lower() for k, _ in h}
                for k, v in extra.items():
                    if k.encode() not in have:
                        h.append((k.encode(), v.encode()))
            await send(message)

        await self.app(scope, receive, wrapped)


class BodyLimitMiddleware:
    """413 when a request body exceeds the limit (Content-Length or streamed)."""

    def __init__(self, app: ASGIApp, max_body: int, max_upload: int):
        self.app, self.max_body, self.max_upload = app, max_body, max_upload

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE:
            return await self.app(scope, receive, send)
        limit = self.max_upload if "/import/" in scope["path"] else self.max_body
        hdrs = dict(scope["headers"])
        cl = hdrs.get(b"content-length")
        if cl is not None:
            try:
                if int(cl) > limit:
                    return await _reply(send, 413, "validation", "حجم درخواست بیش از حد مجاز است")
            except ValueError:
                return await _reply(send, 400, "validation", "Content-Length نامعتبر")
        seen = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return msg

        async def track_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_send)
        except _TooLarge:
            if not started:
                await _reply(send, 413, "validation", "حجم درخواست بیش از حد مجاز است")


class _TooLarge(Exception):
    pass


class OriginCheckMiddleware:
    """Defence in depth next to the CSRF token: an unsafe request carrying an Origin header
    must come from this host or an allow-listed origin."""

    def __init__(self, app: ASGIApp, allowed: tuple[str, ...] = ()):
        self.app, self.allowed = app, set(allowed)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE:
            hdrs = {k.decode(): v.decode() for k, v in scope["headers"]}
            origin = hdrs.get("origin")
            if origin and origin != "null":
                host = hdrs.get("host", "")
                if urlsplit(origin).netloc != host and origin not in self.allowed:
                    return await _reply(send, 403, "forbidden", "مبدأ درخواست مجاز نیست")
            elif origin == "null":
                return await _reply(send, 403, "forbidden", "مبدأ درخواست مجاز نیست")
        await self.app(scope, receive, send)


class RequestLogMiddleware:
    """One JSON line per request. Path only -- never the query string (it can carry ``q=<name>``)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = rid
        t0 = time.perf_counter()
        status = 500

        async def wrapped(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            path = scope["path"]
            if path not in ("/health", "/ready") or status >= 400:
                log.info("request", extra={
                    "request_id": rid, "method": scope["method"], "path": path, "status": status,
                    "ms": round((time.perf_counter() - t0) * 1000, 1),
                    "user": scope.get("state", {}).get("user_id"),
                })
