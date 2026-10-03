# TMS — UX benchmark, expert review and design specs

Author: senior UX researcher/reviewer agent · 2026-10-03 · scope: `/home/user/training` (Persian-first RTL SPA for Irancell Talent Development).

**Reviewed build.** Commit `5c22f82` plus the uncommitted working tree as it stood between 07:20 and 07:40 UTC. Other agents were editing the tree while this review ran (the «موتیویشن» rename, `/templates`, `/dashboard/widgets`, `/me/dashboard-layout`, `/me/preferences`, `screens/Courses.tsx` all appeared during the session). Every finding says whether it is present at HEAD, in the working tree, or both. Prod builds of the tree were made to `/tmp` (the repo `dist/` was not touched); evidence, scripts and small PNGs are in `qa/uiux2/` (`lib.mjs` shared helper, `cls2.mjs`/`jump.mjs`/`journey.mjs`/`slow.mjs`/`virt.mjs` page-jump probes, `audit.mjs` role×width×theme×route sweep with axe, `keys.mjs` real-Tab test, `shots/` screenshots, `audit-*.jsonl` raw results).

---

## 1. Executive summary

**Page jump (complaint 1) — root cause.** There is no polling, timer or refetch loop anywhere: `grep` finds no `refetchInterval`/`setInterval` in `frontend/src`, `main.tsx:17` sets `refetchOnWindowFocus:false`, and 20–40 s idle probes on every screen (mock dev, mock prod, real backend dev, real backend prod) recorded **0 layout shifts, 0 API calls, 0 DOM mutations**. The jumps are *event-driven by data arriving into a frame of the wrong size*, and one of them is a real scroll defect:

1. **Virtualised Employees table re-measures while you scroll** — `components/DataTable.tsx:28` uses a fixed `estimateSize: () => 52` and never calls `measureElement`, but real rows are 79 px (two-line name+division cell). In a 40-step scroll the scroll container's `scrollHeight` changed 18 times (5027→5108→5189→5162→…) in mock and 19 times on the real backend. The scrollbar thumb and rows visibly jiggle. `screens/Employees.tsx:36` virtualises a page that is only 100 rows, so the virtualiser buys nothing. **Fix: delete `virtualize` there** (or add `measureElement` and `estimateSize: 80`).
2. **Skeleton frame ≠ content frame** (cold load, every time the cache is empty): Dashboard CLS **0.22–0.25** (skeleton card 185 px → loaded 250–344 px, pushing the «کارهای خودکار» card down 159 px; `Dashboard.tsx:34-35`), Connectors **0.28–0.32** (a 370–424 px card collapses; `Connectors.tsx:101-114`), Enrollments cold load **0.42** on the real backend (6 skeleton rows of 52 px → 25 rows of 105 px, then the pager appears; `Enrollments.tsx:30`, `DataTable.tsx:67`). Google's "good" threshold is ≤ 0.1.
3. **Content swaps that resize the page under the user's hands**: Letters live preview (`Letters.tsx:54,100`: each field edit swaps the preview HTML; the «نامه‌های ساخته‌شده» table jumps, CLS 0.04 per edit), Run-detail step panel (247 → 416 px when you click another step; `Runs.tsx` `StepPanel`), Runs search typing/clearing (0.04–0.07, `placeholderData` keeps old rows but pager/rows change height).
4. Minor: `font-display: swap` for five weights fetched at first paint (≈0.005 + a 0.01 «HTML 8→900» shift when `#root` fills).

The owner's "every few seconds" is therefore the cadence of navigating/filtering plus Employees scrolling, amplified in mock mode by an artificial 280 ms ±40 % latency (`api/mock/server.ts:29,397`). **Question for the owner:** which screen were you on when you saw it, and was it while scrolling the employee list?

**Top findings (full ranked list in §5).** (1) Dashboard "see all" link `?status=planned` returns 0 rows while the card says 3 (live data: runs are `announced`) — wrong number + dead end; (2) real-backend Level-3 dashboard rows are English names/courses with no `run_id`, so the CTA opens the letter form with **no course** (`wire.ts:89`; backend `dashboard.py` `level3_list`); (3) real-backend automation messages are English with Gregorian ISO dates on Dashboard and Automation (`automation/rules.py:47`); (4) at HEAD there is **no course catalog** and the nav calls the runs list «دوره‌های آموزشی» — course vs run is conflated (a `Courses.tsx` is appearing in the working tree); (5) letters/e-mails have **no user templates UI** (backend `/templates` exists, nothing consumes it), signatures English in 5 of 7 wording blocks at HEAD; (6) no tutorial at all; (7) two starting points on Import («شروع درون‌ریزی» ×2), Automation, Connectors (4× primary save); (8) Enrollments rows are 105 px tall with four native selects each (25 rows ≈ 2 600 px) and Import/Run-detail/Automation each show two primary buttons; (9) 404/forbidden pages have no `h1`, and `heading-order` fails on the filtered runs empty state; (10) status chip «در حال برگزاری» is a yellow fill on a non-actionable thing (breaks the accent rule).

**Good news (so findings read in proportion).** axe-core: 0 colour-contrast violations in light *and* dark across 13 routes × 3 roles × 4 widths (312 loads); no horizontal overflow at 1440/1024/768/390; no console errors or 4xx; real-Tab test: every stop shows a focus ring and dialogs return focus to the opener; the in-app digit law is respected in prose.

**Backlog headline** (§8): P0 jump fixes (S, frontend), P0 dashboard link/Level-3 data fixes (S, core+frontend), template editor (L, frontend; backend largely done), editable dashboard with charts (L, frontend; backend largely done), tutorial (M, frontend), nav regroup + «انتقال اطلاعات» tabs (M, frontend), Persian signature everywhere (M, integrations).

---

## 2. Sources

**Method and honesty note.** `WebFetch` was blocked by the egress proxy for most vendor documentation hosts (`help.sap.com`, `learning.sap.com`, `help.docebo.com`, `doc.workday.com`, `www.metabase.com` → `EGRESS_BLOCKED`; `curl` to the same hosts also failed). `github.com` pages were fetchable. Therefore:

- **[V-fetch]** = I read the page myself (GitHub READMEs).
- **[V-search]** = the claim is in the search tool's summary of the cited vendor URL; I could not open the page. Treat as "reported by search result", wording is paraphrased.
- **[R]** = recalled from general knowledge, *not* verified here. Used sparingly and always tagged.

| # | Source | Used for | Evidence |
|---|---|---|---|
| S1 | https://help.sap.com/docs/SAP_SUCCESSFACTORS_LEARNING/5fae31b1299d4033b665edabea7b9087/d97f83661d7b486cb6518b026b36e132.html (Adding System Tiles) and https://learning.sap.com/learning-journeys/exploring-sap-successfactors-platform/navigating-admin-center-tiles-and-favorites_d2092d55-04df-482e-bcc4-fa99f498d9a4 | SF home = configurable tiles; tile catalog + custom tiles | V-search |
| S2 | https://learning.sap.com/courses/sap-successfactors-learning-academy/configuring-class-settings-1 ; https://help.sap.com/docs/successfactors-learning/managing-sap-successfactors-learning-for-administrators/setting-approval-process-for-enrolling-into-course | class = dated instance of a course, min/max enrollment, approval before enrollment | V-search |
| S3 | https://help.sap.com/docs/successfactors-learning/managing-learning-notification-templates/sap-successfactors-learning-email-notification-messages ; https://help.sap.com/docs/SAP_SUCCESSFACTORS_LEARNING/6e419ace29644057ac39ea5ab1d0261d/7259ab417c3e42ed9dfc71d4eb5d9c1b.html (Legacy Notification Template Editor) | token placeholders in templates; Admin → System Administration → Manage Email → Email Notification Templates; HTML support; a "legacy" editor exists | V-search |
| S4 | https://help.csod.com/help/csod_0/Content/ILT/ILT_Sessions/Create_Session_Details.htm ; https://help.csod.com/help/csod_0/Content/ILT/ILT_Events/ILT_Scheduling_Wizard.htm ; https://help.csod.com/help/csod_0/Content/ILT/ILT_Events/ILT_Event_-_Create/ILT_Event_-_Create_-_Step_5_-_Session_Defaults.htm | Cornerstone ILT events/sessions, scheduling wizard, session defaults (pre-approve), required training/completion approvals | V-search |
| S5 | https://help.docebo.com/hc/en-us/articles/360020081040-Managing-the-Admin-dashboard ; https://help.docebo.com/hc/en-us/articles/17962038195986-Creating-and-managing-custom-dashboards ; https://help.docebo.com/hc/en-us/articles/360020127159-List-of-widgets-for-custom-widget-pages | Docebo admin dashboard, widgets drag/arrange, Insights custom dashboards (add visuals, resize, move, filters, Advanced Insights) | V-search |
| S6 | https://help.docebo.com/hc/en-us/articles/22129375193362-Shortcodes-in-notifications ; https://help.docebo.com/hc/en-us/articles/29547314721938-Customizing-the-notification-message ; https://help.docebo.com/hc/en-us/articles/29346173660050-Notifications-in-different-languages | `{{course_name}}`-style shortcodes as clickable chips inserted at cursor in subject/body; set depends on event; HTML source toggle; per-language notifications | V-search |
| S7 | https://doc.workday.com/workday-education/en-us/course-manuals/learning-for-administrators/manage-learner-enrollment.html ; https://doc.workday.com/workday-education/en-us/course-manuals/learning-for-administrators/administer-learning.html | Workday Learning Admin dashboard (create/manage enrollments, waitlist), "Enroll in Content" business process with approval steps/skip approvals, custom notifications, Maintain Dashboards | V-search |
| S8 | https://totara.help/docs/course-notification-placeholders ; https://totara.help/docs/course-reminders | Totara placeholders `[coursename]`, `[firstname]`, `[managername]`, `[course:full_name]`…, reminders with manager escalation | V-search |
| S9 | https://help.talentlms.com/hc/en-us/articles/9651467334044-How-to-work-with-notifications-in-TalentLMS ; https://help.talentlms.com/hc/en-us/articles/9651467253660-How-to-customize-the-default-system-emails-in-TalentLMS ; https://help.talentlms.com/hc/en-us/articles/18895897930268-How-to-work-with-the-dashboard-widgets | event dropdown incl. instructor-led, rulesets (time/recipient), smart tags in `{curly}` braces; dashboard-widgets article exists (content not seen) | V-search |
| S10 | https://support.absorblms.com/hc/en-us/articles/50813756024851-Admin-Hub ; https://support.absorblms.com/hc/en-us/articles/360046026173-Add-Admin-Dashboard ; https://support.absorblms.com/hc/en-us/articles/1500006359441-Message-Templates | Admin Hub: role-based starting dashboards, widget gallery, global filters, share; ≤ 10 widgets; message templates with `{{FirstName}}` fields; Session Reminder fields | V-search |
| S11 | https://support.360learning.com/hc/en-us/articles/9975805218068-Navigate-the-web-platform ; https://support.360learning.com/hc/en-us/articles/37741343892244-Create-and-share-a-custom-path-dashboard ; https://360learning.com/product/learning-management-system/ | analytics on home and group pages, custom dashboards shareable, Session Builder dynamic enrollment audiences, notification trigger table (email/Slack/Teams) with activate/deactivate | V-search |
| S12 | https://knowledge.hubspot.com/marketing-email/use-personalization-tokens ; https://knowledge.hubspot.com/conversations/how-do-i-add-personalization-tokens-to-a-template-or-snippet | "Personalize" toolbar dropdown → Token → property, **default value** for empty, preview personalization; `{{contact.firstname}}` in coded templates | V-search |
| S13 | https://downloads.mailchimp.com/guides/MailChimp_MergeTags.pdf ; https://mailchimp.com/help/use-merge-tags-to-send-personalized-files/ | Merge Tags dropdown in text-block toolbar, `*\|FNAME\|*` tags | V-search |
| S14 | https://support.microsoft.com/en-us/office/create-reuseable-text-blocks-for-email-messages-8fb6c723-c960-4c8c-9790-3e43ddc4b186 ; https://support.microsoft.com/en-us/word/quick-parts | Outlook My Templates side pane (title + text, click to insert), Quick Parts type-name-then-Enter | V-search |
| S15 | https://www.notion.com/help/keyboard-shortcuts ; https://github.com/timc1/kbar ; https://www.storylane.io/tutorials/how-to-use-linears-command-menu | `/` typeahead block menu (Notion); Ctrl/Cmd+K context-aware command menu showing shortcuts (Linear) | V-search |
| S16 | https://www.metabase.com/docs/latest/dashboards/introduction ; https://github.com/metabase/metabase/blob/master/docs/dashboards/introduction.md | pencil → edit mode, grid appears, snap, drag, resize by bottom-right handle, move card between tabs, filters connect to cards | V-search |
| S17 | https://docs.mixpanel.com/docs/boards | Boards: Add button, handle icon to drag, resizable cards, text/media cards | V-search |
| S18 | https://cloud.google.com/looker/docs/studio/create-a-responsive-report | Looker Studio edit mode, bounding box with handles, responsive layout = 12-column grid snapping | V-search |
| S19 | https://www.appcues.com/blog/product-tours-walkthroughs-ultimate-guide ; https://userpilot.com/blog/onboarding-tour/ ; https://flook.co/blog/posts/product-tours | tour + persistent checklist pattern, 3–5 cards, segment by role, one action + one reason per step, re-accessible | V-search (vendor blogs: marketing-grade evidence) |
| S20 | https://github.com/shepherd-pro/shepherd | Shepherd.js: **AGPL-3.0 for OSS/non-commercial, paid commercial licence otherwise**; React/Vue/Angular/vanilla | **V-fetch** |
| S21 | https://github.com/kamranahmedse/driver.js | driver.js: MIT, zero deps, ≈5 kB gz, "everything is keyboard-controllable" | **V-fetch** |
| S22 | https://github.com/clauderic/dnd-kit | dnd-kit: MIT, pointer/mouse/touch/**keyboard** sensors, default ARIA attributes, customisable screen-reader instructions and live regions, sortable | **V-fetch** |
| S23 | https://github.com/react-grid-layout/react-grid-layout | RGL v2: draggable/resizable, responsive breakpoints, used by Grafana, Metabase, HubSpot, Kibana, BitMEX (README). README as fetched states no keyboard-accessibility feature and no licence text | **V-fetch** |
| S24 | https://github.com/ueberdosis/tiptap ; https://github.com/facebook/lexical | Tiptap: MIT headless editor on ProseMirror, extension model (paid "Pro" extensions exist); Lexical: MIT, accessibility-minded, plugin architecture, custom nodes | **V-fetch** |
| S25 | Local evidence: `docs/*.md`, `frontend/src/**`, `backend/app/**`, `qa/uiux2/**`, `/home/user/Salary/.claude/skills/ui-ux-review/SKILL.md`, `/dataviz` skill palette validator | review of this product | V-local |

