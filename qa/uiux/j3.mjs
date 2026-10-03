import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const ctx = await b.newContext({ viewport:{width:1280,height:900}, locale:"fa-IR" });
await ctx.addInitScript(()=>{
  window.__urls=[]; const RU=URL; 
  window.URL = class extends RU { constructor(u,b){ super(u,b); if(String(u).includes("/email/send")) window.__urls.push(String(u)); } };
  const R=Response;
  window.Response = class extends R { constructor(body,init){ 
    const m=window.__mode;
    if(m==="net") throw new TypeError("net");
    if(m==="500") { super(JSON.stringify({error:{code:"upstream",message:"خطای داخلی سرور (۵۰۰)"}}),{status:500,headers:init?.headers}); return; }
    if(m==="500raw") { super("<html>Bad Gateway</html>",{status:502,headers:{"Content-Type":"text/html"}}); return; }
    if(m==="401") { super(JSON.stringify({error:{code:"unauthorized",message:"نشست شما منقضی شده است. دوباره وارد شوید."}}),{status:401,headers:init?.headers}); return; }
    super(body,init);} };
});
const p = await ctx.newPage();
p.on("pageerror",e=>console.log("PAGEERR",e.message));
await login(p,"admin");
const txt=async(sel)=> (await p.innerText(sel)).replace(/\n+/g," | ").slice(0,300);
// D double click + A failure
await p.goto(`${BASE}/runs/3`); await p.waitForTimeout(900);
await p.click('.step:nth-child(3) .step__btn');
await p.click('button:has-text("ارسال ایمیل اطلاعیه")'); await p.waitForTimeout(500);
await p.click('button:has-text("ادامه و بازبینی")');
await p.evaluate(()=>{window.__mode="500"});
await p.click('button:has-text("ارسال واقعی به")'); await p.waitForTimeout(800);
await p.screenshot({path:`${OUT}/j3-send-500.png`});
console.log("500 send:", await txt('[role=dialog]')); console.log("toasts:", await txt('.toasts'));
await p.evaluate(()=>{window.__mode=null});
await p.click('button:has-text("ادامه و بازبینی")');
const sendBtn = p.locator('button:has-text("ارسال واقعی به")');
await p.evaluate(()=>{window.__urls.length=0});
await sendBtn.dblclick(); await p.waitForTimeout(1200);
console.log("send POST count on dblclick:", await p.evaluate(()=>window.__urls.length));
// network fail on run save
await p.keyboard.press("Escape"); 
await p.goto(`${BASE}/runs/3`); await p.waitForTimeout(900);
await p.click('.step:nth-child(1) .step__btn');
const inst = p.locator('section.card input.input').nth(1);
await inst.fill("مؤسسهٔ تست");
await p.evaluate(()=>{window.__mode="net"});
await p.click('button:has-text("ذخیرهٔ برنامه")'); await p.waitForTimeout(700);
await p.screenshot({path:`${OUT}/j3-save-net.png`});
console.log("net save toast:", await txt('.toasts'), "| input kept:", await inst.inputValue());
await p.evaluate(()=>{window.__mode="500raw"});
await p.click('button:has-text("ذخیرهٔ برنامه")'); await p.waitForTimeout(700);
console.log("502 html toast:", await txt('.toasts'));
// 401 mid-form
await p.evaluate(()=>{window.__mode="401"});
await p.click('button:has-text("ذخیرهٔ برنامه")'); await p.waitForTimeout(900);
console.log("after 401 url:", p.url());
await p.screenshot({path:`${OUT}/j3-401.png`});
console.log("login page text:", await txt("body"));
await p.evaluate(()=>{window.__mode=null});
// list error state
await p.goto(`${BASE}/login`);
await b.close();
