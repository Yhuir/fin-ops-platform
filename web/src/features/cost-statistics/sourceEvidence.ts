import type { CostStatisticsManualAllocationTask } from './types';

// Index the server's current relation blocks; cost draft choices are not evidence.
export function groupSourceEvidence(task: Pick<CostStatisticsManualAllocationTask, 'units' | 'bankEvents' | 'relationDisplayGroups'>) {
  const units = new Map(task.units.map((unit, index) => [unit.unitId, index]));
  const banks = new Map(task.bankEvents.map((bank, index) => [bank.transactionId, index]));
  return task.relationDisplayGroups.map(group => ({
    unitIndexes: group.unitIds.map(id => {
      const index = units.get(id);
      if (index === undefined) throw new Error('关系包含未知 OA 成本项');
      return index;
    }),
    bankIndexes: group.bankTransactionIds.map(id => {
      const index = banks.get(id);
      if (index === undefined) throw new Error('关系包含未知流水');
      return index;
    }),
    sourcesExcluded: group.sourcesExcluded,
  }));
}
