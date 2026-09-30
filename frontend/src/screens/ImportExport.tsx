import { useRef, useState, type DragEvent } from "react";
import { useApi, useAuth } from "../app-context";
import { Button, Callout, Ident, PageHead } from "../components/ui";
import { ConfirmDialog } from "../components/Dialog";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";
import type { ImportResult } from "../api/types";
import { saveBlob } from "../lib/hooks";
import { errMsg } from "../lib/query";
import { toFa } from "../lib/digits";

type Kind = "idp" | "legacy";
const csvCell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
/** UTF-8 with BOM so Excel opens Persian text correctly. */
function downloadCsv(r: ImportResult) {
  const rows = [["sheet", "row", "column", "code", "reason"], ...r.errors.map((e) => [e.sheet, e.row ?? "", e.column, e.code, e.reason])];
  saveBlob(new Blob(["\ufeff" + rows.map((x) => x.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }), "import-errors.csv");
}
function Importer({ kind, title, hint }: { kind: Kind; title: string; hint: string }) {
  const api = useApi(); const { canWrite } = useAuth(); const toast = useToast();
  const [over, setOver] = useState(false); const [file, setFile] = useState<File | null>(null); const [pct, setPct] = useState(0);
  const [ask, setAsk] = useState(false); const [busy, setBusy] = useState(false); const [res, setRes] = useState<ImportResult | null>(null); const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const pick = (f: File | undefined) => {
    setRes(null); setErr(null); setPct(0);
    if (!f) return;
    if (!/\.xlsx$/i.test(f.name)) { setFile(null); setErr("فقط فایل xlsx پذیرفته می‌شود."); return; }
    setFile(f);
  };
  const run = async () => {
    if (!file || busy) return; setAsk(false); setBusy(true); setErr(null); setRes(null); setPct(0);
    try { const r = await (kind === "idp" ? api.importIdp : api.importLegacy)(file, setPct); setRes(r); toast.push({ message: `درون‌ریزی انجام شد: ${toFa(r.created)} جدید، ${toFa(r.updated)} به‌روز.` }); }
    catch (e) { setErr(errMsg(e)); setPct(0); } finally { setBusy(false); }
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); if (canWrite) pick(e.dataTransfer.files[0]); };
  return (
    <section className="card stack" aria-labelledby={`imp-${kind}`}>
      <div><h2 id={`imp-${kind}`} style={{ fontSize: "var(--fs-4)" }}>{title}</h2><p className="muted">{hint}</p></div>
      <div className="dropzone" data-over={over} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        onClick={() => canWrite && input.current?.click()}>
        <Icon name="upload" />
        <p>{file ? <strong className="ltr">{file.name}</strong> : "فایل xlsx را اینجا رها کنید"}</p>
        <Button type="button" disabled={!canWrite || busy} onClick={(e) => { e.stopPropagation(); input.current?.click(); }}>انتخاب فایل</Button>
        <input ref={input} type="file" accept=".xlsx" className="sr-only" aria-label={`فایل ${title}`} onChange={(e) => pick(e.target.files?.[0])} tabIndex={-1} />
        {!canWrite && <span className="muted">نقش شما فقط مشاهده است.</span>}
      </div>
      {(busy || pct > 0) && <div><div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="پیشرفت بارگذاری"><span style={{ inlineSize: `${pct}%` }} /></div><p className="muted num" aria-live="polite">{toFa(pct)}٪</p></div>}
      {err && <Callout tone="danger">{err}</Callout>}
      <div><Button variant="primary" icon="upload" pending={busy} disabled={!file || !canWrite} onClick={() => setAsk(true)}>شروع درون‌ریزی</Button></div>
      <ConfirmDialog open={ask} title={`درون‌ریزی ${title}`} confirmLabel="شروع درون‌ریزی" pending={busy} onCancel={() => setAsk(false)} onConfirm={() => void run()}
        consequence={`فایل «${file?.name ?? ""}» خوانده می‌شود و رکوردهای جدید ساخته یا رکوردهای موجود به‌روز می‌شود (فایل مبدأ تغییر نمی‌کند). این کار در گزارش ممیزی ثبت می‌شود.`} />
      {res && <div className="stack" aria-live="polite">
        <Callout tone={res.errors.length ? "warn" : "ok"}><strong>نتیجه:</strong> {toFa(res.created)} جدید · {toFa(res.updated)} به‌روز · {toFa(res.skipped)} ردشده · {toFa(res.errors.length)} خطا</Callout>
        {res.error_count > 0 && res.errors.length === 0 && <p className="muted">جزئیات خطاها از سرور دریافت نشد.</p>}
        {res.errors.length > 0 && <>
          <div className="row row--between"><h3 style={{ fontSize: "var(--fs-4)" }}>گزارش خطا ({toFa(res.errors.length)}{res.error_count > res.errors.length ? ` از ${toFa(res.error_count)}` : ""})</h3><Button size="sm" icon="download" onClick={() => downloadCsv(res)}>دانلود CSV</Button></div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="گزارش خطا"><table className="table" style={{ minInlineSize: 520 }}><caption className="sr-only">گزارش خطاهای درون‌ریزی</caption>
            <thead><tr><th scope="col">برگه</th><th scope="col">ردیف</th><th scope="col">ستون</th><th scope="col">کد</th><th scope="col">شرح</th></tr></thead>
            <tbody>{res.errors.map((e, i) => <tr key={i}><td><Ident>{e.sheet || "—"}</Ident></td><td className="num">{e.row === null ? "—" : toFa(e.row)}</td><td><Ident>{e.column || "—"}</Ident></td><td><Ident>{e.code}</Ident></td><td>{e.reason}</td></tr>)}</tbody></table></div></>}
      </div>}
    </section>
  );
}

export function ImportExportScreen() {
  const api = useApi(); const { canWrite } = useAuth(); const toast = useToast();
  const [ask, setAsk] = useState(false); const [busy, setBusy] = useState(false);
  const doExport = async () => { setBusy(true); try { const { blob, filename } = await api.exportLegacy(); saveBlob(blob, filename); toast.push({ message: "فایل برون‌بری آماده شد." }); } catch (e) { toast.push({ kind: "error", message: errMsg(e) }); } finally { setBusy(false); setAsk(false); } };
  return (<>
    <PageHead title="درون‌ریزی و برون‌بری" subtitle="ورود خروجی iCare یا کارنامهٔ قدیمی، و خروجی با ستون‌بندی قدیمی." actions={canWrite && <Button icon="download" onClick={() => setAsk(true)}>برون‌بری اکسل قدیمی…</Button>} />
    <div className="grid grid--2" style={{ alignItems: "start" }}>
      <Importer kind="idp" title="خروجی iCare (IDP)" hint="درخواست‌های دوره از iCare. ردیف عنوان باید ردیف ۵ باشد." />
      <Importer kind="legacy" title="کارنامهٔ قدیمی (Record / CHistory / IFS)" hint="ورود یک‌بارهٔ اطلاعات گذشته. تکرار ورود، رکورد تکراری نمی‌سازد." />
    </div>
    <ConfirmDialog open={ask} title="برون‌بری اکسل قدیمی" confirmLabel="دانلود فایل" pending={busy} onCancel={() => setAsk(false)} onConfirm={() => void doExport()}
      consequence="فایل شامل اطلاعات شخصی کارمندان است. آن را در مکان امن نگه دارید و برای دیگران ارسال نکنید." />
  </>);
}
