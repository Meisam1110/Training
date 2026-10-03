import { useQuery } from "@tanstack/react-query";
import { useApi } from "../app-context";
import type { DashItem, SyncSummary } from "../api/types";
import { Link } from "../lib/router";
import { fmtJalali, fmtJalaliDateTime } from "../lib/jalali";
import { toFa } from "../lib/digits";
import { DUE_FA } from "../lib/labels";
import { Chip, ErrorState, PageHead, Skeleton, EmptyState, LinkButton, type Tone } from "../components/ui";
import { Icon } from "../components/Icon";

function SyncChip({ label, s }: { label: string; s: SyncSummary }) {
  const tone: Tone = s.status === "ok" ? "ok" : s.status === "failed" ? "danger" : "neutral";
  const txt = s.status === "never" ? "هرگز" : `${s.status === "failed" ? "ناموفق" : "موفق"} · ${fmtJalaliDateTime(s.at)}`;
  return <Chip tone={tone}>همگام‌سازی {label}: {txt}</Chip>;
}

const CARDS: { key: "not_started_courses" | "payment_not_started" | "over3_motivations" | "level3_due"; title: string; hint: string; cta: string; all: string; to: (i: DashItem) => string }[] = [
  { key: "not_started_courses", title: "دوره‌های شروع‌نشده", hint: "برنامه یا کاندیدای این دوره‌ها هنوز کامل نیست.", cta: "ادامهٔ برنامه‌ریزی", all: "/runs?status=planned", to: (i) => `/runs/${i.run_id}` },
  { key: "payment_not_started", title: "پرداخت آغاز نشده", hint: "فاکتور یا نامهٔ تسویه هنوز شروع نشده است.", cta: "ساخت نامهٔ تسویه", all: "/runs?status=completed", to: (i) => `/letters?kind=settlement_letter${i.run_id ? `&run=${i.run_id}` : ""}` },
  { key: "over3_motivations", title: "بیش از ۳ موتیویشن تأییدنشده", hint: "پیگیری با کاندیداها یا مدیران مستقیم لازم است.", cta: "بررسی موتیویشن‌ها", all: "/enrollments?motivation=pending", to: (i) => (i.ticket ? `/enrollments?q=${encodeURIComponent(i.ticket)}` : i.run_id ? `/enrollments?run=${i.run_id}` : `/enrollments?q=${i.emp_no ?? ""}`) },
  { key: "level3_due", title: "سررسید ارزیابی سطح ۳", hint: "۶۰ روز از پایان این دوره‌ها گذشته یا نزدیک است.", cta: "درخواست ارزیابی", all: "/automation", to: (i) => `/letters?kind=level3_request${i.run_id ? `&run=${i.run_id}` : ""}` },
];

export function DashboardScreen() {
  const api = useApi();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.dashboard() });
  const due = useQuery({ queryKey: ["due"], queryFn: () => api.automationDue() });
  return (
    <>
      <PageHead title="داشبورد" subtitle="کارهایی که امروز نیاز به اقدام دارند." actions={
        <div className="row dash-sync">{dash.data ? <><SyncChip label="اکسل" s={dash.data.last_sync.excel} /><SyncChip label="IFS" s={dash.data.last_sync.ifs} /></> : <><Skeleton w={190} h={26} /><Skeleton w={190} h={26} /></>}</div>} />
      {dash.error ? <div className="card"><ErrorState error={dash.error} onRetry={() => dash.refetch()} /></div> : (
        <div className="grid grid--dash">
          {CARDS.map((c) => {
            const items = dash.data?.[c.key] ?? [];
            return (
              <section key={c.key} className="card dash-card" aria-labelledby={`h-${c.key}`}>
                <div className="row row--between"><h2 id={`h-${c.key}`} style={{ fontSize: "var(--fs-4)" }}>{c.title}</h2>
                  {dash.isLoading ? <Skeleton w={40} h={36} /> : <span className="dash-count num" aria-label={`${toFa(dash.data?.counts[c.key] ?? 0)} مورد`}>{toFa(dash.data?.counts[c.key] ?? 0)}</span>}</div>
                <p className="muted">{c.hint}</p>
                <div className="dash-body">{dash.isLoading ? <><Skeleton h={20} /><Skeleton h={20} w="80%" /><Skeleton h={20} w="60%" /></> : items.length === 0
                  ? <p className="row" style={{ color: "var(--ok)", fontWeight: 600 }}><Icon name="check" />موردی برای اقدام نیست.</p>
                  : <ul className="dash-list">{items.slice(0, 4).map((i) => (
                    <li key={i.key}><div><Link to={c.to(i)}>{i.title}</Link><div className="muted" style={{ fontSize: "var(--fs-2)" }}>{i.detail}</div></div>
                      <LinkButton size="sm" href={`#${c.to(i)}`} aria-label={`${c.cta}: ${i.title}`}>{c.cta}</LinkButton></li>))}</ul>}</div>
                {(dash.data?.counts[c.key] ?? 0) > 4 && <LinkButton size="sm" href={`#${c.all}`}>مشاهدهٔ همهٔ {toFa(dash.data?.counts[c.key] ?? 0)} مورد</LinkButton>}
              </section>
            );
          })}
        </div>
      )}
      <section className="card" style={{ marginBlockStart: "var(--space-5)" }} aria-labelledby="due-h">
        <div className="card__head"><h2 id="due-h" style={{ fontSize: "var(--fs-4)" }}>کارهای خودکار سررسیدشده</h2><LinkButton size="sm" href="#/automation" icon="bolt">رفتن به خودکارسازی</LinkButton></div>
        <div className="due-body">{due.isLoading ? <><Skeleton h={20} /><Skeleton h={20} w="80%" /><Skeleton h={20} w="60%" /></> : due.error ? <ErrorState error={due.error} onRetry={() => due.refetch()} /> : !due.data?.length
          ? <EmptyState title="کار سررسیدشده‌ای نیست" description="وقتی مهلتی نزدیک شود اینجا نمایش داده می‌شود." />
          : <><ul className="dash-list">{due.data.slice(0, 6).map((d) => <li key={d.id}><span><Chip tone="warn">{DUE_FA[d.kind]}</Chip> {d.run_id ? <Link to={`/runs/${d.run_id}`}>{d.title}</Link> : <span>{d.title}</span>}</span>{d.due_date && <span className="muted num">{fmtJalali(d.due_date)}</span>}</li>)}</ul>{due.data.length > 6 && <LinkButton size="sm" href="#/automation">مشاهدهٔ همهٔ {toFa(due.data.length)} مورد</LinkButton>}</>}</div>
      </section>
    </>
  );
}
