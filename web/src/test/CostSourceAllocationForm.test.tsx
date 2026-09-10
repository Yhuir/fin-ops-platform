import { useState } from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import CostSourceAllocationForm from '../components/cost-statistics/CostSourceAllocationForm';
import { createSourceDraft } from '../features/cost-statistics/sourceAllocation';
import type { CostStatisticsManualAllocationTask } from '../features/cost-statistics/types';

function fixture(): CostStatisticsManualAllocationTask {
  return {
    relationCaseId: 'internal-case', relationVersion: 1, sourceFingerprint: 'fingerprint', status: 'pending', pendingReasons: ['source_required'], amountsFixed: false,
    oaTotal: '700.00', grossOutflowTotal: '600.00', wrongPaymentRefundTotal: '0.00', netOutflowTotal: '600.00',
    units: [
      { unitId: 'unit-a', oaId: 'internal-oa', oaApplyType: '支付申请', expenseItemId: '', projectId: 'project', projectName: '项目甲', expenseType: '材料', expenseContent: '材料采购', oaApplicant: '张先生', oaOriginalAmount: '500.00' },
      { unitId: 'unit-b', oaId: 'internal-oa', oaApplyType: '支付申请', expenseItemId: '', projectId: 'project', projectName: '项目甲', expenseType: '运费', expenseContent: '设备运输', oaApplicant: '张先生', oaOriginalAmount: '200.00' },
    ],
    bankEvents: [{ transactionId: 'internal-bank', eventKind: 'outflow', amount: '600.00', tradeTime: '2026-08-15', counterpartyName: '材料公司', bankAccountLabel: '建行 8106', bankTagCode: 'material', bankTagPrimaryLabel: '采购', bankTagSubLabel: '材料款', tags: ['采购', '材料款'] }],
    allocations: [], suggestedSourceAllocations: null, sourceAllocations: null, nonCostAmount: '0.00', nonCostReason: '', version: 0, updatedBy: '', updatedAt: '', canSave: true,
  };
}
function Editor({ task, save = vi.fn() }: { task: CostStatisticsManualAllocationTask; save?: () => void }) {
  const [draft, setDraft] = useState(() => createSourceDraft(task));
  return <CostSourceAllocationForm task={task} draft={draft} disabled={false} saving={false} onChange={setDraft} onSave={save} />;
}

it('hides exhausted hints while preserving capacity, duplicate, current selection and released capacity', async () => {
  const task = fixture(); const user = userEvent.setup();
  task.sourceAllocations = { costLines: [{ unitId: 'unit-a', bankTransactionId: 'internal-bank', amount: '600.00' }], refundLinks: [], nonCostLines: [] };
  const { container } = render(<Editor task={task} />);
  const groups = container.querySelectorAll('.cost-source-table tbody');
  const first = within(groups[0] as HTMLElement); const second = within(groups[1] as HTMLElement);
  await user.click(first.getByRole('combobox'));
  expect(screen.getByRole('option')).not.toHaveAttribute('aria-disabled', 'true');
  await user.keyboard('{Escape}');
  await user.click(second.getByRole('button', { name: '新增来源' }));
  await user.click(second.getByRole('combobox'));
  expect(screen.getByRole('option')).toHaveAttribute('aria-disabled', 'true');
  expect(screen.queryByText('已用完')).not.toBeInTheDocument();
  await user.keyboard('{ArrowDown}{Enter}');
  await user.keyboard('{Escape}');
  expect(second.getByRole('combobox')).toHaveTextContent('选择流水');
  await user.clear(first.getByRole('textbox'));
  await user.type(first.getByRole('textbox'), '300');
  await user.click(second.getByRole('combobox'));
  expect(screen.getByRole('option')).not.toHaveAttribute('aria-disabled', 'true');
  await user.click(screen.getByRole('option'));
  expect(second.getByRole('combobox')).toHaveTextContent('建行 8106');
  expect(first.getByRole('textbox')).toHaveValue('300.00');
  await user.click(first.getByRole('button', { name: '新增来源' }));
  await user.click(first.getAllByRole('combobox')[1]);
  expect(screen.getByRole('option')).toHaveAttribute('aria-disabled', 'true');
  expect(screen.queryByText('本项已使用')).not.toBeInTheDocument();
  await user.keyboard('{ArrowDown}{Enter}{Escape}');
  expect(first.getAllByRole('combobox')[1]).toHaveTextContent('选择流水');
});

