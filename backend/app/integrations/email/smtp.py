"""SMTP sender (STARTTLS or implicit SSL, optional auth). Config: {"host","port","username","password",
"starttls","use_ssl","from_addr","from_name","timeout_s","verify_tls","ca_bundle","rate_limit_per_min"}."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import formataddr, make_msgid
from typing import Any, Callable, Mapping, Sequence

from app.contracts import OutgoingEmail, SendResult
from app.integrations.redact import redact_text, sanitize_error

from .common import BaseSender, MessageValidationError, check_address, check_header_value, html_to_text


class SmtpSender(BaseSender):
    def __init__(self, config: Mapping[str, Any], *, smtp_factory: Callable[..., smtplib.SMTP] | None = None, **kw: Any):
        super().__init__(rate_limit_per_min=float(config.get("rate_limit_per_min") or 0), **kw)
        self.host = str(config.get("host", "")).strip()
        if not self.host:
            raise MessageValidationError("smtp: host is required")
        self.use_ssl = bool(config.get("use_ssl", False))
        self.starttls = bool(config.get("starttls", True)) and not self.use_ssl
        self.port = int(config.get("port") or (465 if self.use_ssl else 587 if self.starttls else 25))
        self.username = str(config.get("username", ""))
        self.password = str(config.get("password", ""))
        self.from_addr = check_address(str(config.get("from_addr", "") or self.username))
        self.from_name = check_header_value(str(config.get("from_name", "")), "from_name")
        self.timeout = float(config.get("timeout_s") or 30)
        self._secrets = [s for s in (self.password,) if s]
        self._smtp_factory = smtp_factory
        ctx = ssl.create_default_context(cafile=config.get("ca_bundle") or None)
        if config.get("verify_tls", True) in (False, "false", "False", 0):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._ctx = ctx

    # ------------------------------------------------------------------
    def _connect(self) -> smtplib.SMTP:
        if self._smtp_factory:
            s = self._smtp_factory(self.host, self.port, timeout=self.timeout)
        elif self.use_ssl:
            s = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=self._ctx)
        else:
            s = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        try:
            s.ehlo()
            if self.starttls:
                s.starttls(context=self._ctx)
                s.ehlo()
            if self.username:
                s.login(self.username, self.password)
        except Exception:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        return s

    def test_connection(self) -> tuple[bool, str]:
        try:
            s = self._connect()
            try:
                s.noop()
            finally:
                s.quit()
            return True, f"OK: connected to SMTP server{' with STARTTLS' if self.starttls else ''}" \
                         f"{', authenticated' if self.username else ''}"
        except smtplib.SMTPAuthenticationError as exc:
            return False, f"SMTP authentication failed (code {exc.smtp_code})"
        except Exception as exc:  # noqa: BLE001
            return False, redact_text(sanitize_error(exc, self._secrets), self._secrets)

    def _build(self, to: Sequence[str], cc: Sequence[str], subject: str, msg: OutgoingEmail) -> EmailMessage:
        m = EmailMessage(policy=SMTP_POLICY)
        m["From"] = formataddr((self.from_name, self.from_addr)) if self.from_name else self.from_addr
        m["To"] = ", ".join(to)
        if cc:
            m["Cc"] = ", ".join(cc)
        m["Subject"] = subject
        m["Message-ID"] = make_msgid(domain=self.from_addr.split("@")[1])
        m.set_content(html_to_text(msg.html_body) or " ")
        m.add_alternative(msg.html_body, subtype="html")
        for name, data, mime in msg.attachments:
            maintype, _, subtype = mime.partition("/")
            m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
        return m

    def _deliver(self, to: Sequence[str], cc: Sequence[str], subject: str, msg: OutgoingEmail) -> list[SendResult]:
        m = self._build(to, cc, subject, msg)
        mid = str(m["Message-ID"])
        s = self._connect()
        try:
            refused = s.send_message(m, from_addr=self.from_addr, to_addrs=list(to) + list(cc))
        except smtplib.SMTPRecipientsRefused as exc:
            refused = exc.recipients
        finally:
            try:
                s.quit()
            except Exception:  # noqa: BLE001
                pass
        out = []
        for r in list(to) + list(cc):
            if r in refused:
                code = refused[r][0]
                out.append(SendResult(recipient=r, ok=False, error=f"recipient refused by server (SMTP {code})"))
            else:
                out.append(SendResult(recipient=r, ok=True, message_id=mid))
        return out
