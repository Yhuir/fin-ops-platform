import { Button, Input, ListBox, Select, TextArea } from '@heroui/react';
import { Plus, Trash2 } from 'lucide-react';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CostStatisticsManualAllocationTask } from '../../features/cost-statistics/types';
import { cents, money, usedBySource, validateSourceDraft, type SourceDraft, type SourceDraftLine } from '../../features/cost-statistics/sourceAllocation';

import { formatDateTimeText } from '../../features/dateTime';

type Props = {
  task: CostStatisticsManualAllocationTask; draft: SourceDraft; disabled: boolean; saving: boolean;
  error?: string; notice?: string; onChange: (draft: SourceDraft) => void; onSave: () => void;
};
type LineKind = 'costLines' | 'refundLinks' | 'nonCostLines';
export default function CostSourceAllocationForm({ task, draft, disabled, saving, error, notice, onChange, onSave }: Props) {
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const root = useRef<HTMLDivElement>(null);
  const focusTarget = useRef<string | null>(null);
  const errors = useMemo(() => validateSourceDraft(task, draft), [task, draft]);
  const used = useMemo(() => usedBySource(draft), [draft]);
  const sources = task.bankEvents.filter(event => event.eventKind === 'outflow');
  const refunds = task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund');
  useLayoutEffect(() => {
    if (!focusTarget.current) return;
    const target = [...(root.current?.querySelectorAll<HTMLElement>('[data-focus-key]') ?? [])].find(element => element.dataset.focusKey === focusTarget.current);
    (target?.matches('button') ? target : target?.querySelector<HTMLElement>('button'))?.focus();
    focusTarget.current = null;
  }, [draft]);
  const touch = (key: string) => setTouched(current => new Set(current).add(key));
  const showError = (key: string) => (submitted || touched.has(key)) && errors[key] ? <p className="cost-source-error" role="alert">{errors[key]}</p> : null;
  const updateLine = (kind: LineKind, id: number, patch: Partial<SourceDraftLine>) => onChange({ ...draft, [kind]: draft[kind].map(line => line.id === id ? { ...line, ...patch } : line) });
  const add = (kind: LineKind, ownerId: string) => {
    const id = Math.max(0, ...draft.costLines.map(line => line.id), ...draft.refundLinks.map(line => line.id), ...draft.nonCostLines.map(line => line.id)) + 1;
    focusTarget.current = `${kind}.${id}`;
    onChange({ ...draft, [kind]: [...draft[kind], { id, ownerId, bankTransactionId: '', amount: '' }] });
  };
  const remove = (kind: LineKind, line: SourceDraftLine) => {
    const siblings = draft[kind].filter(item => item.ownerId === line.ownerId && item.id !== line.id);
    focusTarget.current = siblings.length ? `${kind}.${siblings[siblings.length - 1].id}` : `add.${kind}.${line.ownerId}`;
    onChange({ ...draft, [kind]: draft[kind].filter(item => item.id !== line.id) });
  };
  const renderLines = (kind: LineKind, ownerId: string) => <div className="cost-source-lines">
    {draft[kind].filter(line => line.ownerId === ownerId).map((line, index) => {
      const source = sources.find(event => event.transactionId === line.bankTransactionId);
      const key = `${kind}.${line.id}`;
      return <div className="cost-source-line" key={line.id}>
        <div className="cost-source-line-inputs">
          <div data-focus-key={key}>
            <Select aria-label={`来源流水 ${index + 1}`} placeholder="请选择来源流水" selectedKey={line.bankTransactionId || null} isDisabled={disabled}
              onSelectionChange={value => { updateLine(kind, line.id, { bankTransactionId: String(value ?? '') }); touch(key); }}>
              <Select.Trigger><Select.Value>{source ? `${source.bankAccountLabel || "账户待完善"} · ${source.tradeTime ? formatDateTimeText(source.tradeTime) : "日期待完善"}` : "请选择来源流水"}</Select.Value><Select.Indicator /></Select.Trigger>
              <Select.Popover className="cost-source-popover"><ListBox>
                {sources.map(event => {
                  const remaining = cents(event.amount)! - (used.get(event.transactionId) ?? 0n);
                  const selected = event.transactionId === line.bankTransactionId;
                  return <ListBox.Item key={event.transactionId} id={event.transactionId} textValue={`${event.bankAccountLabel || '账户待完善'} · ${event.tradeTime ? formatDateTimeText(event.tradeTime) : '日期待完善'} · ${event.amount}`}
                    isDisabled={!selected && remaining <= 0n}>
                    <div className="cost-source-option"><strong>{event.bankAccountLabel || '账户待完善'}</strong><span>{event.tradeTime ? formatDateTimeText(event.tradeTime) : '日期待完善'} · {event.amount} 元 · 剩余 {money(remaining)}</span><small>{event.tags.length ? event.tags.join(' / ') : '银行标签待完善'}</small><small>{event.transactionId}</small></div>
                  </ListBox.Item>;
                })}
              </ListBox></Select.Popover>
            </Select>
          </div>
          <Input aria-label={`分配金额 ${index + 1}`} inputMode="decimal" placeholder="0.00" value={line.amount} disabled={disabled} onChange={event => updateLine(kind, line.id, { amount: event.target.value })} onBlur={() => touch(key)} />
          <Button aria-label={`删除来源行 ${index + 1}`} isIconOnly size="sm" variant="ghost" isDisabled={disabled} onPress={() => remove(kind, line)}><Trash2 size={15} /></Button>
        </div>
        {source ? <div className="cost-source-line-meta"><span>{source.bankAccountLabel || '账户待完善'}</span><span>{source.tradeTime ? formatDateTimeText(source.tradeTime) : '日期待完善'}</span><span>{source.tags.length ? source.tags.join(' / ') : '银行标签待完善'}</span></div> : null}
        {showError(key)}
      </div>;
    })}
    {!draft[kind].some(line => line.ownerId === ownerId) ? <p className="cost-source-muted">暂无分配行</p> : null}
    <Button data-focus-key={`add.${kind}.${ownerId}`} size="sm" variant="secondary" isDisabled={disabled} onPress={() => add(kind, ownerId)}><Plus size={14} />新增来源</Button>
  </div>;
  return <div className="cost-source-form" ref={root}>
    {task.pendingReasons.includes('bank_tag_missing') ? <p className="cost-source-notice">来源分配可以保存；请在银行明细完善缺失标签，完成后刷新本页。</p> : null}
    {task.pendingReasons.includes('allocation_stale') ? <p className="cost-source-notice">关联事实已变化，请根据当前流水重新核对分配。</p> : null}
    <section className="cost-source-evidence"><h3>银行流水证据</h3><div className="cost-source-evidence-grid">
      {task.bankEvents.map(event => {
        const amountUsed = used.get(event.transactionId) ?? 0n;
        return <article key={event.transactionId} className={event.eventKind === 'wrong_payment_refund' ? 'cost-source-evidence-card is-refund' : 'cost-source-evidence-card'}>
          <strong>{event.bankAccountLabel || '银行账户待完善'}</strong><small>{event.transactionId}</small>
          <span>{event.eventKind === 'wrong_payment_refund' ? '付错退款 · ' : ''}{event.tradeTime ? formatDateTimeText(event.tradeTime) : '付款日期待完善'}</span>
          <span className="cost-source-money">{event.amount} 元</span>
          {event.eventKind === 'outflow' ? <span>已分 {money(amountUsed)} · 剩余 {money(cents(event.amount)! - amountUsed)}</span> : null}
          <div className="cost-source-line-meta">{event.tags.length ? event.tags.join(' / ') : '银行标签待完善'}</div>
          {showError(`source.${event.transactionId}`)}
        </article>;
      })}
    </div><p className="cost-source-muted">支出 {task.grossOutflowTotal} − 付错退款 {task.wrongPaymentRefundTotal} = 净支出 {task.netOutflowTotal}</p></section>
    <section className="cost-source-units"><h3>成本分配明细</h3>
      {task.units.map(unit => <article className="cost-source-unit" key={unit.unitId}>
        <header><div><strong>{unit.projectName}</strong><span>{unit.oaApplyType} · {unit.expenseType}</span><small>{unit.oaId} · {unit.oaApplicant}</small><span>{unit.expenseContent}</span></div>
          <div className="cost-source-target"><small>原 OA 金额 {unit.oaOriginalAmount}</small><label>本项成本 {task.amountsFixed ? <strong>{unit.oaOriginalAmount}</strong> : <Input aria-label={`${unit.projectName}本项成本`} value={draft.targets[unit.unitId]} disabled={disabled} inputMode="decimal" onChange={event => onChange({ ...draft, targets: { ...draft.targets, [unit.unitId]: event.target.value } })} onBlur={() => touch(`unit.${unit.unitId}`)} />}</label>
          <small>已分 {money(draft.costLines.filter(line => line.ownerId === unit.unitId).reduce((sum, line) => sum + (cents(line.amount) ?? 0n), 0n))}</small></div>
        </header>{renderLines('costLines', unit.unitId)}{showError(`unit.${unit.unitId}`)}
      </article>)}
      {refunds.length ? <details className="cost-source-unit" open={submitted || undefined}><summary>退款归属</summary>{refunds.map(refund => <section key={refund.transactionId}><p>{refund.transactionId} · 退款 {refund.amount}</p>{renderLines('refundLinks', refund.transactionId)}{showError(`refund.${refund.transactionId}`)}</section>)}</details> : null}
      <details className="cost-source-unit" open={cents(draft.nonCostAmount) !== 0n || undefined}><summary>不计入成本的金额</summary><div className="cost-source-non-cost"><Input aria-label="不计入成本金额" inputMode="decimal" value={draft.nonCostAmount} disabled={disabled} onChange={event => onChange({ ...draft, nonCostAmount: event.target.value })} /><TextArea aria-label="不计入成本原因" placeholder="请说明原因" value={draft.nonCostReason} disabled={disabled} onChange={event => onChange({ ...draft, nonCostReason: event.target.value })} /></div>{renderLines('nonCostLines', '')}{showError('nonCost')}</details>
      {showError('total')}{error ? <p className="cost-source-error" role="alert">{error}</p> : null}{notice ? <p className="cost-source-notice" role="status">{notice}</p> : null}
      <footer><Button variant="primary" isDisabled={disabled} onPress={() => { setSubmitted(true); if (!Object.keys(errors).length) onSave(); }}>{saving ? '保存中…' : '保存分配'}</Button></footer>
    </section>
  </div>;
}
