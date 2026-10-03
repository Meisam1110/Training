import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { Connector, ConnectorKind, SyncRun, TestResult } from "../api/types";
import { DataTable } from "../components/DataTable";
import { SelectField, Switch, TextField } from "../components/Field";
import { SecretField } from "../components/domain";
import { ConfirmDialog } from "../components/Dialog";
import { useToast } from "../components/Toast";
import { Button, Callout, Chip, ErrorState, PageHead, Skeleton } from "../components/ui";
import { CONNECTOR_FA } from "../lib/labels";
import { fmtJalaliDateTime } from "../lib/jalali";
import { useDraft } from "../lib/draft";
import { focusFirstInvalid } from "../lib/hooks";
import { errMsg, fieldErrors } from "../lib/query";
import { toFa } from "../lib/digits";

interface FieldDef { key: string; label: string; numeric?: boolean; ltr?: boolean; secret?: boolean }
const AUTH_OPTS = [{ value: "oauth2_client_credentials", label: "OAuth2 (client credentials)" }, { value: "basic", label: "Basic" }, { value: "session_login", label: "ورود با نشست (session)" }];

export function fieldsFor(kind: ConnectorKind, authMode: string): FieldDef[] {
  switch (kind) {
    case "excel": return [{ key: "path", label: "مسیر فایل اکسل (مسیر شبکه یا SharePoint همگام‌شده)", ltr: true }, { key: "watch_dir", label: "پوشهٔ پایش خودکار", ltr: true }];
    case "ifs": return [{ key: "base_url", label: "نشانی پایهٔ IFS", ltr: true },
      ...(authMode === "oauth2_client_credentials" ? [{ key: "token_url", label: "نشانی توکن", ltr: true }, { key: "client_id", label: "شناسهٔ کلاینت", ltr: true }, { key: "client_secret", label: "رمز کلاینت", secret: true }]
        : authMode === "basic" ? [{ key: "username", label: "نام کاربری", ltr: true }, { key: "password", label: "گذرواژه", secret: true }]
        : [{ key: "login_url", label: "نشانی ورود", ltr: true }, { key: "username", label: "نام کاربری", ltr: true }, { key: "password", label: "گذرواژه", secret: true }])];
    case "smtp": return [{ key: "host", label: "میزبان SMTP", ltr: true }, { key: "port", label: "درگاه", numeric: true }, { key: "username", label: "نام کاربری", ltr: true }, { key: "from_addr", label: "نشانی فرستنده", ltr: true }, { key: "password", label: "گذرواژه", secret: true }];
    case "graph": return [{ key: "tenant_id", label: "شناسهٔ Tenant", ltr: true }, { key: "client_id", label: "شناسهٔ کلاینت", ltr: true }, { key: "sender", label: "صندوق فرستنده", ltr: true }, { key: "client_secret", label: "رمز کلاینت", secret: true }];
  }
}

