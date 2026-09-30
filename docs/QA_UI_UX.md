# TMS frontend — independent UI/UX QA

Reviewer: independent QA agent. Build under test: `npm run dev:mock` (mock API), Chromium via Playwright, 2026-09-30.
Evidence and scripts live in `qa/uiux/` (`sweep.mjs`, `j1..j14.mjs`, `stress.mjs`; screenshots `sweep/*.png`, `j*.png`, etc.).
Every finding below was reproduced in the browser (or, where noted, by reading the exact source line it stems from). Source was not modified.

Coverage: 12 screens + login x light/dark x 1440/1280/768/360 (104 screenshots), axe-core on 12 screens x 2 themes x 1280/360, keyboard pass, 200 % zoom, 200 % text scale, 320 px, reduced motion, roles admin/hr/viewer (all routes incl. direct URLs), injected 500 / 502-html / offline / 401 responses, 3,000 employees + 700 candidates, very long names, Jalali and number-input edge cases.

Positives (so the list is read in proportion): no console/page errors on any screen; no horizontal overflow at 1440/1280/768/360; rendered text contrast passes everywhere (axe: 0 colour-contrast violations; yellow is only ever a fill behind ink); focus ring visible on every tab stop; dialogs trap focus, inert `#root`, return focus on Esc; double-click on "real send" produced exactly 1 POST; a failed send keeps recipients and idempotency key; 3,000-row lists are paged and the 700-row candidate list is virtualised (19 DOM rows); long Persian names wrap cleanly; Esfand 29/30 and leap 1403 are computed correctly; Persian/Arabic/Latin digits are accepted in date and number fields; rem-based type scales with browser text size on every screen except the dashboard (H2).

## Findings

Severity: Blocker = user cannot finish or does the wrong outward action; High = wrong result or excludes a user group in normal use; Medium = friction/error-prone; Low = polish.

### Blocker
None found. (H1 and H4/H5 come closest.)

### High

**H1. Dashboard "ساخت نامهٔ تسویه" opens the settlement letter for the wrong course.**
Screen: Dashboard, card «پرداخت آغاز نشده». Repro: admin → click «ساخت نامهٔ تسویه» on the row «امنیت سایبری مقدماتی — مرکز آموزش پارسیان». URL becomes `#/letters?kind=settlement_letter` (no `run=`); the course select defaults to the first run («مدیریت زمان — ۱۴۰۵/۰۸/۱۳») and the preview names supplier «مؤسسه توسعه فردا». Source: `screens/Dashboard.tsx:19` (`to: () => "/letters?kind=settlement_letter"`). Screenshots: `qa/uiux/dash-settle-wrongrun.png`, `dashboard-full.png`.
Cost: a numbered invoice letter for the wrong institute/amount. The level-3 CTAs do pass `run=`.
Fix: pass `&run=${item.run_id}` on every dashboard CTA; on Letters, never preselect a run when the link has none, and show the chosen course name prominently above the preview.

**H2. Dashboard breaks at 200 % text size / 320 px.**
Repro: 360 px viewport with `html{font-size:200%}`, open `#/`. The sync-status chips (non-wrapping `.chip` inside `.row`) are 602 px wide, scrollWidth 618 > 360, and the visible area shows only a clipped chip. Same at 320 px (335 > 320). Screenshots `text200-dash.png`, `w320-dash.png`. All other screens pass at 200 % text and 200 % zoom (640 px).
Rule: WCAG 1.4.4 / 1.4.10. Cost: low-vision users cannot use the landing page.
Fix: `white-space:normal; max-inline-size:100%; overflow-wrap:anywhere` on those chips; shorten the text.

**H3. Session expiry mid-form drops the work silently and says nothing.**
Repro: run 3 → «برنامه‌ریزی», edit «مؤسسه», make the next call 401 (forced by wrapping `Response`), click «ذخیرهٔ برنامه». The app goes to `#/login` with no `?next=` and no «نشست منقضی شد» message; the typed value is gone; after re-login the user lands on the Dashboard. Screenshot `j3-401.png`. Source: `client.ts handle401` only clears the user; `LoginScreen` supports `next` but nothing sets it.
Fix: redirect to `#/login?next=<path>&expired=1`, show a Callout explaining the expiry, and keep dirty form state in `sessionStorage` per route to restore after login.

