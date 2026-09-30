// Screenshots against the REAL backend (vite preview proxies /api -> :8000). Non-mock build required.
// TMS_LIVE_USER / TMS_LIVE_PASS from env. Usage: npm run build && node scripts/screenshots-live.mjs
import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
const PORT = 4180, base = `http://localhost:${PORT}/#`;
const user = process.env.TMS_LIVE_USER ?? "demo_admin", pass = process.env.TMS_LIVE_PASS;
const srv = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
mkdirSync("screenshots/live", { recursive: true });
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const problems = [];
try {
  for (const [w, h] of [[1280, 900], [360, 780]]) {
    const p = await (await b.newContext({ viewport: { width: w, height: h }, locale: "fa-IR" })).newPage();
    p.on("pageerror", (e) => problems.push(`pageerror ${e.message}`));
    p.on("console", (m) => { if (m.type() === "error") problems.push(`console(${w}) ${m.text()}`); });
    p.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400 && r.status() !== 401) problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`); });
    await p.goto(`${base}/login`); await p.fill('input[autocomplete="username"]', user); await p.fill('input[type=password]', pass); await p.click("button[type=submit]");
    await p.waitForSelector("main.content", { timeout: 8000 }).catch(async () => { console.log("login failed at", w, (await p.evaluate(() => document.body.innerText)).slice(0, 200)); throw new Error("login"); });
    for (const [name, path] of [["dashboard", "/"], ["runs", "/runs"], ["run-detail", "/runs/6"], ["candidates", "/runs/6/candidates"], ["enrollments", "/enrollments"], ["letters", "/letters"], ["employees", "/employees"], ["connectors", "/connectors"], ["automation", "/automation"], ["import-export", "/import-export"], ["admin", "/admin"]]) {
      await p.goto(`${base}${path}`); await p.waitForTimeout(1500);
      if (await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) problems.push(`H-OVERFLOW ${name} ${w}`);
      await p.screenshot({ path: `screenshots/live/${name}-${w}.png` });
    }
    // e-mail dialog on a real letter (created by the live test): shows subject, attachment, recipients, already-sent chips
    await p.goto(`${base}/letters`); await p.waitForSelector("tbody tr", { timeout: 8000 }).catch(() => {});
    const mailBtn = p.locator('button:has-text("ایمیل")').first();
    if (await mailBtn.count()) { await mailBtn.click(); await p.waitForSelector('[data-testid=mail-summary]', { timeout: 8000 }).catch(() => {}); await p.waitForTimeout(800); await p.screenshot({ path: `screenshots/live/email-dialog-${w}.png` }); await p.keyboard.press("Escape"); }
  }
} finally { await b.close(); srv.kill(); }
console.log(problems.length ? problems.join("\n") : "live: no console errors / HTTP errors / overflow");
