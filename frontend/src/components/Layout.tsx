import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useRoute } from "../lib/router";
import { useAuth, useApi } from "../app-context";
import { ROLE_FA } from "../lib/labels";
import { storage } from "../lib/hooks";
import { Button } from "./ui";
import { Icon } from "./Icon";
import { Wordmark } from "./Wordmark";
import { NAV } from "../routes";

type Theme = "system" | "light" | "dark";
function applyTheme(t: Theme) { if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t; }
const THEME_FA: Record<Theme, string> = { system: "خودکار (مطابق سیستم)", light: "روشن", dark: "تیره" };

export function ThemeToggle() {
  const [t, setT] = useState<Theme>(() => { const v = storage.get("tms.theme"); return v === "light" || v === "dark" ? v : "system"; });
  useEffect(() => { applyTheme(t); if (t === "system") { try { localStorage.removeItem("tms.theme"); } catch { /* */ } } else storage.set("tms.theme", t); }, [t]);
  const next: Theme = t === "system" ? "light" : t === "light" ? "dark" : "system";
  return <Button variant="ghost" icon={t === "dark" ? "moon" : "sun"} onClick={() => setT(next)} aria-label={`پوسته: ${THEME_FA[t]}. برای تغییر به «${THEME_FA[next]}» بزنید`} title={`پوسته: ${THEME_FA[t]}`}>{THEME_FA[t].split(" ")[0]}</Button>;
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, setUser, isAdmin, canWrite } = useAuth(); const api = useApi();
  const route = useRoute();
  const [open, setOpen] = useState(false);
  const main = useRef<HTMLElement>(null);
  useEffect(() => { setOpen(false); }, [route.path]);
  useEffect(() => {
    if (!open) return;
    setTimeout(() => document.querySelector<HTMLElement>(".drawer-close")?.focus(), 0);
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k);
  }, [open]);
  const logout = async () => { try { await api.logout(); } finally { api.http.clearCsrf(); setUser(null); window.location.hash = "/login"; } };
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <div className="app">
      <a href="#main" className="skip-link" onClick={(e) => { e.preventDefault(); main.current?.focus(); }}>پرش به محتوای اصلی</a>
      <div className="scrim" data-open={open} onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className="sidebar" data-open={open} id="sidebar" aria-label="منوی اصلی">
        <div className="sidebar__brand row row--between"><Wordmark /><Button className="drawer-close" variant="ghost" icon="x" aria-label="بستن منو" onClick={() => setOpen(false)} style={{ display: open ? undefined : "none" }} /></div>
        <nav className="nav">
          {groups.map((g) => (
            <div key={g} role="group" aria-label={g}>
              <div className="nav__group" aria-hidden="true">{g}</div>
              {NAV.filter((n) => n.group === g && (!n.admin || isAdmin) && (!n.hr || canWrite)).map((n) => {
                const active = n.path === "/" ? route.path === "/" : route.path.startsWith(n.path);
                return <Link key={n.path} to={n.path} aria-current={active ? "page" : undefined}><Icon name={n.icon} />{n.title}</Link>;
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar__foot">
          <div className="userbox"><strong>{user?.full_name}</strong><small>{user ? ROLE_FA[user.role] : ""}</small></div>
          <ThemeToggle />
          <Button variant="ghost" icon="logout" onClick={logout}>خروج</Button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <Button variant="ghost" icon="menu" aria-label="باز کردن منو" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)} />
          <Wordmark compact /><span className="grow" /><ThemeToggle />
        </header>
        <main id="main" className="content" tabIndex={-1} ref={main}>{children}</main>
      </div>
    </div>
  );
}
