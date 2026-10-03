import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { Letter, LetterKind, LetterRequest } from "../api/types";
import { LETTER_KINDS } from "../api/types";
import { ApiError } from "../api/client";
import { missingFromMessage } from "../api/wire";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/Field";
import { Button, Callout, Chip, Ident, PageHead, Skeleton } from "../components/ui";
import { EmailSendDialog } from "../components/domain";
import { useToast } from "../components/Toast";
import { useRunRecipients } from "../lib/adapters";
import { fmtJalali, fmtJalaliDateTime } from "../lib/jalali";
import { LETTER_FA } from "../lib/labels";
import { saveBlob, useDebounced } from "../lib/hooks";
import { clearDraft, readDraft, writeDraft } from "../lib/draft";
import { sanitize } from "../lib/sanitize";
import { useRoute } from "../lib/router";
import { errMsg, fieldErrors } from "../lib/query";
import { toFa } from "../lib/digits";

const PER_PERSON: LetterKind[] = ["level3_request", "level3_manager_check", "line_manager_approval"]; // one letter per selected participant / manager batch
const isKind = (k: string | null): k is LetterKind => !!k && (LETTER_KINDS as string[]).includes(k);

export function LettersScreen() {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast(); const { canWrite } = useAuth(); const route = useRoute();
  const qKind = route.query.get("kind"); const qRun = route.query.get("run") ?? "";
  const [kind, setKind] = useState<LetterKind>(isKind(qKind) ? qKind : "course_announcement");
  const [runId, setRunId] = useState(qRun); // never pre-selected: the user (or a link with ?run=) must choose the course
  const [lang, setLang] = useState<"fa" | "en" | "both">("both");
  const [ov, setOv] = useState<Record<string, string>>({});
  const [enrSel, setEnrSel] = useState<number[] | null>(null); // null = untouched (all participants)
  const [touched, setTouched] = useState<Set<string>>(new Set()); const [attempted, setAttempted] = useState(false);
  const [serverErrs, setServerErrs] = useState<Record<string, string>>({});
  const [mailFor, setMailFor] = useState<Letter | null>(null);

  // hash navigation inside the screen (links, Back/Forward) re-syncs the form
  useEffect(() => { if (isKind(qKind)) setKind(qKind); setRunId(qRun); }, [qKind, qRun]);
  const dkey = `letters:${kind}:${runId}`;
  useEffect(() => { setOv(readDraft<Record<string, string>>(dkey) ?? {}); setTouched(new Set()); setAttempted(false); setServerErrs({}); setEnrSel(null); }, [dkey]);
  const setField = (k: string, v: string) => { setOv((o) => { const n = { ...o, [k]: v }; writeDraft(dkey, n); return n; }); setTouched((t) => new Set(t).add(k)); };

  const runs = useQuery({ queryKey: ["runs", "all"], queryFn: () => api.runs({ page_size: 100, sort: "-start_date" }) });
  const courseOf = useMemo(() => new Map((runs.data?.items ?? []).map((r) => [r.id, r.course_name_fa])), [runs.data]);
  const run = runs.data?.items.find((r) => String(r.id) === runId);

  const perPerson = PER_PERSON.includes(kind);
  const enrolls = useQuery({ queryKey: ["run-enrollments-picker", runId], queryFn: () => api.runEnrollments(Number(runId), { page_size: 200 }), enabled: perPerson && !!runId && canWrite });
  const enrIds = perPerson ? (enrSel ?? (enrolls.data?.items ?? []).map((e) => e.id)) : [];
  const req: LetterRequest = useMemo(() => ({ kind, run_id: runId ? Number(runId) : undefined, lang, overrides: ov, enrollment_ids: enrIds }), [kind, runId, lang, ov, enrIds.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const dreq = useDebounced(req, 350);
  const preview = useQuery({ queryKey: ["letter-preview", dreq], queryFn: () => api.previewLetter(dreq), enabled: !!dreq.run_id && canWrite, placeholderData: (p) => p });
  const missing = preview.data?.missing_fields ?? {};
  const missingKeys = Object.keys(missing).filter((k) => !(ov[k] ?? "").trim() && k !== "enrollment_ids");
  const needPeople = perPerson && !!runId && enrIds.length === 0 && !enrolls.isLoading;

  const dl = async (l: Letter) => { try { const { blob, filename } = await api.downloadLetter(l.id); saveBlob(blob, filename || l.file_name); } catch (e) { toast.push({ kind: "error", message: errMsg(e) }); } };
  const create = useMutation({
    mutationFn: () => api.createLetter(req),
    onSuccess: (l) => { clearDraft(dkey); toast.push({ message: `نامهٔ ${l.number} ساخته شد.`, action: { label: "دانلود", onClick: () => void dl(l) } }); void qc.invalidateQueries({ queryKey: ["letters"] }); },
    onError: (e) => { setAttempted(true); setServerErrs({ ...fieldErrors(e), ...(e instanceof ApiError ? missingFromMessage(e.message) : {}) }); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const list = useQuery({ queryKey: ["letters"], queryFn: () => api.letters({ page_size: 50 }) });
  const rec = useRunRecipients(mailFor?.run_id, !!mailFor);

  const shown = Array.from(new Set([...Object.keys(missing), ...Object.keys(ov), ...Object.keys(serverErrs)])).filter((k) => k !== "enrollment_ids");
  const labelOf = (k: string) => /«(.+?)»/.exec(missing[k] ?? serverErrs[k] ?? "")?.[1] ?? k;
  const errFor = (k: string) => ((attempted || touched.has(k)) && !(ov[k] ?? "").trim() ? (serverErrs[k] ?? missing[k]) : undefined);

  const cols: ColumnDef<Letter, any>[] = [
    { id: "number", header: "شماره", cell: ({ row }) => <Ident>{row.original.number}</Ident> },
    { id: "kind", header: "نوع", cell: ({ row }) => LETTER_FA[row.original.kind] },
    { id: "course", header: "دوره", enableSorting: false, cell: ({ row }) => (row.original.run_id ? courseOf.get(row.original.run_id) ?? `دورهٔ ${toFa(row.original.run_id)}` : "—") },
    { id: "state", header: "وضعیت", cell: ({ row }) => <Chip tone={row.original.state === "sent" ? "ok" : "info"}>{row.original.state === "sent" ? "ارسال‌شده" : "ساخته‌شده"}</Chip> },
    { id: "created_at", header: "تاریخ", cell: ({ row }) => <span className="num">{fmtJalaliDateTime(row.original.created_at)}</span> },
    { id: "actions", header: () => <span className="sr-only">عملیات</span>, cell: ({ row }) => <div className="cell-actions"><Button size="sm" icon="download" onClick={() => void dl(row.original)} aria-label={`دانلود ${row.original.number}`}>دانلود docx</Button>{canWrite && <Button size="sm" icon="send" onClick={() => setMailFor(row.original)} aria-label={`ایمیل ${row.original.number}`}>ایمیل</Button>}</div> },
  ];
  const enrProblem = enrIds.length > 0 ? (serverErrs.enrollment_ids ?? missing.enrollment_ids) : undefined; // e.g. "no supervisor for enrollment 4"
  const canCreate = canWrite && !!runId && missingKeys.length === 0 && !needPeople && !enrProblem;
  return (<>
    <PageHead title="مرکز نامه‌ها" subtitle="نوع نامه و دوره را انتخاب کنید؛ پیش‌نمایش با هر تغییر به‌روز می‌شود." />
    <div className="grid grid--2" style={{ alignItems: "start" }}>
      <section className="card stack letters-col" aria-labelledby="lf-h">
        <h2 id="lf-h" style={{ fontSize: "var(--fs-4)" }}>مشخصات نامه</h2>
        <SelectField label="نوع نامه" value={kind} onChange={(v) => setKind(v as LetterKind)} options={LETTER_KINDS.map((k) => ({ value: k, label: LETTER_FA[k] }))} />
        <SelectField label="دوره" value={runId} onChange={setRunId} placeholder="انتخاب دوره…" required options={(runs.data?.items ?? []).map((r) => ({ value: String(r.id), label: `${r.course_name_fa} — ${fmtJalali(r.start_date)}` }))} />
        {kind === "course_announcement" && <SelectField label="زبان" value={lang} onChange={(v) => setLang(v as "fa" | "en" | "both")} options={[{ value: "both", label: "فارسی و انگلیسی" }, { value: "fa", label: "فارسی" }, { value: "en", label: "English" }]} />}
        {missingKeys.length > 0 && <Callout tone="warn"><strong>{toFa(missingKeys.length)} فیلد باید تکمیل شود.</strong> مقدارها را در کادرهای زیر وارد کنید یا اطلاعات دوره را اصلاح کنید.</Callout>}
        {perPerson && !!runId && (
          <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field__label">شرکت‌کنندگان ({toFa(enrIds.length)} از {toFa(enrolls.data?.items.length ?? 0)})</legend>
            {enrolls.isLoading ? <Skeleton h={60} /> : (enrolls.data?.items.length ?? 0) === 0 ? <Callout tone="warn">این دوره شرکت‌کننده‌ای ندارد.</Callout> : <>
              <div className="row"><Button size="sm" onClick={() => setEnrSel((enrolls.data?.items ?? []).map((e) => e.id))}>همه</Button><Button size="sm" onClick={() => setEnrSel([])}>هیچ‌کدام</Button></div>
              <ul className="result-list recips" style={{ maxBlockSize: 220, overflow: "auto" }}>{(enrolls.data?.items ?? []).map((e) => (
                <li key={e.id}><label><input type="checkbox" checked={enrIds.includes(e.id)} aria-label={`شرکت‌کننده ${e.name_fa}`} onChange={() => setEnrSel(enrIds.includes(e.id) ? enrIds.filter((x) => x !== e.id) : [...enrIds, e.id])} /><span>{e.name_fa}</span></label><Ident>{e.ticket}</Ident></li>))}</ul></>}
            {needPeople && (attempted || enrSel !== null) && <span className="field__error" role="alert">حداقل یک شرکت‌کننده انتخاب کنید.</span>}
            {enrProblem && <span className="field__error" role="alert">{enrProblem === "required" ? "انتخاب شرکت‌کنندگان معتبر نیست." : enrProblem}</span>}
          </fieldset>)}
        {shown.map((k) => <TextField key={k} label={labelOf(k)} required={!!missing[k]} value={ov[k] ?? ""} onChange={(v) => setField(k, v)} error={errFor(k)} onBlur={() => setTouched((t) => new Set(t).add(k))} />)}
        <div className="row">
          <Button variant="primary" pending={create.isPending} disabled={!canCreate} onClick={() => { setAttempted(true); if (canCreate) create.mutate(); }}>ساخت نامه و شماره‌گذاری</Button>
          {!canWrite ? <span className="muted">نقش شما فقط مشاهده است.</span> : !runId ? <span className="muted">ابتدا دوره را انتخاب کنید.</span> : needPeople ? <span className="muted">حداقل یک شرکت‌کننده انتخاب کنید.</span> : missingKeys.length > 0 ? <span className="muted">{toFa(missingKeys.length)} فیلد باقی مانده</span> : null}
        </div>
      </section>
      <section className="card stack letters-col" aria-labelledby="pv-h">
        <div className="row row--between"><h2 id="pv-h" style={{ fontSize: "var(--fs-4)" }}>پیش‌نمایش زنده</h2><span className="muted fetch-hint" data-on={preview.isFetching} aria-hidden={!preview.isFetching}>در حال به‌روزرسانی…</span></div>
        <p data-testid="preview-course" style={{ minBlockSize: "1.75rem" }}>{run && <><strong>{run.course_name_fa}</strong> · <span className="muted">{LETTER_FA[kind]} · {fmtJalali(run.start_date)}</span></>}</p>
        <div className="preview-slot">
        {!canWrite ? <Callout tone="info">پیش‌نمایش و ساخت نامه برای نقش «ناظر» در دسترس نیست؛ می‌توانید نامه‌های ساخته‌شده را در فهرست زیر ببینید.</Callout>
          : !runId ? <p className="muted">دوره‌ای انتخاب نشده است.</p>
          : preview.isLoading ? <><Skeleton h={24} /><Skeleton h={120} /></>
          : preview.error ? <Callout tone="danger">{errMsg(preview.error)} <Button size="sm" onClick={() => preview.refetch()}>تلاش دوباره</Button></Callout>
          : preview.data?.html ? <div className="preview" data-testid="letter-preview" dangerouslySetInnerHTML={{ __html: sanitize(preview.data.html) }} />
          : <p className="muted">برای دیدن پیش‌نمایش، فیلدهای ناقص را تکمیل کنید.</p>}
        </div>
      </section>
    </div>
    <section className="card card--flush" style={{ marginBlockStart: "var(--space-5)" }}>
      <div className="card__head" style={{ padding: "var(--space-4) var(--space-4) 0" }}><h2 style={{ fontSize: "var(--fs-4)" }}>نامه‌های ساخته‌شده</h2></div>
      <DataTable caption="نامه‌های ساخته‌شده" columns={cols} data={list.data?.items} getRowId={(l) => String(l.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        empty={{ title: "هنوز نامه‌ای ساخته نشده", description: "یک نوع نامه و دوره انتخاب کنید و «ساخت نامه» را بزنید.", action: undefined }} />
    </section>
    <EmailSendDialog open={!!mailFor} onClose={() => setMailFor(null)} letter={mailFor} courseName={mailFor?.run_id ? courseOf.get(mailFor.run_id) : undefined} recipients={rec.data ?? []} />
  </>);
}
