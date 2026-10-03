import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi, useAuth } from "../app-context";
import type { Course, CourseInput, CourseRun } from "../api/types";
import { DataTable } from "../components/DataTable";
import { Dialog } from "../components/Dialog";
import { Switch, TextField } from "../components/Field";
import { useToast } from "../components/Toast";
import { Button, Chip, LinkButton, PageHead } from "../components/ui";
import { fmtJalali } from "../lib/jalali";
import { parseNum, toFa } from "../lib/digits";
import { focusFirstInvalid, useDebounced } from "../lib/hooks";
import { useDraft } from "../lib/draft";
import { errMsg, fieldErrors } from "../lib/query";

const EMPTY: CourseInput = { name_fa: "", name_en: "", category: "", duration_h: null, active: true };

/** Course CATALOG: what we can teach. Each course has any number of runs (برگزاری) — dated instances managed under #/runs. */
export function CoursesScreen() {
  const api = useApi(); const { canWrite } = useAuth();
  const [q, setQ] = useState(""); const [sort, setSort] = useState("name_fa"); const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const dq = useDebounced(q);
  const list = useQuery({ queryKey: ["courses", "catalog", dq, sort, page], queryFn: () => api.courses({ q: dq, sort, page, page_size: 50 }), placeholderData: (p) => p });
  const runs = useQuery({ queryKey: ["runs", "by-course"], queryFn: () => api.runs({ page_size: 200, sort: "-start_date" }) });
  const stats = useMemo(() => {
    const m = new Map<number, { n: number; last: CourseRun }>();
    for (const r of runs.data?.items ?? []) { const s = m.get(r.course_id); m.set(r.course_id, { n: (s?.n ?? 0) + 1, last: s && s.last.start_date >= r.start_date ? s.last : r }); }
    return m;
  }, [runs.data]);
  const cols: ColumnDef<Course, any>[] = [
    { id: "name_fa", header: "دوره", cell: ({ row }) => <span><strong>{row.original.name_fa}</strong>{row.original.name_en && row.original.name_en !== row.original.name_fa && <><br /><span className="muted latin">{row.original.name_en}</span></>}</span> },
    { id: "category", header: "دسته", cell: ({ row }) => row.original.category || "—" },
    { id: "duration_h", header: "مدت پیش‌فرض", enableSorting: false, cell: ({ row }) => (row.original.duration_h ? <span className="num">{toFa(row.original.duration_h)} ساعت</span> : "—") },
    { id: "runs", header: "برگزاری‌ها", enableSorting: false, cell: ({ row }) => { const s = stats.get(row.original.id); return runs.isLoading ? "…" : s ? <a className="nowrap" href={`#/runs?course=${row.original.id}`}>{toFa(s.n)} برگزاری</a> : <span className="muted nowrap">هنوز برگزار نشده</span>; } },
    { id: "last", header: "آخرین شروع", enableSorting: false, cell: ({ row }) => { const s = stats.get(row.original.id); return s ? <span className="num">{fmtJalali(s.last.start_date)}</span> : "—"; } },
    { id: "active", header: "وضعیت", enableSorting: false, cell: ({ row }) => <Chip tone={row.original.active ? "ok" : "neutral"}>{row.original.active ? "فعال" : "غیرفعال"}</Chip> },
    { id: "actions", header: () => <span className="sr-only">عملیات</span>, cell: ({ row }) => <div className="cell-actions">
        {canWrite && <LinkButton size="sm" variant="primary" href={`#/runs?new=1&course=${row.original.id}`} aria-label={`برگزاری جدید برای ${row.original.name_fa}`}>برگزاری جدید</LinkButton>}
        {canWrite && <Button size="sm" onClick={() => setEditing(row.original)} aria-label={`ویرایش ${row.original.name_fa}`}>ویرایش</Button>}</div> },
  ];
  return (<>
    <PageHead title="کاتالوگ دوره‌ها" subtitle="دوره یعنی «چه چیزی آموزش می‌دهیم»؛ هر دوره می‌تواند چند برگزاری با تاریخ و مؤسسهٔ مشخص داشته باشد." actions={<>
      <LinkButton href="#/runs">همهٔ برگزاری‌ها</LinkButton>{canWrite && <Button variant="primary" icon="plus" onClick={() => setEditing("new")}>دورهٔ جدید</Button>}</>} />
    <div className="card card--flush">
      <div className="toolbar" role="search"><div className="search"><TextField label="جستجو" type="search" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="نام فارسی/انگلیسی یا دسته" /></div></div>
      <DataTable caption="کاتالوگ دوره‌ها" columns={cols} data={list.data?.items} getRowId={(c) => String(c.id)} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={sort} onSort={(s) => setSort(s || "name_fa")} page={page} pageSize={50} total={list.data?.total} onPage={setPage}
        empty={dq ? { title: "دوره‌ای با این عبارت نیست", description: "عبارت دیگری را امتحان کنید.", action: <Button onClick={() => setQ("")}>پاک کردن جستجو</Button> }
          : { title: "هنوز دوره‌ای در کاتالوگ نیست", description: "ابتدا دوره را تعریف کنید، سپس برای آن برگزاری بسازید.", action: canWrite ? <Button variant="primary" icon="plus" onClick={() => setEditing("new")}>دورهٔ جدید</Button> : undefined }} />
      {list.data && <p className="pager" style={{ border: 0 }}>{toFa(list.data.total)} دوره در کاتالوگ</p>}
    </div>
    {editing && <CourseDialog key={editing === "new" ? "new" : editing.id} course={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
  </>);
}

function CourseDialog({ course, onClose }: { course: Course | null; onClose: () => void }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast();
  const [f, setF, clearF] = useDraft<CourseInput>(course ? `course:${course.id}` : "course:new", course ? { name_fa: course.name_fa, name_en: course.name_en, category: course.category, duration_h: course.duration_h, active: course.active } : EMPTY);
  const [dur, setDur] = useState(f.duration_h === null ? "" : String(f.duration_h));
  const [errs, setErrs] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => (course ? api.updateCourse(course.id, f) : api.createCourse(f)),
    onSuccess: () => { clearF(); toast.push({ message: course ? "دوره به‌روزرسانی شد." : "دورهٔ جدید به کاتالوگ اضافه شد." }); void qc.invalidateQueries({ queryKey: ["courses"] }); onClose(); },
    onError: (e) => { setErrs(fieldErrors(e)); focusFirstInvalid(); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const submit = () => {
    const v: Record<string, string> = {};
    if (!f.name_fa.trim() && !f.name_en.trim()) v.name_fa = "نام فارسی یا انگلیسی دوره را وارد کنید.";
    if (dur.trim() !== "") { const n = parseNum(dur); if (n === null || n <= 0) v.duration_h = "مدت را به ساعت و با عدد وارد کنید؛ مثلاً ۱۶."; }
    setErrs(v); if (Object.keys(v).length) { focusFirstInvalid(); return; }
    save.mutate();
  };
  return (
    <Dialog open onClose={onClose} title={course ? `ویرایش دوره — ${course.name_fa}` : "دورهٔ جدید"} locked={save.isPending}
      footer={<><Button variant="primary" pending={save.isPending} onClick={submit}>{course ? "ذخیره" : "افزودن به کاتالوگ"}</Button><Button onClick={onClose} disabled={save.isPending}>انصراف</Button></>}>
      <TextField label="نام فارسی" required value={f.name_fa} onChange={(v) => setF({ ...f, name_fa: v })} error={errs.name_fa} />
      <TextField label="نام انگلیسی / اصلی" dir="ltr" value={f.name_en} onChange={(v) => setF({ ...f, name_en: v })} error={errs.name_en} hint="در نامه‌های انگلیسی استفاده می‌شود" />
      <div className="grid grid--form">
        <TextField label="دسته" value={f.category} onChange={(v) => setF({ ...f, category: v })} error={errs.category} hint="مثلاً مهارت نرم، فنی" />
        <TextField label="مدت پیش‌فرض (ساعت)" numeric value={dur} onChange={(v) => { setDur(v); setF({ ...f, duration_h: parseNum(v) }); }} error={errs.duration_h} />
      </div>
      <Switch label="فعال (قابل انتخاب برای برگزاری جدید)" checked={f.active} onChange={(v) => setF({ ...f, active: v })} />
    </Dialog>
  );
}
