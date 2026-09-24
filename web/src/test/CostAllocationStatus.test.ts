import { describe, expect, it } from 'vitest';
import { allocationOnlyWaitsForFacts, allocationStatusLabel } from '../features/cost-statistics/allocationStatus';

describe('allocation status presentation', () => {
  it('distinguishes stale decisions, missing facts and mixed unresolved sources', () => {
    expect(allocationStatusLabel({status:'stale',pendingReasons:[]})).toBe('待复核');
    expect(allocationStatusLabel({status:'pending',pendingReasons:['allocation_stale']})).toBe('待复核');
    expect(allocationStatusLabel({status:'pending',pendingReasons:['oa_in_progress']})).toBe('待审批');
    expect(allocationStatusLabel({status:'pending',pendingReasons:['bank_account_missing','source_date_missing']})).toBe('待补资料');
    expect(allocationStatusLabel({status:'pending',pendingReasons:['oa_in_progress','source_required']})).toBe('待审批 · 待分配');
    expect(allocationStatusLabel({status:'allocated',pendingReasons:[]})).toBe('已完成');
  });
  it('only prevents unchanged saves when every reason needs updated facts', () => {
    expect(allocationOnlyWaitsForFacts({status:'pending',pendingReasons:['oa_in_progress','bank_tag_missing']})).toBe(true);
    expect(allocationOnlyWaitsForFacts({status:'pending',pendingReasons:['oa_in_progress','amount_required']})).toBe(false);
    expect(allocationOnlyWaitsForFacts({status:'stale',pendingReasons:['allocation_stale']})).toBe(false);
    expect(allocationOnlyWaitsForFacts({status:'pending',pendingReasons:[]})).toBe(false);
  });
});
