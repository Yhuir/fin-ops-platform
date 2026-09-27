import { Tabs, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import type { ComponentProps, ReactNode } from "react";

import "./segmentedControl.css";

/** Presentation only. The caller owns selection, permissions, counts and I/O. */
export function SegmentGroup({ className, ...props }: Omit<ComponentProps<typeof ToggleButtonGroup>, "className"> & { className?: string }) {
  return <ToggleButtonGroup {...props} className={`app-segments ${className ?? ""}`} />;
}

export function Segment({ children, ...props }: Omit<ComponentProps<typeof ToggleButton>, "children"> & { children: ReactNode }) {
  return <ToggleButton {...props}><span className="app-segments__label">{children}</span><Tabs.Indicator className="app-segments__indicator" /></ToggleButton>;
}

export default function SegmentedControl<K extends string>({ label, value, options, onChange, disabled, className }: {
  label: string;
  value: K;
  options: readonly { key: K; label: ReactNode; disabled?: boolean; controls?: string }[];
  onChange: (key: K) => void;
  disabled?: boolean;
  className?: string;
}) {
  return <SegmentGroup aria-label={label} className={className} selectionMode="single" disallowEmptySelection isDisabled={disabled}
    selectedKeys={new Set([value])} onSelectionChange={keys => {
      const option = options.find(item => keys.has(item.key));
      if (option && option.key !== value) onChange(option.key);
    }}>
    {options.map(option => <Segment key={option.key} id={option.key} isDisabled={option.disabled} aria-controls={option.controls}>{option.label}</Segment>)}
  </SegmentGroup>;
}
