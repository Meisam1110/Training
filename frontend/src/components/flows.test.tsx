import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setup } from "../test/utils";
import { EmailSendDialog, MaskedPII, SecretField } from "./domain";
import { ConnectorCard } from "../screens/Connectors";
import { LoginScreen } from "../screens/Login";
import { Dialog } from "./Dialog";
import { DatePicker } from "./DatePicker";
import { useState } from "react";
import { ApiProvider, AuthProvider } from "../app-context";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "./Toast";
import { createApi, createClient } from "../api/client";
import { createMockFetch } from "../api/mock/server";


async function letterAndRecipients(api: Awaited<ReturnType<typeof setup>>["api"], letterId: number) {
  const letters = await api.letters({ page_size: 50 });
  const letter = letters.items.find((l) => l.id === letterId)!;
  const en = await api.runEnrollments(letter.run_id!, { page_size: 200 });
  const recipients = en.items.map((e) => ({ email: e.email, name: e.name_fa }));
  recipients.push({ email: "bounce@example.test", name: "برگشتی" });
  return { letter, recipients };
}

describe("send-email dialog", () => {
  it("shows what is sent; dry-run ON for a first send; confirm shows counts; double click sends once", async () => {
    const { ui, calls, api } = await setup("hr");
    const { letter, recipients } = await letterAndRecipients(api, 3); // letter 3 has never been sent live
    ui(<EmailSendDialog open onClose={() => {}} letter={letter} courseName="ارتباط مؤثر" recipients={recipients} />);
    const summary = await screen.findByTestId("mail-summary");
    expect(summary).toHaveTextContent(letter.number); expect(summary).toHaveTextContent("ارتباط مؤثر"); expect(summary).toHaveTextContent(letter.subject); expect(summary).toHaveTextContent(letter.file_name);
    const sw = await screen.findByTestId("dry-run");
    await waitFor(() => expect(sw).toBeChecked());
    await userEvent.click(screen.getByRole("button", { name: /ادامه و بازبینی/ }));
    expect(screen.getByTestId("confirm-count")).toHaveTextContent(String(recipients.length).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[+d]!));
    expect(screen.getByRole("dialog")).toHaveTextContent("ارتباط مؤثر");
    const go = screen.getByRole("button", { name: /اجرای آزمایشی برای/ });
    fireEvent.click(go); fireEvent.click(go); // a nervous double-click
    await screen.findByTestId("send-results");
    const sends = calls.filter((c) => c.url.includes("/email/send"));
    expect(sends).toHaveLength(1);
    const body = JSON.parse(String(sends[0]!.body));
    expect(body.dry_run).toBe(true); expect(body.idempotency_key).toBeTruthy();
  });

  it("warns per recipient who already received it, unchecks them, keeps dry-run ON, and warns again on a repeat real send", async () => {
    const { ui, api, calls } = await setup("hr");
    const { letter, recipients } = await letterAndRecipients(api, 1); // seed: 4 people already got letter 1 for real
    ui(<EmailSendDialog open onClose={() => {}} letter={letter} courseName="مذاکرهٔ مؤثر" recipients={recipients} />);
    const sw = await screen.findByTestId("dry-run");
    await waitFor(() => expect(screen.getAllByText(/قبلاً در تاریخ/).length).toBe(4));
    expect(sw).toBeChecked(); // already-sent recipients => dry-run stays ON
    const boxes = screen.getAllByRole("checkbox", { name: /^گیرنده / });
    expect(boxes.filter((b) => (b as HTMLInputElement).checked)).toHaveLength(recipients.length - 4);
    // deliberately include one already-notified person and switch to a real send
    const already = boxes.find((b) => !(b as HTMLInputElement).checked)!; await userEvent.click(already);
    await userEvent.click(sw);
    await userEvent.click(screen.getByRole("button", { name: /ادامه و بازبینی/ }));
    expect(screen.getByText(/هشدار ارسال تکراری/)).toBeInTheDocument();
    expect(screen.getByText(/قابل بازگشت نیست/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /ارسال واقعی به/ }));
    const list = await screen.findByTestId("send-results");
    expect(within(list).getByText("ناموفق")).toBeInTheDocument(); // the bounce@ address
    expect(calls.filter((c) => c.url.includes("/email/send"))).toHaveLength(1);
  });
});

