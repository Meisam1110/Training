// Jalali (Solar Hijri) <-> Gregorian conversion. Algorithm: the 33-year-cycle breakpoint
// method (as in jalaali-js), valid for Jalali years -61..3177. Wire format elsewhere in the
// app is ISO Gregorian "YYYY-MM-DD"; only display/input is Jalali.
import { toEn, toFa } from "./digits";

export interface JDate { jy: number; jm: number; jd: number }

const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
const div = (a: number, b: number) => Math.trunc(a / b);
const mod = (a: number, b: number) => a - Math.floor(a / b) * b;

function jalCal(jy: number) {
  if (jy < BREAKS[0]! || jy >= BREAKS[BREAKS.length - 1]!) throw new RangeError(`Invalid Jalali year ${jy}`);
  const gy = jy + 621;
  let leapJ = -14, jp = BREAKS[0]!, jump = 0;
  for (let i = 1; i < BREAKS.length; i++) {
    const jm = BREAKS[i]!;
    jump = jm - jp;
    if (jy < jm) break;
    leapJ += div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }
  let n = jy - jp;
  leapJ += div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;
  return { leap, gy, march };
}

function g2d(gy: number, gm: number, gd: number): number {
  let d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
  d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
  return d;
}
function d2g(jdn: number) {
  let j = 4 * jdn + 139361631;
  j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
  const i = div(mod(j, 1461), 4) * 5 + 308;
  const gd = div(mod(i, 153), 5) + 1;
  const gm = mod(div(i, 153), 12) + 1;
  const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
  return { gy, gm, gd };
}
function j2d(jy: number, jm: number, jd: number): number {
  const r = jalCal(jy);
  return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
}
function d2j(jdn: number): JDate {
  const gy = d2g(jdn).gy;
  let jy = gy - 621;
  const r = jalCal(jy);
  const jdn1f = g2d(gy, 3, r.march);
  let k = jdn - jdn1f;
  if (k >= 0) {
    if (k <= 185) return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
    k -= 186;
  } else {
    jy -= 1;
    k += 179;
    if (r.leap === 1) k += 1;
  }
  return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
}

export function isJalaliLeap(jy: number): boolean { return jalCal(jy).leap === 0; }
export function jalaliMonthLength(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isJalaliLeap(jy) ? 30 : 29;
}
export function isValidJalali(jy: number, jm: number, jd: number): boolean {
  return Number.isInteger(jy) && Number.isInteger(jm) && Number.isInteger(jd) &&
    jy >= -61 && jy < 3177 && jm >= 1 && jm <= 12 && jd >= 1 && jd <= jalaliMonthLength(jy, jm);
}
export function toJalali(gy: number, gm: number, gd: number): JDate { return d2j(g2d(gy, gm, gd)); }
export function toGregorian(jy: number, jm: number, jd: number): { gy: number; gm: number; gd: number } {
  return d2g(j2d(jy, jm, jd));
}

