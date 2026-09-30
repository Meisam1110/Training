# QA report - Training Management System (independent functional / security / integration QA)

Scope: `/home/user/training` working tree (uncommitted; HEAD = contracts only), tested 2026-09-30 by an agent that did not build it.
Method: every finding below was reproduced against the running app (uvicorn on scratch DBs under `/tmp/qa`, SQLite and PostgreSQL 16.13) or with a
pytest in `qa/tests/`. Findings I could not reproduce were dropped. No application source was edited. All data is synthetic
(`qa/synth.py`); the real legacy files were used only to build a ground-truth identifier list in `/tmp/qa/truth` (outside the repo, never printed).

## 1. Executive summary

**Verdict: DO NOT SHIP as-is. Ship-with-fixes once QA-B1 and QA-H1..H3 are fixed** (all four are small, well-localised fixes).

What is solid (verified): RBAC matrix (every OpenAPI operation x anonymous/viewer/hr/admin, no deviation from the documented matrix), CSRF on every unsafe route, cookie flags,
session fixation/logout/tamper, login lockout (XFF rotation does not bypass it, unknown users behave like known ones, no timing oracle),
SQL-injection sweep on every `q`/`sort`/filter (0 hits), PII and connector secrets encrypted at rest (0 of 90 revealed values and the SMTP
password found in raw DB bytes), audit log append-only via ORM/API/raw SQL (SQLite + PostgreSQL incl. TRUNCATE), no secret/PII in logs, audit rows,
sync/error messages, production start-up refusals (13 of 14 cases, exception QA-L2), migrations up/down/up + 0001-with-data on SQLite and PostgreSQL with no model drift,
key rotation, backup + restore, letter numbering under 30-way concurrency (SQLite and PG, all unique), scheduler with 2 workers (18 runs in
17 min, min gap 60.0 s, no duplicates), email idempotency for identical retries / partial failure / concurrency (8 parallel = 1 delivery),
header-injection, HTML escaping, Jalali conversion (0 mismatches over 200 years vs two independent libraries), clean-room build
(413 backend tests + ruff + 82 frontend tests + build pass from a copy with a fresh venv / `npm ci`).

What blocks: one of the six letters cannot be produced at all, the Level-3 workflow can never complete, and the connector configuration API cannot
express settings a real IFS/SMTP needs. A tester who trusts `tests/core/test_real_integrations.py` would not see any of it (see QA-M13).

| Severity | Count |
|---|---|
| Blocker | 1 |
| High | 4 |
| Medium | 16 |
| Low | 12 |

## 2. Findings (severity-ranked)

Owner: core = backend Core (Dev-A), integrations = Dev-B, frontend, deploy. Repro paths are relative to `/home/user/training`; helper scripts read `QA_DEMO_PW`
(`. qa/env.sh`) and expect the scratch servers started by `qa/mkserver.sh` (see `qa/run_all.sh`). Logs of each run are in `qa/logs/`.

### Blocker

**QA-B1 - settlement letter cannot be generated or e-mailed (core + integrations)**
- Repro: `pytest qa/tests -o addopts="" -k B1` or `. qa/env.sh; python qa/letters_e2e.py` (real factory, real templates). `POST /letters` and `/letters/preview`
  with `{"kind":"settlement_letter","run_id":N}` on a run with participants, amount and letterhead settings.
- Observed: 422 `fields: {start_date_greg, total, rows: "required"}` every time. Core (`api/services/letters.py::_run_plan`) builds `start_date_gregorian`,
  `invoice_total`, `attendees`; the real renderer's `required_fields()` (`documents/specs.py`) demands `start_date_greg`, `total`, `rows`, and Core's own
  `check_required` compares against `required_fields`. CONTRACT_REQUESTS says the old names are "still accepted" - only by `render()`, not by `required_fields()`.
- Expected: 201 with a numbered letter; invoice = amount x motivations, split across attendees.
- Impact: the invoice/settlement step of the workflow (one of the six documents) is unusable; the other five kinds render (verified, incl. PDF conversion).
- Fix: emit the renderer's names (`total`, `start_date_greg`, `rows` with `staff_id/description/division_cost_center`) or make `required_fields` alias-aware; add a test that uses the real factory.
- Also found while testing: the per-attendee value printed is `shares[0]` (largest share). For totals not divisible by the attendee count the printed
  `per_attendee x n != total` (e.g. total 100, 3 attendees -> 34 each). Print the exact share per row (the renderer has an optional `amount` row field) or state rounding.

### High

**QA-H1 - Level-3 loop never closes (core)**
- Repro: `python qa/level3_loop.py` (imp server) or `pytest qa/tests -k level3_loop`.
- Observed: `Enrollment.level3_sent` / `level3_status` are read by the due, dashboard, candidate and workflow logic and written nowhere (no endpoint accepts them: PATCH -> 422; letter creation and successful
  e-mail do not set them). After creating and e-mailing the Level-3 request the enrollment is still in `/automation/due`, on the dashboard, and flagged
  `level3_eligible` in candidate search forever; `workflow.level3_started` can never become true.
- Expected: sending the letter marks the enrollment (or an explicit PATCH does), and it leaves the due list.
- Impact: HR re-notifies the same people every day; the dashboard list only grows.
- Fix: set `level3_sent=True` (and `level3_status`) when a `level3_request` letter is sent (state=`sent`); allow `level3_status/level3_sent` in `EnrollmentPatch`.

**QA-H2 - default `FORWARDED_ALLOW_IPS=127.0.0.1` makes every user share one IP behind the compose/docker proxy (deploy)**
- Repro: `python qa/proxy_ip_lockout.py` (source address 127.0.0.2 stands in for the docker bridge gateway; real docker not available). 35 failed logins with
  different usernames and different `X-Forwarded-For` -> 30x401 then 429; a valid login of another user from the same proxy address -> 429 for 15 min. Audit IP = proxy address.
- Observed/expected: uvicorn only trusts XFF from `FORWARDED_ALLOW_IPS`; `.env.example` and DEPLOYMENT.md default it to `127.0.0.1`, but with compose (`ports: 127.0.0.1:8000:8000`,
  nginx on the host) the app sees the bridge gateway address. Real client IPs are never seen, the per-IP limit (30/15 min) is shared by all users, and audit IPs are useless.
