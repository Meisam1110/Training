// Integration check against a RUNNING backend. Skipped unless TMS_LIVE_URL (and TMS_LIVE_USER/PASS) are set:
//   TMS_LIVE_URL=http://localhost:8000 TMS_LIVE_USER=demo_admin TMS_LIVE_PASS=... npx vitest run src/api/live.test.ts
import { describe, expect, it } from "vitest";
import { createApi, createClient, type FetchLike } from "./client";

const URL_ = (globalThis as any).process?.env?.TMS_LIVE_URL;
const d = URL_ ? describe : describe.skip;

d("live backend (wire adapters)", () => {
  const jar = new Map<string, string>();
  const f: FetchLike = async (input, init = {}) => {
    const h = new Headers(init.headers); if (jar.size) h.set("Cookie", [...jar].map(([k, v]) => `${k}=${v}`).join("; "));
    const res = await fetch(`${URL_}${input}`, { ...init, headers: h });
    for (const c of res.headers.getSetCookie?.() ?? []) { const [kv] = c.split(";"); const [k, ...v] = kv!.split("="); jar.set(k!, v.join("=")); }
    return res;
  };
  const api = createApi(createClient({ fetchImpl: f }), { wire: true });
  it("logs in and reads every list through the adapters", async () => {
    const u = await api.login((globalThis as any).process.env.TMS_LIVE_USER!, (globalThis as any).process.env.TMS_LIVE_PASS!);
    expect(u.user.role).toBeTruthy();
    const dash = await api.dashboard(); expect(dash.counts.runs).toBeGreaterThan(0);
    const runs = await api.runs({ page_size: 5, sort: "-start_date" }); expect(runs.items[0]!.course_name_fa).toBeTruthy();
    const emps = await api.employees({ page_size: 5, sort: "name_fa" }); expect(emps.items[0]!.national_code).toMatch(/\*/);
    const en = await api.enrollments({ page_size: 5, sort: "ticket" }); expect(["yes", "no", "pending"]).toContain(en.items[0]!.motivation);
    await api.courses(); await api.letters(); await api.messages(); await api.syncRuns(); await api.users(); await api.audit({ page_size: 5 });
    await api.connectors(); await api.automationDue(); expect((await api.automationSettings()).settings.level3_after_days).toBeGreaterThan(0);
    const c = await api.searchCandidates(runs.items[0]!.id, {}); expect(Array.isArray(c.candidates)).toBe(true);
  });
  it("patches an enrollment with the backend vocabulary and restores it", async () => {
    const e = (await api.enrollments({ page_size: 1 })).items[0]!;
    const back = await api.patchEnrollment(e.id, { motivation: e.motivation === "yes" ? "no" : "yes" });
    expect(back.motivation).not.toBe(e.motivation);
    expect((await api.patchEnrollment(e.id, { motivation: e.motivation })).motivation).toBe(e.motivation);
  });
  it("letters: preview + create + download for all six kinds, then e-mail through a local SMTP sink", async () => {
    // @ts-expect-error node builtin, this file only runs in Node
    const fs = await import("node:fs");
    const sink = (globalThis as any).process.env.TMS_LIVE_SINK as string | undefined; // jsonl written by scripts/smtp-sink (optional)
    // letterhead constants live in settings (admin): set once through the UI adapter
    const cur = (await api.automationSettings()).settings;
    await api.saveAutomationSettings({ ...cur, company_economic_code: "411000000000", company_national_id: "10100000000", company_postal_code: "1234567890", company_address: "نشانی نمونه", settlement_addressee: "واحد مالی", letter_signer_name: "تیم توسعه استعداد", letter_signer_title: "منابع انسانی" });
    let run = (await api.runs({ page_size: 50 })).items[0]!; let enr: Awaited<ReturnType<typeof api.runEnrollments>>["items"] = [];
    for (const r of (await api.runs({ page_size: 50 })).items) { const e = (await api.runEnrollments(r.id, { page_size: 200 })).items; if (r.status === "completed" && e.length > 3) { run = r; enr = e; break; } }
    expect(enr.length).toBeGreaterThan(3);
    await api.updateRun(run.id, { link: "https://example.test/course" });
    const kinds = ["course_announcement", "institute_letter", "settlement_letter", "level3_request", "level3_manager_check", "line_manager_approval"] as const;
    const created: Record<string, number> = {};
    for (const kind of kinds) {
      const per = ["level3_request", "level3_manager_check", "line_manager_approval"].includes(kind);
      let req = { kind, run_id: run.id, enrollment_ids: per ? enr.filter((e) => e.supervisor_email).slice(0, 3).map((e) => e.id) : undefined, overrides: {} as Record<string, string> };
      let p = await api.previewLetter(req);
      if (p.missing_fields) { // per-field problems -> fill them like the UI does, then preview again
        req = { ...req, overrides: Object.fromEntries(Object.keys(p.missing_fields).map((k) => [k, "مقدار آزمایشی"])) };
        p = await api.previewLetter(req);
      }
      if (kind === "settlement_letter" && p.missing_fields) {
        // KNOWN BACKEND MISMATCH (reported in CONTRACT_REQUESTS): Core sends invoice_total/start_date_gregorian/attendees but the
        // renderer requires total/start_date_greg/rows, and `extra` cannot carry a list. The UI shows these per field; nothing to adapt.
        expect(Object.keys(p.missing_fields)).toEqual(expect.arrayContaining(["rows"])); continue;
      }
      expect(p.html.length, `${kind} preview html; missing=${JSON.stringify(p.missing_fields)}`).toBeGreaterThan(50);
      const l = await api.createLetter(req);
      expect(l.number, kind).toBeTruthy(); created[kind] = l.id;
      const { blob, filename } = await api.downloadLetter(l.id);
      const head = new Uint8Array(await blob.arrayBuffer()).slice(0, 2);
      expect(String.fromCharCode(...head), `${kind} .docx is a zip`).toBe("PK"); expect(filename).toMatch(/\.docx$/); expect(blob.size).toBeGreaterThan(2000);
    }
    // e-mail: configure SMTP to the local sink, test, dry-run, real, replay
    await api.updateConnector("smtp", { enabled: true, config: { host: "127.0.0.1", port: 8025, starttls: false, from_addr: "training@example.test" } });
    const t = await api.testConnector("smtp"); expect(t.ok, t.message).toBe(true);
    const recipients = enr.slice(0, 3).map((e) => ({ email: e.email, name: e.name_fa }));
    const rcpts = () => (sink && fs.existsSync(sink) ? fs.readFileSync(sink, "utf8").split("\n").filter(Boolean).reduce((n: number, l: string) => n + JSON.parse(l).to.length, 0) : 0);
    const before = rcpts();
    const d = await api.sendEmail({ letter_id: created.course_announcement, recipients, dry_run: true }, `live-dry-${Date.now()}`);
    expect(d.results.map((r) => r.status)).toEqual(["dry_run", "dry_run", "dry_run"]);
    expect(rcpts() - before, "dry-run must not deliver anything").toBe(0);
    const key = `live-real-${Date.now()}-x`;
    const r1 = await api.sendEmail({ letter_id: created.course_announcement, recipients, dry_run: false }, key);
    expect(r1.results.map((r) => r.status), JSON.stringify(r1)).toEqual(["sent", "sent", "sent"]);
    const r2 = await api.sendEmail({ letter_id: created.course_announcement, recipients, dry_run: false }, key); // replay: no second delivery
    expect(r2.results.length).toBe(3);
    if (sink) expect(rcpts() - before, "exactly 3 deliveries: real send once, replay sends nothing").toBe(3);
    const msgs = await api.messages({ page_size: 10 }); expect(msgs.items.some((m) => m.letter_id === created.course_announcement && !m.dry_run && m.recipients_count === 3)).toBe(true);
  }, 60000);
  it("institutes and users (PATCH) through the adapters; last-admin 409", async () => {
    const name = `Inst ${Date.now()}`;
    const inst = await api.createInstitute({ name, name_fa: "مؤسسه آزمایشی", supplier_code: "SUP-9", contact_email: "x@example.test" });
    expect(inst.name).toBe(name);
    expect((await api.institutes({ q: name })).items.map((i) => i.name)).toContain(name);
    await expect(api.createInstitute({ name, name_fa: "", supplier_code: "", contact_email: "" })).rejects.toMatchObject({ status: 409 });
    const u = await api.createUser({ username: `qa.${Date.now()}`, full_name: "کاربر آزمایشی", role: "viewer", password: "Str0ng-Pass-9" });
    expect(u.role).toBe("viewer");
    expect((await api.updateUser(u.id, { role: "hr" })).role).toBe("hr");
    expect((await api.updateUser(u.id, { is_active: false })).active).toBe(false);
    expect((await api.updateUser(u.id, { password: "An0ther-Pass-9" })).id).toBe(u.id);
    const me = await api.me();
    await expect(api.updateUser(me.id, { is_active: false })).rejects.toMatchObject({ status: 409 });
  });
});
