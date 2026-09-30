// Types aligned with docs/API_CONTRACT.md (v1). Fields the contract does not spell out are
// derived from docs/ARCHITECTURE.md §4 (domain model) and listed in docs/CONTRACT_REQUESTS.md.

export type Role = "admin" | "hr" | "viewer";
export interface User { id: number; username: string; full_name: string; role: Role; active: boolean; last_login?: string | null }
export interface UserPatch { is_active?: boolean; role?: Role; password?: string; display_name?: string }
export interface LoginResult { user: User; csrf_token?: string }

export interface ApiList<T> { items: T[]; total: number; page: number; page_size: number }
export interface ListParams { page?: number; page_size?: number; q?: string; sort?: string; [k: string]: string | number | boolean | undefined }

export type ErrorCode = "validation" | "forbidden" | "not_found" | "conflict" | "upstream" | "unauthorized" | "network" | "unknown";
export interface ErrorEnvelope { error: { code: ErrorCode; message: string; fields?: Record<string, string> } }

// ---- Employees ----
export interface Employee {
  emp_no: string; name_fa: string; name_en: string; gender: "male" | "female";
  email: string; mobile: string; national_code: string; // masked by the server unless ?reveal=1
  division: string; cost_center: string; supervisor_emp_no: string | null; status: "active" | "inactive";
  job_title?: string;
}

// ---- Courses & runs ----
export interface Course { id: number; name_fa: string; name_en: string; category: string; delivery: "online" | "in_person" }
/** Backend run status (RunStatus in backend/app/schemas/domain.py). */
export type RunStatus = "planned" | "announced" | "open" | "running" | "completed" | "cancelled";
export const RUN_STATUSES: RunStatus[] = ["planned", "announced", "open", "running", "completed", "cancelled"];
/** UI-only workflow step, DERIVED from run data by lib/runs.ts (the backend has no such field). */
export type RunStep = "plan" | "candidates" | "announce" | "motivations" | "institute_letter" | "settlement" | "level3";
export const RUN_STEPS: RunStep[] = ["plan", "candidates", "announce", "motivations", "institute_letter", "settlement", "level3"];
export interface CourseRun {
  id: number; course_id: number; course_name_fa: string; course_name_en: string;
  type: "online" | "in_person"; institute: string; duration_h: number;
  start_date: string; end_date: string; days: string; time: string; sessions: number;
  send_date: string | null; deadline: string | null; amount: number | null; section_b: string | null; link: string;
  status: RunStatus; enrollment_count: number; motivation_yes_count: number; payment_started: boolean;
  /** false for backend list items (counts only come with GET /runs/{id}); the table then shows "—" */
  counts_known: boolean;
  /** derived server-side, only on GET/PATCH /runs/{id}; absent on list items (lib/runs.ts falls back to a heuristic) */
  workflow?: RunWorkflow;
}
export interface RunWorkflow { announced: boolean; motivations_collected: boolean; institute_letter_sent: boolean; invoice_received: boolean; settlement_sent: boolean; level3_started: boolean }
export interface Institute { id: number; name: string; name_fa: string; supplier_code: string; contact_email: string }
export type NewInstitute = Omit<Institute, "id">
export type RunInput = Partial<Omit<CourseRun, "id" | "course_name_fa" | "course_name_en" | "enrollment_count" | "motivation_yes_count" | "payment_started" | "counts_known">> & { payment_process?: string };

// ---- Enrollments ----
export type Tri = "yes" | "no" | "pending";
export type Attendance = "attended" | "absent" | "pending";
export type EditableEnrollmentField = "motivation" | "registration" | "calendar" | "attendance";
export interface Enrollment {
  id: number; run_id: number | null; run_name_fa: string;
  emp_no: string; name_fa: string; division: string; ticket: string;
  status: string; motivation: Tri; registration: Tri; calendar: Tri; attendance: Attendance; level3_status: string;
  email: string; supervisor_email: string;
}
export type EnrollmentPatch = Partial<Pick<Enrollment, EditableEnrollmentField>>;
/** Bulk: assign IDP requests to a run (run_id) and/or set fields on many enrollments. */
export interface BulkEnrollmentRequest { enrollment_ids: number[]; run_id?: number; unassign?: boolean; patch?: EnrollmentPatch }
export interface BulkResult { updated: number[]; failed: { id: number; reason: string }[] }

