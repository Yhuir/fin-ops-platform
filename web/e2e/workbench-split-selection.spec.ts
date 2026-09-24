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
  Object.assign(bank, { detail_fields: { '金额': '1001497.22' }, amount: '1497.22', is_split: true, parent_row_id: 'shared-parent', parent_amount: '1001497.22', bank_split_version: 7,
    bank_split_parts: [
      { id: 'principal-other-case', amount: '1000000.00', category_code: 'principal', category_label: '归还借款', category_path: ['外部往来款', '归还借款'], relation_case_id: 'CASE-OTHER' },
      { id: bank.id, amount: '1497.22', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], relation_case_id: 'CASE-202603-101' },
    ],
  });
  group.amount_check = { status: 'matched', direction: 'payment', oa_total: '1497.22', bank_total: '1497.22', bank_related_total: '1497.22', bank_original_total: '1001497.22', invoice_total: '1497.22', requires_note: false };
  await page.route('**/api/workbench?*', route => route.fulfill({ json: payload }));
  await page.route('**/api/workbench/rows/*?*', route => {
    const { bank_split_version, ...detailRow } = bank;
    return route.fulfill({ json: { row: { ...detailRow, split_version: bank_split_version } } });
  });
  await page.route('**/api/bank-transactions/*/splits', route => route.fulfill({ json: {
    transaction_id: 'shared-parent', canonical_transaction_id: 'canonical-parent', amount: '1001497.22', direction: 'expense', version: 7,
    category_code: 'principal', category_label_path: [], turnover_third_label_options: [],
    parts: bank.bank_split_parts, tag_definitions: [], can_edit: false,
  } }));
  await page.reload();
  const relation = page.getByTestId('candidate-group-unpaired-case:CASE-202603-101');
  const bankRow = relation.locator('.record-card-bank');
  await bankRow.getByText('1001497.22', { exact: true }).click();
  const error = page.getByRole('dialog', { name: '操作状态弹窗' });
  await expect(error).toContainText('部分子项已属于其他关联');
  await error.getByRole('button', { name: '确定' }).click();
  await expect(bankRow.getByRole('button', { name: '选择流水子项' })).toHaveCount(0);
  await bankRow.getByRole('button', { name: /查看银行流水.*详情/ }).click();
  const drawer = page.getByRole('dialog', { name: '银行流水详情' });
  await expect(drawer.getByRole('button', { name: '选中子项 外部往来款 / 归还借款', exact: true })).toBeDisabled();
  await drawer.getByRole('button', { name: '选中子项 费用 / 利息', exact: true }).click();
  await expect(drawer.getByRole('button', { name: '取消选中子项 费用 / 利息' })).toHaveAttribute('aria-pressed', 'true');
  await drawer.getByRole('button', { name: '关闭详情抽屉' }).click();
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

test('saving splits clears only that bank selection and reloads the saved version before selecting again', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const initial = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workbench');
  await page.goto('/');
  const payload = await (await initial).json();
  const group = payload.unpaired.groups.find((item: { bank_rows: Array<{ id: string }> }) => item.bank_rows.some(bank => bank.id === 'bk-o-202603-001'));
  const bank = group.bank_rows[0];
  const parts = [
    { id: bank.id, amount: '57000.00', category_code: 'goods', category_label: '设备', category_path: ['货款', '设备'], relation_case_id: null },
    { id: 'second-part', amount: '1000.00', category_code: 'fee', category_label: '利息', category_path: ['费用', '利息'], relation_case_id: null },
  ];
  Object.assign(bank, { detail_fields: { '金额': '58000.00' }, amount: '57000.00', parent_row_id: 'parent-bank', parent_amount: '58000.00', is_split: true, bank_split_version: 7, bank_split_parts: parts });
  const tags = parts.map(part => ({ code: part.category_code, label: part.category_label, path: part.category_path, primary_label: part.category_path[0], sub_label: part.category_path[1], status: 'active', turnover_role: '' }));
  await page.route('**/api/workbench?*', route => route.fulfill({ json: payload }));
  await page.route('**/api/workbench/rows/*?*', route => {
    const { bank_split_version, ...detailRow } = bank;
    return route.fulfill({ json: { row: { ...detailRow, split_version: bank_split_version } } });
  });
  let writes = 0;
  await page.route('**/api/bank-transactions/*/splits', async route => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON();
      expect(body.version).toBe(7);
      parts[0].amount = body.parts[0].amount;
      parts[1].amount = body.parts[1].amount;
      bank.amount = parts[0].amount;
      bank.bank_split_version = 8;
      writes++;
    }
    await route.fulfill({ json: { transaction_id: 'parent-bank', canonical_transaction_id: 'canonical-parent', amount: '58000.00', direction: 'expense', version: bank.bank_split_version,
      category_code: 'goods', category_label_path: ['货款', '设备'], turnover_third_label_options: [], parts, tag_definitions: tags, can_edit: true, changed: true, affected_months: [] } });
  });
  await page.reload();
  const zone = page.getByTestId('zone-unpaired');
  const bankRow = zone.locator('.record-card-bank').filter({ hasText: '智能工厂设备商' });
  await bankRow.getByText('58000.00', { exact: true }).click();
  await expect(zone.getByText('已选 2', { exact: true })).toBeVisible();
  await bankRow.getByRole('button', { name: /查看银行流水.*详情/ }).click();
  const drawer = page.getByRole('dialog', { name: '银行流水详情' });
  await drawer.getByLabel('子项 1 金额').fill('56999.00');
  await drawer.getByLabel('子项 2 金额').fill('1001.00');
  await expect(drawer.getByRole('button', { name: '取消选中子项 费用 / 利息' })).toBeDisabled();
  await drawer.getByRole('button', { name: '保存', exact: true }).click();
  await expect(drawer.getByLabel('子项 2 金额')).toHaveValue('1001.00');
  await expect(drawer.getByRole('button', { name: '选中子项 费用 / 利息', exact: true })).toBeEnabled();
  expect(writes).toBe(1);
  await drawer.getByRole('button', { name: '选中子项 费用 / 利息', exact: true }).click();
  await drawer.getByRole('button', { name: '关闭详情抽屉' }).click();
  await expect(zone.getByText('已选 1', { exact: true })).toBeVisible();
  await expect(zone.getByText('流水 1 / 1001.00', { exact: true })).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
});
