# Integrations (Dev-B): Persian calendar, Excel, IFS, e-mail, letters, automation

Packages: `backend/app/persian`, `integrations/{excel,ifs,email}`, `automation`, `documents`. They depend only on
`app.contracts` (plus each other) and never on Core. Factories: `app/integrations/factory.py`
(`build_calendar`, `build_excel_gateway`, `build_employee_source`, `build_email_sender`, `build_letter_renderer`,
names/signatures exactly as in `contracts.py`).

**pip requirements** (also in `backend/requirements-integrations.txt`): `openpyxl>=3.1`, `python-docx>=1.1`,
`httpx>=0.27`; mock IFS server: `fastapi`, `uvicorn`; tests: `pytest`, `pytest-cov`, `aiosmtpd`. SMTP uses the stdlib.
No jdatetime/hijri libraries, no docxtpl, no Outlook COM (intentionally unsupported).

Run tests: `cd backend && python -m pytest tests/integrations`.

## 1. Persian calendar (`app.persian`)
Port of the VBA Jalali library. 33-year-cycle arithmetic (Borkowski break table), valid for Jalali years -61..3177.
`PersianCalendar` implements `contracts.JalaliCalendar`: `to_jalali/to_gregorian`, `format(d, "short"|"words"|"weekday"|"long")`,
`add_days`, `number_to_words_fa` (1402 -> «یک هزار و چهارصد و دو»), `ordinal_words_fa` (9 -> «نهم»), Persian/Arabic/Latin digit
conversion, Saturday-first weekday names, `parse("۱۴۰۲/۰۳/۰۹")`. Example: `format(date(2023,5,30),"words")` = «نهم خرداد یک هزار و چهارصد و دو».
Verified: known dates (Nowruz 1399/1403/1404/1408, leap years 1399, 1403, 1408, 30 Esfand 1403 and 1408), and an exhaustive
day-by-day round trip and month-length consistency check for years 1300-1500.
Note: this is the arithmetic calendar, which matches the official (astronomical) calendar for all years 1178-1600 checked here
but is not guaranteed to for far-future years.

## 2. Excel (`integrations/excel`)
`OpenpyxlExcelGateway` (`ExcelGateway`) plus `*_report` variants returning a `SyncReport` (errors contain **row numbers and
column names only, never cell values**). `created` = rows parsed, `skipped` = rows dropped.
* `read_idp`: header row detected in the first 40 rows by column aliases (legacy layout has it on row 4 and 5; the repeated header
  row is skipped). Reporter `Name [ MTNIrancell - CR ]` -> `reporter_name` + `department` (the `Reporter Department` column wins when
  filled). Tickets normalised to `LMS-123456`, Section B to `MTC-123456` or `-`; dates accept datetimes, Excel serials, ISO strings,
  Persian/Arabic digits, Jalali years (<1700) and `Sunday-28-May-2023`; yeh/kaf variants normalised; duplicate (employee, ticket) rows skipped.
* `read_employees`: IFS sheet; restores leading zeros Excel drops from mobiles (`9xxxxxxxxx` -> `09xxxxxxxxx`) and national codes (10 digits); e-mails lower-cased.
* `read_legacy`: sheets `IFS`, `IDP`, `Record`, `CHistory` -> `LegacyData` (two-row headers handled). Lookup artefacts such as institute `0` become empty.
* `write_legacy`: writes the four sheets in the legacy column order (IDP header on rows 4-5, Record/CHistory on rows 3-4), atomically (temp file + rename), `.xlsx` only (a macro-free file must not carry `.xlsm`). `.xlsx` and `.xlsm` are both readable.
* Resource guards (`ExcelLimits`, constructor argument): compressed size, decompressed size (zip central directory inspected before anything is parsed), compression ratio, member count, unsafe member paths, `max_rows` (200,000), `max_cols`, `max_cell_chars` (over-long cells are truncated with a row error naming the column), optional `max_seconds` and a `should_cancel` callback (`ExcelReadAborted`). Formula cells are read as cached values (never evaluated); `.xlsm` macros are never loaded (`keep_vba` off). A row that raises is skipped with `row N: could not be parsed (ExcType)`; the read continues. `write_legacy` stores text that starts with `= + - @` as text cells (no live formulas).
* Never mutates or locks the source: the file is read once into memory and closed; `openpyxl` `read_only` streaming; wrong `<dimension>` metadata is repaired. Measured: 3,300 employees + 2,700 IDP rows read in about 1 s.
* `FolderWatcher` (polling, no inotify): reports a file only after its size+mtime were stable for `debounce_s`, it is a complete zip, and its SHA-256 differs from the last reported version (a mere touch does not re-import). Temp/lock files (`~$x.xlsx`, `.tmp`, `.part`, dotfiles) are ignored. `run(callback, stop_event)` loop provided.
* `ExcelEmployeeSource` / `ExcelIdpSource`: config `{"path"| "watch_dir", "sheet"?}`; `modified_since` compares the file mtime.

## 3. IFS connector (`integrations/ifs`)

