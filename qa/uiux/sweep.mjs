import { launch, login, BASE, OUT, AXE } from "./lib.mjs";
import fs from "node:fs";
const axeSrc = fs.readFileSync(AXE, "utf8");
const screens = [["dashboard","/"],["runs","/runs"],["run-detail","/runs/4"],["run-settlement","/runs/6"],["candidates","/runs/3/candidates"],["enrollments","/enrollments"],["letters","/letters?kind=settlement_letter&run=3"],["employees","/employees"],["connectors","/connectors"],["automation","/automation"],["import-export","/import-export"],["admin","/admin"]];
const widths = [[1440,900],[1280,800],[768,900],[360,780]];
const browser = await launch();
const res = { axe: {}, overflow: [], errors: [], small: {} };
fs.mkdirSync(`${OUT}/sweep`, { recursive: true });
for (const scheme of ["light","dark"]) for (const [w,h] of widths) {
  const ctx = await browser.newContext({ viewport:{width:w,height:h}, colorScheme:scheme, locale:"fa-IR" });
  const page = await ctx.newPage();
  page.on("pageerror", e=>res.errors.push(`pageerror ${scheme}${w}: ${e.message}`));
  page.on("console", m=>{ if(m.type()==="error"||m.type()==="warning") res.errors.push(`console.${m.type()} ${scheme}${w}: ${m.text().slice(0,200)}`); });
  page.on("response", r=>{ if(r.status()>=400) res.errors.push(`HTTP ${r.status()} ${r.url()}`); });
  // login screen
  await page.goto(`${BASE}/login`); await page.waitForTimeout(500);
  await page.screenshot({ path:`${OUT}/sweep/login-${scheme}-${w}.png` });
  await login(page,"admin");
  for (const [name,path] of screens) {
    await page.goto(`${BASE}${path}`); await page.waitForTimeout(1300);
    const ov = await page.evaluate(()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth}));
    if (ov.sw>ov.cw+1) res.overflow.push(`${name} ${scheme} ${w}: ${ov.sw}>${ov.cw}`);
    await page.screenshot({ path:`${OUT}/sweep/${name}-${scheme}-${w}.png` });
    if (w===1280||w===360) {
      await page.addScriptTag({ content: axeSrc });
      const r = await page.evaluate(async()=>{ const a = await axe.run(document,{resultTypes:["violations"]}); return a.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,help:v.help,ex:v.nodes.slice(0,3).map(n=>n.target.join(" ")+" :: "+(n.failureSummary||"").split("\n").slice(0,2).join("|").slice(0,220))})); });
      res.axe[`${name} ${scheme} ${w}`] = r;
      const small = await page.evaluate(()=>{ const out=[]; document.querySelectorAll("a[href],button,input,select,textarea,[role=button],summary").forEach(el=>{ const b=el.getBoundingClientRect(); const cs=getComputedStyle(el); if(b.width===0||b.height===0||cs.visibility==="hidden") return; if(el.classList.contains("sr-only")||el.closest(".skip-link")) return; if(b.height<43.5||b.width<43.5) out.push((el.tagName+"."+(el.className||"")).slice(0,50)+" "+Math.round(b.width)+"x"+Math.round(b.height)+" '"+(el.getAttribute("aria-label")||el.textContent||"").trim().slice(0,25)+"'"); }); return out; });
      res.small[`${name} ${scheme} ${w}`]=small;
    }
  }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(`${OUT}/sweep-results.json`, JSON.stringify(res,null,1));
console.log("errors",[...new Set(res.errors)].slice(0,20)); console.log("overflow",res.overflow);
const agg={}; for(const [k,v] of Object.entries(res.axe)) for(const x of v){ (agg[x.id] ??= {impact:x.impact,help:x.help,where:new Set(),ex:x.ex[0]}).where.add(k.split(" ")[0]); }
for(const [id,x] of Object.entries(agg)) console.log(id,x.impact,x.help,[...x.where].join(","),"\n   ",x.ex);