- Impact: one anonymous attacker locks out every login with 30 requests; forensic IPs wrong.
- Fix: document/set `FORWARDED_ALLOW_IPS` to the docker gateway/subnet (or `*` when the port is only bound to loopback), add a deployment check that logs the observed peer, and consider making the per-IP limit much higher than the per-username one.
  (I could not build/run docker: this is reproduced by simulation plus static analysis of compose/Dockerfile.)

**QA-H3 - connector API cannot express settings a real IFS / SMTP needs (core)**
- Repro: `python qa/ifs_e2e.py` (last block): `PUT /connectors/ifs` with `employees_path`, `page_size`, `modified_field`, `scope`, `ca_bundle` -> 422 "unknown keys";
  `PUT /connectors/smtp` with `use_ssl`, `verify_tls`, `ca_bundle`, `timeout_s`, `rate_limit_per_min` -> 422. `max_retries` likewise.
- Observed: `ALLOWED_KEYS_BY_KIND` (`api/services/serializers.py`) is narrower than what Dev-B's `IfsConfig` / `SmtpSender` read. The entity-set path is therefore fixed at
  `<base_url>/PersonInfo` (ARCHITECTURE and INTEGRATIONS say it is configurable), delta filter field is fixed to `ModifiedDate`, implicit-TLS SMTP (port 465) and internal-CA
  servers cannot be configured (self-signed test -> `IFS request failed (ConnectError)` with no way to pass a CA bundle or a hint that TLS verification failed).
- Impact: the real IFS tenant / mail server most probably cannot be connected without editing the DB by hand.
- Fix: derive the allow-list from the config dataclasses; surface a sanitized TLS hint in `last_test_message`.

**QA-H4 - zip-bomb / oversized workbook exhausts CPU and memory (integrations + core)**
- Repro: `python qa/upload_attacks.py` (scratch server on 18701; needs `qa/synth.py`). A 1.0 MiB .xlsx whose sheet XML expands to 300 MB: request ran 62.8 s (client timed out at 60 s),
  worker RSS 98 -> 480 MB and still growing; 50 MB expansion = 10.6 s. Cost is linear, the cap is only on the compressed size (25 MiB), so a 25 MiB file expands to GBs.
- Related (same root, `list(src.fetch_employees())` + one transaction): a 60,000-record IFS page (`qa/faulty_ifs.py` port 18115, `qa/ifs_faults.py`) ran > 16 min in one HTTP request and grew the worker
  to 2.8 GB RSS without finishing; after `kill -9` the SyncRun stayed `running` and new syncs get 409 until the 15-min lease expires. Container limit is 1 GB (compose) / `MemoryMax=1G` (systemd), so both workers die.
- Expected: reject before parsing (inspect zip central directory: uncompressed size / ratio, member count), stream/batch the sync (commit per page), cap records.
- Verified OK: XXE (external entity -> rejected, nothing read), billion-laughs (not expanded), macro (vbaProject.bin ignored), truncated / PK-only / text-as-xlsx files rejected, filename traversal irrelevant (random temp name).

### Medium

**QA-M1 - out-of-range integer ids and NUL bytes give HTTP 500 (core)** - `python qa/probe_overflow.py`: `GET /runs/99999999999999999999` and 14 more routes (`/courses/{id}`, `PATCH /enrollments/{id}`, `?run_id=`, bulk, letters, email, ...) -> 500 `OverflowError`
(SQLite) / `DataError` (PG). `python qa/pg_specific.py`: `POST /courses {"name":"a\u0000b"}` -> 500 on PostgreSQL. Fix: `Path(ge=1, le=2**31-1)` / `Query(le=...)`, strip or reject NUL in `Strict`.

**QA-M2 - re-import silently overwrites manual edits (core)** - `python qa/manual_edit_sync.py`: PATCH `attendance=Attended, registration=Yes, comment="manual note"`, then re-import the legacy workbook -> all three reverted, `updated: 2`; `POST /import/idp` reverts `attendance`.
By code reading the connector-driven Excel sync (`connectors.excel.idp_path`) uses the same `upsert_idp`, so it reverts attendance on every run (not separately exercised). Fix: treat blank incoming values as "no information" for user-owned columns (like `upsert_employees` does), keep manual columns out of the IDP upsert, or track which fields were edited.

**QA-M3 - IDP import moves a ticket to another employee without an error; legacy import not idempotent with duplicate tickets (core)** - `python qa/imp_test.py`: two rows with the same `LMS-` key for different employees -> the
enrollment ends up owned by the last one, no error row, and re-importing the identical file reports `updated: 2` (owner flips back and forth). `pytest qa/tests -k silently_move`. Fix: on `employee_id` change, record an error row and keep the existing owner (or require an explicit flag).

**QA-M4 - one over-long value aborts the whole import/sync on PostgreSQL (core)** - `python qa/pg_specific.py`: legacy workbook with a 300-char name -> 502 "sync failed", nothing imported (SQLite accepts it silently: dev/prod divergence). Employee fields
(`first_name_en` 100, `cost_center` 64, `email` 200, ...) are not truncated/validated like enrollments are. Fix: validate/truncate per column with a row error; run the test-suite on PostgreSQL in CI.

**QA-M5 - `{{...}}` inside data values is interpreted as a template (integrations)** - `python qa/tests/template_injection_probe.py`, `python qa/letters_edge.py`, `pytest qa/tests -k placeholder_in_data`: a participant name / course name / IDP summary containing `{{x}}` makes
the letter fail (`unresolved placeholders after rendering`, 502) for the whole batch, and `{{Letter_No}}` typed into a participant name is substituted with the letter number (a second pass over inserted text). The source of such text is IFS/iCare free text.
Impact: any employee (iCare summary / name) can block letter generation for a run; limited cross-field disclosure inside the same letter. Fix: single-pass substitution over the template text only, or neutralise `{{`/`}}` in values.
HTML e-mail body is correctly escaped (verified with `<b>`, `<script>`, `&`, quotes).

