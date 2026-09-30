import { describe, expect, it } from "vitest";
import { fmtNum, normFa, parseAmount, parseNum, toEn, toFa } from "./digits";

describe("digits", () => {
  it("toFa converts Latin digits only", () => {
    expect(toFa("Ticket LMS-1204")).toBe("Ticket LMS-۱۲۰۴");
    expect(toFa(0)).toBe("۰");
    expect(toFa(null)).toBe("");
  });
  it("toEn accepts Persian and Arabic-Indic digits", () => {
    expect(toEn("۰۹۱۲۳۴۵۶۷۸۹")).toBe("09123456789");
    expect(toEn("٠١٢٣٤٥٦٧٨٩")).toBe("0123456789");
    expect(toEn("۱٬۲۰۰٫۵")).toBe("1,200.5");
  });
  it("parseNum handles separators and rejects junk", () => {
    expect(parseNum("۱٬۲۰۰٬۰۰۰")).toBe(1200000);
    expect(parseNum("12,000")).toBe(12000);
    expect(parseNum("۱۲٫۵")).toBe(12.5);
    expect(parseNum("12a")).toBeNull();
    expect(parseNum("")).toBeNull();
  });
  it("fmtNum groups with Persian separator", () => {
    expect(fmtNum(1234567)).toBe("۱٬۲۳۴٬۵۶۷");
    expect(fmtNum(0)).toBe("۰");
    expect(fmtNum(undefined)).toBe("—");
  });
  it("normFa unifies Arabic letter variants", () => {
    expect(normFa("علي كريمي ۱۲")).toBe("علی کریمی 12");
  });
});

describe("parseAmount (Excel pastes)", () => {
  it("accepts separators, Persian digits and units", () => {
    for (const t of ["260,000,000", "۲۶۰٬۰۰۰٬۰۰۰", "260٫000٫000", "260.000.000", "260,000,000 ریال", " ۲۶۰۰۰۰۰۰۰ ", "260000000 Rial"]) expect(parseAmount(t)).toEqual({ value: 260000000, error: null });
    expect(parseAmount("")).toEqual({ value: null, error: null });
  });
  it("rejects fractions, negatives and junk with a specific reason", () => {
    expect(parseAmount("1.5").error).toMatch(/صحیح/);
    expect(parseAmount("260٫5").error).toMatch(/صحیح/);
    expect(parseAmount("-5").error).toMatch(/منفی/);
    expect(parseAmount("12abc").error).toMatch(/فقط رقم/);
  });
});