---

## 3. Benchmark matrix

Cell legend: `[V]` verified via search summary of a cited vendor URL (S-number), `[R]` recalled, `—` not verified (do not read as "absent"). Columns are the six jobs of a learning admin; the last row is **this team's need**.

| Product | Admin dashboard | Catalog / session management | Enrollment / approval | Notification & e-mail templates | Reporting | Onboarding |
|---|---|---|---|---|---|---|
| **SAP SuccessFactors Learning** | Home built from **tiles**; admin sets the default home from a tile catalog or custom tiles [V S1] | A *class* = dated instance of a course; creating one adds it to the calendar, assigns resources, opens registration [V S2] | min/max enrollment; optional **approval process before enrollment** [V S2] | Templates with **tokens** filled at send time; path Learning Admin → System Admin → Manage Email → Email Notification Templates; HTML supported [V S3]; a "Legacy Notification Template Editor" still exists — i.e. two editors coexisting [V S3] | — | — |
| **Cornerstone OnDemand** | — | Events → Sessions under Admin > Tools > Learning > Catalog Management; **scheduling wizard**; session defaults [V S4] | session defaults can **pre-approve** registration; approvals required counted at LO level, overriding user record [V S4] | Correspondence templates exist [R]; not verified | — | — |
| **Docebo** | Admin dashboard under Data and analytics; widget pages; **Insights custom dashboards**: add visuals, resize/move, filters, Advanced Insights toggle [V S5] | — | — | **Shortcodes** `{{course_name}}`, `{{first_name}}` as **chips you click to insert at the cursor** in subject *and* body; set depends on notification event; HTML source toggle; per-language [V S6] | Insights / report export XLS/CSV/HTML [V S5] | — |
| **Workday Learning** | Learning Admin dashboard of worklets (create, manage enrollments/waitlist); "Maintain Dashboards" [V S7] | — | **Enroll in Content** business process with configurable approvals, skip-approval flag [V S7] | Workday "recommends configuring custom notifications" for status [V S7] | — | — |
| **Moodle Workplace / Totara** | — | — | reminders/escalations to the learner's manager [V S8] | **Placeholders** `[coursename] [firstname] [managername] [days counter]` in reminders; course placeholders `[course:full_name]` [V S8]. Moodle Workplace specifics not verified | — | — |
| **TalentLMS** | dashboard widgets article exists [V S9, content unseen] | — | — | Pick **event** from dropdown (incl. instructor-led), then rulesets (time, recipient); `{course_name}` smart tags [V S9] | — | — |
| **Absorb LMS** | **Admin Hub**: role-based starting dashboards, visual widget gallery, global filters, sharing; **max 10 widgets** per dashboard [V S10] | — | — | Message templates with `{{FirstName}}` auto-fields; Session Reminder fields (name, link, location, start/end, time, address) [V S10] | widgets are graphs, messages, lists [V S10] | — |
| **360Learning** | analytics on home and group pages; shareable **custom dashboards** [V S11] | **Session Builder** with dynamic enrollment audiences [V S11] | rule-based enrollment [V S11] | Table of every notification trigger (email/Slack/Teams) with category + recipient role, searchable, switch on/off [V S11] | custom reports [V S11] | — |
| **HubSpot** (template editor ref.) | — | — | — | Toolbar **Personalize → Token → property**, mandatory-feeling **default value**, preview personalization [V S12] | — | — |
| **Mailchimp** | — | — | — | **Merge Tags** dropdown in the text-block toolbar [V S13] | — | — |
| **Outlook** | — | — | — | **My Templates** pane: list, click inserts; **Quick Parts**: type name + Enter [V S14] | — | — |
| **Notion / Linear** | — | — | — | `/` typeahead inserts blocks, filters as you type [V S15]; Ctrl/Cmd+K context-aware command menu that **shows shortcuts beside each entry** [V S15] | — | — |
| **Metabase / Mixpanel / Looker Studio** (widget-grid ref.) | explicit **Edit** mode; grid appears; snap; drag; resize by corner handle; cards movable between tabs [V S16]; drag by handle icon [V S17]; selection box + 12-col responsive grid [V S18] | — | — | — | filters bound to cards [V S16] | — |
| **Intercom / Appcues / Userpilot / Shepherd / driver.js** | — | — | — | — | — | Tour (3–5 cards) **plus** persistent checklist; segment by role; re-accessible [V S19]. Shepherd is AGPL/commercial [V S20]; driver.js MIT 5 kB [V S21] |
| **TMS today (HEAD)** | 4 action-lists + 1 due list; no charts, no layout choice | runs list only, **no course catalog** | inline select per row, bulk motivation | **none** (6 fixed letter kinds, per-field overrides only) | none | none |
| **TMS need (HR coordinator, 5–30 runs, hundreds of enrollments)** | personal, glanceable, *actionable*: what is late/at risk today | course ≠ run, run is the unit of work | batch motivation + at-risk follow-up | reusable user templates with field chips, Persian signature | per-run and monthly numbers, export | first-run checklist that works on real data |

**Reading the matrix.** The learning-admin suites (SAP, CSOD, Workday) bury the coordinator's job under generic admin trees; the recurring *good* ideas are small and transferable: chips/tokens at the caret (Docebo), event-dependent field sets (Docebo), a default value for empty fields (HubSpot), role-based starting dashboard (Absorb), explicit edit mode with grid snap (Metabase/Looker), notification table with on/off (360Learning), tour + checklist (S19).

---

## 4. Patterns to adopt, and anti-patterns to avoid

### Adopt

| # | Pattern | Evidence | How it lands in TMS |
|---|---|---|---|
| A1 | **Field chips inserted at the caret from a searchable picker; field set depends on template kind** | Docebo S6, HubSpot S12, Mailchimp S13 | §6.2: picker grouped by source; kind-aware availability; `{{`/`/` triggers (Notion S15) |
| A2 | **Default for an empty field** (HubSpot) | S12 | chip menu «مقدار پیش‌فرض / اختیاری»; backend already has `{{key?}}` optional syntax |
| A3 | **Preview with sample data, then with a real run** | HubSpot "preview personalization" S12 | §6.2 live preview, context sample/real |
| A4 | **Explicit Edit mode with visible grid and snap**, not always-draggable widgets | Metabase S16, Looker S18 | §6.1 «شخصی‌سازی» mode; read mode has no drag affordances so nothing moves by accident |
| A5 | **Role-based starting dashboard + reset to default** | Absorb S10 | one default for HR coordinator, one for admin; «بازگشت به پیش‌فرض» |
| A6 | **Cap the widget count** (Absorb: 10) | S10 | catalog is 14 widgets, each at most once; the drawer disables placed ones |
| A7 | **Drag by an explicit handle; resize by a corner handle** | Mixpanel S17, Metabase S16 | plus keyboard equivalents (dnd-kit sensors S22) — the references are mouse-first, TMS must not be |
| A8 | **Notification/trigger table with on/off and recipient role** | 360Learning S11 | Automation screen: one row per automatic e-mail with template picker and switch |
| A9 | **Approval/pre-approval as per-session default** | CSOD S4 | not needed now; note for later (line-manager approval batches) |
| A10 | **Tour + persistent checklist, 3–5 cards per tour, role-segmented, replayable** | S19 | §6.3 |
| A11 | **Own the tour component** (no AGPL, no CDN, RTL control, CSP `script-src 'self'`) | Shepherd AGPL S20; driver.js MIT S21 as fallback | ~250 lines of in-repo React |
| A12 | **Command-style shortcuts shown next to the action** | Linear S15 | field-picker rows and the help menu list their shortcut |

### Anti-patterns (seen in the references or already in TMS)

| # | Anti-pattern | Where | Rule for TMS |
|---|---|---|---|
| X1 | Two template editors coexisting ("legacy") | SAP S3 | one editor; system templates read-only + «ساخت نسخهٔ قابل ویرایش» |
| X2 | Deep admin paths (Admin > Tools > Learning > Catalog Management > Events and Sessions) | CSOD S4 | ≤ 2 clicks from nav to any daily task; the run page is the hub |
| X3 | Always-draggable dashboards | common | edit mode only |
| X4 | Mouse-only drag/resize | S16–S18 describe mouse gestures only | every move/resize has a keyboard path and a menu path |
| X5 | Generic "records" empty states | TMS Employees etc. | every empty state names the next action (SKILL §4) |
| X6 | Token syntax the user must memorise (`*\|FNAME\|*`, `[course:full_name]`) | Mailchimp, Totara | users never type braces; chips show Persian labels (raw key only in a tooltip) |
| X7 | Colour-only meaning, accent on non-actionable things | TMS status chip yellow | accent only on what you can act on (SKILL §9ب) |
| X8 | A tour that blocks the app or hard-depends on a CDN | S19 warns about length | non-modal, skippable, local |
| X9 | Auto-refreshing widgets that re-flow the grid | — | refresh swaps data inside a fixed frame (§6.1) |

---

## 5. Findings, ranked by what they cost the user

Ranking: **A** wrong number / wrong object (user acts on bad information) · **B** doesn't work / dead end / unreachable · **C** friction · **D** polish. `file:line` are as of review time; files were being edited, so the *symbol* is given too. "Live" = real backend (`demo --reset` DB in `/tmp/uiux2/live`, uvicorn :18791/:18792); "mock" = `dev:mock`/mock build. Role is admin unless stated.

### A — wrong number or wrong object

**A1. Dashboard "see all" link and card count disagree (live).** Screen: Dashboard cards «دوره‌های شروع‌نشده», «پرداخت آغاز نشده». Repro (live): card shows ۳; `CARDS[0].all = "/runs?status=planned"` → `GET /runs?status=planned` returns **0** (the three runs are `announced`; `status=announced` → 3). «پرداخت آغاز نشده» shows ۳ but `…/runs?status=completed` returns **2** (the list includes the `running` run). The link is only rendered when count > 4, so the demo hides it; real data will not. Also the card's hint «برنامه یا کاندیدای این دوره‌ها هنوز کامل نیست» is false for an announced run with 12 enrolled. Rule: SKILL §2 "a total shown with the set behind it", §4 empty state ≠ dead end. Source: `screens/Dashboard.tsx` `CARDS` (lines 17-21), backend `api/services/dashboard.py` (`not_started_courses`, `payment_not_started`). Fix: dashboard returns `{count, items, drilldown:{path, query}}` built by the same server query that made the count; UI uses `drilldown` verbatim; rename card «دوره‌های پیش‌رو بدون تکمیل» with a hint that matches the rule (see §6.1 `runs_at_risk`).

**A2. Level-3 rows are English and their CTA has no course (live).** Dashboard «سررسید ارزیابی سطح ۳»: title «Reza Nova1», detail «Effective Communication - Batch A» (IDP English summary). `api/wire.ts:89` sets `run_id: null`, so «درخواست ارزیابی» opens `#/letters?kind=level3_request` with **no run** (Letters never preselects; the user must choose a course from a 100-item select — the original QA H1 wrong-course class). The backend item `{enrollment_id, ticket, emp_no, employee_name, course_name, end_date, days_since_end}` has no `run_id`, no Persian name, no course id. Screens: Dashboard (live only; mock data is Persian, which is why mock QA missed it). Fix (core): add `run_id`, `employee_name_fa`, `course_name_fa`; (frontend) pass `&run=`.

