// Layout-stability regression: measures Cumulative Layout Shift (PerformanceObserver "layout-shift", excluding
// shifts right after user input) plus scroll jumps on every screen for N seconds. Target: CLS 0.00, no jumps.
// Usage:  node scripts/cls.mjs --url http://localhost:4190 --user admin --pass demo [--seconds 30] [--width 1280] [--only runs,letters]
import { chromium } from "playwright-core";
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg("url", "http://localhost:4190"), USER = arg("user", "admin"), PASS = arg("pass", "demo");
const SLOW = process.argv.includes("--slow"); // emulate a slow link (400 ms RTT, 1.5 Mbit/s) + 4x CPU: exposes staggered loads and font swaps
const SECONDS = +arg("seconds", 30), WIDTH = +arg("width", 1280), ONLY = arg("only", "")?.split(",").filter(Boolean);
const SCREENS = [["login", "/login", false], ["dashboard", "/", true], ["runs", "/runs", true], ["courses", "/courses", true], ["run-detail", "/runs/3", true], ["candidates", "/runs/3/candidates", true], ["enrollments", "/enrollments", true],
  ["letters", "/letters?kind=course_announcement&run=3", true], ["employees", "/employees", true], ["connectors", "/connectors", true], ["automation", "/automation", true], ["transfer", "/import-export", true], ["admin", "/admin", true]];
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const results = [];
async function one([name, path, auth]) {
  const ctx = await browser.newContext({ viewport: { width: WIDTH, height: 800 }, locale: "fa-IR" });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    window.__cls = { value: 0, shifts: [], jumps: [] };
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__cls.value += e.value; window.__cls.shifts.push({ t: Math.round(e.startTime), v: +e.value.toFixed(4), n: (e.sources || []).map((s) => { const n = s.node; return n ? (n.nodeName + "." + (n.className?.toString?.() || "")).slice(0, 60) : "?"; }).slice(0, 3) }); } }).observe({ type: "layout-shift", buffered: true });
    let last = 0; setInterval(() => { const y = scrollY; if (Math.abs(y - last) > 2) window.__cls.jumps.push({ t: Math.round(performance.now()), from: last, to: y }); last = y; }, 100);
  });
  if (auth) { await page.goto(`${BASE}/#/login`); await page.fill('input[autocomplete="username"]', USER); await page.fill("input[type=password]", PASS); await page.click("button[type=submit]"); await page.waitForSelector("main.content"); }
  if (SLOW) { const c = await ctx.newCDPSession(page); await c.send("Network.enable"); await c.send("Network.emulateNetworkConditions", { offline: false, latency: 400, downloadThroughput: 190000, uploadThroughput: 190000 }); await c.send("Emulation.setCPUThrottlingRate", { rate: 4 }); await c.send("Network.setCacheDisabled", { cacheDisabled: true }); }
  await page.goto(`${BASE}/#${path}`); await page.reload(); await page.waitForTimeout(SLOW ? 4000 : 1500); // fresh document at the screen under test
  const firstShifts = await page.evaluate(() => JSON.stringify(window.__cls.shifts));
  const first = await page.evaluate(() => { const v = window.__cls.value; window.__cls.value = 0; window.__cls.shifts = []; window.__cls.jumps = []; return v; }); // load phase vs steady state
  await page.waitForTimeout(SECONDS * 1000);
  const r = await page.evaluate(() => window.__cls);
  results.push({ name, load: +first.toFixed(4), loadShifts: JSON.parse(firstShifts), steady: +r.value.toFixed(4), shifts: r.shifts, jumps: r.jumps });
  await ctx.close();
}
for (const s of SCREENS) if (!ONLY.length || ONLY.includes(s[0])) await one(s);
await browser.close();
let bad = 0;
for (const r of results) { const flag = r.steady > 0 || r.jumps.length ? "  <-- UNSTABLE" : ""; if (flag) bad++; if (process.argv.includes("--verbose")) console.log("   load shifts:", JSON.stringify(r.loadShifts));
  console.log(`${r.name.padEnd(13)} load-CLS ${r.load.toFixed(3)}  steady-${SECONDS}s CLS ${r.steady.toFixed(3)}  jumps ${r.jumps.length}${flag}`); if (flag) console.log("   ", JSON.stringify(r.shifts.slice(0, 5)), JSON.stringify(r.jumps.slice(0, 3))); }
console.log(bad ? `${bad} unstable screen(s)` : "CLS 0.00 on all screens");
process.exit(bad ? 1 : 0);
