import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
for (const role of ["viewer","hr"]) {
  const ctx = await b.newContext({ viewport:{width:1280,height:800}, locale:"fa-IR" });
  const p = await ctx.newPage(); p.setDefaultTimeout(3000);
  const bad=[]; p.on("response",r=>{ if(r.status()>=400) bad.push(r.status()+" "+r.url()) }); p.on("pageerror",e=>console.log("PAGEERR",e.message));
  await login(p,role);
  console.log("==",role,"nav:", (await p.$$eval("nav a",a=>a.map(x=>x.innerText.trim()))).join(","));
  for (const path of ["/","/runs","/runs/3","/runs/3/candidates","/enrollments","/letters","/employees","/connectors","/automation","/import-export","/admin"]) {
    await p.goto(`${BASE}${path}`); await p.waitForTimeout(1000);
    const h1 = await p.locator("h1").first().innerText().catch(()=>"(no h1)");
    const btns = await p.$$eval("main button.btn--primary, main a.btn--primary",a=>a.map(x=>x.innerText.trim()+(x.disabled?"[disabled]":"")));
    const body = (await p.innerText("main")).replace(/\n+/g," | ").slice(0,160);
    console.log(path,"|",h1,"| primary:",btns.join(";"),"|",body);
    if (role==="viewer") await p.screenshot({path:`${OUT}/viewer${path.replace(/\//g,"_")||"_root"}.png`});
  }
  console.log("HTTP errors:",[...new Set(bad)].join(" ; "));
  await ctx.close();
}
await b.close();
