import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';
import { expectNoUnexpectedSuccessUiErrors } from './fixtures/successAssertions';

test('search-visible split child selects canonical siblings and preserves preview versions through confirmation', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const initial = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workbench');
  await page.goto('/');
  const payload = await (await initial).json();
  const parts = [
    { id: 'principal-child', amount: '1000000.00', category_code: 'principal', category_label: '归还借款', category_path: ['外部往来款', '归还借款'], relation_case_id: null },
    { id: 'interest-child', amount: '1497.22', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], relation_case_id: null },
  ];
  for (const group of payload.unpaired.groups) {
    group.bank_rows = group.bank_rows.map((bank: { id: string }) => bank.id === 'bk-o-202603-001' ? {
      ...bank, id: 'interest-child', amount: '1497.22', parent_row_id: 'bank-parent', parent_amount: '1001497.22',
      is_split: true, bank_split_version: 7, bank_split_parts: parts,
    } : bank);
  }
  await page.route('**/api/workbench?*', route => route.fulfill({ json: payload }));
  const requestBodies: Array<Record<string, unknown>> = [];
  await page.route('**/api/workbench/actions/confirm-link/preview', route => {
    requestBodies.push(route.request().postDataJSON());
    return route.fulfill({ json: { operation: 'confirm_link', bank_split_versions: { 'bank-parent': 7 },
      can_submit: true, requires_note: false, before: { groups: [] }, after: { groups: [] },
      amount_summary: { before: {}, after: {}, status: 'matched', direction: 'payment', mismatch_fields: [] },
    } });
  });
  await page.route('**/api/workbench/actions/confirm-link', route => {
    requestBodies.push(route.request().postDataJSON());
    return route.fulfill({ json: { success: true, action: 'confirm_link', month: 'all', affected_row_ids: ['principal-child', 'interest-child'], message: '已确认关联' } });
  });
  await page.reload();
  const zone = page.getByTestId('zone-unpaired');
  const bank = zone.getByRole('row', { name: /2026-03-28.*智能工厂设备商.*1001497.22/ });
  await expect(bank).toBeVisible();
  await bank.getByRole('button', { name: '费用 / 利息拆分金额' }).click();
  await expect(bank).toHaveAttribute('data-row-state', 'idle');
  await expect(page.getByRole('tooltip')).toHaveText('¥1497.22');
  await bank.getByText('1001497.22', { exact: true }).click();
  await expect(bank).toHaveAttribute('data-row-state', 'selected');
  await zone.getByRole('row', { name: /陈涛.*智能工厂设备商/ }).click();
  await expect(zone.getByText('已选 3', { exact: true })).toBeVisible();
  await zone.getByRole('button', { name: '确认关联' }).click();
  const preview = page.getByRole('dialog', { name: '确认关联' });
  await expect(preview).toBeVisible();
  expect(requestBodies[0].row_ids).toEqual(['principal-child', 'interest-child', 'oa-o-202603-001']);
  await preview.getByRole('button', { name: '确认关联' }).click();
  await expect(preview.getByRole('status')).toHaveText('关联操作已完成');
  expect(requestBodies[1].row_ids).toEqual(requestBodies[0].row_ids);
  expect(requestBodies[1].bank_split_versions).toEqual({ 'bank-parent': 7 });
  await expectNoUnexpectedSuccessUiErrors(page);
});

test('a split sibling owned elsewhere cannot be selected wholesale but the current relation remains withdrawable', async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: 'user', workbenchInitialIncompleteRelation: true });
  const initial = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workbench');
  await page.goto('/');
  const payload = await (await initial).json();
  const group = payload.unpaired.groups.find((item: { group_id: string }) => item.group_id === 'case:CASE-202603-101');
  const bank = group.bank_rows[0];
  Object.assign(bank, { amount: '1497.22', is_split: true, parent_row_id: 'shared-parent', parent_amount: '1001497.22', bank_split_version: 7,
    bank_split_parts: [
      { id: 'principal-other-case', amount: '1000000.00', category_code: 'principal', category_label: '归还借款', category_path: ['外部往来款', '归还借款'], relation_case_id: 'CASE-OTHER' },
      { id: bank.id, amount: '1497.22', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], relation_case_id: 'CASE-202603-101' },
    ],
  });
  group.amount_check = { status: 'matched', direction: 'payment', oa_total: '1497.22', bank_total: '1497.22', bank_related_total: '1497.22', bank_original_total: '1001497.22', invoice_total: '1497.22', requires_note: false };
  await page.route('**/api/workbench?*', route => route.fulfill({ json: payload }));
  await page.reload();
  const relation = page.getByTestId('candidate-group-unpaired-case:CASE-202603-101');
  const bankRow = relation.locator('.record-card-bank');
  await bankRow.getByText('1001497.22', { exact: true }).click();
  const error = page.getByRole('dialog', { name: '操作状态弹窗' });
  await expect(error).toContainText('部分子项已属于其他关联');
  await error.getByRole('button', { name: '确定' }).click();
  await bankRow.getByRole('button', { name: '选择流水子项' }).click();
  await expect(page.getByRole('menuitem', { name: /外部往来款/ })).toBeDisabled();
  await page.getByRole('menuitem', { name: /费用.*利息/ }).click();
  const zone = page.getByTestId('zone-unpaired');
  await expect(zone.getByText('带入 2', { exact: true })).toBeVisible();
  await expect(zone.getByRole('button', { name: '撤回关联' })).toBeEnabled();
  await zone.getByRole('button', { name: '撤回关联' }).click();
  await expect(page.getByRole('dialog', { name: '撤回关联' })).toBeVisible();
  const request = api.lastBody('POST /api/workbench/actions/withdraw-link/preview');
  expect(request.row_ids).toEqual(['oa-o-202603-001', 'bk-o-202603-001', 'iv-o-202603-001']);
  expect(request.row_ids).not.toContain('principal-other-case');
  await page.unroute('**/api/workbench?*');
  const preview = page.getByRole('dialog', { name: '撤回关联' });
  await preview.getByRole('button', { name: '确认撤回' }).click();
  await expect(preview.getByRole('status')).toHaveText('关联操作已完成');
  const confirmed = api.lastBody('POST /api/workbench/actions/withdraw-link');
  expect(confirmed.row_ids).toEqual(request.row_ids);
  expect(confirmed.row_ids).not.toContain('principal-other-case');
});
