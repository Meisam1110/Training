// Full sweep: role x width x theme x route. node audit.mjs <target> <role> [widths] [themes] > out.json
import fs from "fs";
import { launch, login, axeSrc, ROUTES } from "./lib.mjs";
const [target = "mockprod", role = "admin", widthsArg = "1440,1024,768,390", themesArg = "light,dark"] = process.argv.slice(2);
const routes = [...ROUTES, "/nonexistent", "/runs?status=planned"];
const b = await launch(); const results = [];
for (const theme of themesArg.split(",")) for (const w of widthsArg.split(",").map(Number)) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 }, locale: "fa-IR", colorScheme: theme, bypassCSP: true });
  await ctx.addInitScript(t => { try { localStorage.setItem("tms.theme", t); } catch {} }, theme);
  const page = await ctx.newPage(); const errs = [], bad = [];
  page.on("pageerror", e => errs.push(String(e).slice(0, 150)));
  page.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text().slice(0, 150)); });
  page.on("response", r => { if (r.status() >= 400 && r.url().includes("/api/")) bad.push(r.status() + " " + r.url().replace(/^https?:\/\/[^/]+/, "")); });
  await login(page, target, role);
  for (const r of routes) {
    errs.length = 0; bad.length = 0;
    await page.evaluate(h => { location.hash = h; }, r);
    await page.waitForTimeout(1400);
    await page.addScriptTag({ content: axeSrc }).catch(() => {});
    const m = await page.evaluate(async () => {
      const out = {};
      out.title = document.title; out.h1 = document.querySelector("h1")?.textContent || null;
      out.overflowX = document.documentElement.scrollWidth > document.documentElement.clientWidth;
      out.bodyText = document.body.innerText.length;
      const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
      // digit law: Latin digits in text nodes not inside ltr/id/code/input
      const bad = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (w.nextNode()) { const n = w.currentNode; const t = n.textContent; if (!/[0-9]/.test(t)) continue; const p = n.parentElement; if (!p || !vis(p)) continue; if (p.closest(".id,.ltr,code,[dir=ltr],.mono,script,style,.sr-only")) continue; bad.push(t.trim().slice(0, 50)); }
      out.latinDigitText = bad.slice(0, 8); out.latinDigitCount = bad.length;
      out.latinDigitAttrs = [...document.querySelectorAll("[aria-label],[title],[placeholder]")].filter(e => vis(e) && !e.closest(".id,.ltr,[dir=ltr]")).map(e => e.getAttribute("aria-label") || e.getAttribute("title") || e.getAttribute("placeholder")).filter(s => s && /[0-9]/.test(s)).slice(0, 5);
      out.gregorian = (document.body.innerText.match(/\b(19|20)\d\d[\/-]\d\d[\/-]\d\d\b/g) || []).slice(0, 3);
      out.persianTerm = (document.body.innerText.match(/انگیزه‌?\s?نامه/g) || []).length;
      out.primaryBtns = [...document.querySelectorAll(".btn--primary")].filter(vis).map(b => b.textContent.trim());
      // targets
      const small = []; for (const e of document.querySelectorAll("a[href],button,input:not([type=hidden]),select,textarea,[role=button],[tabindex='0']")) { if (!vis(e)) continue; if (e.closest(".sr-only,.skip-link")) continue; const r = e.getBoundingClientRect(); if (e.matches("a") && e.closest("p,li,td,.muted") && !e.matches(".btn")) { if (r.height < 24) small.push(["inline<24", e.textContent.trim().slice(0, 20), Math.round(r.width) + "x" + Math.round(r.height)]); continue; } if (r.height < 24 || r.width < 24) small.push(["<24", (e.getAttribute("aria-label") || e.textContent).trim().slice(0, 20), Math.round(r.width) + "x" + Math.round(r.height)]); else if (innerWidth <= 768 && (r.height < 44 || r.width < 44) && !e.matches("input[type=checkbox],input[type=radio]")) small.push(["<44", (e.getAttribute("aria-label") || e.textContent).trim().slice(0, 20), Math.round(r.width) + "x" + Math.round(r.height)]); }
      out.smallTargets = small.slice(0, 8); out.smallCount = small.length;
      out.unnamed = [...document.querySelectorAll("button,a[href],select,input:not([type=hidden]),textarea")].filter(e => vis(e) && !(e.getAttribute("aria-label") || e.getAttribute("aria-labelledby") || e.textContent.trim() || (e.labels && e.labels.length) || e.title)).map(e => e.outerHTML.slice(0, 80)).slice(0, 4);
      const main = document.querySelector("main"); const nav = document.querySelector(".sidebar");
      out.mainTop = main ? Math.round(main.getBoundingClientRect().top) : null;
      try { out.axe = (await axe.run(document, { resultTypes: ["violations"] })).violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes[0].target.join(" ").slice(0, 80) })); } catch (e) { out.axe = [{ id: "axe-error", n: 0, sample: String(e).slice(0, 80) }]; }
      return out;
    });
    const rec = { theme, w, route: r, role, errs: [...errs], bad: [...bad], ...m }; results.push(rec); fs.appendFileSync(`audit-${target}-${role}.jsonl`, JSON.stringify(rec) + "\n");
  }
  await ctx.close();
}
console.log("done", results.length);
await b.close();
