import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import TableClassificationHeader from '../components/common/TableClassificationHeader';

test('shows independent branch counts, partial selection, keyboard actions and unknown errors', async () => {
  const select = vi.fn();
  const props = { label: '分类', unit: '笔' as const, pending: false, invalid: false,
    root: { id: 'all', label: '全部', count: 7 },
    groups: [{ id: 'expense', label: '支出', count: 7, tone: 'blue' as const,
      children: [{ id: 'review', label: '金额待核对', count: 7, selected: 'mixed' as const, onSelect: select },
        { id: 'none', label: '无需发票', count: 0, onSelect: select }] }],
  };
  const { rerender } = render(<TableClassificationHeader {...props} />);
  expect(screen.getByRole('group', { name: '支出' })).toBeInTheDocument();
  const review = screen.getByRole('button', { name: '金额待核对 7 笔' });
  expect(review).toHaveAttribute('aria-pressed', 'mixed');
  review.focus(); await userEvent.keyboard('{Enter}'); expect(select).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: '无需发票 0 笔' })).toBeEnabled();
  rerender(<TableClassificationHeader {...props} pending />);
  expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true');
  expect(review).toHaveTextContent('7 笔');
  rerender(<TableClassificationHeader {...props} invalid />);
  expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'false');
  expect(screen.getByRole('button', { name: '金额待核对 — 笔' })).toBeInTheDocument();
  expect(screen.queryByText('0 笔')).not.toBeInTheDocument();
});