/** A candidate is an unassigned IDP request (enrollment) matching the run's course. */
export type CandidateFlag = "over_motivation_limit" | "division_change" | "non_active" | "level3_eligible";
export interface Candidate {
  enrollment_id: number; emp_no: string; name_fa: string; division: string; ticket: string;
  flags: CandidateFlag[]; /** blocking = anything except level3_eligible */
}
export interface ExcludedCandidate { enrollment_id: number; ticket: string; reason: string; conflicting_ticket: string }
export interface CandidateResult { candidates: Candidate[]; excluded: ExcludedCandidate[]; total: number }
export interface CandidateSearch { course_name?: string; include_flagged?: boolean }

// ---- Letters ----
export type LetterKind = "course_announcement" | "institute_letter" | "settlement_letter" | "level3_request" | "level3_manager_check" | "line_manager_approval";
export const LETTER_KINDS: LetterKind[] = ["course_announcement", "institute_letter", "settlement_letter", "level3_request", "level3_manager_check", "line_manager_approval"];
export interface LetterRequest { kind: LetterKind; run_id?: number; enrollment_ids?: number[]; lang?: "fa" | "en" | "both"; overrides?: Record<string, string> }
/** missing_fields: backend field name -> Persian message (derived from a 422 by the wire layer). */
export interface LetterPreview { html: string; subject?: string; missing_fields?: Record<string, string> }
export interface Letter { id: number; kind: LetterKind; run_id: number | null; number: string; state: "rendered" | "sent"; created_at: string; created_by: string; file_name: string; subject: string }

// ---- Email ----
export interface Recipient { email: string; name?: string }
export interface EmailSendRequest { letter_id?: number; template?: string; recipients: Recipient[]; dry_run: boolean; subject?: string }
export interface RecipientResult { email: string; status: "sent" | "failed" | "dry_run"; error?: string }
export interface EmailSendResult { dry_run: boolean; results: RecipientResult[]; message_id?: number }
export interface MessageLog { id: number; subject: string; letter_id: number | null; recipients_count: number; failed_count: number; dry_run: boolean; sent_at: string; sent_by: string; results: { email: string; ok: boolean }[] }

// ---- Connectors / sync ----
export type ConnectorKind = "excel" | "ifs" | "smtp" | "graph";
export type SecretState = "set" | "not_set";
export interface Connector {
  kind: ConnectorKind; enabled: boolean;
  config: Record<string, string | number | boolean>;
  secrets: Record<string, SecretState>; // names + state only, never values
  last_test: { ok: boolean; at: string; message: string } | null;
}
export interface ConnectorUpdate { enabled?: boolean; config?: Record<string, string | number | boolean>; secrets?: Record<string, string> }
export const SECRET_KEYS: Record<ConnectorKind, string[]> = { excel: [], ifs: ["client_secret", "password"], smtp: ["password"], graph: ["client_secret"] };
export interface TestResult { ok: boolean; message: string; latency_ms?: number }
/** one problem found while importing/syncing (backend: {sheet,row,column,code,reason}; reason is a fixed message, never a cell value) */
export interface ImportError { sheet: string; row: number | null; column: string; code: string; reason: string }
export interface SyncRun { id: number; kind: "excel" | "ifs"; started_at: string; finished_at: string | null; status: "running" | "ok" | "failed"; created: number; updated: number; errors: number; message: string; error_list: ImportError[] }

// ---- Dashboard / automation ----
export interface DashItem { key: string; title: string; detail: string; date: string | null; run_id: number | null; emp_no?: string | null; ticket?: string | null }
export interface SyncSummary { at: string | null; status: "ok" | "failed" | "never" }
export interface Dashboard {
  not_started_courses: DashItem[]; payment_not_started: DashItem[]; over3_motivations: DashItem[]; level3_due: DashItem[];
  counts: Record<string, number>; last_sync: { excel: SyncSummary; ifs: SyncSummary };
}
export interface DueItem { id: string; kind: string; title: string; due_date: string | null; run_id: number | null; count: number }
/** Editable subset of GET/PUT /automation/settings (backend has more keys; extra=forbid so only these are sent). */
export interface AutomationSettings {
  enabled: boolean; level3_after_days: number; reminder_days: number; over3_threshold: number;
  letter_number_prefix: string; settlement_addressee: string; letter_signer_name: string; letter_signer_title: string;
  letter_signer_email: string; letter_signer_phone: string;
  company_economic_code: string; company_national_id: string; company_postal_code: string; company_address: string;
}
export interface AutomationInfo { last_run: { at: string; total: number } | null; loop_enabled: boolean }
export interface AutomationRunResult { total: number; message: string }

// ---- Import/export ----
export interface ImportResult {
  created: number; updated: number; skipped: number; error_count: number; errors: ImportError[];
}

// ---- Admin ----
export interface NewUser { username: string; full_name: string; role: Role; password: string }
export interface AuditEntry { id: number; at: string; user: string; action: string; entity: string; entity_id: string; ip: string; detail: string }
