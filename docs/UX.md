# TMS frontend — UX & engineering notes

Persian-first SPA in `frontend/` (React 18 + Vite + TypeScript strict, TanStack Query/Table/Virtual, hash router, Vazirmatn bundled from npm — no CDN, no third-party request at runtime).

## Run it

| Command | What |
|---|---|
| `npm run dev:mock` | dev server with the in-memory mock API (`VITE_MOCK=1`); login `admin` / `hr` / `viewer`, password `demo` |
| `npm run dev` | dev server, `/api` proxied to `http://localhost:8000` (override with `VITE_API_TARGET`) |
| `npm run build` | `tsc -b` (strict) + Vite build; `npm run build:mock` bakes the mock in |
| `npm test` | Vitest (jsdom). `src/api/live.test.ts` runs only with `TMS_LIVE_URL/USER/PASS` set (against a running backend) |
| `npm run screenshots` | needs `VITE_MOCK=1 npm run build`; writes `frontend/screenshots/*` (13 screens × light/dark × 1280/360); `screenshots-flows.mjs` = dialogs/date picker/drawer/undo; `screenshots-live.mjs` = real backend (`screenshots/live/`) |

## Design principles ("Irancell concept")
1. **Confident, not loud.** Yellow `#FFCC00` + ink `#1A1A1A` on warm neutrals. Yellow is only ever a *fill* behind ink text: primary buttons, active nav item, current stepper step, the dry-run frame, progress bars. Never yellow text on white (a test asserts the ratio is < 2 and that no text token is yellow).
2. **Hierarchy through whitespace and weight**, 10 px cards, one `h1` per page, generous 24 px card padding, 15 px base with Persian line-height 1.75.
3. **The next action is always visible**: empty states carry a CTA, every dashboard row has a verb button, the run page has "this step is done → next".
4. **Outward or irreversible actions say what will happen** (send e-mail, run sync/automation, reveal PII, advance a run, export with PII) and must be confirmed. Reversible edits are instant with **undo** instead of a confirm.
5. **Never trust the UI for security.** Role-aware rendering only removes what the API would refuse anyway (viewer: no create/edit/send/import; hr: no connector edit/test, no admin; admin: all). The mock enforces the same roles + CSRF so the 403 paths are exercised.

## Tokens
`docs/design-tokens.json` is the single source. `scripts/tokens.mjs` (run by `predev/prebuild/pretest`) writes `src/styles/tokens.generated.css`: `:root` (light), `@media (prefers-color-scheme: dark){:root:not([data-theme="light"])}` and `:root[data-theme="dark"]`. Beyond the JSON it **derives**, per theme: `surface-2`, `line-strong`, `*-bg` tints for ok/warn/danger/info, and it *nudges* status colours and the focus ring darker (light) / lighter (dark) until they pass AA (4.5:1 text, 3:1 non-text). The JSON is never edited; swap brand colours there only. `src/lib/tokens.test.ts` checks every text/background pair in both themes.

Spacing `--space-1..7`, radius `--radius-sm/md/lg`, type `--fs-1..7`, `--sidebar-width`, `--min-touch` (44px), `--max-content`.

Theme: follows the OS by default; the sidebar/topbar toggle cycles auto → light → dark and persists to `localStorage("tms.theme")` (try/catch; page works without storage). `public/theme-init.js` applies it before first paint and is an external file because the backend CSP is `script-src 'self'`.

## Component inventory (`src/components`)
`Button/LinkButton` (pending state, 44px), `Chip` (tones ok/warn/danger/info/brand + dot), `Skeleton`, `EmptyState`, `ErrorState` (retry), `Callout`, `PageHead` · `Dialog` (focus trap, Esc, focus restore, `#root` inert, scroll lock, `locked` while pending) + `ConfirmDialog` · `Toast` (persistent polite + assertive live regions, action button for undo) · `Field` (`TextField` with `numeric` = Persian display / Latin state, `SelectField`, `TextAreaField`, `Switch`) · `DatePicker` (Jalali text input + calendar popover, arrow/PageUp/PageDown/Home/End) · `DataTable` (TanStack Table, server sort with `aria-sort`, pager, skeleton/empty/error states, optional virtualization, sticky first column) · `Layout` (sidebar → drawer < 980px, skip link, theme toggle) · `Wordmark` · domain: `Stepper`, `RunStatusChip/TriChip/AttChip`, `SecretField`, `MaskedPII`, `EmailSendDialog`.

Libraries: `lib/jalali.ts` (own converter, tested), `lib/digits.ts`, `lib/runs.ts` (step derivation), `lib/labels.ts` (fa strings).

