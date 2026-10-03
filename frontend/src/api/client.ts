import type {
  ApiList, ListParams, ErrorCode, ErrorEnvelope,
} from "./types";

export class ApiError extends Error {
  status: number; code: ErrorCode; fields: Record<string, string>;
  constructor(status: number, code: ErrorCode, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError"; this.status = status; this.code = code; this.fields = fields;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;
export interface ClientOptions {
  baseUrl?: string;
  fetchImpl?: FetchLike;
  onUnauthorized?: () => void;
  /** true when fetchImpl is the in-memory mock: uploads are simulated instead of XHR. */
  simulateUpload?: boolean;
}
export interface RequestOptions { query?: object; body?: unknown; headers?: Record<string, string>; signal?: AbortSignal }

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const CSRF_KEY = "tms.csrf";
const FA_NETWORK = "ارتباط با سرور برقرار نشد. اتصال شبکه را بررسی و دوباره تلاش کنید.";
const FA_UNKNOWN = "خطای غیرمنتظره‌ای رخ داد.";

function buildQuery(q?: object): string {
  if (!q) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}
const safeStore = {
  get(): string | null { try { return sessionStorage.getItem(CSRF_KEY); } catch { return null; } },
  set(v: string | null) { try { if (v) sessionStorage.setItem(CSRF_KEY, v); else sessionStorage.removeItem(CSRF_KEY); } catch { /* storage unavailable */ } },
};

export function parseErrorBody(status: number, body: unknown): ApiError {
  const env = (body as Partial<ErrorEnvelope> | null)?.error;
  if (env && typeof env.message === "string") return new ApiError(status, (env.code as ErrorCode) ?? "unknown", env.message, env.fields ?? {});
  const fallback: Record<number, [ErrorCode, string]> = {
    401: ["unauthorized", "نشست شما منقضی شده است. دوباره وارد شوید."],
    403: ["forbidden", "شما اجازهٔ انجام این کار را ندارید."],
    404: ["not_found", "مورد درخواستی پیدا نشد."],
    409: ["conflict", "این درخواست با وضعیت فعلی داده‌ها تداخل دارد."],
    422: ["validation", "اطلاعات واردشده معتبر نیست."],
    502: ["upstream", "سرویس بیرونی پاسخ نداد."],
  };
  const [code, msg] = fallback[status] ?? ["unknown", FA_UNKNOWN];
  return new ApiError(status, code, msg);
}

export function createClient(opts: ClientOptions = {}) {
  const base = opts.baseUrl ?? "/api/v1";
  const doFetch: FetchLike = opts.fetchImpl ?? ((i, init) => fetch(i, init));
  let csrf: string | null = safeStore.get();

  const setCsrf = (t: string | null | undefined) => { if (t) { csrf = t; safeStore.set(t); } };
  const clearCsrf = () => { csrf = null; safeStore.set(null); };

  function handle401(path: string) {
    if (path.startsWith("/auth/login")) return;
    clearCsrf();
    opts.onUnauthorized?.();
  }

  async function request<T>(method: string, path: string, o: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json", ...o.headers };
    let body: BodyInit | undefined;
    if (o.body instanceof FormData) body = o.body;
    else if (o.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(o.body); }
    if (UNSAFE.has(method) && csrf) headers["X-CSRF-Token"] = csrf;

    let res: Response;
    try {
      res = await doFetch(`${base}${path}${buildQuery(o.query)}`, { method, headers, body, credentials: "same-origin", signal: o.signal });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") throw e;
      throw new ApiError(0, "network", FA_NETWORK);
    }
    setCsrf(res.headers.get("X-CSRF-Token"));
    if (res.status === 204) return undefined as T;
    let json: unknown = null;
    const ct = res.headers.get("Content-Type") ?? "";
    if (ct.includes("json")) { try { json = await res.json(); } catch { json = null; } }
    if (!res.ok) {
      if (res.status === 401) handle401(path);
      throw parseErrorBody(res.status, json);
    }
    const tok = (json as { csrf_token?: string } | null)?.csrf_token;
    setCsrf(tok);
    return json as T;
  }

  async function download(path: string): Promise<{ blob: Blob; filename: string }> {
    let res: Response;
    try { res = await doFetch(`${base}${path}`, { method: "GET", credentials: "same-origin" }); }
    catch { throw new ApiError(0, "network", FA_NETWORK); }
    if (!res.ok) {
      if (res.status === 401) handle401(path);
      let j: unknown = null; try { j = await res.json(); } catch { /* not json */ }
      throw parseErrorBody(res.status, j);
    }
    const cd = res.headers.get("Content-Disposition") ?? "";
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
    return { blob: await res.blob(), filename: m?.[1] ? decodeURIComponent(m[1]) : "download" };
  }

  /** multipart upload with progress. Real mode uses XHR (fetch has no upload progress). */
  function upload<T>(path: string, file: File, onProgress?: (pct: number) => void): Promise<T> {
    const fd = new FormData(); fd.append("file", file);
    if (opts.simulateUpload || typeof XMLHttpRequest === "undefined") {
      return new Promise<T>((resolve, reject) => {
        let p = 0;
        const timer = setInterval(() => { p = Math.min(90, p + 15); onProgress?.(p); }, 120);
        request<T>("POST", path, { body: fd }).then(
          (r) => { clearInterval(timer); onProgress?.(100); resolve(r); },
          (e) => { clearInterval(timer); reject(e); });
      });
    }
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${base}${path}`);
      xhr.withCredentials = true;
      xhr.setRequestHeader("Accept", "application/json");
      if (csrf) xhr.setRequestHeader("X-CSRF-Token", csrf);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100)); };
      xhr.onerror = () => reject(new ApiError(0, "network", FA_NETWORK));
      xhr.onload = () => {
        let json: unknown = null; try { json = JSON.parse(xhr.responseText); } catch { /* empty */ }
        if (xhr.status >= 200 && xhr.status < 300) { onProgress?.(100); resolve(json as T); return; }
        if (xhr.status === 401) handle401(path);
        reject(parseErrorBody(xhr.status, json));
      };
      xhr.send(fd);
    });
  }

  return {
    get: <T>(path: string, query?: object, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
    post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, { body: body ?? {}, headers }),
    put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body: body ?? {} }),
    patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body: body ?? {} }),
    del: <T>(path: string) => request<T>("DELETE", path),
    download, upload,
    setCsrf, clearCsrf, getCsrf: () => csrf,
  };
}
export type HttpClient = ReturnType<typeof createClient>;

/** Typed facade over the endpoints in docs/API_CONTRACT.md. wire=true adapts the real backend's shapes (api/wire.ts). */
import type {
  CandidateResult, CandidateSearch, Connector, ConnectorKind, ConnectorUpdate, Course, CourseRun, Dashboard, Employee,
  Enrollment, EnrollmentPatch, BulkEnrollmentRequest, BulkResult, EmailSendRequest, EmailSendResult, Letter, LetterPreview, LetterRequest,
  LoginResult, CourseInput, MessageLog, NewUser, UserPatch, Institute, NewInstitute, RunInput, SyncRun, TestResult, User, AuditEntry, DueItem, AutomationSettings, AutomationInfo,
  AutomationRunResult, ImportResult,
} from "./types";
import * as W from "./wire";

export const MAX_PAGE_SIZE = 200; // backend cap (422 above this)
const cap = (p: ListParams = {}): ListParams => ({ ...p, page_size: Math.min(p.page_size ?? 50, MAX_PAGE_SIZE) });
type Page<T> = ApiList<T>;
const mapPage = <A, B>(p: Page<A>, f: (a: A) => B): Page<B> => ({ ...p, items: p.items.map(f) });

export function createApi(http: HttpClient, opts: { wire?: boolean } = {}) {
  const wire = !!opts.wire;
  /** apply `f` only when talking to the real backend */
  const m = <A, B>(f: (a: A) => B) => (a: A): B => (wire ? f(a) : (a as unknown as B));
  const mp = <A, B>(f: (a: A) => B) => (p: Page<A>): Page<B> => (wire ? mapPage(p, f) : (p as unknown as Page<B>));
  const q = (entity: "runs" | "enrollments" | "employees" | "courses", p: ListParams): ListParams => {
    const o = cap(p);
    if (wire) { const s = W.sortParam(entity, p.sort); if (s) o.sort = s; else delete o.sort; }
    if (wire && entity === "enrollments" && o.motivation) o.motivation = o.motivation === "pending" ? "none" : W.triTo(String(o.motivation) as "yes");
    if (wire && entity === "enrollments" && o.motivation === "") delete o.motivation;
    return o;
  };
  return {
    http, wire,
    // auth
    login: (username: string, password: string) => http.post<{ user: unknown; csrf_token?: string }>("/auth/login", { username, password }).then((r): LoginResult => ({ ...r, user: m(W.user)(r.user as never) })),
    logout: () => http.post<void>("/auth/logout"),
    me: () => http.get<{ user: unknown }>("/auth/me").then((r): User => m(W.user)((r.user ?? r) as never)),
    // dashboard
    dashboard: () => http.get<Dashboard>("/dashboard").then(m(W.dashboard as never) as (d: Dashboard) => Dashboard),
    // employees
    employees: (p: ListParams) => http.get<Page<Employee>>("/employees", q("employees", p)).then(mp(W.employee as never) as (p: Page<Employee>) => Page<Employee>),
    employee: (empNo: string, reveal = false) => http.get<Employee>(`/employees/${encodeURIComponent(empNo)}`, reveal ? { reveal: 1 } : undefined).then(m(W.employee as never) as (e: Employee) => Employee),
    createCourse: (b: CourseInput) => http.post<Course>("/courses", wire ? W.courseBody(b) : b).then(m(W.course as never) as (c: Course) => Course),
    updateCourse: (id: number, b: CourseInput) => http.patch<Course>(`/courses/${id}`, wire ? W.courseBody(b) : b).then(m(W.course as never) as (c: Course) => Course),
    // courses & runs
    courses: (p: ListParams = {}) => http.get<Page<Course>>("/courses", q("courses", p)).then(mp(W.course as never) as (p: Page<Course>) => Page<Course>),
    runs: (p: ListParams) => http.get<Page<CourseRun>>("/runs", q("runs", p)).then(mp(W.run as never) as (p: Page<CourseRun>) => Page<CourseRun>),
    run: (id: number) => http.get<CourseRun>(`/runs/${id}`).then(m(W.run as never) as (r: CourseRun) => CourseRun),
    createRun: (b: RunInput) => http.post<CourseRun>("/runs", wire ? W.runBody(b) : b).then(m(W.run as never) as (r: CourseRun) => CourseRun),
    updateRun: (id: number, b: RunInput) => http.patch<CourseRun>(`/runs/${id}`, wire ? W.runBody(b) : b).then(m(W.run as never) as (r: CourseRun) => CourseRun),
    runEnrollments: (id: number, p: ListParams = {}) => http.get<Page<Enrollment>>(`/runs/${id}/enrollments`, cap(p)).then(mp(W.enrollment as never) as (p: Page<Enrollment>) => Page<Enrollment>),
    searchCandidates: (id: number, b: CandidateSearch) => http.post<CandidateResult>(`/runs/${id}/candidates:search`, b).then(m(W.candidates as never) as (r: CandidateResult) => CandidateResult),
    // enrollments
    enrollments: (p: ListParams) => http.get<Page<Enrollment>>("/enrollments", q("enrollments", p)).then(mp(W.enrollment as never) as (p: Page<Enrollment>) => Page<Enrollment>),
    patchEnrollment: (id: number, b: EnrollmentPatch) => http.patch<Enrollment>(`/enrollments/${id}`, wire ? W.enrollmentPatchBody(b) : b).then(m(W.enrollment as never) as (e: Enrollment) => Enrollment),
    bulkEnrollments: (b: BulkEnrollmentRequest) => http.post<BulkResult>("/enrollments:bulk", wire ? W.bulkBody(b) : b),
    // letters
    letters: (p: ListParams = {}) => http.get<Page<Letter>>("/letters", cap(p)).then(mp(W.letter as never) as (p: Page<Letter>) => Page<Letter>),
    previewLetter: (b: LetterRequest): Promise<LetterPreview> =>
      http.post<LetterPreview>("/letters/preview", wire ? W.letterBody(b) : b).then(m(W.preview as never) as (r: LetterPreview) => LetterPreview).catch((e: unknown) => {
        // real backend: missing template fields arrive as a 422 -> present them as per-field preview problems
        if (wire && e instanceof ApiError && (e.code === "validation" || e.code === "upstream")) { const mf = { ...W.missingFromFields(e.fields), ...W.missingFromMessage(e.message) }; if (Object.keys(mf).length) return { html: "", missing_fields: mf }; }
        throw e;
      }),
    createLetter: (b: LetterRequest) => http.post<Letter>("/letters", wire ? W.letterBody(b) : b).then(m(W.letter as never) as (l: Letter) => Letter),
    downloadLetter: (id: number) => http.download(`/letters/${id}/download`),
    // email
    sendEmail: (b: EmailSendRequest, idempotencyKey: string) =>
      http.post<EmailSendResult>("/email/send", wire ? W.emailBody(b, idempotencyKey) : { ...b, idempotency_key: idempotencyKey }, { "Idempotency-Key": idempotencyKey }).then(m(W.sendResult as never) as (r: EmailSendResult) => EmailSendResult),
    messages: (p: ListParams = {}) => http.get<Page<MessageLog>>("/messages", cap(p)).then(mp(W.message as never) as (p: Page<MessageLog>) => Page<MessageLog>),
    // connectors
    connectors: () => http.get<{ items: Connector[] }>("/connectors").then((r) => (wire ? r.items.map(W.connector as never) : r.items) as Connector[]),
    updateConnector: (k: ConnectorKind, b: ConnectorUpdate) => http.put<Connector>(`/connectors/${k}`, wire ? W.connectorBody(b) : b).then(m(W.connector as never) as (c: Connector) => Connector),
    testConnector: (k: ConnectorKind) => http.post<TestResult>(`/connectors/${k}:test`),
    runSync: (k: "excel" | "ifs") => http.post<SyncRun>(`/sync/${k}:run`).then(m(W.syncRun as never) as (s: SyncRun) => SyncRun),
    syncRuns: (p: ListParams = {}) => http.get<Page<SyncRun>>("/sync/runs", cap(p)).then(mp(W.syncRun as never) as (p: Page<SyncRun>) => Page<SyncRun>),
    // automation
    automationDue: () => http.get<{ items: DueItem[] }>("/automation/due").then((r) => (wire ? W.due(r) : r.items)),
    runAutomation: () => http.post<{ total: number }>("/automation/run").then((r): AutomationRunResult => ({ total: r.total, message: `${r.total} مورد بررسی شد.` })),
    automationSettings: () => http.get<Record<string, unknown>>("/automation/settings").then((s): { settings: AutomationSettings } & AutomationInfo => (wire ? W.settings(s) : (s as never))),
    saveAutomationSettings: (b: AutomationSettings) => http.put<Record<string, unknown>>("/automation/settings", b).then((s) => (wire ? W.settings(s) : (s as never))),
    // import/export
    importIdp: (f: File, on?: (p: number) => void) => http.upload<ImportResult>("/import/idp", f, on).then(m(W.importResult as never) as (r: ImportResult) => ImportResult),
    importLegacy: (f: File, on?: (p: number) => void) => http.upload<ImportResult>("/import/legacy-workbook", f, on).then(m(W.importResult as never) as (r: ImportResult) => ImportResult),
    exportLegacy: () => http.download("/export/legacy.xlsx"),
    // admin
    users: (p: ListParams = {}) => http.get<Page<User>>("/users", cap(p)).then(mp(W.user as never) as (p: Page<User>) => Page<User>),
    updateUser: (id: number, b: UserPatch) => http.patch<User>(`/users/${id}`, wire ? W.userPatchBody(b) : b).then(m(W.user as never) as (u: User) => User),
    institutes: (p: ListParams = {}) => http.get<Page<Institute>>("/institutes", cap(p)).then(mp(W.institute as never) as (p: Page<Institute>) => Page<Institute>),
    createInstitute: (b: NewInstitute) => http.post<Institute>("/institutes", wire ? W.instituteBody(b) : b).then(m(W.institute as never) as (i: Institute) => Institute),
    createUser: (b: NewUser) => http.post<User>("/users", wire ? W.userBody(b) : b).then(m(W.user as never) as (u: User) => User),
    audit: (p: ListParams) => {
      const o = cap(p) as Record<string, unknown>;
      if (wire) { if (o.user) o.actor = o.user; delete o.user; if (o.from) o.since = o.from; delete o.from; if (o.to) o.until = `${o.to}T23:59:59`; delete o.to; }
      return http.get<Page<AuditEntry>>("/audit", o).then(mp(W.audit as never) as (p: Page<AuditEntry>) => Page<AuditEntry>);
    },
  };
}
export type Api = ReturnType<typeof createApi>;
