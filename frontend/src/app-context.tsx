import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Api } from "./api/client";
import type { Role, User } from "./api/types";
import { navigate } from "./lib/router";

const ApiCtx = createContext<Api | null>(null);
export const ApiProvider = ({ api, children }: { api: Api; children: ReactNode }) => <ApiCtx.Provider value={api}>{children}</ApiCtx.Provider>;
export function useApi(): Api { const a = useContext(ApiCtx); if (!a) throw new Error("ApiProvider missing"); return a; }

interface Auth { user: User | null; status: "loading" | "authed" | "anon"; setUser: (u: User | null) => void; canWrite: boolean; isAdmin: boolean; role: Role | null }
const AuthCtx = createContext<Auth | null>(null);
/** true while a user is signed in — lets the 401 handler tell "session expired" from "never signed in" */
export const authFlag = { authed: false, expired: false };
export function AuthProvider({ children, initialUser }: { children: ReactNode; initialUser?: User | null }) {
  const api = useApi();
  const [user, setUser] = useState<User | null>(initialUser ?? null);
  const [status, setStatus] = useState<Auth["status"]>(initialUser ? "authed" : "loading");
  useEffect(() => {
    if (initialUser) return;
    api.me().then((u) => { setUser(u); setStatus("authed"); }).catch(() => { setStatus("anon"); });
  }, [api, initialUser]);
  useEffect(() => { authFlag.authed = status === "authed"; if (status === "authed") authFlag.expired = false; }, [status]);
  const value = useMemo<Auth>(() => ({
    user, status, role: user?.role ?? null,
    setUser: (u) => { setUser(u); setStatus(u ? "authed" : "anon"); },
    canWrite: user?.role === "admin" || user?.role === "hr", isAdmin: user?.role === "admin",
  }), [user, status]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}
export function useAuth(): Auth { const a = useContext(AuthCtx); if (!a) throw new Error("AuthProvider missing"); return a; }
/** Session expired / not signed in: go to login and come back to the same screen (path + query) afterwards. */
export const toLogin = (expired = false) => {
  const cur = window.location.hash.replace(/^#/, "");
  if (cur.startsWith("/login")) return;
  navigate(`/login?${cur && cur !== "/" ? `next=${encodeURIComponent(cur)}&` : ""}${expired ? "expired=1" : ""}`.replace(/&$/, "").replace(/\?$/, ""), true);
};
