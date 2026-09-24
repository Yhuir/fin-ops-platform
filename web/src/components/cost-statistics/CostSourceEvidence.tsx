import { Button, Popover } from '@heroui/react';
import { memo, useMemo, type ReactNode } from 'react';
import { groupSourceEvidence } from '../../features/cost-statistics/sourceEvidence';
import type { CostStatisticsManualAllocationTask } from '../../features/cost-statistics/types';
import { formatDateTimeText } from '../../features/dateTime';
import { FinanceStatusTag } from '../common/FinanceTable';

export function shortBankAccount(label: string) {
  return label.replace(/\s*账户\s*(\d{4})$/, ' $1');
}
export const CostChips = memo(function CostChips({ values }: { values: string[] }) {
  return <span className="cost-source-chips">{values.filter(Boolean).map((value, index) => <FinanceStatusTag key={index}>{value}</FinanceStatusTag>)}</span>;
}, (previous, next) => previous.values.length === next.values.length && previous.values.every((value, index) => value === next.values[index]));
export const CostText = memo(function CostText({ text, label }: { text: string; label: string }) {
  if (!text) return <span>—</span>;
  return <Popover>
    <Button className="cost-source-text" aria-label={label} variant="ghost">{text}</Button>
    <Popover.Content className="cost-source-popover" placement="bottom start"><Popover.Dialog aria-label={label}>{text}</Popover.Dialog></Popover.Content>
  </Popover>;
});

// Formal relation display does not depend on editable cost allocation choices.
export const CostSourceEvidence = memo(function CostSourceEvidence({ task, sourceError }: { task: CostStatisticsManualAllocationTask; sourceError: (id: string) => ReactNode }) {
  const groups = useMemo(() => groupSourceEvidence(task), [task]);
  const unitContent = (index: number) => {
    const unit = task.units[index];
    return [
      <><span className="cost-source-evidence-identity">{index + 1}. {unit.projectName}</span><span className="cost-source-applicant">{unit.oaApplicant}</span><CostChips values={[unit.oaApplyType, unit.expenseType]} /></>,
      <CostText text={unit.expenseContent} label={`OA ${index + 1} 费用全文`} />,
      <span className="cost-source-money">¥{unit.oaOriginalAmount}</span>,
    ];
  };
  const bankContent = (index: number) => {
    const bank = task.bankEvents[index];
    return [
      <><span className="cost-source-evidence-identity">{index + 1}. <CostChips values={[shortBankAccount(bank.bankAccountLabel)]} /></span><CostChips values={[bank.tradeTime ? formatDateTimeText(bank.tradeTime) : '日期待完善']} /></>,
      <><span className="cost-source-counterparty">{bank.counterpartyName}</span><CostChips values={[bank.bankTagPrimaryLabel, bank.bankTagSubLabel]} />{bank.eventKind === 'wrong_payment_refund' ? <FinanceStatusTag tone="success">退款</FinanceStatusTag> : null}</>,
      <><span className="cost-source-money">{bank.eventKind === 'wrong_payment_refund' ? '−' : ''}¥{bank.amount}</span>{sourceError(bank.transactionId)}</>,
    ];
  };
  const cells = (content: ReactNode[], side: string, span: number) => content.map((value, index) => <td key={index} rowSpan={span} className={`cost-evidence-${side} cost-evidence-col-${index}`}>{value}</td>);
  return <section className="cost-source-evidence" aria-label="当前配对关系">
    <div className="cost-evidence-headings"><h3>OA · {task.units.length} 条</h3><h3>银行流水 · {task.bankEvents.length} 条</h3></div>
    <div className="cost-source-evidence-table"><table aria-label="OA 与流水对照">
      <colgroup><col /><col /><col className="cost-evidence-amount-col" /><col /><col /><col className="cost-evidence-amount-col" /></colgroup>
      <thead><tr>{['项目 / OA', '费用内容', 'OA 金额', '银行 / 时间', '对方 / 标签', '流水金额'].map((label, index) => <th key={label} scope="col" className={index >= 3 ? 'cost-evidence-bank' : ''}>{label}</th>)}</tr></thead>
      {groups.map(group => {
        const { unitIndexes, bankIndexes } = group;
        const many = unitIndexes.length > 1 && bankIndexes.length > 1;
        const matched = unitIndexes.length > 0 && bankIndexes.length > 0;
        return <tbody key={unitIndexes.length ? `oa-${unitIndexes[0]}` : `bank-${bankIndexes[0]}`} data-evidence-kind={many ? 'many' : matched ? 'matched' : 'unassigned'}>
          {many ? <>
            <tr><th colSpan={6} className="cost-evidence-group-label" scope="rowgroup">关联明细 · {unitIndexes.length} 项 / {bankIndexes.length} 笔</th></tr>
            <tr><td colSpan={3} className="cost-evidence-group-cell">{unitIndexes.map(index => <div className="cost-evidence-group-item" key={index}>{unitContent(index).map((value, i) => <div key={i}>{value}</div>)}</div>)}</td>
              <td colSpan={3} className="cost-evidence-group-cell cost-evidence-bank">{bankIndexes.map(index => <div className="cost-evidence-group-item" key={index}>{bankContent(index).map((value, i) => <div key={i}>{value}</div>)}</div>)}</td></tr>
          </> : Array.from({ length: Math.max(unitIndexes.length, bankIndexes.length) }, (_, row) => {
            const span = Math.max(unitIndexes.length, bankIndexes.length);
            return <tr key={row}>
              {unitIndexes.length ? (unitIndexes.length === 1 ? row === 0 && cells(unitContent(unitIndexes[0]), 'oa', span) : cells(unitContent(unitIndexes[row]), 'oa', 1)) : row === 0 && <td colSpan={3} rowSpan={span} className="cost-evidence-unassigned">{bankIndexes.some(index => task.bankEvents[index].eventKind === 'wrong_payment_refund') ? '退款来源' : '尚未对应 OA'}</td>}
              {bankIndexes.length ? (bankIndexes.length === 1 ? row === 0 && cells(bankContent(bankIndexes[0]), 'bank', span) : cells(bankContent(bankIndexes[row]), 'bank', 1)) : row === 0 && <td colSpan={3} rowSpan={span} className="cost-evidence-bank cost-evidence-unassigned">{group.sourcesExcluded ? '—' : '尚未对应流水'}</td>}
            </tr>;
          })}
        </tbody>;
      })}
    </table></div>
  </section>;
});
