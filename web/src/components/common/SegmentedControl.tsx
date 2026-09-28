import { ToggleButton, ToggleButtonGroup } from "@heroui/react";
import type { ComponentProps, ReactNode } from "react";

import "./segmentedControl.css";
import "./countLabel.css";

/** Presentation only. The caller owns selection, permissions, counts and I/O. */
export function SegmentGroup({ className, "aria-busy": busy, ...props }: Omit<ComponentProps<typeof ToggleButtonGroup>, "className"> & { className?: string; "aria-busy"?: boolean }) {
  const group = <ToggleButtonGroup {...props} data-count-pending={busy === true ? "true" : "false"} className={`app-segments ${className ?? ""}`} />;
  return busy === undefined ? group : <div className="count-update-boundary" aria-busy={busy}>{group}</div>;
}

export function Segment({ children, ...props }: Omit<ComponentProps<typeof ToggleButton>, "children"> & { children: ReactNode }) {
  return <ToggleButton {...props}><span className="app-segments__label">{children}</span></ToggleButton>;
}

export default function SegmentedControl<K extends string>({ label, value, options, onChange, disabled, pending, className }: {
  label: string;
  value: K;
  options: readonly { key: K; label: ReactNode; disabled?: boolean; controls?: string }[];
  onChange: (key: K) => void;
  disabled?: boolean;
  pending?: boolean;
  className?: string;
}) {
  return <SegmentGroup aria-label={label} aria-busy={pending} className={className} selectionMode="single" disallowEmptySelection isDisabled={disabled}
    selectedKeys={new Set([value])} onSelectionChange={keys => {
      const option = options.find(item => keys.has(item.key));
      if (option && option.key !== value) onChange(option.key);
    }}>
    {options.map(option => <Segment key={option.key} id={option.key} isDisabled={option.disabled} aria-controls={option.controls}>{option.label}</Segment>)}
  </SegmentGroup>;
}
