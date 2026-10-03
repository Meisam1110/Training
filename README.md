# TMS — Training Management System (سامانه مدیریت آموزش)

Web application replacing the legacy Excel workbook + Word mail-merge + Outlook-macro process of the
Talent Development team: course runs, candidates, announcements, motivations, institute and settlement
letters, Level-3 evaluations, line-manager approvals — with Excel and IFS synchronisation, email delivery
and an audit trail. Persian-first (RTL, Jalali), Irancell-inspired design.

| | |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 · Alembic · SQLite (dev) / PostgreSQL (prod) |
| Frontend | React 18 · Vite · TypeScript (bundled Vazirmatn, no CDN) |
| Deploy | one Docker image serves `/api` and the SPA; `compose.yaml` adds PostgreSQL |

```
make install && make test        # backend + integrations tests
make demo                        # synthetic demo data
cd frontend && npm ci && npm run dev:mock   # UI without a backend
make build && make up            # image + compose (see docs/DEPLOYMENT.md)
```

Start with `docs/ARCHITECTURE.md`, then `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/INTEGRATIONS.md`,
`docs/TEMPLATES.md`, `docs/UX.md`. Independent audits: `docs/QA_REPORT.md`, `docs/QA_UI_UX.md`.

**Data policy:** this repository contains synthetic data only. Never commit real employee data, exports of the
legacy workbook, or credentials (`.env`, connector secrets). Connector secrets are stored encrypted with `TMS_DATA_KEY`.

**Not verified in the build environment:** `docker build`, real IFS / SMTP / Microsoft Graph, Word and Outlook
rendering. See the "Not verified" sections of the docs before going live.
