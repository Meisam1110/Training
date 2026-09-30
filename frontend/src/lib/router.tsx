import { useEffect, useState, type AnchorHTMLAttributes } from "react";

/** Minimal hash router: "#/runs/3?tab=x" -> { path: "/runs/3", query }. */
export interface Route { path: string; query: URLSearchParams }
const read = (): Route => {
  const h = window.location.hash.replace(/^#/, "") || "/";
  const [p, q = ""] = h.split("?");
  return { path: p || "/", query: new URLSearchParams(q) };
};
export function useRoute(): Route {
  const [r, setR] = useState<Route>(read);
  useEffect(() => {
    const f = () => setR(read());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}
export function navigate(path: string, replace = false) {
  if (replace) window.location.replace(`#${path}`); else window.location.hash = path;
}
export function Link({ to, ...rest }: { to: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return <a href={`#${to}`} {...rest} />;
}
export function matchPath(pattern: string, path: string): Record<string, string> | null {
  const a = pattern.split("/"), b = path.split("/");
  if (a.length !== b.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < a.length; i++) {
    if (a[i]!.startsWith(":")) params[a[i]!.slice(1)] = decodeURIComponent(b[i]!);
    else if (a[i] !== b[i]) return null;
  }
  return params;
}
