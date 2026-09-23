import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from './fixtures/apiMocks';

test('bank detail adds labeled children, persists exact amounts and reloads complete saved children', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const tagDefinitions = [
    { code: 'principal', label: '外部往来款 / 归还借款', path: ['外部往来款', '归还借款'], primary_label: '外部往来款', sub_label: '归还借款', status: 'active', turnover_role: 'external_turnover' },
    { code: 'interest', label: '费用 / 利息', path: ['费用', '利息'], primary_label: '费用', sub_label: '利息', status: 'active', turnover_role: '' },
  ];
  let state = { transaction_id: 'bk-o-202603-001', canonical_transaction_id: 'canonical-bank-1', amount: '58000.00', direction: 'expense', version: 0,
    category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '银行往来'], turnover_third_label_options: [{ value: '银行往来', label: '银行往来' }], parts: [] as Array<{ id: string; category_code: string; category_label: string; category_path: string[]; amount: string }>, tag_definitions: tagDefinitions, can_edit: true };
  let writes = 0;
  let rejectSave = false;
  await page.route('**/api/bank-transactions/*/splits', async route => {
    if (route.request().method() === 'PUT') {
      if (rejectSave) {
        await route.fulfill({ status: 503, json: { error: 'temporarily_unavailable', message: '保存暂时不可用' } });
        return;
      }
      const body = route.request().postDataJSON();
      expect(body.version).toBe(state.version);
      expect(body.parts).toEqual([{ category_code: 'principal', category_label_path: ['外部往来款', '归还借款', '银行往来'], amount: '56502.78' }, { category_code: 'interest', category_label_path: ['费用', '利息'], amount: '1497.22' }]);
      state = { ...state, version: state.version + 1, parts: body.parts.map((part: { category_code: string; category_label_path: string[]; amount: string }, index: number) => {
        const tag = tagDefinitions.find(item => item.code === part.category_code)!;
        return { ...part, id: `part-${index + 1}`, category_label: tag.label, category_path: part.category_label_path };
      }) };
      writes += 1;
    }
    await route.fulfill({ json: { ...state, changed: true, affected_months: ['2026-03'] } });
  });
  await page.goto('/bank-details');
  await page.getByRole('button', { name: '查看银行流水 智能工厂设备商 详情' }).click();
  const drawer = page.getByRole('dialog', { name: '银行流水详情' });
  await expect(drawer.getByText('流水子项拆分', { exact: true })).toBeVisible();
  for (const [index, primary, child, amount] of [[1, '外部往来款', '归还借款', '56502.78'], [2, '费用', '利息', '1497.22']] as const) {
    await drawer.getByRole('button', { name: '新增流水子项' }).click();
    await drawer.getByRole('combobox', { name: `子项 ${index} 标签` }).click();
    await page.getByRole('listbox', { name: '主标签' }).getByRole('option', { name: primary, exact: true }).click();
    await page.getByRole('listbox', { name: '子标签' }).getByRole('option', { name: child, exact: true }).click();
    if (index === 1) await drawer.getByLabel('子项 1 往来归属').selectOption('银行往来');
    await drawer.getByLabel(`子项 ${index} 金额`).fill(amount);
  }
  expect(writes).toBe(0);
  await drawer.getByRole('button', { name: '保存', exact: true }).click();
  await expect(drawer.getByText('已保存', { exact: true })).toBeVisible();
  expect(writes).toBe(1);
  await expectNoUnexpectedSuccessUiErrors(page);
  await drawer.getByRole('button', { name: '关闭抽屉' }).click();
  await page.getByRole('button', { name: '查看银行流水 智能工厂设备商 详情' }).click();
  await expect(drawer.getByLabel('子项 1 金额')).toHaveValue('56502.78');
  await expect(drawer.getByLabel('子项 2 金额')).toHaveValue('1497.22');
  await expect(drawer.getByRole('combobox', { name: '子项 2 标签' })).toContainText('费用 / 利息');
  rejectSave = true;
  await drawer.getByLabel('子项 1 金额').fill('56500.00');
  await drawer.getByLabel('子项 2 金额').fill('1500.00');
  await drawer.getByRole('button', { name: '保存', exact: true }).click();
  await expect(drawer.getByRole('alert')).toContainText('保存暂时不可用');
  await expect(drawer.getByLabel('子项 2 金额')).toHaveValue('1500.00');
  expect(writes).toBe(1);
  await drawer.getByRole('button', { name: '取消', exact: true }).click();
  await drawer.getByRole('button', { name: '关闭抽屉' }).click();
  await page.getByRole('button', { name: '查看银行流水 智能工厂设备商 详情' }).click();
  await expect(drawer.getByLabel('子项 1 金额')).toHaveValue('56502.78');
  await expect(drawer.getByLabel('子项 2 金额')).toHaveValue('1497.22');
  await expectNoUnexpectedSuccessUiErrors(page);
});