**QA-M6 - spreadsheet formula injection in `/export/legacy.xlsx` (core)** - `python qa/export_inject.py`: a course/institute/days/time value starting with `=`, `+`, `-`, `@` is written as a live formula (`HYPERLINK`, arithmetic) into `CHistory`/`Record`. Values reach the DB from iCare summaries. Fix: prefix `'` (or set `data_type='s'`) for such strings in `write_legacy`.

**QA-M7 - e-mail idempotency and duplicate-action gaps (core)** - `python qa/email_e2e.py`, `python qa/email_pending.py`:
(a) same `idempotency_key` with a different `subject`, `cc`, or template `fields` returns 200 `replayed:true` (only recipients and letter_id are compared) - the new message is silently never sent; `pytest qa/tests -k idempotency_key_reuse`;
(b) a `pending` row left by a crash blocks its key forever (409, verified with a 3-day-old row) - no expiry/recovery; (c) no key -> auto key -> two POSTs send two mails (documented?); (d) `POST /letters` has no idempotency: a double click creates two letters and burns two numbers.
Verified OK: identical retry replays (1 delivery), partial failure retry only re-sends the failed recipient (2 ok + 1 refused, then 1 more attempt only for the refused), 8 parallel same-key POSTs = 1 delivery + 7x409, connection drop -> `failed` with sanitized error, dry-run sends nothing.

