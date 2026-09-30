import { ListBox, Select } from "@heroui/react";

export default function TurnoverLedgerSelect({ label, value, options, disabled, onChange }: {
  label: string; value: string; options: Array<{ value: string; label: string }>; disabled?: boolean; onChange: (value: string) => void;
}) {
  return <Select className="turnover-select" aria-label={label} selectedKey={value} isDisabled={disabled} onSelectionChange={(key) => { if (key !== null) onChange(String(key)); }}>
    <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
    <Select.Popover><ListBox>{options.map((option) => <ListBox.Item id={option.value} key={option.value} textValue={option.label}>{option.label}</ListBox.Item>)}</ListBox></Select.Popover>
  </Select>;
}
