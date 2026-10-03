// Digit law audit: display numbers/dates are Persian digits; identifiers (.id: employee no., ticket, letter no., email, path)
// are Latin LTR islands. Reports Latin digits in prose and Persian digits inside identifiers on every screen.
// Usage: node scripts/digits-audit.mjs --url http://localhost:4190 --user admin --pass demo
import { chromium } from "playwright-core";
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const BASE = arg("url", "http://localhost:4190"), USER = arg("user", "admin"), PASS = arg("pass", "demo");
const SCREENS = ["/", "/runs", "/courses", "/runs/3", "/runs/6", "/runs/3/candidates", "/courses", "/enrollments", "/letters?kind=settlement_letter&run=6", "/employees", "/connectors", "/automation", "/import-export", "/admin"];
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox"] });
const p = await (await b.newContext({ viewport: { width: 1280, height: 900 }, locale: "fa-IR" })).newPage();
await p.goto(`${BASE}/#/login`); await p.fill('input[autocomplete="username"]', USER); await p.fill("input[type=password]", PASS); await p.click("button[type=submit]"); await p.waitForSelector("main.content");
const bad = [];
for (const s of SCREENS) {
  await p.goto(`${BASE}/#${s}`); await p.waitForTimeout(1500);
  const r = await p.evaluate(() => {
    const out = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      const n = w.currentNode; const t = (n.textContent ?? "").replace(/\u2068[^\u2069]*\u2069/g, ""); /* bidi-isolated runs are identifiers */ const el = n.parentElement; if (!el || !t.trim() || el.closest("script,style,.sr-only,.preview,option")) continue;
      const ident = el.closest(".id, code, .ltr");
      if (!ident && /[0-9]/.test(t)) out.push({ kind: "latin-digit-in-prose", text: t.trim().slice(0, 60), where: el.tagName + "." + (el.className || "") });
      if (ident && /[۰-۹٠-٩]/.test(t)) out.push({ kind: "persian-digit-in-identifier", text: t.trim().slice(0, 60), where: el.tagName + "." + (el.className || "") });
    }
    document.querySelectorAll("input:not([type=checkbox]):not([type=file]),textarea").forEach((i) => { const v = i.value; if (/[0-9]/.test(v) && !i.closest(".dp") && i.getAttribute("dir") !== "ltr" && !i.dataset.ident) out.push({ kind: "latin-digit-in-field", text: v.slice(0, 40), where: "input[" + (i.getAttribute("aria-label") || i.id) + "]" }); });
    return out;
  });
  for (const x of r) bad.push({ screen: s, ...x });
}
await b.close();
const uniq = new Map(bad.map((x) => [`${x.screen}|${x.kind}|${x.text}`, x]));
for (const x of uniq.values()) console.log(`${x.screen}  ${x.kind}  "${x.text}"  <${x.where}>`);
console.log(uniq.size ? `${uniq.size} violation(s)` : "digit law: 0 violations");
process.exit(uniq.size ? 1 : 0);
