import { describe, expect, it } from "vitest";
import samples from "./fixtures/backend-samples.json";
import * as W from "./wire";
import { deriveStep, advanceStatus, advancePatch } from "../lib/runs";

// Fixtures are real payloads captured from the running backend (synthetic demo data).
describe("wire: backend -> UI mapping (captured payloads)", () => {
  it("run: names, counts, payment flag; derives the workflow step", () => {
    const r = W.run(samples.runs.items[0]!);
    expect(r).toMatchObject({ id: 6, course_name_fa: "مهارت‌های مذاکره", course_name_en: "Negotiation Skills", status: "announced", institute: "Sample Training Co", section_b: "MTC-100005", payment_started: false });
    expect(deriveStep({ ...r, enrollment_count: 13, motivation_yes_count: 6 })).toBe("motivations");
    expect(deriveStep({ ...r, motivation_yes_count: 0 })).toBe("announce");
  });
  it("enrollment: tri-state, attendance and unassigned run", () => {
    const e = W.enrollment(samples.enrollments.items[0]!);
    expect(e).toMatchObject({ id: 1, run_id: 1, emp_no: "D00001", name_fa: "رضا نووا۱", motivation: "yes", registration: "pending", attendance: "attended", ticket: "LMS-700000" });
    expect(W.enrollment({ ...samples.enrollments.items[0]!, run_id: null, attendance: "-" })).toMatchObject({ run_id: null, attendance: "pending" });
  });
  it("employee: masked values pass through untouched; Active -> active", () => {
    const e = W.employee(samples.employees.items[0]!);
    expect(e).toMatchObject({ emp_no: "D00001", name_fa: "رضا نووا۱", status: "active", job_title: "Specialist" });
    expect(e.national_code).toMatch(/^\*+\d+$/); expect(e.mobile).toMatch(/^\*+\d+$/);
    expect(W.employee(samples.employee_revealed).national_code).toMatch(/^\d{10}$/);
  });
  it("connector: secrets exposed only as set / not_set per known secret key", () => {
    const c = W.connector({ kind: "ifs", configured: true, enabled: true, config: { base_url: "https://x.test" }, secrets_set: ["client_secret"], last_test_ok: false, last_test_at: "2026-09-30T10:00:00" });
    expect(c.secrets).toEqual({ client_secret: "set", password: "not_set" });
    expect(c.last_test).toMatchObject({ ok: false });
    expect(JSON.stringify(c)).not.toMatch(/secret-value/);
    for (const raw of samples.connectors.items) expect(W.connector(raw).last_test).toBeNull();
  });
  it("dashboard: four lists become actionable items; counts and last_sync survive", () => {
    const d = W.dashboard(samples.dashboard);
    expect(d.not_started_courses[0]).toMatchObject({ run_id: 4, title: "تحلیل داده" });
    expect(d.not_started_courses[0]!.detail).toContain("۱۲ روز تا شروع");
    expect(d.level3_due[0]!.emp_no).toBe("D00001");
    expect(d.counts.level3_due).toBe(14);
    expect(d.last_sync.excel.status).toBe("never");
  });
  it("due items, settings, audit, users, courses, candidates", () => {
    expect(W.due(samples.due)[0]).toMatchObject({ kind: "level3_due", run_id: 1 });
    expect(W.due(samples.due)[0]!.title).toMatch(/^ارزیابی سطح ۳ سررسید شده — .*LMS-\d+.*\([۰-۹]+ روز از پایان\)$/);
    const s = W.settings(samples.settings);
    expect(s.settings).toMatchObject({ enabled: true, level3_after_days: 60, over3_threshold: 3 });
    expect(Object.keys(s.settings)).not.toContain("interval_s"); // PUT is extra=forbid: only editable keys
    expect(W.audit(samples.audit.items[0]!)).toMatchObject({ user: "demo_admin" });
    expect(typeof W.audit(samples.audit.items[0]!).entity_id).toBe("string");
    expect(W.user(samples.users.items[0]!)).toMatchObject({ full_name: "Demo admin", active: true, role: "admin" });
    expect(W.course(samples.courses.items[0]!)).toMatchObject({ name_fa: "تحلیل داده", name_en: "Data Analysis" });
    const c = W.candidates(samples.candidates);
    expect(c.candidates[0]).toMatchObject({ enrollment_id: 13, emp_no: "D00006", flags: [] });
  });
});

