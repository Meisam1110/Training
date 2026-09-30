import { describe, expect, it } from "vitest";
import {
  analyzeJalaliInput, addDaysISO, diffDaysISO, fmtJalali, fmtJalaliLong, isJalaliLeap, isoToJalali, jalaliMonthLength,
  jalaliToISO, parseJalaliInput, toGregorian, toJalali, weekdayIndexISO,
} from "./jalali";

describe("known dates", () => {
  const cases: [string, [number, number, number]][] = [
    ["2024-03-20", [1403, 1, 1]],
    ["2025-03-21", [1404, 1, 1]],
    ["2026-03-21", [1405, 1, 1]],
    ["2025-03-20", [1403, 12, 30]],
    ["2026-09-30", [1405, 7, 8]],
    ["2000-01-01", [1378, 10, 11]],
    ["1979-02-11", [1357, 11, 22]],
    ["2021-03-20", [1399, 12, 30]],
    ["2021-03-21", [1400, 1, 1]],
  ];
  for (const [iso, [jy, jm, jd]] of cases) {
    it(`${iso} <-> ${jy}/${jm}/${jd}`, () => {
      expect(isoToJalali(iso)).toEqual({ jy, jm, jd });
      expect(jalaliToISO(jy, jm, jd)).toBe(iso);
    });
  }
});

describe("leap years", () => {
  it("matches the official calendar for recent years", () => {
    const leaps = [1399, 1403, 1408, 1412];
    for (const y of leaps) expect(isJalaliLeap(y)).toBe(true);
    for (const y of [1400, 1401, 1402, 1404, 1405, 1406, 1407]) expect(isJalaliLeap(y)).toBe(false);
  });
  it("month lengths", () => {
    expect(jalaliMonthLength(1403, 12)).toBe(30);
    expect(jalaliMonthLength(1404, 12)).toBe(29);
    expect(jalaliMonthLength(1404, 1)).toBe(31);
    expect(jalaliMonthLength(1404, 7)).toBe(30);
  });
});

describe("round trip", () => {
  it("every day from 1300 to 1500 survives gregorian -> jalali -> gregorian and is contiguous", () => {
    let prev = "";
    let iso = jalaliToISO(1300, 1, 1);
    const end = jalaliToISO(1500, 1, 1);
    let n = 0;
    while (iso !== end) {
      const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
      const j = toJalali(y, m, d);
      expect(toGregorian(j.jy, j.jm, j.jd)).toEqual({ gy: y, gm: m, gd: d });
      expect(j.jd).toBeLessThanOrEqual(jalaliMonthLength(j.jy, j.jm));
      if (prev) expect(diffDaysISO(prev, iso)).toBe(1);
      prev = iso; iso = addDaysISO(iso, 1); n++;
    }
    expect(n).toBeGreaterThan(73000);
  });
});

describe("formatting and parsing", () => {
  it("formats with Persian digits", () => {
    expect(fmtJalali("2026-09-30")).toBe("۱۴۰۵/۰۷/۰۸");
    expect(fmtJalaliLong("2026-09-30")).toBe("۸ مهر ۱۴۰۵");
    expect(fmtJalali("")).toBe("");
  });
  it("accepts Persian and Latin digits and various separators", () => {
    expect(parseJalaliInput("۱۴۰۵/۰۷/۰۸")).toBe("2026-09-30");
    expect(parseJalaliInput("1405/7/8")).toBe("2026-09-30");
    expect(parseJalaliInput("۱۴۰۵-۷-۸")).toBe("2026-09-30");
    expect(parseJalaliInput("1403/12/30")).toBe("2025-03-20");
  });
  it("rejects impossible dates", () => {
    expect(parseJalaliInput("1404/12/30")).toBeNull();
    expect(parseJalaliInput("1404/13/01")).toBeNull();
    expect(parseJalaliInput("1404/07/31")).toBeNull();
    expect(parseJalaliInput("abc")).toBeNull();
  });
  it("weekday is Saturday-first", () => {
    expect(weekdayIndexISO("2026-09-26")).toBe(0); // Saturday
    expect(weekdayIndexISO("2026-09-25")).toBe(6); // Friday
  });
  it("adds days across month/leap boundaries", () => {
    expect(addDaysISO("2024-02-28", 2)).toBe("2024-03-01");
    expect(addDaysISO("2026-07-01", 60)).toBe("2026-08-30");
    expect(diffDaysISO("2026-01-01", "2026-03-01")).toBe(59);
  });
});

describe("analyzeJalaliInput", () => {
  it("accepts compact 8 digits and mixed separators", () => {
    expect(analyzeJalaliInput("14050708").iso).toBe("2026-09-30");
    expect(analyzeJalaliInput("۱۴۰۵-۷-۸").iso).toBe("2026-09-30");
  });
  it("refuses a Gregorian-looking year and offers the Jalali equivalent", () => {
    const r = analyzeJalaliInput("2026/10/01");
    expect(r.iso).toBeNull(); expect(r.error).toMatch(/میلادی/);
    expect(r.suggestion).toEqual({ iso: "2026-10-01", text: "۱۴۰۵/۰۷/۰۹" });
    expect(analyzeJalaliInput("0001/01/01").error).toMatch(/بین/);
  });
  it("gives specific reasons", () => {
    expect(analyzeJalaliInput("1404/12/30").error).toBe("اسفند ۱۴۰۴ فقط ۲۹ روز دارد.");
    expect(analyzeJalaliInput("1405/13/01").error).toBe("ماه باید ۱ تا ۱۲ باشد.");
    expect(analyzeJalaliInput("1405/07/31").error).toBe("مهر ۱۴۰۵ فقط ۳۰ روز دارد.");
    expect(analyzeJalaliInput("hello").error).toMatch(/سال\/ماه\/روز/);
    expect(analyzeJalaliInput("")).toEqual({ iso: null, error: null, suggestion: null });
  });
});