**A3. English server text and Gregorian dates in a Persian UI (live).** Dashboard «کارهای خودکار سررسیدشده» and Automation list print «LMS-700000: course ended 68 days ago (>= 60), Level…» and ISO dates `2026-07-25`, `2026-09-03`, `2026-09-28` (audit: Latin-digit and Gregorian detectors fire on `/` and `/automation` at all widths, both themes). Source: `backend/app/automation/rules.py:47` builds the message in English; `wire.ts:96-99` forwards it. Rules: SKILL §1 digit law, §3 Jalali everywhere. Fix (integrations): messages are structured `{kind, params}`; the SPA owns the Persian sentence («۶۸ روز از پایان دورهٔ «…» گذشته است») and formats dates with `fmtJalali`.

**A4. Wrong-run risk in the Letters picker.** `screens/Letters.tsx` run `<select>` label = «نام دوره — تاریخ شروع» with no institute, no type, 100 runs max, unsearchable; two runs of one course starting the same week are indistinguishable. Run detail title (`Runs.tsx` `RunDetailScreen` `PageHead title={r.course_name_fa}`) has the same ambiguity. Fix: label «مدیریت زمان · ۲۸ مهر ۱۴۰۵ · Demo Academy · حضوری», combobox with search, preselect from `?run=`, and a pinned banner above the preview naming the chosen run.

**A5. Signature is Persian only in the renderer, not in the product.** (Complaint 6.) At HEAD the sign-off is English in `documents/wording.py` (EN blocks at lines 71, 140, 171 `"Best regards," "Talent Development Team" "Human Resources"`; settlement letter line 181 `{{signer_name}} {{signer_title}}`), defaults `documents/specs.py:44-45`, `templates/letter_defaults.example.json:6-7`, and the field catalog sample (`/templates/fields` returns «Talent Development Team»). The working tree already moved the four Persian-language kinds to `signer_name_fa/signer_title_fa/unit_fa/department_fa` (+ `[[SIGNATURE_IMAGE]]`) — but **no UI or settings endpoint feeds those keys**: `grep signer_name_fa backend/app/api schemas` finds only `field_catalog.py`; `Automation.tsx:61-64` still edits `letter_signer_name/title/email/phone`. With `hide_if_empty` the new Persian lines silently vanish → a letter with *no* signature. The settlement letter (English-only kind) and every EN section remain Latin. Fix: §6.2 «امضای پیش‌فرض» form feeding all five Persian keys; owner decision needed on EN sections (see §9 questions).

### B — doesn't work / dead end / unreachable

**B1. No course catalog; course vs run conflated (complaint 3).** At HEAD there is no screen for courses: nav item «دوره‌های آموزشی» (`routes.tsx` NAV) is the **runs** list; `api.courses` is used only to fill a flat, unsearchable `<select>` in `NewRunDialog` (`Runs.tsx:64-75`, 200 max); `createCourse/updateCourse` exist in `api/client.ts:190-191` with **no UI**, so a course that is not already in the DB cannot be added. The run page's `h1` is the course name. A `screens/Courses.tsx` (catalog, runs-per-course, «برگزاری جدید») appeared in the working tree at 07:34; it is not yet routed/reviewed. Audit of the **runs list** as shipped (`Runs.tsx` `RunsScreen`):
- columns: دوره، نوع، مؤسسه، شروع، پایان، وضعیت، «ثبت‌نام / تأیید». Missing: **days to start** (backend sends `days_to_course`), **progress** (a bare «۶ / ۱۳» pair; header order vs RTL display is ambiguous), **next action** («نامهٔ مؤسسه ساخته نشده»), MTC no., category. Counts showed «—» at HEAD against the real backend (`counts_known=false`); backend round 4 added `participants/motivations_yes`, the live screenshot now shows counts.
- **no total** («۶ دوره»), no result count under filters; pager only when > 15.
- sort: only type/start/end/status are sortable (`enableSorting:false` on course, institute, counts); **no filter by course, institute, or "upcoming / needs action"**; default sort `-start_date` puts the *furthest-future* run first and gives no "today" anchor.
- **state is hard to read**: status chip «در حال برگزاری» is a **yellow fill** (`chip--brand`, `components.css:50`) — the accent colour on a non-actionable thing — while announced is blue and completed green; there is no indication of *which workflow step* (7-step stepper) the run is on.
- duplicates: none in demo data; but no run identity (course + institute + date) is shown anywhere as one string (A4).
- dead ends: dashboard card links (A1), empty-state for filters offers «پاک کردن فیلترها» but the status filter has no «شروع‌نشده» option matching the dashboard's definition.
Fix: §6.4 IA (کاتالوگ دوره‌ها ▸ برگزاری‌ها ▸ صفحهٔ برگزاری) and the list columns in §6.4.

**B2. No user-created templates for e-mails/letters (complaint 5).** `screens/Letters.tsx` offers six fixed kinds and per-field overrides; `EmailSendDialog` (`components/domain.tsx`) has a fixed body. The backend now has `/templates` CRUD, `/templates/fields`, `/templates/preview`, `:duplicate`, `:set-default`, versions, `:send-test`, and `template_id` on `/letters` and `/email/send` (CONTRACT_REQUESTS round 5) — **no frontend consumes any of it**. Spec: §6.2.

**B3. No tutorial / first-run help (complaint 7).** `grep -ri "tutorial|tour|onboard" frontend/src` → nothing. Backend `/me/preferences` already reserves `tutorial:{completed_steps[],dismissed,last_step}`. Spec: §6.3.

**B4. Dashboard is not editable and has no chart (complaint 2).** Four list cards + one due list (`Dashboard.tsx`). Backend `GET /dashboard/widgets`, `/dashboard/data`, `GET|PUT|DELETE /me/dashboard-layout` are in the working tree (a probe against a server started 07:3x returned 404 for the first and last — route registration lagged the code; re-check after restart). Spec: §6.1.

**B5. Import/Export: no history, no single entry point.** `ImportExport.tsx`: two parallel cards each with its own primary «شروع درون‌ریزی» (two starting points, SKILL §0), the legacy export hangs off the page header as «برون‌بری اکسل قدیمی…», and there is no list of previous imports (that lives in Connectors → sync runs, which `viewer` cannot see and which `hr` must discover). Screen is now titled «انتقال اطلاعات» (done in working tree) but verbs on buttons still say درون‌ریزی/برون‌بری (`ImportExport.tsx:32,49,50,68,75`). Spec: §6.4.

**B6. Forbidden/404 pages have no `h1`.** axe `page-has-heading-one` on `/nonexistent` and on `/connectors`, `/import-export`, `/admin` for the roles that cannot open them (viewer; hr on `/admin`) — `App.tsx:30-31` render `EmptyState` (an `h3`, `ui.tsx:37,48`) without `PageHead`. Same hard-coded `h3` gives `heading-order` (h1 → h3) on the filtered-runs empty state in live. Fix: `EmptyState` takes `as="h2"` and the guard renders an `h1`.

**B7. Focus is not moved to the page heading on screens that load data first.** `App.tsx:16-17` focuses `#page-title` on route change, but `RunDetailScreen` shows skeletons (no `h1`) at that moment, so keyboard/SR users get no page announcement there (screenshot `shots/liveprod-run-detail-1440-light.png` has no ring, the others do). Fix: focus when the `h1` mounts (`useEffect` in `PageHead` with `autoFocusOnMount`).

### C — friction

**C1–C7. The page jumps** — see §1 (root causes J1–J7) with file:line, measured CLS and the fix list in §7. Numbers: Employees scrollHeight changes 18/19 per 40 steps; Dashboard 0.22–0.25; Connectors 0.28–0.32; Enrollments cold 0.42; Letters preview 0.04/edit; run-step switch 0.04; Runs search 0.04–0.07.

**C8. Accent on non-actionable status** (`chip--brand` for «در حال برگزاری»; also yellow = the dry-run frame in `EmailSendDialog`, `domain.tsx:169`, which *is* actionable and fine). Use `info` tone + dot for "running".

**C9. Two starting points / many primaries** (measured `.btn--primary` count at 1440): Import ×2 («شروع درون‌ریزی» in each card); Run detail ×2 (`برو به انتخاب کاندیدا` in the plan panel and the active stepper step styled primary); Automation ×2 («اجرای همین حالا…» + «ذخیرهٔ تنظیمات»); Connectors ×4 (one save per connector card, acceptable if each card is a form — make them secondary). Viewer sees a disabled primary «ساخت نامه و شماره‌گذاری» on Letters.

