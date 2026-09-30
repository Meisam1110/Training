import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
const p = await ctx.newPage(); p.setDefaultTimeout(3000); p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
await p.goto(`${BASE}/runs/6`); await p.waitForTimeout(800);
await p.click('.step:nth-child(6) .step__btn'); await p.waitForTimeout(300);
const amt = p.locator('section.card input[dir=ltr]').first();
for (const c of ["260,000,000","260,000,000 ریال","260٫5","-5","1.5"]) {

  await p.waitForTimeout(4500); await amt.fill(c); await p.click('button:has-text("ذخیرهٔ مبلغ")'); await p.waitForTimeout(700);
  const errs = await p.$$eval('section.card .field__error',e=>e.map(x=>x.innerText));
  const toast = await p.$$eval('.toasts .toast',e=>e.map(x=>x.innerText.replace(/\n/g," ")));
  const hint = await p.$$eval('section.card .field__hint',e=>e.map(x=>x.innerText));
  console.log(JSON.stringify(c),"errs",errs,"toasts",toast,"hint",hint);
  if (c==="260,000,000") await p.screenshot({path:`${OUT}/amount-hint-dash.png`,clip:{x:0,y:250,width:1000,height:450}});
}
await b.close();
