import { describe, expect, it } from 'vitest';
import { groupSourceEvidence } from '../features/cost-statistics/sourceEvidence';
import type { CostStatisticsManualAllocationTask } from '../features/cost-statistics/types';
const task = {
  units: ['a','b'].map(unitId=>({unitId})), bankEvents: ['x','y','z'].map(transactionId=>({transactionId})),
  relationDisplayGroups: [{unitIds:['a'],bankTransactionIds:['z','x'],sourcesExcluded:false}, {unitIds:['b'],bankTransactionIds:['y'],sourcesExcluded:false}],
} as CostStatisticsManualAllocationTask;
describe('formal relation evidence', () => {
  it('preserves server blocks and source ordinals independently of allocation choices', () => {
    const before=structuredClone(task);
    expect(groupSourceEvidence(task)).toEqual([{unitIndexes:[0],bankIndexes:[2,0],sourcesExcluded:false},{unitIndexes:[1],bankIndexes:[1],sourcesExcluded:false}]);
    expect(task).toEqual(before);
  });
  it('preserves a shared many-to-many block and excluded source context',()=>{
    expect(groupSourceEvidence({...task,relationDisplayGroups:[{unitIds:['a','b'],bankTransactionIds:['x','y','z'],sourcesExcluded:false}]})).toHaveLength(1);
    expect(groupSourceEvidence({...task,bankEvents:[],relationDisplayGroups:[{unitIds:['a','b'],bankTransactionIds:[],sourcesExcluded:true}]})[0]).toEqual({unitIndexes:[0,1],bankIndexes:[],sourcesExcluded:true});
  });
  it('rejects broken identities instead of silently using draft alignment',()=>{
    expect(()=>groupSourceEvidence({...task,relationDisplayGroups:[{unitIds:['missing'],bankTransactionIds:[],sourcesExcluded:false}]})).toThrow('未知 OA');
    expect(()=>groupSourceEvidence({...task,relationDisplayGroups:[{unitIds:[],bankTransactionIds:['missing'],sourcesExcluded:false}]})).toThrow('未知流水');
  });
});
