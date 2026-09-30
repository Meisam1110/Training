// In-memory implementation of docs/API_CONTRACT.md as a fetch-compatible function.
// It goes through the *real* client (CSRF, error envelope, 401 handling), so the UI exercises
// the same code paths as against the backend. Roles are enforced here too (a viewer gets 403).
import { diffDaysISO, fmtJalaliLong } from "../../lib/jalali";
import { fmtNum, normFa, toFa } from "../../lib/digits";
import type {
  AuditEntry, Candidate, CandidateFlag, ConnectorKind, CourseRun, DashItem, Dashboard, DueItem, EmailSendRequest, EmailSendResult,
  ErrorCode, ExcludedCandidate, ImportResult, Letter, LetterKind, LetterRequest, Role, SyncRun, User,
} from "../types";
import { makeStore, type Store } from "./seed";

export interface MockOptions { latency?: number; store?: Store; storage?: boolean }

const KIND_FA: Record<LetterKind, string> = {
  course_announcement: "اطلاعیهٔ دوره", institute_letter: "نامهٔ مؤسسه", settlement_letter: "نامهٔ تسویه‌حساب",
  level3_request: "درخواست ارزیابی سطح ۳", level3_manager_check: "تأیید مدیر (سطح ۳)", line_manager_approval: "تأیید مدیر مستقیم",
};
const SESSION_KEY = "tms.mock.user";

class HttpErr extends Error {
  constructor(public status: number, public code: ErrorCode, message: string, public fields?: Record<string, string>) { super(message); }
}
const forbidden = () => new HttpErr(403, "forbidden", "شما اجازهٔ انجام این کار را ندارید.");
const notFound = (what = "مورد") => new HttpErr(404, "not_found", `${what} پیدا نشد.`);
const invalid = (fields: Record<string, string>, message = "اطلاعات واردشده معتبر نیست.") => new HttpErr(422, "validation", message, fields);

