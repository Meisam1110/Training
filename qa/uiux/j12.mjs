import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
const p = await ctx.newPage(); p.setDefaultTimeout(3000); p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
const dlg=async(n)=>{ console.log(n,"=>",(await p.innerText('[role=dialog]')).replace(/\n+/g," | ").slice(0,400)); await p.screenshot({path:`${OUT}/dlg-${n}.png`}); };
// automation
await p.goto(`${BASE}/automation`); await p.waitForTimeout(900);
await p.click('button:has-text("اجرای همین حالا")'); await p.waitForTimeout(400); await dlg("automation"); await p.keyboard.press("Escape");
await p.screenshot({path:`${OUT}/automation-full.png`,fullPage:true});
// export
await p.goto(`${BASE}/import-export`); await p.waitForTimeout(900);
await p.click('button:has-text("برون‌بری اکسل قدیمی")'); await p.waitForTimeout(400); await dlg("export"); await p.keyboard.press("Escape");
// import bad file
await p.setInputFiles('input[type=file] >> nth=0',{name:"bad-idp.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer:Buffer.from("x")});
await p.waitForTimeout(300);
await p.click('button:has-text("شروع درون‌ریزی") >> nth=0'); await p.waitForTimeout(1500);
await p.screenshot({path:`${OUT}/import-bad.png`,fullPage:true});
console.log("import bad:", (await p.innerText("main")).replace(/\n+/g," | ").slice(0,500));
await p.setInputFiles('input[type=file] >> nth=0',{name:"idp.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer:Buffer.from("x")});
await p.click('button:has-text("شروع درون‌ریزی") >> nth=0'); await p.waitForTimeout(1500);
await p.screenshot({path:`${OUT}/import-ok.png`,fullPage:true});
console.log("import ok:", (await p.innerText("main")).replace(/\n+/g," | ").slice(0,700));
// PII reveal
await p.goto(`${BASE}/employees`); await p.waitForTimeout(900);
await p.click('button:has-text("جزئیات") >> nth=0'); await p.waitForTimeout(500);
await p.screenshot({path:`${OUT}/employee-detail.png`});
console.log("emp detail:", (await p.innerText("main")).replace(/\n+/g," | ").slice(0,300), await p.locator('[role=dialog]').count());
// enrollments: how many controls to mark 5 motivations
await p.goto(`${BASE}/enrollments?run=4`); await p.waitForTimeout(900);
console.log("checkboxes in enrollments:", await p.locator('tbody input[type=checkbox]').count(), "bulk buttons:", await p.locator('button:has-text("همه")').count());
await p.screenshot({path:`${OUT}/enrollments-motivation.png`});
await b.close();
