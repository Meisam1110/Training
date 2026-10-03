import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
const p = await ctx.newPage(); p.setDefaultTimeout(4000); p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
await p.goto(`${BASE}/runs/6`); await p.waitForTimeout(800);
await p.click('.step:nth-child(1) .step__btn');
const dates = p.locator('section.card input[inputmode=numeric]');
const start = dates.nth(0);
const cases = ["1405/12/29","1405/12/30","1403/12/30","1404/12/30","1405/6/31","1405/7/31","1405/13/1","1405/0/5","۱۴۰۵/۰۷/۰۸","1405-7-8","14050708","2026/10/01","05/07/08","1405/07/08 ","۱۴۰۵٫۰۷٫۰۸","1405/07/00","0001/01/01","9999/01/01","abc"];
for (const c of cases) {
  await start.fill(c); await p.keyboard.press("Tab"); await p.waitForTimeout(120);
  const val = await start.inputValue();
  const err = await p.locator('section.card .field__error').first().innerText().catch(()=>"");
  console.log(JSON.stringify(c),"=>",JSON.stringify(val), err? "ERR:"+err.replace(/\n/g," "):"");
  await p.screenshot({path:`${OUT}/dp-tmp.png`}).catch(()=>{});
}
// calendar popup: open for a 1405/12 date, page through
await start.fill("1405/12/29"); await p.keyboard.press("Tab");
await p.click('button[aria-label^="انتخاب تاریخ از تقویم: شروع"]'); await p.waitForTimeout(300);
await p.screenshot({path:`${OUT}/dp-open-esfand.png`});
console.log("focused day:", await p.evaluate(()=>document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("ArrowDown"); await p.keyboard.press("ArrowDown"); await p.waitForTimeout(200);
console.log("after 2x down:", await p.evaluate(()=>document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("PageDown"); await p.waitForTimeout(200);
console.log("PageDown:", await p.evaluate(()=>document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("Enter"); await p.waitForTimeout(200);
console.log("picked value:", await start.inputValue(), "focus->", await p.evaluate(()=>document.activeElement?.getAttribute("aria-label")));
// tab order / focus inside popup: Tab from grid goes where?
await p.click('button[aria-label^="انتخاب تاریخ از تقویم: شروع"]'); await p.waitForTimeout(200);
await p.keyboard.press("Tab"); console.log("tab1:", await p.evaluate(()=>document.activeElement?.textContent||document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("Tab"); console.log("tab2:", await p.evaluate(()=>document.activeElement?.textContent||document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("Tab"); console.log("tab3:", await p.evaluate(()=>document.activeElement?.textContent||document.activeElement?.getAttribute("aria-label")));
await p.keyboard.press("Escape");
// amount
await p.click('.step:nth-child(6) .step__btn'); await p.waitForTimeout(300);
const amt = p.locator('section.card input[dir=ltr]').first();
for (const c of ["260000000","260,000,000","۲۶۰٬۰۰۰٬۰۰۰","260 000 000","260 000 000","260٫000٫000","1.5","260,000,000 ریال","٢٦٠٠٠٠٠٠٠","-5","1e9","0"]) {
  await amt.fill(c); await p.waitForTimeout(80);
  const hint = await p.locator('section.card .field__hint').last().innerText().catch(()=>"");
  await p.click('button:has-text("ذخیرهٔ مبلغ")'); await p.waitForTimeout(250);
  const err = await p.locator('section.card .field__error').first().innerText().catch(()=>"");
  const toast = await p.innerText('.toasts').catch(()=>"");
  console.log(JSON.stringify(c),"shown",JSON.stringify(await amt.inputValue()),"hint",hint.replace(/\n/g," "),"| err",err,"| toast",toast.replace(/\n/g," ").slice(0,60));
}
await b.close();
