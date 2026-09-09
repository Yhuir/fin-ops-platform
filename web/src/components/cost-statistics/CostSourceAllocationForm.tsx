import { Plus, Trash2 } from 'lucide-react';
import { Fragment, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CostStatisticsManualAllocationTask, CostStatisticsManualAllocationUnit } from '../../features/cost-statistics/types';
import { cents, money, usedBySource, validateSourceDraft, type SourceDraft, type SourceDraftLine } from '../../features/cost-statistics/sourceAllocation';
import { formatDateTimeText } from '../../features/dateTime';

type Props = {
  task: CostStatisticsManualAllocationTask; draft: SourceDraft; disabled: boolean; saving: boolean;
  error?: string; notice?: string; onChange: (draft: SourceDraft) => void; onSave: () => void;
};
type LineKind = 'costLines' | 'refundLinks' | 'nonCostLines';

function OAEvidenceGroup({ units }: { units: CostStatisticsManualAllocationUnit[] }) {
  const [expanded, setExpanded] = useState(false);
  return <article className="cost-source-oa-group">
    <div className="cost-source-oa-heading"><span>{units[0].oaApplyType}</span><span>{units[0].oaApplicant}</span></div>
    {units.map(unit => <div key={unit.unitId} className="cost-source-oa-item">
      <div className="cost-source-evidence-title"><strong>{unit.projectName}</strong><strong className="cost-source-money">¥{unit.oaOriginalAmount}</strong></div>
      <span className="cost-source-muted">{unit.oaApplyType} · {unit.expenseType}</span>
      {unit.expenseContent ? <p>{expanded || unit.expenseContent.length <= 72 ? unit.expenseContent : `${unit.expenseContent.slice(0, 72)}…`}</p> : null}
    </div>)}
    {units.some(unit => unit.expenseContent.length > 72) ? <button type="button" className="cost-source-link" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? '收起' : '展开全文'}</button> : null}
  </article>;
}