## Screen map
`#/login` · `#/` Dashboard · `#/runs` (filter/sort table, new-run dialog) · `#/runs/:id` (stepper + step panel + enrollments) · `#/runs/:id/candidates` (picker) · `#/enrollments` · `#/letters` · `#/employees` · `#/connectors` · `#/automation` · `#/import-export` · `#/admin` (users, audit). Page titles are set per route (`… — مدیریت آموزش`) and the `h1` receives focus on navigation.

Key flows: Enrollments inline edit is optimistic (all cached lists patched synchronously), rolls back with an error toast on failure and offers **«برگردان»**. Email: compose (dry-run switch in a framed box, ON for a letter's first live send) → confirm (counts + consequence) → per-recipient result; one idempotency key per dialog, `inFlight` ref + disabled button = no double send, key kept on retry. Connectors: secrets are password inputs that never show a stored value ("تنظیم شده / تنظیم نشده"), only typed secrets are sent. Employees: national code/mobile masked; "reveal" opens a dialog warning it is audited, value auto-hides after 30 s.

## Data layer & backend adaptation
`api/client.ts`: cookie session (`credentials: same-origin`), `X-CSRF-Token` captured from any response header or login/me body and sent on POST/PUT/PATCH/DELETE, error-envelope parsing (Persian fallbacks), 401 → clear CSRF + redirect to login (not for the login call itself), network errors → `ApiError(code:"network")`, XHR upload with progress. `api/mock/*` implements every endpoint in memory with synthetic data and goes through the same client. **The real backend's JSON differs from the UI types** (names, `Yes/No/""` vocab, status set, connectors, dashboard items…), so `api/wire.ts` maps backend → UI types and UI → request bodies (all backend schemas are `extra=forbid`); the mock speaks UI types directly. `wire.test.ts` uses payloads captured from the running backend; `live.test.ts` exercises the adapters end-to-end. Backend caps `page_size` at 200 (client clamps) and rejects unknown `sort` keys (`sortParam` maps or drops them). Run workflow step is *derived* (see CONTRACT_REQUESTS).

## Accessibility decisions
- `<html lang="fa" dir="rtl">`; logical CSS properties throughout; Latin strings (emails, tickets, paths) get `dir="ltr"` islands, embedded Latin in Persian sentences is bidi-isolated.
- WCAG AA verified for tokens in both themes (test); visible 2px focus ring on every control (`:focus-visible`), extra inner edge on yellow buttons; 44px minimum targets; no colour-only status (chips carry text).
- Forms: label + `aria-invalid` + `aria-describedby`, inline fa errors (`role=alert`), submit disabled while pending, input preserved on failure.
- Dialogs: `role=dialog aria-modal`, labelled, focus trapped and restored; toasts announced (polite/assertive); drawer closes on Esc and focuses its close button; tables have captions, `scope=col`, `aria-sort`, scroll regions are focusable.
- `prefers-reduced-motion` removes shimmer/transitions; skeletons and fixed row heights (52px) avoid layout shift; responsive to 360px (drawer nav, tables scroll with sticky first column, date popover full width).

## Round 2 (QA fixes + backend alignment)
- **Session expiry (H3):** 401 → `#/login?next=<same screen>&expired=1` with a Persian explanation; the router never bounces a public route to `/`; stale toasts are dropped. Form state lives in `useDraft` (sessionStorage, per key, try/catch, cleared on success; never passwords/secrets): new-run dialog, run plan/money form, letter overrides, connector config, automation settings, new-user dialog. Verified in Chromium: type, force 401, re-login, land on the same run with the value restored.
- **E-mail dialog (H4/H5):** shows letter number, course, subject, attachment, collapsible body preview and every recipient with a checkbox; recipients who already received the letter get «قبلاً در تاریخ … ارسال شده» and start unchecked; dry-run is ON for a first send and whenever anyone was already mailed; the confirm step repeats course + count and warns on repeat delivery; the idempotency key is renewed when recipients/mode change and reused on retry.
- **Forms:** Jalali input accepts compact `14050708`, refuses Gregorian-looking years (offers the converted date with an «اعمال» button), explains each invalid date; amounts accept Excel pastes (`260,000,000`, `۲۶۰٬۰۰۰٬۰۰۰`, «ریال») and show the parsed value; failed validation focuses the first invalid field. Untouched required letter fields stay neutral (a counter explains the disabled button).
- **New workflows:** bulk motivation on Enrollments (select → confirm → one undo), candidates «select all» skips flagged people unless «include flagged» is on (names listed in the confirm), user PATCH (role, enable/disable with confirm, password reset, last-admin 409), institute picker with inline create, per-person letter kinds get a participant picker, import error table with CSV download (UTF-8 BOM).
- **Access:** route-level guard shows «دسترسی ندارید» for viewer on `#/connectors`, `#/import-export`, `#/admin`; nav entries hidden.
- **A11y:** wordmark `role=img`; stepper uses `aria-current="step"` + hidden text (no `aria-selected`) and arrow keys; empty table headers labelled; 44px hit areas for checkboxes/sort buttons/in-table links; identifiers (`Ident`) are Latin, mono, LTR everywhere. axe (12 screens × 2 themes × 1280/360): 0 violations.
- **Backend alignment:** `wire.ts` now maps `workflow{}` (run detail; heuristic kept as fallback for list items), per-ticket over-3 items, `errors[]` objects `{sheet,row,column,code,reason}`, enrollment `email/supervisor_email` (recipient join removed), `motivation=none`, `last_test_message`, sync `message`, uniform 422 `fields{}` for letters, institutes, users PATCH. Run **list** items carry no counts, so the table shows «—» (CONTRACT_REQUESTS).
- **Verified live** (real backend, demo data, local aiosmtpd sink, `src/api/live.test.ts`): preview/create/download .docx for 5 of 6 letter kinds; dry-run delivers nothing; real send delivers once and an idempotent replay delivers nothing; SMTP connector test; institutes create/409; users create/patch/last-admin 409. `settlement_letter` cannot be created: backend field-name mismatch (reported).

## Round 3 — layout stability, terminology, courses
- **Page-jump investigation.** Measured with `scripts/cls.mjs` (PerformanceObserver `layout-shift` + scroll-jump probe, 30 s per screen, `--slow` = 400 ms RTT / 1.5 Mbit / 4x CPU) against the mock and the real backend. Idle, every screen already had CLS 0.00 and no timers exist (no `refetchInterval`, `refetchOnWindowFocus:false`), so the "every few seconds" jumps are load-time and interaction-time: (1) five static Vazirmatn weights were fetched lazily, each re-flowing the whole page when it arrived (`base.css`, now one 111 KB variable file, `font-display:block`, first render held ≤2.5 s for it in `main.tsx`); (2) skeleton→content swaps with unreserved height (dashboard 0.26–0.30, connectors 0.30–0.35, letters 0.04) now reserve space (`.dash-body/.due-body/.conn-skel/.letters-col/.preview-slot`, sync chips skeleton, due list capped at 6 + «see all»); (3) inline enrollment edits invalidated the list, so under an active sort rows moved under the cursor (`Enrollments.tsx`: optimistic cache is the truth, no list refetch); (4) sorts had no tie-break (`wire.sortParam` adds `,id`/`,emp_no`; mock sorts tie-break too). Load-phase CLS after: dashboard 0.002–0.019, connectors ≤0.011, letters ≤0.024, others 0.00; steady state 0.000 everywhere. Run `npm run cls -- --url <preview> --user … --pass …` (exit code 1 if any screen is unstable).
- **Terminology.** «انگیزه‌نامه» → «موتیویشن» everywhere (UI, mock, tests, this doc); Import/Export screen is «انتقال اطلاعات» (route `#/import-export` kept, `#/transfer` added as an alias).
- **Course vs run.** New catalog screen «کاتالوگ دوره‌ها» (`#/courses`: course, category, default duration, run count + last start, active, create/edit, «برگزاری جدید» per course). «دوره‌های آموزشی» is now «برگزاری‌ها» (`#/runs`, dated instances): columns course · institute · type · Jalali range · duration · participants · motivation (x of y) · status; filters search/course/status/type, stable sort, count footer, contextual empty states with the next action; `?course=`, `?status=`, `?new=1` deep links.
- **Digit law** (`npm run audit:digits`): display numbers/dates are Persian digits, identifiers are Latin LTR (`Ident`); audit scans every screen's text nodes (mock and real): 0 violations. Backend English prose (`/automation/due` details) is re-composed in Persian by `wire.due`; Latin digits in display names are converted.

## Logo / brand swap
No Irancell logo asset exists in the repo. `components/Wordmark.tsx` is a **neutral placeholder** (yellow tile + "M" glyph + product name). To use the real logo: replace the body of `BrandMark` with `<img src={logo} alt="" />` (or inline SVG) — nothing else references it; change the favicon data-URI in `index.html`; brand colours live only in `docs/design-tokens.json`.

## Known limits
Letters/e-mail against the real backend could not be exercised end to end (templates absent in the dev environment → 502 `template file not found`); the mock covers the UI flow. Virtualized tables are covered by the browser screenshots, not jsdom (jsdom renders a first window).
