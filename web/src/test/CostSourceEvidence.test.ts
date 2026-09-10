import { describe, expect, it } from 'vitest';
import { groupSourceEvidence } from '../features/cost-statistics/sourceEvidence';

const task = {
  units: ['a', 'b', 'c'].map(unitId => ({ unitId })),
  bankEvents: ['x', 'y', 'z'].map(transactionId => ({ transactionId, eventKind: 'outflow' as const })),
};
const links = (pairs: string[][]) => pairs.map(([ownerId, bankTransactionId]) => ({ ownerId, bankTransactionId }));

describe('current source evidence groups', () => {
  it('aligns exact chosen IDs while preserving original ordinals, without mutating facts', () => {
    const before = structuredClone(task);
    expect(groupSourceEvidence(task, links([['a','z'], ['b','x'], ['c','y']]))).toEqual([
      {unitIndexes:[0],bankIndexes:[2]}, {unitIndexes:[1],bankIndexes:[0]}, {unitIndexes:[2],bankIndexes:[1]},
    ]);
    expect(task).toEqual(before);
  });
  it('groups one-to-many and many-to-one without repeating facts', () => {
    expect(groupSourceEvidence(task, links([['a','y'], ['a','x'], ['c','z'], ['b','z']]))).toEqual([
      {unitIndexes:[0],bankIndexes:[0,1]}, {unitIndexes:[1,2],bankIndexes:[2]},
    ]);
  });
  it('groups transitive many-to-many choices, deduplicates edges, and ignores input order', () => {
    const pairs = [['a','x'], ['b','x'], ['b','y'], ['a','x']];
    const expected = [{unitIndexes:[0,1],bankIndexes:[0,1]}, {unitIndexes:[2],bankIndexes:[]}, {unitIndexes:[],bankIndexes:[2]}];
    expect(groupSourceEvidence(task, links(pairs))).toEqual(expected);
    expect(groupSourceEvidence(task, links(pairs.reverse()))).toEqual(expected);
  });
  it('keeps empty and invalid choices unassigned and never matches on amounts', () => {
    const groups = groupSourceEvidence(task, links([['a',''], ['unknown','x'], ['a','missing']]));
    expect(groups).toHaveLength(6);
    expect(groups.every(group => !group.unitIndexes.length || !group.bankIndexes.length)).toBe(true);
    expect(groupSourceEvidence({units:[],bankEvents:[]}, [])).toEqual([]);
  });
  it('does not treat refunds as outflow sources', () => {
    const withRefund = {...task, bankEvents:[...task.bankEvents, {transactionId:'refund', eventKind:'wrong_payment_refund' as const}]};
    const groups = groupSourceEvidence(withRefund, links([['a','refund'],['b','x']]));
    expect(groups[0]).toEqual({unitIndexes:[1],bankIndexes:[0]});
    expect(groups.at(-1)).toEqual({unitIndexes:[],bankIndexes:[3]});
  });
});