describe('compact source allocation editor', () => {
  it('groups one OA document with two cost units and hides all internal identifiers', () => {
    const { container } = render(<Editor task={fixture()} />);
    expect(screen.getByRole('heading', { name: 'OA · 2 条' })).toBeInTheDocument();
    expect(screen.queryByText('按当前分配对齐，未保存的修改尚未生效')).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/internal-|unit-a|unit-b|已分|剩余/);
    expect(within(screen.getByRole('table', { name: '成本分配明细' })).getAllByRole('button', { name: '新增来源' })).toHaveLength(2);
    expect(within(screen.getByRole('table', { name: '成本分配明细' })).getAllByRole('columnheader').map(cell => cell.textContent)).toEqual(['项目', 'OA / 成本项', '来源流水', '银行标签', '分配金额', '操作']);
  });
  it('requires explicit zero and clears zero when adding a source; removing the last row stays unallocated', async () => {
    const user = userEvent.setup(); const task = fixture(); const save = vi.fn();
    const { container } = render(<Editor task={task} save={save} />);
    const unit = within(container.querySelector('.cost-source-table tbody')! as HTMLElement);
    await user.click(unit.getByRole('button', { name: '设为零成本' }));
    expect(unit.getByText('零成本', { exact: true })).toBeInTheDocument();
    await user.click(unit.getByRole('button', { name: '新增来源' }));
    expect(unit.queryByText('零成本', { exact: true })).not.toBeInTheDocument();
    expect(unit.getByRole('combobox')).toHaveFocus();
    await user.click(unit.getByRole('button', { name: '删除来源行 1' }));
    expect(unit.getByRole('button', { name: '新增来源' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    expect(within(screen.getByRole('dialog', { name: '分配校验' })).getByRole('alert')).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });
  it('does not offer zero for a fixed positive OA target', () => {
    const task = fixture(); task.amountsFixed = true;
    render(<Editor task={task} />);
    expect(screen.queryByRole('button', { name: '设为零成本' })).not.toBeInTheDocument();
  });
  it('derives editable totals from source rows and saves a legitimate zero second unit', async () => {
    const user = userEvent.setup(); const save = vi.fn();
    const { container } = render(<Editor task={fixture()} save={save} />);
    const groups = container.querySelectorAll('.cost-source-table tbody');
    const first = within(groups[0] as HTMLElement); const second = within(groups[1] as HTMLElement);
    await user.click(first.getByRole('button', { name: '新增来源' }));
    await user.click(first.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: /建行 8106/ }));
    await user.type(first.getByRole('textbox', { name: '分配金额 1' }), '600');
    await user.click(second.getByRole('button', { name: '设为零成本' }));
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

it('keeps source and amount issues in their own cells without showing instructions on a new row', async () => {
  const user = userEvent.setup(); const save = vi.fn();
  render(<Editor task={fixture()} save={save} />);
  const table = screen.getByRole('table', { name: '成本分配明细' });
  await user.click(within(table).getAllByRole('button', { name: '新增来源' })[0]);
  const source = within(table).getByRole('combobox');
  const amount = within(table).getByRole('textbox');
  await user.click(source); await user.keyboard('{Escape}');
  expect(amount).toHaveAttribute('aria-invalid', 'false');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '保存分配' }));
  await user.keyboard('{Escape}');
  expect(source).toHaveAttribute('aria-invalid', 'true');
  expect(amount).toHaveAttribute('aria-invalid', 'true');
  expect(within(source.closest('td')!).getByRole('button', { name: '请选择本关联中的支出流水' })).toBeInTheDocument();
  expect(within(amount.closest('td')!).getByRole('button', { name: '金额须大于 0，最多两位小数' })).toBeInTheDocument();
  expect(source.closest('td')!.querySelector('p')).toBeNull();
  expect(amount.closest('td')!.querySelector('p')).toBeNull();
  await user.click(within(amount.closest('td')!).getByRole('button'));
  expect(within(screen.getByRole('dialog', { name: '分配校验' })).getByRole('alert')).toHaveTextContent('金额须大于 0');
  expect(save).not.toHaveBeenCalled();
});

it('preserves money when selecting another real source and derives readonly chips from that source', async () => {
  const user = userEvent.setup(); const task = fixture();
  task.bankEvents.push({ ...task.bankEvents[0], transactionId: 'bank-two', bankAccountLabel: '民生银行 账户 9486', bankTagPrimaryLabel: '项目开销', bankTagSubLabel: '差旅费', tradeTime: '2026-09-03' });
  render(<Editor task={task} />);
  const table = screen.getByRole('table', { name: '成本分配明细' });
  await user.click(within(table).getAllByRole('button', { name: '新增来源' })[0]);
  const source = within(table).getByRole('combobox'); const amount = within(table).getByRole('textbox');
  await user.type(amount, '350');
  await user.click(source); await user.click(screen.getByRole('option', { name: /建行 8106/ }));
  await user.click(source); await user.click(screen.getByRole('option', { name: /民生银行 9486/ }));
  expect(amount).toHaveValue('350.00');
  expect(source).toHaveTextContent('民生银行 9486 · 2026-09-03');
  expect(within(table).getByText('差旅费')).toBeInTheDocument();
  expect(within(table).queryByText('材料款')).not.toBeInTheDocument();
  expect(table.textContent).not.toMatch(/账户|bank-two/);
});

it('keeps one inline add action through first, middle and last deletion and preserves each remaining amount', async () => {
  const user = userEvent.setup(); render(<Editor task={fixture()} />);
  const group = within(screen.getByRole('table', { name: '成本分配明细' }).querySelector('tbody')!);
  for (const amount of ['10','20','30']) {
    await user.click(group.getByRole('button', { name: '新增来源' }));
    await user.type(group.getAllByRole('textbox').at(-1)!, amount);
  }
  expect(group.getAllByRole('row')).toHaveLength(3);
  await user.click(group.getByRole('button', { name: '删除来源行 2' }));
  expect(group.getAllByRole('textbox').map(e => (e as HTMLInputElement).value)).toEqual(['10.00','30.00']);
  await user.click(group.getByRole('button', { name: '删除来源行 1' }));
  expect(group.getByRole('textbox')).toHaveValue('30.00');
  expect(group.getByRole('combobox')).toHaveFocus();
  expect(group.getAllByRole('button', { name: '新增来源' })).toHaveLength(1);
  await user.click(group.getByRole('button', { name: '删除来源行 1' }));
  expect(group.getByRole('button', { name: '新增来源' })).toHaveFocus();
  expect(group.getAllByRole('row')).toHaveLength(1);
});

it('opens full evidence with the keyboard without exposing internal IDs or moving table rows', async () => {
  const user = userEvent.setup(); const task = fixture();
  task.units[0].expenseContent = '采购项目详细说明'.repeat(30);
  render(<Editor task={task} />);
  const trigger = screen.getByRole('button', { name: 'OA 1 费用全文' });
  act(() => trigger.focus()); await user.keyboard('{Enter}');
  expect(screen.getByRole('dialog', { name: 'OA 1 费用全文' })).toHaveTextContent(task.units[0].expenseContent);
  await user.keyboard('{Escape}'); await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.getByRole('table', { name: 'OA 与流水对照', exact: true })).not.toHaveTextContent('internal-oa');
});

