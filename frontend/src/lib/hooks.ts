import { useEffect, useState } from "react";
export function useDebounced<T>(v: T, ms = 300): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}
export function newKey(): string {
  try { return crypto.randomUUID(); } catch { return `k-${Date.now()}-${Math.random().toString(36).slice(2)}`; }
}
export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const storage = {
  get(k: string): string | null { try { return localStorage.getItem(k); } catch { return null; } },
  set(k: string, v: string) { try { localStorage.setItem(k, v); } catch { /* unavailable */ } },
};

/** After a failed validation, move focus to the first invalid control (dialog first, else page). */
export function focusFirstInvalid() {
  setTimeout(() => {
    const scope = document.querySelector('[role="dialog"]') ?? document;
    scope.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, 0);
}
