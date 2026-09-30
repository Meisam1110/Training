# Deployment (on-prem, air-gapped capable)

One image serves `/api/*` and the built SPA at `/`. PostgreSQL is used in production; SQLite is for
dev/tests. Nothing is downloaded at run time.

## 1. Requirements
Docker 24+ with the compose plugin (or Python 3.11+ and PostgreSQL 14+ for a systemd install),
2 vCPU / 2 GB RAM, a TLS certificate for the internal host name.

## 2. First install (compose)
```bash
cp .env.example .env
openssl rand -base64 32   # -> TMS_DATA_KEY       (back this up SEPARATELY from the database)
openssl rand -base64 48   # -> TMS_SECRET_KEY
openssl rand -base64 24   # -> POSTGRES_PASSWORD and TMS_BOOTSTRAP_ADMIN_PASSWORD (>= 12 chars)
chmod 600 .env
docker compose build                 # frontend is built inside the image: npm ci && npm run build
docker compose up -d                 # db -> migrate (one-shot, alembic upgrade head) -> app
curl -fsS http://127.0.0.1:8000/ready
```
Sign in as `TMS_BOOTSTRAP_ADMIN_USER` (default `admin`); the account is created **only while the users table is empty**.
Then delete the two `TMS_BOOTSTRAP_ADMIN_*` lines from `.env`, create real users in the UI (admin > users), and
configure connectors (IFS, SMTP/Graph, Excel) in the UI: their secrets are stored encrypted and are write-only.

In `production` mode the app **refuses to start** when `TMS_DATA_KEY` is missing/weak, `TMS_SECRET_KEY` is
missing/short/guessable, a bootstrap password is weak, or CORS is `*`.

## 3. Environment variables
| Variable | Default | Meaning |
|---|---|---|
| `TMS_ENV` | `development` | `development`, `test` or `production` (production enforces secret checks, secure cookie default, hides `/api/docs`) |
| `DATABASE_URL` (alias `TMS_DATABASE_URL`) | `sqlite:///./tms-dev.db` | e.g. `postgresql+psycopg://tms:PW@db:5432/tms` |
| `TMS_DATA_KEY` | required in prod | 32 bytes, base64 or 64 hex: AES-256-GCM key for national code, mobile, date of birth, connector secrets |
| `TMS_DATA_KEY_PREVIOUS` | empty | comma list of old keys, decrypt-only (rotation, see 8; `python -m app.security.rekey`) |
| `TMS_SECRET_KEY` | required in prod | >= 32 random chars; HMAC pepper for session tokens |
| `TMS_BOOTSTRAP_ADMIN_USER` / `_PASSWORD` | empty | first admin, only if no users exist |
| `TMS_COOKIE_SECURE` | true in prod | `Secure` flag of the session cookie |
| `TMS_HSTS` | false | send `Strict-Transport-Security` (set true behind TLS) |
| `TMS_CORS_ORIGINS` | empty (closed) | comma list of allowed cross-site origins |
| `TMS_SESSION_HOURS` | 12 | session lifetime |
| `TMS_LOGIN_MAX_FAILURES` / `TMS_LOGIN_LOCK_MINUTES` / `TMS_LOGIN_IP_MAX_FAILURES` | 5 / 15 / 30 | lockout per username, lock window, per-IP failures in window |
| `TMS_MAX_BODY_BYTES` / `TMS_MAX_UPLOAD_BYTES` | 1 MiB / 25 MiB | request limits (uploads = `/import/*`) |
| `TMS_STORAGE_DIR` | `./data` (`/data` in image) | rendered letters and temp files (volume) |
| `TMS_TEMPLATES_DIR` | `<repo>/templates` (auto-resolved from the package, cwd-independent); `/app/templates` in image | .docx templates and optional `letter_defaults.json` (company letterhead constants; `PUT /automation/settings` values override it) |
| `TMS_STATIC_ROOT` | `/app/static` in image | built SPA |
| `TMS_TICKET_URL_BASE` | iCare browse URL | prefix for ticket links in letters |
| `TMS_AUTOMATION_ENABLED` / `TMS_AUTOMATION_INTERVAL_S` | false / 86400 | background loop (daily job + scheduled sync + folder watcher); safe with many workers (DB leases + last-run check). What it DOES is decided by the DB settings below |
| `TMS_SYNC_WAIT_S` / `TMS_SYNC_CHUNK` / `TMS_SYNC_STALE_S` | 5 / 500 / 600 | a sync/import runs as a background job; the request waits this long and answers `202` + `status:"running"` if unfinished. Rows are committed per chunk; a run with no heartbeat for `STALE_S` is closed as an error on startup / next run |
| `TMS_MAX_XLSX_UNCOMPRESSED_BYTES` / `TMS_MAX_XLSX_RATIO` / `TMS_MAX_IMPORT_ROWS` | 64 MiB / 120 / 200000 | zip-bomb and row caps checked before/while parsing an upload or sync |
| `TMS_EMAIL_PENDING_TTL_S` | 900 | a `pending` e-mail row older than this (crashed worker) may be retried with the same idempotency key |
| `TMS_TRUSTED_PROXIES` | loopback + `172.16.0.0/12` | see Client address; `TMS_TRUSTED_HOSTS` (optional) restricts the accepted `Host` header |
| `TMS_AUTO_MIGRATE` | false | run migrations at start (dev only; single process) |
| `TMS_DEMO_PASSWORD` | random per run | password for the `demo_*` accounts created by `python -m app.demo` (dev only) |
| `TMS_LOG_LEVEL` | INFO | JSON logs to stdout, PII/secrets redacted |
| `TMS_TRUSTED_PROXIES` | `127.0.0.0/8,::1/128,172.16.0.0/12` | proxies (IPs/CIDRs) whose `X-Forwarded-For` is trusted; the client is the first hop from the right that is not a trusted proxy (drives per-IP lockout and audit IPs). Uvicorn runs with `--no-proxy-headers`: this is the only place the header is interpreted |

