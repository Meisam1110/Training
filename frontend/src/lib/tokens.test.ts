import { describe, expect, it } from "vitest";
import tokensJson from "../../../docs/design-tokens.json";
import { buildTokens, contrast } from "../../scripts/tokens.mjs";

const { light, dark, css } = buildTokens(tokensJson);
const themes = { light, dark } as const;

describe("design tokens: WCAG AA", () => {
  for (const [name, t] of Object.entries(themes)) {
    describe(name, () => {
      it("body and muted text >= 4.5:1 on bg and surface", () => {
        for (const fg of ["text", "text-muted"])
          for (const bg of ["bg", "surface", "surface-2"])
            expect(contrast(t[fg]!, t[bg]!), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      });
      it("ink on brand yellow (primary buttons, active nav) >= 4.5:1", () => {
        expect(contrast(t["brand-ink"]!, t["brand"]!)).toBeGreaterThanOrEqual(4.5);
        expect(contrast(t["brand-ink"]!, t["brand-deep"]!)).toBeGreaterThanOrEqual(4.5);
      });
      it("status text >= 4.5:1 on its chip tint, surface and bg", () => {
        for (const k of ["ok", "warn", "danger", "info"])
          for (const bg of [`${k}-bg`, "surface", "bg"])
            expect(contrast(t[k]!, t[bg]!), `${k} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      });
      it("focus ring and control borders >= 3:1 (non-text)", () => {
        for (const bg of ["bg", "surface"]) {
          expect(contrast(t["focus-ring"]!, t[bg]!), `ring on ${bg}`).toBeGreaterThanOrEqual(3);
          expect(contrast(t["line-strong"]!, t[bg]!), `border on ${bg}`).toBeGreaterThanOrEqual(3);
        }
      });
    });
  }
  it("yellow is never used as a text colour token", () => {
    expect(contrast("#FFCC00", "#FFFFFF")).toBeLessThan(2); // documents why
    expect(css).not.toMatch(/--text[a-z-]*:\s*#FFCC00/i);
  });
  it("generated css has light, prefers-color-scheme dark and manual dark blocks", () => {
    expect(css).toContain("prefers-color-scheme: dark");
    expect(css).toContain(':root[data-theme="dark"]');
    expect(css).toContain(':root:not([data-theme="light"])');
  });
});
