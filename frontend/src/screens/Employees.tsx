import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useApi } from "../app-context";
import type { Employee } from "../api/types";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/Field";
import { Dialog } from "../components/Dialog";
import { MaskedPII } from "../components/domain";
import { Button, Chip, Ident, PageHead } from "../components/ui";
import { useDebounced } from "../lib/hooks";
import { toFa } from "../lib/digits";

export function EmployeesScreen() {
  const api = useApi();
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [sort, setSort] = useState("emp_no"); const [page, setPage] = useState(1); const [open, setOpen] = useState<Employee | null>(null);
  const dq = useDebounced(q);
  const list = useQuery({ queryKey: ["employees", dq, status, sort, page], queryFn: () => api.employees({ q: dq, status, sort, page, page_size: 100 }), placeholderData: (p) => p });
  const cols: ColumnDef<Employee, any>[] = [
    { id: "name_fa", header: "نام", cell: ({ row }) => <span><strong>{row.original.name_fa}</strong><br /><span className="muted ltr">{row.original.name_en}</span></span> },
    { id: "emp_no", header: "شمارهٔ پرسنلی", cell: ({ row }) => <Ident>{row.original.emp_no}</Ident> },
    { id: "division", header: "واحد", cell: ({ row }) => row.original.division },
    { id: "national_code", header: "کد ملی", enableSorting: false, cell: ({ row }) => <Ident>{row.original.national_code}</Ident> },
    { id: "mobile", header: "موبایل", enableSorting: false, cell: ({ row }) => <Ident>{row.original.mobile}</Ident> },
    { id: "status", header: "وضعیت", cell: ({ row }) => <Chip tone={row.original.status === "active" ? "ok" : "warn"}>{row.original.status === "active" ? "فعال" : "غیرفعال"}</Chip> },
    { id: "actions", header: () => <span className="sr-only">عملیات</span>, cell: ({ row }) => <Button size="sm" onClick={() => setOpen(row.original)} aria-label={`جزئیات ${row.original.name_fa}`}>جزئیات</Button> },
  ];
  return (<>
    <PageHead title="کارمندان" subtitle="آینهٔ فقط‌خواندنی از IFS. کد ملی و موبایل به‌صورت پیش‌فرض پنهان است." />
    <div className="card card--flush">
      <div className="toolbar" role="search">
        <div className="search"><TextField label="جستجو" type="search" value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="نام، شمارهٔ پرسنلی، واحد یا ایمیل" /></div>
        <SelectField label="وضعیت" value={status} onChange={setStatus} placeholder="همه" options={[{ value: "active", label: "فعال" }, { value: "inactive", label: "غیرفعال" }]} />
      </div>
      <DataTable caption="فهرست کارمندان" columns={cols} data={list.data?.items} getRowId={(e) => e.emp_no} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={sort} onSort={(s) => setSort(s || "emp_no")} virtualize maxHeight={560} page={page} pageSize={100} total={list.data?.total} onPage={setPage}
        empty={{ title: "کارمندی پیدا نشد", description: dq || status ? "جستجو را تغییر دهید." : "ابتدا اتصال IFS را تنظیم و همگام‌سازی کنید.", action: dq || status ? <Button onClick={() => { setQ(""); setStatus(""); }}>پاک کردن فیلترها</Button> : <a className="btn btn--primary" href="#/connectors">رفتن به اتصال‌ها</a> }} />
      {list.data && <p className="pager" style={{ border: 0 }}>{toFa(list.data.total)} کارمند</p>}
    </div>
    <Dialog open={!!open} onClose={() => setOpen(null)} title={open?.name_fa ?? ""} footer={<Button onClick={() => setOpen(null)}>بستن</Button>}>
      {open && <><dl className="kv"><dt>شمارهٔ پرسنلی</dt><dd><Ident>{open.emp_no}</Ident></dd><dt>واحد</dt><dd>{open.division}</dd><dt>مرکز هزینه</dt><dd><Ident>{open.cost_center}</Ident></dd><dt>ایمیل</dt><dd><Ident>{open.email}</Ident></dd></dl><hr className="divider" /><MaskedPII emp={open} /></>}
    </Dialog>
  </>);
}
