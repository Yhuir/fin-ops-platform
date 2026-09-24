import userEvent from '@testing-library/user-event';
import { act, fireEvent, render, screen } from '@testing-library/react';
import RelationGroupGrid from '../components/workbench/RelationGroupGrid';
import RelationGroupCell from '../components/workbench/RelationGroupCell';
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

test('same-parent children occupy one bank row while selection preserves child identity and amount', () => {
  const principal = record('principal-1', '1000000.00', '外部往来款 / 归还借款');
  const interest = record('interest-1', '1497.22', '费用 / 利息');
  const select = vi.fn();
  const { container } = render(<RelationGroupCell zoneId="unpaired" paneId="bank" columns={getWorkbenchColumns('bank')}
    records={[principal, interest]} scrollPaneId="bank" scrollTestId="bank-cell" getRowState={() => 'idle'}
    onSelectRow={select} onOpenDetail={vi.fn()} onRowAction={vi.fn()} showWorkflowActions={false} canOperateData />);
  expect(container.querySelectorAll('.record-card')).toHaveLength(1);
  expect(screen.getByText('1001497.22')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '选择流水子项 费用 / 利息 1497.22' }));
  expect(select).toHaveBeenCalledOnce();
  expect(select).toHaveBeenCalledWith(interest, 'unpaired');
  expect(select.mock.calls[0][0].amount).toBe('1497.22');
});


test('different OA segments show one physical bank parent per case and keep child selection', () => {
  const children = [record('principal-1', '1000000.00', '外部往来款 / 归还借款'), record('interest-1', '1497.22', '费用 / 利息')];
  const oa = children.map((child, index): WorkbenchRecord => ({ ...child, id: `oa-${index}`, recordType: 'oa', isSplit: false,
    parentRowId: undefined, tableValues: { applicant: `申请人${index}`, amount: child.amount } }));
  const group: WorkbenchRelationGroup = { id: 'case-1', groupType: 'unpaired', rawGroupType: 'unpaired', matchConfidence: 'high', reason: 'test',
    rows: { oa, bank: children, invoice: [] },
    displaySubgroups: children.map((child, index) => ({ oaRowIds: [oa[index].id], bankRowIds: [child.id] })),
  };
  const select = vi.fn();
  const otherCase: WorkbenchRelationGroup = { ...group, id: 'case-2', rows: { oa: [], bank: [{ ...children[1], caseId: 'case-2' }], invoice: [] }, displaySubgroups: undefined };
  const { container } = render(<RelationGroupGrid zoneId="unpaired" groups={[group, otherCase]}
    panes={[{ id: 'oa', title: 'OA', rows: oa }, { id: 'bank', title: '银行', rows: children }, { id: 'invoice', title: '发票', rows: [] }]}
    rowTemplateColumns="1fr 8px 1fr 8px 1fr" getRowState={() => 'idle'} onSelectRow={select} onOpenDetail={vi.fn()} onRowAction={vi.fn()} canOperateData />);
  expect(container.querySelectorAll('.record-card-bank')).toHaveLength(2);
  expect(container.querySelectorAll('.record-card-oa')).toHaveLength(2);
  const interest = screen.getAllByRole('button', { name: '选择流水子项 费用 / 利息 1497.22' });
  expect(interest).toHaveLength(2);
  fireEvent.click(interest[0]);
  expect(select).toHaveBeenCalledWith(children[1], 'unpaired');
  fireEvent.click(interest[1]);
  expect(select.mock.calls[1][0].caseId).toBe('case-2');
});


test('split selection uses pressed buttons, keyboard and full label path without visible checkboxes', async () => {
  const user = userEvent.setup();
  const interest = { ...record('interest', '1497.2', '利息'), categoryPath: ['费用', '利息'], bankSplitParts: [{ ...splitParts[1], id: 'interest', amount: '1497.2' }] };
  const select = vi.fn();
  const props = { zoneId: 'unpaired' as const, paneId: 'bank' as const, columns: getWorkbenchColumns('bank'),
    records: [interest], scrollPaneId: 'bank' as const, scrollTestId: 'bank-cell', onSelectRow: select,
    onOpenDetail: vi.fn(), onRowAction: vi.fn(), showWorkflowActions: false, canOperateData: true };
  const { container, rerender } = render(<RelationGroupCell {...props} getRowState={() => 'idle'} />);
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  const button = screen.getByRole('button', { name: '选择流水子项 费用 / 利息 1497.20' });
  expect(button).toHaveTextContent('费用 / 利息');
  expect(button).toHaveAttribute('aria-pressed', 'false');
  act(() => button.focus()); await user.keyboard('{Enter}');
  expect(select).toHaveBeenCalledWith(interest, 'unpaired');
  rerender(<RelationGroupCell {...props} getRowState={() => 'selected'} />);
  expect(button).toHaveAttribute('aria-pressed', 'true');
  await user.keyboard(' ');
  expect(select).toHaveBeenCalledTimes(2);
  expect(container.querySelectorAll('.record-card-bank')).toHaveLength(1);
  expect(container.querySelector('.bank-split-parent-amount')).toHaveTextContent('1001497.22');
  await user.hover(button);
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1497.20');
  rerender(<RelationGroupCell {...props} readOnly getRowState={() => 'idle'} />);
  expect(button).not.toHaveAttribute('aria-pressed');
  await user.click(button);
  expect(select).toHaveBeenCalledTimes(2);
});


test('parent shows an unlinked sibling without granting its selection', async () => {
  const user = userEvent.setup();
  const interest = record('interest-1', '1497.22', '费用 / 利息');
  const select = vi.fn();
  render(<RelationGroupCell zoneId="unpaired" paneId="bank" columns={getWorkbenchColumns('bank')}
    records={[interest]} scrollPaneId="bank" scrollTestId="bank-cell" getRowState={() => 'idle'}
    onSelectRow={select} onOpenDetail={vi.fn()} onRowAction={vi.fn()} showWorkflowActions={false} canOperateData />);
  await user.click(screen.getByRole('button', { name: '外部往来款 / 归还借款拆分金额' }));
  expect(select).not.toHaveBeenCalled();
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1000000.00');
  await user.click(screen.getByRole('button', { name: '选择流水子项 费用 / 利息 1497.22' }));
  expect(select).toHaveBeenCalledWith(interest, 'unpaired');
});
