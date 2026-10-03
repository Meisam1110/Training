// SPA journey: click through sidebar twice (cold then warm cache) and interact; log every layout shift >0.005 with the step that caused it.
import { launch, login } from "./lib.mjs";
const [target = "mockprod", role = "admin", width = "1440"] = process.argv.slice(2);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: Number(width), height: 900 }, locale: "fa-IR" });
await ctx.addInitScript(() => { window.__cls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cls.push({ t: Math.round(performance.now()), v: +e.value.toFixed(4), src: (e.sources || []).map(s => ((s.node && (s.node.className || s.node.nodeName)) || "?").toString().slice(0, 28) + " y" + Math.round(s.previousRect.y) + ">" + Math.round(s.currentRect.y) + " h" + Math.round(s.previousRect.height) + ">" + Math.round(s.currentRect.height)) }); }).observe({ type: "layout-shift" }); });
const page = await ctx.newPage(); await login(page, target, role);
const log = []; let last = 0;
async function step(name, fn, wait = 1500) {
  const before = await page.evaluate(() => window.__cls.length);
  try { await fn(); } catch (e) { log.push({ step: name, error: String(e).slice(0, 120) }); return; }
  await page.waitForTimeout(wait);
  const c = await page.evaluate(n => window.__cls.slice(n), before);
  const tot = +c.reduce((a, x) => a + x.v, 0).toFixed(4);
  log.push({ step: name, shifts: c.length, cls: tot, top: c.filter(x => x.v > 0.005).slice(0, 3).map(x => `${x.v} ${x.src.slice(0, 3).join(" | ")}`) });
}
const nav = async text => { await page.click(`.nav a:has-text("${text}")`); };
const items = (await page.$$eval(".nav a", as => as.map(a => a.textContent.trim())));
for (const pass of ["cold", "warm"]) for (const t of items) await step(`${pass} nav ${t}`, () => nav(t));
await step("runs: type search", async () => { await nav("دوره‌های آموزشی"); await page.waitForTimeout(800); await page.fill('input[type="search"]', "مدیریت"); }, 2000);
await step("runs: clear search", () => page.fill('input[type="search"]', ""), 2000);
await step("runs: sort by start", async () => { await page.click('th button:has-text("شروع")'); });
await step("runs: open first run", () => page.click("table a >> nth=0"), 2500);
await step("run: click step 3", () => page.click(".step__btn >> nth=2"));
await step("run: click step 5", () => page.click(".step__btn >> nth=4"));
await step("enrollments: page/filters", async () => { await nav("ثبت‌نام‌ها"); await page.waitForTimeout(1200); const sel = await page.$$("select"); if (sel[0]) await sel[0].selectOption({ index: 1 }); }, 2000);
await step("enrollments: next page", async () => { const n = await page.$('button:has-text("بعدی")'); if (n) await n.click(); }, 1500);
await step("letters: change kind", async () => { await nav("مرکز نامه‌ها"); await page.waitForTimeout(1200); const sel = await page.$$("select"); if (sel[1]) await sel[1].selectOption({ index: 2 }); }, 2500);
console.log(JSON.stringify({ target, role, width, log: log.filter(l => l.error || l.cls > 0.005 || l.shifts > 3), total: log.length }, null, 1));
await b.close();
