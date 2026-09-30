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
