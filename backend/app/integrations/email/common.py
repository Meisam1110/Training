"""Shared e-mail sender behaviour: validation, header-injection protection, dry-run, rate limit,
idempotency (per-recipient, so a retry never double-sends to someone who already got the mail)."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from html import unescape
from typing import Callable, Protocol, Sequence

from app.contracts import OutgoingEmail, SendResult

_ADDR_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                      r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")
_CTRL_RE = re.compile(r"[\r\n\x00]")
MAX_SUBJECT = 998


class MessageValidationError(ValueError):
    """Message rejected before sending (never echoes the offending value)."""


def check_header_value(value: str, what: str) -> str:
    if _CTRL_RE.search(value) or " " in value or " " in value:
        raise MessageValidationError(f"{what} contains a line break or control character (header injection)")
    return value


def check_address(addr: str) -> str:
    a = check_header_value(str(addr), "address").strip()
    if not _ADDR_RE.match(a) or len(a) > 254:
        raise MessageValidationError("invalid e-mail address")
    return a


def validate(msg: OutgoingEmail) -> tuple[list[str], list[str], str]:
    """Return (to, cc, subject) validated; raises MessageValidationError."""
    if not msg.to:
        raise MessageValidationError("no recipients")
    to = [check_address(a) for a in msg.to]
    cc = [check_address(a) for a in msg.cc]
    subject = check_header_value(msg.subject, "subject")
    if len(subject) > MAX_SUBJECT:
        raise MessageValidationError("subject too long")
    for name, _data, mime in msg.attachments:
        check_header_value(name, "attachment name")
        check_header_value(mime, "attachment mime type")
        if "/" not in mime:
            raise MessageValidationError("invalid attachment mime type")
    return to, cc, subject


def html_to_text(html: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|li)>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", unescape(t)).replace(" \n", "\n").strip()


class IdempotencyConflict(ValueError):
    """Same idempotency key re-used with DIFFERENT message content. Core should map this to HTTP 409."""


class IdempotencyInProgress(IdempotencyConflict):
    """Same key and content is still being sent by another call (pending, not yet stale). Map to 409 too."""


@dataclass
class IdemEntry:
    fingerprint: str
    state: str = "pending"                    # pending | done
    started_at: float = 0.0                   # wall-clock seconds
    results: dict[str, SendResult] = field(default_factory=dict)   # successful recipients only


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def fingerprint(msg: OutgoingEmail) -> str:
    """Digest of the FULL message content (subject, recipients, cc, body, attachments)."""
    h = hashlib.sha256()
    h.update(json.dumps({"s": msg.subject, "to": sorted(msg.to), "cc": sorted(msg.cc), "b": msg.html_body,
                         "a": [[n, hashlib.sha256(d).hexdigest(), m] for n, d, m in msg.attachments]},
                        ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return h.hexdigest()


class IdempotencyStore(Protocol):
    """Pluggable store (Core may back it with the database). Keys arrive already hashed.

    ``claim`` must be atomic: create a pending entry, or return the existing one after checking that the
    fingerprint matches (else raise IdempotencyConflict), that no live pending claim exists (else
    IdempotencyInProgress) and refreshing a *stale* pending claim (older than ``ttl_s``) so it can be retried.
    ``complete`` merges newly successful results and marks the entry done."""

    def claim(self, key_hash: str, fingerprint: str, now: float, ttl_s: float) -> IdemEntry: ...
    def complete(self, key_hash: str, results: dict[str, SendResult]) -> None: ...


class InMemoryIdempotencyStore:
    def __init__(self, max_keys: int = 10_000):
        self._d: dict[str, IdemEntry] = {}
        self._max = max_keys
        self._lock = threading.Lock()

    def claim(self, key_hash: str, fingerprint: str, now: float, ttl_s: float) -> IdemEntry:
        with self._lock:
            e = self._d.get(key_hash)
            if e is None:
                if len(self._d) >= self._max:
                    self._d.pop(next(iter(self._d)))
                e = self._d[key_hash] = IdemEntry(fingerprint, "pending", now)
                return IdemEntry(e.fingerprint, e.state, e.started_at, dict(e.results))
            if e.fingerprint != fingerprint:
                raise IdempotencyConflict("idempotency key was already used with different message content")
            if e.state == "pending" and now - e.started_at < ttl_s:
                raise IdempotencyInProgress("a send with this idempotency key is still in progress")
            e.state, e.started_at = "pending", now          # done -> resume, or stale pending -> retry
            return IdemEntry(e.fingerprint, e.state, e.started_at, dict(e.results))

    def complete(self, key_hash: str, results: dict[str, SendResult]) -> None:
        with self._lock:
            e = self._d.get(key_hash)
            if e is not None:
                e.results.update(results)
                e.state = "done"


class RateLimiter:
    """Minimum spacing between send operations (``per_minute`` <= 0 disables)."""

    def __init__(self, per_minute: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval = 60.0 / per_minute if per_minute and per_minute > 0 else 0.0
        self._clock, self._sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._sleep(self._next - now)
                now = self._next
            self._next = now + self.interval


class BaseSender:
    """Template method: subclasses implement ``_deliver`` for the real transport."""

    def __init__(self, *, idempotency_store: IdempotencyStore | None = None, rate_limit_per_min: float = 0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 wall_clock: Callable[[], float] = time.time, pending_ttl_s: float = 300.0):
        self.store: IdempotencyStore = idempotency_store or InMemoryIdempotencyStore()
        self._wall = wall_clock
        self.pending_ttl_s = pending_ttl_s
        self._limiter = RateLimiter(rate_limit_per_min, clock, sleep)
        self._secrets: list[str] = []

    def _deliver(self, to: Sequence[str], cc: Sequence[str], subject: str, msg: OutgoingEmail) -> list[SendResult]:
        raise NotImplementedError

    def send(self, msg: OutgoingEmail, *, dry_run: bool = False) -> list[SendResult]:
        try:
            to, cc, subject = validate(msg)
        except MessageValidationError as exc:
            recips = [str(a) for a in list(msg.to) + list(msg.cc)] or [""]
            return [SendResult(recipient=r if "\n" not in r and "\r" not in r else "<invalid>", ok=False,
                               error=str(exc)) for r in recips]
        everyone = list(dict.fromkeys(to + cc))
        if dry_run:
            return [SendResult(recipient=r, ok=True, message_id="dry-run") for r in everyone]
        kh = hash_key(msg.idempotency_key) if msg.idempotency_key else ""
        done: dict[str, SendResult] = {}
        if kh:      # raises IdempotencyConflict / IdempotencyInProgress -> Core answers 409
            done = self.store.claim(kh, fingerprint(msg), self._wall(), self.pending_ttl_s).results
        results: dict[str, SendResult] = dict(done)
        fresh_ok: dict[str, SendResult] = {}
        try:
            todo_to = [r for r in to if r not in done]
            todo_cc = [r for r in cc if r not in done]
            if not todo_to and todo_cc:                 # only cc left: promote so the transport has a To
                todo_to, todo_cc = todo_cc, []
            # one message per To recipient (nobody sees the other recipients' addresses); an explicit Cc list
            # is applied to each of those messages
            for recipient in todo_to:
                self._limiter.wait()
                group_cc = todo_cc
                try:
                    fresh = self._deliver([recipient], group_cc, subject, msg)
                except Exception as exc:  # noqa: BLE001
                    from app.integrations.redact import sanitize_error
                    err = sanitize_error(exc, self._secrets)
                    fresh = [SendResult(recipient=r, ok=False, error=err) for r in [recipient] + list(group_cc)]
                for r in fresh:
                    results[r.recipient] = r
                    if r.ok:
                        fresh_ok[r.recipient] = r
        finally:
            if kh:
                self.store.complete(kh, fresh_ok)
        return [results[r] for r in everyone if r in results]
