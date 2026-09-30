import { launch, login, BASE, OUT } from "./lib.mjs";
const b = await launch();
const screens=["/","/runs","/runs/3","/runs/6","/runs/3/candidates","/enrollments","/letters?kind=settlement_letter&run=3","/employees","/connectors","/automation","/import-export","/admin"];
const seen=new Map();
for (const scheme of ["light","dark"]) {
  const ctx = await b.newContext({ viewport:{width:1280,height:800}, locale:"fa-IR", colorScheme:scheme });
  const p = await ctx.newPage(); await login(p,"admin");
  for (const s of screens) {
    await p.goto(`${BASE}${s}`); await p.waitForTimeout(900);
    const r = await p.evaluate(()=>{
      const parse=c=>{const m=c.match(/[\d.]+/g).map(Number);return {r:m[0],g:m[1],b:m[2],a:m[3]??1}};
      const lum=({r,g,b})=>{const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};return .2126*f(r)+.7152*f(g)+.0722*f(b)};
      const over=(t,b)=>({r:t.r*t.a+b.r*(1-t.a),g:t.g*t.a+b.g*(1-t.a),b:t.b*t.a+b.b*(1-t.a),a:1});
      const bgOf=el=>{const stack=[];for(let e=el;e;e=e.parentElement){const c=parse(getComputedStyle(e).backgroundColor);if(c.a>0)stack.push(c);if(c.a===1)break;}let base={r:255,g:255,b:255,a:1};if(!stack.length||stack[stack.length-1].a<1) base=parse(getComputedStyle(document.body).backgroundColor); let acc=base.a?base:{r:255,g:255,b:255,a:1};for(let i=stack.length-1;i>=0;i--)acc=over(stack[i],acc);return acc};
      const out=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
      while(n=w.nextNode()){const t=n.textContent.trim();if(!t)continue;const el=n.parentElement;if(!el.getBoundingClientRect().width)continue;const cs=getComputedStyle(el);if(cs.visibility==="hidden"||el.closest("[aria-hidden=true]")||el.closest(".sr-only"))continue;
        const dis=el.closest(":disabled,[disabled]");const fg=parse(cs.color);const bg=bgOf(el);const f=over(fg,bg);const L1=lum(f),L2=lum(bg);const cr=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
        const size=parseFloat(cs.fontSize);if(cr<4.5) out.push({t:t.slice(0,30),cr:+cr.toFixed(2),size,dis:!!dis,cls:el.className.toString().slice(0,30),fg:cs.color,bg:`rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`});}
      return out;});
    for (const x of r) { const k=`${scheme}|${x.cls}|${x.cr}|${x.dis}|${x.fg}|${x.bg}`; if(!seen.has(k)) seen.set(k,{...x,screen:s,scheme}); }
  }
  await ctx.close();
}
for (const v of seen.values()) console.log(v.scheme,v.screen,"|",JSON.stringify(v.t),v.cr,"size",v.size,v.dis?"(disabled)":"",v.cls,v.fg,"on",v.bg);
await b.close();
