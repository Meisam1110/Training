// Interaction screenshots: dialogs, date picker, drawer, undo toast. Needs `vite preview` build (mock).
import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
const PORT = 4175, base = `http://localhost:${PORT}/#`;
const srv = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const log = [];
try {
  for (const [w, h, scheme] of [[1280, 900, "light"], [360, 780, "dark"]]) {
    const p = await (await b.newContext({ viewport: { width: w, height: h }, colorScheme: scheme })).newPage();
    p.on("pageerror", (e) => log.push("pageerror " + e.message));
    await p.goto(`${base}/login`); await p.fill('input[autocomplete="username"]', "admin"); await p.fill('input[type=password]', "demo"); await p.click('button[type=submit]');
    await p.waitForSelector("main.content");
    await p.goto(`${base}/runs/3`); await p.waitForTimeout(1200);
    await p.click(".step:nth-child(3) .step__btn"); await p.click("text=ارسال ایمیل اطلاعیه…"); await p.waitForSelector('[role=dialog]'); await p.waitForTimeout(600);
    await p.screenshot({ path: `screenshots/flow-email-compose-${scheme}-${w}.png` });
    await p.click("text=ادامه و بازبینی"); await p.waitForTimeout(200);
    await p.screenshot({ path: `screenshots/flow-email-confirm-${scheme}-${w}.png` });
    await p.click("[role=dialog] .dialog__foot .btn >> nth=0"); await p.waitForSelector('[data-testid=send-results]'); await p.waitForTimeout(200);
    await p.screenshot({ path: `screenshots/flow-email-result-${scheme}-${w}.png` });
    await p.keyboard.press("Escape");
    await p.goto(`${base}/runs/1`); await p.waitForTimeout(1200);
    await p.click(".step:nth-child(1) .step__btn"); await p.click('button[aria-label^="انتخاب تاریخ از تقویم: شروع"]'); await p.waitForTimeout(300);
    await p.screenshot({ path: `screenshots/flow-datepicker-${scheme}-${w}.png` });
    await p.goto(`${base}/enrollments`); await p.waitForTimeout(1200);
    await p.selectOption('select[aria-label^="موتیویشن"] >> nth=0', "no"); await p.waitForTimeout(700);
    await p.screenshot({ path: `screenshots/flow-undo-toast-${scheme}-${w}.png` });
    const undo = p.locator("text=برگردان").first(); log.push(`undo visible ${w}: ${await undo.isVisible()}`);
    if (w === 360) { await p.click('button[aria-label="باز کردن منو"]'); await p.waitForTimeout(400); await p.screenshot({ path: `screenshots/flow-drawer-${scheme}-${w}.png` }); }
    await p.goto(`${base}/employees`); await p.waitForTimeout(1200);
    await p.click("text=جزئیات >> nth=0"); await p.click("text=نمایش اطلاعات"); await p.waitForTimeout(300);
    await p.screenshot({ path: `screenshots/flow-reveal-warning-${scheme}-${w}.png` });
  }
} finally { await b.close(); srv.kill(); }
console.log(log.join("\n") || "flows ok");
