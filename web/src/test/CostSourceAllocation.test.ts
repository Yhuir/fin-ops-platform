import { describe, expect, test } from 'vitest';
import { cents, createSourceDraft, money, sourceSaveRequest, validateSourceDraft } from '../features/cost-statistics/sourceAllocation';
import type { CostStatisticsManualAllocationTask } from '../features/cost-statistics/types';

export function sourceTask(): CostStatisticsManualAllocationTask {
  return {
    relationCaseId: 'case-1', relationVersion: 1, sourceFingerprint: 'existing-version-fingerprint',
    status: 'pending', pendingReasons: ['source_required'], amountsFixed: true,
    oaTotal: '600.00', grossOutflowTotal: '600.00', wrongPaymentRefundTotal: '0.00', netOutflowTotal: '600.00',
    units: [{ unitId: 'oa-1:parent', oaId: 'oa-1', oaApplyType: '支付申请', expenseItemId: '', projectId: 'p-1', projectName: '项目 A', expenseType: '原 OA 分类', expenseContent: '材料采购', oaApplicant: '申请人', oaOriginalAmount: '600.00' }],
    bankEvents: [
      { transactionId: 'bank-a', eventKind: 'outflow', amount: '350.00', counterpartyName: '供应商', tradeTime: '2026-08-15', tags: ['采购', '材料款'], bankAccountLabel: '建行 8106', bankTagCode: 'material', bankTagPrimaryLabel: '采购', bankTagSubLabel: '材料款' },
      { transactionId: 'bank-b', eventKind: 'outflow', amount: '250.00', counterpartyName: '供应商', tradeTime: '2026-09-03', tags: ['采购', '材料款'], bankAccountLabel: '民生 9486', bankTagCode: 'material', bankTagPrimaryLabel: '采购', bankTagSubLabel: '材料款' },
    ],
    allocations: [{ unitId: 'oa-1:parent', amount: '600.00' }], sourceAllocations: null,
    nonCostAmount: '0.00', nonCostReason: '', version: 0, updatedAt: '', updatedBy: '', canSave: true,
  };
}

describe('cost source amount closure', () => {
  test('uses exact cents and distinguishes blank from explicit zero', () => {
    expect(cents('')).toBeNull(); expect(cents('0')).toBe(0n);
    expect(cents('0.001')).toBeNull(); expect(cents('-1')).toBeNull();
    expect(cents('1e3')).toBeNull(); expect(cents('1,000')).toBeNull();
    expect(money(cents('0.1')! + cents('0.2')!)).toBe('0.30');
  });
  test('saves two real cross-month sources without writable account or tags', () => {
    const task = sourceTask(); const draft = createSourceDraft(task);
    draft.costLines = [
      { id: 1, ownerId: 'oa-1:parent', bankTransactionId: 'bank-a', amount: '350' },
      { id: 2, ownerId: 'oa-1:parent', bankTransactionId: 'bank-b', amount: '250' },
    ];
    expect(validateSourceDraft(task, draft)).toEqual({});
    expect(sourceSaveRequest(task, draft).sourceAllocations.costLines).toEqual([
      { unitId: 'oa-1:parent', bankTransactionId: 'bank-a', amount: '350.00' },
      { unitId: 'oa-1:parent', bankTransactionId: 'bank-b', amount: '250.00' },
    ]);
    draft.costLines[0].amount = '600'; draft.costLines.pop();
    expect(validateSourceDraft(task, draft)).toHaveProperty('source.bank-a');
    expect(validateSourceDraft(task, draft)).toHaveProperty('source.bank-b');
    expect(() => sourceSaveRequest(task, draft)).toThrow();
  });
  test('rejects duplicate source tuples and editing fixed OA totals', () => {
    const task = sourceTask(); const draft = createSourceDraft(task);
    draft.costLines = [1, 2].map(id => ({ id, ownerId: 'oa-1:parent', bankTransactionId: 'bank-a', amount: '175' }));
    draft.targets['oa-1:parent'] = '350';
    expect(validateSourceDraft(task, draft)).toMatchObject({ 'costLines.2': '此对象已有该来源，请修改已有行', 'unit.oa-1:parent': '本项成本必须等于原 OA 金额' });
  });
  test('rehydrates saved source decisions even while metadata remains pending', () => {
    const task = sourceTask(); task.pendingReasons = ['bank_tag_missing'];
    task.sourceAllocations = { costLines: [{ unitId: 'oa-1:parent', bankTransactionId: 'bank-a', amount: '350.00' }], refundLinks: [], nonCostLines: [] };
    expect(createSourceDraft(task).costLines).toEqual([expect.objectContaining({ bankTransactionId: 'bank-a', amount: '350.00' })]);
  });
  test('requires refund and non-cost sources with exact per-bank closure', () => {
    const task = sourceTask(); task.amountsFixed = false;
    task.bankEvents.push({ ...task.bankEvents[0], transactionId: 'refund', eventKind: 'wrong_payment_refund', amount: '50.00' });
    task.wrongPaymentRefundTotal = '50.00'; task.netOutflowTotal = '550.00';
    const draft = createSourceDraft(task); draft.targets['oa-1:parent'] = '500'; draft.nonCostAmount = '50'; draft.nonCostReason = '非成本往来';
    draft.costLines = [{ id: 1, ownerId: 'oa-1:parent', bankTransactionId: 'bank-a', amount: '300' }, { id: 2, ownerId: 'oa-1:parent', bankTransactionId: 'bank-b', amount: '200' }];
    draft.refundLinks = [{ id: 3, ownerId: 'refund', bankTransactionId: 'bank-a', amount: '50' }];
    draft.nonCostLines = [{ id: 4, ownerId: '', bankTransactionId: 'bank-b', amount: '50' }];
    expect(validateSourceDraft(task, draft)).toEqual({});
    draft.refundLinks = [];
    expect(validateSourceDraft(task, draft)).toHaveProperty('refund.refund');
  });
});
