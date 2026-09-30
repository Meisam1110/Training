// Anti-corruption layer between the backend's actual JSON (backend/app/api/services/serializers.py,
// backend/app/schemas/domain.py) and the UI types in types.ts. Used only for the real backend
// (the in-memory mock already speaks UI types). Everything here is covered by wire.test.ts using
// payloads captured from the running backend.
import type {
  AuditEntry, Attendance, ImportError, Institute, NewInstitute, RunWorkflow, UserPatch, AutomationSettings, BulkEnrollmentRequest, Candidate, CandidateFlag, CandidateResult, Connector,
  ConnectorKind, ConnectorUpdate, Course, CourseRun, Dashboard, DashItem, DueItem, EmailSendRequest, EmailSendResult, Employee,
  Enrollment, EnrollmentPatch, ImportResult, Letter, LetterPreview, LetterRequest, MessageLog, RunInput, RunStatus, SyncRun, Tri, User,
} from "./types";
import { SECRET_KEYS } from "./types";
import { toFa } from "../lib/digits";

/** Isolate an embedded Latin string so it cannot reorder the surrounding Persian text (bidi). */
const iso = (x: unknown) => `\u2068${x ?? ""}\u2069`;

type J = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

// ---------- tri-state / attendance ----------
export const triFrom = (v: unknown): Tri => { const s = String(v ?? "").trim().toLowerCase(); return /^(yes|true|done|ok|1)$/.test(s) ? "yes" : /^(no|false|0)$/.test(s) ? "no" : "pending"; };
export const triTo = (v: Tri | string): string => (v === "yes" ? "Yes" : v === "no" ? "No" : "");
export const attFrom = (v: unknown): Attendance => { const s = String(v ?? "").trim().toLowerCase(); return s.startsWith("attend") || s === "yes" ? "attended" : s.startsWith("absent") || s === "no" ? "absent" : "pending"; };
export const attTo = (v: Attendance | string): string => (v === "attended" ? "Attended" : v === "absent" ? "Absent" : "-"); // "-" is the workbook's "not recorded"

