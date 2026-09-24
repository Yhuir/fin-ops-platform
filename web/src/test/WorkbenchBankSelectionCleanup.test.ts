import { act, renderHook } from '@testing-library/react';
import useWorkbenchSelection from '../hooks/useWorkbenchSelection';
import type { WorkbenchRecord } from '../features/workbench/types';

const row = (id: string, recordType: WorkbenchRecord['recordType'], parentRowId?: string) => ({ id, recordType, parentRowId } as WorkbenchRecord);
test('post-save cleanup removes children in both zones, preserves other banks and OA and leaves detail open', () => {
  const { result } = renderHook(() => useWorkbenchSelection());
  const child = row('part', 'bank', 'parent');
  act(() => {
    result.current.toggleOpenRowSelection([child, row('other', 'bank'), row('part', 'oa')]);
    result.current.togglePairedRowSelection([row('sibling', 'bank', 'parent')]);
    result.current.openDetail(child);
  });
  act(() => result.current.clearBankSelection('parent'));
  expect(result.current.selectedOpenRows.map(item => `${item.recordType}:${item.id}`)).toEqual(['bank:other', 'oa:part']);
  expect(result.current.selectedPairedRows).toEqual([]);
  expect(result.current.detailRow).toEqual(child);
});
