import userEvent from '@testing-library/user-event';
import { fireEvent, render, screen } from '@testing-library/react';
import RelationGroupCell from '../components/workbench/RelationGroupCell';
import RelationGroupGrid from '../components/workbench/RelationGroupGrid';
import { getWorkbenchColumns } from '../features/workbench/tableConfig';
import type { WorkbenchRecord, WorkbenchRelationGroup } from '../features/workbench/types';

const splitParts = [
  { id: 'principal-1', amount: '1000000.00', category_code: 'principal-1', category_label: '外部往来款 / 归还借款', category_path: ['外部往来款', '归还借款'] },
  { id: 'interest-1', amount: '1497.22', category_code: 'interest-1', category_label: '费用 / 利息', category_path: ['费用', '利息'] },
];

const record = (id: string, amount: string, category: string): WorkbenchRecord => ({
  id, caseId: 'case-1', recordType: 'bank', amount, parentAmount: '1001497.22', parentRowId: 'parent-1', isSplit: true,
  bankSplitParts: splitParts,
  label: '银行流水', status: '待关联', statusCode: 'pending_match', statusTone: 'warn', exceptionHandled: false,
  counterparty: '测试银行', categoryCode: id, categoryLabel: category, detailFields: [],
  tableValues: { counterparty: '测试银行', amount, direction: '支出', paymentAccount: '银行 1234', note: '还款' },
  actionVariant: 'detail-only', availableActions: ['detail'],
});

test('same-parent children show once, chips only reveal amounts and row click selects whole transaction', async () => {
  const user = userEvent.setup();
  const principal = record('principal-1', '1000000.00', '外部往来款 / 归还借款');
  const interest = record('interest-1', '1497.22', '费用 / 利息');
  const select = vi.fn();
  const { container } = render(<RelationGroupCell zoneId="unpaired" paneId="bank" columns={getWorkbenchColumns('bank')}
    records={[principal, interest]} scrollPaneId="bank" scrollTestId="bank-cell" getRowState={() => 'idle'}
    onSelectRow={select} onOpenDetail={vi.fn()} onRowAction={vi.fn()} showWorkflowActions={false} canOperateData />);
  expect(container.querySelectorAll('.record-card')).toHaveLength(1);
  expect(screen.queryByRole('button', { name: '选择流水子项' })).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '费用 / 利息拆分金额' }));
  expect(select).not.toHaveBeenCalled();
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1497.22');
  fireEvent.click(screen.getByText('1001497.22'));
  expect(select).toHaveBeenCalledOnce();
  expect(select).toHaveBeenCalledWith(principal, 'unpaired');
});

test('read-only split rows permit hover but neither whole nor child selection', async () => {
  const user = userEvent.setup();
  const interest = record('interest-1', '1497.22', '费用 / 利息');
  const select = vi.fn();
  render(<RelationGroupCell zoneId="unpaired" paneId="bank" columns={getWorkbenchColumns('bank')}
    records={[interest]} scrollPaneId="bank" scrollTestId="bank-cell" getRowState={() => 'idle'} readOnly
    onSelectRow={select} onOpenDetail={vi.fn()} onRowAction={vi.fn()} showWorkflowActions={false} canOperateData />);
  expect(screen.queryByRole('button', { name: '选择流水子项' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('1001497.22'));
  await user.click(screen.getByRole('button', { name: '费用 / 利息拆分金额' }));
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1497.22');
  expect(select).not.toHaveBeenCalled();
});


test('OA display segments still show each physical bank parent only once per relation', () => {
  const children = [record('principal-1', '1000000.00', '外部往来款 / 归还借款'), record('interest-1', '1497.22', '费用 / 利息')];
  const oa = children.map((child, index): WorkbenchRecord => ({ ...child, id: `oa-${index}`, recordType: 'oa', isSplit: false,
    parentRowId: undefined, tableValues: { applicant: `申请人${index}`, amount: child.amount } }));
  const group: WorkbenchRelationGroup = { id: 'case-1', groupType: 'unpaired', rawGroupType: 'unpaired', matchConfidence: 'high', reason: 'test',
    rows: { oa, bank: children, invoice: [] },
    displaySubgroups: children.map((child, index) => ({ oaRowIds: [oa[index].id], bankRowIds: [child.id] })),
  };
  const otherCase: WorkbenchRelationGroup = { ...group, id: 'case-2', rows: { oa: [], bank: [{ ...children[1], caseId: 'case-2' }], invoice: [] }, displaySubgroups: undefined };
  const { container } = render(<RelationGroupGrid zoneId="unpaired" groups={[group, otherCase]}
    panes={[{ id: 'oa', title: 'OA', rows: oa }, { id: 'bank', title: '银行', rows: children }, { id: 'invoice', title: '发票', rows: [] }]}
    rowTemplateColumns="1fr 8px 1fr 8px 1fr" getRowState={() => 'idle'} onSelectRow={vi.fn()} onOpenDetail={vi.fn()} onRowAction={vi.fn()} canOperateData />);
  expect(container.querySelectorAll('.record-card-bank')).toHaveLength(2);
  expect(container.querySelectorAll('.record-card-oa')).toHaveLength(2);
  expect(screen.getAllByRole('button', { name: '费用 / 利息拆分金额' })).toHaveLength(2);
});
