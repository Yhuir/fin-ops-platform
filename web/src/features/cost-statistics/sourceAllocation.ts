import type { CostSourceAllocations, CostStatisticsManualAllocationTask } from './types';

export type SourceDraftLine = { id: number; ownerId: string; bankTransactionId: string; amount: string };
export type SourceDraft = {
  targets: Record<string, string>;
  costLines: SourceDraftLine[];
  refundLinks: SourceDraftLine[];
  nonCostLines: SourceDraftLine[];
  nonCostAmount: string;
  nonCostReason: string;
};
export const moneyPattern = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,2})?$/;
export function cents(value: string): bigint | null {
  if (!moneyPattern.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}
export function money(value: bigint): string {
  const absolute = value < 0n ? -value : value;
  return `${value < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
}
export function createSourceDraft(task: CostStatisticsManualAllocationTask): SourceDraft {
  let id = 0;
  const saved = task.sourceAllocations;
  return {
    targets: Object.fromEntries(task.units.map(unit => [unit.unitId, task.allocations.find(line => line.unitId === unit.unitId)?.amount ?? ''])),
    costLines: (saved?.costLines ?? []).map(line => ({ ...line, ownerId: line.unitId, id: ++id })),
    refundLinks: (saved?.refundLinks ?? []).map(line => ({ ...line, ownerId: line.refundTransactionId, id: ++id })),
    nonCostLines: (saved?.nonCostLines ?? []).map(line => ({ ...line, ownerId: '', id: ++id })),
    nonCostAmount: task.nonCostAmount,
    nonCostReason: task.nonCostReason,
  };
}
export function usedBySource(draft: SourceDraft): Map<string, bigint> {
  const used = new Map<string, bigint>();
  for (const line of [...draft.costLines, ...draft.refundLinks, ...draft.nonCostLines]) {
    const amount = cents(line.amount);
    if (amount !== null && line.bankTransactionId) used.set(line.bankTransactionId, (used.get(line.bankTransactionId) ?? 0n) + amount);
  }
  return used;
}
export function validateSourceDraft(task: CostStatisticsManualAllocationTask, draft: SourceDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const sources = new Map(task.bankEvents.filter(event => event.eventKind === 'outflow').map(event => [event.transactionId, event]));
  const sum = (lines: SourceDraftLine[]) => lines.reduce((total, line) => total + (cents(line.amount) ?? 0n), 0n);
  for (const key of ['costLines', 'refundLinks', 'nonCostLines'] as const) {
    const seen = new Set<string>();
    for (const line of draft[key]) {
      const field = `${key}.${line.id}`;
      if (!sources.has(line.bankTransactionId)) errors[field] = '请选择本关联中的支出流水';
      const amount = cents(line.amount);
      if (amount === null || amount <= 0n) errors[field] = '请输入大于零的金额，最多两位小数';
      const identity = JSON.stringify([line.ownerId, line.bankTransactionId]);
      if (line.bankTransactionId && seen.has(identity)) errors[field] = '此对象已有该来源，请修改已有行';
      seen.add(identity);
    }
  }
  let total = 0n;
  for (const unit of task.units) {
    const target = cents(draft.targets[unit.unitId]);
    const key = `unit.${unit.unitId}`;
    if (target === null) errors[key] = '请填写本项成本，零成本请明确填写 0';
    else {
      total += target;
      if (task.amountsFixed && target !== cents(unit.oaOriginalAmount)) errors[key] = '本项成本必须等于原 OA 金额';
      else if (sum(draft.costLines.filter(line => line.ownerId === unit.unitId)) !== target) errors[key] = '来源分配合计必须等于本项成本';
    }
  }
  const nonCost = cents(draft.nonCostAmount);
  if (nonCost === null) errors.nonCost = '请填写非成本金额，未发生请填 0';
  else {
    if (sum(draft.nonCostLines) !== nonCost) errors.nonCost = '非成本来源合计与非成本金额不一致';
    if (nonCost > 0n && !draft.nonCostReason.trim()) errors.nonCost = '请填写不计入成本的原因';
    if (total + nonCost !== cents(task.netOutflowTotal)) errors.total = '成本与非成本合计必须等于净支出';
  }
  for (const refund of task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund')) {
    if (sum(draft.refundLinks.filter(line => line.ownerId === refund.transactionId)) !== cents(refund.amount)) errors[`refund.${refund.transactionId}`] = '请将退款完整归属到原支出';
  }
  const used = usedBySource(draft);
  for (const source of sources.values()) {
    if ((used.get(source.transactionId) ?? 0n) !== cents(source.amount)) errors[`source.${source.transactionId}`] = '该支出的成本、退款和非成本合计必须等于流水金额';
  }
  return errors;
}
export function sourceSaveRequest(task: CostStatisticsManualAllocationTask, draft: SourceDraft) {
  if (Object.keys(validateSourceDraft(task, draft)).length) throw new Error('请先完成来源与金额核对');
  const normalized = (value: string) => money(cents(value)!);
  const sourceAllocations: CostSourceAllocations = {
    costLines: draft.costLines.map(line => ({ unitId: line.ownerId, bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
    refundLinks: draft.refundLinks.map(line => ({ refundTransactionId: line.ownerId, bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
    nonCostLines: draft.nonCostLines.map(line => ({ bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
  };
  return {
    relationCaseId: task.relationCaseId, expectedVersion: task.version, sourceFingerprint: task.sourceFingerprint,
    allocations: task.units.map(unit => ({ unitId: unit.unitId, amount: normalized(draft.targets[unit.unitId]) })),
    sourceAllocations, nonCostAmount: normalized(draft.nonCostAmount), nonCostReason: draft.nonCostReason.trim(),
  };
}
