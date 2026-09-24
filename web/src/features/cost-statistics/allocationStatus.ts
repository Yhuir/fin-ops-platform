import type { CostStatisticsManualAllocationTask } from './types';

type AllocationState = Pick<CostStatisticsManualAllocationTask, 'status' | 'pendingReasons'>;
const missingMetadata = new Set(['bank_tag_missing', 'bank_account_missing', 'source_date_missing']);

export function allocationStatusLabel(task: AllocationState): string {
  if (task.status === 'stale' || task.pendingReasons.includes('allocation_stale')) return '待复核';
  if (task.status === 'allocated') return '已完成';
  const labels: string[] = [];
  if (task.pendingReasons.includes('oa_in_progress')) labels.push('待审批');
  if (task.pendingReasons.some(reason => missingMetadata.has(reason))) labels.push('待补资料');
  if (!labels.length || task.pendingReasons.some(reason => reason !== 'oa_in_progress' && !missingMetadata.has(reason))) labels.push('待分配');
  return labels.join(' · ');
}

// Waiting facts cannot be repaired by resaving an unchanged source decision.
export function allocationOnlyWaitsForFacts(task: AllocationState): boolean {
  return task.status === 'pending' && task.pendingReasons.length > 0
    && task.pendingReasons.every(reason => reason === 'oa_in_progress' || missingMetadata.has(reason));
}
