import { Button, Popover } from '@heroui/react';
import { CircleAlert, Plus, Trash2 } from 'lucide-react';
import { Fragment, useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CostStatisticsManualAllocationTask } from '../../features/cost-statistics/types';
import { cents, money, usedBySource, validateSourceDraft, type SourceDraft, type SourceDraftLine } from '../../features/cost-statistics/sourceAllocation';
import { formatDateTimeText } from '../../features/dateTime';
import { CostChips, CostSourceEvidence, CostText, shortBankAccount } from './CostSourceEvidence';
import CostSourcePicker from './CostSourcePicker';

type Props = {
  task: CostStatisticsManualAllocationTask; draft: SourceDraft; disabled: boolean; saving: boolean;
  error?: string; notice?: string; onChange: (draft: SourceDraft) => void; onSave: () => void;
};
type LineKind = 'costLines' | 'refundLinks' | 'nonCostLines';

function FieldIssue({ message, field, open, onOpenChange }: { message: string; field: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  return <Popover isOpen={open} onOpenChange={onOpenChange}>
    <Button className="cost-source-issue" variant="ghost" aria-label={message} data-error-key={field}><CircleAlert size={15} /></Button>
    <Popover.Content className="cost-source-popover cost-source-issue-popover" placement="bottom end"><Popover.Dialog aria-label="分配校验"><span role="alert">{message}</span></Popover.Dialog></Popover.Content>
  </Popover>;
}

export default function CostSourceAllocationForm({ task, draft, disabled, saving, error, notice, onChange, onSave }: Props) {
  const [submitted, setSubmitted] = useState(0);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [openIssue, setOpenIssue] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const focusTarget = useRef<string | null>(null);
  const focusErrors = useRef(false);
  const nextId = useRef(Math.max(0, ...draft.costLines.map(line => line.id), ...draft.refundLinks.map(line => line.id), ...draft.nonCostLines.map(line => line.id)) + 1);
  const errors = useMemo(() => validateSourceDraft(task, draft), [task, draft]);
  const used = useMemo(() => usedBySource(draft), [draft]);
  const sources = useMemo(() => task.bankEvents.filter(event => event.eventKind === 'outflow'), [task.bankEvents]);
  const sourceOptions = useMemo(() => task.bankEvents.flatMap((event, index) => event.eventKind === 'outflow' ? [{
    id: event.transactionId, label: `${index + 1}. ${shortBankAccount(event.bankAccountLabel)}`, amount: event.amount, amountCents: cents(event.amount)!,
    date: event.tradeTime ? formatDateTimeText(event.tradeTime) : '日期待完善', counterparty: event.counterpartyName,
    tags: [event.bankTagPrimaryLabel, event.bankTagSubLabel],
  }] : []), [task.bankEvents]);
  // Event handlers read the committed draft so closed pickers can skip unrelated edits.
  const editState = useRef({ draft, onChange, used, sourceOptions });
  useLayoutEffect(() => { editState.current = { draft, onChange, used, sourceOptions }; }, [draft, onChange, used, sourceOptions]);
  const sourceLineKind = (current: SourceDraft, id: number): LineKind => {
    const kind = (['costLines', 'refundLinks', 'nonCostLines'] as const).find(key => current[key].some(line => line.id === id));
    if (!kind) throw new Error('来源行已不存在');
    return kind;
  };
  const chooseSource = useCallback((id: number, sourceId: string) => {
    const current = editState.current;
    const kind = sourceLineKind(current.draft, id);
    setTouched(previous => new Set(previous).add(`${kind}.${id}.source`));
    current.onChange({ ...current.draft, [kind]: current.draft[kind].map(line => line.id === id ? { ...line, bankTransactionId: sourceId } : line) });
  }, []);
  const isSourceDisabled = useCallback((id: number, sourceId: string) => {
    const current = editState.current;
    const kind = sourceLineKind(current.draft, id);
    const line = current.draft[kind].find(item => item.id === id)!;
    if (line.bankTransactionId === sourceId) return false;
    if (current.draft[kind].some(other => other.id !== id && other.ownerId === line.ownerId && other.bankTransactionId === sourceId)) return true;
    const source = current.sourceOptions.find(option => option.id === sourceId)!;
    return (current.used.get(sourceId) ?? 0n) >= source.amountCents;
  }, []);
  const refunds = task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund');
  useLayoutEffect(() => {
    if (focusTarget.current) {
      const target = [...(root.current?.querySelectorAll<HTMLElement>('[data-focus-key]') ?? [])].find(element => element.dataset.focusKey === focusTarget.current);
      target?.focus(); focusTarget.current = null;
    } else if (focusErrors.current) {
      const target = root.current?.querySelector<HTMLElement>('.cost-source-allocation [data-error-key]') ?? root.current?.querySelector<HTMLElement>('[data-error-key]');
      if (target) { target.focus(); setOpenIssue(target.dataset.errorKey!); }
      else root.current?.querySelector<HTMLElement>('[role="alert"]')?.focus();
    }
    focusErrors.current = false;
  }, [draft, submitted]);
  const touch = (key: string) => setTouched(current => new Set(current).add(key));
  const visibleError = (key: string) => (submitted > 0 || touched.has(key)) && !!errors[key];
  const showError = (key: string) => visibleError(key) ? <FieldIssue message={errors[key]} field={key} open={openIssue === key} onOpenChange={open => setOpenIssue(open ? key : null)} /> : null;
  // Only visible evidence issues affect the readonly tables; amount keystrokes usually do not.
  const evidenceIssueText = JSON.stringify(submitted ? Object.fromEntries(Object.entries(errors).filter(([key]) => key.startsWith('source.'))) : {});
  const evidenceIssues = useMemo<Record<string, string>>(() => JSON.parse(evidenceIssueText), [evidenceIssueText]);
  const evidenceOpenIssue = openIssue?.startsWith('source.') ? openIssue : null;
  const sourceError = useCallback((id: string) => {
    const key = `source.${id}`;
    return evidenceIssues[key] ? <FieldIssue message={evidenceIssues[key]} field={key} open={evidenceOpenIssue === key} onOpenChange={open => setOpenIssue(open ? key : null)} /> : null;
  }, [evidenceIssues, evidenceOpenIssue]);
  const updateLine = (kind: LineKind, id: number, patch: Partial<SourceDraftLine>) => onChange({ ...draft, [kind]: draft[kind].map(line => line.id === id ? { ...line, ...patch } : line) });
  const add = (kind: LineKind, ownerId: string) => {
    const id = nextId.current++;
    focusTarget.current = `${kind}.${id}`;
    onChange({ ...draft, zeroUnitIds: kind === 'costLines' ? draft.zeroUnitIds.filter(unitId => unitId !== ownerId) : draft.zeroUnitIds, [kind]: [...draft[kind], { id, ownerId, bankTransactionId: '', amount: '' }] });
  };
  const remove = (kind: LineKind, line: SourceDraftLine) => {
    const siblings = draft[kind].filter(item => item.ownerId === line.ownerId && item.id !== line.id);
    focusTarget.current = siblings.length ? `${kind}.${siblings[siblings.length - 1].id}` : `add.${kind}.${line.ownerId}`;
    setOpenIssue(null);
    onChange({ ...draft, [kind]: draft[kind].filter(item => item.id !== line.id) });
  };
  const addButton = (kind: LineKind, ownerId: string) => <button type="button" className="cost-source-icon cost-source-add" aria-label="新增来源" title="新增来源" data-focus-key={`add.${kind}.${ownerId}`} disabled={disabled} onClick={() => add(kind, ownerId)}><Plus size={16} /></button>;
  const lineCells = (kind: LineKind, line: SourceDraftLine, index: number, first: boolean) => {
    const source = sources.find(event => event.transactionId === line.bankTransactionId);
    const key = `${kind}.${line.id}`;
    return <>
      <td><div className="cost-source-field"><CostSourcePicker value={line.bankTransactionId} options={sourceOptions} lineId={line.id} isSourceDisabled={isSourceDisabled} label={`来源流水 ${index + 1}`} focusKey={key} invalid={visibleError(`${key}.source`)} disabled={disabled}
        onChange={chooseSource} />{showError(`${key}.source`)}</div>{showError(`${key}.owner`)}</td>
      <td>{source ? <CostChips values={[source.bankTagPrimaryLabel, source.bankTagSubLabel]} /> : <span className="cost-source-muted">—</span>}</td>
      <td><div className="cost-source-field"><input aria-label={`分配金额 ${index + 1}`} aria-invalid={visibleError(`${key}.amount`)} inputMode="decimal" placeholder="0.00" value={line.amount} disabled={disabled}
        onChange={event => { touch(`${key}.edited`); updateLine(kind, line.id, { amount: event.target.value }); }} onBlur={() => { if (touched.has(`${key}.edited`)) touch(`${key}.amount`); const amount = cents(line.amount); if (amount !== null) updateLine(kind, line.id, { amount: money(amount) }); }} />{showError(`${key}.amount`)}</div></td>
      <td><div className="cost-source-actions">{first ? addButton(kind, line.ownerId) : null}<button type="button" className="cost-source-icon" aria-label={`删除来源行 ${index + 1}`} disabled={disabled} onClick={() => remove(kind, line)}><Trash2 size={14} /></button></div></td>
    </>;
  };
  const auxiliaryLines = (kind: 'refundLinks' | 'nonCostLines', ownerId: string) => {
    const lines = draft[kind].filter(line => line.ownerId === ownerId);
    return <div className="cost-source-table-scroll"><table className="cost-source-table cost-source-aux-table" aria-label={kind === 'refundLinks' ? '退款来源' : '非成本来源'}>
      <thead><tr><th>来源流水</th><th>银行标签</th><th>分配金额</th><th>操作 {lines.length ? null : addButton(kind, ownerId)}</th></tr></thead>
      <tbody>{lines.map((line, index) => <tr key={line.id}>{lineCells(kind, line, index, index === 0)}</tr>)}</tbody>
    </table></div>;
  };
  return <div className="cost-source-form" ref={root}>
    {task.pendingReasons.includes('scope_refund_required') ? <p className="cost-source-notice">请先确认退款对应的原支出</p> : null}
    {task.pendingReasons.includes('bank_tag_missing') ? <p className="cost-source-notice">银行标签待完善</p> : null}
    {task.pendingReasons.includes('allocation_stale') ? <p className="cost-source-notice">数据已变化，请重新核对</p> : null}
    <CostSourceEvidence task={task} costLines={draft.costLines} nonCostLines={draft.nonCostLines} sourceError={sourceError} />
    <section className="cost-source-allocation"><h3>成本分配明细</h3>
      <div className="cost-source-table-scroll"><table className="cost-source-table" aria-label="成本分配明细">
        <colgroup><col className="cost-source-project-col" /><col className="cost-source-unit-col" /><col /><col className="cost-source-tag-col" /><col className="cost-source-amount-col" /><col className="cost-source-action-col" /></colgroup>
        <thead><tr><th>项目</th><th>OA / 成本项</th><th>来源流水</th><th>银行标签</th><th>分配金额</th><th>操作</th></tr></thead>
        {task.units.map((unit, unitIndex) => {
          const lines = draft.costLines.filter(line => line.ownerId === unit.unitId);
          const zero = draft.zeroUnitIds.includes(unit.unitId) || task.amountsFixed && cents(unit.oaOriginalAmount) === 0n;
          const identity = <><td className="cost-source-project-cell cost-source-identity-cell" rowSpan={Math.max(1, lines.length)} title={unit.projectName}>{unit.projectName}</td><td className="cost-source-identity-cell" rowSpan={Math.max(1, lines.length)}><CostText text={`${unitIndex + 1}. ${unit.expenseContent || unit.oaApplyType}`} label={`成本项 ${unitIndex + 1} 全文`} /><span className="cost-source-applicant">{unit.oaApplicant}</span><CostChips values={[unit.oaApplyType]} />{showError(`unit.${unit.unitId}`)}</td></>;
          return <tbody key={unit.unitId}>
            {lines.length ? lines.map((line, index) => <tr key={line.id}>{index === 0 ? identity : null}{lineCells('costLines', line, index, index === 0)}</tr>) : <tr className={zero ? 'cost-source-zero' : 'cost-source-unallocated'}>{identity}<td colSpan={3}><span>{zero ? '零成本' : '未分配'}</span>{!task.amountsFixed ? <button type="button" className="cost-source-link cost-source-zero-button" disabled={disabled} onClick={() => onChange({ ...draft, zeroUnitIds: zero ? draft.zeroUnitIds.filter(id => id !== unit.unitId) : [...draft.zeroUnitIds, unit.unitId] })}>{zero ? '取消零成本' : '设为零成本'}</button> : null}</td><td>{addButton('costLines', unit.unitId)}</td></tr>}
          </tbody>;
        })}
      </table></div>
      {refunds.length ? <details className="cost-source-extra" open><summary>退款归属</summary>{refunds.map(refund => <Fragment key={refund.transactionId}><div className="cost-source-extra-heading"><CostChips values={[shortBankAccount(refund.bankAccountLabel), refund.tradeTime ? formatDateTimeText(refund.tradeTime) : '日期待完善']} /><span className="cost-source-money">¥{refund.amount}</span>{showError(`refund.${refund.transactionId}`)}</div>{auxiliaryLines('refundLinks', refund.transactionId)}</Fragment>)}</details> : null}
      <details className="cost-source-extra" open={cents(draft.nonCostAmount) !== 0n || undefined}><summary>不计入成本 {showError('nonCost')}</summary><div className="cost-source-non-cost"><input aria-label="不计入成本金额" inputMode="decimal" value={draft.nonCostAmount} disabled={disabled} onChange={event => onChange({ ...draft, nonCostAmount: event.target.value })} /><input aria-label="不计入成本原因" placeholder="原因" value={draft.nonCostReason} disabled={disabled} onChange={event => onChange({ ...draft, nonCostReason: event.target.value })} /></div>{auxiliaryLines('nonCostLines', '')}</details>
    </section>
    <footer><div>{submitted > 0 && errors.total ? <p className="cost-source-error" role="alert" tabIndex={-1}>{errors.total}</p> : null}{error ? <p className="cost-source-error" role="alert">{error}</p> : null}{notice ? <p className="cost-source-notice" role="status">{notice}</p> : null}</div><div className="cost-source-save-actions"><span className="cost-source-balanced" role="status">{!Object.keys(errors).length && !saving && !error && !notice ? '分配金额一致' : ''}</span><button type="button" className="cost-source-save" disabled={disabled} onClick={() => { focusErrors.current = !!Object.keys(errors).length; setSubmitted(value => value + 1); if (!Object.keys(errors).length) onSave(); }}>{saving ? '保存中…' : '保存分配'}</button></div></footer>
  </div>;
}