**QA-M8 - credentials accepted inside connector URLs are stored in plaintext and returned (core)** - `PUT /connectors/ifs {"base_url":"http://user:PW@host","token_url":"http://h/oauth?apikey=K"}` -> 200; `GET /connectors` (hr) returns them; the raw SQLite file contains them (public JSON is not encrypted).
Fix: reject userinfo/query in URL fields on PUT (Dev-B's `IfsConfig` already refuses at use time). `pytest qa/tests -k embedded_credentials`.

**QA-M9 - plaintext national IDs / mobiles in `letters.html_body` (core)** - `python qa/db_inspect.py` after `python qa/letters_e2e.py`: 14 of 90 revealed values are present in the raw DB bytes (the institute-letter e-mail body with the participants table is stored in `letters.html_body`).
Contradicts SECURITY.md/DEPLOYMENT.md ("a restored DB is unreadable without the key"); `POST /letters/preview` (hr) returns the same PII and is not audited. Fix: do not persist the HTML (re-render on send) or encrypt the column; audit preview of PII kinds.

**QA-M10 - Level-3 rule differs between engines (integrations vs core)** - `pytest qa/tests -k boundary`: `automation/rules.py::compute_due` uses `today >= end + 60` and category `== "soft skill"`; Core (`rules.level3_eligible`, dashboard, candidates) uses `> 60` and substring match (legacy: `today-end>60d`).
An enrollment ended exactly 60 days ago is "due" in `/automation/due` and the scheduler but absent from the dashboard. Fix: one shared function.

**QA-M11 - performance / memory (core)** (SQLite, 5,000 employees, 12,240 IDP rows, 300 runs, 2 workers, 4 shared vCPU: `qa/build_load.py`, `qa/load_test.py`, `qa/nplus1.py`):
5 clients: p50 81 ms, p95 1.46 s, 0 errors; 50 clients: 259 requests in 25 s, p95 42.9 s, 6 read timeouts. Slow endpoints: `POST /runs/{id}/candidates:search` 377 SQL statements for one call, 425 KB unpaged response (p50 16.6 s @50 clients);
`GET /automation/due` unpaged 154 KB (p50 12 s); `GET /dashboard` p50 9.5 s; `/runs/{id}/enrollments?page_size=200` = 75 statements (N+1 supervisor look-ups); `/enrollments?q=` 28. Steady RSS 745 MB for two workers vs the 1 GB container limit. Page size cap (200) verified.
Fix: batch supervisor e-mail lookups, paginate/cap candidates and due lists, do the course-name filter in SQL (it currently loads every unassigned enrollment into Python), test on PostgreSQL.

**QA-M12 - bulk PII export is one click and one audit row (core)** - `GET /export/legacy.xlsx` (hr) writes decrypted national code and mobile of every employee; one `export.legacy` audit row. Masking/reveal is per employee elsewhere. Consider admin-only or an explicit confirmation + count in the audit detail (count exists: `employees`).

**QA-M13 - test suite gives false assurance (core)** - `tests/core/test_real_integrations.py::test_all_six_letter_kinds_render_with_the_real_renderer` builds its app through fixtures `seed -> app -> factory`, where `factory` monkeypatches `gateway.get_factory` and `compute_due` with `tests/core/fakes.py`;
it never touches the real renderer, which is why QA-B1 passes CI. Also: no PostgreSQL test job (CI only runs migrations there; QA-M4/M1 are PG-only), CI frontend job skips `npm test`, `test_smtp_bad_password_sanitized` takes 60 s (network timeout dependent), SECURITY.md cites "8 threads on PostgreSQL" numbering test that exists only for SQLite (I ran it on PG manually: 30/30 unique).

**QA-M14 - no scheduled sync / watcher wiring; scheduler only counts (core + integrations)** - `python qa/watcher_test.py`: `FolderWatcher` works as a library (partial write, atomic replace, lock files, touch-without-change handled) but is referenced nowhere in `app/` (no `EXCEL_WATCH_DIR`); IFS and Excel sync run only on `POST /sync/{source}:run`; the daily automation job computes and stores counts, it sends no reminders or e-mails (ARCHITECTURE section 5.1/5.5).
Decide: wire it or remove the claims. (Scheduler correctness itself verified: no duplicate runs with 2 workers.)

**QA-M15 - letters cannot be produced for employees with empty gender or no supervisor, and there is no way to fix the data (core)** - `python qa/letters_edge.py`: `level3_request` -> 422 `Ftitle/En_title required` (gender empty); `level3_manager_check`/`line_manager_approval` -> 422 for missing supervisor, and `Title required` when the supervisor is not in IFS. There is no `PATCH /employees` or `extra` override for these kinds; messages name internal template fields.
Fix: allow per-request overrides or a neutral fallback ("Dear colleague"), and list which enrollments were skipped.

**QA-M16 - date-overlap rule counts un-assigned IDP requests as clashes (core, needs product decision)** - `POST /enrollments:bulk` assigning an enrollment to a run failed with `conflict` for an employee who merely had another *unassigned* IDP request with overlapping iCare dates
(`qa/letters_edge.py`, `pytest` helper had to move the run to 2027). Legacy compared against booked courses. Decide and document.

### Low

- **QA-L1** `Server: uvicorn` header sent; `TMS_TRUSTED_HOSTS` is parsed into `Settings.trusted_hosts` but never applied (no TrustedHost middleware) (Host header not validated; `curl -H 'Host: evil.example'` -> 200) - owner core.
- **QA-L2** Password policy weak: `12345678901234` and `Password123456` accepted (bootstrap and users); SPA says min 8 characters (`Admin.tsx`, mock) while the server needs 12 - owner core/frontend.
- **QA-L3** Per-username lockout lets an anonymous attacker lock any known account (incl. the only admin) for 15 min by repeating 5 bad logins (`qa/sec_login.py`); accepted trade-off, no admin bypass documented - core.
- **QA-L4** Malformed uploads (PK-only, truncated zip) return 502 `upstream` instead of 422 (`qa/upload_attacks.py`); subject with CR/LF returns 200 with status `failed` (should be 422); `"x"@b.co` and `a@[127.0.0.1]` pass API validation and fail in the sender - core/integrations.
- **QA-L5** Rendering (LibreOffice -> PDF, `qa/letters_e2e.py`): in the English section of `course_announcement` a Persian day list followed by `10:00-16:00` shows as `16:00-10:00 | ...` (no bidi isolation outside the `|fa` filter; Word not available to confirm); institute-letter table mixes Latin digits (ID/phone) with Persian digits in text and wraps an e-mail address mid-word; 90-character unbroken names wrap by character (acceptable). Frontend `sanitize()` is a small deny-list used with `dangerouslySetInnerHTML` (input is server-escaped and CSP blocks inline script; prefer DOMPurify) - integrations/frontend.
- **QA-L6** `pg_restore --clean --no-owner` (DEPLOYMENT section 7) into an empty DB prints 110 "does not exist" errors and exits 1 (data restored correctly, triggers intact); use `--if-exists`. `backup.sh` puts the PG password in the `pg_dump` argv - deploy.
- **QA-L7** Privacy hygiene: 2 distinct identifiers that also occur in the real workbook (one `LMS-` ticket key, one `MTC-` Section-B number) appear in 3 source files (`app/integrations/excel/normalize.py` docstring, `tests/integrations/test_excel.py`, `tests/integrations/synth.py`) - replace with obviously fake values; 8 Persian two-token full names in the UI-QA agent's `qa/uiux/sweep-results.json` and `frontend/qa-rerun/out/sweep-results.json` coincide with names in the real workbook; they are composed from the frontend mock seed's common first/last-name lists (checked: both halves come from `mock/seed.ts`) - coincidence, not leakage, but worth a glance by the frontend owner. Real e-mails, mobiles, national IDs and employee numbers: 0 hits in all 1,144 text/zip members scanned (`qa/logs/privacy_scan.txt`); generated demo letters exist under `backend/data/letters/` (git-ignored, synthetic). `.gitignore` does not cover `templates/letter_defaults.json` (company economic code / national ID), `*.dump`, `*.sqlite`, `qa/logs/`; `frontend/screenshots` (6.8 MB, synthetic) is not ignored.
- **QA-L8** Dependency scan: `pip-audit` on the clean venv: no application dependency affected (only venv `pip`/`setuptools`); `npm audit`: 0 production vulnerabilities, 5 dev-tool advisories (vitest UI critical, vite high, esbuild/vite-node/@vitest/mocker moderate) - dev server only, not shipped.
- **QA-L9** Dev-mode defaults: `TMS_ENV` unset = development (OpenAPI docs exposed, non-Secure cookie, generated dev key file) even with a PostgreSQL URL; refuse or warn loudly when `DATABASE_URL` is not SQLite and env is development - core/deploy.
- **QA-L10** All recipients of one e-mail are placed in a single `To:` header (each participant sees the others' addresses; `qa/email_e2e.py` shows `To: a1@..., a2@...`); use per-recipient sends or Bcc - integrations.
- **QA-L11** SPA `index.html` has no `Cache-Control` (stale UI after upgrade); CSP keeps `style-src 'unsafe-inline'` - deploy/frontend.
- **QA-L12** Login-adjacent details: SyncRun rows stay `running` after a crash (QA-H4); `TMS_AUTO_MIGRATE` documented "dev only" but not blocked in production - core.

## 3. Static review of Docker / compose / nginx / systemd / backup / CI (docker daemon unavailable)

`hadolint` could not be installed (not on PyPI/apt in this sandbox); `shellcheck` (via `shellcheck-py`) reports nothing for `deploy/backup.sh`. `docker compose config` was not run.
Checked by reading and by reproducing the equivalent locally: `COPY backend/pyproject.toml + backend/app` then `pip wheel ".[postgres]"` (setuptools `packages.find include=app*` is consistent);
runtime `pip install --no-index --find-links=/wheels` then `COPY backend/app ./app` shadows the installed package (cwd wins; `alembic.ini` `script_location = alembic` resolves from `/app`); templates copied to `/app/templates` and `/ready` checks them; `.dockerignore`
excludes `.env*`, `*.db`, `node_modules`, `frontend/dist`, `backend/data`; non-root uid 10001, `/data` volume owned by it, read-only rootfs + tmpfs `/tmp` (the app writes only under `/data`), healthcheck uses `/health`, DB port not published, `TMS_BIND=127.0.0.1`.
What a real build could still break: (1) QA-H2 (proxy address); (2) memory: measured 745 MB for two workers before any spike versus `limits.memory: 1g` (QA-H4/M11) - OOM kills both workers; (3) `COPY frontend/` sends `frontend/screenshots` (6.8 MB) and a stale `tsconfig.tsbuildinfo` into the build (add both to `.dockerignore`; `tsc -b` may treat stale info as up to date);
(4) Python 3.12 / node 20 images were not exercised (I ran 3.11 / node 22; CI matrix covers 3.12 and node 20); (5) nginx sample uses `listen 443 ssl http2` (deprecated warning on nginx >= 1.25) and `proxy_read_timeout 120s` while a large sync can run for minutes (504 while the work continues); (6) systemd `MemoryMax=1G` same as (2);
(7) the `migrate` one-shot needs `.env` complete but does not validate keys (fine) - the `app` service refuses to start with weak keys (verified with the production matrix in `qa/prod_config.py`, 13/14 as expected; the exception: bootstrap password `Password123456` accepted, QA-L2).
CI (`.github/workflows/ci.yml`): backend matrix 3.11/3.12 with coverage gate 85 (measured 97 %), PG job runs only migrations, frontend job builds but does not test, docker job builds without pushing and validates compose.

## 4. Documentation truth spot-check
- DEPLOYMENT env table vs code: all listed variables exist; `TMS_TRUSTED_HOSTS` exists in code but is undocumented and inert (QA-L1); `TMS_DEMO_PASSWORD` (demo) undocumented; `TMS_DATABASE_URL` alias undocumented. `.env.example` variables all consumed (`TMS_PORT/TMS_BIND` only by compose).
- Key rotation (`python -m app.security.rekey`, section 8) verified end to end: dry run 232 values, real run, second run idempotent (0 rekeyed / 232 current), old key rejected afterwards, connector secrets readable with the new key.
- Backup (SQLite fallback without the `sqlite3` binary and PostgreSQL) and restore verified (60 employees / 65 audit rows restored, audit triggers restored and still block DELETE); see QA-L6 for the `--clean` exit code.
- "First admin only while the users table is empty", "no default password": verified (production start with missing bootstrap password creates no admin and starts).
- SECURITY.md claims verified true: encryption at rest for the four columns, secrets write-only, letters hr-only (viewer -> 403 on download, download audited), audit append-only, CSP/headers, CORS closed (evil origin gets no ACAO), body limits (2 MB JSON -> 413, 26 MB upload -> 413; a chunked 30 MB multipart without Content-Length returned 400, not 413), scrubbing.
  Claims not true or not covered: "letters ... on disk contain the same personal data as the DB" is understated (QA-M9); "8 threads on PostgreSQL" test (QA-M13); ARCHITECTURE section 5 items on watcher/scheduled reminders (QA-M14); INTEGRATIONS "configured (ifs.field_map)" is true only for `field_map`, not for `employees_path` (QA-H3).
- No README at repo root; the Makefile targets work (`make test lint` in the clean copy: 413 passed in 118 s, ruff clean).

## 5. Business logic vs legacy workbook (docs/ANALYSIS.md)
Verified correct: candidate search (course substring, attendance "-", unassigned only, excluded reasons), over-motivation flag at >= threshold (default 3) per ticket, non-active and division-change flags, line-manager batching (10 enrollments -> 5 letters by manager, max 9 per letter),
level-3 strict `> 60` days with soft-skill category in Core (see QA-M10 for the other engine), invoice split sums exactly (`rules.invoice_split`; letter display caveat in QA-B1), letter number allocation, Jalali dates on letters (1405/07/03 = 2026-09-25, Esfand 30 of 1399 and 1403 valid, 1404/12/30 rejected, year rollover 2026-12-31 = 1405/10/10; legacy 1499->1399 hack absent),
Persian digits / Arabic yeh-kaf / ZWNJ / blank rows / Terminate rows / unknown-employee tickets on import (unknown employee becomes a stub employee with status `Unknown`; `qa/imp_test.py`), long names through letters, HTML in names rendered as text.
Not correct: see QA-M3 (duplicate tickets), QA-M10, QA-M15, QA-M16. Persian-digit search terms (`q=۹۱۰۰۰۰۱`) are not normalised (0 hits) - Low.

## 6. Test-coverage matrix
| Area | Tested | Notes |
|---|---|---|
| Clean-room build | yes | copy w/o `.venv`/`node_modules`/`__pycache__`/screenshots; fresh venv, `pip install -e backend[dev,postgres]`, 413 tests pass (118 s), ruff clean; `npm ci`, build, 82 tests pass; nothing depended on pre-existing local state (dev key is generated) |
| RBAC / CSRF / authn | yes, every OpenAPI operation x anon/viewer/hr/admin (`qa/rbac_matrix.py`) | |
| Injection / traversal / uploads / XXE | yes | see QA-H4, QA-M1 |
| SSRF | partly | admin-only by design; redirects not followed, next-link cross-host refused (code + redirect test); internal/link-local targets (127.0.0.1, 169.254.169.254) are accepted as documented (admin-only, restrict egress at the network); `file://`, `ftp://`, `gopher://`, `//host` -> 422 |
| Migrations | yes, SQLite and PostgreSQL 16.13 (temporary cluster on 55432) | `qa/migrations_test.py`; only informational drift: `server_default` on two 0003 columns |
| Excel/IDP import, export | yes, synthetic workbook generator | |
| IFS (mock, 3 auth modes, expiry, 429, 500, 401, malformed, slow, TLS, redirect, huge) | yes with the in-repo mock and a fault server | real IFS not tested; field map/paths unverified against a tenant |
| SMTP | yes with aiosmtpd sink (attachment, partial refusal, drop, slow) | real SMTP/STARTTLS servers and MS Graph not tested (no credentials/network); Outlook/Word rendering not tested (LibreOffice only) |
| Letters | all 6 kinds x docx/PDF/PNG inspected (5 render; settlement blocked) | Word/Outlook not available |
| Concurrency / load | yes (SQLite; numbering also on PG) | no full 50-client run on PostgreSQL |
| Privacy scan | yes, text + docx/xlsx internals + template images + screenshots by viewing | counts in QA-L7; `qa/logs/privacy_scan.txt` |
| Docker build, compose, TLS/nginx | no (no daemon) | static review only, section 3 |
| Backup/restore, key rotation | yes | |
| Frontend UI | not in scope (another agent) | |

## 7. Reproduction index
`qa/run_all.sh` lists every script in order; `qa/mkserver.sh NAME PORT [--demo N]` builds scratch servers; helper servers: `qa/smtp_sink.py`, `qa/faulty_ifs.py`, in-repo mock IFS; `pytest qa/tests -o addopts="" -p no:cacheprovider`
runs the reproduced findings as tests (11 tests: 10 currently fail = findings B1, H1, M10, M1, M7, M6, M3, M5, M8, M2; 1 passes). Ports used: 18700-18705, 18025, 18099, 18110-18115, PostgreSQL 55432. Nothing in `qa/` contains real data.

## Developer response (integrations)

Owner Dev-B. Tests: `cd backend && python -m pytest tests/integrations -q` (all green, ruff clean); regression tests for every row live in `tests/integrations/test_round3.py` unless noted. `qa/tests` (11) also pass here with Core's current code. Not verifiable here: real IFS / SMTP relay / Microsoft Graph, Word and Outlook rendering.

| Finding | Status | How / test |
|---|---|---|
| QA-B1 settlement letter (integrations half) | **Fixed** | Canonical names are now Core's real payload (`start_date_gregorian`, `invoice_total`, `attendees[].label`); the other spelling (`start_date_greg`, `total`, `rows`, `description`) is normalised before validation, so BOTH work. `required_fields()` omits aliased fields so Core's `k not in fields` pre-check passes with either spelling (render() still names anything missing). `supplier_code` optional (`-`). Tests `test_b1_*` call the real factory with the exact dict `_run_plan` builds and Core's own `check_required`. Each row now prints its exact share (`Amount` column; 100/3 -> 34/33/33, sums to total); `per_attendee` labelled "base share". Rendered to PDF and inspected. |
| QA-B1 "sixth letter QA could not render" | **Found + fixed** | It was `settlement_letter` (blocked only by the name mismatch above); it now renders like the other five (docx + PDF via LibreOffice inspected). |
| QA-M5 `{{...}}` in data | **Fixed** | Single-pass substitution: data braces are shielded during rendering and restored at the end, so `{{x}}`, `{{Letter_No}}`, `{%`, `${` in any scalar or list value stay literal, never fail the batch and never pull other fields. NUL/C0/C1/surrogates stripped. HTML stays escaped. Tests `test_m5_*` (10 hostile values x institute letter, all kinds, control chars); `qa/tests/template_injection_probe.py` output clean. |
| QA-M6 formula injection in export | **Fixed** (my `write_legacy`) | Strings starting `= + - @` are written as text cells. `test_write_legacy_neutralises_formula_injection`; QA's `test_QA_M_export_neutralises_spreadsheet_formulas` passes. |
| QA-M10 Level-3 rule | **Fixed / documented** | Kept `today - end >= level3_after_days` (documented in INTEGRATIONS.md; the legacy `> 60` differs by one day, Core must use the same function or `>=`). The only other difference (category `==` vs substring) is removed: substring `"soft skill"`. Test `test_level3_rule_is_ge_60_and_substring_category`. |
| QA-H4 zip bomb / oversize (integrations half) | **Fixed** | `ExcelLimits`: compressed size, decompressed size and ratio from the zip central directory before parsing, member count, unsafe paths, row/column/cell caps, time budget + cancel callback, formulas read as values, macros never loaded, per-row error capture. Tests `test_zip_bomb_guard`, `test_row_cap_*`, `test_cancel_and_time_budget`, `test_formulas_*`, `test_one_bad_row_*`. Core must still cap upload size and commit per chunk (below). |
| QA-H4 IFS sync memory / no cancel | **Fixed (connector side)** | `fetch_employees` is a lazy generator with `max_records`, `should_cancel`, `on_progress`; `fetch_employee_chunks(n)` for per-chunk commits; `max_response_bytes`; record-level error capture; over-long values truncated with a field-name-only error. Test `test_fetch_is_lazy_generator_*`, `test_ifs_overlong_*`. **Not fixed here:** Core's `list(...)` + single transaction and stale `running` SyncRun are Core code (Dev-A). |
| QA-M4 over-long value aborts import (Excel/IFS side) | **Fixed for readers** | Excel cells > `max_cell_chars` and IFS fields > 300 chars are truncated with a row error; per-column DB limits remain Core's. |
| QA-M7 idempotency (library side) | **Fixed in the integrations store** | Key stored hashed; fingerprint of the full content; same key + different subject/cc/body/attachments/recipients -> `IdempotencyConflict`; live pending -> `IdempotencyInProgress` (both for Core to map to 409); stale pending expires after `pending_ttl_s` and can be retried; failure releases the key. Tests `test_idempotency_conflict_*`, `test_pending_claim_*`, `test_failed_send_*`. Core's own `MessageLog` logic (its 200 `replayed:true`) is Core's to fix. |
| QA-M8 credentials in connector URLs | **Fixed at use time + validation helper** | `IfsConfig`/`GraphSender` reject userinfo and secret-looking query parameters in every URL (also `token_url`, `login_url`); `check_url` is available for Core's PUT validation. Storing/returning them in the config API is Core. |
| SSRF / URL hygiene (matrix "partly") | **Fixed** | `urlcheck.py`: http(s) only, no credentials, redirects never followed (no `Authorization` forwarded), same-origin API calls and next links, private/loopback/link-local/metadata targets refused unless `allow_private_hosts: true` (default false; required for on-prem IFS on a private network - documented). Tests `test_urlcheck_*`, `test_ifs_*`, `test_graph_*`. Residual: DNS rebinding TOCTOU; SMTP host not URL-checked. |
| QA-L4 addresses `"x"@b.co`, `a@[127.0.0.1]` | **Fixed (sender side)** | Sender rejects them with a per-recipient error (no send); API-level 422 is Core. |
| QA-L5 bidi of time range in the English section; e-mail wraps mid-word | **Fixed** | Persian day names are isolated (`|iso`) and the time range is LTR-isolated in the English section (docx and HTML); participants table gives the e-mail column 43% width. Test `test_l5_*`; LibreOffice PDF inspected. Word not available. |
| QA-L7 real-looking identifiers | **Fixed** | Remaining real `LMS-`/`MTC-` numbers in `normalize.py`, `test_excel.py`, `synth.py` replaced by fake values (`LMS-900002`, `MTC-900001`, ...); repo grep of my paths for the identifiers I know is clean. I cannot see QA's ground-truth list, so QA should re-run `qa/privacy_scan.py`. |
| QA-L10 all recipients in one `To:` | **Fixed** | Both senders send one message per recipient (own Message-ID and result; refusal isolated; explicit `cc` applied to each message; idempotency per recipient). Tests `test_each_recipient_gets_own_message_*` (aiosmtpd: each raw message contains only its own address), `test_refusal_of_one_recipient_*`, Graph payload test. |
| QA-M14 watcher not wired / scheduler only counts | **Not fixed (Core wiring)** | `FolderWatcher` behaviour re-verified (partial writes, stability, hash de-dupe: `test_watcher_*`); it is a library, wiring `EXCEL_WATCH_DIR` and sending reminders is Core's. Documented; no claim made in my docs that it is wired. |
| QA-H3 connector keys | **Integrations side already supports them** | `IfsConfig`/`SmtpSender`/`GraphSender` read `employees_path`, `page_size`, `modified_field`, `scope`, `ca_bundle`, `use_ssl`, `verify_tls`, `timeout_s`, `rate_limit_per_min`, `max_retries`, `allow_private_hosts`, `max_response_bytes`; the Core API allow-list is Dev-A's. |
| QA-M13 (test suite false assurance), M1-M3, M9, M11, M12, M15, M16, H1, H2, L1-L3, L6, L8, L9, L11, L12 | **Not mine** | Core / deploy / frontend findings. (M15: the renderer accepts `gender`/`*_gender` and fails naming the field; a neutral fallback is a Core/product decision.) |

## Developer response (core/deploy)

Status of every finding after round 4. "Test" names live in `backend/tests/core/` (`test_qa_fixes.py` unless another file is named). `qa/tests` now passes 11/11 (run at the time of writing).
Verified = executed here (SQLite for the whole `tests/core` suite, PostgreSQL 16 for the whole `tests/core` suite via `TMS_TEST_PG_URL`, real factory/renderer/sender where stated). Docker was still not available.

| ID | Status | How / test |
|---|---|---|
| QA-B1 | Fixed | Core now sends exactly Dev-B's `documents/specs.py` names: `total`, `start_date_greg`, `rows[]` (`staff_id, description, full_name, division_cost_center, amount`). Each row prints that attendee's exact share (34/33/33 for 100/3), so rows sum to the total. Test: `test_real_integrations.py::test_settlement_letter_sends_the_renderers_field_names_and_exact_shares` (real renderer, reads the docx), `test_letters_email.py::test_settlement_letter_math` |
| QA-H1 | Fixed | Creating a `level3_request` letter sets `level3_sent=true`, `level3_status="requested"` (manager check: `manager_check`); `PATCH /enrollments` accepts `level3_status/level3_sent` (explicit reopen). Gone from `/automation/due`, dashboard, candidate flags; `workflow.level3_started` turns true. Idempotent. `test_QA_H1_*` (3). Note: "generated" counts as started (the mail is sent from the letter list); the daily job with `auto_send` marks only after the e-mail was accepted |
| QA-H2 | Fixed | Own client-address resolution: `X-Forwarded-For` honoured only from `TMS_TRUSTED_PROXIES` (default loopback + docker bridge `172.16.0.0/12`), read from the right, spoofed left entries ignored; uvicorn `--no-proxy-headers` (Dockerfile, systemd); per-IP limit raised to 100. `test_QA_H2_*` (4) simulate the docker-bridge peer. Not verified with real docker/nginx |
| QA-H3 | Fixed | Allow-list derived from `IfsConfig` dataclass fields + explicit smtp/graph/excel lists (incl. `use_ssl, verify_tls, ca_bundle, timeout_s, rate_limit_per_min, employees_path, page_size, modified_field, scope, max_retries, allow_private_hosts`), typed/ranged; unknown keys still 422; secrets still write-only; sanitized TLS hint in `last_test_message`. `test_QA_H3_*` incl. a drift test that greps `config.get("...")` in Dev-B's sources |
| QA-H4 | Fixed (Core side) | Upload guard before parsing (required members, <=2000 members, no traversal, decompressed <=64 MiB, ratio <=120, corrupt -> 422); row cap; imports/syncs are background jobs (own session, chunked commits of 500, streamed `fetch_employees`, heartbeat + `processed`, lease renewed per chunk, `202 running` if not done in 5 s, stale-run recovery at startup and before each run). Measured: 60,000-record sync 7 s, peak RSS 87 MB (idle 82 MB). `test_QA_H4_*` (5). Not fixed here: Dev-B's xlsx reader still loads an accepted workbook in memory (bounded by the caps); RSS of a 64 MiB upload not measured |
| QA-M1 | Fixed | `PathId`/`Id` (1..2^31-1) on every id (path, query, body), NUL rejected in every body/query, `DataError`/`OverflowError` -> 422 safety net. `test_QA_M1_*` (28 routes + NUL); runs on PG in CI |
| QA-M2 | Fixed | Per-field `manual_fields` (attendance, registration, calendar, payment, comment, motivation): imports/sync never overwrite them, blank incoming never erases; `release_fields` hands back. `test_QA_M2_*` (2) |
| QA-M3 | Fixed | Owner change -> row skipped, error `ticket_owner_conflict`; re-import idempotent (no flip-flop), also for the legacy loader. `test_QA_M3_*` (2) |
| QA-M4 | Fixed | Employee values validated per column (`too_long` row error), each chunk in a savepoint with row-by-row fallback (`db_error`). `test_QA_M4_*` (2); whole suite runs on PG (CI job `postgres`) |
| QA-M5 | Dev-B (renderer) | Core passes values untouched (data as data); the fix is single-pass substitution in `documents/`. `qa/tests` placeholder test passes now |
| QA-M6 | Fixed (Core side) | Export prefixes `'` to strings starting `= + - @ TAB CR` before `write_legacy` (a lone `-` marker kept). `test_QA_M6_*` (2). The gateway itself was not changed |
| QA-M7 | Fixed (a)(b) | Key bound to a hash of recipients/cc/subject/letter or template+fields/channel: same key + different content = 409; `pending` older than `TMS_EMAIL_PENDING_TTL_S` is retryable. `test_QA_M7_*` (3). (c) documented: the generated key is returned in the response, retry with it. (d) Not fixed: `POST /letters` has no idempotency key (double click = two numbers) |
| QA-M8 | Fixed | URL fields reject userinfo, query and fragment (never stored). `test_QA_M8_*` (5 forms x 2 routes) |
| QA-M9 | Fixed | `letters.html_body` is encrypted (AES-GCM, legacy plaintext rows still readable); letter files are AES-GCM blobs on disk (download/e-mail decrypt in memory); rekey covers both; PII-kind preview is audited; SECURITY.md updated. `test_QA_M9_*` (2), `test_rekey_covers_letter_files_*` |
| QA-M10 | Fixed | One implementation: Core builds facts and calls `app.automation.rules.compute_due` for dashboard, candidate flags and scheduler (due ON day end+60, `>=`). `test_level3_boundary_is_ge_60_days_in_every_view` + qa test |
| QA-M11 | Fixed (measured statements) | `candidates:search` 377 -> 9 statements (SQL name pre-filter, batched supervisor e-mail, capped at 500 + `truncated`); lists 3-5; dashboard 18; `/automation/due` capped (`limit`). Ceilings asserted in `test_QA_M11_*`. Not re-measured: the 50-client load test and RSS of two workers; the dashboard is still O(all runs/tickets) |
| QA-M12 | Fixed | Export leaves national code/mobile blank; `include_pii=1` admin-only; audit says which. `test_QA_M12_*` |
| QA-M13 | Fixed (Core) | `test_real_integrations.py` uses the `real_app` fixture (no fake factory; asserts the real module); CI job `postgres` = migrations + the whole core suite on PG (database per test cloned from a migrated template; SQLite-only tests marked); CI frontend job runs `npm test`. Not fixed: Dev-B's 60 s `test_smtp_bad_password_sanitized` |
| QA-M14 | Fixed | Loop now runs: scheduled IFS sync (`ifs_sync_interval_min`), folder watcher (`watch_excel`), daily job sends Level-3 / reminder e-mails only with `auto_send` (default off = dry run in audit + `last_run.notify`), fixed idempotency keys, mark-after-send, no-email skip, one worker at a time. `test_QA_M14_*` (5). Reminder text is a fixed bilingual sentence (no template); not tested against a real SMTP server |
| QA-M15 | Fixed | Neutral honorifics for unknown gender, employee number for a supervisor missing from IFS, per-person kinds skip enrollments without supervisor and report `skipped[]` (422 only when nothing can be built). `test_QA_M15_*` |
| QA-M16 | Fixed | Overlap is tested against booked (run-assigned) courses only. `test_unassigned_idp_requests_do_not_count_as_date_clashes`, `test_candidate_search_rules` |
| QA-L1 | Fixed | `TMS_TRUSTED_HOSTS` applied (TrustedHost middleware), `--no-server-header`; documented. `test_QA_L1_*` |
| QA-L2 | Fixed (server) | Stricter policy (12+, 3 classes, no common word/run/repeat); `Password123456` rejected for users and bootstrap. `test_QA_L2_*`. The SPA text "min 8" is the frontend owner's |
| QA-L3 | Accepted | Documented in SECURITY.md (an attacker can lock a known account 15 min; changing the password resets it) |
| QA-L4 | Fixed (Core) | Malformed uploads -> 422; CR/LF subject -> 422; stricter e-mail regex (no quoted/bracketed forms). `test_QA_L4_*`, `test_QA_H4_zip_bomb_and_bad_archives_*` |
| QA-L5 | Not fixed | Rendering/bidi and frontend `sanitize()` belong to integrations/frontend |
| QA-L6 | Fixed | `pg_restore --clean --if-exists` in DEPLOYMENT; `backup.sh` passes the password via `PGPASSWORD` (checked URL rewrite for 3 URL shapes; PG dump path exercised earlier) |
| QA-L7 | Fixed | The two identifiers replaced by obviously fake ones (`LMS-900002`, `MTC-900001`) in `normalize.py`, `tests/integrations/test_excel.py`, `tests/integrations/synth.py` (edited at the lead's request although those paths are Dev-B's). `.gitignore` now also covers `templates/letter_defaults.json`, `*.dump`, `*.sqlite`, `qa/logs/`, `frontend/screenshots/`, `*.tsbuildinfo`. The `qa/uiux` name coincidence is the frontend's |
| QA-L8 | Info | No action |
| QA-L9 | Warn only | A development-mode app with a non-SQLite URL logs a loud warning; not refused |
| QA-L10 | Dev-B | Per-recipient sending; Core's results/MessageLog line up (`test_extra_per_recipient_email_with_real_sender_matches_message_log`, real factory + SMTP sink) |
| QA-L11 | Fixed / not fixed | `index.html` `Cache-Control: no-cache`, hashed assets immutable (`test_QA_L11_*`). `style-src 'unsafe-inline'` kept (Vite inline styles) |
| QA-L12 | Fixed | Stale `running` runs recovered (heartbeat); `TMS_AUTO_MIGRATE` refused in production (`test_QA_L12_*`) |
| Static review 3 | Fixed | `.dockerignore` excludes `frontend/screenshots`, `*.tsbuildinfo`, `qa`, `docs`; nginx sample uses `http2 on;` and a 300 s read timeout (imports no longer hold the request) |
| Extra: runs list counts | Fixed | `GET /runs` items carry `participants, motivations_yes, letters_sent, level3_started` in 2 queries per page. `test_extra_runs_list_carries_counts_without_n_plus_one` |
| Extra: Persian messages | Fixed | Every `message` and `fields` text is Persian; a source scan + endpoint probes fail on ASCII-only text. `test_extra_every_error_message_and_field_text_is_persian`, `test_extra_runtime_validation_errors_are_persian` |
| Extra: payment path | Fixed | `payment_process` <-> `pr_process_start_date` kept consistent on PATCH; dashboard `payment_not_started` reacts both ways. `test_extra_payment_path_writes_payment_process_and_dashboard_reacts` |
| Extra: per-recipient e-mail | Fixed / verified | Real `SmtpSender` against an aiosmtpd sink: one message per To (cc on each), per-recipient results, MessageLog and idempotent replay line up |

Docs updated: SECURITY.md (encryption of letters, client address, password policy, manual-edit precedence, roles), DEPLOYMENT.md (env table, automation switches, measured limits, trusted proxies), CONTRACT_REQUESTS.md (round 4 API notes).
