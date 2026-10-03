import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, useAuth } from "../app-context";
import type { AutomationSettings } from "../api/types";
import { SwitchRow } from "./_shared";
import { TextField } from "../components/Field";
import { ConfirmDialog } from "../components/Dialog";
import { useToast } from "../components/Toast";
import { Button, Chip, EmptyState, ErrorState, PageHead, Skeleton } from "../components/ui";
import { DUE_FA } from "../lib/labels";
import { fmtJalali, fmtJalaliDateTime } from "../lib/jalali";
import { errMsg, fieldErrors } from "../lib/query";
import { clearDraft, readDraft, writeDraft } from "../lib/draft";
import { focusFirstInvalid } from "../lib/hooks";
import { toFa } from "../lib/digits";
import { Link } from "../lib/router";

export function AutomationScreen() {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast(); const { isAdmin, canWrite } = useAuth();
  const due = useQuery({ queryKey: ["due"], queryFn: () => api.automationDue() });
  const settings = useQuery({ queryKey: ["automation-settings"], queryFn: () => api.automationSettings() });
  const [s, setS] = useState<AutomationSettings | null>(null); const [errs, setErrs] = useState<Record<string, string>>({}); const [ask, setAsk] = useState(false);
  useEffect(() => { if (settings.data) setS(readDraft<AutomationSettings>("automation") ?? settings.data.settings); }, [settings.data]);
  const edit = (patch: Partial<AutomationSettings>) => setS((cur) => { if (!cur) return cur; const n = { ...cur, ...patch }; writeDraft("automation", n); return n; });
  const run = useMutation({
    mutationFn: () => api.runAutomation(),
    onSuccess: (r) => { setAsk(false); toast.push({ message: r.message }); void qc.invalidateQueries({ queryKey: ["due"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); void qc.invalidateQueries({ queryKey: ["automation-settings"] }); },
    onError: (e) => { setAsk(false); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const save = useMutation({
    mutationFn: (b: AutomationSettings) => api.saveAutomationSettings(b),
    onSuccess: () => { setErrs({}); clearDraft("automation"); toast.push({ message: "تنظیمات خودکارسازی ذخیره شد." }); void qc.invalidateQueries({ queryKey: ["automation-settings"] }); },
    onError: (e) => { setErrs(fieldErrors(e)); toast.push({ kind: "error", message: `${errMsg(e)} ورودی‌ها حفظ شد.` }); },
  });
  const submit = () => {
    if (!s) return; const v: Record<string, string> = {};
    if (!(s.level3_after_days >= 1 && s.level3_after_days <= 365)) v.level3_after_days = "تعداد روز باید بین ۱ تا ۳۶۵ باشد.";
    if (!(s.reminder_days >= 0 && s.reminder_days <= 60)) v.reminder_days = "یادآوری باید بین ۰ تا ۶۰ روز باشد.";
    if (!(s.over3_threshold >= 1)) v.over3_threshold = "سقف باید عدد مثبت باشد.";
    setErrs(v); if (!Object.keys(v).length) save.mutate(s); else focusFirstInvalid();
  };
  return (<>
    <PageHead title="خودکارسازی" subtitle="کارهای زمان‌بندی‌شدهٔ روزانه: سررسید سطح ۳، یادآوری مهلت‌ها و هشدارها." actions={canWrite && <Button variant="primary" icon="bolt" onClick={() => setAsk(true)}>اجرای همین حالا…</Button>} />
    <div className="grid grid--2" style={{ alignItems: "start" }}>
      <section className="card" aria-labelledby="due-h2">
        <div className="card__head"><h2 id="due-h2" style={{ fontSize: "var(--fs-4)" }}>موارد سررسیدشده</h2>{due.data && <Chip>{toFa(due.data.length)} مورد</Chip>}</div>
        {due.isLoading ? <Skeleton h={80} /> : due.error ? <ErrorState error={due.error} onRetry={() => due.refetch()} />
          : !due.data?.length ? <EmptyState title="موردی سررسید نشده" description="همه‌چیز طبق برنامه است." />
          : <ul className="dash-list">{due.data.map((d) => <li key={d.id}><span><Chip tone="warn">{DUE_FA[d.kind]}</Chip><br />{d.run_id ? <Link to={`/runs/${d.run_id}`}>{d.title}</Link> : <span>{d.title}</span>}</span>{d.due_date && <span className="muted num">{fmtJalali(d.due_date)}</span>}</li>)}</ul>}
      </section>
      <section className="card stack" aria-labelledby="set-h">
        <h2 id="set-h" style={{ fontSize: "var(--fs-4)" }}>تنظیمات</h2>
        {!s ? <Skeleton h={200} /> : <form className="stack" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
          <SwitchRow label="اجرای روزانهٔ خودکار" checked={s.enabled} onChange={(v) => edit({ enabled: v })} disabled={!isAdmin} />
          <div className="grid grid--form">
            <TextField label="روز پس از پایان تا ارزیابی سطح ۳" numeric value={String(s.level3_after_days)} onChange={(v) => edit({ level3_after_days: Number(v) || 0 })} error={errs.level3_after_days} disabled={!isAdmin} />
            <TextField label="یادآوری چند روز مانده" numeric value={String(s.reminder_days)} onChange={(v) => edit({ reminder_days: Number(v) || 0 })} error={errs.reminder_days} disabled={!isAdmin} />
            <TextField label="سقف موتیویشن تأییدنشده" numeric value={String(s.over3_threshold)} onChange={(v) => edit({ over3_threshold: Number(v) || 0 })} error={errs.over3_threshold} disabled={!isAdmin} />
            <TextField label="پیشوند شمارهٔ نامه" dir="ltr" value={s.letter_number_prefix} onChange={(v) => edit({ letter_number_prefix: v })} error={errs.letter_number_prefix} disabled={!isAdmin} />
            <TextField label="گیرندهٔ نامهٔ تسویه" value={s.settlement_addressee} onChange={(v) => edit({ settlement_addressee: v })} disabled={!isAdmin} />
            <TextField label="امضاکننده" value={s.letter_signer_name} onChange={(v) => edit({ letter_signer_name: v })} disabled={!isAdmin} />
            <TextField label="سمت امضاکننده" value={s.letter_signer_title} onChange={(v) => edit({ letter_signer_title: v })} disabled={!isAdmin} />
            <TextField label="ایمیل امضاکننده" type="email" value={s.letter_signer_email} onChange={(v) => edit({ letter_signer_email: v })} disabled={!isAdmin} />
            <TextField label="تلفن امضاکننده" numeric value={s.letter_signer_phone} onChange={(v) => edit({ letter_signer_phone: v })} disabled={!isAdmin} />
            <TextField label="کد اقتصادی شرکت" numeric hint="در سربرگ نامهٔ مؤسسه" value={s.company_economic_code} onChange={(v) => edit({ company_economic_code: v })} disabled={!isAdmin} />
            <TextField label="شناسهٔ ملی شرکت" numeric value={s.company_national_id} onChange={(v) => edit({ company_national_id: v })} disabled={!isAdmin} />
            <TextField label="کد پستی شرکت" numeric value={s.company_postal_code} onChange={(v) => edit({ company_postal_code: v })} disabled={!isAdmin} />
            <TextField label="نشانی شرکت" value={s.company_address} onChange={(v) => edit({ company_address: v })} disabled={!isAdmin} />
          </div>
          {settings.data?.last_run && <p className="muted">آخرین اجرا: {fmtJalaliDateTime(settings.data.last_run.at)} · {toFa(settings.data.last_run.total)} مورد</p>}
          {isAdmin ? <div><Button type="submit" variant="primary" pending={save.isPending}>ذخیرهٔ تنظیمات</Button></div> : <p className="muted">ویرایش تنظیمات فقط برای مدیر سامانه است.</p>}
        </form>}
      </section>
    </div>
    <ConfirmDialog open={ask} title="اجرای خودکارسازی" confirmLabel="اجرا کن" pending={run.isPending} onCancel={() => setAsk(false)} onConfirm={() => run.mutate()}
      consequence={`همهٔ ${toFa(due.data?.length ?? 0)} مورد سررسیدشده بررسی و ثبت می‌شود و ممکن است ایمیل یادآوری یا هشدار ارسال شود. این کار در گزارش ممیزی ثبت می‌شود.`} />
  </>);
}
