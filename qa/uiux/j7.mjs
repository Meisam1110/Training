import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
const p = await ctx.newPage(); p.setDefaultTimeout(3000);
await login(p,"admin");
await p.goto(`${BASE}/letters?kind=course_announcement&run=3`); await p.waitForTimeout(1500);
console.log((await p.innerText('[data-testid=letter-preview]')).replace(/\n+/g," | "));
await p.screenshot({path:`${OUT}/letters-announce.png`});
// letters create flow click count: settlement letter run 6 (has amount)
await p.goto(`${BASE}/runs`); await p.goto(`${BASE}/letters?kind=settlement_letter&run=6`); await p.waitForTimeout(1500);
console.log("run6 settle missing callout:", await p.locator(".callout--warn").count(), (await p.innerText('[data-testid=letter-preview]')).replace(/\n+/g," | "));
await p.screenshot({path:`${OUT}/letters-settle-run6.png`});
console.log("create disabled:", await p.locator('button:has-text("ساخت نامه و شماره‌گذاری")').isDisabled());
await p.locator('section.card input.input').first().fill("INV-1405/۱۲"); await p.waitForTimeout(600);
console.log("create disabled after 1 of N fields:", await p.locator('button:has-text("ساخت نامه و شماره‌گذاری")').isDisabled());
// letter list / preview after fill
await p.screenshot({path:`${OUT}/letters-settle-fill.png`});
await b.close();
