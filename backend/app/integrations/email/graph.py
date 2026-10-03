"""Microsoft Graph sendMail sender (app-only OAuth2 client credentials).
Config: {"tenant_id","client_id","client_secret","sender", optional "authority_url", "graph_url",
"timeout_s","save_to_sent_items","rate_limit_per_min","verify_tls"}."""
from __future__ import annotations

import base64
import threading
import time
import uuid
from typing import Any, Mapping, Sequence

import httpx

from app.contracts import OutgoingEmail, SendResult
from app.integrations.redact import redact_text, sanitize_error
from app.integrations.urlcheck import UnsafeUrlError, check_url

from .common import BaseSender, MessageValidationError, check_address

RETRY = {429, 500, 502, 503, 504}


class GraphSender(BaseSender):
    def __init__(self, config: Mapping[str, Any], *, transport: httpx.BaseTransport | None = None,
                 max_retries: int = 3, **kw: Any):
        super().__init__(rate_limit_per_min=float(config.get("rate_limit_per_min") or 0), **kw)
        for k in ("tenant_id", "client_id", "client_secret", "sender"):
            if not str(config.get(k, "")).strip():
                raise MessageValidationError(f"graph: {k} is required")
        self.tenant = str(config["tenant_id"]).strip()
        if not all(c.isalnum() or c in "-." for c in self.tenant):
            raise MessageValidationError("graph: invalid tenant_id")
        self.client_id = str(config["client_id"])
        self.client_secret = str(config["client_secret"])
        self.sender = check_address(str(config["sender"]))
        self.authority = str(config.get("authority_url") or "https://login.microsoftonline.com").rstrip("/")
        self.graph = str(config.get("graph_url") or "https://graph.microsoft.com").rstrip("/")
        allow_private = config.get("allow_private_hosts", False) in (True, "true", "True", 1, "1")
        try:
            self.authority = check_url(self.authority, "authority_url", allow_private_hosts=allow_private).rstrip("/")
            self.graph = check_url(self.graph, "graph_url", allow_private_hosts=allow_private).rstrip("/")
        except UnsafeUrlError as exc:
            raise MessageValidationError(f"graph: {exc}") from None
        self.save_to_sent = bool(config.get("save_to_sent_items", True))
        self.max_retries = max_retries
        self._secrets = [self.client_secret]
        self._sleep = kw.get("sleep", time.sleep)
        self._client = httpx.Client(transport=transport, follow_redirects=False, timeout=float(config.get("timeout_s") or 30),
                                    verify=config.get("verify_tls", True) not in (False, "false", "False", 0))
        self._token = ""
        self._expiry = 0.0
        self._lock = threading.Lock()

    def _get_token(self, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and time.monotonic() < self._expiry - 60:
                return self._token
            r = self._client.post(f"{self.authority}/{self.tenant}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": self.client_id,
                "client_secret": self.client_secret, "scope": f"{self.graph}/.default"})
            if r.status_code != 200:
                raise PermissionError(f"Graph token request rejected (HTTP {r.status_code})")
            body = r.json()
            self._token = str(body["access_token"])
            self._expiry = time.monotonic() + float(body.get("expires_in", 3600))
            self._secrets = [self.client_secret, self._token]
            return self._token

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._get_token(force=True)
            return True, "OK: Graph token acquired (app-only). Mail.Send permission is verified on first send."
        except Exception as exc:  # noqa: BLE001
            return False, redact_text(sanitize_error(exc, self._secrets), self._secrets)

    @staticmethod
    def _rcpt(a: str) -> dict:
        return {"emailAddress": {"address": a}}

    def _payload(self, to: Sequence[str], cc: Sequence[str], subject: str, msg: OutgoingEmail) -> dict:
        m: dict[str, Any] = {"subject": subject, "body": {"contentType": "HTML", "content": msg.html_body},
                             "toRecipients": [self._rcpt(a) for a in to]}
        if cc:
            m["ccRecipients"] = [self._rcpt(a) for a in cc]
        if msg.attachments:
            m["attachments"] = [{"@odata.type": "#microsoft.graph.fileAttachment", "name": n, "contentType": mime,
                                 "contentBytes": base64.b64encode(d).decode()} for n, d, mime in msg.attachments]
        return {"message": m, "saveToSentItems": self.save_to_sent}

    def _deliver(self, to: Sequence[str], cc: Sequence[str], subject: str, msg: OutgoingEmail) -> list[SendResult]:
        payload = self._payload(to, cc, subject, msg)
        url = f"{self.graph}/v1.0/users/{self.sender}/sendMail"
        reauth, attempt = False, 0
        while True:
            r = self._client.post(url, json=payload, headers={"Authorization": f"Bearer {self._get_token()}"})
            if r.status_code == 401 and not reauth:
                reauth = True
                self._get_token(force=True)
                continue
            if r.status_code in RETRY and attempt < self.max_retries:
                try:
                    delay = min(float(r.headers.get("Retry-After", 2 ** attempt)), 30.0)
                except ValueError:
                    delay = 2.0
                attempt += 1
                self._sleep(delay)
                continue
            break
        recipients = list(to) + list(cc)
        if r.status_code == 202:
            mid = f"graph-{uuid.uuid4()}"      # sendMail returns no id; this is a local correlation id
            return [SendResult(recipient=a, ok=True, message_id=mid) for a in recipients]
        err = f"Graph sendMail failed (HTTP {r.status_code})"
        return [SendResult(recipient=a, ok=False, error=err) for a in recipients]
