import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { CourseRun, RunInput, RunStep } from "../api/types";
import { RUN_STATUSES, RUN_STEPS } from "../api/types";
import { advancePatch, deriveStep, stepIndex } from "../lib/runs";
import { DataTable } from "../components/DataTable";
import { DatePicker } from "../components/DatePicker";
import { TextField, SelectField } from "../components/Field";
import { InstituteField } from "../components/InstituteField";
import { Button, Callout, Chip, ErrorState, Ident, LinkButton, PageHead, Skeleton } from "../components/ui";
import { Dialog, ConfirmDialog } from "../components/Dialog";
import { EmailSendDialog, RunStatusChip, Stepper } from "../components/domain";
import { useToast } from "../components/Toast";
import { EnrollmentsTable } from "./Enrollments";
import { useRunRecipients } from "../lib/adapters";
import { addDaysISO, diffDaysISO, fmtJalali, fmtJalaliLong, todayISO } from "../lib/jalali";
import { fmtNum, toFa, parseAmount } from "../lib/digits";
import { useDraft } from "../lib/draft";
import { RUN_STATUS_FA, STEP_FA, TYPE_FA } from "../lib/labels";
import { focusFirstInvalid, useDebounced } from "../lib/hooks";
import { Link, useRoute } from "../lib/router";
import { errMsg, fieldErrors } from "../lib/query";

const STATUS_OPTS = RUN_STATUSES.map((v) => ({ value: v, label: RUN_STATUS_FA[v] }));

