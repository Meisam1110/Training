import type { ReactNode } from "react";
import { Switch } from "../components/Field";
export const SwitchRow = ({ label, checked, onChange, disabled }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) => <Switch label={label} checked={checked} onChange={onChange} disabled={disabled} />;
