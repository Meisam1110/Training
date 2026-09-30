import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useApi } from "../app-context";
import { ApiError } from "../api/client";
import type { CourseRun, Employee, EmailSendResult, Letter, Recipient, RunStatus, RunStep, SecretState } from "../api/types";
import { RUN_STEPS } from "../api/types";
import { stepIndex } from "../lib/runs";
import { newKey } from "../lib/hooks";
import { ATT_FA, ATT_TONE, LETTER_FA, RUN_STATUS_FA, RUN_STATUS_TONE, STEP_FA, TRI_FA, TRI_TONE } from "../lib/labels";
import { sanitize } from "../lib/sanitize";
import { fmtJalali } from "../lib/jalali";
import { toFa } from "../lib/digits";
import { Dialog } from "./Dialog";
import { Icon } from "./Icon";
import { Switch } from "./Field";
import { Button, Callout, Chip, Ident, Skeleton } from "./ui";
import { useToast } from "./Toast";
import type { Attendance, Tri } from "../api/types";

export const RunStatusChip = ({ status }: { status: RunStatus }) => <Chip tone={RUN_STATUS_TONE[status]}>{RUN_STATUS_FA[status]}</Chip>;
export const TriChip = ({ v }: { v: Tri }) => <Chip tone={TRI_TONE[v]}>{TRI_FA[v]}</Chip>;
export const AttChip = ({ v }: { v: Attendance }) => <Chip tone={ATT_TONE[v]}>{ATT_FA[v]}</Chip>;

/** Stepper: Plan → Candidates → Announce → Motivations → Institute letter → Invoice/Settlement → Level 3.
 *  Semantics: an ordered list of buttons; the current step carries aria-current="step", the step being viewed is announced
 *  with visually-hidden text (aria-selected is not valid on buttons). Arrow keys move between steps. */
