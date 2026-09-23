import { render, screen } from '@testing-library/react';
import BankSplitChips from '../features/bankSplits/BankSplitChips';

test('all consumers display explicit primary, child and instance classification with exact two-decimal child amounts', () => {
  const { container } = render(<BankSplitChips parts={[
    { id: 'principal', category_code: 'repay', category_label: '归还借款', category_path: ['外部往来款付款', '归还借款', '银行往来'], amount: '1000000' },
    { id: 'interest', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], amount: '1497.2' },
  ]} />);
  expect(screen.getByText('外部往来款付款 / 归还借款 / 银行往来')).toBeVisible();
  expect(screen.getByText('费用 / 利息')).toBeVisible();
  expect(screen.getByText('1000000.00')).toHaveClass('bank-split-part-amount');
  expect(screen.getByText('1497.20')).toHaveClass('bank-split-part-amount');
  expect(container.querySelectorAll('.bank-split-part')).toHaveLength(2);
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByText(/另.*项/)).not.toBeInTheDocument();
});
