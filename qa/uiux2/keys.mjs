// Real Tab test (not element.focus()): per screen, Tab through, record ring visibility, reachability, order jumps.
import { launch, login, ROUTES } from "./lib.mjs";
const [target = "mockprod", role = "admin", theme = "light"] = process.argv.slice(2);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR", colorScheme: theme });
const page = await ctx.newPage(); await login(page, target, role);
const out = [];
for (const r of ROUTES) {
  await page.evaluate(h => { location.hash = h; }, r); await page.waitForTimeout(1500);
  await page.evaluate(() => { window.__seen = new WeakSet(); document.activeElement?.blur(); window.scrollTo(0, 0); });
  const stops = []; let first = null;
  const total = await page.evaluate(() => [...document.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex='0']")].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden" && !e.closest("[inert],[hidden]"); }).length);
  for (let i = 0; i < 120; i++) {
    await page.keyboard.press("Tab");
    const s = await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return { body: true }; window.__seen = window.__seen || new WeakSet(); const rep = window.__seen.has(e); window.__seen.add(e); if (rep) return { repeat: true }; const cs = getComputedStyle(e); const rc = e.getBoundingClientRect(); const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== "none"); return { tag: e.tagName.toLowerCase(), name: (e.getAttribute("aria-label") || e.textContent || e.value || e.id || "").trim().slice(0, 28), ring: !!ring, vis: rc.top >= -2 && rc.bottom <= innerHeight + 2, key: e.outerHTML.slice(0, 60) }; });
    if (s.body) { stops.push(s); break; }
    if (s.repeat) break;
    stops.push(s);
  }
  const noRing = stops.filter(s => s.ring === false).map(s => `${s.tag}:${s.name}`);
  const hidden = stops.filter(s => s.vis === false).length;
  out.push({ route: r, interactive: total, tabStops: stops.length, reachedPct: Math.round(100 * stops.length / Math.max(1, total)), noRing: noRing.slice(0, 6), noRingCount: noRing.length, offscreenAfterFocus: hidden, firstStops: stops.slice(0, 3).map(s => s.name) });
}
// dialog focus-return test
await page.evaluate(() => { location.hash = "/runs"; }); await page.waitForTimeout(1200);
const btn = page.locator('button:has-text("دورهٔ جدید")'); await btn.focus(); await page.keyboard.press("Enter"); await page.waitForTimeout(400);
const inDialog = await page.evaluate(() => !!document.activeElement.closest('[role=dialog]'));
await page.keyboard.press("Escape"); await page.waitForTimeout(300);
const back = await page.evaluate(() => document.activeElement.textContent.trim().slice(0, 20));
console.log(JSON.stringify({ target, role, theme, dialog: { focusInside: inDialog, returnedTo: back }, out }, null, 1));
await b.close();