// ---------- entities ----------
export const user = (u: J): User => ({ id: u.id, username: u.username, full_name: u.display_name || u.username, role: u.role, active: !!u.is_active, last_login: u.last_login_at ?? null });
export const institute = (i: J): Institute => ({ id: i.id, name: i.name, name_fa: i.name_fa ?? "", supplier_code: i.supplier_code ?? "", contact_email: i.contact_email ?? "" });
export const instituteBody = (b: NewInstitute): J => ({ name: b.name, name_fa: b.name_fa, supplier_code: b.supplier_code, contact_email: b.contact_email });
export const employee = (e: J): Employee => ({
  emp_no: e.emp_no, name_fa: `${e.first_name_fa ?? ""} ${e.last_name_fa ?? ""}`.trim() || `${e.first_name_en} ${e.last_name_en}`,
  name_en: `${e.first_name_en ?? ""} ${e.last_name_en ?? ""}`.trim(), gender: e.gender === "female" ? "female" : "male", email: e.email ?? "",
  mobile: e.mobile ?? "", national_code: e.national_code ?? "", division: e.division ?? "", cost_center: e.cost_center ?? "",
  supervisor_emp_no: e.supervisor_emp_no || null, status: /^active$/i.test(e.status ?? "") ? "active" : "inactive", job_title: e.position_title ?? "",
});
export const course = (c: J): Course => ({ id: c.id, name_fa: c.name_fa || c.name, name_en: c.name, category: c.category ?? "", delivery: "in_person" });
export const run = (r: J): CourseRun => ({
  id: r.id, course_id: r.course_id, course_name_fa: r.course_name_fa || r.course_name, course_name_en: r.course_name, type: r.type, institute: r.institute ?? "",
  duration_h: r.duration_h ?? 0, start_date: r.start_date, end_date: r.end_date ?? r.start_date, days: r.days ?? "", time: r.time ?? "", sessions: r.sessions ?? 0,
  send_date: r.send_date ?? null, deadline: r.deadline ?? null, amount: r.amount ?? null, section_b: r.section_b || null, link: r.link ?? "", status: r.status as RunStatus,
  enrollment_count: r.enrollment_count ?? 0, motivation_yes_count: r.motivation_yes ?? 0, counts_known: r.enrollment_count !== undefined, payment_started: !!(r.payment_process || r.pr_process_start_date || r.invoice_receive_date),
  workflow: r.workflow ? workflowOf(r.workflow) : undefined,
});
const workflowOf = (w: J): RunWorkflow => ({ announced: !!w.announced, motivations_collected: !!w.motivations_collected, institute_letter_sent: !!w.institute_letter_sent, invoice_received: !!w.invoice_received, settlement_sent: !!w.settlement_sent, level3_started: !!w.level3_started });
export const enrollment = (e: J): Enrollment => ({
  id: e.id, run_id: e.run_id ?? null, run_name_fa: e.course_name ?? "", emp_no: e.emp_no, name_fa: e.employee_name_fa || e.employee_name, division: e.division ?? "",
  ticket: e.ticket, status: e.status ?? "", motivation: triFrom(e.motivation), registration: triFrom(e.registration), calendar: triFrom(e.calendar),
  attendance: attFrom(e.attendance), level3_status: e.level3_status ?? "", email: e.email ?? "", supervisor_email: e.supervisor_email ?? "",
});
export const letter = (l: J): Letter => ({ id: l.id, kind: l.kind, run_id: l.run_id ?? null, number: l.number ?? "", state: l.state === "sent" ? "sent" : "rendered", created_at: l.created_at, created_by: l.created_by ?? "", file_name: l.filename ?? "", subject: l.subject ?? "" });
export const message = (m: J): MessageLog => ({
  id: m.id, subject: m.subject ?? "", letter_id: m.letter_id ?? null, recipients_count: (m.recipients ?? []).length,
  failed_count: (m.results ?? []).filter((r: J) => !r.ok).length, dry_run: !!m.dry_run, sent_at: m.created_at, sent_by: "",
  results: (m.results ?? []).map((r: J) => ({ email: String(r.recipient ?? "").toLowerCase(), ok: !!r.ok })),
});
export const sendResult = (r: J): EmailSendResult => ({
  dry_run: !!r.dry_run, message_id: r.id,
  results: (r.results ?? []).map((x: J) => ({ email: x.recipient, status: !x.ok ? "failed" as const : r.dry_run ? "dry_run" as const : "sent" as const, ...(x.error ? { error: String(x.error) } : {}) })),
});
export const connector = (c: J): Connector => {
  const kind = c.kind as ConnectorKind; const set = new Set<string>(c.secrets_set ?? []);
  return {
    kind, enabled: !!c.enabled, config: c.config ?? {},
    secrets: Object.fromEntries(SECRET_KEYS[kind].map((k) => [k, set.has(k) ? "set" as const : "not_set" as const])),
    last_test: c.last_test_ok === null || c.last_test_ok === undefined ? null : { ok: !!c.last_test_ok, at: c.last_test_at, message: c.last_test_message || (c.last_test_ok ? "آخرین آزمون موفق بود." : "آخرین آزمون ناموفق بود.") },
  };
};
const importErrors = (l: unknown): ImportError[] => (Array.isArray(l) ? l : []).map((x: J) => ({ sheet: x.sheet ?? "", row: x.row ?? null, column: x.column ?? "", code: x.code ?? "", reason: x.reason ?? "" }));
export const syncRun = (s: J): SyncRun => {
  const status = s.status === "running" ? "running" : s.status === "ok" ? "ok" : "failed";
  const list = importErrors(s.errors);
  return {
    id: s.id, kind: s.source === "ifs" ? "ifs" : "excel", started_at: s.started_at, finished_at: s.finished_at ?? null, status,
    created: s.created ?? 0, updated: s.updated ?? 0, errors: Array.isArray(s.errors) ? s.errors.length : (s.errors ?? 0), error_list: list,
    message: s.message || (s.status === "partial" ? "با خطاهای جزئی تمام شد." : `${s.unchanged ?? 0} بدون تغییر · ${s.skipped ?? 0} ردشده`),
  };
};
export const audit = (a: J): AuditEntry => ({
  id: a.id, at: a.ts, user: a.actor, action: a.action, entity: a.entity, entity_id: String(a.entity_id ?? ""), ip: a.ip ?? "",
  detail: a.detail && Object.keys(a.detail).length ? Object.entries(a.detail).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join("، ") : "-",
});

