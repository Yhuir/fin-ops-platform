import type { CostSourceAllocations, CostStatisticsManualAllocationTask, SaveCostStatisticsManualAllocationRequest } from './types';

export type SourceDraftLine = { id: number; ownerId: string; bankTransactionId: string; amount: string };
export type SourceDraft = {
  zeroUnitIds: string[];
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
  const saved = task.pendingReasons.includes('allocation_stale') ? null : task.sourceAllocations;
  return {
    zeroUnitIds: task.pendingReasons.includes('allocation_stale') ? [] : task.allocations.filter(line => cents(line.amount) === 0n).map(line => line.unitId),
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
// One pass over editable rows; totals are derived, never a second editable fact.
export function sourceUnitAmounts(task: CostStatisticsManualAllocationTask, draft: SourceDraft): Map<string, bigint | null> {
  const sums = new Map<string, bigint | null>();
  for (const line of draft.costLines) {
    const amount = cents(line.amount);
    const previous = sums.get(line.ownerId);
    sums.set(line.ownerId, previous === null || amount === null || amount <= 0n ? null : (previous ?? 0n) + amount);
  }
  const zero = new Set(draft.zeroUnitIds);
  return new Map(task.units.map(unit => [unit.unitId, task.amountsFixed
    ? cents(unit.oaOriginalAmount)
    : zero.has(unit.unitId) ? 0n : sums.get(unit.unitId) ?? null]));
}
export function validateSourceDraft(task: CostStatisticsManualAllocationTask, draft: SourceDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const sources = new Map(task.bankEvents.filter(event => event.eventKind === 'outflow').map(event => [event.transactionId, event]));
  const units = new Set(task.units.map(unit => unit.unitId));
  const refunds = new Set(task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund').map(event => event.transactionId));
  const totals = new Map<string, bigint>();
  const targets = sourceUnitAmounts(task, draft);
  const zero = new Set(draft.zeroUnitIds);
  const sum = (lines: SourceDraftLine[]) => lines.reduce((total, line) => total + (cents(line.amount) ?? 0n), 0n);
  for (const kind of ['costLines', 'refundLinks', 'nonCostLines'] as const) {
    const seen = new Set<string>();
    for (const line of draft[kind]) {
      const field = `${kind}.${line.id}`;
      if (!sources.has(line.bankTransactionId)) errors[`${field}.source`] = '请选择本关联中的支出流水';
      if (kind === 'costLines' && !units.has(line.ownerId)) errors[`${field}.owner`] = '请选择有效的 OA 成本项';
      if (kind === 'refundLinks' && !refunds.has(line.ownerId)) errors[`${field}.owner`] = '请选择有效的退款流水';
      const amount = cents(line.amount);
      if (amount === null || amount <= 0n) errors[`${field}.amount`] = '金额须大于 0，最多两位小数';
      else if (kind === 'costLines') totals.set(line.ownerId, (totals.get(line.ownerId) ?? 0n) + amount);
      const identity = JSON.stringify([line.ownerId, line.bankTransactionId]);
      if (line.bankTransactionId && seen.has(identity)) errors[`${field}.source`] = '此成本项已有该来源';
      seen.add(identity);
    }
  }
  let total = 0n;
  for (const unit of task.units) {
    const target = targets.get(unit.unitId);
    const key = `unit.${unit.unitId}`;
    if (target === null || target === undefined) errors[key] = '请分配来源，或明确设为零成本';
    else {
      total += target;
      if (zero.has(unit.unitId) && (task.amountsFixed && target > 0n || draft.costLines.some(line => line.ownerId === unit.unitId))) {
        errors[key] = task.amountsFixed && target > 0n ? '固定金额不能设为零成本' : '请删除来源行后再设为零成本';
      } else if ((totals.get(unit.unitId) ?? 0n) !== target) errors[key] = `该成本项分配合计须为 ${money(target)}`;
    }
  }
  const nonCost = cents(draft.nonCostAmount);
  if (nonCost === null) errors.nonCost = '请填写非成本金额，未发生请填 0';
  else {
    if (sum(draft.nonCostLines) !== nonCost) errors.nonCost = '非成本来源合计与金额不一致';
    if (nonCost > 0n && !draft.nonCostReason.trim()) errors.nonCost = '请填写不计入成本的原因';
    if (total + nonCost !== cents(task.netOutflowTotal)) errors.total = '成本与非成本合计须等于净支出';
  }
  for (const refund of task.bankEvents.filter(event => event.eventKind === 'wrong_payment_refund')) {
    if (sum(draft.refundLinks.filter(line => line.ownerId === refund.transactionId)) !== cents(refund.amount)) errors[`refund.${refund.transactionId}`] = '请完整分配此笔退款';
  }
  const used = usedBySource(draft);
  for (const source of sources.values()) {
    const allocated = used.get(source.transactionId) ?? 0n;
    if (allocated !== cents(source.amount)) errors[`source.${source.transactionId}`] = allocated > cents(source.amount)!
      ? '分配金额超过该流水金额' : '该流水尚未完整分配';
  }
  return errors;
}
export function sourceSaveRequest(task: CostStatisticsManualAllocationTask, draft: SourceDraft) {
  if (Object.keys(validateSourceDraft(task, draft)).length) throw new Error('请先完成来源与金额核对');
  const normalized = (value: string) => money(cents(value)!);
  const targets = sourceUnitAmounts(task, draft);
  const sourceAllocations: CostSourceAllocations = {
    costLines: draft.costLines.map(line => ({ unitId: line.ownerId, bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
    refundLinks: draft.refundLinks.map(line => ({ refundTransactionId: line.ownerId, bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
    nonCostLines: draft.nonCostLines.map(line => ({ bankTransactionId: line.bankTransactionId, amount: normalized(line.amount) })),
  };
  return {
    relationCaseId: task.relationCaseId, expectedVersion: task.version, sourceFingerprint: task.sourceFingerprint,
    allocations: task.units.map(unit => ({ unitId: unit.unitId, amount: money(targets.get(unit.unitId)!) })),
    sourceAllocations, nonCostAmount: normalized(draft.nonCostAmount), nonCostReason: draft.nonCostReason.trim(),
  };
}

// Reconcile an interrupted response against the actual saved decision, not version alone.
export function sourceDecisionMatches(request: SaveCostStatisticsManualAllocationRequest, task: CostStatisticsManualAllocationTask): boolean {
  if (task.version <= request.expectedVersion || task.sourceFingerprint !== request.sourceFingerprint
    || task.pendingReasons.includes('allocation_stale') || !task.sourceAllocations) return false;
  const ordered = (rows: string[][]) => JSON.stringify(rows.map(row => JSON.stringify(row)).sort());
  const matrix = (value: CostSourceAllocations) => [
    ordered(value.costLines.map(line => [line.unitId, line.bankTransactionId, line.amount])),
    ordered(value.refundLinks.map(line => [line.refundTransactionId, line.bankTransactionId, line.amount])),
    ordered(value.nonCostLines.map(line => [line.bankTransactionId, line.amount])),
  ].join('|');
  return matrix(request.sourceAllocations) === matrix(task.sourceAllocations)
    && ordered(request.allocations.map(line => [line.unitId, line.amount])) === ordered(task.allocations.map(line => [line.unitId, line.amount]))
    && request.nonCostAmount === task.nonCostAmount && request.nonCostReason === task.nonCostReason;
}
