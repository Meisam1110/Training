import { launch, login } from "./lib.mjs";
const [target = "liveprod", role = "admin"] = process.argv.slice(2);
const b = await launch();
for (const [w, theme] of [[1440, "light"], [390, "light"], [1440, "dark"]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: w > 500 ? 900 : 844 }, locale: "fa-IR", colorScheme: theme });
  const page = await ctx.newPage(); await login(page, target, role);
  for (const [name, r] of [["dashboard", "/"], ["runs", "/runs"], ["run-detail", "/runs/5"], ["letters", "/letters"], ["import-export", "/import-export"], ["enrollments", "/enrollments"]]) {
    if (theme === "dark" && name !== "dashboard" && name !== "letters") continue;
    if (w === 390 && !["dashboard", "runs", "letters"].includes(name)) continue;
    await page.evaluate(h => { location.hash = h; }, r); await page.waitForTimeout(1500);
    await page.screenshot({ path: `shots/${target}-${name}-${w}-${theme}.png`, fullPage: false });
  }
  await ctx.close();
}
await b.close();
