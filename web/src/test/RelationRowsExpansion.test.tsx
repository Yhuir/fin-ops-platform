import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { RelationCountButton } from '../components/common/RelationCountButton';
import RelationRowsMotion, { RelationAnimatedCell } from '../components/common/RelationRowsMotion';
import { useRelationExpansion, useRelationRowExpansion } from '../hooks/useRelationExpansion';
import { originalRelationMembers } from '../features/bankSplits/originalRelationMembers';

test('invoice and source views share one parent selection and replacing rows clears both views', () => {
  const rows = ['first', 'second'];
  const { result, rerender } = renderHook(({ rows }) => useRelationExpansion(rows), { initialProps: { rows } });
  act(() => result.current.toggle('first', 'invoice'));
  expect(result.current).toMatchObject({ rowId: 'first', view: 'invoice', expanded: true });
  act(() => result.current.toggle('first', 'oa'));
  expect(result.current).toMatchObject({ rowId: 'first', view: 'oa', expanded: true });
  act(() => result.current.toggle('second', 'invoice'));
  expect(result.current).toMatchObject({ rowId: 'second', view: 'invoice', expanded: true });
  rerender({ rows: [...rows] });
  expect(result.current).toMatchObject({ rowId: null, view: null, expanded: false });
});

test('an old exit cannot clear another closing parent or view, and the owned exit clears it', () => {
  // Keep one list identity across renders, just as a loaded response does.
  const rows: string[] = [];
  const owned = renderHook(() => useRelationExpansion(rows));
  act(() => owned.result.current.toggle('first', 'oa'));
  const firstExit = owned.result.current.exited;
  act(() => owned.result.current.toggle('second', 'oa'));
  act(() => owned.result.current.toggle('second', 'oa'));
  act(firstExit);
  expect(owned.result.current).toMatchObject({ rowId: 'second', view: 'oa', expanded: false });
  act(owned.result.current.exited);
  expect(owned.result.current.rowId).toBeNull();
  act(() => owned.result.current.toggle('first', 'oa'));
  const sourceExit = owned.result.current.exited;
  act(() => owned.result.current.toggle('first', 'invoice'));
  act(() => owned.result.current.toggle('first', 'invoice'));
  act(sourceExit);
  expect(owned.result.current).toMatchObject({ rowId: 'first', view: 'invoice', expanded: false });
});

test('split uses produce one original source and retain distinct formal relationships without adding money', () => {
  expect(originalRelationMembers([
    {id:'interest',originalId:'parent',title:'贷款',amount:'1001497.22',relationId:'interest-case',detailAvailable:true},
    {id:'principal',originalId:'parent',title:'贷款',amount:'1001497.22',relationId:'principal-case',detailAvailable:true},
  ])).toEqual([expect.objectContaining({id:'parent',amount:'1001497.22',relationIds:['interest-case','principal-case']})]);
});

test('button count includes the original member and exposes its own expanded state', () => {
  const click = vi.fn();
  render(<RelationCountButton kind="invoice" count={3} expanded onClick={click} />);
  const button = screen.getByRole('button', { name: '收起配对关系，发票共 3 张' });
  expect(button).toHaveTextContent('共 3 张');
  expect(button).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(button); expect(click).toHaveBeenCalledOnce();
});

test('outgoing members retain their view until exit; an old row exit cannot clear a new row', () => {
  const rows = ['a', 'b'];
  const hook = renderHook(() => {
    const expansion = useRelationExpansion(rows);
    return { expansion, a: useRelationRowExpansion('a', expansion), b: useRelationRowExpansion('b', expansion) };
  });
  act(() => hook.result.current.expansion.toggle('a', 'invoice'));
  act(() => hook.result.current.expansion.toggle('b', 'bank'));
  expect(hook.result.current.a).toMatchObject({ view: 'invoice', expanded: false });
  act(hook.result.current.a.onExited);
  expect(hook.result.current.a.view).toBeNull();
  expect(hook.result.current.b).toMatchObject({ view: 'bank', expanded: true });
});

test('row motion uses native cells without adding a summary row; reduced motion closes immediately', () => {
  vi.mocked(window.matchMedia).mockReturnValue({ matches: true } as MediaQueryList);
  const exit = vi.fn();
  const view = render(<table><tbody><RelationRowsMotion expanded onExited={exit}>
    <tr><td><RelationAnimatedCell>first</RelationAnimatedCell></td><td><RelationAnimatedCell>second</RelationAnimatedCell></td></tr>
  </RelationRowsMotion></tbody></table>);
  expect(screen.getAllByRole('row')).toHaveLength(1);
  expect(screen.getAllByRole('cell')).toHaveLength(2);
  expect(exit).not.toHaveBeenCalled();
  view.rerender(<table><tbody><RelationRowsMotion expanded={false} onExited={exit}>
    <tr><td><RelationAnimatedCell>first</RelationAnimatedCell></td><td><RelationAnimatedCell>second</RelationAnimatedCell></td></tr>
  </RelationRowsMotion></tbody></table>);
  expect(exit).toHaveBeenCalledOnce();
});

test('cells registered after the motion owner mounts still slide in from zero', () => {
  const animate = vi.spyOn(HTMLElement.prototype, 'animate');
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(100);
  const exit = vi.fn();
  const view = render(<RelationRowsMotion expanded onExited={exit}>{null}</RelationRowsMotion>);
  expect(animate).not.toHaveBeenCalled();
  view.rerender(<RelationRowsMotion expanded onExited={exit}>
    <table><tbody><tr><td><RelationAnimatedCell>delayed member</RelationAnimatedCell></td></tr></tbody></table>
  </RelationRowsMotion>);
  expect(animate).toHaveBeenCalledWith([{ height: '0px' }, { height: '100px' }], expect.objectContaining({ duration: 220 }));
  expect(exit).not.toHaveBeenCalled();
});
