import { Header, Input, ListBox, Select, Tabs } from "@heroui/react";
import { useCallback, type HTMLInputTypeAttribute, type ReactNode } from "react";

export function CashInput({ label, value, onChange, type = "text", required, disabled, placeholder }: {
  label: string; value: string; onChange: (value: string) => void;
  type?: HTMLInputTypeAttribute; required?: boolean; disabled?: boolean; placeholder?: string;
}) {
  return <label className="cash-field"><span>{label}{required ? " *" : ""}</span>
    <Input aria-label={label} type={type} value={value} onChange={event => onChange(event.target.value)} required={required} disabled={disabled} placeholder={placeholder} />
  </label>;
}

export function CashSelect({ label, value, onChange, options, required, disabled, children, onOpenChange, validationError }: {
  label: string; value: string; onChange: (value: string) => void;
  options: { value: string; label: string; disabled?: boolean; group?: { id: string; label: string } }[]; required?: boolean; disabled?: boolean; children?: ReactNode; onOpenChange?: (open: boolean) => void; validationError?: string;
}) {
  const validate = useCallback(() => validationError || null, [validationError]);
  const sections = [...new Map(options.filter(option => option.group).map(option => [option.group!.id, option.group!])).values()];
  const item = (option: typeof options[number]) => <ListBox.Item key={option.value} id={option.value} textValue={option.label} isDisabled={option.disabled}>{option.label}</ListBox.Item>;
  return <div className="cash-field"><span>{label}{required ? " *" : ""}</span>
    <Select aria-label={label} selectedKey={value === "" && !options.some(option => option.value === "") ? null : value} isRequired={required} isDisabled={disabled}
      placeholder="请选择" validationBehavior="native" validate={validate} onOpenChange={onOpenChange} onSelectionChange={key => onChange(key === null ? "" : String(key))}>
      <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
      <Select.Popover className="cash-select-popover"><ListBox>
        {options.filter(option => !option.group).map(item)}
        {sections.map(section => <ListBox.Section key={section.id} id={section.id} aria-label={section.label}>
          <Header>{section.label}</Header>{options.filter(option => option.group?.id === section.id).map(item)}
        </ListBox.Section>)}
      </ListBox>{children}</Select.Popover>
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
  return <Tabs className="cash-tabs" selectedKey={value} onSelectionChange={key => onChange(String(key))}>
    <Tabs.List aria-label="当前现金子页面视图">{tabs.map(tab => <Tabs.Tab key={tab.id} id={tab.id}>{tab.label}</Tabs.Tab>)}</Tabs.List>
  </Tabs>;
}
