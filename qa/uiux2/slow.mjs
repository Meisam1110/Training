// Dashboard on a slow link: shows that independent queries resolve at different times -> several separate shifts seconds apart.
import { launch, login } from "./lib.mjs";
const lat = Number(process.argv[2] || 900);
const b = await launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, locale: "fa-IR" });
await ctx.addInitScript(() => { window.__cls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__cls.push({ t: Math.round(performance.now()), v: +e.value.toFixed(3), src: (e.sources || []).map(s => ((s.node && (s.node.className || s.node.nodeName)) || "?").toString().slice(0, 24) + " h" + Math.round(s.previousRect.height) + ">" + Math.round(s.currentRect.height)).slice(0, 3) }); }).observe({ type: "layout-shift", buffered: true }); });
const page = await ctx.newPage(); await login(page, "liveprod", "admin");
const cdp = await ctx.newCDPSession(page); await cdp.send("Network.enable");
await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: lat, downloadThroughput: 400 * 1024, uploadThroughput: 200 * 1024 });
await page.evaluate(() => { location.hash = "/"; }); await page.waitForTimeout(lat * 6);
await page.reload(); await page.waitForTimeout(lat * 10 + 3000);
const r = await page.evaluate(() => window.__cls);
console.log("latency", lat, "shifts:", JSON.stringify(r)); await b.close();
