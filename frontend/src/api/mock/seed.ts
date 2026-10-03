// Synthetic, deterministic demo data. Names are random combinations of common Persian given
// names and surnames: no real person, no real national codes or phone numbers.
import { addDaysISO, todayISO } from "../../lib/jalali";
import type {
  AuditEntry, AutomationInfo, Institute, AutomationSettings, Connector, Course, CourseRun, Employee, Enrollment, Letter, MessageLog,
  RunStatus, SyncRun, User, Tri,
} from "../types";

export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface StoredEmployee extends Employee { raw_mobile: string; raw_national_code: string }
export interface Store {
  today: string;
  users: (User & { password: string })[];
  institutes: Institute[]; employees: StoredEmployee[]; courses: Course[]; runs: CourseRun[]; enrollments: Enrollment[];
  letters: Letter[]; messages: MessageLog[]; connectors: Connector[]; syncRuns: SyncRun[]; audit: AuditEntry[];
  automation: AutomationSettings; automationInfo: AutomationInfo; idempotency: Map<string, unknown>;
  seq: { letter: number; message: number; audit: number; sync: number; enrollment: number; run: number; user: number; institute: number };
}

const FIRST: [string, string, "male" | "female"][] = [
  ["علی", "Ali", "male"], ["مریم", "Maryam", "female"], ["رضا", "Reza", "male"], ["سارا", "Sara", "female"],
  ["حسین", "Hossein", "male"], ["زهرا", "Zahra", "female"], ["محمد", "Mohammad", "male"], ["نرگس", "Narges", "female"],
  ["امیر", "Amir", "male"], ["فاطمه", "Fatemeh", "female"], ["مهدی", "Mahdi", "male"], ["الهام", "Elham", "female"],
  ["پویا", "Pouya", "male"], ["شیوا", "Shiva", "female"], ["کاوه", "Kaveh", "male"], ["ندا", "Neda", "female"],
  ["بهنام", "Behnam", "male"], ["لیلا", "Leila", "female"], ["سعید", "Saeed", "male"], ["مینا", "Mina", "female"],
];
const LAST: [string, string][] = [
  ["احمدی", "Ahmadi"], ["کریمی", "Karimi"], ["حسینی", "Hosseini"], ["رحیمی", "Rahimi"], ["صادقی", "Sadeghi"],
  ["موسوی", "Mousavi"], ["نوری", "Nouri"], ["قاسمی", "Ghasemi"], ["یزدانی", "Yazdani"], ["فرهادی", "Farhadi"],
  ["امینی", "Amini"], ["طاهری", "Taheri"], ["برزگر", "Barzegar"], ["اسدی", "Asadi"], ["مرادی", "Moradi"],
];
export const DIVISIONS = ["منابع انسانی", "فناوری اطلاعات", "مالی", "بازاریابی", "شبکه", "خدمات مشتریان", "حقوقی", "تحلیل داده"];
export const INSTITUTES = ["مؤسسه توسعه فردا", "آکادمی آریا", "مرکز آموزش پارسیان", "اسکیل‌لب"];

const COURSES: [string, string, string, "online" | "in_person"][] = [
  ["مدیریت زمان", "Time Management", "مهارت نرم", "online"],
  ["رهبری تیم‌های چابک", "Agile Team Leadership", "مهارت نرم", "in_person"],
  ["مذاکرهٔ مؤثر", "Effective Negotiation", "مهارت نرم", "in_person"],
  ["تحلیل داده با Power BI", "Data Analysis with Power BI", "فنی", "online"],
  ["مدیریت پروژه (PMP)", "Project Management (PMP)", "فنی", "in_person"],
  ["ارتباط مؤثر", "Effective Communication", "مهارت نرم", "online"],
  ["امنیت سایبری مقدماتی", "Cyber Security Basics", "فنی", "online"],
  ["تفکر طراحی", "Design Thinking", "مهارت نرم", "in_person"],
];

const DAYS = ["شنبه و دوشنبه", "یکشنبه و سه‌شنبه", "چهارشنبه", "شنبه تا چهارشنبه", "پنجشنبه"];
const TIMES = ["۰۹:۰۰ تا ۱۶:۰۰", "۰۸:۳۰ تا ۱۲:۳۰", "۱۴:۰۰ تا ۱۸:۰۰"];

