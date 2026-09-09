import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
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
    allocations: [], sourceAllocations: null, nonCostAmount: '0.00', nonCostReason: '', version: 0, updatedBy: '', updatedAt: '', canSave: true,
  };
}
function Editor({ task, save = vi.fn() }: { task: CostStatisticsManualAllocationTask; save?: () => void }) {
  const [draft, setDraft] = useState(() => createSourceDraft(task));
  return <CostSourceAllocationForm task={task} draft={draft} disabled={false} saving={false} onChange={setDraft} onSave={save} />;
}

describe('compact source allocation editor', () => {
  it('groups one OA document with two cost units and hides all internal identifiers', () => {
    const { container } = render(<Editor task={fixture()} />);
    expect(screen.getByRole('heading', { name: /1 张.*2 个/ })).toBeInTheDocument();
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
    expect(unit.getByText('请分配来源，或明确设为零成本')).toBeInTheDocument();
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
    await user.selectOptions(first.getByRole('combobox'), 'internal-bank');
    await user.type(first.getByRole('textbox', { name: '分配金额 1' }), '600');
    await user.click(second.getByRole('button', { name: '设为零成本' }));
    await user.click(screen.getByRole('button', { name: '保存分配' }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