it('keeps refunds and non-cost sources editable through inline actions with full closure', async () => {
  const user = userEvent.setup(); const task = fixture(); const save = vi.fn();
  task.netOutflowTotal = '500.00'; task.wrongPaymentRefundTotal = '100.00';
  task.bankEvents.push({ ...task.bankEvents[0], transactionId: 'refund', eventKind: 'wrong_payment_refund', amount: '100.00' });
  task.nonCostAmount = '100.00'; task.nonCostReason = '往来款';
  task.allocations = [{ unitId: 'unit-a', amount: '400.00' }, { unitId: 'unit-b', amount: '0.00' }];
  task.sourceAllocations = { costLines: [{ unitId: 'unit-a', bankTransactionId: 'internal-bank', amount: '400.00' }], refundLinks: [{ refundTransactionId: 'refund', bankTransactionId: 'internal-bank', amount: '100.00' }], nonCostLines: [{ bankTransactionId: 'internal-bank', amount: '100.00' }] };
  render(<Editor task={task} save={save} />);
  for (const name of ['退款来源', '非成本来源']) {
    const table = within(screen.getByRole('table', { name }));
    expect(table.getAllByRole('row')).toHaveLength(2);
    await user.click(table.getByRole('button', { name: '删除来源行 1' }));
    expect(table.getByRole('button', { name: '新增来源' })).toHaveFocus();
    await user.click(table.getByRole('button', { name: '新增来源' }));
    await user.click(table.getByRole('combobox'));
    await user.click(screen.getByRole('option', { name: /建行 8106/ }));
    await user.type(table.getByRole('textbox'), '100');
  }
  await user.click(screen.getByRole('button', { name: '保存分配' }));
  expect(save).toHaveBeenCalledOnce();
});