export function ConnectorCard({ c, canEdit, canRun }: { c: Connector; canEdit: boolean; canRun: boolean }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast();
  // config (never secrets) survives a session expiry / reload until it is saved
  const [draft, setDraft, clearDraft] = useDraft<{ cfg: Record<string, string | number | boolean>; enabled: boolean }>(`connector:${c.kind}`, { cfg: { ...c.config }, enabled: c.enabled });
  const cfg = draft.cfg; const enabled = draft.enabled;
  const setCfg = (x: Record<string, string | number | boolean>) => setDraft((d) => ({ ...d, cfg: x }));
  const setEnabled = (v: boolean) => setDraft((d) => ({ ...d, enabled: v }));
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [test, setTest] = useState<TestResult | null>(null);
  const [confirmSync, setConfirmSync] = useState(false);
  const authMode = String(cfg.auth_mode ?? "oauth2_client_credentials");
  const fields = fieldsFor(c.kind, authMode);

  const save = useMutation({
    mutationFn: () => {
      const s = Object.fromEntries(Object.entries(secrets).filter(([, v]) => v !== "")); // only changed secrets are sent
      return api.updateConnector(c.kind, { enabled, config: cfg, secrets: s });
    },
    onSuccess: () => { setSecrets({}); setErrs({}); setTest(null); clearDraft(); toast.push({ message: "تنظیمات ذخیره شد." }); void qc.invalidateQueries({ queryKey: ["connectors"] }); },
    onError: (e) => { setErrs(fieldErrors(e)); focusFirstInvalid(); toast.push({ kind: "error", message: `${errMsg(e)} ورودی‌های شما حفظ شد.` }); },
  });
  const testM = useMutation({
    mutationFn: () => api.testConnector(c.kind),
    onSuccess: (r) => { setTest(r); void qc.invalidateQueries({ queryKey: ["connectors"] }); },
    onError: (e) => setTest({ ok: false, message: errMsg(e) }),
  });
  const sync = useMutation({
    mutationFn: () => api.runSync(c.kind as "excel" | "ifs"),
    onSuccess: (r) => { setConfirmSync(false); toast.push({ kind: r.status === "failed" ? "error" : "info", message: r.status === "failed" ? `همگام‌سازی ناموفق: ${r.message}` : `همگام‌سازی انجام شد: ${toFa(r.created)} جدید، ${toFa(r.updated)} به‌روز.` }); void qc.invalidateQueries({ queryKey: ["sync-runs"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); },
    onError: (e) => { setConfirmSync(false); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const last = test ?? c.last_test;
  return (
    <section className="card stack" aria-labelledby={`c-${c.kind}`}>
      <div className="row row--between">
        <h2 id={`c-${c.kind}`} style={{ fontSize: "var(--fs-4)" }}>{CONNECTOR_FA[c.kind]}</h2>
        <Chip tone={enabled ? "ok" : "neutral"}>{enabled ? "فعال" : "غیرفعال"}</Chip>
      </div>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} aria-label={`تنظیمات ${CONNECTOR_FA[c.kind]}`}>
        <Switch label="فعال" checked={enabled} onChange={setEnabled} disabled={!canEdit} />
        {c.kind === "ifs" && <SelectField label="روش احراز هویت" value={authMode} onChange={(v) => setCfg({ ...cfg, auth_mode: v })} options={AUTH_OPTS} disabled={!canEdit} />}
        <div className="grid grid--form">
          {fields.map((f) => f.secret
            ? <SecretField key={f.key} label={f.label} state={c.secrets[f.key] ?? "not_set"} value={secrets[f.key] ?? ""} onChange={(v) => setSecrets({ ...secrets, [f.key]: v })} />
            : <TextField key={f.key} label={f.label} numeric={f.numeric} dir={f.ltr ? "ltr" : undefined} value={String(cfg[f.key] ?? "")} disabled={!canEdit}
              onChange={(v) => setCfg({ ...cfg, [f.key]: f.numeric && v !== "" ? Number(v) || 0 : v })} error={errs[f.key]} />)}
        </div>
        {c.kind === "smtp" && <Switch label="رمزنگاری STARTTLS" checked={Boolean(cfg.starttls)} onChange={(v) => setCfg({ ...cfg, starttls: v })} disabled={!canEdit} />}
        <div className="row">
          {canEdit && <Button type="submit" variant="primary" pending={save.isPending}>ذخیرهٔ تنظیمات</Button>}
          {canEdit && <Button icon="plug" pending={testM.isPending} onClick={() => testM.mutate()}>آزمون اتصال</Button>}
          {canRun && (c.kind === "excel" || c.kind === "ifs") && <Button icon="refresh" onClick={() => setConfirmSync(true)}>اجرای همگام‌سازی…</Button>}
        </div>
        {!canEdit && <p className="muted">ویرایش تنظیمات فقط برای مدیر سامانه است.</p>}
      </form>
      <div aria-live="polite">
        {testM.isPending ? <Skeleton h={44} /> : last && <Callout tone={last.ok ? "ok" : "danger"}><strong>{last.ok ? "اتصال موفق" : "اتصال ناموفق"}</strong>: {last.message}{"at" in last && <span className="muted"> · {fmtJalaliDateTime((last as { at: string }).at)}</span>}</Callout>}
      </div>
      <ConfirmDialog open={confirmSync} title={`همگام‌سازی ${CONNECTOR_FA[c.kind]}`} confirmLabel="اجرای همگام‌سازی" pending={sync.isPending} onCancel={() => setConfirmSync(false)} onConfirm={() => sync.mutate()}
        consequence={c.kind === "ifs" ? "اطلاعات کارمندان از IFS خوانده و در سامانه به‌روزرسانی می‌شود. (IFS تغییر نمی‌کند.)" : "فایل اکسل خوانده و ردیف‌های جدید یا تغییرکرده وارد سامانه می‌شود. فایل مبدأ هرگز تغییر نمی‌کند."} />
    </section>
  );
}

export function SyncHistory() {
  const api = useApi();
  const q = useQuery({ queryKey: ["sync-runs"], queryFn: () => api.syncRuns({ page_size: 20 }) });
  const cols: ColumnDef<SyncRun, any>[] = [
    { id: "kind", header: "منبع", cell: ({ row }) => (row.original.kind === "excel" ? "اکسل" : "IFS") },
    { id: "started_at", header: "شروع", cell: ({ row }) => <span className="num">{fmtJalaliDateTime(row.original.started_at)}</span> },
    { id: "status", header: "نتیجه", cell: ({ row }) => <Chip tone={row.original.status === "ok" ? "ok" : row.original.status === "failed" ? "danger" : "info"}>{row.original.status === "ok" ? "موفق" : row.original.status === "failed" ? "ناموفق" : "در حال اجرا"}</Chip> },
    { id: "counts", header: "جدید / به‌روز / خطا", cell: ({ row }) => <span className="num">{toFa(row.original.created)} / {toFa(row.original.updated)} / {toFa(row.original.errors)}</span> },
    { id: "message", header: "پیام", cell: ({ row }) => row.original.message },
  ];
  return <DataTable caption="تاریخچهٔ همگام‌سازی" columns={cols} data={q.data?.items} getRowId={(r) => String(r.id)} loading={q.isLoading} error={q.error} onRetry={() => q.refetch()} empty={{ title: "هنوز همگام‌سازی انجام نشده", description: "پس از تنظیم اتصال، «اجرای همگام‌سازی» را بزنید." }} />;
}

export function ConnectorsScreen() {
  const api = useApi(); const { isAdmin, canWrite } = useAuth();
  const q = useQuery({ queryKey: ["connectors"], queryFn: () => api.connectors() });
  return (<>
    <PageHead title="اتصال‌ها" subtitle="منابع داده و سرویس‌های ایمیل. رمزها فقط نوشتنی‌اند و هرگز نمایش داده نمی‌شوند." />
    {q.error ? <div className="card"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>
      : q.isLoading ? <div className="grid grid--2"><div className="card conn-skel"><Skeleton h={220} /></div><div className="card conn-skel"><Skeleton h={220} /></div></div>
      : <div className="grid grid--2" style={{ alignItems: "start" }}>{q.data!.map((c) => <ConnectorCard key={c.kind} c={c} canEdit={isAdmin} canRun={canWrite} />)}</div>}
    <section className="card card--flush" style={{ marginBlockStart: "var(--space-5)" }}>
      <div className="card__head" style={{ padding: "var(--space-4) var(--space-4) 0" }}><h2 style={{ fontSize: "var(--fs-4)" }}>تاریخچهٔ همگام‌سازی</h2></div>
      <SyncHistory />
    </section>
  </>);
}
