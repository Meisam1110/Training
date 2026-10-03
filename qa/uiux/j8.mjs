import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:800}, locale:"fa-IR", reducedMotion:"reduce" });
const p = await ctx.newPage(); p.setDefaultTimeout(3000);
await login(p,"admin");
const desc = ()=>p.evaluate(()=>{const e=document.activeElement; if(!e) return "none"; const cs=getComputedStyle(e); const cur=e.closest('.step')?"step":""; return `${e.tagName}.${(e.className||"").toString().slice(0,25)} '${(e.getAttribute("aria-label")||e.innerText||e.value||"").trim().slice(0,28)}' outline=${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor} shadow=${cs.boxShadow.slice(0,40)}`});
// order on /runs from top
await p.goto(`${BASE}/runs`); await p.waitForTimeout(900);
await p.evaluate(()=>document.activeElement.blur());
console.log("h1 focused after nav?", await p.evaluate(()=>document.activeElement?.id));
let n=0; const seq=[];
for (let i=0;i<30;i++){ await p.keyboard.press("Tab"); const d=await desc(); seq.push(d); if(/دورهٔ جدید/.test(d)) {n=i+1;break;} }
console.log("tabs to reach 'دورهٔ جدید' from page start:", n); console.log(seq.slice(0,14).join("\n"));
// after route change focus
await p.goto(`${BASE}/`); await p.waitForTimeout(400);
await p.click('nav a:has-text("دوره‌های آموزشی")'); await p.waitForTimeout(500);
console.log("focus after nav click:", await desc());
// dialog keyboard
await p.focus('text=دورهٔ جدید'); await p.keyboard.press("Enter"); await p.waitForTimeout(300);
console.log("dialog first focus:", await desc());
for(let i=0;i<9;i++){await p.keyboard.press("Tab");}
console.log("after 9 tabs inside dialog:", await desc());
console.log("root inert:", await p.evaluate(()=>document.getElementById("root").hasAttribute("inert")));
await p.keyboard.press("Escape"); await p.waitForTimeout(300);
console.log("after Esc focus:", await desc());
// submit empty -> error focus?
await p.keyboard.press("Enter"); await p.waitForTimeout(300);
await p.click('[role=dialog] button:has-text("ساخت دوره")'); await p.waitForTimeout(300);
console.log("after invalid submit focus:", await desc(), "| alerts:", await p.$$eval('[role=dialog] [role=alert]',e=>e.length));
await p.screenshot({path:`${OUT}/dialog-errors.png`});
await p.keyboard.press("Escape");
// run detail stepper keyboard
await p.goto(`${BASE}/runs/3`); await p.waitForTimeout(800);
await p.evaluate(()=>document.getElementById("main").focus());
const seq2=[]; for(let i=0;i<14;i++){await p.keyboard.press("Tab"); seq2.push(await desc());}
console.log(seq2.join("\n"));
// select via keyboard in enrollments
await b.close();
