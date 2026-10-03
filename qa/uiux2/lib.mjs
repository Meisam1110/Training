// shared helpers for the uiux2 review. Run with NODE_PATH=/tmp/uiux2/node_modules
import { createRequire } from "module";
const require = createRequire("/tmp/uiux2/");
export const { chromium } = require("playwright-core");
export const axeSrc = require("fs").readFileSync("/tmp/uiux2/node_modules/axe-core/axe.min.js", "utf8");
export const TARGETS = {
  mock: { url: "http://localhost:5191", users: { admin: ["admin", "demo"], hr: ["hr", "demo"], viewer: ["viewer", "demo"] } },
  live: { url: "http://localhost:5192", users: { admin: ["demo_admin", "Rl86z8jqXqkoXe1J-Aa1"], hr: ["demo_hr", "Rl86z8jqXqkoXe1J-Aa1"], viewer: ["demo_viewer", "Rl86z8jqXqkoXe1J-Aa1"] } },
};
TARGETS.liveprod = { ...TARGETS.live, url: "http://localhost:18792" };
TARGETS.mockprod = { ...TARGETS.mock, url: "http://localhost:5193" };
export async function launch() {
  return chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args: ["--no-sandbox"] });
}
export async function login(page, target, role) {
  const t = TARGETS[target]; const [u, p] = t.users[role];
  await page.goto(t.url + "/#/login");
  await page.waitForSelector("input");
  const inputs = await page.$$("input");
  await inputs[0].fill(u); await page.fill('input[type="password"]', p);
  await page.keyboard.press("Enter");
  await page.waitForSelector("main#main", { timeout: 15000 });
}
export const ROUTES = ["/", "/runs", "/runs/1", "/runs/1/candidates", "/enrollments", "/letters", "/employees", "/connectors", "/automation", "/import-export", "/admin"];
