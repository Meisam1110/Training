import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { Candidate } from "../api/types";
import { DataTable } from "../components/DataTable";
import { CheckBox, TextField, Switch } from "../components/Field";
import { Button, Callout, Chip, ErrorState, Ident, LinkButton, PageHead } from "../components/ui";
import { ConfirmDialog } from "../components/Dialog";
import { useToast } from "../components/Toast";
import { useDebounced } from "../lib/hooks";
import { fmtJalali } from "../lib/jalali";
import { errMsg } from "../lib/query";
import { normFa, toFa } from "../lib/digits";
import { EXCLUDE_FA, FLAG_FA } from "../lib/labels";
import { navigate } from "../lib/router";

const blocking = (c: Candidate) => c.flags.filter((f) => f !== "level3_eligible");

/** Candidates = unassigned IDP requests for this run's course. Selecting + adding assigns them to the run. */
export function CandidatesScreen({ id }: { id: number }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast(); const { canWrite } = useAuth();
  const [q, setQ] = useState(""); const [hideFlagged, setHideFlagged] = useState(false); const [sel, setSel] = useState<Set<number>>(new Set()); const [ask, setAsk] = useState(false); const [inclFlagged, setInclFlagged] = useState(false);
  const dq = useDebounced(q);
  const run = useQuery({ queryKey: ["run", id], queryFn: () => api.run(id) });
  const res = useQuery({ queryKey: ["candidates", id, hideFlagged], queryFn: () => api.searchCandidates(id, { include_flagged: !hideFlagged }), placeholderData: (p) => p, enabled: canWrite });
  const items = useMemo(() => (res.data?.candidates ?? []).filter((c) => !dq || normFa(`${c.name_fa} ${c.emp_no} ${c.division} ${c.ticket}`).includes(normFa(dq))), [res.data, dq]);
  const eligible = items.filter((c) => inclFlagged || blocking(c).length === 0); // what "select all" touches
  const skipped = items.length - eligible.length;
  const allOn = eligible.length > 0 && eligible.every((c) => sel.has(c.enrollment_id));
  const flaggedSel = items.filter((c) => sel.has(c.enrollment_id) && blocking(c).length);
  const toggle = (n: number) => setSel((s) => { const x = new Set(s); if (x.has(n)) x.delete(n); else x.add(n); return x; });

  const add = useMutation({
    mutationFn: () => api.bulkEnrollments({ enrollment_ids: [...sel], run_id: id }),
    onSuccess: (r) => {
      toast.push(r.failed.length ? { kind: "error", message: `${toFa(r.updated.length)} نفر اضافه شد، ${toFa(r.failed.length)} مورد ناموفق (${r.failed[0]!.reason}).` } : { message: `${toFa(r.updated.length)} کاندیدا به دوره اضافه شد.` });
      void qc.invalidateQueries(); if (!r.failed.length) navigate(`/runs/${id}`); else { setAsk(false); setSel(new Set(r.failed.map((f) => f.id))); }
    },
    onError: (e) => { setAsk(false); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const onAdd = () => (flaggedSel.length ? setAsk(true) : add.mutate());

  const cols = useMemo<ColumnDef<Candidate, any>[]>(() => [
    { id: "select", size: 56, header: () => <CheckBox label={inclFlagged ? "انتخاب همهٔ نتایج" : "انتخاب همهٔ نتایج بدون هشدار"} checked={allOn} disabled={!canWrite}
        onChange={() => setSel((s) => { const n = new Set(s); eligible.forEach((c) => (allOn ? n.delete(c.enrollment_id) : n.add(c.enrollment_id))); return n; })} />,
      cell: ({ row }) => <CheckBox label={`انتخاب ${row.original.name_fa}`} disabled={!canWrite} checked={sel.has(row.original.enrollment_id)} onChange={() => toggle(row.original.enrollment_id)} /> },
    { id: "name_fa", header: "نام", cell: ({ row }) => <strong>{row.original.name_fa}</strong> },
    { id: "emp_no", header: "شمارهٔ پرسنلی", cell: ({ row }) => <Ident>{row.original.emp_no}</Ident> },
    { id: "division", header: "واحد", cell: ({ row }) => row.original.division },
    { id: "ticket", header: "تیکت", cell: ({ row }) => <Ident>{row.original.ticket}</Ident> },
    { id: "flags", header: "هشدارها", cell: ({ row }) => row.original.flags.length === 0 ? <Chip tone="ok">بدون هشدار</Chip>
        : <span className="row" style={{ gap: 6 }}>{row.original.flags.map((f) => <Chip key={f} tone={f === "level3_eligible" ? "info" : "warn"}>{FLAG_FA[f] ?? f}</Chip>)}</span> },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [sel, allOn, items, canWrite, inclFlagged]);

  return (<>
    <PageHead title="انتخاب کاندیدا" subtitle={run.data ? `${run.data.course_name_fa} · ${fmtJalali(run.data.start_date)} تا ${fmtJalali(run.data.end_date)}` : undefined}
      actions={<LinkButton href={`#/runs/${id}`}>بازگشت به دوره</LinkButton>} />
    {!canWrite ? <Callout tone="info">جستجو و افزودن کاندیدا فقط برای مدیر سامانه و کارشناس آموزش در دسترس است. نقش «ناظر» می‌تواند ثبت‌نام‌های دوره را در صفحهٔ دوره ببیند.</Callout> : null}
    {canWrite && <div className="card card--flush" style={{ marginBlockStart: "var(--space-4)" }}>
      <div className="toolbar" role="search">
        <div className="search"><TextField label="جستجوی کاندیدا" type="search" value={q} onChange={setQ} placeholder="نام، شمارهٔ پرسنلی، واحد یا تیکت" /></div>
        <Switch checked={hideFlagged} onChange={setHideFlagged} label="پنهان کردن موارد دارای هشدار" />
        <Switch checked={inclFlagged} onChange={setInclFlagged} label="«انتخاب همه» شامل موارد دارای هشدار هم بشود" />
      </div>
      {res.error && !res.data ? <ErrorState error={res.error} onRetry={() => res.refetch()} /> :
        <DataTable caption="درخواست‌های IDP قابل تخصیص به این دوره" columns={cols} data={items} getRowId={(c) => String(c.enrollment_id)} loading={res.isLoading} virtualize maxHeight={480}
          isSelected={(c) => sel.has(c.enrollment_id)}
          empty={{ title: "کاندیدایی پیدا نشد", description: dq ? "عبارت جستجو را تغییر دهید." : "درخواست IDP بدون تخصیصی برای این دوره وجود ندارد. ابتدا خروجی iCare را درون‌ریزی کنید.", action: dq ? <Button onClick={() => setQ("")}>پاک کردن جستجو</Button> : <LinkButton variant="primary" href="#/import-export">رفتن به درون‌ریزی</LinkButton> }} />}
      <div className="pager" style={{ position: "sticky", insetBlockEnd: 0, background: "var(--surface)" }}>
        <span aria-live="polite"><strong>{toFa(sel.size)}</strong> نفر انتخاب شده{flaggedSel.length > 0 && <span className="overlap"> · {toFa(flaggedSel.length)} مورد دارای هشدار</span>}{!inclFlagged && skipped > 0 && <span className="muted"> · «انتخاب همه» {toFa(skipped)} نفر دارای هشدار را کنار می‌گذارد</span>}</span>
        <span className="row">
          <Button onClick={() => setSel(new Set())} disabled={!sel.size}>پاک کردن انتخاب</Button>
          <Button variant="primary" icon="plus" disabled={!sel.size || !canWrite} pending={add.isPending && !ask} onClick={onAdd}>افزودن {toFa(sel.size)} نفر به دوره</Button>
        </span>
      </div>
    </div>}
    {(res.data?.excluded.length ?? 0) > 0 && (
      <details className="card" style={{ marginBlockStart: "var(--space-4)" }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, minBlockSize: 44, display: "flex", alignItems: "center" }}>{toFa(res.data!.excluded.length)} درخواست به‌دلیل تداخل یا هشدار کنار گذاشته شد</summary>
        <ul className="result-list">{res.data!.excluded.map((x) => (
          <li key={x.enrollment_id}><span className="ltr num">{x.ticket}</span><span className="overlap">{x.reason.split(",").map((r) => EXCLUDE_FA[r] ?? FLAG_FA[r] ?? r).join("، ")}{x.conflicting_ticket && <> · <span className="ltr">{x.conflicting_ticket}</span></>}</span></li>))}</ul>
      </details>)}
    <ConfirmDialog open={ask} title="افزودن مواردِ دارای هشدار" confirmLabel="با هشدار اضافه کن" pending={add.isPending} onCancel={() => setAsk(false)} onConfirm={() => add.mutate()}
      consequence={`${toFa(flaggedSel.length)} نفر از انتخاب‌شده‌ها هشدار دارند. در صورت ادامه به دوره اضافه می‌شوند و مسئولیت با شماست.`}>
      <ul className="result-list">{flaggedSel.slice(0, 12).map((c) => <li key={c.enrollment_id}><span>{c.name_fa}</span><span className="overlap">{blocking(c).map((f) => FLAG_FA[f] ?? f).join("، ")}</span></li>)}{flaggedSel.length > 12 && <li className="muted">و {toFa(flaggedSel.length - 12)} نفر دیگر…</li>}</ul>
    </ConfirmDialog>
  </>);
}
