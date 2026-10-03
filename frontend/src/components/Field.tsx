import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { toEn, toFa } from "../lib/digits";
import { Icon } from "./Icon";

interface Base { label: string; error?: string | null; hint?: string; required?: boolean }

function Shell({ id, label, error, hint, required, children }: Base & { id: string; children: ReactNode }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>{label}{required && <span aria-hidden="true"> *</span>}</label>
      {children}
      {hint && !error && <span className="field__hint" id={`${id}-hint`}>{hint}</span>}
      {error && <span className="field__error" id={`${id}-err`} role="alert"><Icon name="alert" className="" />{error}</span>}
    </div>
  );
}
const aria = (id: string, error?: string | null, hint?: string) => ({
  id, "aria-invalid": error ? true : undefined, "aria-describedby": error ? `${id}-err` : hint ? `${id}-hint` : undefined,
});

type TF = Base & Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  value: string; onChange: (v: string) => void;
  /** digits: Persian/Arabic digits typed by the user are stored as Latin; shown Persian. */
  numeric?: boolean;
};
export function TextField({ label, error, hint, required, value, onChange, numeric, ...rest }: TF) {
  const id = useId();
  return (
    <Shell id={id} label={label} error={error} hint={hint} required={required}>
      <input className="input" {...aria(id, error, hint)} required={required} aria-required={required || undefined}
        value={numeric ? toFa(value) : value} inputMode={numeric ? "numeric" : rest.inputMode}
        dir={numeric || rest.type === "email" || rest.dir === "ltr" ? "ltr" : undefined}
        onChange={(e) => onChange(numeric ? toEn(e.target.value) : e.target.value)} {...rest} />
    </Shell>
  );
}
type SF = Base & Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> & { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string };
export function SelectField({ label, error, hint, required, value, onChange, options, placeholder, ...rest }: SF) {
  const id = useId();
  return (
    <Shell id={id} label={label} error={error} hint={hint} required={required}>
      <select className="select" {...aria(id, error, hint)} value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Shell>
  );
}
type TA = Base & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value"> & { value: string; onChange: (v: string) => void };
export function TextAreaField({ label, error, hint, required, value, onChange, ...rest }: TA) {
  const id = useId();
  return (
    <Shell id={id} label={label} error={error} hint={hint} required={required}>
      <textarea className="textarea" {...aria(id, error, hint)} value={value} onChange={(e) => onChange(e.target.value)} {...rest} />
    </Shell>
  );
}
/** 44x44 hit area around a native checkbox; the accessible name goes on the input. */
export function CheckBox({ checked, onChange, label, disabled }: { checked: boolean; onChange: () => void; label: string; disabled?: boolean }) {
  return <label className="hit"><input type="checkbox" aria-label={label} checked={checked} disabled={disabled} onChange={onChange} /></label>;
}
export function Switch({ label, checked, onChange, disabled, testId }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testId?: string }) {
  return (
    <label className="switch">
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} data-testid={testId} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch__track" aria-hidden="true" />
      <span>{label}</span>
    </label>
  );
}
export { Shell as FieldShell, aria as fieldAria };