**C10. Dashboard sync chips** read as faults («همگام‌سازی اکسل: هرگز» in a neutral chip on every load, on the page's title row); move to the `sync_health` widget with a clear "هنوز اجرا نشده — اتصال را تنظیم کنید" action (admin) or hide for hr/viewer.

**C11. Enrollments rows are 105 px tall with four native `<select>`s each** (motivation, registration, calendar, attendance) → 25 rows ≈ 2 600 px; scanning "who has not answered" requires reading every select. Show state as chips, edit in a row popover, keep bulk-select; default filter «موتیویشن: بدون پاسخ».

**C12. Theme toggle label shows the current state («خودکار») not the action;** sidebar foot has two ghost buttons of different shapes. Use a 3-option segmented control (روشن / تیره / سیستم) per SKILL §9ب.

**C13. Names with Latin digits in live data** («رضا نووا1» on `/employees`, `/enrollments`, `/runs/1`, `/runs/1/candidates`): the demo generator appends an index; verify with real IFS data whether `toFa` is applied to names (`wire.ts:29` applies it to `name_fa`, the screens evidently use another path). Low until reproduced with real data.

**C14. Nav grouping by entity, not job; 9 items today (the brief said 12; Courses and Templates will make 11).** Groups «کار روزانه / داده‌ها / سیستم» put «کارمندان» (a lookup) between daily work and import, and bury «مرکز نامه‌ها». Spec: §6.4.

### D — polish

- `h1` focus ring is a full-width pill around the title on keyboard navigation (intended; shrink with `outline-offset` and `inline-size: fit-content`).
- `font-display: swap` for 5 weights → preload Regular/SemiBold/Bold woff2 and add `size-adjust` fallback metrics (removes the 0.005–0.01 first-paint shifts).
- Mock latency 280 ms ±40 % makes mock look jumpier than prod; set to 80 ms for reviews.

### Checks that passed (so the next reviewer does not redo them)

axe 0 contrast violations in light/dark (3 roles × 13 routes × 4 widths mock; admin × 13 routes × 1440/390 × 2 themes live, run with `bypassCSP` because the axe injection trips `script-src 'self'` — that console error is a probe artifact, not an app bug); no horizontal overflow; no `pageerror`, no 4xx/5xx; real-Tab sweep (admin, light): 0 stops without a focus ring, Esc returns focus to «دورهٔ جدید»; `main` top = 0 (≥ 980 px) / 61 (topbar) — no empty band; checkbox hit area is 44×44 (`.hit` label wraps a 22 px input — not a defect); document titles per route; digit law for UI-built prose; Jalali dates for UI-built dates.

### Terminology: every «انگیزه‌نامه» → «موتیویشن»

At `5c22f82` there were **30 code/test/script lines in 10 files** (plus 2 in `docs/QA_UI_UX.md` and 12 in `qa/uiux/sweep-results.json`, both quoting the old UI) — list by `git grep` at HEAD:

| File:line | Context |
|---|---|
| `backend/app/api/services/automation.py:98` | reminder e-mail body «مهلت ثبت‌نام…» wording |
| `frontend/scripts/screenshots-flows.mjs:27` | selector `select[aria-label^="انگیزه‌نامه"]` |
| `frontend/src/api/mock/server.ts:123` | sample field label |
| `frontend/src/components/flows2.test.tsx:41,47,53,57,63` | role-name regexes |
| `frontend/src/components/flows3.test.tsx:77,78,82` | role-name regexes, «رد انگیزه‌نامه» |
| `frontend/src/lib/labels.ts:9,13,27` | step label «جمع‌آوری…», flag «سقف انگیزه‌نامهٔ تأییدنشده», due label |
| `frontend/src/screens/Automation.tsx:58` | setting label |
| `frontend/src/screens/Dashboard.tsx:20` | card title «بیش از ۳ انگیزه‌نامهٔ تأییدنشده» |
| `frontend/src/screens/Enrollments.tsx:21,60,88,97,101,102,108,109,118` | field label, toast, column, filter, bulk buttons, confirm, subtitle |
| `frontend/src/screens/Runs.tsx:117,144,145,162,170` | step help, validation messages, «مهلت انگیزه‌نامه», count line |
| `docs/QA_UI_UX.md:46,56` | historical QA text (leave; it quotes the old UI) |

**Working tree at 07:40: zero remaining in code**; guards exist (`backend/tests/core/test_templates_dashboard.py:594`, `backend/tests/integrations/test_custom.py:88`). Remaining checks: the identifier `motivation` in code/API stays English; the parenthetical «(Motivation Form)» in letters is intentional (it is the LMS form's real name).

### Digit law, Jalali, two-starting-points, empty states — results

- Digit law: UI-built prose clean on all screens (mock). Violations come from **backend text** (A3) and **data** (C13). Identifiers (tickets `LMS-…`, letter numbers `TD-1405/…`) correctly stay Latin in `.id` islands; their `aria-label`s contain Latin ids by design.
- Jalali: UI dates are Jalali; Gregorian only via A3.
- Empty states: all list screens carry title + hint + action except **Employees** (no import CTA for a fresh install — add «انتقال اطلاعات ▸ ورود فهرست کارمندان») and **Letters → «نامه‌های ساخته‌شده»** (`action: undefined`, `Letters.tsx` empty prop) — add «ساخت اولین نامه».
- Roles walked: admin, hr, viewer on all 11 routes + `/nonexistent` + `/runs?status=planned`; viewer is guarded on `/connectors`, `/import-export`, `/admin` (sentence + back button; no firing 403s) — only the missing `h1` (B6).

---

## 6. Design specs

Conventions used in all four specs: strings are final Persian copy; sizes are CSS px at the 15 px root; all numbers shown through `toFa`/`fmtNum` (Persian digits, `٬` thousands, `٫` decimals, percent as «۷۵٪»); identifiers (`LMS-…`, field keys, letter numbers) in `.id` (Latin, mono, `dir=ltr`); logical CSS properties only; every colour is a token; nothing animates under `prefers-reduced-motion`. **Backend status:** core already implements most endpoints named below (CONTRACT_REQUESTS round 5); each spec lists exactly what is still missing under *API gaps*.

### 6.1 Dashboard — editable, graphical

**Purpose.** An HR coordinator running 5–30 runs opens the dashboard to answer, in this order: *what is late or at risk today*, *where do I stand* (numbers), *what is coming*. Charts support those answers; they are not decoration. Every widget has a verb (a drill-down link) — SKILL §4 "next action is always visible".

#### Grid and frame
- 12-column CSS grid, `column-gap: 16px`, **row unit 64 px**, `row-gap: 16px`. A widget of height `h` units has `block-size: h*64 + (h-1)*16` px — **fixed**; content scrolls *inside* the widget (`overflow:auto`, focusable region) and never changes the frame. x = 0 is the **right** edge (native RTL grid placement; do not mirror numbers in code).
- Frame: card (`--surface`, 1px `--line`, radius `--radius-md`), header row 44 px (title `h2` 17 px/700, right; actions left: «⋯» menu), body padding 16 px. In edit mode the frame gets a dashed 2 px `--line-strong` outline and a handle bar (below).
- Max one instance per widget id (backend validates duplicates); max 14 widgets (catalog size; Absorb caps at 10 [V S10] but our catalog is the cap).

#### Widget catalog (ids = backend ids so the API needs no renaming)

Sizes are `w×h` in grid units (default / min / max). Role = minimum role that sees it. «جدول» = every chart has a "نمایش جدول" toggle (accessible data table of the same numbers), which is the relief rule for the chart palette (below).

| id | Persian title | Chart & rationale | Size def / min / max | Role | Drill-down |
|---|---|---|---|---|---|
| `kpi_runs_active` | برگزاری‌های فعال | **KPI tile**: one hero number (`value`), caption «از ۱۲ برگزاری»، delta chip. A single number needs no chart | 3×2 / 2×2 / 6×3 | viewer | `/runs?status=active` |
| `kpi_enrollments` | ثبت‌نام‌ها | KPI + **12-point sparkline** (2 px line, last point 8 px dot) — trend, no axes | 3×2 / 2×2 / 6×3 | viewer | `/enrollments` |
| `kpi_motivation_rate` | نرخ موتیویشن | KPI «۷۵٪» + thin 8 px progress bar (yes / total); delta in percentage points | 3×2 / 2×2 / 6×3 | viewer | `/enrollments?motivation=none` |
| `kpi_unassigned_requests` (new) | درخواست‌های IDP بدون برگزاری | KPI; the pool a coordinator picks candidates from (backend already has `counts.unassigned_enrollments`) | 3×2 / 2×2 / 6×3 | viewer | `/enrollments?run=none` |
| `kpi_budget` | بودجهٔ برنامه‌ریزی‌شده | KPI in «میلیون ریال» (exact rials in `title` + table), sub-line expected cost | 3×2 / 2×2 / 6×3 | hr | `/runs` sorted by amount |
| `runs_timeline_upcoming` | برگزاری‌های پیش‌رو و در معرض خطر | **Timeline list** (not a Gantt: 5–30 rows read faster as a list): date column, run label, 8 px mini-progress of motivations, **risk chips** (text + icon), next-action button | 8×4 / 4×3 / 12×8 | viewer | `/runs/:id` |
| `alerts_over3` | هشدار: بیش از ۳ موتیویشن تأییدنشده | **List** (name, ticket, count), grouped by manager when ≥ 3 | 4×4 / 4×3 / 12×8 | viewer | `/enrollments?q=<ticket>` |
| `motivation_progress_by_run` | پیشرفت موتیویشن هر برگزاری | **100 % horizontal stacked bar per run**, sorted by days-to-start (most urgent on top); segments yes / no / pending with 2 px surface gaps; direct count labels. Part-to-whole per row → stacked bar, not pie | 6×4 / 4×3 / 12×8 | viewer | `/enrollments?run=:id` |
| `funnel_run_stages` | مراحل برگزاری‌ها | **Horizontal bars, one per stage** (برنامه‌ریزی‌شده → اطلاع‌رسانی‌شده → ثبت‌نام باز → در حال برگزاری → تکمیل‌شده), single-hue ramp, label «تعداد · ٪ از مرحلهٔ قبل». Bars not a trapezoid funnel: areas mislead | 4×4 / 3×3 / 12×8 | viewer | `/runs?status=:stage` |
| `enrollments_by_division` | ثبت‌نام به تفکیک واحد | **Sorted horizontal bar**, top 8 + «سایر»; single hue; value labels at bar end | 4×4 / 4×3 / 12×8 | viewer | `/enrollments?division=…` |
| `trend_monthly` | روند ماهانه | **Two small multiples sharing the x-axis** (12 Jalali months): «برگزاری‌ها» columns above «شرکت‌کنندگان» line. **No dual axis** (runs ≈ 5, participants ≈ 100 — different scales) | 8×4 / 4×3 / 12×8 | viewer | `/runs?from=…` |
| `invoices_status` | وضعیت فاکتور و تسویه | **One 100 % segmented bar of rials** (بدون فاکتور / فاکتور دریافت‌شده / تسویه آغاز شده) + three rows «۱۲ برگزاری · ۱۸۰ میلیون ریال» | 4×4 / 3×3 / 12×8 | hr | `/runs?payment=…` |
| `level3_due` | ارزیابی سطح ۳ سررسید | **List**; days-overdue chip (`warn` when due ≤ 0 days); row action «درخواست ارزیابی» (needs `run_id`, A2) | 4×4 / 4×3 / 12×8 | viewer | `/letters?kind=level3_request&run=:id` |
| `sync_health` | سلامت همگام‌سازی | **Status rows** (icon + word + age): اکسل، IFS، خودکارسازی; never colour-only | 12×2 / 4×2 / 12×4 | hr | `/import-export` ▸ تاریخچه |

#### Default layouts (x,y,w,h; x from the right)

**HR coordinator** (role `hr`; the thing to act on is top-right):
```
y0  kpi_runs_active 0,0,3,2 · kpi_enrollments 3,0,3,2 · kpi_motivation_rate 6,0,3,2 · kpi_unassigned_requests 9,0,3,2
y2  runs_timeline_upcoming 0,2,8,4 · alerts_over3 8,2,4,4
y6  motivation_progress_by_run 0,6,6,4 · level3_due 6,6,6,4
y10 funnel_run_stages 0,10,4,4 · trend_monthly 4,10,8,4
y14 enrollments_by_division 0,14,6,4 · invoices_status 6,14,6,4
```
**Admin** (role `admin`): `sync_health 0,0,12,2` first; then the HR layout shifted down 2, with `kpi_budget` replacing `kpi_unassigned_requests`. **Viewer**: HR layout minus `invoices_status`, `kpi_budget`, `sync_health` (backend `catalog_for(role)` already filters).
(Backend `DEFAULT_POSITIONS` puts KPIs → funnel+timeline → progress+division → trend+invoices → level3+alerts → sync. Keep the structure; swap to the order above so *alerts and level-3* sit above the fold — this is data, one edit in `dashboard_widgets.py`.)

#### Edit mode (all of it keyboard-operable; no mouse-only path)
Entry: primary-less secondary button **«شخصی‌سازی»** (pencil icon) at the page head. Read mode shows **no** drag affordance (X3). In edit mode a sticky bar replaces the head actions: «افزودن ویجت» · «بازگشت به پیش‌فرض» · «انصراف» · **«ذخیره چیدمان»** (the one primary; disabled until a change; shows «۳ تغییر»).
1. **Move.** Each widget has a handle button (grip icon, `aria-label="جابه‌جایی ویجت «قیف مراحل»"`, 44×44 hit area, in the header's start side). Pointer: drag by handle, a 12-col ghost placeholder snaps; others reflow *only after drop*. Keyboard (dnd-kit KeyboardSensor [V S22]): focus handle → **Space** picks up → **←/→/↑/↓** moves one cell (RTL-correct: ← moves toward the left edge) → **Space** drops, **Esc** cancels and restores. Live region (polite): «ویجت «قیف مراحل» برداشته شد. با کلیدهای جهت‌نما جابه‌جا کنید.» / «به ستون ۴، ردیف ۲ منتقل شد.» / «رها شد.» / «انصراف داده شد.»
2. **Resize.** Bottom-inline-end corner handle (pointer) **and** a «اندازه» item in the «⋯» menu (works for keyboard and screen readers): radio list کوچک / متوسط / بزرگ / تمام‌عرض mapping to the widget's min / default / 1.5× / 12-col, plus **Shift+←/→/↑/↓** on the focused handle to grow/shrink by one unit. Clamp to min/max from `/dashboard/widgets` (backend rejects otherwise, 422 per widget).
3. **Remove.** «⋯ ▸ حذف از داشبورد» (no confirm: reversible, widget returns to the drawer; toast ««قیف مراحل» حذف شد. [برگردان]»).
4. **Add.** «افزودن ویجت» opens a **side drawer** (start side, 360 px, `role="dialog"`, focus trap, Esc closes and returns focus): search field, cards grouped «شاخص‌ها / نمودارها / فهرست‌ها / سیستم», each with a 160×96 static thumbnail, title, one-line purpose, «افزودن» button (disabled with «در داشبورد هست» when placed). Added widget lands at the first free slot at its default size and takes focus; announce «ویجت «…» اضافه شد.»
5. **Save / reset / leave.** Save → `PUT /me/dashboard-layout` (body `{widgets:[{id,x,y,w,h,config}]}`); success toast «چیدمان شما ذخیره شد.»; failure keeps edit mode with the server's Persian per-widget message. «بازگشت به پیش‌فرض» → confirm dialog «چیدمان شخصی شما حذف و چیدمان پیش‌فرض نقش «کارشناس آموزش» برگردانده می‌شود.» → `DELETE`. Unsaved changes + navigation → «تغییرات ذخیره‌نشده دارید. [ذخیره] [دور بریز] [ادامهٔ ویرایش]».
6. **Persisted layout is the desktop layout**; narrow screens derive their own (below). Edit mode is offered ≥ 1024 px; below that the button becomes «ترتیب ویجت‌ها» which offers only move-up/move-down buttons per widget (no free grid).
Implementation guidance: CSS Grid with explicit `grid-column`/`grid-row` from `{x,y,w,h}` + dnd-kit for movement; **do not** adopt react-grid-layout (its README lists no keyboard support [S23]; it is widely used though [V S23]) unless a spike proves keyboard + RTL.

#### States per widget (all inside the fixed frame)
- **Loading:** skeleton shaped like the final widget (KPI: 56 px number bar + 12 px line; chart: 5 bars at final positions; list: N rows at final row height) — same box, so zero shift.
- **Empty:** icon + one sentence + the verb, e.g. `runs_timeline_upcoming` «برگزاری پیش‌رویی نیست. [برگزاری جدید]»; `level3_due` «ارزیابی سررسیدشده‌ای نیست ✓»; KPI with no data: «—» and caption «هنوز داده‌ای نیست».
- **Error (per widget, never page-wide):** «این بخش بارگذاری نشد. [تلاش دوباره]» + server `message` in muted text; other widgets keep working.
- **Stale:** footer text «به‌روزرسانی: ۱۰ دقیقه پیش» turns `warn` (icon + text) after 30 min.
- **Forbidden by role:** the widget is not in the catalog and is dropped from a saved layout silently; the page shows once «برخی ویجت‌ها برای نقش شما در دسترس نیست.»

#### Refresh behaviour (the anti-jump contract)
No polling. One request on mount: `GET /dashboard/data?widgets=<all placed ids>&range=90d` (one round-trip, per-widget errors inside the payload). `staleTime: 60 s`, `placeholderData: keepPreviousData`; manual «به‌روزرسانی» icon button + «به‌روزرسانی: ۲ دقیقه پیش» text (fixed `min-inline-size: 18ch`). Data swaps **inside** the fixed frame: numbers in `tabular-nums` with a reserved width (`min-inline-size: 6ch`), SVG charts have a fixed `viewBox` and animate nothing, lists render a fixed row count with internal scroll. Range selector («۳۰ روز · ۹۰ روز · ۶ ماه · ۱۲ ماه · همه») sits in the page head and only changes data.

#### Colour (validated)
Accent yellow only on actionable controls («شخصی‌سازی», «ذخیره», links). Chart ink uses these tokens (add to `docs/design-tokens.json` → generated CSS):

| Token | Light | Dark | Use |
|---|---|---|---|
| `--viz-1` | `#2a78d6` | `#3987e5` | primary series, single-hue bars |
| `--viz-2` | `#eb6834` | `#d95926` | second series (trend: participants) |
| `--viz-3` | `#1baf7a` | `#199e70` | third series (rare) |
| `--seq-1…5` | `#DCE8F7 #A9C6EA #6FA0DB #2A78D6 #1B4F94` | `#1E3556 #27508A #3A71BE #5C93D6 #9DBFE8` | funnel stages / magnitude (light→dark = low→high; dark mode inverts so higher = lighter against the dark surface) |
| status | `--ok #1B7F4B`, `--warn #B26A00`, `--danger #C0392B`, `--info #1F5FA8` (existing, AA-nudged by `scripts/gen-tokens.mjs`) | existing derived | risk chips, deltas — always with icon + word |

Validation run (`dataviz/scripts/validate_palette.js`): light `#2a78d6,#eb6834,#1baf7a` — lightness band PASS, chroma PASS, **CVD ΔE 9.2 PASS (≥ 8)**, normal-vision ΔE 27.6 PASS, contrast vs surface **WARN: aqua 2.74:1 → relief rule** (direct labels + «جدول» toggle are mandatory, spec'd above). Dark `#3987e5,#d95926,#199e70`: all five checks PASS (CVD 9.4, normal 26.5, all ≥ 3:1). Sequential ramps are not covered by that script; I checked OKLab lightness is strictly monotonic in both modes (L 0.93→0.43 light; 0.33→0.79 dark) and that steps 3–5 clear 2.7/4.4/8.1:1 (light) and 3.5/5.4/9.0:1 (dark) — **use steps 3–5 for bar fills, 1–2 only as tracks**. Motivation yes/no/pending is a *state*, so it uses status styling not series colours: yes = `--ok` + «✓», no = `--text-muted`, pending = hatched outline; the three differ in lightness and pattern (CVD-safe). Text in charts is always `--text`/`--text-muted`, never the series colour.

#### Number & label rules
Counts «۱٬۲۳۴»; percent «۷۵٪» (no decimals under 10 000 rows); money: ≥ 1 000 000 → «۲۴۰ میلیون ریال» (one decimal max: «۲٫۵ میلیارد ریال»), exact in `title` and in the table view; deltas «▲ ۱۲٪ نسبت به ۳۰ روز قبل» / «▼ ۳ نسبت به ماه قبل» (arrow + word, colour secondary); dates `fmtJalali`; month axis labels from the API (`label` is Jalali month + Persian-digit year). Axis ticks ≤ 4, gridlines 1 px `--line`, bars 4 px rounded at the data end, 2 px surface gap between segments.

#### Responsive
≥ 1200 px: 12 columns. 768–1199: 6 columns (`w' = max(min(w,6), ceil(w/2))`, order by y then x). < 768: 1 column, order by (y,x), every widget full width, height = max(default h, 3) units; KPIs pair up 2-per-row (6-col half). Pointer targets ≥ 44 px < 768. Verified requirement: `documentElement.scrollWidth ≤ clientWidth` at 390 (SKILL §0).

#### API contract per widget (JSON)
Existing shapes (CONTRACT_REQUESTS round 5) are kept; **bold = needed additions**. Envelope: `GET /dashboard/data?widgets=a,b&range=30d|90d|6m|12m|all` → `{range, generated_at, widgets:{<id>: <data> | {error:{code,message}}}}`.
```jsonc
// kpi_runs_active   (same for kpi_enrollments, kpi_motivation_rate, kpi_unassigned_requests, kpi_budget)
{ "value": 7, "total_runs": 12, "starting_30d": 3, "by_status": {"announced":3,"running":1},
  "delta": {"abs": 2, "pct": 40.0, "basis": "previous_30d"},          // NEW  (null when no prior period)
  "spark": [4,5,5,6,6,7,7,6,7,8,7,7],                                   // NEW  12 monthly points (kpi_enrollments, kpi_motivation_rate)
  "drilldown": {"path": "/runs", "query": {"status": "active"}} }       // NEW
// kpi_unassigned_requests (NEW widget)
{ "value": 45, "oldest_age_days": 68, "drilldown": {"path": "/enrollments", "query": {"run": "none"}} }
// kpi_motivation_rate (existing) {value(%), participants, yes, no, pending}; kpi_budget (existing) {currency:"IRR", planned_total, planned_runs, expected_cost, expected_runs, payment_started_total, payment_pending_total, ...} integer rials

// runs_timeline_upcoming
{ "horizon_days": 90, "items": [ { "run_id": 5, "label": "مدیریت زمان · Demo Academy", "course_name": "…", "institute": "…", "type": "in_person",
    "start_date": "2026-10-28", "end_date": "2026-10-30", "status": "announced", "days_to_course": 25, "participants": 11, "motivations_yes": 6,
    "risk": ["low_motivation","no_institute_letter"],                  // NEW  codes: no_announcement | no_candidates | low_motivation(<50% and <14d) | deadline_passed_unanswered | no_institute_letter | no_invoice
    "next_action": {"kind":"followup_motivation","path":"/enrollments","query":{"run":"5","motivation":"none"}} } ] }   // NEW
// motivation_progress_by_run (existing) {items:[{run_id,course_name,start_date,participants,yes,no,pending,percent_yes}]}  + NEW: days_to_course, label, drilldown
// funnel_run_stages (existing) {stages:[{id,label_fa,count}],cancelled,total}   + NEW: stages[].drilldown
// enrollments_by_division (existing) {items:[{division,count}],total}           + NEW: items capped server-side at 8 with an "other" bucket
// trend_monthly (existing) {months:[{label,start,runs,participants,motivations_yes,expected_cost}]}
// invoices_status (existing) {currency,items:[{id:"no_invoice|invoice_received|payment_started",label_fa,runs,amount}]}
// level3_due (existing) {items,count,after_days} -> items: [{enrollment_id, ticket, emp_no, employee_name_fa /*NEW*/, course_name_fa /*NEW*/, run_id /*NEW*/, end_date, days_since_end}]
// alerts_over3 (existing) {items,count,threshold} -> items add {employee_name_fa, run_ids[], manager_name_fa?}
// sync_health (existing) {sources:[{source,status,started_at,finished_at,age_minutes,processed,message,stale}],running,connectors{},automation,ok}  -> message must be Persian (A3)
```
Layout: `GET|PUT|DELETE /me/dashboard-layout` → `{version, widgets:[{id,x,y,w,h,config}], is_default}` (exists). **Gaps:** (a) `delta/spark/drilldown` fields; (b) `runs_timeline_upcoming.risk/next_action` and the `kpi_unassigned_requests` widget; (c) `level3_due` Persian names + `run_id`; (d) `If-Match: version` conflict handling when two tabs save (currently "informational"); (e) every list widget returns `count` *and* `truncated`.

---

### 6.2 Template editor (e-mails and letters)

#### Where it lives
New nav item **«قالب‌ها»** (icon `template`) in the «ارتباطات» group next to «مرکز نامه‌ها». Also reachable in context: the Letters form and `EmailSendDialog` get a «قالب» select (default template for that kind preselected) with a link «ویرایش این قالب». Route `#/templates` (list) and `#/templates/:id` (editor); `viewer` sees the list and previews, cannot edit.

#### List screen
`PageHead`: «قالب‌ها» / «متن ایمیل‌ها و نامه‌ها را یک بار بنویسید و برای هر برگزاری دوباره استفاده کنید.» Primary: **«قالب جدید»**. Filters: search, نوع (ایمیل/نامه + kind), زبان (فارسی / انگلیسی / دوزبانه), «فقط قالب‌های من». Columns:

| ستون | محتوا |
|---|---|
| نام | name (link) + chip «سیستمی» or «من» |
| نوع | e.g. «ایمیل · اطلاع‌رسانی دوره» / «نامه · نامهٔ مؤسسه» |
| زبان | فارسی / English / دوزبانه |
| پیش‌فرض | chip «پیش‌فرض این نوع» (exclusive per kind+lang) |
| آخرین ویرایش | Jalali date + editor name |
| آخرین استفاده | Jalali date + «۱۲ بار» (**API gap:** `last_used_at`, `use_count`) |
| عملیات | ویرایش · کپی · پیش‌فرض کن · حذف (system rows: only «کپی» and «پیش‌نمایش») |
Empty state (cannot happen: system templates are seeded) — still: «هنوز قالبی ندارید. [قالب جدید]».

#### Editor layout (≥ 1100 px: two columns; below: tabs «ویرایش | پیش‌نمایش»)
```
┌ page head: «ویرایش قالب: یادآوری مهلت موتیویشن»  [نسخه‌ها] [ارسال آزمایشی به خودم] [ذخیره]
├ right column (editor, 60 %)                         ├ left column (preview + checks, 40 %)
│ نام قالب [..............]  نوع [ایمیل · یادآوری ▾ (قفل بعد از ساخت)]  زبان [فارسی ▾]
│ موضوع [ …{فیلد: نام دوره}… ] [{ } درج فیلد]       │ پیش‌نمایش  ( ) داده نمونه  ( ) برگزاری واقعی [انتخاب ▾]
│ ┌ toolbar: B I · • ۱. · 🔗 · ⇤ ⇥(جهت) · [{ } درج فیلد] [درج امضا] · ↶ ↷ ┐  ┌ rendered subject + body ┐
│ │ body (rich text, RTL, min 360 px)                                   │  └─────────────────────────┘
│ └─────────────────────────────────────────────────────────────────────┘  بررسی‌ها: ⚠ ۱ فیلد ناشناخته · ✓ امضا فارسی است
```
- **Toolbar kept minimal:** بولد، ایتالیک، فهرست نقطه‌ای/عددی، پیوند، تغییر جهت پاراگراف (راست‌به‌چپ/چپ‌به‌راست — needed for English lines), «جدول مشخصات دوره» (inserts the standard 5-row details table), «درج امضا», undo/redo. No fonts, sizes or colours (letters must look consistent; backend sanitises with an allow-list `rich_text.py`).
- **Editor engine:** Tiptap (MIT, headless, ProseMirror, custom inline atom node [V S24]) or Lexical (MIT, custom node [V S24]); spike both on RTL caret behaviour with Persian ZWNJ before committing. The body model is the backend's: sanitised HTML where a chip is `<span data-field="course_name_fa">نمونه</span>` and link chips are `<a data-field-href="link">` (CONTRACT_REQUESTS). Subject is a single-line editor of the same node type (chips allowed).
- **Chips:** inline atoms rendered as a rounded 24 px pill with a soft `--info-bg` fill, 1 px `--info` border, label in Persian («نام دوره»), `dir` of the surrounding text, `role="img"`-free: exposed as `<span role="mark" aria-label="فیلد: نام دوره">`. Atomic: arrow keys jump over a chip, **Backspace/Delete removes it whole**, double-click or **Enter** on a selected chip opens its menu: «اختیاری (اگر خالی بود حذف شود)» (writes `{{key?}}`), «نمایش با ارقام فارسی» (`|fa`), «ایزولهٔ چپ‌به‌راست» (`|ltr`, for phone/e-mail/ticket), «حذف». **Unknown field chip:** `--danger-bg` + ⚠ icon + tooltip «این فیلد وجود ندارد؛ آن را حذف یا جایگزین کنید.» **Chip not available for this kind** (e.g. «نام مدیر» in a letter to the institute): amber + «برای این نوع نامه مقدار ندارد».
- **Field picker.** Opens by: toolbar button «درج فیلد»; **Ctrl+Shift+F** (checked on `e.code === "KeyF"` so it works on a Persian layout); typing **`{{`** or **`/`** at the caret (typeahead; the typed trigger characters are removed on pick or Esc). Popover (listbox pattern, `role="combobox"` input + `role="listbox"`, `aria-activedescendant`), 360×420 px, anchored at the caret, flips at screen edge. Search matches Persian label, key, and sample value; results grouped with sticky group headers **«دوره · برگزاری · کارمند · مدیر · مؤسسه · شرکت · امضا · پیوندها · سیستم»**. Row = Persian label (start), sample value muted («مثلاً: مدیریت زمان»), key as `.id` (end), and «ضروری» chip when required by this kind. ↑/↓ move, **Enter** inserts and closes, **Tab** inserts and keeps typing, **Esc** closes returning focus to the caret, **Ctrl+Enter** inserts and keeps the picker open (insert several). Fields not valid for the template's kind are listed disabled at the bottom group «در این نوع قالب در دسترس نیست» with the reason. On a Persian keyboard `/` may be a different physical key — the three triggers are redundant by design; verify on the team's real layouts (see §9).
- **Live preview.** `POST /templates/preview` debounced 400 ms; shows rendered subject + body with **sample data** («نمونه» watermark chip) or **real data** (choose a برگزاری; per-person kinds also choose a کارمند). Result lists `used_fields`, `unknown_fields` (**blocks save**: «۱ فیلد ناشناخته: …») and `missing_fields` in real context (warning, not blocking: «برای این برگزاری «مهلت موتیویشن» ثبت نشده است. [برو به برنامه‌ریزی]»). Clicking an item in the list selects the chip in the editor. The preview area has a fixed min-height so edits do not move the page (§7).
- **Send test to me.** «ارسال آزمایشی به خودم» → `POST /templates/{id}:send-test` to the caller's own address; copy «یک نسخهٔ آزمایشی به <ایمیل شما> فرستاده می‌شود؛ هیچ‌کس دیگری ایمیل نمی‌گیرد.» If the user has no e-mail: inline «ابتدا ایمیل خود را در «حساب من» وارد کنید.» If the SMTP connector is not configured: the response is a dry run and the toast says «اتصال ایمیل تنظیم نشده؛ نسخهٔ آزمایشی فقط شبیه‌سازی شد.»
- **Versioning.** Every save creates version N+1 (backend). «نسخه‌ها» drawer: list (شمارهٔ نسخه، تاریخ شمسی، ویرایشگر), select a row to preview it read-only, **«بازگردانی این نسخه»** (creates a *new* version, confirm text «نسخهٔ ۴ به‌عنوان نسخهٔ ۷ ذخیره می‌شود؛ نسخه‌های قبلی حفظ می‌شوند.»).
- **System templates.** Read-only with a banner «این قالب سیستمی است و قابل ویرایش نیست. برای شخصی‌سازی یک نسخه کپی بسازید.» + primary «ساخت نسخهٔ قابل ویرایش» (`:duplicate`). Only one editor exists (X1).
- **Unsaved-changes guard,** autosave of a *draft* to `sessionStorage` via the existing `useDraft` (never to the server), «ذخیره» is the only way to publish. Delete a template used as default → confirm with the consequence «پیش‌فرض این نوع به قالب سیستمی برمی‌گردد.»
- **Where templates are consumed.** Letters form («قالب e-mail» select, sets the e-mail subject/body; the .docx still comes from the renderer, per the backend contract), `EmailSendDialog` (select + preview + recipient list as today), Automation (each automatic e-mail row picks a template, A8).

#### Templates that exist (seeded by core from `documents/default_templates.py`; names final)
| kind | کانال | نام فارسی | کاربرد | lang |
|---|---|---|---|---|
| `course_announcement` | نامه (.docx) + ایمیل | اطلاعیهٔ دوره | announce run, ask for موتیویشن by deadline | فا / En / هر دو |
| `institute_letter` | نامه | نامهٔ معرفی شرکت‌کنندگان به مؤسسه | official letter with participants table | فا |
| `settlement_letter` | نامه | درخواست تأیید فاکتور و تسویه | finance letter with attendee table | فا (see §9 Q2) |
| `level3_request` | نامه + ایمیل | درخواست ارزیابی سطح ۳ از شرکت‌کننده | 60 days after end | فا / En / هر دو |
| `level3_manager_check` | نامه + ایمیل | درخواست تأیید مدیر برای ارزیابی سطح ۳ | manager confirmation | فا / En / هر دو |
| `line_manager_approval` | نامه | تأیید مدیر مستقیم (دسته‌ای تا ۹ نفر) | batch of ≤ 9 tickets per manager | فا |
| `email_announcement` | ایمیل | ایمیل اطلاع‌رسانی دوره | covering e-mail of the announcement | فا |
| `email_reminder` | ایمیل | یادآوری مهلت موتیویشن | before deadline | فا |
| `email_level3` | ایمیل | ایمیل ارزیابی سطح ۳ | | فا |
| `email_manager_check` | ایمیل | ایمیل تأیید مدیر | | فا |
| `email_institute` | ایمیل | ایمیل ارسال نامه به مؤسسه | | فا |
| `email_settlement` | ایمیل | ایمیل ارسال تسویه | | فا |
| `email_generic` | ایمیل | ایمیل آزاد | free text with course context | فا |

#### Signature block rules (complaint 6)
1. **Every letter and e-mail ends with a Persian signature block, regardless of body language.** Lines, in order: **کلمهٔ پایانی** (`closing`: «با سپاس» to employees; «با احترام» to institutes, managers, finance) · [تصویر امضا اختیاری `[[SIGNATURE_IMAGE]]`] · **نام امضاکننده** (`signer_name_fa`) · **سمت** (`signer_title_fa`) · **واحد** (`unit_fa`, e.g. «توسعه استعدادها») · **اداره** (`department_fa`, «منابع انسانی») · ایمیل and تلفن (`signer_email`, `signer_phone`, `|ltr`, Persian digits for the phone with LTR isolation). Empty optional lines vanish (backend `hide_if_empty`).
2. **One place to set it:** «قالب‌ها ▸ امضای پیش‌فرض» (a card on the list page) with fields نام / سمت / واحد / اداره / ایمیل / تلفن / تصویر امضا, a live preview of the block, and per-template override via the «درج امضا» toolbar button (inserts the five chips; the chips resolve from the default unless overridden). This replaces `Automation.tsx:61-64` (`letter_signer_*`, English). **Core gap:** `PUT /automation/settings` (or a new `/settings/signature`) must store the five `_fa` keys + image; today nothing feeds them (A5).
3. **No Latin signature in a Persian block.** Validation: if the resolved signature lines contain `[A-Za-z]` in a template of lang `fa` or `both` the editor shows «امضا باید فارسی باشد: «Talent Development Team»» (warning on save, error when «امضای رسمی» is on). Proper nouns inside Persian text («LMS», «IFS») are allowed in body, not in the signature.
4. Persian digits for phone/numbers, LTR isolation for e-mail/phone, ZWNJ correct («منابع انسانی», «توسعهٔ استعداد»).

#### Field catalog the backend must expose
`GET /templates/fields` → `{items:[{key, label_fa, source, type, sample_fa, required_for_kinds[], available_for_kinds[] /*GAP*/, item_keys[]}], kinds[]}`. **Naming issue to resolve first:** `field_catalog.py` today keys on the legacy MERGEFIELD names (`Farsi_Course_Name`, `Reporter__Name`, `jStart_Date` …) while Dev-B's `default_templates.py` bodies use snake_case (`course_name_fa`, `employee_name_fa`, `start_date_jalali`, `deadline_fa`). One must win; the picker must never show the legacy key. Proposed canonical catalog (snake_case; keep legacy names as `aliases[]` so existing .docx templates still render; sample values are Persian-digit strings):

| key | label_fa | source | type | sample_fa |
|---|---|---|---|---|
| `course_name_fa` | نام دوره | course | text | مدیریت زمان |
| `course_name_en` | نام دوره (انگلیسی) | course | text | Time Management |
| `course_category_fa` | دستهٔ دوره | course | text | مهارت نرم |
| `course_type_fa` | نوع برگزاری | course | text | حضوری |
| `duration_fa` | مدت دوره | course | text | ۱۲ ساعت |
| `sessions_count` | تعداد جلسات | course | number | ۳ |
| `days_fa` | روزهای برگزاری | run | text | یکشنبه و دوشنبه |
| `time` | ساعت برگزاری | run | text(ltr) | ۱۰:۰۰–۱۶:۰۰ |
| `start_date_jalali` | تاریخ شروع | run | date_jalali | ۱۴۰۵/۰۸/۰۶ |
| `start_date_words` | تاریخ شروع (به حروف) | run | text | ششم آبان یک هزار و چهارصد و پنج |
| `end_date_jalali` | تاریخ پایان | run | date_jalali | ۱۴۰۵/۰۸/۰۸ |
| `deadline_fa` | مهلت ثبت موتیویشن | run | date_jalali | ۲۹ مهر ۱۴۰۵ |
| `send_date_jalali` | تاریخ ارسال اطلاعیه | run | date_jalali | ۱۴۰۵/۰۷/۱۶ |
| `days_to_start` | روز مانده تا شروع | run | number | ۲۵ |
| `method_fa` | روش برگزاری | run | text | آنلاین |
| `mtc_no` | شمارهٔ MTC (بخش ب) | run | text(ltr) | MTC-100004 |
| `invoice_no` | شمارهٔ فاکتور | run | text(ltr) | INV-0001 |
| `invoice_total` | مبلغ کل فاکتور (ریال) | run | money | ۲۴۰٬۰۰۰٬۰۰۰ |
| `per_attendee` | سهم هر نفر (ریال) | run | money | ۴۰٬۵۰۰٬۰۰۰ |
| `attendee_count` | تعداد شرکت‌کنندگان | run | number | ۵ |
| `participants_table` | جدول شرکت‌کنندگان | run | list | (نام، کد ملی، تلفن، ایمیل) |
| `settlement_table` | جدول ردیف‌های تسویه | run | list | (ردیف، کد پرسنلی، شرح، واحد-مرکز هزینه) |
| `employee_name_fa` | نام کارمند | employee | text | علی نمونه |
| `employee_first_name_fa` | نام کوچک کارمند | employee | text | علی |
| `employee_title_fa` | عنوان کارمند | employee | text | جناب آقای |
| `employee_emp_no` | شمارهٔ پرسنلی | employee | text(ltr) | D00001 |
| `employee_division_fa` | واحد کارمند | employee | text | فناوری اطلاعات |
| `employee_email` | ایمیل کارمند | employee | text(ltr) | ali@example.test |
| `ticket_no` | شمارهٔ تیکت | employee | text(ltr) | LMS-700000 |
| `manager_name_fa` | نام مدیر مستقیم | manager | text | رضا نمونه |
| `manager_title_fa` | عنوان مدیر | manager | text | جناب آقای |
| `manager_email` | ایمیل مدیر | manager | text(ltr) | reza@example.test |
| `manager_employees_table` | فهرست کارکنان مدیر (تا ۹ نفر) | manager | list | (نام، دوره، تیکت) |
| `institute_name` | نام مؤسسه | institute | text | مؤسسه نمونه |
| `institute_supplier_code` | کد تأمین‌کننده | institute | text(ltr) | S-102 |
| `institute_contact_email` | ایمیل مؤسسه | institute | text(ltr) | info@example.test |
| `company_name_fa` | نام شرکت | company | text | شرکت خدمات ارتباطی ایرانسل |
| `company_economic_code` | کد اقتصادی | company | text(ltr) | ۰۰۰۰-۰۰۰۰-۰۰۰۰ |
| `company_national_id` | شناسهٔ ملی | company | text(ltr) | ۰۰۰۰۰۰۰۰۰۰۰ |
| `company_postal_code` | کد پستی | company | text(ltr) | ۰۰۰۰۰۰۰۰۰۰ |
| `company_address` | نشانی دفتر مرکزی | company | text | تهران، خیابان نمونه، پلاک ۱ |
| `closing` | کلمهٔ پایانی | signature | text | با سپاس |
| `signer_name_fa` | نام امضاکننده | signature | text | علی نمونه |
| `signer_title_fa` | سمت امضاکننده | signature | text | کارشناس توسعه استعدادها |
| `unit_fa` | واحد | signature | text | توسعه استعدادها |
| `department_fa` | اداره | signature | text | منابع انسانی |
| `signer_email` | ایمیل امضاکننده | signature | text(ltr) | training@example.test |
| `signer_phone` | تلفن امضاکننده | signature | text(ltr) | ۰۲۱-۰۰۰۰۰۰۰۰ |
| `course_link` | پیوند محتوای دوره | links | url | https://lms.example.test/course/1 |
| `guide_link` | پیوند راهنمای ثبت موتیویشن | links | url | https://lms.example.test/guide |
| `ticket_url` | پیوند تیکت (iCare) | links | url | https://icare.example.test/browse/LMS-000001 |
| `letter_no` | شمارهٔ نامه | system | text(ltr) | TD-۱۴۰۵/۰۱۴۱ |
| `letter_date_jalali` | تاریخ نامه | system | date_jalali | ۱۴۰۵/۰۷/۱۱ |
| `today_jalali` | تاریخ امروز | system | date_jalali | ۱۴۰۵/۰۷/۱۱ |

Groups shown in the picker = `source`: course «دوره», run «برگزاری», employee «کارمند», manager «مدیر مستقیم», institute «مؤسسه», company «شرکت», signature «امضا», links «پیوندها», system «سیستم». Types drive formatting: `date_jalali` (never Gregorian), `money` (grouped Persian digits), `url` (rendered as link chip), `list` (only valid inside a table row — the picker inserts the table preset, not a loose chip). **Gaps for core/integrations:** `available_for_kinds`, `aliases`, `last_used_at/use_count` on templates, the `_fa` signature settings, and a rule that every `date_*` field renders Jalali with Persian digits.

---

### 6.3 Interactive tutorial (first-run guide)

**Principles.** Short tour + persistent checklist (S19); non-modal and skippable; resumes where you left; replayable from the help menu; role-specific; completion is **detected from data**, not from clicking «بعدی»; built in-repo (≈ 250 lines of React, no dependency: Shepherd is AGPL/commercial [V S20], driver.js is MIT and keyboard-friendly [V S21] and is the fallback if the in-house component slips); nothing loads from a CDN (CSP is `script-src 'self'`, on-prem air-gapped install).

#### Entry points
1. **First login** (`/me/preferences.tutorial` absent): a non-modal welcome card at the top of the dashboard (not a blocking modal): «به سامانهٔ مدیریت آموزش خوش آمدید. در حدود ۵ دقیقه، مراحل کار با یک برگزاری را قدم‌به‌قدم می‌بینید.» Buttons: **«شروع راهنما»** (primary) · «با داده‌های نمونه تمرین می‌کنم» · «بعداً» · link «دیگر نشان نده».
2. **Checklist card «شروع کار»** at the dashboard top (collapsible, remembers state) and in the help menu: progress bar «۳ از ۹ مرحله»، each row = checkbox state (done ✓ + text «انجام شد», not colour only), title, «برو به این مرحله». Hides itself 14 days after completion (kept in the help menu).
3. **Help menu «؟ راهنما»** (sidebar foot + topbar on mobile; `aria-haspopup="menu"`, `aria-expanded`, Esc closes and returns focus): «راهنمای شروع (چک‌لیست)» · «تور همین صفحه» · «پخش دوبارهٔ راهنما از اول» · «حالت آموزشی (داده نمونه)» · «میانبرهای صفحه‌کلید» · «گزارش مشکل».
4. **Contextual hints** inside empty states (table below) with a «راهنمای این مرحله» link opening the matching step.

#### Steps (admin: all 9; hr: 2–9 with step 1 replaced; viewer: V1–V3)
`data-tour="…"` attributes on the target elements are the stable hooks (no CSS-class coupling). Each coach-mark: title (≤ 6 words), body (≤ 2 sentences, imperative, friendly-formal «لطفاً/می‌توانید»), counter «مرحلهٔ ۲ از ۹», buttons «قبلی · بعدی · بعداً ادامه می‌دهم».

| # | Page · target | Title | Body copy | Done when (detection) |
|---|---|---|---|---|
| 1 | `/connectors` · `[data-tour=connector-ifs]` | اتصال منابع داده | «ابتدا اتصال IFS یا فایل اکسل را تنظیم و آزمایش کنید تا فهرست کارمندان و درخواست‌ها وارد شود.» | any connector `last_test_ok === true` (`GET /connectors`). **hr variant:** «اتصال‌ها را مدیر سامانه تنظیم می‌کند. اگر انجام شده، «ادامه» را بزنید.» (auto-done if step 2 is done) |
| 2 | `/import-export` · `[data-tour=import-start]` | ورود اطلاعات | «فایل خروجی iCare (IDP) یا کارنامهٔ قدیمی را انتخاب کنید و «ورود اطلاعات» را بزنید. تکرار ورود، رکورد تکراری نمی‌سازد.» | `counts.enrollments > 0` and `counts.employees > 0` (`GET /dashboard` counts) or a sync run with status ok/partial (`GET /sync/runs`) |
| 3 | `/runs` · `[data-tour=new-run]` | ساخت اولین برگزاری | «دوره را از کاتالوگ انتخاب کنید و تاریخ شروع و پایان را بدهید. بقیهٔ اطلاعات را بعداً هم می‌توانید کامل کنید.» | `counts.runs > 0` (created after tutorial start or any) |
| 4 | `/runs/:id/candidates` · `[data-tour=candidate-table]` | انتخاب کاندیدا | «درخواست‌های IDP مرتبط با این دوره را انتخاب و به برگزاری اضافه کنید. موارد دارای هشدار را پیش از افزودن بررسی کنید.» | run has `participants > 0` (`GET /runs/:id`) |
| 5 | `/letters` or run step «اطلاع‌رسانی» · `[data-tour=announce-preview]` | پیش‌نمایش و ارسال آزمایشی | «پیش‌نمایش اطلاعیه را ببینید و یک نسخهٔ آزمایشی به ایمیل خودتان بفرستید. ارسال واقعی بعد از تأیید شماست.» | a `MessageLog` with `dry_run=true` or a template `:send-test` for the user (`GET /messages`) |
| 6 | `/enrollments?run=:id` · `[data-tour=motivation-col]` | ثبت موتیویشن | «وضعیت موتیویشن هر نفر را «بله» یا «خیر» کنید؛ برای چند نفر با هم، آن‌ها را انتخاب و گروهی ثبت کنید.» | any enrollment `motivation in (Yes,No)` (`runs.motivations_yes > 0`) |
| 7 | `/letters?kind=institute_letter&run=:id` · `[data-tour=letter-create]` | نامهٔ مؤسسه | «نامهٔ رسمی را بسازید، پیش‌نمایش کنید و برای مؤسسه ایمیل کنید. شمارهٔ نامه خودکار داده می‌شود.» | `GET /letters` has `kind=institute_letter` |
| 8 | run step «فاکتور و تسویه» · `[data-tour=settlement-form]` | فاکتور و تسویه | «مبلغ و شمارهٔ MTC را ثبت کنید و نامهٔ تسویه را بسازید.» | run `amount` set and a `settlement_letter` exists |
| 9 | `/letters?kind=level3_request` · `[data-tour=level3-list]` | ارزیابی سطح ۳ | «۶۰ روز پس از پایان دوره، ارزیابی را از شرکت‌کنندگان و مدیرانشان بخواهید. سررسیدها در داشبورد دیده می‌شوند.» | any enrollment `level3_sent === true` |
| V1 | `/` · `[data-tour=dashboard]` | داشبورد | «اینجا وضعیت برگزاری‌ها و موارد نیازمند پیگیری را می‌بینید. شما فقط دسترسی مشاهده دارید.» | on viewing |
| V2 | `/runs` · `[data-tour=runs-table]` | برگزاری‌ها | «هر ردیف یک برگزاری است. با کلیک روی نام، مراحل و ثبت‌نام‌های آن را ببینید.» | on viewing |
| V3 | `/enrollments` · `[data-tour=enroll-filters]` | ثبت‌نام‌ها | «با فیلتر موتیویشن، افراد بدون پاسخ را پیدا کنید.» | on viewing |

Completion = union of **auto-detected** (a `useTutorialProgress()` hook polling nothing: it reads the already-cached list queries + one `GET /dashboard` on checklist open) and **manually ticked** («این مرحله را انجام داده‌ام»). Persisted in `PUT /me/preferences` as `tutorial:{completed_steps:["connect","import",…], dismissed:false, last_step:"candidates", sandbox:false, role_variant:"hr"}` (exists; 8 KB cap). Skip = `dismissed:true`; resume = reopen from the help menu at `last_step`.

#### Coach-mark behaviour
- **Visual:** 320 px max popover with an arrow to the target, dimmed backdrop with a cut-out ring (`--focus-ring` colour, 2 px, 6 px offset); dimmer is `pointer-events:none` on the target so the user can *do the thing* (type, click) — the step is done by the action, the popover then offers «بعدی». Position uses logical placement (`inset-inline-*`), flips at edges, repositions on resize/scroll; on < 768 px it becomes a bottom sheet pinned to the viewport bottom.
- **Keyboard:** popover is `role="dialog" aria-modal="false" aria-labelledby aria-describedby`. On open focus moves to the popover heading (`tabindex=-1`); **Tab** cycles popover buttons then continues into the page (non-modal); **Esc** pauses the tour (focus returns to the target); **Enter** on «بعدی»; arrow keys are *not* captured. The target gets `aria-describedby` pointing at the popover body while the step is active.
- **Screen reader:** a polite live region announces «مرحلهٔ ۲ از ۹: ورود اطلاعات» on each step; completion announces «این مرحله انجام شد».
- **Resilience:** if the target is missing or hidden (role, empty page, narrow layout) show a centred card «این بخش را در این صفحه پیدا نکردم. [برو به صفحهٔ مربوط] [رد کردن این مرحله]»; never block the app; tour state survives reload; `prefers-reduced-motion` removes the ring pulse and slide.
- **Never** auto-start a tour twice in a session, never start on a screen with an open dialog, never show on `/login`.

#### Sandbox / demo data («حالت آموزشی»)
Reuse the in-repo mock API (`api/mock/*`: in-memory store, same client, same wire types) lazy-loaded with `import()` so production pays ≈ 50 kB only when used. Toggle in the help menu → confirm «در حالت آموزشی با داده‌های نمونه کار می‌کنید؛ هیچ داده واقعی تغییر نمی‌کند و هیچ ایمیلی ارسال نمی‌شود.» A persistent yellow frame (the existing dry-run frame component) + banner «حالت آموزشی — [خروج از حالت آموزشی]» on every page; outward actions are simulated and labelled «(آزمایشی)»; state is memory-only (reload resets), so a trainee can never pollute the real DB. Checklist progress made in sandbox is stored separately (`sandbox_completed_steps`) and does not mark real steps done.

#### Contextual empty-state hints
| Screen | Empty state copy + action |
|---|---|
| Dashboard (no data) | «هنوز داده‌ای وارد نشده است. با «ورود اطلاعات» شروع کنید.» [انتقال اطلاعات] |
| Runs | «هنوز برگزاری‌ای ثبت نشده. از کاتالوگ یک دوره انتخاب و برای آن برگزاری بسازید.» [برگزاری جدید] [راهنمای این مرحله] |
| Candidates (none eligible) | «درخواست IDP مرتبطی پیدا نشد. فهرست درخواست‌ها را وارد یا به‌روز کنید.» [ورود اطلاعات] |
| Enrollments | «هنوز ثبت‌نامی نیست. درخواست‌های IDP را وارد کنید یا کاندیدا به یک برگزاری اضافه کنید.» |
| Letters (created) | «هنوز نامه‌ای ساخته نشده. یک نوع نامه و برگزاری انتخاب کنید.» [ساخت اولین نامه] |
| Templates | «قالب سیستمی را کپی کنید و متن را به سلیقهٔ خود تغییر دهید.» [ساخت نسخهٔ قابل ویرایش] |
| Employees | «فهرست کارمندان خالی است. فایل IFS را وارد کنید.» [انتقال اطلاعات] |
| Import history | «هنوز انتقالی انجام نشده.» |

---

### 6.4 Navigation, glossary, «انتقال اطلاعات», course vs run

#### Navigation regrouped by job (replaces the 9-item, 3-group menu; 11 items with Courses + Templates)
One icon family (the current `Icon.tsx`: 24×24 grid, ≈1.75 stroke, round caps/joins, no fills); new glyphs needed in the same style: `book`, `template`, `transfer`, `help`, `chart`. Icons are `aria-hidden` beside their label. Items with a count show it as text («۳») inside a small neutral badge, never colour alone.

| گروه (job) | آیتم | آیکون | نقش |
|---|---|---|---|
| (بدون عنوان) | داشبورد | `home` | all |
| **برنامه‌ریزی** | کاتالوگ دوره‌ها | `book` | all |
| | برگزاری‌ها (badge: تعداد «نیازمند اقدام») | `calendar` | all |
| **شرکت‌کنندگان** | ثبت‌نام‌ها و موتیویشن | `list` | all |
| | کارمندان | `users` | all |
| **ارتباطات** | مرکز نامه‌ها | `mail` | all (view-only for viewer) |
| | قالب‌ها | `template` | all (edit: hr+) |
| **داده‌ها** | انتقال اطلاعات | `transfer` | hr+ |
| **سیستم** | اتصال‌ها · خودکارسازی · مدیریت | `plug` · `bolt` · `shield` | hr+ / hr+ / admin |
Bottom of sidebar: «؟ راهنما» menu, a 3-way theme control (روشن · تیره · سیستم, `aria-pressed`), user box, خروج. Group headings stay (`role=group aria-label`); «سیستم» is collapsed by default for `hr`. The label «دوره‌های آموزشی» for the runs list is retired (it is the root of the course/run confusion).

#### Terminology glossary (use everywhere: UI, letters, e-mails, docs, errors)
| Use | Meaning | Never |
|---|---|---|
| **موتیویشن** (فرم موتیویشن) | the form each employee submits in the LMS | انگیزه‌نامه |
| **دوره** | a course in the catalog (what we teach) | for a dated instance |
| **برگزاری** | a dated run of a course at an institute | «دوره» alone |
| **درخواست IDP** | request from iCare not yet attached to a run | کاندیدا |
| **کاندیدا** | a person attached to a run, motivation pending | – |
| **شرکت‌کننده** | a person whose motivation is «بله» for that run | – |
| **ثبت‌نام** | one person's record in a run (row on «ثبت‌نام‌ها») | for "registration" column → say «ثبت‌نام در LMS» |
| **اطلاعیه** | the announcement letter/e-mail of a run | – |
| **مؤسسه** | training institute | شرکت آموزشی |
| **نامهٔ مؤسسه / نامهٔ تسویه** | the two outward letters | – |
| **فاکتور** / **تسویه** | invoice / settlement | – |
| **ارزیابی سطح ۳** | Level-3 effectiveness evaluation (always Persian digit ۳) | Level 3 |
| **مدیر مستقیم** | line manager | سرپرست |
| **انتقال اطلاعات** → **ورود اطلاعات / خروج اطلاعات / تاریخچه** | the import/export screen and its tabs | درون‌ریزی، برون‌بری، ایمپورت |
| **قالب**، **فیلد**، **پیش‌نمایش**، **ارسال آزمایشی**، **پیش‌فرض** | template editor vocabulary | تمپلیت، متغیر |
| **همگام‌سازی**، **اتصال**، **خودکارسازی** | sync / connector / automation | – |
Status words (one set everywhere): برنامه‌ریزی‌شده · اطلاع‌رسانی‌شده · ثبت‌نام باز · در حال برگزاری · برگزارشده · لغوشده. (Today the list says «برگزارشده» while the backend funnel label says «تکمیل‌شده» — align the backend label.) Persian digits and ZWNJ in all copy; «ي ك» Arabic forms never stored or shown.

#### «انتقال اطلاعات» (replaces `ImportExport.tsx`)
Page head: «انتقال اطلاعات» / «ورود فایل‌ها از iCare و کارنامهٔ قدیمی، و خروجی گرفتن از اطلاعات سامانه». `role=tablist`, arrow-key tabs, URL `#/import-export?tab=in|out|history`.
1. **ورود اطلاعات** — one linear flow, **one** primary:
   ① انتخاب نوع (radio cards): «درخواست‌های IDP (خروجی iCare)» · «کارنامهٔ قدیمی (Record / CHistory / IFS)» · «فهرست کارمندان (IFS)» — each with «دانلود فایل نمونه»; ② انتخاب فایل (dropzone, .xlsx, size limit stated); ③ **«بررسی پیش از ورود»** (server dry run): جدید / به‌روزرسانی / بدون تغییر / خطا + first 10 errors; ④ primary **«ورود اطلاعات»** (disabled until ③ ok; confirm text says repeat imports never duplicate and manual edits are kept). Progress with cancel; long jobs poll `GET /sync/runs` (202 handling exists). Result card with «مشاهدهٔ گزارش خطا» (CSV with BOM).
2. **خروج اطلاعات** — cards: «کارنامهٔ قدیمی (xlsx)» · «فهرست برگزاری‌ها» · «ثبت‌نام‌ها»; option «شامل کد ملی و موبایل» only for admin with warning «در گزارش ممیزی ثبت می‌شود»; one primary **«گرفتن خروجی»**; the button shows «در حال ساخت فایل…» while building.
3. **تاریخچه** — table: تاریخ (Jalali) · نوع (ورود / خروج / همگام‌سازی) · منبع · کاربر · نتیجه (chip with word) · ردیف‌ها (جدید/به‌روز/خطا) · «گزارش خطا». Replaces the Connectors → sync-runs entry point for imports. **API gap (core):** exports are audited but not listed — add `GET /transfers` (union of sync runs + export audit rows) with the same paging/sort contract.

#### Course vs run — information architecture
`کاتالوگ دوره‌ها` (courses: name fa/en, category, default duration, active, **number of runs, last run date**, «برگزاری جدید») ▸ `برگزاری‌ها` (runs) ▸ `صفحهٔ برگزاری` (stepper + panel + enrollments). Every run is named **«<دوره> · <تاریخ شروع> · <مؤسسه>»** wherever it is chosen or titled (selects, letters, toasts, breadcrumb), the run page `h1` stays the course name with the identity line under it and a breadcrumb «کاتالوگ دوره‌ها ‹ مدیریت زمان ‹ برگزاری ۶ آبان ۱۴۰۵». «برگزاری جدید» is reachable from the catalog row (pre-fills the course; `?new=1&course=ID` already coded in `Courses.tsx`) and from the runs list.

**Runs list (proposed columns, all sortable except actions):** برگزاری (two lines: course bold, institute muted) · شروع (Jalali + «۲۵ روز دیگر») · نوع · **مرحله** («۴ از ۷ · جمع‌آوری موتیویشن») · **موتیویشن** (progress bar + «۶ از ۱۱») · **اقدام بعدی** (one button, e.g. «پیگیری موتیویشن») · وضعیت (chip, no brand yellow). Tabs «پیش‌رو و فعال · گذشته · همه»; filters: جستجو، دوره (searchable select), مؤسسه، وضعیت، نوع، «نیازمند اقدام»; count line «۶ برگزاری · ۲ مورد نیازمند اقدام»; default order: needs-action first, then start date ascending. Needs `GET /runs` to accept `course_id`, `institute_id`, `needs_action`, `from/to`, and return `workflow_step` + `next_action` (core).

---

## 7. Page-jump fix guidelines (rules for every screen) and the concrete fix list

**Rules.**
1. **A skeleton is the same box as its content.** Build it from the content component (`<Row loading/>`), same row height and count (use the page size). Reserve `min-block-size` on cards that load (Dashboard card: 4 rows × 76 px).
2. **Never mount/unmount a sibling because data arrived.** Slots exist from the first paint: sync chips, pager (always rendered, fixed 56 px, disabled when single page), «در حال به‌روزرسانی…» text (fixed-width slot, `visibility`, not conditional render).
3. **Every parameterised list uses `placeholderData: keepPreviousData`** (Runs/Enrollments/Employees do; Dashboard, Connectors, Admin users, Letters list, `["run"]` do not).
4. **No virtualisation under ~300 rows.** If a table must virtualise, rows have a fixed CSS `block-size` with `overflow:hidden` + truncation (the 52 px `td` rule is a *minimum* today) or the virtualiser uses `measureElement`.
5. **Previews and charts have fixed frames** (`min-block-size`, SVG `viewBox`); content swaps inside, scroll inside.
6. **Refetch in the background must not reorder** (backend now has total order + `id` tie-break) and must not change heights; no polling.
7. **Fonts:** `<link rel="preload" as="font" type="font/woff2" crossorigin>` for Regular/SemiBold/Bold; fallback with `size-adjust`/`ascent-override`; keep `scrollbar-gutter: stable` (already present, works).
8. **Budget + test:** CLS ≤ 0.02 per screen load and zero `scrollHeight` changes while scrolling a virtualised table, asserted in CI with `qa/uiux2/cls2.mjs`, `journey.mjs`, `virt.mjs` (run against a 280 ms and a 900 ms latency; `slow.mjs`). Mock latency default 80 ms.

**Concrete fixes (frontend unless noted).**
| ID | File:symbol | Fix |
|---|---|---|
| J1 | `components/DataTable.tsx:28` + `screens/Employees.tsx:36` | drop `virtualize` (100 rows) — or `measureElement` + `estimateSize: () => 80` |
| J2 | `screens/Dashboard.tsx` loading branches (lines ≈31–54) | skeleton cards = final card (title row, hint, 3–4 item rows of 76 px); sync chips slot reserved; due card `min-block-size` |
| J3 | `screens/Connectors.tsx:101-114` | skeleton card with the real card's height (≈ 400 px) or render the form shell immediately |
| J4 | `components/DataTable.tsx` skeleton (line ≈67) + `Enrollments.tsx` | `skeletonRows = pageSize`, skeleton row height = real row height (105 px → also fix C11), pager slot reserved |
| J5 | `screens/Letters.tsx:54,100` | preview card `min-block-size: 480px`, scroll inside, keep old HTML until new HTML arrives (already `placeholderData`), fixed-width «در حال به‌روزرسانی» slot |
| J6 | `screens/Runs.tsx` `StepPanel` | step panel `min-block-size` = tallest panel (≈ 416 px) |
| J7 | `index.html`, `base.css` | font preload + fallback metrics; give `#root` a `min-block-size: 100dvh` shell so the first paint is not 8 px high |

## 8. Prioritised implementation backlog

Effort: S ≤ 1 day · M 2–4 days · L 1–2 weeks. Owners follow `docs/ARCHITECTURE.md` §3: **frontend** = Dev-C, **core** = Dev-A, **integrations** = Dev-B.

| P | ID | Item | Eff. | Owner |
|---|---|---|---|---|
| P0 | J1 | Remove `virtualize` on Employees (scroll jiggle) | S | frontend |
| P0 | J2–J4 | Skeleton = content frame on Dashboard, Connectors, Enrollments; pager slot | S–M | frontend |
| P0 | A1 | Server-built `drilldown` per dashboard list + correct hint/status definitions | S+S | core, frontend |
| P0 | A2 | `level3_due` + `alerts_over3`: `run_id`, `employee_name_fa`, `course_name_fa`; CTA passes `run` | S+S | core, frontend |
| P0 | A3 | Structured due messages (`{kind, params}`), Persian rendering, Jalali dates | M | integrations (+frontend S) |
| P0 | A4 | Run label «دوره · تاریخ · مؤسسه» + searchable run combobox on Letters/dialogs | S | frontend |
| P0 | A5 | Persian signature: `_fa` settings storage + «امضای پیش‌فرض» form + validation; settlement/EN-section decision | M+M+S | core, integrations, frontend |
| P1 | B2 | Template list + editor (chips, picker, preview, test-send, versions, duplicate) | L | frontend |
| P1 | B2a | Field catalog unification (snake_case canonical + aliases, `available_for_kinds`, `last_used_at/use_count`) | M | integrations + core |
| P1 | B4 | Editable dashboard: grid, edit mode, drawer, 14 widgets, charts, states | L | frontend |
| P1 | B4a | Widget API additions (`delta/spark/drilldown/risk/next_action`, `kpi_unassigned_requests`, `If-Match`) | S–M | core |
| P1 | B1 | Route + review Courses catalog; runs-list columns/filters/tabs; run identity string; breadcrumbs; rename nav | M | frontend (+core S: list filters) |
| P1 | C14 | Nav regroup with 5 new icons + help menu + 3-way theme control | M | frontend |
| P1 | B5 | «انتقال اطلاعات» tabs, dry-run step, history; `GET /transfers` | M + S | frontend, core |
| P1 | B3 | Tutorial: welcome, checklist, coach-marks, role variants, sandbox via lazy mock, hints | M | frontend |
| P1 | B6/B7 | `h1` on forbidden/404; `EmptyState as`; focus heading when it mounts | S | frontend |
| P2 | C8/C9 | Status chip tone for «در حال برگزاری»; one primary per screen (Import, Automation, Run detail) | S | frontend |
| P2 | C11 | Enrollments row redesign (chips + popover edit, default filter «بدون پاسخ»), 105 → 64 px rows | M | frontend |
| P2 | C10 | Move sync chips into `sync_health` widget; hr/viewer variant | S | frontend |
| P2 | J5–J7 | Letters preview frame, run step min-height, font preload, `#root` shell | S | frontend |
| P2 | CI | CLS/virt probes in CI (`qa/uiux2/*.mjs`), mock latency 80 ms | S | frontend |
| P2 | C13 | Verify digits in names with real IFS data; apply `toFa` on the Employees path | S | frontend |
| P3 | D | `h1` focus ring shape, empty states on Employees/Letters list | S | frontend |

## 9. What I could not verify

- **Vendor documentation:** the fetch tool was blocked for SAP, Docebo, Workday, Metabase and learning.sap.com hosts; all `[V]`/V-search claims rest on search-engine summaries of the cited URLs, not on my reading of the pages. Not verified at all: Cornerstone correspondence/notification templates, Moodle Workplace specifics (only Totara placeholders), TalentLMS dashboard-widget behaviour, any vendor's own onboarding/tutorial design, Intercom specifics. react-grid-layout's licence and keyboard support (README fetched states neither); dnd-kit RTL behaviour with arrow keys (documented keyboard sensor only).
- **Persian keyboard:** which physical key yields `/` and `{` on the coordinators' layouts — the three redundant picker triggers are a hedge, not a test. Ctrl+Shift+F conflicts in the team's browsers/IME were not tested.
- **Tab testing** was done as admin, light, 1440 px; hr/viewer/dark/narrow were covered by axe + DOM probes, not by a Tab walk. axe on the live backend ran admin only (1440/390 × 2 themes) and needed `bypassCSP` for injection.
- **Live data is synthetic** (`app.demo`); real IFS/iCare data may expose other name/digit issues (C13) and larger lists (the runs list, Letters run select cap of 100).
- **Moving target:** other agents edited frontend, backend and templates during the review. Findings cite HEAD + the 07:20–07:40 working tree; `/dashboard/widgets` and `/me/dashboard-layout` returned 404 on a server started at 07:3x (route registration lagged), so those endpoints were verified by reading code and CONTRACT_REQUESTS, **not** by calling them. `screens/Courses.tsx` appeared after the review build and is unreviewed in a browser.
- **Not exercised:** real SMTP/Graph sending, real .docx rendering of the new Persian signature, printing/PDF, Safari/Firefox, screen-reader speech (VoiceOver/NVDA), 200 % text zoom on new screens, performance with > 1 000 enrollments in one run.
- **Chart palette:** categorical set validated with the script; the sequential ramp checked by lightness monotonicity and contrast only (the script is categorical-only); the hatched "pending" texture is specified, not rendered.

**Questions for the owner**
1. Which screen were you on when the page "jumped every few seconds" — was it the employee list while scrolling, or a screen right after loading? (A screen recording of 10 s would settle it.)
2. Letters: the settlement letter and the English halves of bilingual letters currently end «Best regards, …». Should *every* letter, including English text, end with the Persian signature block (the spec assumes yes), or may English sections keep an English sign-off under a Persian block?
3. Templates: should user-created templates be **shared by the whole HR team** (spec default; admin/hr edit, viewer reads) or **private per user** with an optional «اشتراک‌گذاری» switch?
