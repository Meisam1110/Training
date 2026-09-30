import { useEffect } from "react";
import { matchPath, navigate, useRoute } from "./lib/router";
import { toLogin, useAuth } from "./app-context";
import { Shell } from "./components/Layout";
import { ROUTES } from "./routes";
import { EmptyState, LinkButton } from "./components/ui";

export function App() {
  const route = useRoute();
  const { status, isAdmin, canWrite } = useAuth();
  let params: Record<string, string> | null = null;
  const def = ROUTES.find((r) => (params = matchPath(r.pattern, route.path)) !== null);

  useEffect(() => {
    document.title = `${def?.title ?? "صفحه پیدا نشد"} — مدیریت آموزش`;
    if (status === "authed") document.getElementById("page-title")?.focus({ preventScroll: true });
  }, [def, status, route.path]);
  useEffect(() => {
    if (status === "anon" && !def?.public) {
      toLogin(false);
    }
    if (status === "authed" && def?.public) { const next = route.query.get("next"); navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/", true); }
  }, [status, def, route.path]);

  if (status === "loading") return <div className="login" role="status" aria-live="polite"><span className="sr-only">در حال بارگذاری…</span><span className="btn__spinner" style={{ inlineSize: 32, blockSize: 32 }} /></div>;
  if (def?.public) return status === "anon" ? <>{def.render(params ?? {})}</> : null;
  if (status !== "authed") return null;
  return (
    <Shell>
      {!def ? <EmptyState title="صفحه پیدا نشد" description="نشانی واردشده وجود ندارد." action={<LinkButton variant="primary" href="#/">بازگشت به داشبورد</LinkButton>} />
        : (def.admin && !isAdmin) || (def.hr && !canWrite) ? <EmptyState icon="lock" title="دسترسی ندارید" description={def.admin ? "این بخش فقط برای مدیر سامانه در دسترس است." : "این بخش برای نقش «ناظر» در دسترس نیست؛ با مدیر سامانه یا کارشناس آموزش هماهنگ کنید."} action={<LinkButton href="#/">بازگشت به داشبورد</LinkButton>} />
        : def.render(params ?? {})}
    </Shell>
  );
}
