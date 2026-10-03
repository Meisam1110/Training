import { useEffect, useId, useRef, useState } from "react";
import { toFa } from "../lib/digits";
import {
  addDaysISO, fmtJalali, isoToJalali, jalaliMonthLength, jalaliToISO, JALALI_MONTHS, JALALI_WEEKDAYS, JALALI_WEEKDAYS_SHORT,
  analyzeJalaliInput, todayISO, weekdayIndexISO,
} from "../lib/jalali";
import { Button } from "./ui";
import { FieldShell, fieldAria } from "./Field";

interface Props { label: string; value: string; onChange: (iso: string) => void; error?: string | null; hint?: string; required?: boolean; disabled?: boolean }

/** Jalali date input + calendar popover. Value on the wire is ISO Gregorian. */
export function DatePicker({ label, value, onChange, error, hint, required, disabled }: Props) {
  const id = useId();
  const [text, setText] = useState(fmtJalali(value));
  const [open, setOpen] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [suggest, setSuggest] = useState<{ iso: string; text: string } | null>(null);
  const [focused, setFocused] = useState(value || todayISO());
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => { setText(fmtJalali(value)); setLocalErr(null); setSuggest(null); }, [value]);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [open]);

  const commit = () => {
    const r = analyzeJalaliInput(text);
    if (text.trim() === "") { setLocalErr(null); setSuggest(null); if (value) onChange(""); return; }
    if (!r.iso) { setLocalErr(r.error); setSuggest(r.suggestion); return; }
    setLocalErr(null); setSuggest(null); setText(fmtJalali(r.iso)); if (r.iso !== value) onChange(r.iso);
  };
  const pick = (iso: string) => { onChange(iso); setOpen(false); btn.current?.focus(); };
  const shown = error || localErr;

  return (
    <FieldShell id={id} label={label} error={shown} hint={hint} required={required}>
      <div className="dp" ref={wrap} onKeyDown={(e) => { if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); btn.current?.focus(); } }}>
        <div className="dp__row">
          <input className="input" {...fieldAria(id, shown, hint)} dir="ltr" inputMode="numeric" autoComplete="off" disabled={disabled}
            value={text} placeholder="۱۴۰۵/۰۷/۰۸" onChange={(e) => setText(e.target.value)} onBlur={commit}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "ArrowDown" && e.altKey) setOpen(true); }} />
          <Button ref={btn} aria-label={`انتخاب تاریخ از تقویم: ${label}`} aria-haspopup="dialog" aria-expanded={open} icon="calendar" disabled={disabled}
            onClick={() => { setFocused(value || todayISO()); setOpen((o) => !o); }} />
        </div>
        {suggest && <div className="callout callout--info" style={{ marginBlockStart: 6 }}><span>معادل شمسی: <strong>{suggest.text}</strong></span><Button size="sm" onClick={() => { onChange(suggest.iso); setSuggest(null); setLocalErr(null); }}>اعمال</Button></div>}
        {open && <Calendar selected={value} focused={focused} setFocused={setFocused} onPick={pick} label={label} />}
      </div>
    </FieldShell>
  );
}

function Calendar({ selected, focused, setFocused, onPick, label }: { selected: string; focused: string; setFocused: (s: string) => void; onPick: (s: string) => void; label: string }) {
  const j = isoToJalali(focused)!;
  const len = jalaliMonthLength(j.jy, j.jm);
  const firstISO = jalaliToISO(j.jy, j.jm, 1);
  const offset = weekdayIndexISO(firstISO);
  const today = todayISO();
  const gridRef = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    gridRef.current?.querySelector<HTMLElement>('[tabindex="0"]')?.focus();
    first.current = false;
  }, [focused]);

  const shiftMonth = (n: number) => {
    let m = j.jm + n, y = j.jy;
    while (m > 12) { m -= 12; y++; } while (m < 1) { m += 12; y--; }
    setFocused(jalaliToISO(y, m, Math.min(j.jd, jalaliMonthLength(y, m))));
  };
  const key = (e: React.KeyboardEvent) => {
    const map: Record<string, number> = { ArrowRight: -1, ArrowLeft: 1, ArrowUp: -7, ArrowDown: 7 }; // RTL: right = previous day
    if (e.key in map) { e.preventDefault(); setFocused(addDaysISO(focused, map[e.key]!)); }
    else if (e.key === "PageUp") { e.preventDefault(); shiftMonth(-1); }
    else if (e.key === "PageDown") { e.preventDefault(); shiftMonth(1); }
    else if (e.key === "Home") { e.preventDefault(); setFocused(firstISO); }
    else if (e.key === "End") { e.preventDefault(); setFocused(jalaliToISO(j.jy, j.jm, len)); }
  };
  return (
    <div className="dp__pop" role="dialog" aria-label={`تقویم ${label}`}>
      <div className="dp__head">
        <Button variant="ghost" icon="chevron" aria-label="ماه بعد" onClick={() => shiftMonth(1)} style={{ transform: "scaleX(-1)" }} />
        <div className="dp__title" aria-live="polite">{JALALI_MONTHS[j.jm - 1]} {toFa(j.jy)}</div>
        <Button variant="ghost" icon="chevron" aria-label="ماه قبل" onClick={() => shiftMonth(-1)} />
      </div>
      <div className="dp__grid" role="grid" ref={gridRef} onKeyDown={key} aria-label={`${JALALI_MONTHS[j.jm - 1]} ${toFa(j.jy)}`}>
        {JALALI_WEEKDAYS_SHORT.map((d, i) => <div key={d} className="dp__dow" role="columnheader" aria-label={JALALI_WEEKDAYS[i]}>{d}</div>)}
        {Array.from({ length: offset }, (_, i) => <span key={`b${i}`} />)}
        {Array.from({ length: len }, (_, i) => {
          const iso = jalaliToISO(j.jy, j.jm, i + 1);
          return (
            <button key={iso} type="button" className="dp__day" role="gridcell" tabIndex={iso === focused ? 0 : -1}
              aria-selected={iso === selected} data-today={iso === today} aria-label={`${toFa(i + 1)} ${JALALI_MONTHS[j.jm - 1]} ${toFa(j.jy)}`}
              onClick={() => onPick(iso)}>{toFa(i + 1)}</button>
          );
        })}
      </div>
      <div className="dp__foot">
        <Button size="sm" variant="ghost" onClick={() => onPick(today)}>امروز</Button>
        <Button size="sm" variant="ghost" onClick={() => onPick("")}>پاک کردن</Button>
      </div>
    </div>
  );
}
