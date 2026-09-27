import userEvent from '@testing-library/user-event';
import { fireEvent, render, screen, within } from '@testing-library/react';
import BankSplitTagPicker from '../features/bankSplits/BankSplitTagPicker';
import type { BankSplitTag } from '../features/bankSplits/api';

const tags: BankSplitTag[] = [
  { code: 'fee', label: '利息', path: ['费用', '利息'], primary_label: '费用', sub_label: '利息', turnover_role: '', status: 'active' },
  { code: 'repay', label: '归还借款', path: ['外部往来款', '归还借款'], primary_label: '外部往来款', sub_label: '归还借款', turnover_role: 'external_turnover', status: 'active' },
  { code: 'lend', label: '借出款', path: ['外部往来款', '借出款'], primary_label: '外部往来款', sub_label: '借出款', turnover_role: 'external_turnover', status: 'active' },
  { code: 'flat', label: '内部往来', path: ['内部往来'], primary_label: '内部往来', sub_label: '', turnover_role: '', status: 'active' },
];
const familyOptions = ['银行往来', '公司往来'].map(value => ({ value, label: value }));
const pick = (column: string, name: string) => userEvent.click(within(screen.getByRole('listbox', { name: column })).getByRole('option', { name, exact: true }));

test('columns follow the selected branch and only complete leaves emit a selection', async () => {
  const onChange = vi.fn();
  render(<BankSplitTagPicker value={{ category_code: 'repay', category_label_path: ['外部往来款', '归还借款', '银行往来'] }}
    tags={tags} familyOptions={familyOptions} label="标签" disabled={false} onChange={onChange} />);
  fireEvent.click(screen.getByRole('combobox'));
  expect(screen.getAllByRole('listbox')).toHaveLength(3);
  expect(within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '银行往来' })).toHaveAttribute('aria-selected', 'true');
  await pick('子标签', '借出款');
  expect(within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '银行往来' })).toHaveAttribute('aria-selected', 'false');
  expect(onChange).not.toHaveBeenCalled();
  await pick('主标签', '费用');
  expect(screen.getAllByRole('listbox')).toHaveLength(2);
  expect(onChange).not.toHaveBeenCalled();
  await pick('子标签', '利息');
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith({ category_code: 'fee', category_label_path: ['费用', '利息'] });
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});

test('flat labels complete in one step and missing options do not invent a category', async () => {
  const onChange = vi.fn();
  const props = { value: { category_code: '', category_label_path: [] }, tags, familyOptions, label: '标签', disabled: false, onChange };
  const { rerender } = render(<BankSplitTagPicker {...props} />);
  fireEvent.click(screen.getByRole('combobox'));
  await pick('主标签', '内部往来');
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith({ category_code: 'flat', category_label_path: ['内部往来'] });
  rerender(<BankSplitTagPicker {...props} tags={[]} />);
  fireEvent.click(screen.getByRole('combobox'));
  expect(screen.getByRole('status')).toHaveTextContent('暂无可选标签');
  expect(onChange).toHaveBeenCalledTimes(1);
});

test('Escape abandons browsing and reopening restores the saved path', async () => {
  const onChange = vi.fn();
  render(<BankSplitTagPicker value={{ category_code: 'fee', category_label_path: ['费用', '利息'] }}
    tags={tags} familyOptions={familyOptions} label="标签" disabled={false} onChange={onChange} />);
  const trigger = screen.getByRole('combobox');
  fireEvent.keyDown(trigger, { key: 'ArrowDown' });
  await pick('主标签', '外部往来款');
  await pick('子标签', '归还借款');
  fireEvent.keyDown(screen.getByRole('listbox', { name: '往来归属' }), { key: 'Escape' });
  expect(onChange).not.toHaveBeenCalled();
  expect(trigger).toHaveTextContent('费用 / 利息');
  fireEvent.click(trigger);
  expect(screen.getAllByRole('listbox')).toHaveLength(2);
  expect(within(screen.getByRole('listbox', { name: '子标签' })).getByRole('option', { name: '利息' })).toHaveAttribute('aria-selected', 'true');
});


test('choosing the current leaf completes and closes the menu', async () => {
  const onChange = vi.fn();
  render(<BankSplitTagPicker value={{ category_code: 'fee', category_label_path: ['费用', '利息'] }}
    tags={tags} familyOptions={familyOptions} label="标签" disabled={false} onChange={onChange} />);
  fireEvent.click(screen.getByRole('combobox'));
  await pick('子标签', '利息');
  expect(onChange).toHaveBeenCalledWith({ category_code: 'fee', category_label_path: ['费用', '利息'] });
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});

test('hover browses parent levels without changing the value and a leaf click commits', async () => {
  const onChange = vi.fn();
  render(<BankSplitTagPicker value={{ category_code: 'fee', category_label_path: ['费用', '利息'] }}
    tags={tags} familyOptions={familyOptions} label="标签" disabled={false} onChange={onChange} />);
  fireEvent.click(screen.getByRole('combobox'));
  await userEvent.hover(within(screen.getByRole('listbox', { name: '主标签' })).getByRole('option', { name: '外部往来款' }));
  await userEvent.hover(within(screen.getByRole('listbox', { name: '子标签' })).getByRole('option', { name: '归还借款' }));
  const bank = within(screen.getByRole('listbox', { name: '往来归属' })).getByRole('option', { name: '银行往来' });
  await userEvent.hover(bank);
  expect(screen.getByRole('combobox', { hidden: true })).toHaveTextContent('费用 / 利息');
  expect(onChange).not.toHaveBeenCalled();
  await userEvent.click(bank);
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith({ category_code: 'repay', category_label_path: ['外部往来款', '归还借款', '银行往来'] });
});

test('disabled picker cannot open and long selected paths remain available as a title', async () => {
  render(<BankSplitTagPicker value={{ category_code: 'repay', category_label_path: ['外部往来款', '归还借款', '银行往来'] }}
    tags={tags} familyOptions={familyOptions} label="标签" disabled onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole('combobox'));
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  expect(screen.getByTitle('外部往来款 / 归还借款 / 银行往来')).toBeVisible();
});
