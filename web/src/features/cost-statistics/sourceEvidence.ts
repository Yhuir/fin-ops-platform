import type { SourceDraftLine } from './sourceAllocation';
import type { CostStatisticsManualAllocationTask } from './types';

export type SourceEvidenceGroup = { unitIndexes: number[]; bankIndexes: number[] };

// Connected source choices are presentation groups, never new matching decisions.
export function groupSourceEvidence(
  task: { units: Pick<CostStatisticsManualAllocationTask['units'][number], 'unitId'>[]; bankEvents: Pick<CostStatisticsManualAllocationTask['bankEvents'][number], 'transactionId' | 'eventKind'>[] },
  lines: Pick<SourceDraftLine, 'ownerId' | 'bankTransactionId'>[],
): SourceEvidenceGroup[] {
  const unitCount = task.units.length;
  const unitIndex = new Map(task.units.map((unit, index) => [unit.unitId, index]));
  const bankIndex = new Map(task.bankEvents.flatMap((bank, index) => bank.eventKind === 'outflow' ? [[bank.transactionId, index] as const] : []));
  const neighbors = Array.from({ length: unitCount + task.bankEvents.length }, () => new Set<number>());
  for (const line of lines) {
    const unit = unitIndex.get(line.ownerId); const bank = bankIndex.get(line.bankTransactionId);
    // Incomplete/invalid choices remain visible as unassigned facts; form validation owns the error.
    if (unit === undefined || bank === undefined) continue;
    neighbors[unit].add(unitCount + bank);
    neighbors[unitCount + bank].add(unit);
  }
  const groups: SourceEvidenceGroup[] = [];
  const owners = new Map<number, SourceEvidenceGroup>();
  for (let start = 0; start < neighbors.length; start++) {
    if (owners.has(start)) continue;
    const group: SourceEvidenceGroup = { unitIndexes: [], bankIndexes: [] };
    groups.push(group);
    const pending = [start]; owners.set(start, group);
    while (pending.length) {
      const node = pending.pop()!;
      for (const next of neighbors[node]) {
        if (!owners.has(next)) { owners.set(next, group); pending.push(next); }
      }
    }
  }
  // Preserve source ordinals independently of graph traversal or draft editing order.
  task.units.forEach((_, index) => owners.get(index)!.unitIndexes.push(index));
  task.bankEvents.forEach((_, index) => owners.get(unitCount + index)!.bankIndexes.push(index));
  return [...groups.filter(group => group.unitIndexes.length && group.bankIndexes.length),
    ...groups.filter(group => !group.unitIndexes.length || !group.bankIndexes.length)];
}
