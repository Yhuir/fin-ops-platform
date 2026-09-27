import { Tabs } from "@heroui/react";

/** Presentation only: callers own status meanings, counts and query state. */
export default function InvoiceCountSegments({ label, selectedKey, options, unit, pending, onChange }: {
  label: string;
  selectedKey: string;
  options: readonly { key: string; label: string; count?: number }[];
  unit: "笔" | "张";
  pending?: boolean;
  onChange: (key: string) => void;
}) {
  return <Tabs className="invoice-count-segments" selectedKey={selectedKey} onSelectionChange={key => onChange(String(key))}>
    <Tabs.List aria-label={label}>
      {options.map(option => <Tabs.Tab id={option.key} key={option.key}>
        <span>{option.label}</span>
        {option.key !== "multiple" ? <span className="invoice-count-segments__count">{pending || option.count === undefined ? "—" : option.count} {unit}</span> : null}
        <Tabs.Indicator />
      </Tabs.Tab>)}
    </Tabs.List>
  </Tabs>;
}
