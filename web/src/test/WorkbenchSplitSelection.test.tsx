import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { installMockApiFetch } from './apiMock';
import { renderWorkbenchPage } from './workbenchRenderHelpers';

afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

function installSplitFixture(owner: string | null = null) {
  const fetchMock = installMockApiFetch();
  const original = fetchMock.getMockImplementation()!;
  const parts = [
    { id: 'principal-child', amount: '1000000.00', category_code: 'principal', category_label: '归还借款', category_path: ['外部往来款', '归还借款'], relation_case_id: owner },
    { id: 'interest-child', amount: '1497.22', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], relation_case_id: null },
  ];
  const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://localhost').pathname;
    if (path === '/api/workbench/actions/confirm-link/preview') {
      requests.push({ path, body: JSON.parse(String(init?.body)) });
      return new Response(JSON.stringify({ operation: 'confirm_link', bank_split_versions: { 'bank-parent': 7 },
        can_submit: true, requires_note: false, before: { groups: [] }, after: { groups: [] },
        amount_summary: { before: {}, after: {}, status: 'matched', direction: 'payment', mismatch_fields: [] },
      }));
    }
    if (path === '/api/workbench/actions/confirm-link') {
      requests.push({ path, body: JSON.parse(String(init?.body)) });
      return new Response(JSON.stringify({ success: true, action: 'confirm_link', month: 'all', affected_row_ids: ['principal-child', 'interest-child'], message: '已确认关联' }));
    }
    const response = await original(input, init);
    if (path !== '/api/workbench') return response;
    const payload = await response.json();
    payload.unpaired.groups = payload.unpaired.groups.map((group: { bank_rows: Array<Record<string, unknown>> }) => ({
      ...group, bank_rows: group.bank_rows.map(bank => bank.id === 'bk-o-202603-001' ? {
        ...bank, id: 'interest-child', amount: '1497.22', parent_row_id: 'bank-parent', parent_amount: '1001497.22',
        is_split: true, bank_split_version: 7, bank_split_parts: parts,
      } : bank),
    }));
    return new Response(JSON.stringify(payload));
  });
  return requests;
}

test('visible interest child selects whole bank, preview and confirm carry both IDs and preview split version', async () => {
  const user = userEvent.setup();
  const requests = installSplitFixture();
  renderWorkbenchPage();
  const bankRow = await screen.findByRole('row', { name: /2026-03-28.*智能工厂设备商.*1001497.22/ });
  await user.click(within(bankRow).getByRole('button', { name: '费用 / 利息拆分金额' }));
  expect(bankRow).toHaveAttribute('data-row-state', 'idle');
  fireEvent.click(bankRow);
  expect(bankRow).toHaveAttribute('data-row-state', 'selected');
  await user.click(await screen.findByRole('row', { name: /陈涛.*智能工厂设备商/ }));
  const zone = screen.getByTestId('zone-unpaired');
  expect(within(zone).getByText('已选 3')).toBeInTheDocument();
  await user.click(within(zone).getByRole('button', { name: '确认关联' }));
  const dialog = await screen.findByRole('dialog', { name: '确认关联' });
  expect(requests[0].body.row_ids).toEqual(['principal-child', 'interest-child', 'oa-o-202603-001']);
  await user.click(within(dialog).getByRole('button', { name: '确认关联' }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1].body.row_ids).toEqual(requests[0].body.row_ids);
  expect(requests[1].body.bank_split_versions).toEqual({ 'bank-parent': 7 });
});

test('occupied sibling blocks whole selection with explicit feedback and sends no mutation', async () => {
  const requests = installSplitFixture('other-relation');
  renderWorkbenchPage();
  const bankRow = await screen.findByRole('row', { name: /2026-03-28.*智能工厂设备商.*1001497.22/ });
  fireEvent.click(bankRow);
  expect(await screen.findByRole('dialog', { name: '操作状态弹窗' })).toHaveTextContent('部分子项已属于其他关联');
  expect(bankRow).toHaveAttribute('data-row-state', 'idle');
  expect(requests).toEqual([]);
});
