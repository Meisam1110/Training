// Screenshots of every screen (light+dark, 1280 and 360) against the MOCK build.
// Usage: VITE_MOCK=1 npm run build && node scripts/screenshots.mjs
import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";

const PORT = 4173, base = `http://localhost:${PORT}/#`;
const srv = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
mkdirSync("screenshots", { recursive: true });
const screens = [["login", "/login", null], ["dashboard", "/", "admin"], ["runs", "/runs", "admin"], ["run-detail", "/runs/4", "admin"], ["run-detail-settlement", "/runs/6", "admin"],
  ["candidates", "/runs/3/candidates", "admin"], ["enrollments", "/enrollments", "admin"], ["letters", "/letters?kind=settlement_letter&run=3", "admin"], ["employees", "/employees", "admin"],
  ["connectors", "/connectors", "admin"], ["automation", "/automation", "admin"], ["import-export", "/import-export", "admin"], ["admin", "/admin", "admin"]];
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const problems = [];
try {
  for (const scheme of ["light", "dark"]) for (const [w, h] of [[1280, 900], [360, 780]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: "fa-IR", deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const external = []; page.on("request", (r) => { if (!r.url().startsWith(`http://localhost:${PORT}`) && !r.url().startsWith("data:") && !r.url().startsWith("blob:")) external.push(r.url()); });
    page.on("pageerror", (e) => problems.push(`pageerror ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") problems.push(`console ${m.text()}`); });
    let loggedIn = false;
    for (const [name, path, role] of screens) {
      if (role && !loggedIn) {
        await page.goto(`${base}/login`); await page.fill('input[autocomplete="username"]', role); await page.fill('input[type=password]', "demo");
        await page.click('button[type=submit]'); await page.waitForSelector("main.content"); loggedIn = true;
      }
      await page.goto(`${base}${path}`); await page.waitForTimeout(1400);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      if (overflow) problems.push(`H-OVERFLOW ${name} ${scheme} ${w}`);
      await page.screenshot({ path: `screenshots/${name}-${scheme}-${w}.png`, fullPage: false });
    }
    if (external.length) problems.push(`EXTERNAL REQUESTS ${external.join(",")}`);
    await ctx.close();
  }
} finally { await browser.close(); srv.kill(); }
console.log(problems.length ? problems.join("\n") : "no overflow/console problems");
