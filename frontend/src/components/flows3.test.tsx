import { describe, expect, it } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setup } from "../test/utils";
import { CandidatesScreen } from "../screens/Candidates";
import { EnrollmentsTable } from "../screens/Enrollments";
import { LoginScreen } from "../screens/Login";
import { LettersScreen } from "../screens/Letters";
import { AdminScreen } from "../screens/Admin";
import { App } from "../App";
import { ApiProvider, AuthProvider, toLogin } from "../app-context";
import { ToastProvider } from "./Toast";
import { createApi, createClient } from "../api/client";
import { createMockFetch } from "../api/mock/server";
import { useDraft } from "../lib/draft";

describe("session expiry keeps the user's work (H3)", () => {
  it("toLogin sends the current screen as ?next= plus the expiry flag", () => {
    window.location.hash = "#/runs/3?tab=x";
    toLogin(true);
    expect(window.location.hash).toBe(`#/login?next=${encodeURIComponent("/runs/3?tab=x")}&expired=1`);
    window.location.hash = "#/login?expired=1"; toLogin(true); // never nests
    expect(window.location.hash).toBe("#/login?expired=1");
  });
  it("login shows the Persian expiry message and returns to the same screen", async () => {
    window.location.hash = `#/login?next=${encodeURIComponent("/runs/3")}&expired=1`;
    const api = createApi(createClient({ fetchImpl: createMockFetch({ latency: 0, storage: false }).fetch }));
    render(<QueryClientProvider client={new QueryClient()}><ApiProvider api={api}><ToastProvider><AuthProvider initialUser={null}><LoginScreen /></AuthProvider></ToastProvider></ApiProvider></QueryClientProvider>);
    expect(screen.getByText(/نشست شما منقضی شد/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/نام کاربری/), "hr"); await userEvent.type(screen.getByLabelText(/گذرواژه/), "demo");
    await userEvent.click(screen.getByRole("button", { name: "ورود" }));
    await waitFor(() => expect(window.location.hash).toBe("#/runs/3"));
  });
  it("form drafts survive a remount (sessionStorage) and are cleared explicitly", async () => {
    sessionStorage.clear();
    function F() { const [d, set, clear] = useDraft("t:1", { v: "" }); return <><input aria-label="x" value={d.v} onChange={(e) => set({ v: e.target.value })} /><button onClick={clear}>clear</button></>; }
    const r = render(<F />);
    await userEvent.type(screen.getByLabelText("x"), "نیمه‌کاره");
    r.unmount(); render(<F />);
    expect(screen.getByLabelText("x")).toHaveValue("نیمه‌کاره");
    await userEvent.click(screen.getByText("clear"));
    expect(sessionStorage.getItem("tms.draft:t:1")).toBeNull();
  });
});

describe("route guards (M8)", () => {
  it.each(["/connectors", "/import-export", "/admin"])("viewer opening %s sees the access-denied page", async (path) => {
    const { ui } = await setup("viewer");
    window.location.hash = `#${path}`;
    ui(<App />);
    expect(await screen.findByText("دسترسی ندارید")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "اتصال‌ها" })).not.toBeInTheDocument();
  });
});

describe("candidates: select-all skips flagged people by default (M2)", () => {
  it("shows the count of skipped people and has an explicit include-flagged control", async () => {
    const { ui } = await setup("hr");
    ui(<CandidatesScreen id={3} />);
    await screen.findByText("کارمند غیرفعال");
    await userEvent.click(screen.getByRole("checkbox", { name: "انتخاب همهٔ نتایج بدون هشدار" }));
    expect(screen.getByText(/دارای هشدار را کنار می‌گذارد/)).toBeInTheDocument();
    expect(screen.queryByText(/مورد دارای هشدار$/)).not.toBeInTheDocument(); // no flagged among the selected
    const flaggedRow = screen.getByText("کارمند غیرفعال").closest("tr")!;
    expect(within(flaggedRow).getByRole("checkbox")).not.toBeChecked();
    await userEvent.click(screen.getByRole("switch", { name: /شامل موارد دارای هشدار/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "انتخاب همهٔ نتایج" }));
    expect(within(flaggedRow).getByRole("checkbox")).toBeChecked();
  });
});