> **Not tested against a real IFS tenant.** No IFS environment, credentials or network path existed. Everything below was verified only
> against the in-repo mock server (`ifs/mock_server.py`) and `httpx.MockTransport`. Endpoint paths, projection/entity names, field names,
> the OData filter syntax and the token/login flows of a real tenant must be checked by an administrator (checklist below).

Config (ConnectorConfig JSON): `base_url`, `auth_mode` (`oauth2_client_credentials|basic|session_login`), `client_id`, `client_secret`,
`token_url`, `scope`, `username`, `password`, `login_url`, `login_user_field`/`login_password_field` (default `username`/`password`),
`verify_tls` (default **true**), `allow_private_hosts` (default **false**, see below), `max_response_bytes`, `ca_bundle` (path to a private CA), `timeout_s` (30), `employees_path` (default `/PersonInfo`),
`page_size` (500), `max_retries` (4), `backoff_base_s`, `backoff_max_s`, `breaker_threshold` (5), `breaker_cooldown_s` (60),
`modified_field` (default `ModifiedDate`), `delta_mode` (`server` = `$filter=<modified_field> ge <ISO-Z>`, `client` = filter after download),
`active_statuses`, `field_map`.

* **Auth**: OAuth2 client-credentials (token cached, refreshed 30 s before expiry, one re-authentication + retry on 401); Basic; session login
  (form POST, cookie jar, transparent re-login on 401 or a redirect back to the login URL).
* **URL hygiene / SSRF** (`integrations/urlcheck.py`, IFS and Graph): only `http`/`https`; no credentials or secret-looking query parameters in any URL (`base_url`, `token_url`, `login_url`, next links); redirects are **never followed** (a 3xx is an error, so the `Authorization` header or session cookie cannot be forwarded to another host); API calls and next links must stay on `base_url`'s origin. By default (`allow_private_hosts: false`) a host that resolves to loopback, private (RFC 1918/ULA), link-local (including the 169.254.169.254 metadata address), multicast or reserved space is refused at configuration time and again on every request. **An on-prem IFS on a private network therefore needs `allow_private_hosts: true`, set deliberately by the administrator for that connector**; scheme, credential and redirect rules still apply then. Residual risks: DNS rebinding between check and connect, and unresolvable names are not rejected by the check; keep egress firewalling in place. SMTP host names are not URL-checked.
* **Streaming sync**: `fetch_employees(modified_since, *, max_records=None, should_cancel=None, on_progress=None)` is a generator (one page in memory); `max_records` stops early (`truncated=True`), `should_cancel()` is polled per record (`cancelled=True`), `on_progress(records, pages)` after each page; `fetch_employee_chunks(chunk_size)` yields lists so Core can commit per chunk. Response bodies are capped by `max_response_bytes` (default 64 MB, streamed), over-long field values (>300 chars) are truncated with a row error naming only the field, and a record that fails mapping is skipped with a row error instead of aborting.
* **Paging**: `@odata.nextLink` (refused if it points to another host, loop-guarded), `d.results/__next`, bare lists, or `$top/$skip`.
* **Resilience**: timeouts, exponential backoff with jitter on 429/500/502/503/504 and transport errors, `Retry-After` honoured (capped), circuit breaker (closed/open/half-open), TLS verification on.
* **Secrets**: never logged or put in exceptions (`redact.py`; bearer tokens and passwords are scrubbed, error text carries only the HTTP status, never response bodies). `base_url` may not embed credentials. Test `test_secrets_never_in_logs_or_errors` proves this for all three modes at DEBUG log level.
* `test_connection()` returns `(ok, sanitized message)`; `fetch_employees(modified_since)` yields `EmployeeRecord`; `last_report` lists skipped records without values.
* **Field map**: nothing tenant-specific is hard-coded. `field_map` maps each `EmployeeRecord` field to an ordered list of candidate JSON keys (dotted paths for nested objects, case-insensitive); the shipped default (`ifs/config.py: DEFAULT_FIELD_MAP`) is a documented guess for IFS Cloud OData `PersonInfo`/`CompanyPerson`-style shapes, e.g. `emp_no: ["EmpNo","PersonId","EmployeeId","CompanyPersonId"]`, `first_name_en: ["FirstName","Fname"]`, `email: ["Email","PrimaryEmail","EmailAddress"]`, `supervisor_emp_no: ["SupEmpNo","SupervisorId","ManagerId"]`, `status: ["EmployeeStatus","Status"]`. Override any entry: `"field_map": {"emp_no": "CompanyPersonId", "position_title": ["Position.Title"]}`. Unknown targets are rejected.

