"""IFS employee source (``contracts.EmployeeSource``).

Auth modes: ``oauth2_client_credentials`` (token cache, refresh before expiry, one retry on 401),
``basic``, ``session_login`` (form POST + cookie jar, transparent re-login on expiry).
Resilience: timeouts, exponential backoff + jitter on 429/5xx/transport errors (honours
Retry-After), circuit breaker, TLS verification on by default. Secrets are never logged and are
scrubbed from every exception message this module raises.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Mapping
from urllib.parse import urljoin, urlsplit

import httpx

from app.contracts import EmployeeRecord, SyncReport
from app.integrations.redact import redact_text, sanitize_error
from app.integrations.urlcheck import UnsafeUrlError, check_url
from app.persian import normalize_fa

from .config import REQUIRED_TARGETS, IfsConfig
from .resilience import CircuitBreaker, backoff_delay

log = logging.getLogger("app.integrations.ifs")

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_PAGES = 100_000


class IfsError(Exception):
    """Base error. Messages are already sanitised (no secrets, no response bodies)."""


class IfsAuthError(IfsError):
    pass


class IfsUpstreamError(IfsError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class CircuitOpenError(IfsError):
    pass


class _TooLarge(Exception):
    pass


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, Mapping):
            return None
        if part in cur:
            cur = cur[part]
        else:
            lowered = {str(k).lower(): v for k, v in cur.items()}
            if part.lower() not in lowered:
                return None
            cur = lowered[part.lower()]
    return cur


def _first(rec: Mapping[str, Any], candidates: Iterable[str]) -> str:
    for c in candidates:
        v = _get_path(rec, c)
        if v is None or isinstance(v, (dict, list)):
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _parse_iso(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso_z(d: datetime) -> str:
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


MAX_FIELD_CHARS = 300


def map_employee(rec: Mapping[str, Any], cfg: IfsConfig, notes: list[str] | None = None) -> EmployeeRecord | None:
    """Apply ``cfg.field_map`` to one JSON record. Returns None when required fields are missing.
    Over-long values are truncated to MAX_FIELD_CHARS; the field NAME is appended to *notes* (never the value)."""
    fm = cfg.field_map
    vals = {k: _first(rec, fm[k]) for k in fm}
    for k, v in vals.items():
        if len(v) > MAX_FIELD_CHARS:
            vals[k] = v[:MAX_FIELD_CHARS]
            if notes is not None:
                notes.append(k)
    if any(not vals.get(k) for k in REQUIRED_TARGETS):
        return None
    from app.integrations.excel import normalize as N  # digit/leading-zero fixes shared with Excel path
    g = vals["gender"].lower()
    gender = "male" if g in ("male", "m", "مرد") else "female" if g in ("female", "f", "زن") else ""
    st = vals["status"]
    status = "Active" if not st or st.lower() in cfg.active_statuses else st
    return EmployeeRecord(
        emp_no=N.clean_emp_no(vals["emp_no"]),
        first_name_en=vals["first_name_en"], last_name_en=vals["last_name_en"],
        first_name_fa=normalize_fa(vals["first_name_fa"]), last_name_fa=normalize_fa(vals["last_name_fa"]),
        gender=gender,  # type: ignore[arg-type]
        email=N.clean_email(vals["email"]), mobile=N.fix_mobile(vals["mobile"]),
        national_code=N.fix_national_code(vals["national_code"]),
        division=vals["division"], cost_center=vals["cost_center"], org_code=vals["org_code"],
        position_title=vals["position_title"], supervisor_emp_no=N.clean_emp_no(vals["supervisor_emp_no"]),
        status=status)


def extract_page(payload: Any) -> tuple[list[Mapping[str, Any]], str | None]:
    """Return (records, next_link) for OData v4 (`value`), OData v2 (`d.results`) or bare lists."""
    if isinstance(payload, list):
        return payload, None
    if isinstance(payload, dict):
        if isinstance(payload.get("value"), list):
            return payload["value"], payload.get("@odata.nextLink") or payload.get("odata.nextLink")
        d = payload.get("d")
        if isinstance(d, dict) and isinstance(d.get("results"), list):
            return d["results"], d.get("__next")
        for k in ("items", "results", "data"):
            if isinstance(payload.get(k), list):
                return payload[k], payload.get("next") or payload.get("nextLink")
    raise IfsUpstreamError("Unexpected response shape from IFS (no record list found)")


class IfsEmployeeSource:
    def __init__(self, config: Mapping[str, Any] | IfsConfig, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, rand: Callable[[], float] = random.random,
                 clock: Callable[[], float] = time.monotonic):
        self.cfg = config if isinstance(config, IfsConfig) else IfsConfig.from_dict(config)
        self._sleep, self._rand, self._clock = sleep, rand, clock
        self._secrets = self.cfg.secrets
        self.breaker = CircuitBreaker(self.cfg.breaker_threshold, self.cfg.breaker_cooldown_s, clock)
        verify: Any = self.cfg.ca_bundle or self.cfg.verify_tls
        if not self.cfg.verify_tls:
            log.warning("IFS connector: TLS verification is DISABLED by configuration")
        self._client = httpx.Client(
            verify=verify, follow_redirects=False, transport=transport,
            timeout=httpx.Timeout(self.cfg.timeout_s, connect=min(10.0, self.cfg.timeout_s)))
        self._base = urlsplit(self.cfg.base_url)
        self._token = ""
        self._token_expiry = 0.0
        self._logged_in = False
        self._lock = threading.RLock()
        self.last_report: SyncReport | None = None
        self.truncated = self.cancelled = False
        self.stats = {"requests": 0, "retries": 0, "reauth": 0}

    # ---------------------------------------------------------------- lifecycle
    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------------- helpers
    def _clean(self, text: str) -> str:
        return redact_text(text, self._secrets)

    def _url(self, path_or_url: str) -> str:
        return urljoin(self.cfg.base_url + "/", path_or_url.lstrip("/")) if not path_or_url.startswith("http") \
            else path_or_url

    def _same_origin(self, url: str) -> bool:
        u = urlsplit(url)
        return (u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80)) == \
               (self._base.scheme, self._base.hostname, self._base.port or (443 if self._base.scheme == "https" else 80))

    # ---------------------------------------------------------------- low-level send (retry + breaker)
    def _send(self, method: str, url: str, **kw: Any) -> httpx.Response:
        if not self.breaker.allow():
            raise CircuitOpenError("IFS circuit breaker is open; not calling IFS until the cooldown ends")
        try:      # scheme / userinfo / private-host guard on EVERY request (token, login, api, next links)
            check_url(url, "IFS URL", allow_private_hosts=self.cfg.allow_private_hosts)
        except UnsafeUrlError as exc:
            raise IfsUpstreamError(f"Refusing to call an unsafe URL: {exc}") from None
        attempt = 0
        while True:
            self.stats["requests"] += 1
            try:
                resp = self._read_capped(method, url, **kw)
            except _TooLarge:
                raise IfsUpstreamError("IFS response exceeds max_response_bytes; aborted") from None
            except httpx.HTTPError as exc:
                err: IfsError = IfsUpstreamError(f"IFS request failed ({type(exc).__name__})")
                retry_after = None
            else:
                log.debug("IFS %s %s -> %s", method, urlsplit(url).path, resp.status_code)
                if resp.status_code not in RETRY_STATUS and resp.status_code < 500:
                    self.breaker.success()
                    return resp
                err = IfsUpstreamError(f"IFS returned HTTP {resp.status_code}", resp.status_code)
                retry_after = self._retry_after(resp)
            if attempt >= self.cfg.max_retries:
                self.breaker.failure()
                raise err
            delay = backoff_delay(attempt, self.cfg.backoff_base_s, self.cfg.backoff_max_s, self._rand)
            if retry_after is not None:
                delay = min(max(delay, retry_after), self.cfg.backoff_max_s)
            attempt += 1
            self.stats["retries"] += 1
            self._sleep(delay)

    def _read_capped(self, method: str, url: str, **kw: Any) -> httpx.Response:
        """Stream the body and abort once ``max_response_bytes`` is exceeded (memory guard)."""
        cap = self.cfg.max_response_bytes
        with self._client.stream(method, url, **kw) as r:
            declared = r.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > cap:
                raise _TooLarge
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > cap:
                    raise _TooLarge
            return httpx.Response(r.status_code, headers=r.headers, content=bytes(buf), request=r.request)

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        v = resp.headers.get("Retry-After")
        if not v:
            return None
        try:
            return max(0.0, float(v))
        except ValueError:
            return None

    # ---------------------------------------------------------------- authentication
    def _authenticate(self, force: bool = False) -> dict[str, str]:
        mode = self.cfg.auth_mode
        with self._lock:
            if mode == "basic":
                return {}
            if mode == "oauth2_client_credentials":
                skew = 30.0
                if force or not self._token or self._clock() >= self._token_expiry - skew:
                    self._fetch_token()
                return {"Authorization": f"Bearer {self._token}"}
            if force or not self._logged_in:
                self._login()
            return {}

    def _fetch_token(self) -> None:
        data = {"grant_type": "client_credentials", "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret}
        if self.cfg.scope:
            data["scope"] = self.cfg.scope
        resp = self._send("POST", self._url(self.cfg.token_url), data=data,
                          headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise IfsAuthError(f"Token endpoint rejected the credentials (HTTP {resp.status_code})")
        try:
            body = resp.json()
            token = str(body["access_token"])
            ttl = float(body.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError):
            raise IfsAuthError("Token endpoint returned an unexpected response") from None
        self._token, self._token_expiry = token, self._clock() + ttl
        self._secrets = self.cfg.secrets + [token]      # scrub the live token from any later message

    def _login(self) -> None:
        self._client.cookies.clear()
        resp = self._send("POST", self._url(self.cfg.login_url), data={
            self.cfg.login_user_field: self.cfg.username, self.cfg.login_password_field: self.cfg.password})
        if resp.status_code >= 400 or not len(self._client.cookies.jar):
            raise IfsAuthError(f"Login was rejected or did not create a session (HTTP {resp.status_code})")
        self._logged_in = True

    def _invalidate(self) -> None:
        with self._lock:
            self._token, self._token_expiry, self._logged_in = "", 0.0, False

    def _session_expired(self, resp: httpx.Response) -> bool:
        if resp.status_code == 401:
            return True
        if self.cfg.auth_mode == "session_login" and resp.status_code in (302, 303, 307):
            login_path = urlsplit(self.cfg.login_url).path.rstrip("/")
            loc = urlsplit(resp.headers.get("location", "")).path.rstrip("/")
            return bool(login_path) and loc.endswith(login_path)
        return False

    def _api(self, method: str, url: str, **kw: Any) -> httpx.Response:
        """Authenticated request; on 401/expired session re-authenticates exactly once."""
        if not self._same_origin(url):     # the Authorization header / session cookie never leave base_url's origin
            raise IfsUpstreamError("Refusing to send credentials to a different host")
        for attempt in (0, 1):
            headers = {"Accept": "application/json", **self._authenticate(force=False), **kw.pop("headers", {})}
            auth = httpx.BasicAuth(self.cfg.username, self.cfg.password) if self.cfg.auth_mode == "basic" else None
            resp = self._send(method, url, headers=headers, auth=auth, **kw) if auth else \
                self._send(method, url, headers=headers, **kw)
            if not self._session_expired(resp):
                if 300 <= resp.status_code < 400:
                    raise IfsUpstreamError(f"IFS answered with a redirect (HTTP {resp.status_code}); redirects are not followed")
                return resp
            if self.cfg.auth_mode == "basic" or attempt == 1:
                raise IfsAuthError("IFS rejected the credentials (HTTP 401)")
            self.stats["reauth"] += 1
            self._invalidate()
            kw.pop("headers", None)
        raise IfsAuthError("unreachable")  # pragma: no cover

    # ---------------------------------------------------------------- EmployeeSource
    def test_connection(self) -> tuple[bool, str]:
        try:
            resp = self._api("GET", self._url(self.cfg.employees_path), params={"$top": 1})
            if resp.status_code >= 400:
                return False, f"Authenticated but the employee endpoint returned HTTP {resp.status_code}; " \
                              f"check employees_path"
            records, _ = extract_page(resp.json())
            return True, f"OK: {self.cfg.auth_mode} authentication works; employee endpoint readable " \
                         f"({len(records)} sample record)"
        except IfsError as exc:
            return False, self._clean(str(exc))
        except Exception as exc:  # noqa: BLE001 - never leak internals/secrets
            return False, self._clean(sanitize_error(exc, self._secrets))

    def fetch_employee_chunks(self, chunk_size: int = 500, modified_since: datetime | None = None,
                              **kw: Any) -> Iterator[list[EmployeeRecord]]:
        """Same as ``fetch_employees`` but yields lists of at most *chunk_size* records, so Core can commit
        per chunk (bounded memory, progress survives a crash)."""
        buf: list[EmployeeRecord] = []
        for emp in self.fetch_employees(modified_since, **kw):
            buf.append(emp)
            if len(buf) >= chunk_size:
                yield buf
                buf = []
        if buf:
            yield buf

    def fetch_employees(self, modified_since: datetime | None = None, *, max_records: int | None = None,
                        should_cancel: Callable[[], bool] | None = None,
                        on_progress: Callable[[int, int], None] | None = None) -> Iterator[EmployeeRecord]:
        """Streaming generator (never builds the full list). ``max_records`` stops after N employees
        (``self.truncated = True``); ``should_cancel()`` is polled between records and pages
        (``self.cancelled = True``); ``on_progress(records_yielded, pages_fetched)`` is called after each page."""
        report = SyncReport(source="ifs", started_at=datetime.now(timezone.utc))
        self.last_report = report
        self.truncated = self.cancelled = False
        pages = 0
        cfg = self.cfg
        params: dict[str, Any] = {"$top": cfg.page_size, "$skip": 0}
        if modified_since is not None and cfg.delta_mode == "server" and cfg.modified_field:
            params["$filter"] = f"{cfg.modified_field} ge {_iso_z(modified_since)}"
        url: str | None = self._url(cfg.employees_path)
        seen_links: set[str] = set()
        idx = 0
        try:
            for _ in range(MAX_PAGES):
                resp = self._api("GET", url, params=params)  # type: ignore[arg-type]
                if resp.status_code >= 400:
                    raise IfsUpstreamError(f"IFS returned HTTP {resp.status_code} for the employee list",
                                           resp.status_code)
                try:
                    payload = resp.json()
                except ValueError:
                    raise IfsUpstreamError("IFS returned a non-JSON response") from None
                records, next_link = extract_page(payload)
                pages += 1
                for rec in records:
                    if should_cancel is not None and should_cancel():
                        self.cancelled = True
                        report.errors.append("cancelled by caller; result is partial")
                        return
                    if max_records is not None and report.created >= max_records:
                        self.truncated = True
                        report.errors.append(f"max_records={max_records} reached; result is partial")
                        return
                    idx += 1
                    if not isinstance(rec, Mapping):
                        report.skipped += 1
                        report.errors.append(f"record {idx}: not an object")
                        continue
                    if modified_since is not None and cfg.delta_mode == "client" and cfg.modified_field:
                        m = _parse_iso(_get_path(rec, cfg.modified_field))
                        if m is not None and m < (modified_since if modified_since.tzinfo
                                                  else modified_since.replace(tzinfo=timezone.utc)):
                            report.unchanged += 1
                            continue
                    notes: list[str] = []
                    try:
                        emp = map_employee(rec, cfg, notes)
                    except Exception as exc:  # noqa: BLE001 - one bad record never aborts the sync
                        report.skipped += 1
                        report.errors.append(f"record {idx}: could not be mapped ({type(exc).__name__})")
                        continue
                    for n in notes:
                        report.errors.append(f"record {idx}: field '{n}' was over-long and truncated")
                    if emp is None:
                        report.skipped += 1
                        report.errors.append(f"record {idx}: required field(s) missing "
                                             f"({', '.join(REQUIRED_TARGETS)}); check field_map")
                        continue
                    report.created += 1
                    yield emp
                if on_progress is not None:
                    on_progress(report.created, pages)
                if next_link:
                    nxt = urljoin(str(resp.url), next_link)
                    if not self._same_origin(nxt):
                        raise IfsUpstreamError("Refusing to follow a pagination link to a different host")
                    if nxt in seen_links:
                        raise IfsUpstreamError("Pagination loop detected")
                    seen_links.add(nxt)
                    url, params = nxt, None            # type: ignore[assignment]
                elif len(records) >= cfg.page_size and cfg.page_size > 0 and records:
                    params["$skip"] = int(params["$skip"]) + len(records)
                else:
                    break
            else:
                raise IfsUpstreamError("Too many pages; aborting")
        except IfsError as exc:
            report.errors.append(self._clean(str(exc)))
            raise
        finally:
            report.finished_at = datetime.now(timezone.utc)