// ---- ISO helpers (wire format) ----
export const pad = (n: number, w = 2) => String(n).padStart(w, "0");
export function parseISO(iso: string): { y: number; m: number; d: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const y = +m[1]!, mo = +m[2]!, d = +m[3]!;
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return { y, m: mo, d };
}
export const toISO = (y: number, m: number, d: number) => `${pad(y, 4)}-${pad(m)}-${pad(d)}`;
export function isoToJalali(iso: string | null | undefined): JDate | null {
  if (!iso) return null;
  const p = parseISO(iso);
  return p ? toJalali(p.y, p.m, p.d) : null;
}
export function jalaliToISO(jy: number, jm: number, jd: number): string {
  const g = toGregorian(jy, jm, jd);
  return toISO(g.gy, g.gm, g.gd);
}
export function addDaysISO(iso: string, days: number): string {
  const p = parseISO(iso);
  if (!p) return iso;
  const dt = new Date(Date.UTC(p.y, p.m - 1, p.d + days));
  return toISO(dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate());
}
export function diffDaysISO(a: string, b: string): number {
  const pa = parseISO(a), pb = parseISO(b);
  if (!pa || !pb) return NaN;
  return Math.round((Date.UTC(pb.y, pb.m - 1, pb.d) - Date.UTC(pa.y, pa.m - 1, pa.d)) / 86400000);
}
export function todayISO(now: Date = new Date()): string {
  return toISO(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

export const JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
/** Saturday-first week, matching the Iranian calendar. */
export const JALALI_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
export const JALALI_WEEKDAYS_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
/** 0 = Saturday … 6 = Friday for an ISO date. */
export function weekdayIndexISO(iso: string): number {
  const p = parseISO(iso);
  if (!p) return 0;
  return mod(new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay() + 1, 7);
}

/** ISO -> "۱۴۰۵/۰۷/۰۸" (or "" for empty). */
export function fmtJalali(iso: string | null | undefined): string {
  const j = isoToJalali(iso);
  return j ? toFa(`${pad(j.jy, 4)}/${pad(j.jm)}/${pad(j.jd)}`) : "";
}
/** ISO -> "۸ مهر ۱۴۰۵" */
export function fmtJalaliLong(iso: string | null | undefined): string {
  const j = isoToJalali(iso);
  return j ? `${toFa(j.jd)} ${JALALI_MONTHS[j.jm - 1]} ${toFa(j.jy)}` : "";
}
/** ISO date-time -> "۱۴۰۵/۰۷/۰۸ ۱۴:۳۰" in the browser's local time. */
export function fmtJalaliDateTime(isoDT: string | null | undefined): string {
  if (!isoDT) return "";
  const d = new Date(isoDT);
  if (Number.isNaN(d.getTime())) return "";
  const j = toJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return toFa(`${pad(j.jy, 4)}/${pad(j.jm)}/${pad(j.jd)} ${pad(d.getHours())}:${pad(d.getMinutes())}`);
}

/**
 * Parse user-typed Jalali text ("1405/7/8", "۱۴۰۵-۰۷-۰۸", "۱۴۰۵.۷.۸") into ISO Gregorian.
 * Returns null when the text is not a real Jalali date.
 */
export function parseJalaliInput(text: string): string | null {
  const m = /^\s*(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$/.exec(toEn(text));
  if (!m) return null;
  const [jy, jm, jd] = [+m[1]!, +m[2]!, +m[3]!];
  if (!isValidJalali(jy, jm, jd)) return null;
  return jalaliToISO(jy, jm, jd);
}

export interface JalaliAnalysis { iso: string | null; error: string | null; suggestion: { iso: string; text: string } | null }
const JMIN = 1300, JMAX = 1500;
/**
 * Explain what is wrong with typed Jalali text. Accepts "1405/7/8", "۱۴۰۵-۰۷-۰۸" and compact "14050708".
 * A year that looks Gregorian (1700-2200) is refused with a converted suggestion.
 */
export function analyzeJalaliInput(text: string): JalaliAnalysis {
  const none = { iso: null, suggestion: null };
  let t = toEn(text).trim();
  if (t === "") return { iso: null, error: null, suggestion: null };
  const compact = /^(\d{4})(\d{2})(\d{2})$/.exec(t); if (compact) t = `${compact[1]}/${compact[2]}/${compact[3]}`;
  const m = /^(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})$/.exec(t);
  if (!m) return { ...none, error: "تاریخ را به صورت سال/ماه/روز بنویسید؛ مثلاً ۱۴۰۵/۰۷/۰۸." };
  const [y, mo, d] = [+m[1]!, +m[2]!, +m[3]!];
  if (y >= 1700 && y <= 2200) {
    const g = parseISO(toISO(y, Math.min(Math.max(mo, 1), 12), Math.max(d, 1)));
    const conv = g && mo >= 1 && mo <= 12 ? toJalali(g.y, g.m, g.d) : null;
    const sug = conv ? { iso: toISO(g!.y, g!.m, g!.d), text: `${pad(conv.jy, 4)}/${pad(conv.jm)}/${pad(conv.jd)}` } : null;
    return { iso: null, error: `${toFa(y)} سال میلادی به نظر می‌رسد؛ این فیلد شمسی است.`, suggestion: sug && { iso: sug.iso, text: toFa(sug.text) } };
  }
  if (y < JMIN || y > JMAX) return { ...none, error: `سال باید بین ${toFa(JMIN)} و ${toFa(JMAX)} باشد.` };
  if (mo < 1 || mo > 12) return { ...none, error: "ماه باید ۱ تا ۱۲ باشد." };
  const len = jalaliMonthLength(y, mo);
  if (d < 1) return { ...none, error: "روز باید دست‌کم ۱ باشد." };
  if (d > len) return { ...none, error: `${JALALI_MONTHS[mo - 1]} ${toFa(y)} فقط ${toFa(len)} روز دارد.` };
  return { iso: jalaliToISO(y, mo, d), error: null, suggestion: null };
}
