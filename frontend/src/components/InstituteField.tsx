import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, useAuth } from "../app-context";
import type { NewInstitute } from "../api/types";
import { Dialog } from "./Dialog";
import { SelectField, TextField } from "./Field";
import { Button } from "./ui";
import { useToast } from "./Toast";
import { errMsg, fieldErrors } from "../lib/query";
import { focusFirstInvalid } from "../lib/hooks";

const NEW = "__new__";
/** Institute picker backed by GET /institutes, with inline "create new" (POST /institutes, hr+). Value is the institute NAME (what runs store). */
export function InstituteField({ value, onChange, error, disabled, label = "مؤسسهٔ برگزارکننده" }: { value: string; onChange: (name: string) => void; error?: string | null; disabled?: boolean; label?: string }) {
  const api = useApi(); const qc = useQueryClient(); const toast = useToast(); const { canWrite } = useAuth();
  const q = useQuery({ queryKey: ["institutes"], queryFn: () => api.institutes({ page_size: 200 }) });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<NewInstitute>({ name: "", name_fa: "", supplier_code: "", contact_email: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const names = (q.data?.items ?? []).map((i) => i.name);
  const options = [...(q.data?.items ?? []).map((i) => ({ value: i.name, label: i.name_fa && i.name_fa !== i.name ? `${i.name_fa} (${i.name})` : i.name })),
    ...(value && !names.includes(value) ? [{ value, label: value }] : []), ...(canWrite ? [{ value: NEW, label: "＋ مؤسسهٔ جدید…" }] : [])];
  const create = useMutation({
    mutationFn: () => api.createInstitute(f),
    onSuccess: (i) => { void qc.invalidateQueries({ queryKey: ["institutes"] }); onChange(i.name); setOpen(false); setF({ name: "", name_fa: "", supplier_code: "", contact_email: "" }); toast.push({ message: `مؤسسهٔ «${i.name}» ساخته شد.` }); },
    onError: (e) => { setErrs(fieldErrors(e)); toast.push({ kind: "error", message: errMsg(e) }); },
  });
  const submit = () => {
    const v: Record<string, string> = {};
    if (!f.name.trim()) v.name = "نام مؤسسه را وارد کنید.";
    if (f.contact_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.contact_email)) v.contact_email = "نشانی ایمیل معتبر نیست؛ مثلاً info@example.com";
    setErrs(v); if (Object.keys(v).length) { focusFirstInvalid(); return; }
    create.mutate();
  };
  return (<>
    <SelectField label={label} value={value} onChange={(v) => (v === NEW ? setOpen(true) : onChange(v))} placeholder={q.isLoading ? "در حال بارگذاری…" : "— انتخاب مؤسسه —"} options={options} error={error} disabled={disabled} />
    <Dialog open={open} onClose={() => setOpen(false)} title="مؤسسهٔ جدید" locked={create.isPending}
      footer={<><Button variant="primary" pending={create.isPending} onClick={submit}>ساخت مؤسسه</Button><Button onClick={() => setOpen(false)} disabled={create.isPending}>انصراف</Button></>}>
      <TextField label="نام (انگلیسی یا اصلی)" required value={f.name} onChange={(v) => setF({ ...f, name: v })} error={errs.name} />
      <TextField label="نام فارسی" value={f.name_fa} onChange={(v) => setF({ ...f, name_fa: v })} error={errs.name_fa} />
      <div className="grid grid--form">
        <TextField label="کد تأمین‌کننده" dir="ltr" value={f.supplier_code} onChange={(v) => setF({ ...f, supplier_code: v })} error={errs.supplier_code} />
        <TextField label="ایمیل تماس" type="email" value={f.contact_email} onChange={(v) => setF({ ...f, contact_email: v })} error={errs.contact_email} />
      </div>
    </Dialog>
  </>);
}
