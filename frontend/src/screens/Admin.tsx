import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi } from "../app-context";
import type { AuditEntry, NewUser, Role, User, UserPatch } from "../api/types";
import { ApiError } from "../api/client";
import { useDraft } from "../lib/draft";
import { DataTable } from "../components/DataTable";
import { DatePicker } from "../components/DatePicker";
import { ConfirmDialog, Dialog } from "../components/Dialog";
import { SelectField, TextField } from "../components/Field";
import { useToast } from "../components/Toast";
import { Button, Callout, Chip, Ident, PageHead } from "../components/ui";
import { ROLE_FA } from "../lib/labels";
import { fmtJalaliDateTime } from "../lib/jalali";
import { errMsg, fieldErrors } from "../lib/query";
import { focusFirstInvalid, useDebounced } from "../lib/hooks";

const ROLE_OPTS = (["admin", "hr", "viewer"] as Role[]).map((r) => ({ value: r, label: ROLE_FA[r] }));

function Users() {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast();
  const [open, setOpen] = useState(false);
  const [f, setF, clearF] = useDraft<Omit<NewUser, "password">>("admin:newuser", { username: "", full_name: "", role: "viewer" }); const [password, setPassword] = useState(""); const [errs, setErrs] = useState<Record<string, string>>({});
  const [deact, setDeact] = useState<User | null>(null); const [reset, setReset] = useState<User | null>(null); const [newPw, setNewPw] = useState(""); const [pwErr, setPwErr] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["users"], queryFn: () => api.users({ page_size: 100 }) });
  const create = useMutation({
    mutationFn: () => api.createUser({ ...f, password }),
    onSuccess: () => { toast.push({ message: "کاربر ساخته شد." }); clearF(); setPassword(""); setOpen(false); setF({ username: "", full_name: "", role: "viewer" }); void qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => { setErrs(fieldErrors(e)); focusFirstInvalid(); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: UserPatch }) => api.updateUser(id, body),
    onSuccess: (_u, { body }) => { toast.push({ message: body.password ? "گذرواژه تغییر کرد؛ نشست‌های این کاربر بسته شد." : "کاربر به‌روزرسانی شد." }); setDeact(null); setReset(null); setNewPw(""); void qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => { setDeact(null); if (e instanceof ApiError && e.code === "validation") setPwErr(e.fields.password ?? e.message); else { setReset(null); } toast.push({ kind: "error", message: e instanceof ApiError && e.status === 409 ? `${e.message} (حداقل یک مدیر فعال باید بماند.)` : errMsg(e) }); void qc.invalidateQueries({ queryKey: ["users"] }); },
  });
  const submit = () => {
    const v: Record<string, string> = {};
    if (f.username.trim().length < 3) v.username = "نام کاربری دست‌کم ۳ نویسه (حروف انگلیسی، عدد، نقطه یا خط‌تیره) باشد.";
    else if (!/^[A-Za-z0-9_.@-]+$/.test(f.username.trim())) v.username = "نام کاربری فقط حروف انگلیسی، عدد و . _ - @ داشته باشد.";
    if (!f.full_name.trim()) v.full_name = "نام کامل را وارد کنید.";
    if (password.length < 8) v.password = "گذرواژه باید دست‌کم ۸ نویسه باشد.";
    setErrs(v); if (Object.keys(v).length) { focusFirstInvalid(); return; }
    create.mutate();
  };
  const submitReset = () => { if (newPw.length < 8) { setPwErr("گذرواژه باید دست‌کم ۸ نویسه باشد."); focusFirstInvalid(); return; } setPwErr(null); patch.mutate({ id: reset!.id, body: { password: newPw } }); };
  const cols: ColumnDef<User, any>[] = [
    { id: "username", header: "نام کاربری", cell: ({ row }) => <Ident>{row.original.username}</Ident> },
    { id: "full_name", header: "نام", cell: ({ row }) => row.original.full_name },
    { id: "role", header: "نقش", cell: ({ row }) => <select className="select" style={{ minInlineSize: 130 }} aria-label={`نقش ${row.original.username}`} value={row.original.role} disabled={patch.isPending}
        onChange={(e) => patch.mutate({ id: row.original.id, body: { role: e.target.value as Role } })}>{ROLE_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select> },
    { id: "active", header: "وضعیت", cell: ({ row }) => <Chip tone={row.original.active ? "ok" : "warn"}>{row.original.active ? "فعال" : "غیرفعال"}</Chip> },
    { id: "last_login", header: "آخرین ورود", cell: ({ row }) => <span className="num">{fmtJalaliDateTime(row.original.last_login) || "—"}</span> },
    { id: "actions", header: () => <span className="sr-only">عملیات</span>, cell: ({ row }) => <div className="cell-actions">
        {row.original.active ? <Button size="sm" variant="danger" onClick={() => setDeact(row.original)} aria-label={`غیرفعال کردن ${row.original.username}`}>غیرفعال</Button>
          : <Button size="sm" onClick={() => patch.mutate({ id: row.original.id, body: { is_active: true } })} aria-label={`فعال کردن ${row.original.username}`}>فعال‌سازی</Button>}
        <Button size="sm" onClick={() => { setReset(row.original); setNewPw(""); setPwErr(null); }} aria-label={`بازنشانی گذرواژه ${row.original.username}`}>گذرواژه</Button></div> },
  ];
  return (
    <section className="card card--flush">
      <div className="toolbar"><h2 className="grow" style={{ fontSize: "var(--fs-4)" }}>کاربران</h2><Button variant="primary" icon="plus" onClick={() => setOpen(true)}>کاربر جدید</Button></div>
      <DataTable caption="کاربران" columns={cols} data={list.data?.items} getRowId={(u) => String(u.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        empty={{ title: "کاربری وجود ندارد", action: <Button variant="primary" onClick={() => setOpen(true)}>کاربر جدید</Button> }} />
      <Dialog open={open} onClose={() => setOpen(false)} title="کاربر جدید" locked={create.isPending}
        footer={<><Button variant="primary" pending={create.isPending} onClick={submit}>ساخت کاربر</Button><Button onClick={() => setOpen(false)} disabled={create.isPending}>انصراف</Button></>}>
        <TextField label="نام کاربری" dir="ltr" required value={f.username} onChange={(v) => setF({ ...f, username: v })} error={errs.username} />
        <TextField label="نام کامل" required value={f.full_name} onChange={(v) => setF({ ...f, full_name: v })} error={errs.full_name} />
        <SelectField label="نقش" value={f.role} onChange={(v) => setF({ ...f, role: v as Role })} options={ROLE_OPTS} />
        <TextField label="گذرواژهٔ اولیه" type="password" dir="ltr" required value={password} onChange={setPassword} error={errs.password} hint="دست‌کم ۸ نویسه (در پیش‌نویس ذخیره نمی‌شود)" autoComplete="new-password" />
      </Dialog>
      <ConfirmDialog open={!!deact} title="غیرفعال کردن کاربر" confirmLabel="غیرفعال کن" danger pending={patch.isPending} onCancel={() => setDeact(null)} onConfirm={() => deact && patch.mutate({ id: deact.id, body: { is_active: false } })}
        consequence={`«${deact?.username ?? ""}» دیگر نمی‌تواند وارد شود و نشست‌های باز او بسته می‌شود. آخرین مدیر فعال را نمی‌توان غیرفعال کرد.`} />
      <Dialog open={!!reset} onClose={() => setReset(null)} title={`بازنشانی گذرواژه — ${reset?.username ?? ""}`} locked={patch.isPending}
        footer={<><Button variant="primary" pending={patch.isPending} onClick={submitReset}>ثبت گذرواژهٔ جدید</Button><Button onClick={() => setReset(null)} disabled={patch.isPending}>انصراف</Button></>}>
        <Callout tone="warn">پس از تغییر، همهٔ نشست‌های این کاربر بسته می‌شود.</Callout>
        <TextField label="گذرواژهٔ جدید" type="password" dir="ltr" required value={newPw} onChange={setNewPw} error={pwErr} autoComplete="new-password" hint="دست‌کم ۸ نویسه" />
      </Dialog>
    </section>
  );
}

function Audit() {
  const api = useApi();
  const [q, setQ] = useState(""); const [user, setUser] = useState(""); const [action, setAction] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const params = { q: dq, user, action, from, to, page, page_size: 100 };
  const list = useQuery({ queryKey: ["audit", params], queryFn: () => api.audit(params), placeholderData: (p) => p });
  const all = useQuery({ queryKey: ["audit", "facets"], queryFn: () => api.audit({ page_size: 500 }) });
  const uniq = (k: "user" | "action") => Array.from(new Set((all.data?.items ?? []).map((a) => a[k]))).map((v) => ({ value: v, label: v }));
  const cols: ColumnDef<AuditEntry, any>[] = [
    { id: "at", header: "زمان", cell: ({ row }) => <span className="num">{fmtJalaliDateTime(row.original.at)}</span> },
    { id: "user", header: "کاربر", cell: ({ row }) => <Ident>{row.original.user}</Ident> },
    { id: "action", header: "عملیات", cell: ({ row }) => <code>{row.original.action}</code> },
    { id: "entity", header: "موجودیت", cell: ({ row }) => <span>{row.original.entity} <span className="muted ltr">#{row.original.entity_id}</span></span> },
    { id: "ip", header: "IP", cell: ({ row }) => <Ident>{row.original.ip}</Ident> },
    { id: "detail", header: "توضیح", cell: ({ row }) => row.original.detail },
  ];
  const filtered = !!(dq || user || action || from || to);
  return (
    <section className="card card--flush">
      <div className="toolbar" role="search">
        <div className="search"><TextField label="جستجو" type="search" value={q} onChange={setQ} /></div>
        <SelectField label="کاربر" value={user} onChange={setUser} placeholder="همه" options={uniq("user")} />
        <SelectField label="عملیات" value={action} onChange={setAction} placeholder="همه" options={uniq("action")} />
        <DatePicker label="از تاریخ" value={from} onChange={setFrom} hint=" " />
        <DatePicker label="تا تاریخ" value={to} onChange={setTo} hint=" " />
      </div>
      <DataTable caption="گزارش ممیزی" columns={cols} data={list.data?.items} getRowId={(a) => String(a.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()} virtualize maxHeight={520} page={page} pageSize={100} total={list.data?.total} onPage={setPage}
        empty={{ title: "رویدادی پیدا نشد", description: filtered ? "بازهٔ زمانی یا فیلترها را تغییر دهید." : "هنوز رویدادی ثبت نشده است.", action: filtered ? <Button onClick={() => { setQ(""); setUser(""); setAction(""); setFrom(""); setTo(""); }}>پاک کردن فیلترها</Button> : undefined }} />
    </section>
  );
}

export function AdminScreen() {
  const [tab, setTab] = useState<"users" | "audit">("users");
  return (<>
    <PageHead title="مدیریت" subtitle="کاربران، نقش‌ها و گزارش ممیزی (فقط افزودنی و غیرقابل ویرایش)" />
    <div role="tablist" aria-label="بخش‌های مدیریت" className="seg" style={{ marginBlockEnd: "var(--space-4)" }}>
      {(["users", "audit"] as const).map((t) => <button key={t} role="tab" id={`tab-${t}`} aria-selected={tab === t} aria-controls={`panel-${t}`}
        onClick={() => setTab(t)} onKeyDown={(e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { setTab(tab === "users" ? "audit" : "users"); } }}>{t === "users" ? "کاربران" : "گزارش ممیزی"}</button>)}
    </div>
    <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>{tab === "users" ? <Users /> : <Audit />}</div>
  </>);
}
