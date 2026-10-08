import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import TableClassificationHeader from '../components/common/TableClassificationHeader';

test('shows independent branch counts, selection, keyboard actions and unknown errors', async () => {
  const select = vi.fn();
  const props = { label: '分类', unit: '笔' as const, pending: false, invalid: false,
    root: { id: 'all', label: '全部', count: 7 },
    groups: [{ id: 'expense', label: '支出', count: 7, tone: 'blue' as const,
      children: [{ id: 'review', label: '金额待核对', count: 7, selected: false, onSelect: select },
        { id: 'none', label: '无需发票', count: 0, onSelect: select }] }],
  };
  const { rerender } = render(<TableClassificationHeader {...props} />);
  expect(screen.getByRole('group', { name: '支出' })).toBeInTheDocument();
  const review = screen.getByRole('button', { name: '金额待核对 7 笔' });
  expect(review).toHaveAttribute('aria-pressed', 'false');
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


test('parent selection does not mark children and transfers cleanly to a leaf', () => {
  const onSelect = vi.fn();
  const props = { label: '分类', unit: '张' as const, pending: false, invalid: false,
    root: { id: 'all', label: '全部', count: 2, onSelect },
    groups: [{ id: 'paid', label: '蓝字', count: 2, selected: true, onSelect, tone: 'blue' as const,
      children: [{ id: 'received', label: '已收款', count: 2, selected: false, onSelect }] }],
  };
  const { container, rerender } = render(<TableClassificationHeader {...props} />);
  expect(container.querySelectorAll('[aria-pressed="true"]')).toHaveLength(1);
  expect(screen.getByRole('button', { name: '蓝字 2 张' })).toHaveAttribute('aria-pressed', 'true');
  rerender(<TableClassificationHeader {...props} groups={[{ ...props.groups[0], selected: false,
    children: [{ ...props.groups[0].children[0], selected: true }] }]} />);
  expect(container.querySelectorAll('[aria-pressed="true"]')).toHaveLength(1);
  expect(screen.getByRole('button', { name: '已收款 2 张' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: '蓝字 2 张' })).toHaveAttribute('aria-pressed', 'false');
});
