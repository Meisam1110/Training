const FA = "۰۱۲۳۴۵۶۷۸۹";
const AR = "٠١٢٣٤٥٦٧٨٩";

/** Latin digits -> Persian digits (display). Non-digit characters are untouched. */
export function toFa(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[0-9]/g, (d) => FA[Number(d)] ?? d);
}

/** Persian and Arabic-Indic digits (and their separators) -> Latin. Used on every input. */
export function toEn(v: string): string {
  return v
    .replace(/[۰-۹]/g, (d) => String(FA.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String(AR.indexOf(d)))
    .replace(/٫/g, ".")
    .replace(/[٬،]/g, ",");
}

/** Parse a number typed with any digit script and optional thousand separators. */
export function parseNum(v: string): number | null {
  const s = toEn(v).replace(/[,\s]/g, "");
  if (s === "" || !/^-?\d+(\.\d+)?$/.test(s)) return null;
  return Number(s);
}

/** 1234567 -> ۱٬۲۳۴٬۵۶۷ */
export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return toFa(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "٬"));
}

/** Persian-normalise typed text: Arabic ي/ك -> ی/ک so search matches regardless of keyboard. */
export function normFa(v: string): string {
  return toEn(v).replace(/ي/g, "ی").replace(/ك/g, "ک").trim().toLowerCase();
}

export interface AmountResult { value: number | null; error: string | null }
/**
 * Parse a money amount typed or pasted from Excel: Persian/Arabic/Latin digits, units ("ریال", "تومان", "rial"),
 * thousands separators (, ٬ ، and ٫ when it groups by three), spaces. Whole rials only, non-negative.
 */
export function parseAmount(text: string): AmountResult {
  let s = toEn(text).replace(/ریال|تومان|rials?|irr/gi, "").replace(/[\s ‌]/g, "");
  if (s === "") return { value: null, error: null };
  if (/^-/.test(s)) return { value: null, error: "مبلغ نمی‌تواند منفی باشد." };
  if (!/^[\d.,]+$/.test(s)) return { value: null, error: "فقط رقم بنویسید؛ مثلاً ۲۶۰٬۰۰۰٬۰۰۰." };
  // thousands grouping: 1,234,567 (also with dots when every group has 3 digits)
  if (/^\d{1,3}([.,]\d{3})+$/.test(s)) s = s.replace(/[.,]/g, "");
  else if (/[.,]/.test(s)) return { value: null, error: "مبلغ باید عدد صحیح (ریال) باشد؛ اعشار مجاز نیست." };
  const n = Number(s);
  if (!Number.isFinite(n) || n > 1e15) return { value: null, error: "مبلغ بیش از حد بزرگ است." };
  return { value: n, error: null };
}