export function RunsScreen() {
  const api = useApi(); const { canWrite } = useAuth();
  const route = useRoute(); const [q, setQ] = useState(""); const [status, setStatus] = useState(route.query.get("status") ?? ""); const [type, setType] = useState(""); const [page, setPage] = useState(1); const [sort, setSort] = useState("-start_date");
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q);
  const params = { q: dq, status, type, page, page_size: 15, sort };
  const list = useQuery({ queryKey: ["runs", params], queryFn: () => api.runs(params), placeholderData: (p) => p });
  const cols: ColumnDef<CourseRun, any>[] = [
    { id: "course_name_fa", header: "دوره", enableSorting: false, cell: ({ row }) => <Link to={`/runs/${row.original.id}`}><strong>{row.original.course_name_fa}</strong></Link> },
    { id: "type", header: "نوع", cell: ({ row }) => <Chip plain>{TYPE_FA[row.original.type]}</Chip> },
    { id: "institute", header: "مؤسسه", enableSorting: false, cell: ({ row }) => row.original.institute || "—" },
    { id: "start_date", header: "شروع", cell: ({ row }) => <span className="num">{fmtJalali(row.original.start_date)}</span> },
    { id: "end_date", header: "پایان", cell: ({ row }) => <span className="num">{fmtJalali(row.original.end_date)}</span> },
    { id: "status", header: "وضعیت", cell: ({ row }) => <RunStatusChip status={row.original.status} /> },
    { id: "enrollment_count", header: "ثبت‌نام / تأیید", enableSorting: false, cell: ({ row }) => (row.original.counts_known ? <span className="num">{toFa(row.original.enrollment_count)} / {toFa(row.original.motivation_yes_count)}</span> : <span className="muted" title="تعداد در فهرست دوره‌ها ارائه نمی‌شود">—</span>) },
  ];
  const filtered = !!(dq || status || type);
  return (<>
    <PageHead title="دوره‌های آموزشی" subtitle="هر برگزاری یک دوره است؛ از برنامه‌ریزی تا ارزیابی سطح ۳" actions={canWrite && <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>دورهٔ جدید</Button>} />
    <div className="card card--flush">
      <div className="toolbar" role="search">
        <div className="search"><TextField label="جستجو" type="search" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="نام دوره، مؤسسه یا شمارهٔ MTC" /></div>
        <SelectField label="وضعیت" value={status} onChange={(v) => { setStatus(v); setPage(1); }} placeholder="همه" options={STATUS_OPTS} />
        <SelectField label="نوع" value={type} onChange={(v) => { setType(v); setPage(1); }} placeholder="همه" options={[{ value: "online", label: "آنلاین" }, { value: "in_person", label: "حضوری" }]} />
      </div>
      <DataTable caption="فهرست دوره‌ها" columns={cols} data={list.data?.items} getRowId={(r) => String(r.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={sort} onSort={(s) => setSort(s || "-start_date")} page={page} pageSize={15} total={list.data?.total} onPage={setPage}
        empty={filtered ? { title: "دوره‌ای با این فیلترها نیست", description: "فیلترها را تغییر دهید.", action: <Button onClick={() => { setQ(""); setStatus(""); setType(""); }}>پاک کردن فیلترها</Button> }
          : { title: "هنوز دوره‌ای ثبت نشده", description: "با ساخت نخستین دوره، مراحل برنامه‌ریزی تا ارزیابی را دنبال کنید.", action: canWrite ? <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>دورهٔ جدید</Button> : undefined }} />
    </div>
    <NewRunDialog open={creating} onClose={() => setCreating(false)} />
  </>);
}

function NewRunDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast();
  const courses = useQuery({ queryKey: ["courses"], queryFn: () => api.courses({ page_size: 200 }), enabled: open });
  const [f, setF, clearF] = useDraft("newrun", { course_id: "", institute: "", start_date: "", end_date: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const m = useMutation({
    mutationFn: (b: RunInput) => api.createRun(b),
    onSuccess: (r) => { clearF(); toast.push({ message: "دورهٔ جدید ساخته شد." }); void qc.invalidateQueries({ queryKey: ["runs"] }); onClose(); window.location.hash = `/runs/${r.id}`; },
    onError: (e) => { setErrs(fieldErrors(e)); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const submit = () => {
    const v: Record<string, string> = {};
    if (!f.course_id) v.course_id = "دوره را انتخاب کنید.";
    if (!f.start_date) v.start_date = "تاریخ شروع را وارد کنید.";
    if (!f.end_date) v.end_date = "تاریخ پایان را وارد کنید.";
    else if (f.start_date && f.end_date < f.start_date) v.end_date = "تاریخ پایان نباید قبل از تاریخ شروع باشد.";
    setErrs(v); if (Object.keys(v).length) { focusFirstInvalid(); return; }
    m.mutate({ course_id: Number(f.course_id), institute: f.institute, start_date: f.start_date, end_date: f.end_date });
  };
  return (
    <Dialog open={open} onClose={onClose} title="دورهٔ جدید" locked={m.isPending}
      footer={<><Button variant="primary" pending={m.isPending} onClick={submit}>ساخت دوره</Button><Button onClick={onClose} disabled={m.isPending}>انصراف</Button></>}>
      <SelectField label="دوره" required value={f.course_id} onChange={(v) => setF({ ...f, course_id: v })} error={errs.course_id} placeholder="انتخاب کنید…" options={(courses.data?.items ?? []).map((c) => ({ value: String(c.id), label: c.name_fa }))} />
      <InstituteField value={f.institute} onChange={(v) => setF({ ...f, institute: v })} error={errs.institute} />
      <div className="grid grid--form">
        <DatePicker label="تاریخ شروع" required value={f.start_date} onChange={(v) => setF({ ...f, start_date: v })} error={errs.start_date} />
        <DatePicker label="تاریخ پایان" required value={f.end_date} onChange={(v) => setF({ ...f, end_date: v })} error={errs.end_date} />
      </div>
    </Dialog>
  );
}

export function RunDetailScreen({ id }: { id: number }) {
  const api = useApi(); const { canWrite } = useAuth();
  const run = useQuery({ queryKey: ["run", id], queryFn: () => api.run(id) });
  const [sel, setSel] = useState<RunStep | null>(null);
  if (run.isLoading) return <div className="stack"><Skeleton h={36} w="40%" /><Skeleton h={90} /><Skeleton h={200} /></div>;
  if (run.error || !run.data) return <div className="card"><ErrorState error={run.error} onRetry={() => run.refetch()} title="دوره بارگذاری نشد" /></div>;
  const r = run.data; const current = deriveStep(r); const active: RunStep = sel ?? current ?? "level3";
  return (<>
    <PageHead title={r.course_name_fa} subtitle={`${r.institute || "مؤسسه مشخص نشده"} · ${TYPE_FA[r.type]} · ${fmtJalaliLong(r.start_date)} تا ${fmtJalaliLong(r.end_date)}`}
      actions={<><RunStatusChip status={r.status} /><LinkButton href="#/runs">همهٔ دوره‌ها</LinkButton></>} />
    <div className="stack stack--lg">
      {r.status === "cancelled" && <Callout tone="warn">این دوره لغو شده است.</Callout>}
      <Stepper current={current} selected={active} onSelect={setSel} />
      <StepPanel key={r.id} run={r} step={active} canWrite={canWrite} />
      <section aria-labelledby="enr-h"><h2 id="enr-h" style={{ fontSize: "var(--fs-4)", marginBlockEnd: "var(--space-3)" }}>ثبت‌نام‌های این دوره</h2><EnrollmentsTable runId={id} showRun={false} /></section>
    </div>
  </>);
}

const STEP_HELP: Record<RunStep, string> = {
  plan: "اطلاعات پایهٔ برگزاری را کامل کنید؛ این‌ها منبع واحد تاریخ‌ها برای همهٔ نامه‌ها هستند. سپس کاندیداها را انتخاب کنید.",
  candidates: "درخواست‌های IDP مرتبط با این دوره را به برگزاری اضافه کنید. پس از ارسال اطلاعیه، مرحله خودکار پیش می‌رود.",
  announce: "اطلاعیه را بسازید و برای کاندیداها ایمیل کنید (ابتدا آزمایشی). پس از ارسال موفق، مرحله خودکار پیش می‌رود.",
  motivations: "انگیزه‌نامه‌ها را پیگیری کنید. وقتی همهٔ پاسخ‌ها (بله/خیر) ثبت شد، این مرحله خودکار تمام می‌شود.",
  institute_letter: "نامهٔ رسمی به مؤسسه را بسازید و ارسال کنید؛ پس از ارسال، مرحلهٔ فاکتور شروع می‌شود.",
  settlement: "مبلغ و شمارهٔ MTC را ثبت کنید، نامهٔ تسویه را بسازید و ارسال کنید.",
  level3: "۶۰ روز پس از پایان دوره، ارزیابی سطح ۳ را از شرکت‌کنندگان و مدیران بخواهید.",
};

function StepPanel({ run, step, canWrite }: { run: CourseRun; step: RunStep; canWrite: boolean }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast();
  const [f, setF, clearF, restored] = useDraft(`run:${run.id}`, { link: run.link, institute: run.institute, start_date: run.start_date, end_date: run.end_date, send_date: run.send_date ?? "", deadline: run.deadline ?? "", amount: run.amount ? String(run.amount) : "", section_b: run.section_b ?? "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [mail, setMail] = useState(false); const [advance, setAdvance] = useState(false);
  const letters = useQuery({ queryKey: ["letters"], queryFn: () => api.letters({ page_size: 100 }) });
  const rec = useRunRecipients(run.id, mail);
  const announce = letters.data?.items.find((l) => l.run_id === run.id && l.kind === "course_announcement");
  const save = useMutation({
    mutationFn: (b: RunInput) => api.updateRun(run.id, b),
    onSuccess: () => { setErrs({}); clearF(); toast.push({ message: "تغییرات دوره ذخیره شد." }); void qc.invalidateQueries({ queryKey: ["run", run.id] }); void qc.invalidateQueries({ queryKey: ["runs"] }); setAdvance(false); },
    onError: (e) => { setErrs(fieldErrors(e)); setAdvance(false); focusFirstInvalid(); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const idx = RUN_STEPS.indexOf(step);
  const current = deriveStep(run); const nextPatch = advancePatch(step, run);
  const nextStep = RUN_STEPS[stepIndex(step) + 1];
  const l3 = addDaysISO(run.end_date, 60); const l3days = diffDaysISO(todayISO(), l3);
  const amt = parseAmount(f.amount);
  const savePlan = () => {
    const v: Record<string, string> = {};
    if (f.end_date < f.start_date) v.end_date = `تاریخ پایان (${fmtJalali(f.end_date)}) قبل از تاریخ شروع (${fmtJalali(f.start_date)}) است.`;
    if (f.deadline && f.send_date && f.deadline < f.send_date) v.deadline = `مهلت انگیزه‌نامه (${fmtJalali(f.deadline)}) قبل از تاریخ ارسال اطلاعیه (${fmtJalali(f.send_date)}) است.`;
    if (f.deadline && f.deadline > f.start_date) v.deadline = `مهلت انگیزه‌نامه (${fmtJalali(f.deadline)}) بعد از شروع دوره (${fmtJalali(f.start_date)}) است.`;
    setErrs(v); if (Object.keys(v).length) { focusFirstInvalid(); return; }
    save.mutate({ link: f.link, institute: f.institute, start_date: f.start_date, end_date: f.end_date, send_date: f.send_date || null, deadline: f.deadline || null });
  };
  const saveMoney = () => {
    if (amt.error) { setErrs({ amount: amt.error }); focusFirstInvalid(); return; }
    save.mutate({ amount: amt.value, section_b: f.section_b || null });
  };
  const letterLink = (kind: string, label: string) => <LinkButton variant="primary" icon="mail" href={`#/letters?kind=${kind}&run=${run.id}`}>{label}</LinkButton>;
  const body = {
    plan: <div className="stack">
      <div className="grid grid--form">
        <TextField label="پیوند دوره (Link)" dir="ltr" value={f.link} onChange={(v) => setF({ ...f, link: v })} disabled={!canWrite} error={errs.link} hint="در اطلاعیه درج می‌شود" />
        <InstituteField value={f.institute} onChange={(v) => setF({ ...f, institute: v })} disabled={!canWrite} error={errs.institute} />
        <DatePicker label="شروع" value={f.start_date} onChange={(v) => setF({ ...f, start_date: v })} disabled={!canWrite} error={errs.start_date} />
        <DatePicker label="پایان" value={f.end_date} onChange={(v) => setF({ ...f, end_date: v })} disabled={!canWrite} error={errs.end_date} />
        <DatePicker label="تاریخ ارسال اطلاعیه" value={f.send_date} onChange={(v) => setF({ ...f, send_date: v })} disabled={!canWrite} error={errs.send_date} />
        <DatePicker label="مهلت انگیزه‌نامه" value={f.deadline} onChange={(v) => setF({ ...f, deadline: v })} disabled={!canWrite} error={errs.deadline} />
      </div>
      {restored && <Callout tone="info">ورودی‌های ذخیره‌نشدهٔ قبلی شما بازیابی شد.</Callout>}
      <div className="row">{canWrite && <Button pending={save.isPending} onClick={savePlan}>ذخیرهٔ برنامه</Button>}<LinkButton variant="primary" icon="users" href={`#/runs/${run.id}/candidates`}>برو به انتخاب کاندیدا</LinkButton></div></div>,
    candidates: <div className="stack"><p><strong className="num">{toFa(run.enrollment_count)}</strong> کاندیدا ثبت شده است.</p><div className="row"><LinkButton variant="primary" icon="users" href={`#/runs/${run.id}/candidates`}>{canWrite ? "انتخاب و افزودن کاندیدا" : "مشاهدهٔ کاندیداها"}</LinkButton></div></div>,
    announce: <div className="stack"><p>{announce ? <>اطلاعیه با شمارهٔ <Ident>{announce.number}</Ident> ساخته شده است.</> : "ابتدا اطلاعیهٔ دوره را بسازید، سپس برای کاندیداها ایمیل کنید."}</p>
      <div className="row">{announce ? canWrite && <Button variant="primary" icon="send" onClick={() => setMail(true)}>ارسال ایمیل اطلاعیه…</Button> : letterLink("course_announcement", "ساخت اطلاعیه")}</div>
      {announce && <EmailSendDialog open={mail} onClose={() => setMail(false)} letter={announce} courseName={run.course_name_fa} recipients={rec.data ?? []} />}</div>,
    motivations: <div className="stack"><p><strong className="num">{toFa(run.motivation_yes_count)}</strong> از <span className="num">{toFa(run.enrollment_count)}</span> انگیزه‌نامه تأیید شده است.</p>{run.deadline && <p className="muted">مهلت: {fmtJalaliLong(run.deadline)}</p>}<div className="row"><LinkButton variant="primary" href={`#/enrollments?run=${run.id}`}>بررسی انگیزه‌نامه‌ها</LinkButton></div></div>,
    institute_letter: <div className="stack"><p>نامهٔ رسمی به مؤسسه {run.institute ? <strong>{run.institute}</strong> : "(مؤسسه مشخص نشده)"} همراه فهرست شرکت‌کنندگان.</p><div className="row">{letterLink("institute_letter", "ساخت نامهٔ مؤسسه")}</div></div>,
    settlement: <div className="stack"><p className="muted">مبلغ کل = مبلغ هر نفر × تعداد تأییدشده‌ها.</p><div className="grid grid--form">
      <TextField label="مبلغ کل (ریال)" numeric value={f.amount} onChange={(v) => setF({ ...f, amount: v })} error={errs.amount ?? amt.error} disabled={!canWrite} hint={amt.value !== null ? `${fmtNum(amt.value)} ریال` : "می‌توانید از اکسل کپی کنید؛ جداکننده و «ریال» پذیرفته می‌شود"} />
      <TextField label="شمارهٔ MTC (بخش ب)" dir="ltr" value={f.section_b} onChange={(v) => setF({ ...f, section_b: v })} disabled={!canWrite} /></div>
      <div className="row">{canWrite && <Button pending={save.isPending} onClick={saveMoney}>ذخیرهٔ مبلغ</Button>}{letterLink("settlement_letter", "ساخت نامهٔ تسویه")}</div></div>,
    level3: <div className="stack"><Callout tone={l3days <= 0 ? "warn" : "info"}>سررسید ارزیابی سطح ۳: <strong>{fmtJalaliLong(l3)}</strong> ({l3days > 0 ? `${toFa(l3days)} روز دیگر` : l3days === 0 ? "امروز" : `${toFa(-l3days)} روز گذشته`})</Callout>
      <div className="row">{letterLink("level3_request", "درخواست ارزیابی از شرکت‌کنندگان")}<LinkButton href={`#/letters?kind=level3_manager_check&run=${run.id}`}>تأیید مدیر</LinkButton></div></div>,
  }[step];
  const isCurrent = step === current;
  return (
    <section className="card" aria-labelledby="step-h">
      <div className="card__head"><h2 id="step-h" style={{ fontSize: "var(--fs-4)" }}>مرحلهٔ {toFa(idx + 1)}: {STEP_FA[step]}</h2>
        {canWrite && isCurrent && nextPatch && run.status !== "cancelled" && <Button onClick={() => setAdvance(true)}>{nextStep ? `این مرحله تمام شد؛ برو به «${STEP_FA[nextStep]}»` : "ثبت پایان"}</Button>}</div>
      <p className="muted" style={{ marginBlockEnd: "var(--space-3)" }}>{STEP_HELP[step]}</p>
      {body}
      <ConfirmDialog open={advance} title="رفتن به مرحلهٔ بعد" confirmLabel="تأیید" pending={save.isPending} onCancel={() => setAdvance(false)} onConfirm={() => nextPatch && save.mutate(nextPatch)}
        consequence={nextPatch?.status ? `وضعیت دوره به «${RUN_STATUS_FA[nextPatch.status]}» تغییر می‌کند و در داشبورد و گزارش ممیزی ثبت می‌شود.` : "آغاز فرایند پرداخت ثبت می‌شود و دوره از فهرست «پرداخت آغاز نشده» خارج می‌شود. در گزارش ممیزی ثبت می‌شود."} />
    </section>
  );
}