export function createMockFetch(o: MockOptions = {}) {
  const store = o.store ?? makeStore();
  const latency = o.latency ?? 280;
  const csrfToken = "mock-csrf-" + Math.random().toString(36).slice(2, 10);
  let sessionUser: string | null = null;
  if (o.storage !== false) { try { sessionUser = localStorage.getItem(SESSION_KEY); } catch { /* ignore */ } }

  const user = (): (User & { password: string }) | null => store.users.find((u) => u.username === sessionUser && u.active) ?? null;
  const need = (...roles: Role[]) => {
    const u = user(); if (!u) throw new HttpErr(401, "unauthorized", "نشست شما منقضی شده است. دوباره وارد شوید.");
    if (roles.length && !roles.includes(u.role)) throw forbidden();
    return u;
  };
  const write = () => need("admin", "hr");
  const log = (action: string, entity: string, id: string | number, detail = "-") => {
    const a: AuditEntry = { id: store.seq.audit++, at: new Date().toISOString(), user: sessionUser ?? "-", action, entity, entity_id: String(id), ip: "127.0.0.1", detail };
    store.audit.unshift(a);
  };

  const withCounts = (r: CourseRun): CourseRun => {
    const es = store.enrollments.filter((e) => e.run_id === r.id);
    return { ...r, counts_known: true, enrollment_count: es.length, motivation_yes_count: es.filter((e) => e.motivation === "yes").length };
  };
  const paginate = <T,>(items: T[], q: URLSearchParams) => {
    const page = Math.max(1, Number(q.get("page") ?? 1)); const size = Math.min(500, Math.max(1, Number(q.get("page_size") ?? 50)));
    return { items: items.slice((page - 1) * size, page * size), total: items.length, page, page_size: size };
  };
  function sortBy<T>(items: T[], sort: string | null, dflt: string): T[] {
    const s = sort || dflt; const desc = s.startsWith("-"); const key = s.replace(/^-/, "") as keyof T;
    return [...items].sort((a, b) => {
      const x = a[key] as unknown, y = b[key] as unknown;
      const c = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "fa");
      return desc ? -c : c;
    });
  }
  const matchQ = (q: string | null, ...fields: (string | number | null | undefined)[]) =>
    !q || normFa(fields.map((f) => String(f ?? "")).join(" ")).includes(normFa(q));

  // ---- derived dashboard lists (same definitions as backend/app/api/services/dashboard.py) ----
  const nonYesByEmp = () => {
    const m = new Map<string, number>();
    store.enrollments.filter((e) => e.motivation !== "yes" && e.run_id !== null).forEach((e) => m.set(e.emp_no, (m.get(e.emp_no) ?? 0) + 1));
    return m;
  };
  function lists() {
    const t = store.today; const runs = store.runs.map(withCounts);
    const item = (r: CourseRun, detail: string, date: string | null): DashItem => ({ key: `run-${r.id}`, title: r.course_name_fa, detail, date, run_id: r.id });
    const notStarted = runs.filter((r) => (r.status === "planned" || r.status === "announced") && r.start_date >= t)
      .map((r) => item(r, `${r.institute || "—"} · ${toFa(diffDaysISO(t, r.start_date))} روز تا شروع`, r.start_date));
    const payment = runs.filter((r) => r.status !== "cancelled" && r.start_date <= t && r.amount && !r.payment_started)
      .map((r) => item(r, `${r.institute || "—"} · مبلغ ${fmtNum(r.amount)} ریال`, r.end_date));
    const over3 = [...nonYesByEmp().entries()].filter(([, n]) => n > store.automation.over3_threshold).map(([no, n]): DashItem => {
      const e = store.employees.find((x) => x.emp_no === no)!; const en = store.enrollments.find((x) => x.emp_no === no && x.run_id !== null && x.motivation !== "yes")!;
      return { key: `tk-${en.ticket}`, title: e.name_fa, detail: `${toFa(n)} بار پیشنهاد بدون تأیید · \u2068${en.ticket}\u2069`, date: null, run_id: en.run_id, emp_no: no, ticket: en.ticket };
    });
    const l3 = store.enrollments.filter((e) => e.run_id !== null && e.level3_status === "Evaluation Level 3").flatMap((e): DashItem[] => {
      const r = store.runs.find((x) => x.id === e.run_id)!; const days = diffDaysISO(r.end_date, t);
      return days >= store.automation.level3_after_days ? [{ key: `enr-${e.id}`, title: e.name_fa, detail: `${r.course_name_fa} · ${toFa(days)} روز از پایان`, date: r.end_date, run_id: r.id, emp_no: e.emp_no }] : [];
    });
    return { notStarted, payment, over3, l3 };
  }
  function dashboard(): Dashboard {
    const L = lists(); const ls = (k: "excel" | "ifs") => store.syncRuns.find((s) => s.kind === k);
    const sum = (k: "excel" | "ifs") => { const s = ls(k); return s ? { at: s.finished_at ?? s.started_at, status: s.status === "failed" ? "failed" as const : "ok" as const } : { at: null, status: "never" as const }; };
    return {
      not_started_courses: L.notStarted, payment_not_started: L.payment, over3_motivations: L.over3, level3_due: L.l3.slice(0, 10),
      counts: {
        not_started_courses: L.notStarted.length, payment_not_started: L.payment.length, over3_motivations: L.over3.length, level3_due: L.l3.length,
        runs: store.runs.length, employees: store.employees.length, enrollments: store.enrollments.length,
      },
      last_sync: { excel: sum("excel"), ifs: sum("ifs") },
    };
  }
  function due(): DueItem[] {
    const L = lists(); const out: DueItem[] = [];
    L.l3.forEach((i) => out.push({ id: `l3-${i.key}`, kind: "level3_due", title: `${i.title} — ${i.detail}`, due_date: i.date, run_id: i.run_id, count: 1 }));
    L.over3.forEach((i) => out.push({ id: `o3-${i.key}`, kind: "over3_motivations", title: `${i.title}: ${i.detail}`, due_date: null, run_id: null, count: 1 }));
    L.payment.forEach((i) => out.push({ id: `pay-${i.key}`, kind: "payment_not_started", title: `${i.title} — ${i.detail}`, due_date: i.date, run_id: i.run_id, count: 1 }));
    return out;
  }

  function workflowOf(r: CourseRun) {
    const es = store.enrollments.filter((e) => e.run_id === r.id);
    const sent = (k: LetterKind) => store.letters.some((l) => l.run_id === r.id && l.kind === k && l.state === "sent");
    return {
      announced: sent("course_announcement") || ["announced", "open", "running", "completed"].includes(r.status),
      motivations_collected: es.length > 0 && es.every((e) => e.motivation !== "pending"),
      institute_letter_sent: sent("institute_letter"), invoice_received: r.payment_started, settlement_sent: sent("settlement_letter"),
      level3_started: r.payment_started && es.some((e) => e.level3_status !== "-"),
    };
  }
  // ---- letters ----
  function letterFields(kind: LetterKind, run: CourseRun | undefined, ov: Record<string, string>) {
    const ex = (k: string, v: string | null | undefined) => (ov[k] ?? v ?? "").toString();
    const r = run;
    const spec: Record<LetterKind, [string, string, string][]> = {
      course_announcement: [["Farsi_Course_Name", "نام دوره", ex("Farsi_Course_Name", r?.course_name_fa)], ["jStart_Date", "تاریخ شروع", ex("jStart_Date", r ? fmtJalaliLong(r.start_date) : "")], ["deadline_farsi", "مهلت ارسال انگیزه‌نامه", ex("deadline_farsi", r?.deadline ? fmtJalaliLong(r.deadline) : "")], ["Time_Farsi", "ساعت برگزاری", ex("Time_Farsi", r?.time)], ["Day_Farsi", "روزهای برگزاری", ex("Day_Farsi", r?.days)]],
      institute_letter: [["To", "گیرنده (مؤسسه)", ex("To", r?.institute)], ["Course_Name", "نام دوره", ex("Course_Name", r?.course_name_fa)], ["Jstart_Date", "تاریخ شروع", ex("Jstart_Date", r ? fmtJalaliLong(r.start_date) : "")], ["Duration", "مدت (ساعت)", ex("Duration", r ? toFa(r.duration_h) : "")]],
      settlement_letter: [["supplier", "تأمین‌کننده", ex("supplier", r?.institute)], ["MTC_no", "شمارهٔ MTC (بخش ب)", ex("MTC_no", r?.section_b)], ["total", "مبلغ کل (ریال)", ex("total", r?.amount ? fmtNum(r.amount) : "")], ["invoice_no", "شمارهٔ فاکتور", ex("invoice_no", "")]],
      level3_request: [["Ftitle", "عنوان (فارسی)", ex("Ftitle", "جناب آقای/سرکار خانم")], ["Summary", "عنوان دوره", ex("Summary", r?.course_name_fa)]],
      level3_manager_check: [["Manager_Fname", "نام مدیر", ex("Manager_Fname", "")], ["Summary", "عنوان دوره", ex("Summary", r?.course_name_fa)]],
      line_manager_approval: [["Mg_name", "نام مدیر مستقیم", ex("Mg_name", "")], ["EmpSummary1", "شرح دوره کارمند ۱", ex("EmpSummary1", r?.course_name_fa)]],
    };
    return spec[kind];
  }
  function renderLetter(req: LetterRequest) {
    const run = req.run_id ? store.runs.find((r) => r.id === req.run_id) : undefined;
    if (req.run_id && !run) throw notFound("دوره");
    const fields = letterFields(req.kind, run, req.overrides ?? {});
    const missing: Record<string, string> = {};
    if (["level3_request", "level3_manager_check", "line_manager_approval"].includes(req.kind) && !(req.enrollment_ids ?? []).length) missing.enrollment_ids = "شرکت‌کننده‌ای انتخاب نشده است.";
    fields.forEach(([k, label, v]) => { if (!v.trim()) missing[k] = `مقدار «${label}» خالی است.`; });
    const rows = fields.map(([, label, v]) => `<tr><th>${label}</th><td>${v ? v : `<mark>[${label}]</mark>`}</td></tr>`).join("");
    const html = `<article dir="rtl" lang="fa"><h2>${KIND_FA[req.kind]}</h2><p>با سلام و احترام،</p><table>${rows}</table><p>با تشکر — تیم توسعه استعداد، منابع انسانی</p></article>`;
    return { html, missing };
  }

  // ---- routing ----
  type Ctx = { q: URLSearchParams; body: any; path: string; m: RegExpExecArray; file?: { name: string; size: number } };
  type Handler = (c: Ctx) => unknown;
  const routes: [string, RegExp, Handler][] = [];
  const on = (method: string, re: RegExp, h: Handler) => routes.push([method, re, h]);

  on("POST", /^\/auth\/login$/, ({ body }) => {
    const errs: Record<string, string> = {};
    if (!body?.username) errs.username = "نام کاربری را وارد کنید.";
    if (!body?.password) errs.password = "گذرواژه را وارد کنید.";
    if (Object.keys(errs).length) throw invalid(errs);
    const u = store.users.find((x) => x.username === body.username && x.password === body.password && x.active);
    if (!u) throw new HttpErr(401, "unauthorized", "نام کاربری یا گذرواژه درست نیست.");
    sessionUser = u.username; if (o.storage !== false) { try { localStorage.setItem(SESSION_KEY, u.username); } catch { /* ignore */ } }
    log("login", "user", u.id);
    const { password: _p, ...pub } = u; void _p;
    return { user: pub, csrf_token: csrfToken };
  });
  on("POST", /^\/auth\/logout$/, () => { sessionUser = null; if (o.storage !== false) { try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ } } return null; });
  on("GET", /^\/auth\/me$/, () => { const u = need(); const { password: _p, ...pub } = u; void _p; return { user: pub, csrf_token: csrfToken }; });
  on("GET", /^\/dashboard$/, () => { need(); return dashboard(); });

  on("GET", /^\/employees$/, ({ q }) => {
    need();
    let items = store.employees.filter((e) => matchQ(q.get("q"), e.emp_no, e.name_fa, e.name_en, e.division, e.email));
    if (q.get("division")) items = items.filter((e) => e.division === q.get("division"));
    if (q.get("status")) items = items.filter((e) => e.status === q.get("status"));
    const pub = sortBy(items, q.get("sort"), "emp_no").map(({ raw_mobile: _a, raw_national_code: _b, ...e }) => { void _a; void _b; return e; });
    return paginate(pub, q);
  });
  on("GET", /^\/employees\/([^/]+)$/, ({ q, m }) => {
    const u = need(); const e = store.employees.find((x) => x.emp_no === decodeURIComponent(m[1]!)); if (!e) throw notFound("کارمند");
    const { raw_mobile, raw_national_code, ...pub } = e;
    if (q.get("reveal") === "1") {
      if (u.role === "viewer") throw forbidden();
      log("employee.reveal", "employee", e.emp_no, "نمایش کد ملی و موبایل");
      return { ...pub, mobile: raw_mobile, national_code: raw_national_code };
    }
    return pub;
  });

  on("GET", /^\/courses$/, ({ q }) => { need(); return paginate(store.courses.filter((c) => matchQ(q.get("q"), c.name_fa, c.name_en)), q); });

  on("GET", /^\/runs$/, ({ q }) => {
    need();
    let items = store.runs.map(withCounts).filter((r) => matchQ(q.get("q"), r.course_name_fa, r.course_name_en, r.institute, r.section_b));
    if (q.get("status")) items = items.filter((r) => r.status === q.get("status"));
    if (q.get("type")) items = items.filter((r) => r.type === q.get("type"));
    return paginate(sortBy(items, q.get("sort"), "-start_date"), q);
  });
  on("POST", /^\/runs$/, ({ body }) => {
    write();
    const errs: Record<string, string> = {};
    const c = store.courses.find((x) => x.id === Number(body?.course_id)); if (!c) errs.course_id = "دوره را انتخاب کنید.";
    if (!body?.start_date) errs.start_date = "تاریخ شروع را وارد کنید.";
    if (!body?.end_date) errs.end_date = "تاریخ پایان را وارد کنید.";
    else if (body.start_date && body.end_date < body.start_date) errs.end_date = "تاریخ پایان نباید قبل از تاریخ شروع باشد.";
    if (Object.keys(errs).length) throw invalid(errs);
    const r: CourseRun = { id: store.seq.run++, course_id: c!.id, course_name_fa: c!.name_fa, course_name_en: c!.name_en, type: body.type ?? c!.delivery, institute: body.institute ?? "", duration_h: body.duration_h ?? 12, start_date: body.start_date, end_date: body.end_date, days: body.days ?? "", time: body.time ?? "", sessions: body.sessions ?? 2, send_date: null, deadline: null, amount: null, section_b: null, link: body.link ?? "", status: "planned", enrollment_count: 0, motivation_yes_count: 0, payment_started: false, counts_known: true };
    store.runs.unshift(r); log("run.create", "run", r.id); return withCounts(r);
  });
  const detail = (r: CourseRun) => ({ ...withCounts(r), workflow: workflowOf(r) });
  on("GET", /^\/runs\/(\d+)$/, ({ m }) => { need(); const r = store.runs.find((x) => x.id === +m[1]!); if (!r) throw notFound("دوره"); return detail(r); });
  on("PATCH", /^\/runs\/(\d+)$/, ({ m, body }) => {
    write(); const r = store.runs.find((x) => x.id === +m[1]!); if (!r) throw notFound("دوره");
    const errs: Record<string, string> = {};
    const start = body.start_date ?? r.start_date, end = body.end_date ?? r.end_date;
    if (end < start) errs.end_date = "تاریخ پایان نباید قبل از تاریخ شروع باشد.";
    if (body.amount !== undefined && body.amount !== null && !(body.amount >= 0)) errs.amount = "مبلغ باید عدد باشد.";
    if (Object.keys(errs).length) throw invalid(errs);
    if (body.payment_process) { r.payment_started = true; delete body.payment_process; }
    Object.assign(r, body); log("run.update", "run", r.id); return detail(r);
  });
  on("GET", /^\/runs\/(\d+)\/enrollments$/, ({ m, q }) => { need(); const id = +m[1]!; return paginate(store.enrollments.filter((e) => e.run_id === id), q); });
 on("POST", /^\/runs\/(\d+)\/candidates:search$/, ({ m, body }) => {
    write(); const run = store.runs.find((r) => r.id === +m[1]!); if (!run) throw notFound("دوره");
    const nonYes = nonYesByEmp(); const includeFlagged = body?.include_flagged !== false;
    const candidates: Candidate[] = []; const excluded: ExcludedCandidate[] = [];
    store.enrollments.filter((e) => e.run_id === null && e.run_name_fa === (body?.course_name ?? run.course_name_fa) && e.status !== "cancelled").forEach((e) => {
      const clash = store.enrollments.filter((x) => x.emp_no === e.emp_no && x.run_id !== null && x.run_id !== run.id).find((x) => { const r = store.runs.find((rr) => rr.id === x.run_id)!; return r.start_date <= run.end_date && r.end_date >= run.start_date; });
      if (clash) { excluded.push({ enrollment_id: e.id, ticket: e.ticket, reason: "date_overlap", conflicting_ticket: clash.ticket }); return; }
      const emp = store.employees.find((x) => x.emp_no === e.emp_no)!;
      const flags: CandidateFlag[] = [];
      if ((nonYes.get(e.emp_no) ?? 0) > store.automation.over3_threshold) flags.push("over_motivation_limit");
      if (emp.status === "inactive") flags.push("non_active");
      if (flags.length && !includeFlagged) { excluded.push({ enrollment_id: e.id, ticket: e.ticket, reason: flags.join(","), conflicting_ticket: "" }); return; }
      candidates.push({ enrollment_id: e.id, emp_no: e.emp_no, name_fa: e.name_fa, division: e.division, ticket: e.ticket, flags });
    });
    return { candidates, excluded, total: candidates.length };
  });

  on("GET", /^\/enrollments$/, ({ q }) => {
    need();
    let items = store.enrollments.filter((e) => matchQ(q.get("q"), e.name_fa, e.emp_no, e.ticket, e.run_name_fa));
    if (q.get("run_id")) items = items.filter((e) => e.run_id === Number(q.get("run_id")));
    if (q.get("motivation")) items = items.filter((e) => e.motivation === q.get("motivation"));
    return paginate(sortBy(items, q.get("sort"), "-id"), q);
  });
  on("PATCH", /^\/enrollments\/(\d+)$/, ({ m, body }) => {
    write(); const e = store.enrollments.find((x) => x.id === +m[1]!); if (!e) throw notFound("ثبت‌نام");
    if (body.attendance === "attended" && (store.runs.find((r) => r.id === e.run_id)?.start_date ?? "0") > store.today) throw invalid({ attendance: "پیش از شروع دوره نمی‌توان حضور را ثبت کرد." });
    for (const k of ["motivation", "registration", "calendar", "attendance"] as const) if (body[k] !== undefined) (e as any)[k] = body[k];
    log("enrollment.update", "enrollment", e.id); return e;
  });
 on("POST", /^\/enrollments:bulk$/, ({ body }) => {
    write(); const updated: number[] = []; const failed: { id: number; reason: string }[] = [];
    const run = body.run_id ? store.runs.find((r) => r.id === body.run_id) : undefined;
    if (body.run_id && !run) throw notFound("دوره");
    for (const id of new Set<number>(body.enrollment_ids ?? [])) {
      const e = store.enrollments.find((x) => x.id === id);
      if (!e) { failed.push({ id, reason: "not_found" }); continue; }
      if (run) {
        if (store.enrollments.some((x) => x.run_id === run.id && x.emp_no === e.emp_no)) { failed.push({ id, reason: "conflict" }); continue; }
        e.run_id = run.id; e.run_name_fa = run.course_name_fa;
      }
      if (body.unassign) e.run_id = null;
      Object.assign(e, body.patch ?? {}); updated.push(id);
    }
    log("enrollment.bulk", "enrollment", "-", `${updated.length} مورد`);
    return { updated, failed };
  });

  on("GET", /^\/letters$/, ({ q }) => { need(); return paginate(sortBy(store.letters, q.get("sort"), "-id"), q); });
  on("POST", /^\/letters\/preview$/, ({ body }) => { write(); const { html, missing } = renderLetter(body); return { html, missing_fields: missing }; });
  on("POST", /^\/letters$/, ({ body }) => {
    write(); const { missing } = renderLetter(body);
    if (Object.keys(missing).length) throw invalid(missing, "برای ساخت نامه ابتدا فیلدهای خالی را کامل کنید.");
    const id = store.seq.letter++;
    const l: Letter = { id, kind: body.kind, run_id: body.run_id ?? null, number: `TD-1405/${String(150 + id).padStart(4, "0")}`, state: "rendered", created_at: new Date().toISOString(), created_by: sessionUser ?? "-", file_name: `${body.kind}-${id}.docx`, subject: `${KIND_FA[body.kind as LetterKind]} — ${store.runs.find((r) => r.id === body.run_id)?.course_name_fa ?? ""}` };
    store.letters.unshift(l); log("letter.create", "letter", id); return l;
  });
  on("GET", /^\/letters\/(\d+)\/download$/, ({ m }) => { need(); const l = store.letters.find((x) => x.id === +m[1]!); if (!l) throw notFound("نامه"); return { __blob: true, name: l.file_name }; });

  on("POST", /^\/email\/send$/, ({ body }) => {
    write(); const b = body as EmailSendRequest & { idempotency_key?: string };
    const cached = b.idempotency_key ? store.idempotency.get(b.idempotency_key) : undefined;
    if (cached) return cached;
    if (!b.recipients?.length) throw invalid({ recipients: "حداقل یک گیرنده لازم است." });
    const bad = b.recipients.filter((r) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(r.email));
    if (bad.length) throw invalid({ recipients: `نشانی ایمیل نامعتبر: ${bad[0]!.email}` });
    const results = b.recipients.map((r) => ({ email: r.email, status: (b.dry_run ? "dry_run" : r.email.includes("bounce") ? "failed" : "sent") as "sent" | "failed" | "dry_run", ...(r.email.includes("bounce") && !b.dry_run ? { error: "صندوق گیرنده پر است (۵۵۲)." } : {}) }));
    const id = store.seq.message++;
    const l = store.letters.find((x) => x.id === b.letter_id);
    store.messages.unshift({ id, subject: b.subject ?? (l ? `${KIND_FA[l.kind]} ${l.number}` : "پیام"), letter_id: b.letter_id ?? null, recipients_count: results.length, failed_count: results.filter((r) => r.status === "failed").length, dry_run: b.dry_run, sent_at: new Date().toISOString(), sent_by: sessionUser ?? "-", results: results.map((r) => ({ email: r.email.toLowerCase(), ok: r.status !== "failed" })) });
    if (!b.dry_run && l) l.state = "sent";
    log("email.send", "message", id, b.dry_run ? "آزمایشی" : `${results.length} گیرنده`);
    const out: EmailSendResult = { dry_run: b.dry_run, results, message_id: id };
    if (b.idempotency_key) store.idempotency.set(b.idempotency_key, out);
    return out;
  });
  on("GET", /^\/messages$/, ({ q }) => { write(); return paginate(store.messages, q); });

  on("GET", /^\/connectors$/, () => { need("admin", "hr"); return { items: store.connectors }; });
  on("PUT", /^\/connectors\/(\w+)$/, ({ m, body }) => {
    need("admin"); const c = store.connectors.find((x) => x.kind === m[1]); if (!c) throw notFound("اتصال");
    const errs: Record<string, string> = {};
    if (body.config?.port !== undefined && !(Number(body.config.port) > 0 && Number(body.config.port) < 65536)) errs.port = "درگاه باید بین ۱ تا ۶۵۵۳۵ باشد.";
    if (body.config?.base_url && !/^https?:\/\//.test(String(body.config.base_url))) errs.base_url = "نشانی باید با http:// یا https:// شروع شود.";
    if (Object.keys(errs).length) throw invalid(errs);
    if (body.enabled !== undefined) c.enabled = body.enabled;
    if (body.config) Object.assign(c.config, body.config);
    for (const [k, v] of Object.entries(body.secrets ?? {})) if (typeof v === "string" && v !== "") c.secrets[k] = "set"; // value is discarded: write-only
    c.last_test = null; log("connector.update", "connector", c.kind);
    return c;
  });
  on("POST", /^\/connectors\/(\w+):test$/, ({ m }) => {
    need("admin"); const c = store.connectors.find((x) => x.kind === m[1]); if (!c) throw notFound("اتصال");
    const empty = Object.entries(c.config).find(([k, v]) => ["base_url", "host", "path", "tenant_id"].includes(k) && !String(v));
    const ok = !empty && c.kind !== "smtp";
    const message = empty ? `فیلد «${empty[0]}» تنظیم نشده است.` : ok ? "اتصال برقرار شد." : "اتصال به سرور پست ایجاد نشد (مهلت به پایان رسید).";
    c.last_test = { ok, at: new Date().toISOString(), message };
    return { ok, message, latency_ms: ok ? 120 + Math.floor(Math.random() * 200) : undefined };
  });
  on("POST", /^\/sync\/(excel|ifs):run$/, ({ m }) => {
    need("admin", "hr"); const kind = m[1] as "excel" | "ifs"; const c = store.connectors.find((x) => x.kind === (kind as ConnectorKind))!;
    const now = new Date().toISOString();
    const s: SyncRun = { id: store.seq.sync++, kind, started_at: now, finished_at: now, status: c.enabled ? "ok" : "failed", created: c.enabled ? 2 : 0, updated: c.enabled ? 14 : 0, errors: c.enabled ? 0 : 1, message: c.enabled ? "همگام‌سازی کامل شد." : "اتصال غیرفعال است.", error_list: c.enabled ? [] : [{ sheet: "", row: null, column: "", code: "source_error", reason: "اتصال غیرفعال است." }] };
    store.syncRuns.unshift(s); log("sync.run", "sync", s.id, kind); return s;
  });
  on("GET", /^\/sync\/runs$/, ({ q }) => { need(); let items = store.syncRuns; if (q.get("kind")) items = items.filter((s) => s.kind === q.get("kind")); return paginate(items, q); });

  on("GET", /^\/automation\/due$/, () => { need(); return { items: due() }; });
  on("POST", /^\/automation\/run$/, () => { write(); const d = due(); log("automation.run", "automation", "-", `${d.length} مورد`); store.automationInfo.last_run = { at: new Date().toISOString(), total: d.length }; return { total: d.length, message: `${toFa(d.length)} مورد بررسی شد.` }; });
 on("GET", /^\/automation\/settings$/, () => { need(); return { settings: store.automation, ...store.automationInfo }; });
  on("PUT", /^\/automation\/settings$/, ({ body }) => {
    need("admin"); const errs: Record<string, string> = {};
    if (!(body.level3_after_days >= 1 && body.level3_after_days <= 365)) errs.level3_after_days = "تعداد روز باید بین ۱ تا ۳۶۵ باشد.";
    if (!(body.reminder_days >= 0 && body.reminder_days <= 60)) errs.reminder_days = "یادآوری باید بین ۰ تا ۶۰ روز باشد.";
    if (!(body.over3_threshold >= 1)) errs.over3_threshold = "سقف باید عدد مثبت باشد.";
    if (Object.keys(errs).length) throw invalid(errs);
    Object.assign(store.automation, body); log("automation.settings", "automation", "-"); return { settings: store.automation, ...store.automationInfo };
  });

  const doImport = (kind: string) => ({ file }: Ctx): ImportResult => {
    write();
    if (!file || !/\.xlsx$/i.test(file.name)) throw invalid({ file: "فقط فایل با پسوند xlsx پذیرفته می‌شود." });
    if (/bad/i.test(file.name)) throw new HttpErr(422, "validation", "ساختار فایل شناخته نشد؛ ردیف عنوان (ردیف ۵) پیدا نشد.", { file: "ردیف عنوان پیدا نشد." });
    log("import." + kind, "import", "-", file.name);
    return { created: 24, updated: 6, skipped: 2, error_count: 2, errors: [{ sheet: "idp", row: 14, column: "Employee ID", code: "unknown_employee", reason: "شناسهٔ کارمند در فهرست IFS پیدا نشد." }, { sheet: "idp", row: 37, column: "Course Start Date", code: "bad_date", reason: "تاریخ شروع قابل خواندن نیست." }] };
  };
  on("POST", /^\/import\/idp$/, doImport("idp"));
  on("POST", /^\/import\/legacy-workbook$/, doImport("legacy"));
  on("GET", /^\/export\/legacy\.xlsx$/, () => { write(); return { __blob: true, name: "legacy-export.xlsx" }; });

  on("GET", /^\/users$/, ({ q }) => { need("admin"); return paginate(store.users.map(({ password: _p, ...u }) => { void _p; return u; }), q); });
  on("POST", /^\/users$/, ({ body }) => {
    need("admin"); const errs: Record<string, string> = {};
    if (!body.username?.trim()) errs.username = "نام کاربری را وارد کنید."; else if (store.users.some((u) => u.username === body.username)) errs.username = "این نام کاربری قبلاً ثبت شده است.";
    if (!body.full_name?.trim()) errs.full_name = "نام کامل را وارد کنید.";
    if ((body.password ?? "").length < 8) errs.password = "گذرواژه باید دست‌کم ۸ نویسه باشد.";
    if (Object.keys(errs).length) throw invalid(errs);
    const u = { id: store.seq.user++, username: body.username, full_name: body.full_name, role: body.role as Role, active: true, last_login: null, password: body.password };
    store.users.push(u); log("user.create", "user", u.id); const { password: _p, ...pub } = u; void _p; return pub;
  });
  on("GET", /^\/audit$/, ({ q }) => {
    need("admin");
    let items = store.audit.filter((a) => matchQ(q.get("q"), a.user, a.action, a.entity_id, a.detail));
    if (q.get("user")) items = items.filter((a) => a.user === q.get("user"));
    if (q.get("action")) items = items.filter((a) => a.action === q.get("action"));
    if (q.get("from")) items = items.filter((a) => a.at.slice(0, 10) >= q.get("from")!);
    if (q.get("to")) items = items.filter((a) => a.at.slice(0, 10) <= q.get("to")!);
    return paginate(items, q);
  });
  on("PATCH", /^\/users\/(\d+)$/, ({ m, body }) => {
    need("admin"); const u = store.users.find((x) => x.id === +m[1]!); if (!u) throw notFound("کاربر");
    const errs: Record<string, string> = {};
    if (body.password !== undefined && String(body.password).length < 8) errs.password = "گذرواژه باید دست‌کم ۸ نویسه باشد.";
    if (body.role !== undefined && !["admin", "hr", "viewer"].includes(body.role)) errs.role = "نقش نامعتبر است.";
    if (Object.keys(errs).length) throw invalid(errs);
    const admins = store.users.filter((x) => x.role === "admin" && x.active);
    const losing = u.role === "admin" && u.active && admins.length === 1 && ((body.is_active === false) || (body.role && body.role !== "admin"));
    if (losing) throw new HttpErr(409, "conflict", "آخرین مدیر فعال را نمی‌توان غیرفعال یا تنزل داد.");
    if (body.is_active !== undefined) u.active = !!body.is_active;
    if (body.role) u.role = body.role; if (body.display_name) u.full_name = body.display_name; if (body.password) u.password = body.password;
    log("user.update", "user", u.id, Object.keys(body).filter((k) => k !== "password").join(",")); const { password: _p, ...pub } = u; void _p; return pub;
  });
  on("GET", /^\/institutes$/, ({ q }) => { need(); return paginate(store.institutes.filter((i) => matchQ(q.get("q"), i.name, i.name_fa)), q); });
  on("POST", /^\/institutes$/, ({ body }) => {
    write(); const errs: Record<string, string> = {};
    if (!String(body.name ?? "").trim()) errs.name = "نام مؤسسه را وارد کنید.";
    else if (store.institutes.some((i) => i.name === body.name.trim())) errs.name = "مؤسسه‌ای با این نام وجود دارد.";
    if (body.contact_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.contact_email)) errs.contact_email = "ایمیل معتبر نیست.";
    if (Object.keys(errs).length) throw invalid(errs);
    const i = { id: store.seq.institute++, name: body.name.trim(), name_fa: body.name_fa ?? "", supplier_code: body.supplier_code ?? "", contact_email: body.contact_email ?? "" };
    store.institutes.push(i); log("institute.create", "institute", i.id); return i;
  });
  on("GET", /^\/health$/, () => ({ status: "ok" }));
  on("GET", /^\/ready$/, () => ({ status: "ready" }));

  const jsonRes = (status: number, body: unknown, headers: Record<string, string> = {}) =>
    new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, ...headers } });

  const fetchImpl = async (input: string, init: RequestInit = {}): Promise<Response> => {
    if (latency) await new Promise((r) => setTimeout(r, latency * (0.6 + Math.random() * 0.8)));
    const method = (init.method ?? "GET").toUpperCase();
    const url = new URL(input, "http://mock.local");
    const path = url.pathname.replace(/^\/api\/v1/, "");
    try {
      if (method !== "GET" && method !== "HEAD" && !path.startsWith("/auth/login")) {
        const h = new Headers(init.headers); const u = user();
        if (u && h.get("X-CSRF-Token") !== csrfToken) throw forbidden();
      }
      let body: any = undefined; let file: Ctx["file"];
      if (init.body instanceof FormData) { const f = init.body.get("file"); if (f instanceof File) file = { name: f.name, size: f.size }; }
      else if (typeof init.body === "string") { try { body = JSON.parse(init.body); } catch { throw invalid({}, "بدنهٔ درخواست معتبر نیست.") } }
      for (const [mth, re, h] of routes) {
        if (mth !== method) continue; const m = re.exec(path); if (!m) continue;
        const out = h({ q: url.searchParams, body, path, m, file }) as any;
        if (out === null) return jsonRes(204, null);
        if (out?.__blob) return new Response(new Blob([`synthetic ${out.name}`]), { status: 200, headers: { "Content-Disposition": `attachment; filename="${out.name}"`, "Content-Type": "application/octet-stream", "X-CSRF-Token": csrfToken } });
        return jsonRes(200, out);
      }
      throw notFound("آدرس");
    } catch (e) {
      if (e instanceof HttpErr) return jsonRes(e.status, { error: { code: e.code, message: e.message, ...(e.fields ? { fields: e.fields } : {}) } });
      return jsonRes(500, { error: { code: "unknown", message: "خطای داخلی نمونه‌سرور." } });
    }
  };
  return { fetch: fetchImpl, store };
}