// ---------- dashboard / automation ----------
const runItem = (r: J, detail: string): DashItem => ({ key: `run-${r.id}`, title: r.course_name_fa || r.course_name, detail, date: r.start_date ?? null, run_id: r.id });
export const dashboard = (d: J): Dashboard => ({
  not_started_courses: (d.not_started_courses ?? []).map((r: J) => runItem(r, `${toFa(r.days_to_course ?? "?")} روز تا شروع · ${iso(r.institute || "—")}`)),
  payment_not_started: (d.payment_not_started ?? []).map((r: J) => runItem(r, `${toFa(r.days_since_start ?? "?")} روز از شروع · ${iso(r.institute || "—")}`)),
  over3_motivations: (d.over3_motivations ?? []).map((o: J): DashItem => ({ key: `tk-${o.ticket ?? o.emp_no}`, title: o.employee_name, detail: `${toFa(o.non_yes_count)} بار پیشنهاد بدون تأیید · ${iso(o.ticket ?? "")}`, date: null, run_id: (o.run_ids ?? [])[0] ?? null, emp_no: o.emp_no, ticket: o.ticket ?? null })),
  level3_due: (d.level3_due ?? []).map((e: J): DashItem => ({ key: `enr-${e.enrollment_id}`, title: e.employee_name, detail: `${toFa(e.days_since_end)} روز از پایان · ${iso(e.course_name)}`, date: e.end_date, run_id: null, emp_no: e.emp_no })),
  counts: d.counts ?? {},
  last_sync: { excel: syncSummary(d.last_sync?.excel), ifs: syncSummary(d.last_sync?.ifs) },
});
const syncSummary = (s: J | null | undefined) => (s ? { at: s.finished_at ?? s.started_at, status: (s.status === "ok" || s.status === "partial" ? "ok" : s.status === "running" ? "ok" : "failed") as "ok" | "failed" } : { at: null, status: "never" as const });
export const due = (r: J): DueItem[] => (r.items ?? []).map((i: J, n: number): DueItem => ({ id: `${i.kind}-${i.enrollment_id ?? i.run_id ?? n}-${n}`, kind: i.kind, title: i.detail, due_date: null, run_id: i.run_id ?? null, count: 1 }));
export const settings = (s: J): { settings: AutomationSettings; last_run: { at: string; total: number } | null; loop_enabled: boolean } => ({
  settings: { enabled: !!s.enabled, level3_after_days: s.level3_after_days, reminder_days: s.reminder_days, over3_threshold: s.over3_threshold, letter_number_prefix: s.letter_number_prefix ?? "", settlement_addressee: s.settlement_addressee ?? "", letter_signer_name: s.letter_signer_name ?? "", letter_signer_title: s.letter_signer_title ?? "",
    letter_signer_email: s.letter_signer_email ?? "", letter_signer_phone: s.letter_signer_phone ?? "", company_economic_code: s.company_economic_code ?? "", company_national_id: s.company_national_id ?? "", company_postal_code: s.company_postal_code ?? "", company_address: s.company_address ?? "" },
  last_run: s.last_run ?? null, loop_enabled: !!s.loop_enabled,
});

