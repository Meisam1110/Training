import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Button } from "./ui";
import { authFlag } from "../app-context";

interface ToastInput { message: string; kind?: "info" | "error"; action?: { label: string; onClick: () => void }; duration?: number }
interface ToastItem extends ToastInput { id: number }
const Ctx = createContext<{ push: (t: ToastInput) => void; dismiss: (id: number) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(1);
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback((t: ToastInput) => {
    if (authFlag.expired) return; // session expired: the login page explains it; follow-up failure toasts would be noise
    const id = seq.current++;
    setItems((l) => [...l.slice(-3), { ...t, id }]);
    const ms = t.duration ?? (t.action ? 9000 : t.kind === "error" ? 8000 : 4500);
    setTimeout(() => dismiss(id), ms);
  }, [dismiss]);
  // stale toasts must not follow the user to another screen (or the login page)
  useEffect(() => { const f = () => setItems([]); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);
  const render = (list: ToastItem[]) => list.map((t) => (
    <div key={t.id} className={`toast ${t.kind === "error" ? "toast--error" : ""}`}>
      <span>{t.message}</span>
      {t.action && <Button size="sm" onClick={() => { t.action!.onClick(); dismiss(t.id); }}>{t.action.label}</Button>}
      <Button size="sm" variant="ghost" icon="x" aria-label="بستن اعلان" onClick={() => dismiss(t.id)} />
    </div>
  ));
  return (
    <Ctx.Provider value={value}>
      {children}
      {/* Two persistent live regions: polite for info, assertive for errors. */}
      <div className="toasts">
        <div role="status" aria-live="polite" aria-atomic="false" style={{ display: "contents" }}>{render(items.filter((t) => t.kind !== "error"))}</div>
        <div role="alert" aria-live="assertive" style={{ display: "contents" }}>{render(items.filter((t) => t.kind === "error"))}</div>
      </div>
    </Ctx.Provider>
  );
}
export function useToast() {
  const c = useContext(Ctx);
  if (!c) throw new Error("ToastProvider missing");
  return c;
}
