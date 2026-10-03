import { launch, login, TARGETS, ROUTES } from "./lib.mjs";
const [target = "mock", role = "admin", secs = "35"] = process.argv.slice(2);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR" });
const page = await ctx.newPage();
const errs = []; page.on("pageerror", e => errs.push(String(e)));
await login(page, target, role);
const out = [];
for (const r of ROUTES) {
  const reqs = [];
  const onreq = q => { if (q.url().includes("/api/")) reqs.push([Date.now(), q.method(), q.url().replace(/^https?:\/\/[^/]+/, "")]); };
  page.on("request", onreq);
  await page.evaluate(() => { window.__cls = []; window.__sh = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cls.push({ t: Math.round(e.startTime), v: +e.value.toFixed(4), input: e.hadRecentInput, src: (e.sources||[]).map(s => (s.node?.className||s.node?.nodeName||"?").toString().slice(0,40)+":"+Math.round(s.previousRect.height)+">"+Math.round(s.currentRect.height)) }); }).observe({ type: "layout-shift", buffered: true }); window.__h0 = document.documentElement.scrollHeight; });
  const t0 = Date.now();
  await page.evaluate(h => { location.hash = h; }, r);
  await page.waitForTimeout(Number(secs) * 1000);
  const res = await page.evaluate(() => ({ cls: window.__cls, h: document.documentElement.scrollHeight, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  page.off("request", onreq);
  const afterLoad = reqs.filter(x => x[0] - t0 > 3000);
  out.push({ route: r, shifts: res.cls.length, total: +res.cls.reduce((a, c) => a + c.v, 0).toFixed(4), detail: res.cls.slice(0, 6), reqTotal: reqs.length, reqAfter3s: afterLoad.map(x => `${x[1]} ${x[2]} @+${((x[0]-t0)/1000).toFixed(1)}s`), overflowX: res.sw > res.cw });
}
console.log(JSON.stringify({ target, role, errs, out }, null, 1));
await b.close();
