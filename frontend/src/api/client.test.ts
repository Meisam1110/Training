import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApi, createClient, parseErrorBody } from "./client";
import { createMockFetch } from "./mock/server";

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

beforeEach(() => { try { sessionStorage.clear(); } catch { /* */ } });

describe("client: CSRF", () => {
  it("captures X-CSRF-Token and sends it only on unsafe methods", async () => {
    const f = vi.fn(async () => json(200, {}, { "X-CSRF-Token": "tok123" }));
    const c = createClient({ fetchImpl: f });
    await c.get("/auth/me");
    await c.get("/dashboard");
    await c.post("/runs", { a: 1 });
    await c.patch("/runs/1", {});
    await c.put("/x", {});
    await c.del("/x");
    const hdr = (i: number) => new Headers((f.mock.calls[i] as unknown as [string, RequestInit])[1].headers);
    expect(hdr(0).get("X-CSRF-Token")).toBeNull();
    expect(hdr(1).get("X-CSRF-Token")).toBeNull();
    for (const i of [2, 3, 4, 5]) expect(hdr(i).get("X-CSRF-Token")).toBe("tok123");
  });
  it("also accepts the token from the login body", async () => {
    const f = vi.fn(async () => json(200, { user: {}, csrf_token: "fromBody" }));
    const c = createClient({ fetchImpl: f });
    await c.post("/auth/login", { username: "a", password: "b" });
    expect(c.getCsrf()).toBe("fromBody");
  });
});

describe("client: errors", () => {
  it("parses the error envelope with field errors", async () => {
    const c = createClient({ fetchImpl: async () => json(422, { error: { code: "validation", message: "نامعتبر", fields: { start_date: "الزامی است" } } }) });
    const e = await c.get("/x").catch((x) => x as ApiError);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 422, code: "validation", message: "نامعتبر", fields: { start_date: "الزامی است" } });
  });
  it("falls back to Persian messages when the body is not an envelope", () => {
    expect(parseErrorBody(500, "<html>").message).toMatch(/خطا/);
    expect(parseErrorBody(403, null).code).toBe("forbidden");
  });
  it("maps network failure to a Persian error", async () => {
    const c = createClient({ fetchImpl: async () => { throw new TypeError("fail"); } });
    await expect(c.get("/x")).rejects.toMatchObject({ code: "network", status: 0 });
  });
  it("401 calls onUnauthorized (redirect to login) and drops the CSRF token", async () => {
    const onUnauthorized = vi.fn();
    const c = createClient({ fetchImpl: async () => json(401, { error: { code: "unauthorized", message: "x" } }), onUnauthorized });
    c.setCsrf("t");
    await expect(c.get("/dashboard")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(c.getCsrf()).toBeNull();
  });
  it("a failed login (401) does NOT trigger the redirect", async () => {
    const onUnauthorized = vi.fn();
    const c = createClient({ fetchImpl: async () => json(401, { error: { code: "unauthorized", message: "bad" } }), onUnauthorized });
    await expect(c.post("/auth/login", {})).rejects.toMatchObject({ message: "bad" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
  it("drops empty query params and encodes the rest", async () => {
    const f = vi.fn(async () => json(200, {}));
    await createClient({ fetchImpl: f }).get("/runs", { q: "مدیریت", page: 2, sort: "", status: undefined });
    expect((f.mock.calls[0] as unknown as [string])[0]).toBe(`/api/v1/runs?q=${encodeURIComponent("مدیریت")}&page=2`);
  });
});

describe("mock backend behind the real client", () => {
  function setup() {
    const mock = createMockFetch({ latency: 0, storage: false });
    const onUnauthorized = vi.fn();
    const api = createApi(createClient({ fetchImpl: mock.fetch, onUnauthorized }));
    return { api, onUnauthorized, mock };
  }
  it("requires login (401), then works; unsafe writes need the CSRF token", async () => {
    const { api, onUnauthorized } = setup();
    await expect(api.dashboard()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalled();
    await expect(api.login("admin", "wrong")).rejects.toMatchObject({ status: 401 });
    await api.login("hr", "demo");
    const d = await api.dashboard();
    expect(d.counts.runs).toBeGreaterThan(5);
    api.http.clearCsrf();
    await expect(api.updateRun(1, { institute: "x" })).rejects.toMatchObject({ status: 403 });
  });
  it("viewer cannot write, and cannot reveal PII", async () => {
    const { api } = setup();
    await api.login("viewer", "demo");
    await expect(api.patchEnrollment(1, { motivation: "yes" })).rejects.toMatchObject({ code: "forbidden" });
    await expect(api.employee("71000", true)).rejects.toMatchObject({ code: "forbidden" });
  });
  it("employee list is masked; reveal returns full value", async () => {
    const { api } = setup();
    await api.login("hr", "demo");
    const list = await api.employees({ page_size: 5 });
    expect(list.items[0]!.national_code).toMatch(/^\*+\d{4}$/);
    const full = await api.employee(list.items[0]!.emp_no, true);
    expect(full.national_code).toMatch(/^\d{10}$/);
  });
  it("email send is idempotent by key", async () => {
    const { api, mock } = setup();
    await api.login("hr", "demo");
    const before = mock.store.messages.length;
    const req = { recipients: [{ email: "a@example.test" }], dry_run: false, letter_id: 1 };
    const a = await api.sendEmail(req, "key-1");
    const b = await api.sendEmail(req, "key-1");
    expect(b).toEqual(a);
    expect(mock.store.messages.length).toBe(before + 1);
  });
  it("connector secrets are never returned", async () => {
    const { api } = setup();
    await api.login("admin", "demo");
    const updated = await api.updateConnector("graph", { secrets: { client_secret: "s3cr3t-value" } });
    expect(updated.secrets.client_secret).toBe("set");
    expect(JSON.stringify(await api.connectors())).not.toContain("s3cr3t-value");
  });
});
