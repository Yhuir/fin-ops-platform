import { ChevronDown } from 'lucide-react';
import type { RelationKind } from '../../features/relations/types';

const labels = { oa: 'OA', bank: '流水', invoice: '发票' };
const units = { oa: '条', bank: '笔', invoice: '张' };

export function RelationCountButton({ count, kind, expanded, onClick, label }: {
  count: number; kind: RelationKind; expanded: boolean; onClick: () => void; label?: string;
}) {
  return <button type="button" className="relation-count-button" aria-expanded={expanded}
    aria-label={label ?? `${expanded ? '收起' : '展开'}配对关系，${labels[kind]}共 ${count} ${units[kind]}`}
    onClick={onClick}>共 {count} {units[kind]}<ChevronDown aria-hidden="true" size={12} /></button>;
}
