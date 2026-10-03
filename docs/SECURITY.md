# Security

## Assets and data classification
| Class | Data | Protection |
|---|---|---|
| Restricted | national code, mobile, date of birth; connector secrets (IFS/SMTP/Graph passwords, client secrets); letters (rendered body and .docx file: institute letters carry participants' IDs and phones) | AES-256-GCM at rest (column level), masked in every list/detail response, revealed only to hr/admin with an audit row; secrets are write-only |
| Confidential | names, work e-mail, division, cost centre, motivations | authenticated + RBAC; not encrypted at rest (needed for search/joins) |
| Internal | courses, runs, institutes, dashboards | authenticated read for all roles |
| Integrity-critical | `audit_log` | append-only (see below) |

## What is encrypted
`employees.national_code`, `employees.mobile`, `employees.date_of_birth`, `connector_configs.secrets` (JSON), `letters.html_body` (the rendered
e-mail body, which contains the participants table of an institute letter) and every letter **file** under `letters/` (AES-GCM blob `TMS1` + nonce +
ciphertext; download and e-mail attachment decrypt in memory; the file is never a readable .docx on disk). Format of columns: `v1.` + base64(nonce 12 B ||
ciphertext || tag), fresh nonce per write, the column/file context is bound as AAD (a value copied elsewhere fails authentication). Rows/files written before
this was introduced are still readable and are encrypted by `python -m app.security.rekey` (which also re-encrypts everything on key rotation).
National code and mobile are not searchable by design. **Not encrypted:** names, e-mail, everything else, and the database/volume itself
(use disk encryption at the host if your policy requires it). The preview endpoint returns the same personal data to the caller and is audited for PII kinds.

## Secrets handling
* No secret, key or default password is in the repo. `.env` is git-ignored; `.env.example` is empty of values.
* `TMS_DATA_KEY` (encryption) and `TMS_SECRET_KEY` (session pepper) come from the environment. Production refuses to start if they are missing/weak.
* Passwords: `hashlib.scrypt` (n=2^15, r=8, p=1, per-user salt, parameters stored in the hash). First admin comes from env only while no user exists.
* Sessions: 256-bit random token in an `HttpOnly; SameSite=Lax` (`Secure` in prod) cookie; only an HMAC of it is stored; logout revokes it.
* Logs, `SyncRun.errors`, `MessageLog.results` and error responses are scrubbed (e-mails, 10/11-digit ids, `password=`/`token` pairs, bearer tokens, URL credentials);
  request logs never contain the query string; unhandled exceptions log only class and file:line.
* Connector secrets decrypt only in memory when a sync/test/send runs and are handed to Dev-B's factory; they are never returned by the API (not even masked or as a length; only the *names* of fields that are set).

## Threat model (STRIDE, condensed)
| Threat | Mitigation | Residual |
|---|---|---|
| Credential stuffing / brute force | scrypt; lockout per username (5 fails/15 min, applies to unknown names too, uniform 401 message, dummy hash for timing); per-IP window (100 fails/15 min) keyed on the REAL client address (see Client address) | an attacker can lock a known account for 15 min by failing 5 logins (accepted; an admin can reset it by changing the password) |
| Session theft | HttpOnly, Secure, SameSite=Lax, server-side revocation, 12 h expiry, CSP `script-src 'self'` | XSS in a bundled dependency |
| CSRF | per-session token in `X-CSRF-Token` on POST/PUT/PATCH/DELETE (constant-time compare) + Origin check + SameSite=Lax | login form itself is not CSRF-token protected (Origin check applies) |
| Privilege escalation | RBAC `admin > hr > viewer` enforced by a dependency on every route; a test walks all routers and fails if a route lacks one or is missing from the role matrix | |
| PII exposure | masking by default; `?reveal=1` needs hr/admin and writes `employee.reveal`; letters/exports write audit rows | hr/admin can reveal by design |
| Tampering with history | audit log has no update/delete code path, an ORM guard, and DB triggers (SQLite and PostgreSQL incl. TRUNCATE) | a DB superuser can drop the triggers: protect with backups and separate DB roles |
| Double e-mail send | `idempotency_key` stored in `message_logs` (unique) and bound to a hash of the WHOLE request (recipients, cc, subject, letter/template+fields): same key + different content = 409; retry replays the stored result and only re-sends recipients that failed; a `pending` row older than `TMS_EMAIL_PENDING_TTL_S` (crashed worker) may be retried | a crash between SMTP acceptance and the DB update can duplicate one message (at-least-once); `POST /letters` has no idempotency key (a double click makes two numbered letters) |
| Letter number duplicates | atomic `UPDATE ... RETURNING` counter + UNIQUE(kind, seq); `tests/core` (threads) runs on SQLite and, in CI, on PostgreSQL | failed renders leave gaps, never duplicates |
| Malicious upload / zip bomb | `.xlsx` only, `PK` magic, 25 MiB compressed cap, and BEFORE parsing: required members, member count <= 2000, no path traversal, decompressed size <= 64 MiB and expansion ratio <= 120 (`TMS_MAX_XLSX_*`), row cap (`TMS_MAX_IMPORT_ROWS`), random temp name deleted afterwards; the parse itself runs in a background job (`TMS_SYNC_WAIT_S`) so it never holds the request | a compliant 64 MiB workbook still costs ~10 s of CPU in the job |
| SSRF via connector URL | admin-only, scheme limited to http/https | an admin can point IFS at an internal host; restrict egress at the network layer |
| Path traversal | download path is `letters/<id>_<sanitized name>` and must resolve inside the storage dir | |
| DoS | body-size limit (1 MiB JSON / 25 MiB uploads), page_size <= 200, single-flight sync lease | no global rate limit: add one at nginx |
| Clickjacking / sniffing | CSP `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` | |
| Cross-site API use | CORS closed unless `TMS_CORS_ORIGINS` lists origins (never `*`) | |

## Client address behind a proxy
`X-Forwarded-For` is honoured only when the TCP peer is inside `TMS_TRUSTED_PROXIES` (default loopback + `172.16.0.0/12`, the docker bridge range) and is read
from the right: the first hop that is not itself a trusted proxy is the client. Entries a client prepends are ignored, garbage falls back to the peer. Uvicorn runs
with `--no-proxy-headers`, so this is the only interpretation. The per-IP lockout and the audit IP therefore identify the real client, not the proxy. If the app is
reachable directly by untrusted hosts, none of them can influence the address.

## Password policy
Users and the bootstrap admin: >= 12 characters, >= 8 distinct, at least 3 of {lower, upper, digit, symbol}, no username, no common word (password, admin, welcome,
qwerty ...), no 6-long run (123456, abcdef), no 4 repeated characters. `Password123456` and `12345678901234` are rejected. Production refuses to start with a weak bootstrap password.

## User-written templates
Rich text is sanitised on the server at save AND at render: allow-list of tags (b i u strong em ul ol li p br a table thead tbody tr th td h2 h3 span) and attributes
(`dir`, `colspan/rowspan`, chip `data-field`, link `href` limited to http/https/mailto/tel); scripts, styles, iframes, svg, forms, event handlers, `style`, `javascript:`/`data:`
URLs and comments are removed. Field values are HTML-escaped and inserted in ONE pass over the template text, so a value can neither inject markup nor be expanded as a field
(`{{x}}` inside a name stays literal). Subjects are plain text with CR/LF stripped. System templates are read-only; every change is versioned and audited; a test e-mail goes only to the caller's own address.

## Manual edits vs imports
A person's edit wins: attendance, registration, calendar, payment, comment and motivation set through the API are recorded per enrollment (`manual_fields`) and are never
overwritten by an IDP/legacy import or an Excel sync. A blank incoming value never erases a stored one. `PATCH /enrollments/{id}` with `release_fields` hands a column back to the importer.
A ticket never changes owner through an import: the row is skipped and reported (`ticket_owner_conflict`).

## Roles
`viewer`: read dashboard, employees (masked), courses, runs, enrollments, letter list, automation due/settings.
`hr`: everything that changes training data, letters (create/preview/download), e-mail, messages, sync/import/export (the export leaves national code and mobile blank), connectors (read), automation run, reveal.
`admin`: plus the PII export (`GET /export/legacy.xlsx?include_pii=1`), users (create, role/active/password change; the last active admin cannot be disabled or demoted; password, role or deactivation revokes that user's sessions), audit log, connector write/test, automation settings.

## Audit
Actions recorded: login/logout/failed login (IP only), user create/update, letter preview of PII kinds, automation runs (with what was or would have been sent), course/run/enrollment writes, letter create/download, email send, connector update/test,
sync/import/export, automation run/settings, employee reveal. Details hold ids, counts and field names, never personal values.

## Known gaps
No MFA/SSO; a global request rate limiter is expected at the proxy;
the Dockerfile was not built in the development environment (no Docker daemon) -- CI builds it.
