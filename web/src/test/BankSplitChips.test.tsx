import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import BankSplitChips, { BankSplitPartContent } from '../features/bankSplits/BankSplitChips';

const parts = [
  { id: 'principal', category_code: 'repay', category_label: '归还借款', category_path: ['外部往来款付款', '归还借款', '银行往来'], amount: '1000000' },
  { id: 'interest', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], amount: '1497.22' },
];

test('full paths occupy separate rows and child amounts appear only in the hover overlay', async () => {
  const user = userEvent.setup();
  const { container } = render(<BankSplitChips parts={parts} />);
  expect(screen.getByText('外部往来款付款 / 归还借款 / 银行往来')).toBeVisible();
  expect(screen.getByText('费用 / 利息')).toBeVisible();
  expect(screen.queryByText('¥1000000.00')).not.toBeInTheDocument();
  expect(screen.queryByText('¥1497.22')).not.toBeInTheDocument();
  expect(container.querySelectorAll('.bank-split-part')).toHaveLength(2);
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  const trigger = screen.getByRole('button', { name: '费用 / 利息拆分金额' });
  await user.hover(trigger);
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1497.22');
  expect(container.querySelector('.bank-split-part-amount')).not.toBeInTheDocument();
});

test('keyboard focus and touch click reveal amounts without selecting a surrounding row', async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  render(<div onClick={select}><BankSplitChips parts={parts} /></div>);
  await user.tab();
  expect(await screen.findByRole('tooltip')).toHaveTextContent('¥1000000.00');
  fireEvent.blur(screen.getByRole('button', { name: /银行往来拆分金额/ }));
  await user.click(screen.getByRole('button', { name: '费用 / 利息拆分金额' }));
  expect(await screen.findByText('¥1497.22')).toBeVisible();
  expect(select).not.toHaveBeenCalled();
});

test('split chips never act as hidden selection controls', async () => {
  const user = userEvent.setup();
  const { container } = render(<BankSplitPartContent part={parts[1]} />);
  await user.click(screen.getByRole('button', { name: '费用 / 利息拆分金额' }));
  expect(screen.getByRole('button')).not.toHaveAttribute('aria-pressed');
  expect(container.querySelector('button button')).toBeNull();
});
