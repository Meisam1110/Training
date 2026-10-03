import { launch, login } from "./lib.mjs";
const b = await launch(); const page = await (await b.newContext({ viewport: { width: 390, height: 844 } })).newPage(); await login(page, "mockprod", "admin");
await page.evaluate(() => { location.hash = "/enrollments"; }); await page.waitForTimeout(1500);
console.log(await page.evaluate(() => { const i = document.querySelector('tbody input[type=checkbox]'); const l = i.closest("label"); const r = l.getBoundingClientRect(); const c = i.getBoundingClientRect(); return { input: [c.width, c.height], label: [r.width, r.height], labelClass: l.className }; }));
await b.close();
