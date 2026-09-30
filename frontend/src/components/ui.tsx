import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

type Variant = "default" | "primary" | "danger" | "ghost";
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: Variant; size?: "md" | "sm"; pending?: boolean; icon?: IconName }
const cls = (variant: Variant, size: string, extra?: string) => ["btn", variant !== "default" && `btn--${variant}`, size === "sm" && "btn--sm", extra].filter(Boolean).join(" ");

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant = "default", size = "md", pending = false, icon, children, className, disabled, type = "button", ...rest }, ref) {
  return (
    <button ref={ref} type={type} className={cls(variant, size, className)} disabled={disabled || pending} aria-busy={pending || undefined} {...rest}>
      {pending ? <span className="btn__spinner" aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
});
export function LinkButton({ variant = "default", size = "md", icon, children, className, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant; size?: "md" | "sm"; icon?: IconName }) {
  return <a className={cls(variant, size, className)} {...rest}>{icon && <Icon name={icon} />}{children}</a>;
}

/** Identifier (employee no., ticket, letter no.): always Latin, mono, LTR island — one rule everywhere. */
export const Ident = ({ children }: { children: ReactNode }) => <span className="id">{children}</span>;

export type Tone = "neutral" | "ok" | "warn" | "danger" | "info" | "brand";
export function Chip({ tone = "neutral", children, plain }: { tone?: Tone; children: ReactNode; plain?: boolean }) {
  return <span className={`chip ${tone !== "neutral" ? `chip--${tone}` : ""} ${plain ? "chip--plain" : ""}`}>{children}</span>;
}

export function Skeleton({ w = "100%", h = 16 }: { w?: string | number; h?: number }) {
  return <span className="skel" style={{ inlineSize: w, blockSize: h }} aria-hidden="true" />;
}

export function EmptyState({ title, description, action, icon = "inbox" }: { title: string; description?: string; action?: ReactNode; icon?: IconName }) {
  return (
    <div className="state" data-testid="empty-state">
      <div className="state__icon"><Icon name={icon} /></div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
export function ErrorState({ error, onRetry, title = "بارگذاری انجام نشد" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const msg = error instanceof Error ? error.message : "خطای ناشناخته";
  return (
    <div className="state state--error" role="alert" data-testid="error-state">
      <div className="state__icon"><Icon name="alert" /></div>
      <h3>{title}</h3>
      <p>{msg}</p>
      {onRetry && <Button icon="refresh" onClick={onRetry}>تلاش دوباره</Button>}
    </div>
  );
}

export function Callout({ tone = "info", icon, children }: { tone?: "info" | "warn" | "danger" | "ok"; icon?: IconName; children: ReactNode }) {
  return (
    <div className={`callout callout--${tone}`} role={tone === "danger" ? "alert" : undefined}>
      <Icon name={icon ?? (tone === "ok" ? "check" : tone === "info" ? "info" : "alert")} />
      <div>{children}</div>
    </div>
  );
}

export function PageHead({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div><h1 tabIndex={-1} id="page-title">{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}
