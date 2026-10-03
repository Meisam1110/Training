// Layout-shift timeline per route: fresh document load, then idle. node cls2.mjs <mock|live> <role> <idleSeconds> [route,route]
import { launch, login, TARGETS, ROUTES } from "./lib.mjs";
const [target = "mock", role = "admin", secs = "40", only] = process.argv.slice(2);
const routes = only ? only.split(",") : ROUTES;
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR" });
await ctx.addInitScript(() => {
  window.__cls = []; window.__mut = [];
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cls.push({ t: Math.round(e.startTime), v: +e.value.toFixed(4), input: e.hadRecentInput, src: (e.sources || []).map(s => ((s.node && (s.node.className || s.node.nodeName)) || "?").toString().slice(0, 30) + " " + Math.round(s.previousRect.height) + ">" + Math.round(s.currentRect.height) + "@y" + Math.round(s.previousRect.y) + ">" + Math.round(s.currentRect.y)) }); }).observe({ type: "layout-shift", buffered: true }); } catch {}
  document.addEventListener("DOMContentLoaded", () => { new MutationObserver(m => window.__mut.push([Math.round(performance.now()), m.length])).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true }); });
});
const page = await ctx.newPage();
const reqs = []; page.on("request", q => { if (q.url().includes("/api/")) reqs.push([Date.now(), q.method() + " " + q.url().replace(/^https?:\/\/[^/]+/, "")]); });
const errs = []; page.on("pageerror", e => errs.push(String(e)));
await login(page, target, role);
const out = [];
for (const r of routes) {
  await page.evaluate(h => { location.hash = h; }, r);
  await page.reload({ waitUntil: "load" });
  const t0 = Date.now(); const n0 = reqs.length;
  await page.waitForTimeout(Number(secs) * 1000);
  const res = await page.evaluate(() => ({ cls: window.__cls, mut: window.__mut, now: Math.round(performance.now()), fonts: [...document.fonts].filter(f => f.status === "loaded").length }));
  const late = res.cls.filter(c => c.t > 4000);
  out.push({ route: r, shiftCount: res.cls.length, total: +res.cls.reduce((a, c) => a + c.v, 0).toFixed(4), lateShifts: late, firstShifts: res.cls.filter(c => c.t <= 4000).map(c => ({ t: c.t, v: c.v, src: c.src.slice(0, 3) })), apiCalls: reqs.slice(n0).map(x => `+${((x[0] - t0) / 1000).toFixed(1)}s ${x[1]}`), mutationsAfter4s: res.mut.filter(m => m[0] > 4000).length });
}
console.log(JSON.stringify({ target, role, errs, out }, null, 1));
await b.close();
