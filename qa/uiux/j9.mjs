import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
for (const [name,vw,vh,fs] of [["zoom200",640,450,null],["zoom400",320,256,null],["text200-360",360,780,"200%"]]) {
  const ctx = await b.newContext({ viewport:{width:vw,height:vh}, locale:"fa-IR" });
  const p = await ctx.newPage(); p.setDefaultTimeout(3000);
  await login(p,"admin");
  if (fs) await p.addStyleTag({content:`html{font-size:${fs} !important}`});
  for (const [n,path] of [["dash","/"],["runs","/runs"],["run","/runs/3"],["cand","/runs/3/candidates"],["letters","/letters?kind=settlement_letter&run=6"],["conn","/connectors"]]) {
    await p.goto(`${BASE}${path}`); await p.waitForTimeout(900);
    const o = await p.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.clientWidth]);
    console.log(name,n,"overflow?",o[0]>o[1]+1,o.join("/"));
    if (n==="run"||n==="runs"||n==="letters") await p.screenshot({path:`${OUT}/${name}-${n}.png`});
  }
  // dialog at small height
  await p.goto(`${BASE}/runs/3`); await p.waitForTimeout(800);
  await p.click('.step:nth-child(3) .step__btn'); 
  await p.click('button:has-text("ارسال ایمیل اطلاعیه")'); await p.waitForTimeout(500);
  const r = await p.evaluate(()=>{const d=document.querySelector(".dialog").getBoundingClientRect(); const f=document.querySelector(".dialog__foot").getBoundingClientRect(); return {dh:d.height,dtop:d.top,fbottom:f.bottom,vh:innerHeight}});
  console.log(name,"dialog",JSON.stringify(r));
  await p.screenshot({path:`${OUT}/${name}-dialog.png`});
  await ctx.close();
}
await b.close();
