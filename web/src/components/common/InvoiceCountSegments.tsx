import { Tabs } from "@heroui/react";
import CountLabel from "./CountLabel";

/** Presentation only: callers own status meanings, counts and query state. */
export default function InvoiceCountSegments({ label, selectedKey, options, unit, pending, invalid, onChange }: {
  label: string;
  selectedKey: string;
  options: readonly { key: string; label: string; count?: number }[];
  unit: "笔" | "张";
  pending?: boolean;
  invalid?: boolean;
  onChange: (key: string) => void;
}) {
  return <div className="count-update-boundary" aria-busy={Boolean(pending && !invalid)}><Tabs data-count-pending={pending && !invalid ? "true" : "false"} className="invoice-count-segments" selectedKey={selectedKey} onSelectionChange={key => onChange(String(key))}>
    <Tabs.List aria-label={label}>
      {options.map(option => <Tabs.Tab id={option.key} key={option.key}>
        <span>{option.label}</span>
        {option.key !== "multiple" ? <span className="invoice-count-segments__count"><CountLabel value={invalid ? undefined : option.count} unit={unit} spaced /></span> : null}
        <Tabs.Indicator />
      </Tabs.Tab>)}
    </Tabs.List>
  </Tabs></div>;
}
