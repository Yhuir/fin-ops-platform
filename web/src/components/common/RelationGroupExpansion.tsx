import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import { formatMoney } from '../../features/money';
import StatePanel from './StatePanel';

export type SourceDetailTarget = { kind: 'oa' | 'bank' | 'invoice'; id: string; rowId?: string };
export type RelationMember = {
  id: string;
  title: string;
  subtitle?: string;
  date?: string;
  amount?: string;
  status?: string;
  relationId?: string;
  relationIds?: string[];
  detailAvailable: boolean;
};
export type RelationColumn = {
  kind: SourceDetailTarget['kind'];
  count: number;
  members: RelationMember[];
};
const labels = { oa: 'OA', bank: '流水', invoice: '发票' };
const units = { oa: '条', bank: '笔', invoice: '张' };

export function RelationCountButton({ count, kind, expanded, onClick, label }: {
  count: number; kind: SourceDetailTarget['kind']; expanded: boolean; onClick: () => void; label?: string;
}) {
  return <button type="button" className="relation-count-button" aria-expanded={expanded}
    aria-label={label ?? `${expanded ? '收起' : '展开'}配对关系，${labels[kind]}共 ${count} ${units[kind]}`}
    onClick={onClick}>共 {count} {units[kind]}<ChevronDown aria-hidden="true" size={12} /></button>;
}

export default function RelationGroupExpansion({ columns, expanded, onClose, onExited, onOpenDetail }: {
  columns: RelationColumn[] | null; expanded: boolean; onClose: () => void; onExited: () => void;
  onOpenDetail: (target: SourceDetailTarget) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  useLayoutEffect(() => {
    const node = ref.current!;
    const viewport = node.closest<HTMLElement>('.finance-table__scroll');
    if (!viewport) return;
    const measure = () => { node.style.maxWidth = `${viewport.clientWidth}px`; };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const node = ref.current!;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const height = node.scrollHeight;
    const startHeight = started.current ? node.getBoundingClientRect().height : 0;
    started.current = true;
    const animation = node.animate([
      { height: `${startHeight}px`, opacity: Number(getComputedStyle(node).opacity) },
      { height: expanded ? `${height}px` : '0px', opacity: expanded ? 1 : 0.6 },
    ], { duration: reduced ? 0 : expanded ? 220 : 170, easing: 'cubic-bezier(.2,.7,.2,1)' });
    node.style.height = expanded ? 'auto' : '0px';
    node.style.opacity = expanded ? '1' : '0.6';
    animation.onfinish = () => { if (!expanded) onExited(); };
    return () => {
      // Preserve the current frame when a user reverses the slide mid-animation.
      node.style.height = `${node.getBoundingClientRect().height}px`;
      node.style.opacity = getComputedStyle(node).opacity;
      animation.cancel();
    };
  }, [expanded, onExited]);
  const validColumns = columns ?? [];
  const relationIds = [...new Set(validColumns.flatMap(column => column.members.flatMap(member => member.relationIds ?? (member.relationId ? [member.relationId] : []))))];
  const incomplete = !columns || validColumns.some(column => !Number.isInteger(column.count) || column.count < 0 || column.count !== column.members.length || column.members.some(member => !member.id));
  return <div ref={ref} className="relation-expansion-motion" data-expanded={expanded}>
    <section className="relation-expansion" aria-label="配对关系">
      <div className="relation-expansion__heading">
        <strong>配对关系</strong>
        {relationIds.length > 1 && <span className="relation-expansion__scope">{relationIds.length} 组独立关系</span>}
        <button type="button" className="relation-expansion__close" onClick={onClose}>收起<ChevronUp size={14} aria-hidden="true" /></button>
      </div>
      {incomplete ? <StatePanel compact tone="error">关系摘要不完整，请重新查询后查看。</StatePanel> :
        <div className="relation-expansion__columns" style={{ gridTemplateColumns: `repeat(${validColumns.length}, minmax(0, 1fr))` }}>
          {validColumns.map(column => <div className="relation-expansion__column" key={column.kind}>
            <h3>{labels[column.kind]}<span>{column.count} {units[column.kind]}</span></h3>
            {column.members.length === 0 ? <p className="relation-expansion__empty">暂无关联{labels[column.kind]}</p> :
              <ul>{column.members.map((member, index) => <li key={`${member.relationId ?? ''}:${member.id}:${index}`}>
                <div className="relation-expansion__member-heading">
                  <span className="relation-expansion__number">{index + 1}</span>
                  <strong>{member.title || '—'}</strong>
                  <span className="relation-expansion__amount">{formatMoney(member.amount, '—')}</span>
                  <button type="button" className="relation-expansion__detail" disabled={!member.detailAvailable}
                    title={member.detailAvailable ? `${labels[column.kind]}详情` : '详情暂不可用'}
                    aria-label={`查看${labels[column.kind]} ${member.title || member.id} 详情`}
                    onClick={() => onOpenDetail({ kind: column.kind, id: member.id })}><Info size={14} aria-hidden="true" /></button>
                </div>
                {member.subtitle && <p className="relation-expansion__description">{member.subtitle}</p>}
                <div className="relation-expansion__metadata">
                  {member.date && <span>{member.date}</span>}{member.status && <span className={column.kind === "invoice" ? `relation-expansion__invoice-status relation-expansion__invoice-status--${member.status === "红字" ? "red" : "blue"}` : undefined}>{member.status}</span>}
                  {relationIds.length > 1 && (member.relationIds ?? (member.relationId ? [member.relationId] : [])).map(id => <span key={id}>关系 {relationIds.indexOf(id) + 1}</span>)}
                </div>
              </li>)}</ul>}
          </div>)}
        </div>}
    </section>
  </div>;
}
