import { useCallback, useEffect, useRef, useState } from "react";

const PREFIX = "tms.draft:";
export function readDraft<T>(key: string): T | null {
  try { const v = sessionStorage.getItem(PREFIX + key); return v ? (JSON.parse(v) as T) : null; } catch { return null; }
}
export function writeDraft(key: string, value: unknown) { try { sessionStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch { /* storage unavailable */ } }
export function clearDraft(key: string) { try { sessionStorage.removeItem(PREFIX + key); } catch { /* ignore */ } }

/**
 * Form state that survives a page reload / session expiry (sessionStorage, per key, try/catch).
 * Never put passwords or secrets in it. Call clear() after a successful save.
 * `initial` seeds the state when there is no draft; the draft wins otherwise.
 */
export function useDraft<T extends object>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void, () => void, boolean] {
  const restored = useRef<boolean>(false);
  const [state, setState] = useState<T>(() => { const d = readDraft<T>(key); if (d) { restored.current = true; return { ...initial, ...d }; } return initial; });
  const first = useRef(true);
  useEffect(() => { if (first.current) { first.current = false; if (!restored.current) return; } writeDraft(key, state); }, [key, state]);
  const clear = useCallback(() => { clearDraft(key); restored.current = false; }, [key]);
  return [state, setState, clear, restored.current];
}
