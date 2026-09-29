import SegmentedControl from "../common/SegmentedControl";
import { useState, type CSSProperties, type ReactNode } from "react";

import CostExplorerList from "./CostExplorerList";
import "./costStatisticsHierarchy.css";

type Item = { key: string; label: string; primary?: ReactNode; meta: ReactNode; secondary?: ReactNode };
export type CostHierarchyLane = {
  title: string;
  selectedKey: string | null;
  items: Item[];
  loading: boolean;
  emptyLabel: string;
  onSelect: (key: string) => void;
};

type Props = {
  lanes: CostHierarchyLane[];
  detailTitle: string;
  navigationLabel: string;
  children: ReactNode;
};

export default function CostStatisticsHierarchy({ lanes, detailTitle, navigationLabel, children }: Props) {
  const [focusedLane, setFocusedLane] = useState<number | null>(null);
  const nextLane = lanes.findIndex(lane => lane.selectedKey === null);
  const activeLane = focusedLane ?? (nextLane < 0 ? lanes.length : nextLane);

  return (
    <div className="cost-hierarchy" data-lanes={lanes.length} style={{ "--cost-lane-count": lanes.length } as CSSProperties}>
      <div className="cost-hierarchy-breadcrumb">
        <SegmentedControl label={navigationLabel} value={String(activeLane)} onChange={key => setFocusedLane(Number(key))}
          options={[...lanes.map((lane, index) => ({ key: String(index), label: `${lane.title}${lane.selectedKey ? `：${lane.items.find(item => item.key === lane.selectedKey)?.label ?? ""}` : ""}` })), { key: String(lanes.length), label: detailTitle }]} />
      </div>
      <div className="cost-hierarchy-grid">
        {lanes.map((lane, index) => (
          <div key={lane.title} className={`cost-hierarchy-column${activeLane === index ? " is-current" : ""}`}>
            <CostExplorerList<Item>
              key={JSON.stringify(lanes.slice(0, index).map(parent => parent.selectedKey))}
              title={lane.title}
              count={lane.items.length}
              items={lane.items}
              loading={lane.loading}
              emptyLabel={lane.emptyLabel}
              getKey={item => item.key}
              getPrimaryText={item => item.label}
              isActive={item => item.key === lane.selectedKey}
              onSelect={item => { lane.onSelect(item.key); setFocusedLane(index + 1); }}
              renderPrimary={item => item.primary ?? item.label}
              renderMeta={item => item.meta}
              renderSecondary={item => item.secondary}
            />
          </div>
        ))}
        <div key={JSON.stringify(lanes.map(lane => lane.selectedKey))} className={`cost-hierarchy-detail${activeLane === lanes.length ? " is-current" : ""}`}>{children}</div>
      </div>
    </div>
  );
}
