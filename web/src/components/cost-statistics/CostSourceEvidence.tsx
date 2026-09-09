import { Button, Popover } from '@heroui/react';
import { memo, type ReactNode } from 'react';
import type { CostStatisticsManualAllocationTask } from '../../features/cost-statistics/types';
import { formatDateTimeText } from '../../features/dateTime';
import { FinanceStatusTag, FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from '../common/FinanceTable';

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

// Evidence is immutable while editing amounts; keep the readonly tables out of that render path.
export const CostSourceEvidence = memo(function CostSourceEvidence({ task, sourceError }: {
  task: CostStatisticsManualAllocationTask; sourceError: (id: string) => ReactNode;
}) {
  return <div className="cost-source-evidence">
    <section><h3>OA · {task.units.length} 条</h3>
      <FinanceTable ariaLabel="OA" className="cost-source-evidence-table" minWidth={460} selectableText>
        <FinanceTableHeader>
          <FinanceTableColumn columnRole="identity" isRowHeader>项目 / OA</FinanceTableColumn>
          <FinanceTableColumn columnRole="description">费用内容</FinanceTableColumn>
          <FinanceTableColumn columnRole="amount">金额</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>{task.units.map((unit, index) => <FinanceTableRow key={unit.unitId} id={unit.unitId} textValue={unit.projectName}>
          <FinanceTableCell columnRole="identity"><span className="cost-source-evidence-identity">{index + 1}. {unit.projectName}</span><span className="cost-source-applicant">{unit.oaApplicant}</span><CostChips values={[unit.oaApplyType, unit.expenseType]} /></FinanceTableCell>
          <FinanceTableCell columnRole="description"><CostText text={unit.expenseContent} label={`OA ${index + 1} 费用全文`} /></FinanceTableCell>
          <FinanceTableCell columnRole="amount"><span className="cost-source-money">¥{unit.oaOriginalAmount}</span></FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>
    </section>
    <section><h3>银行流水 · {task.bankEvents.length} 条</h3>
      <FinanceTable ariaLabel="银行流水" className="cost-source-evidence-table" minWidth={490} selectableText>
        <FinanceTableHeader>
          <FinanceTableColumn columnRole="account" isRowHeader>银行 / 时间</FinanceTableColumn>
          <FinanceTableColumn columnRole="identity">对方 / 标签</FinanceTableColumn>
          <FinanceTableColumn columnRole="amount">金额</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>{task.bankEvents.map((event, index) => <FinanceTableRow key={event.transactionId} id={event.transactionId} textValue={event.bankAccountLabel}>
          <FinanceTableCell columnRole="account"><span className="cost-source-evidence-identity">{index + 1}. <CostChips values={[shortBankAccount(event.bankAccountLabel)]} /></span><CostChips values={[event.tradeTime ? formatDateTimeText(event.tradeTime) : '日期待完善']} /></FinanceTableCell>
          <FinanceTableCell columnRole="identity"><span className="cost-source-counterparty">{event.counterpartyName}</span><CostChips values={[event.bankTagPrimaryLabel, event.bankTagSubLabel]} />{event.eventKind === 'wrong_payment_refund' ? <FinanceStatusTag tone="success">退款</FinanceStatusTag> : null}</FinanceTableCell>
          <FinanceTableCell columnRole="amount"><span className="cost-source-money">{event.eventKind === 'wrong_payment_refund' ? '−' : ''}¥{event.amount}</span>{sourceError(event.transactionId)}</FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>
    </section>
  </div>;
});
