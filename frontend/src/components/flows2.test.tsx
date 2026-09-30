import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setup } from "../test/utils";
import { CandidatesScreen } from "../screens/Candidates";
import { EnrollmentsTable } from "../screens/Enrollments";
import { RunsScreen } from "../screens/Runs";
import { DataTable } from "./DataTable";
import { useState } from "react";

describe("candidates picker", () => {
  it("shows warning chips, asks for confirmation when flagged people are selected, and assigns via bulk", async () => {
    const { ui, calls } = await setup("hr");
    ui(<CandidatesScreen id={3} />);
    const flagged = await screen.findByText("کارمند غیرفعال");
    expect(flagged).toBeInTheDocument();
    const row = flagged.closest("tr")!;
    await userEvent.click(within(row).getByRole("checkbox")); // keyboard-operable native checkbox
    expect(screen.getByText(/۱ مورد دارای هشدار/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /افزودن ۱ نفر به دوره/ }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(/هشدار دارند/)).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: /با هشدار اضافه کن/ }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/enrollments:bulk"))).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.url.includes("/enrollments:bulk"))!.body));
    expect(body).toMatchObject({ run_id: 3 });
    expect(body.enrollment_ids).toHaveLength(1);
  });
  it("viewer gets an explanation instead of the picker (candidates:search is hr+)", async () => {
    const { ui } = await setup("viewer");
    ui(<CandidatesScreen id={3} />);
    expect(await screen.findByText(/فقط برای مدیر سامانه و کارشناس آموزش/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /افزودن/ })).not.toBeInTheDocument();
  });
});

describe("enrollments inline edit", () => {
  it("updates optimistically and offers undo", async () => {
    const { ui } = await setup("hr");
    ui(<EnrollmentsTable runId={4} showRun={false} />);
    const sel = (await screen.findAllByRole("combobox", { name: /^انگیزه‌نامه / }))[0]! as HTMLSelectElement;
    const before = sel.value; const next = before === "no" ? "yes" : "no";
    await userEvent.selectOptions(sel, next);
    expect(sel.value).toBe(next);
    const undo = await screen.findByRole("button", { name: "برگردان" });
    await userEvent.click(undo);
    await waitFor(() => expect((screen.getAllByRole("combobox", { name: /^انگیزه‌نامه / })[0] as HTMLSelectElement).value).toBe(before));
  });
  it("rolls back and shows an error toast when the server refuses", async () => {
    const { ui, api } = await setup("hr");
    vi.spyOn(api, "patchEnrollment").mockRejectedValueOnce(new Error("سرور رد کرد"));
    ui(<EnrollmentsTable runId={4} showRun={false} />);
    const sel = (await screen.findAllByRole("combobox", { name: /^انگیزه‌نامه / }))[0]! as HTMLSelectElement;
    const before = sel.value;
    await userEvent.selectOptions(sel, before === "no" ? "yes" : "no");
    expect(await screen.findByText(/مقدار قبلی برگردانده شد/)).toBeInTheDocument();
    await waitFor(() => expect((screen.getAllByRole("combobox", { name: /^انگیزه‌نامه / })[0] as HTMLSelectElement).value).toBe(before));
  });
  it("viewer sees read-only chips, no inputs", async () => {
    const { ui } = await setup("viewer");
    ui(<EnrollmentsTable runId={4} showRun={false} />);
    await screen.findAllByText("بله");
    expect(screen.queryAllByRole("combobox", { name: /^انگیزه‌نامه / })).toHaveLength(0);
  });
});

describe("role-aware actions", () => {
  it("viewer does not get the create-run button; hr does", async () => {
    const v = await setup("viewer"); const r1 = v.ui(<RunsScreen />);
    await screen.findAllByText("مدیریت زمان");
    expect(screen.queryByRole("button", { name: /دورهٔ جدید/ })).not.toBeInTheDocument();
    r1.unmount();
    const h = await setup("hr"); h.ui(<RunsScreen />);
    expect(await screen.findByRole("button", { name: /دورهٔ جدید/ })).toBeInTheDocument();
  });
});

describe("table states", () => {
  const cols = [{ id: "a", header: "ستون", cell: ({ row }: { row: { original: { a: string } } }) => row.original.a }];
  it("skeleton while loading, empty state with CTA, error state with retry", async () => {
    const retry = vi.fn();
    const { rerender } = render(<DataTable caption="t" columns={cols} data={undefined} getRowId={(r: { a: string }) => r.a} loading empty={{ title: "خالی" }} />);
    expect(document.querySelectorAll(".skel").length).toBeGreaterThan(3);
    rerender(<DataTable caption="t" columns={cols} data={[]} getRowId={(r: { a: string }) => r.a} empty={{ title: "خالی", action: <button>اقدام بعدی</button> }} />);
    expect(screen.getByText("خالی")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "اقدام بعدی" })).toBeInTheDocument();
    rerender(<DataTable caption="t" columns={cols} data={undefined} getRowId={(r: { a: string }) => r.a} error={new Error("قطع شد")} onRetry={retry} empty={{ title: "خالی" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("قطع شد");
    await userEvent.click(screen.getByRole("button", { name: /تلاش دوباره/ })); expect(retry).toHaveBeenCalled();
  });
  it("sortable header exposes aria-sort and reports the next sort", async () => {
    const onSort = vi.fn();
    function H() { const [s, setS] = useState(""); return <DataTable caption="t" columns={cols} data={[{ a: "x" }]} getRowId={(r: { a: string }) => r.a} sort={s} onSort={(v) => { onSort(v); setS(v); }} empty={{ title: "e" }} />; }
    render(<H />);
    const th = screen.getByRole("columnheader", { name: "ستون" });
    expect(th).toHaveAttribute("aria-sort", "none");
    await userEvent.click(within(th).getByRole("button")); expect(onSort).toHaveBeenLastCalledWith("a");
    expect(screen.getByRole("columnheader", { name: "ستون" })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(within(screen.getByRole("columnheader")).getByRole("button")); expect(onSort).toHaveBeenLastCalledWith("-a");
  });
});