**H4. Email actions do not show what will be sent, nor which course/letter it belongs to.**
Repro A: run 3 → «اطلاع‌رسانی» → «ارسال ایمیل اطلاعیه…». The compose dialog has only the dry-run switch and 7 recipients — no subject, no body preview, no attachment, no letter number, no course name; recipients cannot be deselected (`j2-send-compose.png`). Repro B: Letters → «نامه‌های ساخته‌شده» has columns شماره / نوع / وضعیت / تاریخ / عملیات only (no course), and row button «ایمیل» opens «ارسال نامهٔ مؤسسه» without naming the course (`viewer_letters.png`). The confirm step says only «۷ ایمیل ارسال می‌شود. این کار قابل بازگشت نیست.»
Rule: UX.md principle 4. Cost: an irreversible mass mail whose content the sender never saw, possibly for the wrong course.
Fix: dialog header «اطلاعیهٔ دوره · <دوره> · TD-1405/0141», subject + collapsible body + attachment, «دوره» column in the list, deselectable recipients, course + count in the confirm sentence.

**H5. Re-sending defaults to a real send and re-mails everyone, with no "already sent" warning.**
Repro: run 3 (seed has a prior real send of letter #1) → «ارسال ایمیل اطلاعیه…». Switch is «خاموش» from the first frame, callout «ارسال واقعی … قابل بازگرداندن نیست», recipients = all 7 enrolled, including those already notified; no "sent on … to N" line. Dry-run stays off even right after a dry run (`j2.mjs`).
Cost: duplicate announcements to employees. The safeguard exists only for the very first send.
Fix: show «قبلاً در <تاریخ> برای N نفر ارسال شده»; default recipients to "not yet notified"; keep dry-run ON by default per dialog or require a second confirmation for a repeat real send.

### Medium

**M1. No bulk marking of motivations.** Enrollments table has 0 checkboxes and no bulk control; 10 people = 10 native-select interactions + 10 toasts, although the API has `enrollments:bulk` (`enrollments-motivation.png`). Fix: row selection + «تأیید انگیزه‌نامهٔ انتخاب‌شده‌ها» with one undo.

**M2. Candidates "select all" silently selects every result including flagged ones** (697 in the stress run: «۶۹۷ نفر انتخاب شده · ۴۱ مورد دارای هشدار»; `s-cand-700-scrolled.png`). Fix: select only unflagged rows by default, and list flagged names (not just a count) in the confirm.

**M3. Jalali date input accepts a Gregorian year.** `2026/10/01` is accepted as Jalali year 2026; `0001/01/01` also accepted; `14050708` rejected (`j4.mjs`). Fix: sane window (1300–1500), «این تاریخ میلادی به نظر می‌رسد؛ معادل شمسی: …؟», accept compact 8 digits.

**M4. Date/number errors are not actionable.** Every invalid date (1405/12/30, 1405/07/31, month 13) gives «تاریخ معتبر نیست؛ نمونه: ۱۴۰۵/۰۷/۰۸». Amount: `260,000,000 ریال` and `260٫000٫000` → «مبلغ باید عدد باشد.» Fix: «اسفند ۱۴۰۵ فقط ۲۹ روز دارد», «ماه باید ۱ تا ۱۲ باشد», strip units, treat `٬` and `,` as thousands only.

**M5. Amount hint contradicts a valid Excel paste.** Settlement step: `260,000,000` or `۲۶۰٬۰۰۰٬۰۰۰` saves, but the hint reads «— ریال» (`fmtNum(Number("260,000,000"))` = NaN). `260٫5` is accepted and hinted «۲۶۱ ریال» (silent rounding); `1.5` and `-5` reach the server and return an unattached toast «اطلاعات واردشده معتبر نیست.» (`amount-hint-dash.png`). Fix: compute the hint with `parseNum`; reject non-integers/negatives with a field error.

**M6. Plan step of a new run shows wrong help and no next action.** Step 1 says «این مرحله با ثبت داده (کاندیدا یا انگیزه‌نامهٔ تأییدشده) خودکار پیش می‌رود.» (copy for steps 2/4; also shown on «اطلاع‌رسانی»), and the only button is «ذخیرهٔ برنامه» (`j1-newrun-detail.png`). Fix: per-step help and a primary «برو به انتخاب کاندیدا».

**M7. Letters form shows errors on untouched fields.** A settlement letter with missing invoice data opens with three red inputs and three alerts, and a disabled primary with no reason beside it (`sweep/letters-light-1280.png`). Fix: neutral required styling until blur/submit; «۳ فیلد باقی مانده» next to the button.

**M8. Forbidden screens are guarded inconsistently for the viewer.** `#/admin` shows «دسترسی ندارید», but `#/connectors` fires the call and shows «بارگذاری انجام نشد … شما اجازهٔ انجام این کار را ندارید» with a useless «تلاش دوباره», and `#/import-export` renders dead disabled «شروع درون‌ریزی» buttons (`viewer_connectors.png`, `viewer_import-export.png`). Fix: route-level role guard.

**M9. Letters ignores in-place hash navigation.** Changing `?kind=…&run=…` while on Letters (Back/Forward, link) keeps the old selection/preview; state is initialised from the query once (`j7.mjs`). Fix: sync state from `route.query`.

**M10. Touch targets below the product's own 44 px rule.** Candidate checkboxes 22x22, sort buttons 36 px high, switch inputs 44x26, in-table links 23–25 px high (`sweep-results.json` → `small`). Fix: 44 px label wrappers, `min-block-size:44px` on `.th-sort`, padded links.

**M11. axe violations on every screen.** `aria-prohibited-attr` (serious): `.wordmark` is a `<span aria-label>` with no role; `aria-allowed-attr` (critical): Stepper buttons use `aria-selected` (run detail); `empty-table-header` (minor): Employees actions `<th>`. Fix: `role="img"` or sr-only text on the wordmark, use `aria-current`/`aria-pressed` (or a real tablist), add sr-only «عملیات».

**M12. Repeated identical link names on the dashboard** (4x «ادامهٔ برنامه‌ریزی», 4x «درخواست ارزیابی», 2x «ساخت نامهٔ تسویه») with no row context (WCAG 2.4.4); KPI «۱۷» level-3 items but only 4 rows and no «مشاهدهٔ همه». Fix: per-row `aria-label`, add "see all".

**M13. Identifier digits are inconsistent.** Employee number is Persian («۷۱۰۰۰») on Employees but Latin («71224») on Candidates; the employee dialog mixes bold Persian, mono Latin ids and left/right-aligned values in one list (`employee-detail.png`, `candidates-light-1280.png`, `employees-light-1280.png`). Decide once: identifiers Latin, `dir=ltr`, mono, consistently aligned.

### Low
- L1. Invalid dialog submit leaves focus on the button instead of the first invalid field (`dialog-errors.png`).
- L2. Stale toasts survive navigation and appear even on the login page; a failed send reports twice (dialog callout + toast) (`j3-401.png`, `j3-send-500.png`).
- L3. Stepper is 7 tab stops with no arrow keys; the whole step panel is `aria-live="polite"`.
- L4. Import failure leaves the progress bar at «۱۵٪» beside the error (`import-bad.png`); import (creates/updates records) has no confirm, unlike export and automation.
- L5. ZWNJ inconsistency: «برگزارشده», «لغوشده» vs «برنامه‌ریزی‌شده».
- L6. «دوره» means both course and run; «کاندیدا/شرکت‌کننده/کارمند» alternate; a dry run reports «۷ موفق» for mails not sent.
- L7. Hint «به شمسی، مثلاً ۱۴۰۵/۰۷/۰۸» repeated under six date fields and again as placeholder.
- L8. Disabled yellow primary becomes pale yellow/grey text and looks unfinished; wordmark is a generic «M» tile (documented placeholder).
- L9. Login demo hint mixes Latin/Persian in odd bidi order (`mmisc.png`); demo only.
- At 360 px the Admin users table clips the role chip at the edge (`m360b.png`).

## Critical journeys (mouse clicks, admin, mock at ~280 ms latency)

| Step | Clicks | Notes |
|---|---|---|
| Plan run | 3 + 3 typed fields | +1 to save send date/deadline |
| Pick candidates | 3 + N | N=7 → 10; +1 confirm if any flagged |
| Announcement letter | 3 | hop to Letters and back |
| Dry-run then real send | 9 | measured |
| Mark 10 motivations | ~20 | no bulk (M1) |
| Institute letter | ~4 | course not shown on list row (H4) |
| Settlement letter | ~6 | from dashboard the wrong course opens (H1) |
| Level 3 request | ~4 | |
One 10-person run end to end: roughly 55–65 clicks plus ~12 typed fields.

Dangerous paths: double-click send = 1 POST (OK); browser Back after send = leaves the run page, no duplicate (OK); 500 / 502-html / offline = Persian, actionable message, input kept (OK); session expiry = H3; viewer = M8.

## Scorecard (0–5)

| Area | Score | Why |
|---|---|---|
| Task success | 3.0 | All steps work; wrong-course deep link (H1), no email preview (H4), duplicate-send risk (H5), no bulk marking (M1) |
| Accessibility | 3.5 | Strong focus/dialog/live-region/contrast work; ARIA misuse (M11), dashboard fails 200 % text (H2), targets < 44 px (M10), session loss (H3) |
| RTL / Persian | 4.0 | Logical layout, correct Jalali maths, digits handled, bidi islands good; Gregorian year accepted (M3), id-digit inconsistency (M13) |
| Visual polish | 4.0 | Confident yellow/ink system, consistent cards/tables/chips, good dark theme; small inconsistencies (kv alignment, disabled primary) |
| Responsiveness | 4.0 | No overflow 1440→360, drawer nav, sticky-column tables; dashboard fails at 320 px / 200 % text |

## What I could not test
- The real backend (mock only): real error envelopes, Excel/IFS/SMTP behaviour, actual e-mail rendering, .docx output and its RTL/digit fidelity.
- Real Irancell logo (none in repo); print/PDF of letters.
- Screen readers (NVDA/JAWS/VoiceOver/TalkBack) — only axe and DOM/focus inspection; real phones/touch; Firefox/Safari; real browser zoom (emulated via viewport size and root font size).
- 401/500/offline were simulated by wrapping `Response` in the page (the mock has no failure switch); real cookie expiry and CSRF rotation are untested.
- 3,000 rows / long names were injected by rewriting the mock seed in flight (source untouched); server-side paging with thousands of enrollments/runs not exercised.
- Inline-edit rollback/undo on a failing PATCH, connectors save/test with secrets, Admin user-create validation, audit filters, automation settings form (only opened/screenshotted).
- Persian keyboard layouts/IME composition and Excel clipboard HTML (plain pasted strings only).


## Developer response

Verification: QA scripts re-run against the fixed mock build (copies in `frontend/qa-rerun/`, outputs there; the QA evidence in `qa/uiux/` is untouched): sweep = no console errors, no horizontal overflow, axe 0 violations; j2/j3/j9/j12/j13/j14 re-checked (j1, j2, j3, j12 needed small edits because the flows changed by design: institute is now a picker, dry-run defaults ON, import asks for confirmation). `npm test` (unit/component + live adapters) and `npm run build` pass.

| ID | Status | Note |
|---|---|---|
| H1 | Resolved | every dashboard CTA carries `run=`; Letters never preselects a course and shows the chosen course above the preview (j14, test) |
| H2 | Resolved | chips wrap; no overflow at 200 % text, 320 px, 400 % zoom (j9) |
| H3 | Resolved | `?next=&expired=1`, Persian message, drafts in sessionStorage, returns to the same screen with input restored (browser-verified). Not covered by drafts: inline enrollment edits (optimistic + rollback instead) and search boxes |
| H4 | Resolved | dialog shows number/course/subject/attachment/body preview/recipient checkboxes; Letters list has a course column; confirm names course + count |
| H5 | Resolved | per-recipient «قبلاً در تاریخ … ارسال شده», unchecked by default, dry-run ON if first send or anyone already mailed, extra repeat-delivery warning |
| M1 | Resolved | row selection + bulk «بله/خیر» with confirm and a single undo |
| M2 | Resolved | select-all skips flagged, count shown, explicit include-flagged switch, names listed in confirm |
| M3 | Resolved | window 1300–1500, Gregorian year refused with converted suggestion, compact 8 digits accepted |
| M4 | Resolved | month/day/year specific messages; amount parser accepts separators/units/Persian digits, rejects fractions/negatives with reasons |
| M5 | Resolved | hint uses the parsed value; invalid values get field errors before any request |
| M6 | Resolved | per-step help and a primary «برو به انتخاب کاندیدا» on the plan step |
| M7 | Resolved | neutral until touched/submit; «N فیلد باقی مانده» beside the disabled button |
| M8 | Resolved | route-level guard + hidden nav for viewer (`#/connectors`, `#/import-export`, `#/admin`) |
| M9 | Resolved | Letters state follows `route.query` |
| M10 | Partly | 44px hit areas: sort buttons, in-table links, switches, checkbox labels; the native checkbox box itself stays 22px inside a 44px label. The pre-fix sweep list was re-checked only partially after the last CSS tweak |
| M11 | Resolved | axe: 0 violations on all screens/themes/widths |
| M12 | Resolved | per-row aria-labels «CTA: title», «مشاهدهٔ همهٔ N مورد» links; over-3 items are per ticket |
| M13 | Resolved | `Ident` (Latin, mono, LTR) for employee no., tickets, letter numbers, emails |
| L1 | Resolved | first invalid field is focused after a failed submit (dialogs and forms) |
| L2 | Resolved | toasts cleared on navigation and suppressed after session expiry; send failure reported once (in the dialog) |
| L3 | Partly | arrow keys move between steps and the panel is no longer `aria-live`; the stepper is still 7 tab stops |
| L4 | Resolved | progress resets on failure; import asks for confirmation stating the consequence |
| L5 | Partly | «برگزار‌شده / لغو‌شده» now use ZWNJ like the other labels; not every string audited |
| L6 | Partly | dry-run result says «بررسی شد، چیزی ارسال نشد»; course/run and candidate/participant vocabulary left as is |
| L7 | Resolved | hint under date fields removed (placeholder only) |
| L8 | Resolved | disabled primary is neutral with a dashed border |
| L9 | Resolved | demo hint uses bidi-isolated code spans |
| 360 px Admin role chip | Partly | role is now a select in a horizontally scrolling table (sticky name column); it can still sit at the scroll edge at 360 px |
| Wordmark «M» tile | Not resolved | documented placeholder, no logo asset available |