describe("secret fields are write-only", () => {
  it("never renders a stored value; shows set / not set", () => {
    render(<><SecretField label="رمز A" state="set" value="" onChange={() => {}} /><SecretField label="رمز B" state="not_set" value="" onChange={() => {}} /></>);
    expect(screen.getByText("تنظیم شده")).toBeInTheDocument();
    expect(screen.getByText("تنظیم نشده")).toBeInTheDocument();
    for (const el of screen.getAllByDisplayValue("")) expect((el as HTMLInputElement).type).toBe("password");
    expect(screen.getByLabelText("رمز A")).toHaveValue("");
  });
  it("connector save sends only the secrets the user typed", async () => {
    const { ui, api } = await setup("admin");
    const spy = vi.spyOn(api, "updateConnector");
    const conns = await api.connectors();
    ui(<ConnectorCard c={conns.find((c) => c.kind === "ifs")!} canEdit canRun />);
    await userEvent.type(screen.getByLabelText("رمز کلاینت"), "new-secret-1");
    await userEvent.click(screen.getByRole("button", { name: "ذخیرهٔ تنظیمات" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const body = spy.mock.calls[0]![1];
    expect(body.secrets).toEqual({ client_secret: "new-secret-1" });
    await waitFor(() => expect(screen.getByLabelText("رمز کلاینت")).toHaveValue("")); // cleared after save
  });
  it("auth-mode selector swaps the credential fields", async () => {
    const { ui, api } = await setup("admin");
    const conns = await api.connectors();
    ui(<ConnectorCard c={conns.find((c) => c.kind === "ifs")!} canEdit canRun />);
    expect(screen.getByLabelText("رمز کلاینت")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("روش احراز هویت"), "basic");
    expect(screen.queryByLabelText("رمز کلاینت")).not.toBeInTheDocument();
    expect(screen.getByLabelText("گذرواژه")).toBeInTheDocument();
  });
  it("test-connection shows a clear failure state", async () => {
    const { ui, api } = await setup("admin");
    const conns = await api.connectors();
    ui(<ConnectorCard c={conns.find((c) => c.kind === "smtp")!} canEdit canRun />);
    await userEvent.click(screen.getByRole("button", { name: /آزمون اتصال/ }));
    expect(await screen.findByText("اتصال ناموفق")).toBeInTheDocument();
  });
});

describe("PII is masked by default", () => {
  it("shows masked value, requires an audited confirmation to reveal", async () => {
    const { ui, api, mock } = await setup("hr");
    const emp = (await api.employees({ page_size: 1 })).items[0]!;
    const auditBefore = mock.store.audit.length;
    ui(<MaskedPII emp={emp} />);
    expect(screen.getByTestId("pii-national")).toHaveTextContent(/^\*+\d{4}$/);
    await userEvent.click(screen.getByRole("button", { name: /نمایش اطلاعات/ }));
    const dlg = screen.getByRole("dialog");
    expect(within(dlg).getByText(/در گزارش ممیزی ثبت می‌شود/)).toBeInTheDocument();
    expect(mock.store.audit.length).toBe(auditBefore); // nothing revealed/audited before confirming
    await userEvent.click(within(dlg).getByRole("button", { name: /نمایش بده/ }));
    await waitFor(() => expect(screen.getByTestId("pii-national")).toHaveTextContent(/^\d{10}$/));
    expect(mock.store.audit.length).toBe(auditBefore + 1);
    await userEvent.click(screen.getByRole("button", { name: /پنهان کردن/ }));
    expect(screen.getByTestId("pii-national")).toHaveTextContent(/^\*+/);
  });
});

describe("form validation (login)", () => {
  function mountLogin() {
    const api = createApi(createClient({ fetchImpl: createMockFetch({ latency: 0, storage: false }).fetch }));
    const qc = new QueryClient();
    return render(<QueryClientProvider client={qc}><ApiProvider api={api}><ToastProvider><AuthProvider initialUser={null}><LoginScreen /></AuthProvider></ToastProvider></ApiProvider></QueryClientProvider>);
  }
  it("shows inline Persian errors for empty fields and links them with aria", async () => {
    mountLogin();
    await userEvent.click(screen.getByRole("button", { name: "ورود" }));
    expect(screen.getByText("نام کاربری را وارد کنید.")).toBeInTheDocument();
    expect(screen.getByText("گذرواژه را وارد کنید.")).toBeInTheDocument();
    const u = screen.getByLabelText(/نام کاربری/);
    expect(u).toHaveAttribute("aria-invalid", "true");
    expect(u.getAttribute("aria-describedby")).toBeTruthy();
  });
  it("preserves input and shows the server message after a failed login; submit re-enabled", async () => {
    mountLogin();
    await userEvent.type(screen.getByLabelText(/نام کاربری/), "admin");
    await userEvent.type(screen.getByLabelText(/گذرواژه/), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "ورود" }));
    expect(await screen.findByText("نام کاربری یا گذرواژه درست نیست.")).toBeInTheDocument();
    expect(screen.getByLabelText(/نام کاربری/)).toHaveValue("admin");
    expect(screen.getByLabelText(/گذرواژه/)).toHaveValue("wrong");
    expect(screen.getByRole("button", { name: "ورود" })).toBeEnabled();
  });
});

describe("dialog accessibility", () => {
  function Harness() {
    const [o, setO] = useState(false);
    return <><button onClick={() => setO(true)}>open</button><Dialog open={o} title="عنوان" onClose={() => setO(false)} footer={<button>بستن پایین</button>}><input aria-label="ورودی" /></Dialog></>;
  }
  it("traps focus, closes on Escape and restores focus", async () => {
    render(<div id="root"><Harness /></div>);
    const opener = screen.getByText("open"); opener.focus();
    await userEvent.click(opener);
    const dlg = screen.getByRole("dialog");
    expect(dlg).toHaveAttribute("aria-modal", "true");
    expect(dlg).toHaveAccessibleName("عنوان");
    expect(within(dlg).getByLabelText("ورودی")).toHaveFocus();
    for (let i = 0; i < 6; i++) { await userEvent.tab(); expect(dlg.contains(document.activeElement)).toBe(true); }
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("Jalali date picker", () => {
  it("accepts Persian digits, emits ISO Gregorian, flags invalid dates", async () => {
    const onChange = vi.fn();
    function H() { const [v, setV] = useState(""); return <DatePicker label="شروع" value={v} onChange={(x) => { onChange(x); setV(x); }} />; }
    render(<H />);
    const input = screen.getByLabelText("شروع");
    await userEvent.type(input, "۱۴۰۵/۰۷/۰۸{Enter}");
    expect(onChange).toHaveBeenLastCalledWith("2026-09-30");
    await userEvent.clear(input); await userEvent.type(input, "1404/12/30{Enter}");
    expect(screen.getByText("اسفند ۱۴۰۴ فقط ۲۹ روز دارد.")).toBeInTheDocument();
    await userEvent.clear(input); await userEvent.type(input, "2026/09/30{Enter}");
    expect(screen.getByText(/سال میلادی به نظر می‌رسد/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "اعمال" })); // offered Jalali equivalent
    expect(onChange).toHaveBeenLastCalledWith("2026-09-30");
    await userEvent.clear(input); await userEvent.type(input, "14050708{Enter}");
    expect(onChange).toHaveBeenLastCalledWith("2026-09-30");
  });
  it("calendar popover is keyboard operable", async () => {
    const onChange = vi.fn();
    render(<DatePicker label="پایان" value="2026-09-30" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /انتخاب تاریخ از تقویم/ }));
    const cell = await screen.findByRole("gridcell", { name: "۸ مهر ۱۴۰۵" });
    await waitFor(() => expect(cell).toHaveFocus());
    await userEvent.keyboard("{ArrowLeft}{Enter}"); // RTL: left = next day
    expect(onChange).toHaveBeenCalledWith("2026-10-01");
  });
});