describe("bulk motivation (M1)", () => {
  it("marks selected rows with one confirm and one undo", async () => {
    const { ui } = await setup("hr");
    ui(<EnrollmentsTable runId={4} showRun={false} />);
    await screen.findAllByRole("combobox", { name: /^موتیویشن / });
    const rows = () => screen.getAllByRole("combobox", { name: /^موتیویشن / }) as HTMLSelectElement[];
    const before = rows().slice(0, 2).map((s) => s.value);
    const boxes = screen.getAllByRole("checkbox", { name: /^انتخاب (?!همهٔ)/ });
    await userEvent.click(boxes[0]!); await userEvent.click(boxes[1]!);
    await userEvent.click(screen.getByRole("button", { name: /رد موتیویشن/ }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /ثبت «خیر» برای همه/ }));
    await waitFor(() => expect(rows().slice(0, 2).map((s) => s.value)).toEqual(["no", "no"]));
    await userEvent.click(await screen.findByRole("button", { name: "برگردان" }));
    await waitFor(() => expect(rows().slice(0, 2).map((s) => s.value)).toEqual(before));
  });
});

describe("letters (H1/M7/M9)", () => {
  it("never preselects a course, and follows the hash when it changes", async () => {
    const { ui } = await setup("hr");
    window.location.hash = "#/letters?kind=settlement_letter";
    ui(<LettersScreen />);
    const course = await screen.findByLabelText(/^دوره/);
    expect(course).toHaveValue("");
    expect(screen.getByText("دوره‌ای انتخاب نشده است.")).toBeInTheDocument();
    act(() => { window.location.hash = "#/letters?kind=institute_letter&run=5"; });
    await waitFor(() => expect(screen.getByLabelText("نوع نامه")).toHaveValue("institute_letter"));
    await waitFor(() => expect(screen.getByLabelText(/^دوره/)).toHaveValue("5"));
    expect(await screen.findByTestId("preview-course")).toHaveTextContent("مدیریت پروژه");
  });
  it("list has a course column; untouched missing fields are not red", async () => {
    const { ui } = await setup("hr");
    window.location.hash = "#/letters?kind=settlement_letter&run=3";
    ui(<LettersScreen />);
    expect(await screen.findByRole("columnheader", { name: "دوره" })).toBeInTheDocument();
    await screen.findByText(/فیلد باید تکمیل شود/);
    expect(document.querySelectorAll('[aria-invalid="true"]').length).toBe(0);
    expect(screen.getByText(/فیلد باقی مانده/)).toBeInTheDocument();
  });
});

describe("admin users (PATCH)", () => {
  it("handles the last-admin 409 with a clear message", async () => {
    const { ui, mock } = await setup("admin");
    mock.store.users.forEach((u) => { if (u.username !== "admin" && u.role === "admin") u.role = "hr"; });
    ui(<AdminScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "غیرفعال کردن admin" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "غیرفعال کن" }));
    expect(await screen.findByText(/آخرین مدیر فعال/)).toBeInTheDocument();
    expect(mock.store.users.find((u) => u.username === "admin")!.active).toBe(true);
  });
  it("role change and password reset", async () => {
    const { ui, mock } = await setup("admin");
    ui(<AdminScreen />);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "نقش viewer" }), "hr");
    await waitFor(() => expect(mock.store.users.find((u) => u.username === "viewer")!.role).toBe("hr"));
    await userEvent.click(screen.getByRole("button", { name: "بازنشانی گذرواژه viewer" }));
    const dlg = screen.getByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: /ثبت گذرواژهٔ جدید/ }));
    expect(within(dlg).getByText("گذرواژه باید دست‌کم ۸ نویسه باشد.")).toBeInTheDocument();
    await userEvent.type(within(dlg).getByLabelText(/گذرواژهٔ جدید/), "Newpass-123"); await userEvent.click(within(dlg).getByRole("button", { name: /ثبت گذرواژهٔ جدید/ }));
    await waitFor(() => expect(mock.store.users.find((u) => u.username === "viewer")!.password).toBe("Newpass-123"));
  });
});
