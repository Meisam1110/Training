import { launch, login, BASE, OUT } from "./lib.mjs";
import fs from "node:fs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:800}, locale:"fa-IR" });
await ctx.route("**/src/api/mock/seed.ts*", async r => {
  const resp = await r.fetch(); let t = await resp.text();
  t = t.replace("employees.length < 84","employees.length < 3000").replace("if (used.has(key)) continue;","")
       .replace("name_fa: `${fa} ${lfa}`","name_fa: (i%40===0 ? `${fa} ${lfa} ${lfa}${lfa}${lfa} بین‌المللی‌ترین نماینده‌ی هماهنگ‌کننده‌ی توسعه‌ی استعداد` : `${fa} ${lfa}`)")
       .replace("k < 8; k++","k < 700; k++");
  await r.fulfill({ response: resp, body: t });
});
const p = await ctx.newPage(); p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
let t=Date.now();
await p.goto(`${BASE}/employees`); await p.waitForSelector("tbody tr"); await p.waitForTimeout(800);
console.log("employees total text:", (await p.innerText(".pager")).replace(/\n/g," "), "load ms", Date.now()-t);
await p.screenshot({path:`${OUT}/s-employees-3000.png`});
t=Date.now();
await p.goto(`${BASE}/runs/3/candidates`); await p.waitForSelector("tbody tr"); await p.waitForTimeout(1500);
console.log("cand rows in DOM", await p.$$eval("tbody tr",r=>r.length), "load", Date.now()-t);
console.log("selected txt", (await p.innerText(".pager")).replace(/\n/g," "));
await p.screenshot({path:`${OUT}/s-cand-700.png`});
// select all
t=Date.now(); await p.click('thead input[type=checkbox]'); await p.waitForTimeout(300);
console.log("select-all ms", Date.now()-t, (await p.innerText(".pager")).replace(/\n/g," "));
// scroll table
await p.evaluate(()=>{const s=document.querySelector(".table-wrap"); s.scrollTop=s.scrollHeight/2;}); await p.waitForTimeout(400);
await p.screenshot({path:`${OUT}/s-cand-700-scrolled.png`});
// keyboard: is table-wrap focusable, can Space toggle rows?
// long name on runs enrollments page
await p.goto(`${BASE}/enrollments`); await p.waitForTimeout(1200);
await p.screenshot({path:`${OUT}/s-enroll.png`});
await p.goto(`${BASE}/employees?q=بین‌المللی`); await p.waitForTimeout(500);
await p.fill('input[type=search]',"بین‌المللی"); await p.waitForTimeout(900);
await p.screenshot({path:`${OUT}/s-longname-employees.png`});
console.log("overflow", await p.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.clientWidth]));
await p.setViewportSize({width:360,height:780}); await p.waitForTimeout(400);
await p.screenshot({path:`${OUT}/s-longname-employees-360.png`});
await p.fill('input[type=search]',"zzzz"); await p.waitForTimeout(900);
await p.screenshot({path:`${OUT}/s-empty-employees-360.png`});
await b.close();
