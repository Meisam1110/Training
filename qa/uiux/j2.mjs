import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
const p = await ctx.newPage(); let clicks=0;
const reqs=[]; 
p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
for (const id of [3]) {
  await p.goto(`${BASE}/runs/${id}`); await p.waitForTimeout(800);
  await p.click('.step:nth-child(3) .step__btn'); await p.waitForTimeout(400);
  console.log(id, (await p.innerText("section#step-h, section[aria-labelledby=step-h]")).replace(/\n+/g," | "));
}
// run 4 announce: try send
await p.goto(`${BASE}/runs/3`); await p.waitForTimeout(800);
await p.click('.step:nth-child(3) .step__btn');
const btn = p.locator('button:has-text("ارسال ایمیل اطلاعیه")');
console.log("send btn count", await btn.count());
if (await btn.count()) {
  await btn.click(); clicks++; await p.waitForSelector('[role=dialog]'); await p.waitForTimeout(600);
  await p.screenshot({path:`${OUT}/j2-send-compose.png`});
  console.log("dry checked", await p.isChecked('[data-testid=dry-run]'));
  console.log((await p.innerText('[role=dialog]')).replace(/\n+/g," | ").slice(0,600));
  await p.click('[data-testid=dry-run]',{force:true}); clicks++;
  await p.click('button:has-text("ادامه و بازبینی")'); clicks++;
  await p.screenshot({path:`${OUT}/j2-send-confirm.png`});
  // dry run
  await p.click('button:has-text("اجرای آزمایشی برای")'); clicks++;
  await p.waitForSelector('[data-testid=send-results]'); 
  await p.screenshot({path:`${OUT}/j2-send-dryresult.png`});
  console.log((await p.innerText('[role=dialog]')).replace(/\n+/g," | ").slice(0,500));
  await p.click('[role=dialog] button:has-text("بستن")'); clicks++;
  // real
  await p.click('button:has-text("ارسال ایمیل اطلاعیه")'); clicks++; await p.waitForTimeout(600);
  console.log("dry default after dry-run", await p.isChecked('[data-testid=dry-run]'));
  if (await p.isChecked('[data-testid=dry-run]')) { await p.click('[data-testid=dry-run]',{force:true}); clicks++; }
  await p.screenshot({path:`${OUT}/j2-send-real-compose.png`});
  await p.click('button:has-text("ادامه و بازبینی")'); clicks++;
  await p.screenshot({path:`${OUT}/j2-send-real-confirm.png`});
  // double click send
  let posts=0; 
  const real = p.locator('button:has-text("ارسال واقعی به")');
  await real.dblclick(); 
  await p.waitForSelector('[data-testid=send-results]');
  console.log("after real send:", (await p.innerText('[role=dialog]')).replace(/\n+/g," | ").slice(0,300));
  await p.screenshot({path:`${OUT}/j2-send-realresult.png`});
  await p.click('[role=dialog] button:has-text("بستن")');
  // messages count via /messages? go check back
  await p.goBack(); await p.waitForTimeout(600); console.log("after back", p.url());
  await p.goForward(); await p.waitForTimeout(600);
  console.log("clicks", clicks);
}
await b.close();
