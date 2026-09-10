import { Button } from '@heroui/react';
import { useState, type ReactNode } from 'react';
import CostExplorerList from './CostExplorerList';
import { formatCostAmount } from '../../features/cost-statistics/format';
import './costStatisticsHierarchy.css';

type Item = { key: string; label: string; amount: string };
export type CostHierarchyLane = { title: string; selectedKey: string | null; items: Item[]; onSelect: (key: string) => void };
export default function CostStatisticsHierarchy({ lanes, children }: { lanes: CostHierarchyLane[]; children: ReactNode }) {
  const [focusedLane, setFocusedLane] = useState<number | null>(null);
  const nextLane = lanes.findIndex(lane => lane.selectedKey === null);
  const activeLane = focusedLane ?? (nextLane < 0 ? lanes.length : nextLane);
  return <div className="cost-hierarchy" data-lanes={lanes.length} style={{ '--cost-lane-count': lanes.length } as React.CSSProperties}>
    <nav aria-label="成本下钻路径" className="cost-hierarchy-breadcrumb">
      {lanes.map((lane, index) => <Button key={lane.title} size="sm" variant={activeLane === index ? 'primary' : 'secondary'} onPress={() => setFocusedLane(index)}>{lane.title}{lane.selectedKey ? `：${lane.items.find(item => item.key === lane.selectedKey)?.label ?? ''}` : ''}</Button>)}
      <Button size="sm" variant={activeLane === lanes.length ? 'primary' : 'secondary'} onPress={() => setFocusedLane(lanes.length)}>成本明细</Button>
    </nav>
    <div className="cost-hierarchy-grid">
      {lanes.map((lane, index) => <div key={lane.title} className={`cost-hierarchy-column${activeLane === index ? ' is-current' : ''}`}>
        <CostExplorerList<Item> key={JSON.stringify(lanes.slice(0, index).map(parent => parent.selectedKey))} title={lane.title} count={lane.items.length} items={lane.items} emptyLabel={index > 0 && !lanes[index - 1].selectedKey ? `请先选择${lanes[index - 1].title}` : '当前范围暂无数据'} getKey={item => item.key} getPrimaryText={item => item.label} isActive={item => item.key === lane.selectedKey} onSelect={item => { lane.onSelect(item.key); setFocusedLane(index + 1); }} renderMeta={item => <span className="cost-source-money">{formatCostAmount(item.amount)}</span>} />
      </div>)}
      <div key={JSON.stringify(lanes.map(lane => lane.selectedKey))} className={`cost-hierarchy-detail${activeLane === lanes.length ? ' is-current' : ''}`}>{children}</div>
    </div>
  </div>;
}