export function Stepper({ current, selected, onSelect }: { current: RunStep | null; selected: RunStep; onSelect: (s: RunStep) => void }) {
  const cur = stepIndex(current);
  const ref = useRef<HTMLOListElement>(null);
  useEffect(() => { ref.current?.querySelector('[aria-current="step"]')?.scrollIntoView({ inline: "center", block: "nearest" }); }, [current]);
  const onKey = (e: React.KeyboardEvent) => {
    const map: Record<string, number> = { ArrowLeft: 1, ArrowRight: -1 }; // RTL: left = next step
    if (!(e.key in map)) return;
    const btns = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>(".step__btn") ?? []);
    const i = btns.indexOf(document.activeElement as HTMLButtonElement); if (i < 0) return;
    e.preventDefault(); btns[Math.min(btns.length - 1, Math.max(0, i + map[e.key]!))]?.focus();
  };
  return (
    <ol className="stepper" aria-label="مراحل دوره" ref={ref} onKeyDown={onKey}>
      {RUN_STEPS.map((s, i) => {
        const state = i < cur ? "done" : i === cur ? "current" : "todo";
        return (
          <li key={s} className="step" data-state={state}>
            <button className="step__btn" data-viewing={selected === s} aria-current={state === "current" ? "step" : undefined} onClick={() => onSelect(s)}>
              <span className="step__num">{state === "done" ? <Icon name="check" /> : toFa(i + 1)}</span>
              <span className="step__label">{STEP_FA[s]}</span>
              <span className="sr-only">{state === "done" ? "انجام شده" : state === "current" ? "مرحلهٔ فعلی" : "در انتظار"}{selected === s ? "، در حال نمایش" : ""}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** Write-only secret: never displays or receives the stored value; only "set / not set". */
export function SecretField({ label, state, value, onChange, hint }: { label: string; state: SecretState; value: string; onChange: (v: string) => void; hint?: string }) {
  const id = useId();
  return (
    <div className="field" data-testid={`secret-${label}`}>
      <div className="row row--between">
        <label className="field__label" htmlFor={id}>{label}</label>
        <span className="secret-state"><Chip tone={state === "set" ? "ok" : "warn"}>{state === "set" ? "تنظیم شده" : "تنظیم نشده"}</Chip></span>
      </div>
      <input id={id} className="input" type="password" dir="ltr" autoComplete="new-password" value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={state === "set" ? "برای تغییر، مقدار جدید را وارد کنید" : "مقدار را وارد کنید"} aria-describedby={`${id}-h`} />
      <span className="field__hint" id={`${id}-h`}>{hint ?? "فقط نوشتنی است؛ مقدار ذخیره‌شده هرگز نمایش داده نمی‌شود. خالی بگذارید تا تغییری نکند."}</span>
    </div>
  );
}

/** Masked personal data with an explicit, audited reveal. */
export function MaskedPII({ emp }: { emp: Employee }) {
  const api = useApi(); const toast = useToast();
  const [ask, setAsk] = useState(false);
  const [full, setFull] = useState<Employee | null>(null);
  const timer = useRef<number>();
  const reveal = useMutation({
    mutationFn: () => api.employee(emp.emp_no, true),
    onSuccess: (e) => { setFull(e); setAsk(false); timer.current = window.setTimeout(() => setFull(null), 30000); },
    onError: (e) => { setAsk(false); toast.push({ kind: "error", message: (e as Error).message }); },
  });
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const show = full ?? emp;
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <dl className="kv">
        <dt>کد ملی</dt><dd data-testid="pii-national"><Ident>{show.national_code}</Ident></dd>
        <dt>موبایل</dt><dd data-testid="pii-mobile"><Ident>{show.mobile}</Ident></dd>
      </dl>
      {full
        ? <Button size="sm" icon="eyeOff" onClick={() => { setFull(null); window.clearTimeout(timer.current); }}>پنهان کردن</Button>
        : <Button size="sm" icon="eye" onClick={() => setAsk(true)}>نمایش اطلاعات (ثبت در گزارش ممیزی)</Button>}
      <Dialog open={ask} onClose={() => setAsk(false)} title="نمایش اطلاعات شخصی" locked={reveal.isPending}
        footer={<><Button variant="primary" pending={reveal.isPending} onClick={() => reveal.mutate()}>می‌فهمم، نمایش بده</Button><Button onClick={() => setAsk(false)} disabled={reveal.isPending}>انصراف</Button></>}>
        <Callout tone="warn"><strong>این کار در گزارش ممیزی ثبت می‌شود.</strong> نام شما، زمان و کارمند مورد نظر ذخیره خواهد شد. فقط در صورت نیاز کاری نمایش دهید؛ مقدار پس از ۳۰ ثانیه دوباره پنهان می‌شود.</Callout>
      </Dialog>
    </div>
  );
}

interface EmailProps { open: boolean; onClose: () => void; letter: Letter | null; courseName?: string; recipients: Recipient[]; title?: string }
type Phase = "compose" | "confirm" | "result";
/**
 * compose (what is sent, to whom, already-sent warnings) → confirm (counts + consequence) → per-recipient result.
 * Dry-run is ON for a letter's first live send and whenever any recipient already received it; people who already got it
 * start unchecked. One idempotency key per unchanged request (kept on retry, renewed when recipients/mode change).
 */
export function EmailSendDialog({ open, onClose, letter, courseName, recipients, title }: EmailProps) {
  const api = useApi();
  const letterId = letter?.id;
  const messages = useQuery({ queryKey: ["messages"], queryFn: () => api.messages({ page_size: 200 }), enabled: open });
  const body = useQuery({ queryKey: ["letter-body", letter?.kind, letter?.run_id], queryFn: () => api.previewLetter({ kind: letter!.kind, run_id: letter!.run_id ?? undefined }), enabled: open && !!letter });
  const sentMap = useMemo(() => {
    const m = new Map<string, string>(); // email -> latest live send date
    for (const msg of messages.data?.items ?? []) if (msg.letter_id === letterId && !msg.dry_run) for (const r of msg.results) if (r.ok && (!m.has(r.email) || m.get(r.email)! < msg.sent_at)) m.set(r.email, msg.sent_at);
    return m;
  }, [messages.data, letterId]);
  const firstSend = messages.isSuccess && !(messages.data?.items ?? []).some((m) => m.letter_id === letterId && !m.dry_run && m.failed_count < m.recipients_count);
  const already = recipients.filter((r) => sentMap.has(r.email.toLowerCase()));
  const [dry, setDry] = useState(true);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<Phase>("compose");
  const [result, setResult] = useState<EmailSendResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = useRef(newKey());
  const inFlight = useRef(false);

  useEffect(() => { if (open) { setPhase("compose"); setResult(null); setErr(null); inFlight.current = false; key.current = newKey(); } }, [open]);
  const recSig = recipients.map((r) => r.email).join("|");
  useEffect(() => { if (open && messages.isSuccess) { setPicked(new Set(recipients.filter((r) => !sentMap.has(r.email.toLowerCase())).map((r) => r.email))); setDry(firstSend || already.length > 0); } // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, messages.isSuccess, recSig, sentMap, firstSend]);
  const chosen = recipients.filter((r) => picked.has(r.email));
  const chosenAlready = chosen.filter((r) => sentMap.has(r.email.toLowerCase()));
  const sig = `${dry}|${chosen.map((r) => r.email).join(",")}`;
  useEffect(() => { if (!inFlight.current) key.current = newKey(); }, [sig]);

  const send = useMutation({
    mutationFn: () => api.sendEmail({ letter_id: letterId, recipients: chosen, dry_run: dry }, key.current),
    onSuccess: (r) => { setResult(r); setPhase("result"); void messages.refetch(); },
    onError: (e) => { setErr(e instanceof ApiError ? e.message : "ارسال انجام نشد."); setPhase("compose"); },
    onSettled: () => { inFlight.current = false; },
  });
  const confirmSend = () => { if (inFlight.current) return; inFlight.current = true; send.mutate(); };
  const n = chosen.length;
  const ok = result?.results.filter((r) => r.status !== "failed").length ?? 0;
  const failed = (result?.results.length ?? 0) - ok;
  const label = letter ? `${LETTER_FA[letter.kind]}${courseName ? ` · ${courseName}` : ""} · ${letter.number}` : "";
  const toggle = (e: string) => setPicked((s) => { const x = new Set(s); if (x.has(e)) x.delete(e); else x.add(e); return x; });

  return (
    <Dialog open={open} onClose={onClose} title={title ?? (letter ? `ارسال ${label}` : "ارسال ایمیل")} locked={send.isPending} wide={phase !== "confirm"}
      footer={phase === "compose" ? <>
        <Button variant="primary" disabled={!n} onClick={() => setPhase("confirm")}>ادامه و بازبینی ({toFa(n)} گیرنده)</Button><Button onClick={onClose}>انصراف</Button></>
        : phase === "confirm" ? <>
          <Button variant={dry ? "primary" : "danger"} pending={send.isPending} onClick={confirmSend}>{dry ? `اجرای آزمایشی برای ${toFa(n)} گیرنده` : `ارسال واقعی به ${toFa(n)} گیرنده`}</Button>
          <Button onClick={() => setPhase("compose")} disabled={send.isPending}>بازگشت</Button></>
          : <Button variant="primary" onClick={onClose}>بستن</Button>}>
      {phase === "compose" && <>
        {err && <Callout tone="danger">{err}</Callout>}
        <dl className="kv" data-testid="mail-summary">
          <dt>نامه</dt><dd>{letter ? <>{LETTER_FA[letter.kind]} · <Ident>{letter.number}</Ident></> : "—"}</dd>
          <dt>دوره</dt><dd>{courseName ?? "—"}</dd>
          <dt>موضوع</dt><dd>{letter?.subject || body.data?.subject || "—"}</dd>
          <dt>پیوست</dt><dd><Ident>{letter?.file_name || "—"}</Ident></dd>
        </dl>
        <details><summary style={{ cursor: "pointer", minBlockSize: 44, display: "flex", alignItems: "center", fontWeight: 600 }}>پیش‌نمایش متن ایمیل</summary>
          <div className="details-body">{body.isLoading ? <Skeleton h={60} /> : body.data?.html ? <div className="preview" dangerouslySetInnerHTML={{ __html: sanitize(body.data.html) }} /> : <p className="muted">پیش‌نمایش در دسترس نیست.</p>}</div></details>
        <div className="callout" style={{ borderColor: dry ? "var(--brand-deep)" : "var(--warn)", borderWidth: 2 }}>
          <Switch testId="dry-run" checked={dry} onChange={setDry} label={<>اجرای آزمایشی (Dry-run) — {dry ? "روشن" : "خاموش"}</>} />
        </div>
        {dry ? <Callout tone="info">در حالت آزمایشی هیچ ایمیلی ارسال نمی‌شود؛ فقط نتیجهٔ هر گیرنده نمایش داده می‌شود.{firstSend ? " این نخستین ارسال این نامه است، پس آزمایشی پیشنهاد می‌شود." : ""}{already.length > 0 ? " برای بعضی گیرندگان این نامه قبلاً ارسال شده است." : ""}</Callout>
          : <Callout tone="warn"><strong>ارسال واقعی:</strong> ایمیل‌ها فوراً به گیرندگان می‌رسد و قابل بازگرداندن نیست.</Callout>}
        {already.length > 0 && <Callout tone="warn" icon="alert"><strong>{toFa(already.length)} نفر قبلاً این نامه را دریافت کرده‌اند</strong> و به‌طور پیش‌فرض انتخاب نشده‌اند.</Callout>}
        <div className="row row--between"><h3 style={{ fontSize: "var(--fs-4)" }}>گیرندگان ({toFa(n)} از {toFa(recipients.length)})</h3>
          <span className="row"><Button size="sm" onClick={() => setPicked(new Set(recipients.map((r) => r.email)))}>همه</Button><Button size="sm" onClick={() => setPicked(new Set())}>هیچ‌کدام</Button></span></div>
        {recipients.length === 0 ? <Callout tone="warn">گیرنده‌ای برای این نامه پیدا نشد (ثبت‌نام‌های این دوره ایمیل ندارند).</Callout>
          : <ul className="result-list recips" style={{ maxBlockSize: 260, overflow: "auto" }}>{recipients.map((r) => { const at = sentMap.get(r.email.toLowerCase()); return (
            <li key={r.email}><label><input type="checkbox" checked={picked.has(r.email)} onChange={() => toggle(r.email)} aria-label={`گیرنده ${r.name ?? r.email}`} /><span>{r.name ?? "—"}</span></label>
              <span className="row"><Ident>{r.email}</Ident>{at && <Chip tone="warn">قبلاً در تاریخ {fmtJalali(at.slice(0, 10))} ارسال شده</Chip>}</span></li>); })}</ul>}
      </>}
      {phase === "confirm" && <>
        <Callout tone={dry ? "info" : "warn"}>
          <strong>{dry ? "اجرای آزمایشی:" : "ارسال واقعی:"}</strong>{" "}
          {dry ? `${toFa(n)} گیرنده برای «${label}» بررسی می‌شود و هیچ ایمیلی ارسال نخواهد شد.` : `«${label}» برای ${toFa(n)} گیرنده ایمیل می‌شود. این کار قابل بازگشت نیست.`}
        </Callout>
        {!dry && chosenAlready.length > 0 && <Callout tone="danger"><strong>هشدار ارسال تکراری:</strong> {toFa(chosenAlready.length)} نفر از انتخاب‌شده‌ها قبلاً همین نامه را دریافت کرده‌اند.</Callout>}
        <dl className="kv"><dt>تعداد گیرندگان</dt><dd data-testid="confirm-count">{toFa(n)}</dd><dt>حالت</dt><dd>{dry ? "آزمایشی" : "ارسال واقعی"}</dd><dt>موضوع</dt><dd>{letter?.subject || "—"}</dd></dl>
        <p className="muted">برای جلوگیری از ارسال دوباره، دکمه پس از کلیک غیرفعال می‌شود و درخواست کلید یکتا دارد.</p>
      </>}
      {phase === "result" && result && <>
        <Callout tone={failed ? "warn" : "ok"}>{result.dry_run ? `اجرای آزمایشی: ${toFa(ok)} گیرنده بررسی شد و چیزی ارسال نشد. ` : `${toFa(ok)} ارسال موفق. `}{toFa(failed)} ناموفق.</Callout>
        <ul className="result-list" data-testid="send-results">
          {result.results.map((r) => <li key={r.email}><Ident>{r.email}</Ident>
            <span className="row"><Chip tone={r.status === "failed" ? "danger" : r.status === "sent" ? "ok" : "info"}>{r.status === "failed" ? "ناموفق" : r.status === "sent" ? "ارسال شد" : "آزمایشی"}</Chip>{r.error && <span className="muted">{r.error}</span>}</span></li>)}
        </ul>
      </>}
    </Dialog>
  );
}

export function runLabel(r: Pick<CourseRun, "course_name_fa" | "start_date">, fmt: (s: string) => string) { return `${r.course_name_fa} — ${fmt(r.start_date)}`; }