## 4. TLS
Terminate TLS in nginx: `deploy/nginx.conf.example`. Keep the app on loopback (`TMS_BIND=127.0.0.1`), set
`TMS_HSTS=true`, `TMS_COOKIE_SECURE=true`, and `TMS_TRUSTED_PROXIES` if the proxy is not on the host or in the docker bridge range (172.16.0.0/12). With compose + host nginx nothing needs changing: the app sees the bridge gateway (172.x) as peer, trusts it and reads the real client from `X-Forwarded-For`. The app sets CSP
(`frame-ancestors 'none'`), `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `no-store` on API responses.

## 5. Air-gapped install
On a connected build host: `docker build -t tms:1.x .` then `docker save tms:1.x postgres:16-alpine | gzip > tms-bundle.tgz`.
Carry the file over, `docker load < tms-bundle.tgz`, copy `compose.yaml` and `.env`, `docker compose up -d`.
The runtime image installs and downloads nothing; the font and all JS are bundled (no CDN).
Without Docker: `deploy/tms.service` (systemd, hardened) with a venv built from `pip download`ed wheels.

## 6. Upgrade and rollback
1. `deploy/backup.sh` (database + letters). Note the current image tag.
2. `docker compose build && docker compose up -d`: `migrate` runs `alembic upgrade head` before `app` restarts.
   Migrations are never run by the app on start (they would race between workers).
3. Check `/ready` (200 means DB reachable and migrations at head; 503 `migrations_pending` otherwise).
4. Rollback: `docker compose stop app`, `docker compose run --rm migrate alembic downgrade <previous-revision>`
   (or restore the backup), start the previous image tag. Migration 0001 downgrade drops all tables: only use it on an empty DB.

## 7. Backup and restore
`BACKUP_DIR=/var/backups/tms RETENTION_DAYS=30 deploy/backup.sh` (cron daily): `pg_dump -Fc` (or a consistent SQLite copy)
plus a tarball of `letters/`; files older than the retention are deleted. **The data key is not in the backup** (by design):
store `TMS_DATA_KEY` in your secret vault; without it the personal-data columns of a restored DB are unreadable.
Restore: `pg_restore --clean --if-exists --no-owner -d tms tms-db-*.dump`, untar letters into `TMS_STORAGE_DIR`, start with the same key,
`/ready` must be 200 (it also fails with `templates_missing` if a letter template is absent). Test a restore quarterly. `audit_log` is append-only, but backups are what protects it from someone with DB superuser rights.

## 8. Key rotation
1. `deploy/backup.sh`, and keep the old key.
2. Generate the new key; set it as `TMS_DATA_KEY` and put the old one in `TMS_DATA_KEY_PREVIOUS`. Restart: reads work with either.
3. Preview: `python -m app.security.rekey --dry-run` (in the container: `docker compose run --rm app python -m app.security.rekey --dry-run`).
4. Re-encrypt everything: `python -m app.security.rekey` (batched, idempotent, prints counts; a value that no configured key opens is reported by table/column/id and left untouched, exit status 1).
   It covers every encrypted column automatically (employee national code/mobile/date of birth, connector secrets).
5. When it reports `failed=0`, remove `TMS_DATA_KEY_PREVIOUS` and restart. Keep the old key in the vault until old backups are retired.

## 9. Automation switches (admin: `PUT /automation/settings`)
All off by default. `auto_send`: the daily job e-mails due Level-3 requests and registration reminders (with it off it only logs what it WOULD send, in the audit
row and `GET /automation/settings.last_run.notify`). Every e-mail has a fixed idempotency key, so re-runs and second workers never double-send; a Level-3
enrollment is marked done only after its e-mail was accepted. `watch_excel`: poll `connectors.excel.watch_dir` and import a changed workbook (debounced, hash-checked).
`ifs_sync_interval_min`: scheduled IFS delta sync every N minutes. They run only where `TMS_AUTOMATION_ENABLED=true`, one worker at a time.

## 10. Resource limits (measured)
A 60,000-record IFS sync runs as a streamed background job in fixed chunks of 500: peak RSS 87 MB on top of an 82 MB idle process, 7 s on SQLite (`/tmp` benchmark,
QA-H4 saw > 2.8 GB before). A 1 GB container therefore holds two workers plus a sync. Uploads: 25 MiB compressed, 64 MiB / 120x decompressed, 200 000 rows.

## 11. Operations
* Probes: `/health` (liveness), `/ready` (readiness: DB reachable, migrations at head, all six letter templates present). Compose healthcheck uses `/health`.
* Logs: JSON lines on stdout (`docker compose logs app`); request lines carry the path only, never the query string.
* Shutdown: SIGTERM drains within 20 s (`--timeout-graceful-shutdown`), stops the automation loop, disposes the DB pool.
* Resource defaults: app 2 CPU / 1 GB, db 1 CPU / 1 GB; read-only root filesystem, no capabilities, `/data` volume only.
* Imports/syncs: `POST /sync/{src}:run` and `/import/*` answer `200` with the finished run, or `202` with `status:"running"`; poll `GET /sync/runs` (`processed`, `message`).
* Local dev: `make install && make demo` (synthetic data, demo logins printed once), `make test`, `make lint`.
