# API contract (v1) — Core implements, Frontend consumes

Base `/api/v1`. JSON. Auth: `POST /auth/login {username,password}` → sets HttpOnly
`tms_session` cookie (SameSite=Lax) + CSRF header `X-CSRF-Token` for unsafe methods.
Errors: `{"error":{"code":"validation|forbidden|not_found|conflict|upstream","message":"fa text","fields":{...}}}`
Lists: `?page=1&page_size=50&q=&sort=-start_date` → `{items:[],total,page,page_size}`.
Dates are ISO Gregorian on the wire; the UI renders Jalali. Roles: admin > hr > viewer.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` |
| Dashboard | `GET /dashboard` → `{not_started_courses[], payment_not_started[], over3_motivations[], level3_due[], counts{}, last_sync{excel,ifs}}` |
| Employees | `GET /employees` · `GET /employees/{emp_no}` (`?reveal=1` audited) |
| Courses | `GET/POST /courses` · `GET/PATCH /courses/{id}` |
| Runs | `GET/POST /runs` · `GET/PATCH /runs/{id}` · `GET /runs/{id}/enrollments` · `POST /runs/{id}/candidates:search` |
| Enrollments | `GET /enrollments` · `PATCH /enrollments/{id}` (motivation, registration, calendar, attendance) · `POST /enrollments:bulk` |
| Letters | `GET /letters` · `POST /letters/preview {kind,run_id|enrollment_ids,lang}` → html · `POST /letters {…}` (creates+renders, numbered) · `GET /letters/{id}/download` |
| Email | `POST /email/send {letter_id|template,recipients,dry_run}` → per-recipient results · `GET /messages` |
| Connectors | `GET /connectors` · `PUT /connectors/{kind}` (secrets write-only) · `POST /connectors/{kind}:test` · `POST /sync/{excel|ifs}:run` · `GET /sync/runs` |
| Automation | `GET /automation/due` · `POST /automation/run` · `GET/PUT /automation/settings` |
| Import/Export | `POST /import/idp` (xlsx) · `POST /import/legacy-workbook` · `GET /export/legacy.xlsx` |
| Admin | `GET/POST /users` · `GET /audit` · `GET /health` · `GET /ready` |

## v1.1 — additions and deviations merged by the lead (source of truth = running code + OpenAPI at `/api/docs`)
- **Errors:** codes now include `unauthorized` (401) and `rate_limited` (429 + `Retry-After`). Missing-letter-field errors are
  422 `validation` with `fields{<name>:"required"}`. All user-facing messages are Persian.
- **Users:** `PATCH /users/{id} {is_active, role, password, display_name}` (admin; last active admin cannot be disabled/demoted → 409;
  password change/deactivation revokes sessions).
- **Institutes:** `GET/POST /institutes`, `PATCH /institutes/{id}`; `POST /runs` also accepts an institute *name* (auto-created).
- **Runs:** list items carry counts (participants, motivations_yes, letters_sent, level3_started); `GET/PATCH /runs/{id}` include
  `workflow{announced, motivations_collected, institute_letter_sent, invoice_received, settlement_sent, level3_started}`; `delivery_type` = `type`.
- **Enrollments:** items carry `email`, `supervisor_emp_no`, `supervisor_email`; filter `?motivation=none`.
  `candidates:search` returns flags `over_motivation_limit` (per **ticket**, ≥3 offers without "Yes"), `division_change`, `non_active`, `level3_eligible` (end+60d, ≥).
- **Letters:** `POST /letters` returns the first Letter plus `items[]` (per-person kinds and manager batches of ≤9 create several);
  `POST /letters/preview` → `{kind, subject, html, filename, count, missing_fields}`. Letter bodies/files are encrypted at rest.
- **Email:** one message per recipient; idempotency key is bound to the full request (same key + different content → 409).
- **Connectors:** `last_test_message` (sanitized); accepted config keys derive from the connector config classes; URLs with credentials rejected.
- **Import/sync:** long runs are background jobs — the API answers `202 {status:"running"}`; poll `GET /sync/runs`. `errors[]` items are
  `{sheet,row,column,code,reason}` (never cell values), capped at 100.
- **Ops:** `/ready` also checks migrations and the six letter templates.
