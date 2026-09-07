import { Input, ListBox, Select } from "@heroui/react";
import type { HTMLInputTypeAttribute, ReactNode } from "react";

export function CashInput({ label, value, onChange, type = "text", required, disabled, placeholder }: {
  label: string; value: string; onChange: (value: string) => void;
  type?: HTMLInputTypeAttribute; required?: boolean; disabled?: boolean; placeholder?: string;
}) {
  return <label className="cash-field"><span>{label}{required ? " *" : ""}</span>
    <Input aria-label={label} type={type} value={value} onChange={event => onChange(event.target.value)} required={required} disabled={disabled} placeholder={placeholder} />
  </label>;
}

export function CashSelect({ label, value, onChange, options, required, disabled }: {
  label: string; value: string; onChange: (value: string) => void;
  options: { value: string; label: string; disabled?: boolean }[]; required?: boolean; disabled?: boolean;
}) {
  return <div className="cash-field"><span>{label}{required ? " *" : ""}</span>
    <Select aria-label={label} selectedKey={value === "" && !options.some(option => option.value === "") ? null : value} isRequired={required} isDisabled={disabled}
      placeholder="请选择" onSelectionChange={key => onChange(key === null ? "" : String(key))}>
      <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
      <Select.Popover className="cash-select-popover"><ListBox>
        {options.map(option => <ListBox.Item key={option.value} id={option.value} textValue={option.label} isDisabled={option.disabled}>{option.label}</ListBox.Item>)}
      </ListBox></Select.Popover>
    </Select>
  </div>;
}

export function CashNotice({ error, children }: { error?: string | null; children?: ReactNode }) {
  if (!error && !children) return null;
  return <div className={`cash-notice${error ? " cash-notice--error" : ""}`} role={error ? "alert" : "status"}>{error || children}</div>;
}

export function CashTabs({ value, onChange, tabs }: {
  value: string; onChange: (value: string) => void; tabs: { id: string; label: string }[];
}) {
  return <div className="cash-tabs" role="tablist" aria-label="当前现金子页面视图">{tabs.map(tab =>
    <button key={tab.id} type="button" role="tab" aria-selected={value === tab.id} className={value === tab.id ? "active" : ""}
      onClick={() => onChange(tab.id)} onKeyDown={event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const current = tabs.findIndex(item => item.id === tab.id);
        const index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
          (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
        onChange(tabs[index].id);
        (event.currentTarget.parentElement?.children[index] as HTMLButtonElement)?.focus();
      }}>{tab.label}</button>)}</div>;
}