export default function CostSourceAllocationForm({ task, draft, disabled, saving, error, notice, onChange, onSave }: Props) {
  const [submitted, setSubmitted] = useState(0);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const root = useRef<HTMLDivElement>(null);
  const focusTarget = useRef<string | null>(null);
  const focusErrors = useRef(false);
  const nextId = useRef(Math.max(0, ...draft.costLines.map(line => line.id), ...draft.refundLinks.map(line => line.id), ...draft.nonCostLines.map(line => line.id)) + 1);
  const errors = useMemo(() => validateSourceDraft(task, draft), [task, draft]);
  const used = useMemo(() => usedBySource(draft), [draft]);
  const sources = useMemo(() => task.bankEvents.filter(event => event.eventKind === 'outflow'), [task.bankEvents]);
  const sourceOptions = useMemo(() => sources.map((event, index) => ({
    event, amount: cents(event.amount)!,
    description: `${index + 1}. ${event.bankAccountLabel || '账户待完善'} · ${event.tradeTime ? formatDateTimeText(event.tradeTime) : '日期待完善'} · ¥${event.amount}${event.counterpartyName ? ` · ${event.counterpartyName}` : ''}`,
  })), [sources]);
  const refunds = task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund');
  const oaGroups = useMemo(() => {
    const groups = new Map<string, CostStatisticsManualAllocationUnit[]>();
    for (const unit of task.units) {
      const group = groups.get(unit.oaId);
      if (group) group.push(unit); else groups.set(unit.oaId, [unit]);
    }
    return [...groups.entries()];
  }, [task.units]);
  useLayoutEffect(() => {
    if (focusTarget.current) {
      const target = [...(root.current?.querySelectorAll<HTMLElement>('[data-focus-key]') ?? [])].find(element => element.dataset.focusKey === focusTarget.current);
      target?.focus(); focusTarget.current = null;
    } else if (focusErrors.current) root.current?.querySelector<HTMLElement>('[role="alert"]')?.focus();
    focusErrors.current = false;
  }, [draft, submitted]);
  const touch = (key: string) => setTouched(current => new Set(current).add(key));
  const showError = (key: string) => (submitted > 0 || touched.has(key)) && errors[key] ? <p className="cost-source-error" role="alert" tabIndex={-1}>{errors[key]}</p> : null;
  const updateLine = (kind: LineKind, id: number, patch: Partial<SourceDraftLine>) => onChange({ ...draft, [kind]: draft[kind].map(line => line.id === id ? { ...line, ...patch } : line) });
  const add = (kind: LineKind, ownerId: string) => {
    const id = nextId.current++;
    focusTarget.current = `${kind}.${id}`;
    onChange({ ...draft, zeroUnitIds: kind === 'costLines' ? draft.zeroUnitIds.filter(unitId => unitId !== ownerId) : draft.zeroUnitIds, [kind]: [...draft[kind], { id, ownerId, bankTransactionId: '', amount: '' }] });
  };
  const remove = (kind: LineKind, line: SourceDraftLine) => {
    const siblings = draft[kind].filter(item => item.ownerId === line.ownerId && item.id !== line.id);
    focusTarget.current = siblings.length ? `${kind}.${siblings[siblings.length - 1].id}` : `add.${kind}.${line.ownerId}`;
    onChange({ ...draft, [kind]: draft[kind].filter(item => item.id !== line.id) });
  };
  const addButton = (kind: LineKind, ownerId: string) => <button type="button" className="cost-source-link" data-focus-key={`add.${kind}.${ownerId}`} disabled={disabled} onClick={() => add(kind, ownerId)}><Plus size={12} />新增来源</button>;
  const lineCells = (kind: LineKind, line: SourceDraftLine, index: number) => {
    const source = sources.find(event => event.transactionId === line.bankTransactionId);
    const key = `${kind}.${line.id}`;
    return <>
      <td><select data-focus-key={key} aria-label={`来源流水 ${index + 1}`} value={line.bankTransactionId} disabled={disabled}
        aria-invalid={(submitted > 0 || touched.has(key)) && !!errors[key]} onChange={event => updateLine(kind, line.id, { bankTransactionId: event.target.value })} onBlur={() => touch(key)}>
        <option value="">请选择来源流水</option>
        {sourceOptions.map(({ event, amount, description }) => {
          const selected = event.transactionId === line.bankTransactionId;
          const duplicate = draft[kind].some(other => other.id !== line.id && other.ownerId === line.ownerId && other.bankTransactionId === event.transactionId);
          const full = (used.get(event.transactionId) ?? 0n) >= amount;
          const reason = !selected && duplicate ? '本项已使用' : !selected && full ? '已用完' : '';
          return <option key={event.transactionId} value={event.transactionId} disabled={!!reason}>{description}{reason ? `（${reason}）` : ''}</option>;
        })}
      </select>{showError(key)}</td>
      <td className="cost-source-tag">{source ? source.tags.length ? source.tags.join(' / ') : '银行标签待完善' : '—'}</td>
      <td><input aria-label={`分配金额 ${index + 1}`} inputMode="decimal" placeholder="0.00" value={line.amount} disabled={disabled}
        onChange={event => updateLine(kind, line.id, { amount: event.target.value })} onBlur={() => { touch(key); const amount = cents(line.amount); if (amount !== null) updateLine(kind, line.id, { amount: money(amount) }); }} /></td>
      <td><button type="button" className="cost-source-icon" aria-label={`删除来源行 ${index + 1}`} disabled={disabled} onClick={() => remove(kind, line)}><Trash2 size={13} /></button></td>
    </>;
  };
  const auxiliaryLines = (kind: 'refundLinks' | 'nonCostLines', ownerId: string) => <div className="cost-source-table-scroll"><table className="cost-source-table cost-source-aux-table">
    <thead><tr><th>来源流水</th><th>银行标签</th><th>分配金额</th><th>操作</th></tr></thead>
    <tbody>{draft[kind].filter(line => line.ownerId === ownerId).map((line, index) => <tr key={line.id}>{lineCells(kind, line, index)}</tr>)}
      <tr className="cost-source-add-row"><td colSpan={4}>{addButton(kind, ownerId)}</td></tr></tbody>
  </table></div>;
  return <div className="cost-source-form" ref={root}>
    {task.pendingReasons.includes('bank_tag_missing') ? <p className="cost-source-notice">银行标签待完善</p> : null}
    {task.pendingReasons.includes('allocation_stale') ? <p className="cost-source-notice">关联事实已变化，请重新核对分配</p> : null}
    <div className="cost-source-evidence">
      <section><h3>OA · {oaGroups.length} 张 OA · {task.units.length} 个成本项</h3>{oaGroups.map(([id, units]) => <OAEvidenceGroup key={id} units={units} />)}</section>
      <section><h3>银行流水 · {task.bankEvents.length} 条</h3>{task.bankEvents.map((event, index) => <article className="cost-source-bank-row" key={event.transactionId}>
        <div><div className="cost-source-evidence-title"><strong>{index + 1}. {event.bankAccountLabel || '账户待完善'}</strong>{event.eventKind === 'wrong_payment_refund' ? <span className="cost-source-refund">退款</span> : null}<span>{event.counterpartyName}</span></div>
          <p>{event.tradeTime ? formatDateTimeText(event.tradeTime) : '付款日期待完善'}</p><p className="cost-source-tag">{event.tags.length ? event.tags.join(' / ') : '银行标签待完善'}</p>{showError(`source.${event.transactionId}`)}</div>
        <strong className="cost-source-money">{event.eventKind === 'wrong_payment_refund' ? '−' : ''}¥{event.amount}</strong>
      </article>)}</section>
    </div>
    <section className="cost-source-allocation"><h3>成本分配明细</h3>
      <div className="cost-source-table-scroll"><table className="cost-source-table" aria-label="成本分配明细">
        <colgroup><col className="cost-source-project-col" /><col className="cost-source-unit-col" /><col /><col className="cost-source-tag-col" /><col className="cost-source-amount-col" /><col className="cost-source-action-col" /></colgroup>
        <thead><tr><th>项目</th><th>OA / 成本项</th><th>来源流水</th><th>银行标签</th><th>分配金额</th><th>操作</th></tr></thead>
        {task.units.map((unit, unitIndex) => {
          const lines = draft.costLines.filter(line => line.ownerId === unit.unitId);
          const zero = draft.zeroUnitIds.includes(unit.unitId) || task.amountsFixed && cents(unit.oaOriginalAmount) === 0n;
          const identity = <><td title={unit.projectName}>{unit.projectName}</td><td><strong title={unit.expenseContent}>{unitIndex + 1}. {unit.expenseContent || unit.oaApplyType}</strong><span>{unit.oaApplicant} · {unit.oaApplyType}</span></td></>;
          return <tbody key={unit.unitId}>
            {lines.length ? lines.map((line, index) => <tr key={line.id}>{index === 0 ? identity : <><td /><td /></>}{lineCells('costLines', line, index)}</tr>) : <tr className={zero ? 'cost-source-zero' : 'cost-source-unallocated'}>{identity}<td colSpan={4}>{zero ? '零成本' : '未分配'}</td></tr>}
            <tr className="cost-source-add-row"><td /><td /><td colSpan={4}>{addButton('costLines', unit.unitId)}
              {!task.amountsFixed && !lines.length ? <button type="button" className="cost-source-link cost-source-zero-button" disabled={disabled} onClick={() => onChange({ ...draft, zeroUnitIds: zero ? draft.zeroUnitIds.filter(id => id !== unit.unitId) : [...draft.zeroUnitIds, unit.unitId] })}>{zero ? '取消零成本' : '设为零成本'}</button> : null}
              {showError(`unit.${unit.unitId}`)}</td></tr>
          </tbody>;
        })}
      </table></div>
      {refunds.length ? <details className="cost-source-extra" open><summary>退款归属</summary>{refunds.map(refund => <Fragment key={refund.transactionId}><p>{refund.bankAccountLabel || '账户待完善'} · {refund.tradeTime ? formatDateTimeText(refund.tradeTime) : '日期待完善'} · ¥{refund.amount}</p>{auxiliaryLines('refundLinks', refund.transactionId)}{showError(`refund.${refund.transactionId}`)}</Fragment>)}</details> : null}
      <details className="cost-source-extra" open={cents(draft.nonCostAmount) !== 0n || undefined}><summary>不计入成本</summary><div className="cost-source-non-cost"><input aria-label="不计入成本金额" inputMode="decimal" value={draft.nonCostAmount} disabled={disabled} onChange={event => onChange({ ...draft, nonCostAmount: event.target.value })} /><input aria-label="不计入成本原因" placeholder="原因" value={draft.nonCostReason} disabled={disabled} onChange={event => onChange({ ...draft, nonCostReason: event.target.value })} /></div>{auxiliaryLines('nonCostLines', '')}{showError('nonCost')}</details>
      {showError('total')}{error ? <p className="cost-source-error" role="alert">{error}</p> : null}{notice ? <p className="cost-source-notice" role="status">{notice}</p> : null}
    </section>
    <footer><button type="button" className="cost-source-save" disabled={disabled} onClick={() => { focusErrors.current = !!Object.keys(errors).length; setSubmitted(value => value + 1); if (!Object.keys(errors).length) onSave(); }}>{saving ? '保存中…' : '保存分配'}</button></footer>
  </div>;
}
