import { launch, login, ROUTES } from "./lib.mjs";
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const page = await ctx.newPage();
const t0 = Date.now(); const f = [];
page.on("requestfinished", q => { if (q.url().includes(".woff2")) f.push(`+${((Date.now() - t0) / 1000).toFixed(1)}s ${q.url().split("/").pop()}`); });
await login(page, "liveprod", "admin"); f.push("--- logged in ---");
for (const r of ROUTES) { await page.evaluate(h => { location.hash = h; }, r); await page.waitForTimeout(1200); f.push("--- " + r); }
await page.click('button:has-text("دورهٔ جدید")').catch(() => {}); await page.waitForTimeout(500);
console.log(f.join("\n")); await b.close();
