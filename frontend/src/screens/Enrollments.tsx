import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { ApiList, EditableEnrollmentField, Enrollment, EnrollmentPatch } from "../api/types";
import { DataTable } from "../components/DataTable";
import { CheckBox, TextField, SelectField } from "../components/Field";
import { ConfirmDialog } from "../components/Dialog";
import { Button, Ident, LinkButton, PageHead } from "../components/ui";
import { useToast } from "../components/Toast";
import { AttChip, TriChip } from "../components/domain";
import { ATT_FA, TRI_FA } from "../lib/labels";
import type { Tri } from "../api/types";
import { useDebounced } from "../lib/hooks";
import { Link, useRoute } from "../lib/router";
import { errMsg } from "../lib/query";
import { toFa } from "../lib/digits";

const TRI_OPTS = (["yes", "no", "pending"] as const).map((v) => ({ value: v, label: TRI_FA[v] }));
const ATT_OPTS = (["attended", "absent", "pending"] as const).map((v) => ({ value: v, label: ATT_FA[v] }));
const FIELD_FA: Record<EditableEnrollmentField, string> = { motivation: "انگیزه‌نامه", registration: "ثبت‌نام", calendar: "تقویم", attendance: "حضور" };

/** Inline-editable enrollments table: optimistic updates, rollback on failure, undo toast. */
export function EnrollmentsTable({ runId, showRun = true, initialQ = "", initialMotivation = "" }: { runId?: number; showRun?: boolean; initialQ?: string; initialMotivation?: string }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast(); const { canWrite } = useAuth();
  const [q, setQ] = useState(initialQ); const [motivation, setMotivation] = useState(initialMotivation); const [page, setPage] = useState(1); const [sort, setSort] = useState("");
  const dq = useDebounced(q);
  const [sel, setSel] = useState<Set<number>>(new Set()); const [ask, setAsk] = useState<null | "yes" | "no">(null);
  const params = { q: dq, motivation, page, page_size: 25, sort, run_id: runId };
  const list = useQuery({ queryKey: ["enrollments", params], queryFn: () => api.enrollments(params), placeholderData: (p) => p });

  const patchCaches = (id: number, patch: EnrollmentPatch) =>
    qc.setQueriesData<ApiList<Enrollment>>({ queryKey: ["enrollments"] }, (old) => old && { ...old, items: old.items.map((e) => (e.id === id ? { ...e, ...patch } : e)) });

  const mut = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: EnrollmentPatch; prev: EnrollmentPatch; undo?: boolean }) => api.patchEnrollment(id, patch),
    onMutate: async () => { await qc.cancelQueries({ queryKey: ["enrollments"] }); },
    onError: (e, { id, prev }) => { patchCaches(id, prev); toast.push({ kind: "error", message: `ذخیره نشد و مقدار قبلی برگردانده شد: ${errMsg(e)}` }); },
    onSuccess: (_d, { id, prev, patch, undo }) => {
      void qc.invalidateQueries({ queryKey: ["enrollments"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (undo) { toast.push({ message: "تغییر برگردانده شد." }); return; }
      const f = Object.keys(patch)[0] as EditableEnrollmentField;
      toast.push({ message: `«${FIELD_FA[f]}» ذخیره شد.`, action: { label: "برگردان", onClick: () => run({ id, patch: prev, prev: patch, undo: true }) } });
    },
  });
  /** optimistic: patch every cached list synchronously, then persist; onError rolls back */
  const run = (v: { id: number; patch: EnrollmentPatch; prev: EnrollmentPatch; undo?: boolean }) => { patchCaches(v.id, v.patch); mut.mutate(v); };
  const edit = (e: Enrollment, f: EditableEnrollmentField, v: string) => {
    if (e[f] === v) return;
    run({ id: e.id, patch: { [f]: v } as EnrollmentPatch, prev: { [f]: e[f] } as EnrollmentPatch });
  };
  const bulk = useMutation({
    mutationFn: async ({ ids, value, prev }: { ids: number[]; value: Tri; prev: Map<number, Tri>; undo?: boolean }) => { void prev; return api.bulkEnrollments({ enrollment_ids: ids, patch: { motivation: value } }); },
    onError: (e, { ids, prev }) => { ids.forEach((id) => patchCaches(id, { motivation: prev.get(id) ?? "pending" })); toast.push({ kind: "error", message: `اعمال گروهی انجام نشد و مقدارهای قبلی برگردانده شد: ${errMsg(e)}` }); },
    onSuccess: (r, { value, prev, undo }) => {
      r.failed.forEach((f) => patchCaches(f.id, { motivation: prev.get(f.id) ?? "pending" }));
      void qc.invalidateQueries({ queryKey: ["enrollments"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); void qc.invalidateQueries({ queryKey: ["run"] });
      if (undo) { toast.push({ message: "تغییر گروهی برگردانده شد." }); return; }
      const done = r.updated.length;
      toast.push({ kind: r.failed.length ? "error" : "info", message: `«انگیزه‌نامه: ${TRI_FA[value]}» برای ${toFa(done)} نفر ثبت شد${r.failed.length ? ` (${toFa(r.failed.length)} مورد ناموفق)` : ""}.`,
        action: { label: "برگردان", onClick: () => undoBulk(r.updated, prev) } });
    },
  });
  const undoBulk = (ids: number[], prev: Map<number, Tri>) => {
    const groups = new Map<Tri, number[]>(); ids.forEach((id) => { const v = prev.get(id) ?? "pending"; groups.set(v, [...(groups.get(v) ?? []), id]); });
    groups.forEach((gids, v) => { gids.forEach((id) => patchCaches(id, { motivation: v })); bulk.mutate({ ids: gids, value: v, prev: new Map(gids.map((id) => [id, (v === "yes" ? "no" : "yes") as Tri])), undo: true }); });
  };
  const applyBulk = (value: Tri) => {
    const ids = [...sel]; const prev = new Map<number, Tri>();
    (list.data?.items ?? []).forEach((e) => { if (sel.has(e.id)) prev.set(e.id, e.motivation); });
    ids.forEach((id) => patchCaches(id, { motivation: value })); setAsk(null); setSel(new Set());
    bulk.mutate({ ids, value, prev });
  };
  const cell = (f: EditableEnrollmentField, opts: { value: string; label: string }[]) => ({ row }: { row: { original: Enrollment } }) => {
    const e = row.original; const v = e[f] as string;
    if (!canWrite) return f === "attendance" ? <AttChip v={e.attendance} /> : <TriChip v={e[f as "motivation"]} />;
    return <select className="select" style={{ minInlineSize: 110 }} aria-label={`${FIELD_FA[f]} ${e.name_fa}`} value={v} onChange={(ev) => edit(e, f, ev.target.value)}>
      {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>;
  };
  const items = list.data?.items ?? [];
  const allOn = items.length > 0 && items.every((e) => sel.has(e.id));
  const cols: ColumnDef<Enrollment, any>[] = [
    ...(canWrite ? [{ id: "select", size: 56, header: () => <CheckBox label="انتخاب همهٔ ردیف‌های این صفحه" checked={allOn} onChange={() => setSel(allOn ? new Set() : new Set(items.map((e) => e.id)))} />,
      cell: ({ row }: { row: { original: Enrollment } }) => <CheckBox label={`انتخاب ${row.original.name_fa}`} checked={sel.has(row.original.id)} onChange={() => setSel((s) => { const n = new Set(s); if (n.has(row.original.id)) n.delete(row.original.id); else n.add(row.original.id); return n; })} /> } as ColumnDef<Enrollment, any>] : []),
    { id: "name_fa", header: "نام", cell: ({ row }) => <span><strong>{row.original.name_fa}</strong><br /><span className="muted">{row.original.division}</span></span> },
    ...(showRun ? [{ id: "run_name_fa", header: "دوره", cell: ({ row }: { row: { original: Enrollment } }) => <Link to={`/runs/${row.original.run_id}`}>{row.original.run_name_fa}</Link> } as ColumnDef<Enrollment, any>] : []),
    { id: "ticket", header: "تیکت", cell: ({ row }) => <Ident>{row.original.ticket}</Ident> },
    { id: "motivation", header: "انگیزه‌نامه", cell: cell("motivation", TRI_OPTS) },
    { id: "registration", header: "ثبت‌نام", cell: cell("registration", TRI_OPTS), enableSorting: false },
    { id: "calendar", header: "تقویم", cell: cell("calendar", TRI_OPTS), enableSorting: false },
    { id: "attendance", header: "حضور", cell: cell("attendance", ATT_OPTS), enableSorting: false },
  ];
  return (
    <div className="card card--flush">
      <div className="toolbar" role="search">
        <div className="search"><TextField label="جستجو" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="نام، شمارهٔ پرسنلی یا تیکت" type="search" /></div>
        <SelectField label="انگیزه‌نامه" value={motivation} onChange={(v) => { setMotivation(v); setPage(1); }} placeholder="همه" options={TRI_OPTS} />
      </div>
      {sel.size > 0 && <div className="bulkbar" role="region" aria-label="عملیات گروهی">
        <strong aria-live="polite">{toFa(sel.size)} ردیف انتخاب شده</strong>
        <Button size="sm" variant="primary" onClick={() => setAsk("yes")}>تأیید انگیزه‌نامه (بله)</Button>
        <Button size="sm" onClick={() => setAsk("no")}>رد انگیزه‌نامه (خیر)</Button>
        <Button size="sm" variant="ghost" onClick={() => setSel(new Set())}>پاک کردن انتخاب</Button>
      </div>}
      <DataTable caption="فهرست ثبت‌نام‌ها" columns={cols} data={list.data?.items} getRowId={(e) => String(e.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={sort} onSort={setSort} page={page} pageSize={25} total={list.data?.total} onPage={setPage}
        empty={{ title: dq || motivation ? "نتیجه‌ای پیدا نشد" : "هنوز ثبت‌نامی وجود ندارد", description: dq || motivation ? "فیلترها را تغییر دهید." : "کاندیداها را به یک دوره اضافه کنید تا اینجا دیده شوند.", action: !(dq || motivation) && runId ? <LinkButton variant="primary" href={`#/runs/${runId}/candidates`}>انتخاب کاندیدا</LinkButton> : undefined }} />
      <ConfirmDialog open={!!ask} title="ثبت گروهی انگیزه‌نامه" confirmLabel={ask === "yes" ? "ثبت «بله» برای همه" : "ثبت «خیر» برای همه"} pending={bulk.isPending} onCancel={() => setAsk(null)} onConfirm={() => ask && applyBulk(ask)}
        consequence={`انگیزه‌نامهٔ ${toFa(sel.size)} نفر روی «${ask ? TRI_FA[ask] : ""}» تنظیم می‌شود و در گزارش ممیزی ثبت می‌شود. بلافاصله می‌توانید با «برگردان» آن را لغو کنید.`} />
      {list.data && <p className="pager muted" style={{ border: 0 }}>{toFa(list.data.total)} ثبت‌نام{canWrite ? " · با تغییر هر فیلد، ذخیره فوری انجام و امکان «برگردان» فراهم می‌شود." : " · نقش شما فقط مشاهده است."}</p>}
    </div>
  );
}

export function EnrollmentsScreen() {
  const route = useRoute(); const run = route.query.get("run");
  return (<>
    <PageHead title="ثبت‌نام‌ها" subtitle="وضعیت انگیزه‌نامه، ثبت‌نام، تقویم و حضور هر کاربر" />
    <EnrollmentsTable key={route.path + route.query.toString()} runId={run ? Number(run) : undefined} initialQ={route.query.get("q") ?? ""} initialMotivation={route.query.get("motivation") ?? ""} />
  </>);
}
