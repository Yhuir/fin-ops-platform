import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import RelationGroupExpansion, { RelationCountButton, type RelationColumn } from '../components/common/RelationGroupExpansion';
import { useRelationExpansion } from '../hooks/useRelationExpansion';
import { originalRelationMembers } from '../features/bankSplits/originalRelationMembers';

const columns: RelationColumn[] = [
  {kind:'oa',count:2,members:[{id:'oa-1',title:'申请人甲',amount:'0',detailAvailable:true},{id:'oa-2',title:'申请人乙',detailAvailable:false}]},
  {kind:'bank',count:1,members:[{id:'bank-1',title:'交易对方',amount:'-12.30',detailAvailable:true}]},
  {kind:'invoice',count:0,members:[]},
];
function List({rows,detail}: {rows:string[];detail:ReturnType<typeof vi.fn>}) {
  const expansion = useRelationExpansion(rows);
  return <>{rows.map(id=><div key={id}>
    <RelationCountButton count={2} kind="oa" expanded={expansion.rowId===id && expansion.expanded} onClick={()=>expansion.toggle(id)} label={`${id} OA`} />
    <RelationCountButton count={2} kind="bank" expanded={expansion.rowId===id && expansion.expanded} onClick={()=>expansion.toggle(id)} label={`${id} 流水`} />
    {expansion.rowId===id && <RelationGroupExpansion columns={columns} expanded={expansion.expanded}
      onClose={()=>expansion.toggle(id)} onExited={expansion.exited} onOpenDetail={detail} />}
  </div>)}</>;
}

test('each row shares one expansion, replacing list data clears it, and detail targets exact source identity', () => {
  const detail = vi.fn(); const rows = ['first','second'];
  const view = render(<List rows={rows} detail={detail} />);
  const opener = screen.getByRole('button',{name:'first OA'});
  opener.focus(); fireEvent.click(opener);
  const region = screen.getByRole('region',{name:'配对关系'});
  expect(within(region).getByText('0.00')).toBeVisible();
  expect(within(region).getByText('-12.30')).toBeVisible();
  expect(within(region).getByRole('button',{name:'查看OA 申请人乙 详情'})).toBeDisabled();
  expect(within(region).getByText('暂无关联发票')).toBeVisible();
  expect(detail).not.toHaveBeenCalled();
  fireEvent.click(within(region).getByRole('button',{name:'查看流水 交易对方 详情'}));
  expect(detail).toHaveBeenCalledWith({kind:'bank',id:'bank-1'});
  fireEvent.click(screen.getByRole('button',{name:'first 流水'}));
  expect(opener).toHaveFocus();
  expect(opener).toHaveAttribute('aria-expanded','false');
  fireEvent.click(screen.getByRole('button',{name:'second OA'}));
  expect(screen.getAllByRole('region',{name:'配对关系'})).toHaveLength(1);
  view.rerender(<List rows={[...rows]} detail={detail} />);
  expect(screen.queryByRole('region',{name:'配对关系'})).not.toBeInTheDocument();
});

test.each([null,[{kind:'oa',count:3,members:columns[0].members}] as RelationColumn[]])('incomplete relationship is explicit and does not open a partial source list', columns => {
  render(<RelationGroupExpansion columns={columns} expanded onClose={vi.fn()} onExited={vi.fn()} onOpenDetail={vi.fn()} />);
  expect(screen.getByRole('alert')).toHaveTextContent('关系摘要不完整');
  expect(screen.queryByRole('button',{name:/详情$/})).not.toBeInTheDocument();
});

test('split uses produce one original source and retain distinct formal relationships without adding money', () => {
  expect(originalRelationMembers([
    {id:'interest',originalId:'parent',title:'贷款',amount:'1001497.22',relationId:'interest-case',detailAvailable:true},
    {id:'principal',originalId:'parent',title:'贷款',amount:'1001497.22',relationId:'principal-case',detailAvailable:true},
  ])).toEqual([expect.objectContaining({id:'parent',amount:'1001497.22',relationIds:['interest-case','principal-case']})]);
});