it('keeps source ordinals aligned with bank evidence when refunds appear first', async () => {
  const user = userEvent.setup(); const task = fixture();
  task.bankEvents.unshift({ ...task.bankEvents[0], transactionId: 'refund-first', eventKind: 'wrong_payment_refund', amount: '100.00' });
  render(<Editor task={task} />);
  const table = within(screen.getByRole('table', { name: '成本分配明细' }));
  await user.click(table.getAllByRole('button', { name: '新增来源' })[0]);
  await user.click(table.getByRole('combobox'));
  expect(screen.getByRole('option', { name: /^2\. 建行 8106/ })).toBeInTheDocument();
  expect(screen.getAllByRole('option')).toHaveLength(1);
});

 it('merges both identity cells across suggested sources and updates spans on deletion', async () => {
   const task = fixture(); const user = userEvent.setup();
   task.suggestedSourceAllocations = {costLines: [
     {unitId: 'unit-a', bankTransactionId: 'internal-bank', amount: '300.00'},
     {unitId: 'unit-a', bankTransactionId: 'second-bank', amount: '200.00'},
   ], refundLinks: [], nonCostLines: []};
   task.bankEvents.push({...task.bankEvents[0], transactionId: 'second-bank', amount: '200.00'});
   const {container} = render(<Editor task={task} />);
   const group = container.querySelector('.cost-source-table tbody')!;
   expect(group.querySelectorAll('td[rowspan="2"]')).toHaveLength(2);
   expect(group.querySelectorAll('tr')[1].children).toHaveLength(4);
   await user.click(within(group as HTMLElement).getByRole('button', {name: '删除来源行 1'}));
   expect(group.querySelectorAll('td[rowspan="1"]')).toHaveLength(2);
   expect(within(group as HTMLElement).getByRole('textbox', {name: '分配金额 1'})).toHaveValue('200.00');
   await user.click(within(group as HTMLElement).getByRole('button', {name: '删除来源行 1'}));
   expect(within(group as HTMLElement).getByText('未分配')).toBeVisible();
   expect(within(group as HTMLElement).queryByRole('combobox')).not.toBeInTheDocument();
 });

it('shows balance only for complete allocations and updates the current source correspondence', async () => {
  const task = fixture(); const user = userEvent.setup();
  task.amountsFixed = true; task.oaTotal = '600.00'; task.units[0].oaOriginalAmount = '400.00';
  task.bankEvents[0].amount = '400.00';
  task.bankEvents.push({...task.bankEvents[0],transactionId:'bank-b',amount:'200.00',bankAccountLabel:'民生银行 9486'});
  task.sourceAllocations = {costLines:[{unitId:'unit-a',bankTransactionId:'internal-bank',amount:'400.00'},{unitId:'unit-b',bankTransactionId:'bank-b',amount:'200.00'}],refundLinks:[],nonCostLines:[]};
  const {container} = render(<Editor task={task} />);
  const evidence = screen.getByRole('table', {name:'OA 与流水对照'});
  expect(screen.getByText('分配金额一致')).toBeVisible();
  expect(within(evidence).getAllByRole('rowgroup')).toHaveLength(3);
  const groups = container.querySelectorAll('.cost-source-table tbody');
  const first = within(groups[0] as HTMLElement); const second = within(groups[1] as HTMLElement);
  await user.clear(second.getByRole('textbox')); await user.type(second.getByRole('textbox'),'100');
  expect(screen.queryByText('分配金额一致')).not.toBeInTheDocument();
  await user.clear(first.getByRole('textbox')); await user.type(first.getByRole('textbox'),'500');
  // Grand total still equals 600, but per-unit/source amounts are wrong.
  expect(screen.queryByText('分配金额一致')).not.toBeInTheDocument();
  await user.clear(first.getByRole('textbox')); await user.type(first.getByRole('textbox'),'400');
  await user.click(first.getByRole('combobox'));
  await user.click(screen.getByRole('option',{name:/民生银行 9486/}));
  expect(evidence.querySelectorAll('td[rowspan="2"]')).toHaveLength(3);
  expect(evidence.querySelector('[data-evidence-kind="unassigned"]')).toHaveTextContent('建行 8106');
  expect(screen.queryByText('分配金额一致')).not.toBeInTheDocument();
});

it.each([{saving:true}, {error:'保存结果待确认'}, {error:'关联事实已变化'}, {notice:'已保存，银行信息待完善'}])('prioritizes save feedback over balance: %j', state => {
  const task = fixture();
  task.sourceAllocations = {costLines:[{unitId:'unit-a',bankTransactionId:'internal-bank',amount:'400.00'},{unitId:'unit-b',bankTransactionId:'internal-bank',amount:'200.00'}],refundLinks:[],nonCostLines:[]};
  render(<CostSourceAllocationForm task={task} draft={createSourceDraft(task)} disabled={false} saving={false} {...state} onChange={vi.fn()} onSave={vi.fn()} />);
  expect(screen.queryByText('分配金额一致')).not.toBeInTheDocument();
});
