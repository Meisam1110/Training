/** Preview HTML comes from our own backend, but strip active content defensively anyway. */
export function sanitize(html: string): string {
  const t = document.createElement("template"); t.innerHTML = html;
  t.content.querySelectorAll("script,iframe,object,embed,link,style").forEach((n) => n.remove());
  t.content.querySelectorAll("*").forEach((el) => { for (const a of Array.from(el.attributes)) if (/^on/i.test(a.name) || /^\s*javascript:/i.test(a.value)) el.removeAttribute(a.name); });
  return t.innerHTML;
}
