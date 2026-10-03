// Page-jump probe: samples scrollHeight/scrollY/main-top every 150ms for N seconds while idle and while the SPA
// navigates A->B->A (to expose stale-refetch swaps). node jump.mjs <target> <role> <route> <secs>
import { launch, login } from "./lib.mjs";
const [target = "mockprod", role = "admin", route = "/", secs = "30"] = process.argv.slice(2);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR" });
await ctx.addInitScript(() => { window.__cls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cls.push({ t: Math.round(e.startTime), v: +e.value.toFixed(4), src: (e.sources || []).map(s => ((s.node && (s.node.className || s.node.nodeName)) || "?").toString().slice(0, 28) + " " + Math.round(s.previousRect.y) + ">" + Math.round(s.currentRect.y) + " h" + Math.round(s.previousRect.height) + ">" + Math.round(s.currentRect.height)) }); }).observe({ type: "layout-shift", buffered: true }); });
const page = await ctx.newPage(); const calls = [];
page.on("request", q => { if (q.url().includes("/api/")) calls.push([Date.now(), q.url().replace(/^https?:\/\/[^/]+/, "")]); });
await login(page, target, role);
await page.evaluate(h => { location.hash = h; }, route); await page.reload();
const t0 = Date.now(); const samples = [];
await page.evaluate(() => { window.__s = []; setInterval(() => { const m = document.querySelector("main"); window.__s.push([Math.round(performance.now()), document.documentElement.scrollHeight, Math.round(scrollY), m ? Math.round(m.getBoundingClientRect().top) : null, document.querySelector("h1")?.getBoundingClientRect().top | 0]); }, 150); });
// mimic a person: move the mouse around + scroll a bit
for (let i = 0; i < Number(secs) * 2; i++) { await page.mouse.move(300 + (i * 37) % 900, 200 + (i * 53) % 500); await page.waitForTimeout(500); if (i === 6) await page.mouse.wheel(0, 300); }
const r = await page.evaluate(() => ({ s: window.__s, cls: window.__cls }));
let changes = []; for (let i = 1; i < r.s.length; i++) { const a = r.s[i - 1], c = r.s[i]; if (a[1] !== c[1] || a[3] !== c[3] || (a[2] !== c[2])) changes.push({ t: c[0], height: a[1] + ">" + c[1], scrollY: a[2] + ">" + c[2], mainTop: a[3] + ">" + c[3] }); }
console.log(JSON.stringify({ target, route, samples: r.s.length, cls: r.cls.filter(c => c.v > 0.001), changes: changes.slice(0, 30), apiCallsAfter3s: calls.filter(c => c[0] - t0 > 3000).map(c => c[1]) }, null, 1));
await b.close();