export function makeStore(seed = 1405, today = todayISO()): Store {
  const r = rng(seed);
  const pick = <T,>(a: readonly T[]) => a[Math.floor(r() * a.length)]!;
  const digits = (n: number) => Array.from({ length: n }, () => Math.floor(r() * 10)).join("");
  const iso = (off: number) => addDaysISO(today, off);
  const at = (off: number, h = 10, m = 0) => {
    const d = new Date(`${iso(off)}T00:00:00`); d.setHours(h, m); return d.toISOString();
  };

  const employees: StoredEmployee[] = [];
  const used = new Set<string>();
  while (employees.length < 84) {
    const [fa, en, gender] = pick(FIRST); const [lfa, len] = pick(LAST);
    const key = fa + lfa; if (used.has(key)) continue; used.add(key);
    const i = employees.length;
    const raw_mobile = `0990${digits(7)}`; const raw_national_code = digits(10);
    employees.push({
      emp_no: String(71000 + i * 7), name_fa: `${fa} ${lfa}`, name_en: `${en} ${len}`, gender,
      email: `${en.toLowerCase()}.${len.toLowerCase()}${i}@example.test`,
      mobile: `${raw_mobile.slice(0, 4)}***${raw_mobile.slice(7)}`, national_code: `******${raw_national_code.slice(6)}`,
      raw_mobile, raw_national_code,
      division: pick(DIVISIONS), cost_center: `CC${1000 + Math.floor(r() * 40)}`,
      supervisor_emp_no: i < 6 ? null : String(71000 + Math.floor(r() * 6) * 7),
      status: i % 17 === 5 ? "inactive" : "active", job_title: pick(["کارشناس", "کارشناس ارشد", "سرپرست", "مدیر"]),
    });
  }

  const courses: Course[] = COURSES.map(([fa, en, category, delivery], i) => ({ id: i + 1, name_fa: fa, name_en: en, category, delivery, duration_h: [8, 16, 12, 24, 40, 8, 16, 12][i] ?? 12, active: true }));

  // [course index, start offset, length days, status, amount (million Rial), payment started]
  const plan: [number, number, number, RunStatus, number | null, boolean][] = [
    [0, 35, 2, "planned", null, false], [1, 26, 3, "planned", null, false], [2, 21, 2, "announced", null, false],
    [3, 12, 3, "announced", null, false], [4, 6, 5, "open", 480, false], [5, -4, 2, "completed", 260, false],
    [6, -14, 3, "completed", 300, false], [7, -27, 2, "completed", 210, true], [0, -50, 2, "completed", 150, true],
    [2, -75, 2, "completed", 240, true], [3, -120, 3, "completed", 360, true], [5, -160, 2, "cancelled", 180, false],
  ];
  const runs: CourseRun[] = plan.map(([ci, off, len, status, amt, paid], i) => {
    const c = courses[ci]!; const start = iso(off); const early = i < 2;
    return {
      id: i + 1, course_id: c.id, course_name_fa: c.name_fa, course_name_en: c.name_en, type: c.delivery,
      institute: INSTITUTES[i % INSTITUTES.length]!, duration_h: len * 6, start_date: start, end_date: addDaysISO(start, len - 1),
      days: DAYS[i % DAYS.length]!, time: TIMES[i % TIMES.length]!, sessions: len,
      send_date: early ? null : addDaysISO(start, -14), deadline: early ? null : addDaysISO(start, -7),
      amount: amt === null ? null : amt * 1_000_000, section_b: early || status === "announced" ? null : `MTC-${5200 + i}`, link: "",
      status, enrollment_count: 0, motivation_yes_count: 0, payment_started: paid, counts_known: true,
    };
  });

  const supEmail = (e: StoredEmployee) => employees.find((x) => x.emp_no === e.supervisor_emp_no)?.email ?? "";
  const enrollments: Enrollment[] = [];
  const active = employees.filter((e) => e.status === "active");
  runs.forEach((run, ri) => {
    if (ri === 0) return; // a brand-new run with nobody enrolled
    const n = 7 + ((ri * 3) % 6);
    for (let k = 0; k < n; k++) {
      const emp = active[(ri * 9 + k * 5) % active.length]!;
      const past = run.end_date < today;
      const moti = (ri === 1 || ri === 2) ? "pending"
        : ((ri === 3 && k < 5) ? (k < 4 ? "no" : "pending") : (r() < 0.85 ? "yes" : (r() < 0.5 ? "no" : "pending")));
      enrollments.push({
        id: enrollments.length + 1, run_id: run.id, run_name_fa: run.course_name_fa, emp_no: emp.emp_no, name_fa: emp.name_fa,
        division: emp.division, ticket: `LMS-${21000 + enrollments.length * 3}`, status: past ? "completed" : "enrolled",
        motivation: moti as Tri, registration: moti === "yes" && r() < 0.8 ? "yes" : "pending", calendar: moti === "yes" && r() < 0.6 ? "yes" : "pending",
        attendance: past ? (r() < 0.9 ? "attended" : "absent") : "pending", level3_status: run.payment_started ? "Evaluation Level 3" : "-", email: emp.email, supervisor_email: supEmail(emp),
      });
    }
  });
  // Unassigned IDP requests (what "candidates" are): several per upcoming course, some flagged.
  runs.slice(0, 5).forEach((run, ri) => {
    for (let k = 0; k < 8; k++) {
      const emp = employees[(ri * 11 + k * 7 + 3) % employees.length]!;
      if (enrollments.some((e) => e.run_id === run.id && e.emp_no === emp.emp_no) || enrollments.some((e) => e.run_id === null && e.emp_no === emp.emp_no && e.run_name_fa === run.course_name_fa)) continue;
      enrollments.push({
        id: enrollments.length + 1, run_id: null, run_name_fa: run.course_name_fa, emp_no: emp.emp_no, name_fa: emp.name_fa, division: emp.division,
        ticket: `LMS-${21000 + enrollments.length * 3}`, status: "requested", motivation: "pending", registration: "pending", calendar: "pending", attendance: "pending", level3_status: "-", email: emp.email, supervisor_email: supEmail(emp),
      });
    }
  });

  const users = [
    { id: 1, username: "admin", full_name: "مدیر سامانه (نمایشی)", role: "admin" as const, active: true, last_login: at(0, 8, 12), password: "demo" },
    { id: 2, username: "hr", full_name: "کارشناس آموزش (نمایشی)", role: "hr" as const, active: true, last_login: at(-1, 15, 40), password: "demo" },
    { id: 3, username: "viewer", full_name: "ناظر (نمایشی)", role: "viewer" as const, active: true, last_login: at(-3, 9, 5), password: "demo" },
    { id: 4, username: "guest.old", full_name: "کاربر غیرفعال (نمایشی)", role: "viewer" as const, active: false, last_login: at(-90), password: "demo" },
  ];

  const letters: Letter[] = [
    { id: 1, kind: "course_announcement", run_id: 3, number: "TD-1405/0141", state: "sent", created_at: at(-8), created_by: "hr", file_name: "announcement-3.docx", subject: "اطلاعیهٔ دورهٔ مذاکرهٔ مؤثر" },
    { id: 2, kind: "institute_letter", run_id: 5, number: "TD-1405/0152", state: "rendered", created_at: at(-2), created_by: "hr", file_name: "institute-5.docx", subject: "نامهٔ مؤسسه — مدیریت پروژه" },
    { id: 3, kind: "settlement_letter", run_id: 6, number: "TD-1405/0153", state: "rendered", created_at: at(-1), created_by: "admin", file_name: "settlement-6.docx", subject: "نامهٔ تسویه — ارتباط مؤثر" },
  ];
  const messages: MessageLog[] = [
    { id: 1, subject: "اطلاعیهٔ برگزاری دورهٔ رهبری تیم‌های چابک", letter_id: 1, recipients_count: 9, failed_count: 0, dry_run: false, sent_at: at(-8, 11), sent_by: "hr", results: [] },
    { id: 2, subject: "اطلاعیهٔ برگزاری دورهٔ مذاکرهٔ مؤثر", letter_id: 1, recipients_count: 8, failed_count: 1, dry_run: false, sent_at: at(-5, 10, 30), sent_by: "hr", results: enrollments.filter((e) => e.run_id === 3).slice(0, 4).map((e) => ({ email: e.email.toLowerCase(), ok: true })) },
  ];
  const connectors: Connector[] = [
    { kind: "excel", enabled: true, config: { path: "\\\\fileserver\\training\\IDP-export.xlsx", watch_dir: "/data/incoming" }, secrets: {}, last_test: { ok: true, at: at(-1, 9), message: "فایل خوانده شد؛ ۱۲۴ ردیف." } },
    { kind: "ifs", enabled: true, config: { base_url: "https://ifs.example.test/main", auth_mode: "oauth2_client_credentials", client_id: "tms-client", token_url: "https://iam.example.test/token", username: "", login_url: "" }, secrets: { client_secret: "set", password: "not_set" }, last_test: { ok: true, at: at(-1, 9, 2), message: "توکن دریافت شد." } },
    { kind: "smtp", enabled: true, config: { host: "smtp.example.test", port: 587, username: "tms-mailer", from_addr: "training@example.test", starttls: true }, secrets: { password: "set" }, last_test: { ok: false, at: at(-2, 14), message: "اتصال به سرور پست ایجاد نشد (مهلت به پایان رسید)." } },
    { kind: "graph", enabled: false, config: { tenant_id: "", client_id: "", sender: "" }, secrets: { client_secret: "not_set" }, last_test: null },
  ];
  const syncRuns: SyncRun[] = [
    { id: 1, kind: "excel", started_at: at(-1, 6, 0), finished_at: at(-1, 6, 1), status: "ok", created: 12, updated: 41, errors: 0, message: "همگام‌سازی کامل شد.", error_list: [] },
    { id: 2, kind: "ifs", started_at: at(-1, 6, 5), finished_at: at(-1, 6, 7), status: "ok", created: 0, updated: 9, errors: 0, message: "۹ کارمند به‌روزرسانی شد.", error_list: [] },
    { id: 3, kind: "ifs", started_at: at(-2, 6, 5), finished_at: at(-2, 6, 6), status: "failed", created: 0, updated: 0, errors: 1, message: "خطای احراز هویت (۴۰۱): توکن دریافت نشد.", error_list: [{ sheet: "", row: null, column: "", code: "source_error", reason: "خطای احراز هویت (۴۰۱): توکن دریافت نشد." }] },
    { id: 4, kind: "excel", started_at: at(-2, 6, 0), finished_at: at(-2, 6, 1), status: "ok", created: 3, updated: 7, errors: 2, message: "دو ردیف نامعتبر نادیده گرفته شد.", error_list: [{ sheet: "idp", row: 14, column: "Employee ID", code: "unknown_employee", reason: "شناسهٔ کارمند در فهرست IFS پیدا نشد." }, { sheet: "idp", row: 37, column: "Course Start Date", code: "bad_date", reason: "تاریخ شروع قابل خواندن نیست." }] },
  ];
  const actions = ["login", "employee.reveal", "letter.create", "email.send", "sync.run", "run.update", "enrollment.update", "connector.update"];
  const audit: AuditEntry[] = Array.from({ length: 48 }, (_, i) => {
    const u = users[i % 3]!; const a = actions[(i * 3) % actions.length]!;
    return { id: 48 - i, at: at(-Math.floor(i / 4), 8 + (i % 9), (i * 7) % 60), user: u.username, action: a, entity: a.split(".")[0]!, entity_id: String(1 + ((i * 5) % 12)), ip: `10.20.${i % 5}.${10 + i}`, detail: a === "employee.reveal" ? "نمایش کد ملی و موبایل" : "-" };
  });

  return {
    today, users, institutes: INSTITUTES.map((n, i) => ({ id: i + 1, name: n, name_fa: n, supplier_code: `SUP-${100 + i}`, contact_email: `info${i + 1}@example.test` })), employees, courses, runs, enrollments, letters, messages, connectors, syncRuns, audit,
    automation: { enabled: true, level3_after_days: 60, reminder_days: 7, over3_threshold: 3, letter_number_prefix: "TD-1405/", settlement_addressee: "واحد مالی", letter_signer_name: "تیم توسعه استعداد", letter_signer_title: "منابع انسانی", letter_signer_email: "training@example.test", letter_signer_phone: "", company_economic_code: "", company_national_id: "", company_postal_code: "", company_address: "" },
    automationInfo: { last_run: null, loop_enabled: true },
    idempotency: new Map(),
    seq: { letter: 4, message: 3, audit: 49, sync: 5, enrollment: enrollments.length + 1, run: runs.length + 1, user: 5, institute: INSTITUTES.length + 1 },
  };
}