// ---------- candidates / letters / import ----------
export const candidates = (r: J): CandidateResult => ({
  candidates: (r.candidates ?? []).map((e: J): Candidate => ({ enrollment_id: e.id, emp_no: e.emp_no, name_fa: e.employee_name_fa || e.employee_name, division: e.division ?? "", ticket: e.ticket, flags: (e.flags ?? []) as CandidateFlag[] })),
  excluded: (r.excluded ?? []).map((x: J) => ({ enrollment_id: x.enrollment_id, ticket: x.ticket, reason: x.reason, conflicting_ticket: x.conflicting_ticket ?? "" })),
  total: r.total ?? 0,
});
/** Backend 422 for missing template data: fields:{<field>:"required", …} (legacy: {fields:"a, b"}). */
export function missingFromFields(fields: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  if (typeof fields.fields === "string") for (const k of fields.fields.split(",").map((x) => x.trim()).filter(Boolean)) out[k] = `مقدار «${k}» خالی است.`;
  for (const [k, v] of Object.entries(fields)) if (k !== "fields") out[k] = v === "required" ? `مقدار «${k}» خالی است.` : v;
  return out;
}
/** Real backend: a template with missing data answers 502/`upstream` "…missing required field(s): a, b". */
export function missingFromMessage(message: string): Record<string, string> {
  const m = /missing required field\(s\):\s*(.+)$/i.exec(message); const out: Record<string, string> = {};
  if (m) for (const k of m[1]!.split(",").map((x) => x.trim()).filter(Boolean)) out[k] = `مقدار «${k}» خالی است.`;
  return out;
}
export const preview = (p: J): LetterPreview => {
  const mf = p.missing_fields; const out: Record<string, string> = {};
  if (Array.isArray(mf)) mf.forEach((k: string) => { out[k] = `مقدار «${k}» خالی است.`; }); else if (mf && typeof mf === "object") Object.assign(out, missingFromFields(mf));
  return { html: p.html ?? "", subject: p.subject, missing_fields: Object.keys(out).length ? out : undefined };
};
export const importResult = (s: J): ImportResult => { const errors = importErrors(s.errors); return { created: s.created ?? 0, updated: s.updated ?? 0, skipped: s.skipped ?? 0, error_count: Array.isArray(s.errors) ? s.errors.length : (s.errors ?? 0), errors }; };

// ---------- requests (UI -> backend, all schemas are extra=forbid) ----------
export const runBody = (b: RunInput): J => {
  const o: J = { ...b };
  if (o.section_b === null) o.section_b = "";
  for (const k of Object.keys(o)) if (o[k] === undefined) delete o[k];
  return o;
};
export const enrollmentPatchBody = (p: EnrollmentPatch): J => {
  const o: J = {};
  if (p.motivation !== undefined) o.motivation = triTo(p.motivation);
  if (p.registration !== undefined) o.registration = triTo(p.registration);
  if (p.calendar !== undefined) o.calendar = triTo(p.calendar);
  if (p.attendance !== undefined) o.attendance = attTo(p.attendance);
  return o;
};
export const bulkBody = (b: BulkEnrollmentRequest): J => ({
  enrollment_ids: b.enrollment_ids, ...(b.run_id !== undefined ? { run_id: b.run_id } : {}), ...(b.unassign ? { unassign: true } : {}), ...enrollmentPatchBody(b.patch ?? {}),
});
export const letterBody = (b: LetterRequest): J => ({
  kind: b.kind, ...(b.run_id ? { run_id: b.run_id } : {}), ...(b.enrollment_ids?.length ? { enrollment_ids: b.enrollment_ids } : {}),
  lang: b.lang ?? "both", extra: Object.fromEntries(Object.entries(b.overrides ?? {}).filter(([, v]) => v !== "")),
});
export const emailBody = (b: EmailSendRequest, key: string): J => ({
  ...(b.letter_id ? { letter_id: b.letter_id } : { template: b.template }), recipients: b.recipients.map((r) => r.email),
  dry_run: b.dry_run, ...(b.subject ? { subject: b.subject } : {}), idempotency_key: key,
});
export const connectorBody = (b: ConnectorUpdate): J => ({ enabled: b.enabled ?? true, config: { ...(b.config ?? {}), ...(b.secrets ?? {}) } });
export const userPatchBody = (b: UserPatch): J => ({ ...b });
export const userBody = (b: { username: string; full_name: string; role: string; password: string }): J => ({ username: b.username, password: b.password, role: b.role, display_name: b.full_name });

/** UI column id -> backend sort key; unsupported columns are not sortable server-side (undefined -> dropped). */
const SORTS: Record<string, Record<string, string | undefined>> = {
  runs: { start_date: "start_date", end_date: "end_date", status: "status", type: "type" },
  enrollments: { name_fa: undefined, ticket: "ticket", motivation: "motivation", run_name_fa: "course_name" },
  employees: { emp_no: "emp_no", division: "division", status: "status", name_fa: "last_name_en" },
};
export function sortParam(entity: keyof typeof SORTS, sort?: string): string | undefined {
  if (!sort) return undefined;
  const desc = sort.startsWith("-"); const key = SORTS[entity]![sort.replace(/^-/, "")];
  return key ? `${desc ? "-" : ""}${key}` : undefined;
}
export const wireUpdate = (b: AutomationSettings): J => ({ ...b });
