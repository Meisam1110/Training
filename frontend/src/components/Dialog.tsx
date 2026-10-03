import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "./ui";

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

interface DialogProps {
  open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode;
  wide?: boolean; /** block Esc / backdrop / close button, e.g. while a request is pending */ locked?: boolean;
  initialFocus?: string; /** CSS selector inside the dialog */
}

/** Accessible modal: role=dialog, aria-modal, focus trap, Esc, focus restore, background inert. */
export function Dialog({ open, title, onClose, children, footer, wide, locked, initialFocus }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const lockedRef = useRef(locked); lockedRef.current = locked;

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const root = document.getElementById("root");
    root?.setAttribute("inert", "");
    const prevOverflow = document.body.style.overflow; document.body.style.overflow = "hidden";
    const node = ref.current!;
    const focusables = () => Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
    const target = (initialFocus && node.querySelector<HTMLElement>(initialFocus)) || node.querySelector<HTMLElement>(".dialog__body " + FOCUSABLE.split(",").join(", .dialog__body ")) || focusables()[0] || node;
    target.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); if (!lockedRef.current) closeRef.current(); return; }
      if (e.key !== "Tab") return;
      const f = focusables(); if (!f.length) { e.preventDefault(); return; }
      const first = f[0]!, last = f[f.length - 1]!;
      if (e.shiftKey && (document.activeElement === first || document.activeElement === node)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      root?.removeAttribute("inert"); document.body.style.overflow = prevOverflow;
      prev?.focus?.();
    };
  }, [open, initialFocus]);

  if (!open) return null;
  return createPortal(
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !locked) onClose(); }}>
      <div ref={ref} className={`dialog ${wide ? "dialog--wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="dialog__head">
          <h2 id={titleId} style={{ fontSize: "var(--fs-5)" }}>{title}</h2>
          <Button variant="ghost" icon="x" aria-label="بستن" onClick={onClose} disabled={locked} />
        </div>
        <div className="dialog__body">{children}</div>
        {footer && <div className="dialog__foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

interface ConfirmProps {
  open: boolean; title: string; consequence: ReactNode; confirmLabel: string; cancelLabel?: string;
  danger?: boolean; pending?: boolean; onConfirm: () => void; onCancel: () => void; children?: ReactNode;
}
/** Confirmation that states the consequence of an outward or destructive action. */
export function ConfirmDialog({ open, title, consequence, confirmLabel, cancelLabel = "انصراف", danger, pending, onConfirm, onCancel, children }: ConfirmProps) {
  return (
    <Dialog open={open} title={title} onClose={onCancel} locked={pending} initialFocus="[data-cancel]"
      footer={<>
        <Button variant={danger ? "danger" : "primary"} pending={pending} onClick={onConfirm}>{confirmLabel}</Button>
        <Button data-cancel onClick={onCancel} disabled={pending}>{cancelLabel}</Button>
      </>}>
      <p>{consequence}</p>
      {children}
    </Dialog>
  );
}