describe("wire: UI -> backend request bodies (all schemas are extra=forbid)", () => {
  it("enrollment patch uses the backend vocabulary", () => {
    expect(W.enrollmentPatchBody({ motivation: "yes" })).toEqual({ motivation: "Yes" });
    expect(W.enrollmentPatchBody({ motivation: "pending" })).toEqual({ motivation: "" });
    expect(W.enrollmentPatchBody({ attendance: "absent" })).toEqual({ attendance: "Absent" });
    expect(W.enrollmentPatchBody({ attendance: "pending" })).toEqual({ attendance: "-" });
  });
  it("bulk assign body", () => {
    expect(W.bulkBody({ enrollment_ids: [1, 2], run_id: 6 })).toEqual({ enrollment_ids: [1, 2], run_id: 6 });
  });
  it("email: recipients are plain strings, template XOR letter_id, idempotency key in body", () => {
    const b = W.emailBody({ letter_id: 3, recipients: [{ email: "a@example.test", name: "الف" }], dry_run: true }, "key-12345678");
    expect(b).toEqual({ letter_id: 3, recipients: ["a@example.test"], dry_run: true, idempotency_key: "key-12345678" });
  });
  it("email result -> per-recipient status", () => {
    const r = W.sendResult({ id: 9, dry_run: false, status: "partial", results: [{ recipient: "a@x.test", ok: true }, { recipient: "b@x.test", ok: false, error: "boom" }] });
    expect(r.results).toEqual([{ email: "a@x.test", status: "sent" }, { email: "b@x.test", status: "failed", error: "boom" }]);
    expect(W.sendResult({ id: 1, dry_run: true, results: [{ recipient: "a@x.test", ok: true }] }).results[0]!.status).toBe("dry_run");
  });
  it("letter body: overrides go to `extra`; empty overrides dropped", () => {
    expect(W.letterBody({ kind: "settlement_letter", run_id: 1, overrides: { invoice_no: "F-1", total: "" } })).toEqual({ kind: "settlement_letter", run_id: 1, lang: "both", extra: { invoice_no: "F-1" } });
  });
  it("connector body merges secrets into config (backend splits them server-side)", () => {
    expect(W.connectorBody({ enabled: true, config: { host: "h" }, secrets: { password: "p" } })).toEqual({ enabled: true, config: { host: "h", password: "p" } });
  });
  it("user body", () => {
    expect(W.userBody({ username: "u1", full_name: "نام", role: "hr", password: "x" })).toEqual({ username: "u1", password: "x", role: "hr", display_name: "نام" });
  });
  it("sort keys are translated or dropped (backend answers 422 to unknown sort keys)", () => {
    expect(W.sortParam("runs", "-start_date")).toBe("-start_date,-id"); // tie-break on the unique key
    expect(W.sortParam("runs", "course_name_fa")).toBeUndefined();
    expect(W.sortParam("employees", "name_fa")).toBe("last_name_en,emp_no");
  });
  it("missing template fields (422 fields.fields) become per-field problems", () => {
    expect(W.missingFromFields({ fields: "start_date_greg, total, rows" })).toEqual({ start_date_greg: "مقدار «start_date_greg» خالی است.", total: "مقدار «total» خالی است.", rows: "مقدار «rows» خالی است." });
    expect(W.missingFromFields({})).toEqual({});
    expect(W.missingFromMessage("تولید نامه ناموفق بود: Cannot render x: missing required field(s): link, total")).toEqual({ link: "مقدار «link» خالی است.", total: "مقدار «total» خالی است." });
  });
});

describe("run step derivation", () => {
  const base = { enrollment_count: 0, motivation_yes_count: 0, payment_started: false };
  it("maps every backend status", () => {
    expect(deriveStep({ ...base, status: "planned" })).toBe("plan");
    expect(deriveStep({ ...base, status: "planned", enrollment_count: 3 })).toBe("candidates");
    expect(deriveStep({ ...base, status: "open" })).toBe("institute_letter");
    expect(deriveStep({ ...base, status: "running" })).toBe("settlement");
    expect(deriveStep({ ...base, status: "completed" })).toBe("settlement");
    expect(deriveStep({ ...base, status: "completed", payment_started: true })).toBe("level3");
    expect(deriveStep({ ...base, status: "cancelled" })).toBeNull();
  });
  it("advance statuses", () => {
    expect(advanceStatus("candidates")).toBe("announced");
    expect(advanceStatus("plan")).toBeNull();
    expect(advancePatch("settlement", { status: "running" })).toEqual({ status: "completed" });
    expect(advancePatch("settlement", { status: "completed" })).toEqual({ payment_process: "started" });
  });
});
