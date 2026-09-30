# Training Management (TMS) — Architecture & Build Contract

Single source of truth for the three developer agents. **Stay inside your ownership area;
change shared files only through the contract below.**

## 1. What it replaces
`New_Calendar_2021-Meisam.xlsm` + 9 Word mail-merge templates + Outlook macros
(see docs/ANALYSIS.md). TMS makes the same flow a web app:

IFS (employees) + iCare IDP export (course requests) → plan a course run → announce
(email) → collect motivations → institute letter → invoice/settlement letter → Level-3
evaluation (60 days after end) → manager confirmation → line-manager approval batches.

## 2. Stack (matches the sibling PARDAKHT repo — do not deviate)
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2. SQLite in dev/tests,
  PostgreSQL in prod (`DATABASE_URL`).
- Frontend: React 18 + Vite + TypeScript, TanStack Query/Table, hash router, Vazirmatn
  bundled (no CDN — on‑prem, air‑gapped install must work).
- One Docker image serves `/api/*` and the built SPA at `/`. `compose.yaml` adds Postgres.
- Docs/letters: python-docx (+ docxtpl-style `{{ field }}` rendering), openpyxl, jdatetime
  is NOT allowed (offline, keep deps small) → port the VBA Jalali library (`persian/`).

## 3. Ownership (no overlaps)
| Agent | Owns | Must NOT touch |
|---|---|---|
| **Dev-A Core** | `backend/app/{main,config,db,models,schemas,api,auth,audit,security}`, `backend/alembic`, `backend/tests/core`, `deploy/`, `Dockerfile`, `compose.yaml`, `Makefile`, `.github/`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md` | integrations/, frontend/ |
| **Dev-B Integrations** | `backend/app/{integrations,automation,documents,persian}`, `backend/tests/integrations`, `templates/`, `docs/INTEGRATIONS.md`, `docs/TEMPLATES.md` | api/, models/ (request changes via §6) |
| **Dev-C Frontend** | `frontend/`, `docs/UX.md` | backend/ |
Shared and frozen (only the lead edits): `backend/app/contracts.py`, `docs/API_CONTRACT.md`,
`docs/ARCHITECTURE.md`, `docs/design-tokens.json`.

## 4. Domain model (Dev-A implements; names are final)
`User(role: admin|hr|viewer)`, `Institute`, `Employee` (mirror of IFS: emp_no, names en/fa,
gender, email, mobile, national_code*, division, cost_center, supervisor_emp_no, status),
`Course`, `CourseRun` (= CHistory row: course, type online|in_person, institute, duration_h,
start/end date, days, time, sessions, send_date, deadline, amount, section_b, status),
`Enrollment` (= IDP/Record row: employee, run, ticket LMS-…, status, motivation, registration,
calendar, attendance, level3_status), `Letter` (kind, run, rendered file path, number, state),
`MessageLog` (email sent/failed, recipients, subject, letter_id), `ConnectorConfig`
(kind: excel|ifs|smtp|graph, encrypted JSON), `SyncRun`, `AuditLog` (append-only).
`*` national_code, mobile, DOB are personal data: encrypted at rest (AES‑GCM), masked in
lists, revealed only for role admin/hr with an audit entry.

## 5. Automations (Dev-B implements behind `contracts.py` Protocols)
1. **Excel sync** — import IDP export (.xlsx) and the legacy workbook (`Record`,`CHistory`,
   `IFS` sheets) idempotently; watch a folder (`EXCEL_WATCH_DIR`) or a UNC/SharePoint-synced
   path; export back to xlsx in the legacy column layout. Never modify the source file.
2. **IFS connector** — read employees/supervisors. Auth modes: `oauth2_client_credentials`
   (IFS Cloud/IAM), `basic`, `session_login` (form login, cookie jar with auto re‑login on
   401/expired). Token refresh + retry with backoff, timeouts, circuit breaker, pagination,
   `test_connection()`, delta sync by modified‑since. Ship an in‑repo mock IFS server for
   tests/demo. **No real credentials in the repo.** Real IFS endpoint shapes are configured
   (`ifs.field_map`) not hard-coded, because tenant projections differ — document this.
3. **Letters** — render the six documents from `templates/*.docx`: `course_announcement`
   (fa+en), `institute_letter`, `settlement_letter`, `level3_request`, `level3_manager_check`,
   `line_manager_approval`. Field names = the MERGEFIELD names in docs/ANALYSIS.md.
   Output .docx (+ HTML body for email). Persian digits/date-in-words/deadline logic ported
   from VBA (`J_JALALDATE`, `J_ADDDAY`, `TbH`, `AbH`).
4. **Email** — `SmtpSender` (STARTTLS) and `GraphSender` (MS Graph app-only). Outlook COM is
   Windows-only and is intentionally dropped. Dry‑run mode, per‑recipient result, rate limit,
   idempotency key so a retry never double-sends.
5. **Scheduler** — daily job: Level‑3 due (end_date+60d), deadline reminders, >3 motivations
   alert, payment-not-started alert. Idempotent; exposes `run_now()` for the UI.

## 6. Changing the contract
Need a new field/endpoint? Add a line to `docs/CONTRACT_REQUESTS.md` (agent, what, why) and
code against the request; the lead reconciles. Never edit frozen files.

## 7. Quality bar (QA agents will test all of this)
- Every endpoint: authz test, validation test, happy path. RBAC enforced server-side.
- No secret/PII in logs, repo, sample data, or error bodies. Only **synthetic** data
  (`backend/app/demo.py` generates it). The real workbook/letters contain real employees —
  never commit them.
- Fully offline build. Reproducible: `make test`, `make run`, `make build`.
- Persian first: RTL, Jalali dates, Persian digits display, Latin digits in inputs accepted.