**Administrator checklist (must be configured/verified against the real tenant)**
1. `base_url` and TLS: certificate chain trusted (else set `ca_bundle`; do not disable `verify_tls`).
2. Auth mode and its endpoints: `token_url` (IFS IAM/Keycloak realm), client id/secret with read scope on the projection, `scope` if required; or the exact login form URL/field names and what a *expired* session returns (401 vs redirect).
3. `employees_path`: the projection/entity set that lists employees with supervisor, division, cost centre and status; verify with `$metadata`.
4. `field_map` against real JSON field names (run `test_connection`, then a small fetch and inspect `last_report.errors`).
5. `modified_field` really exists and supports `ge` filtering on that entity; otherwise use `delta_mode: "client"` (downloads everything) or omit delta.
6. Pagination style (`@odata.nextLink` vs `$skip`) and the tenant's server-side page-size cap; rate limits (429) and the service account's permissions.
7. Status vocabulary (`active_statuses`), gender vocabulary (Male/Female/M/F handled), and whether national code/mobile are exposed at all (personal data, needs approval).

**Mock server**: `python -m app.integrations.ifs.mock_server --port 8099` (or `MockIfsServer` in tests). Serves `/oauth/token`, `/login`, `/PersonInfo`;
credentials `mock-client/mock-client-secret`, `mock-user/mock-password` (synthetic). `POST /__control` sets `fail_429`, `fail_500`, `token_ttl`,
`session_ttl`, `use_next_link`, `expire_now`.

## 4. E-mail (`integrations/email`)
`SmtpSender` config: `host, port, username, password, starttls (default true), use_ssl, from_addr, from_name, timeout_s, verify_tls, ca_bundle, rate_limit_per_min`.
`GraphSender` config: `tenant_id, client_id, client_secret, sender` (+ `authority_url`, `graph_url` for a fake/sovereign cloud, `allow_private_hosts` default false; the same URL rules as IFS apply, redirects are not followed). App-only token, `POST /v1.0/users/{sender}/sendMail`, needs the *Mail.Send* application permission (admin consent) - **not verified against Microsoft Graph**.
Shared semantics: **one separate message per `To` recipient** (own Message-ID and `SendResult`; nobody sees anyone else's address; a refusal for one recipient does not affect the others; an explicit `cc` list is applied to each message and only when requested); one `SendResult` per recipient (To+Cc); `dry_run` validates only and sends nothing; header-injection protection (CR/LF/NUL in subject, addresses, names, attachment names -> rejected, value never echoed); address validation; `rate_limit_per_min` spacing; `idempotency_key` de-dupe per recipient (a retry after a partial failure only re-sends to recipients that failed). The store receives `sha256(key)` and a fingerprint of the FULL content (subject, to, cc, body, attachment digests): the same key with different content raises `IdempotencyConflict` (Core maps to 409); a live pending claim raises `IdempotencyInProgress` (also 409); a pending claim older than `pending_ttl_s` (300 s) is stale and can be retried; a failed send releases the key. Store: `InMemoryIdempotencyStore` or any object implementing `claim/complete` (Core can plug a DB-backed store, e.g. `MessageLog`); errors sanitized (no passwords/tokens, only SMTP/HTTP codes). HTML body is sent with a plain-text alternative. Graph `sendMail` returns no id, so `message_id` is a local `graph-<uuid>` correlation id.
Tested with an in-process `aiosmtpd` server (plain, AUTH, per-recipient refusal, and real STARTTLS with a throw-away certificate) and an in-process fake Graph (`httpx.MockTransport`). Not tested against a real corporate SMTP relay or Exchange Online.

## 5. Automation (`app/automation`)
`compute_due(facts, today, *, level3_after_days=60, reminder_days=2, over3_threshold=3)` is pure (dates only, no timezone, no clock). Boundaries:
level3 due on day N (`today - end_date >= N`; documented choice: the legacy sheet used `> 60`, so an enrollment ended exactly 60 days ago is due here on day 60 - Core must use the same `>=` or the shared function), status exactly "Evaluation Level 3", category contains "soft skill" (case/hyphen-insensitive substring, like Core and the legacy SEARCH), not already sent;
deadline reminder when `0 <= deadline - today <= reminder_days` and motivation still empty; over-3 per ticket (the same ticket on several enrollments), when the number of motivations that are not "Yes" is `>= threshold` (default 3, legacy `COUNTIFS(Record[Ticket]=t, Motivation<>"Yes")>=3`; one item per ticket);
payment-not-started once per run when the run started, the enrollment's motivation is "Yes" and no payment. `batch_by_manager(items, key, max_per_batch=9)`;
`split_invoice(total, n, places=0)` (Decimal, shares sum exactly; remainder to the first attendees) and `invoice_total(unit, motivations)`.

## 6. Letters (`app/documents`)
See `docs/TEMPLATES.md`. `DocxLetterRenderer(templates_dir)`: `render(kind, fields, lang)` -> `RenderedLetter` (docx bytes, e-mail HTML body, single-line subject, safe filename), `required_fields(kind, lang)`.

## 7. What was verified here vs not
Executed: full pytest suite (see final report for counts/coverage); all six letters rendered to .docx and converted to PDF with LibreOffice 24.2 (Writer installed for the check) and inspected visually; the e-mail HTML was string-checked only (no mail client/Outlook rendering was possible).
Not verified: real IFS, real SMTP relay, Microsoft Graph, Word/Outlook rendering (only LibreOffice), Persian shaping in Word with the Tahoma font (templates use Tahoma for portability; switch in `templates/build_templates.py` if the organisation uses another face).
