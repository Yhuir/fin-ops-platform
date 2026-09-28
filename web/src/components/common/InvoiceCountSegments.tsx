import { Tabs } from "@heroui/react";
import { CountedLabel } from "./CountLabel";
import "./segmentedControl.css";

/** Presentation only: callers own status meanings, counts and query state. */
export default function InvoiceCountSegments({ label, selectedKey, options, unit, pending, invalid, onChange, className = "" }: {
  className?: string;
  label: string;
  selectedKey: string;
  options: readonly { key: string; label: string; count?: number }[];
  unit: "笔" | "张";
  pending?: boolean;
  invalid?: boolean;
  onChange: (key: string) => void;
}) {
  return <div className="count-update-boundary" aria-busy={Boolean(pending && !invalid)}><Tabs data-count-pending={pending && !invalid ? "true" : "false"} className={`invoice-count-segments ${className}`} selectedKey={selectedKey} onSelectionChange={key => onChange(String(key))}>
    <Tabs.List aria-label={label}>
      {options.map(option => <Tabs.Tab id={option.key} key={option.key}>
        {option.key === "multiple" ? <span>{option.label}</span> : <CountedLabel label={option.label} value={invalid ? undefined : option.count} unit={unit} spaced />}

      </Tabs.Tab>)}
    </Tabs.List>
  </Tabs></div>;
}
