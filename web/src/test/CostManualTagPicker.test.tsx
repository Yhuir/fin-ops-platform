import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import CostManualTagPicker from '../components/cost-statistics/CostManualTagPicker';
const tags = [
  {code:'salary',label:'薪资社保福利 / 工资',primary_label:'薪资社保福利',sub_label:'工资'},
  {code:'transport',label:'费用 / 运费/邮费/杂费',primary_label:'费用',sub_label:'运费/邮费/杂费'},
  {code:'internal_transfer',label:'内部往来款',primary_label:'内部往来款',sub_label:''},
  {code:'other_salary',label:'其他 / 工资',primary_label:'其他',sub_label:'工资'},
];
it('uses current structured hierarchy and codes, preserves slashes and single-level tags', async () => {
  const user=userEvent.setup(), onChange=vi.fn(), onLoad=vi.fn();
  render(<CostManualTagPicker tags={tags} value="salary" savedLabel="" loading={false} disabled={false} onChange={onChange} onLoad={onLoad} />);
  const trigger=screen.getByRole('combobox',{name:'人工成本标签'});
  await user.click(trigger);
  expect(within(screen.getByRole('listbox',{name:'子标签'})).getByRole('option',{name:'工资'})).toBeVisible();
  await user.click(screen.getByRole('option',{name:'费用',exact:true}));
  await user.click(screen.getByRole('option',{name:'运费/邮费/杂费',exact:true}));
  expect(onChange).toHaveBeenLastCalledWith(tags[1]);
  await user.click(trigger);
  await user.click(screen.getByRole('option',{name:'其他',exact:true}));
  await user.click(screen.getByRole('option',{name:'工资',exact:true}));
  expect(onChange).toHaveBeenLastCalledWith(tags[3]);
  await user.click(trigger);
  await user.click(screen.getByRole('option',{name:'内部往来款',exact:true}));
  expect(onChange).toHaveBeenLastCalledWith(tags[2]);
  expect(onLoad).toHaveBeenCalledTimes(3);
});
it('hides stale options on loading/failure, supports retry, preserves archived label',async()=>{
  const user=userEvent.setup(), onLoad=vi.fn(), onChange=vi.fn();
  const props={tags,value:'old',savedLabel:'旧标签',loading:true,disabled:false,onLoad,onChange};
  const {rerender}=render(<CostManualTagPicker {...props}/>);
  await user.click(screen.getByRole('combobox'));
  expect(screen.getByRole('status')).toHaveTextContent('正在读取标签');
  expect(screen.queryByRole('option')).not.toBeInTheDocument();
  rerender(<CostManualTagPicker {...props} loading={false} error="标签读取失败，请重试"/>);
  expect(screen.getByRole('alert')).toHaveTextContent('读取失败');
  expect(screen.queryByRole('option')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'重试'}));
  expect(onLoad).toHaveBeenCalledTimes(2);
  expect(onChange).not.toHaveBeenCalled();
  await user.keyboard('{Escape}');
  expect(screen.getByRole('combobox')).toHaveTextContent('旧标签（已停用）');
});
it('disabled picker cannot open or request data',async()=>{
  const user=userEvent.setup(), onLoad=vi.fn();
  render(<CostManualTagPicker tags={tags} value="" savedLabel="" loading={false} disabled onLoad={onLoad} onChange={vi.fn()}/>);
  await user.click(screen.getByRole('combobox'));
  expect(onLoad).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
