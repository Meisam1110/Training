// Virtualised tables: scroll the table-wrap in 120px wheel steps; log scrollHeight changes / thumb jumps and real vs estimated row heights.
import { launch, login } from "./lib.mjs";
const [target = "mockprod"] = process.argv.slice(2);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR" }); const page = await ctx.newPage(); await login(page, target, "admin");
for (const route of ["/employees", "/runs/5/candidates", "/admin"]) {
  await page.evaluate(h => { location.hash = h; }, route); await page.waitForTimeout(2000);
  const info = await page.evaluate(() => { const w = document.querySelector(".table-wrap"); if (!w) return null; const rows = [...w.querySelectorAll("tbody tr:not([aria-hidden])")]; return { rows: rows.length, h: [...new Set(rows.map(r => Math.round(r.getBoundingClientRect().height)))].slice(0, 6), scrollH: w.scrollHeight, clientH: w.clientHeight }; });
  if (!info) { console.log(route, "no table"); continue; }
  const log = []; let prev = null;
  for (let i = 0; i < 40; i++) {
    await page.evaluate(() => { const w = document.querySelector(".table-wrap"); w.scrollTop += 150; });
    await page.waitForTimeout(60);
    const s = await page.evaluate(() => { const w = document.querySelector(".table-wrap"); const first = [...w.querySelectorAll("tbody tr:not([aria-hidden])")][0]; return { top: Math.round(w.scrollTop), sh: w.scrollHeight, first: first ? Math.round(first.getBoundingClientRect().top - w.getBoundingClientRect().top) : null }; });
    if (prev && prev.sh !== s.sh) log.push(`i=${i} scrollHeight ${prev.sh}>${s.sh}`);
    prev = s;
  }
  console.log(route, JSON.stringify(info), "scrollHeight changes while scrolling:", log.length, log.slice(0, 5));
}
await b.close();
