import { createRequire } from "node:module";
const require = createRequire("/home/user/training/frontend/");
export const { chromium } = require("playwright-core");
export const AXE = "/tmp/claude-0/-home-user-Salary/336d2072-f701-5866-914d-4be7e75e596c/scratchpad/axe/node_modules/axe-core/axe.min.js";
export const BASE = "http://127.0.0.1:5199/#";
export const OUT = "/home/user/training/qa/uiux";
export const launch = () => chromium.launch({ executablePath: "/opt/pw-browsers/chromium/chrome-linux/chrome", args: ["--no-sandbox"] }).catch(() => chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] }));
export async function login(page, role) {
  await page.goto(`${BASE}/login`);
  await page.fill('input[autocomplete="username"]', role); await page.fill('input[type=password]', "demo");
  await page.click('button[type=submit]'); await page.waitForSelector("main.content");
}
