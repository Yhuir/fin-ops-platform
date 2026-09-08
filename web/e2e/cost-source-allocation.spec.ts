import { expect, test, type Page } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from './fixtures/apiMocks';

async function sourceScenario(page: Page, options: { missingTag?: boolean; conflict?: boolean; canSave?: boolean } = {}) {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const task = {
    relation_case_id: 'source-case', relation_version: 1, source_fingerprint: 'a'.repeat(64),
    status: 'pending', pending_reasons: options.missingTag ? ['bank_tag_missing'] : ['source_required'], amounts_fixed: true,
    oa_total: '600.00', gross_outflow_total: '600.00', wrong_payment_refund_total: '0.00', net_outflow_total: '600.00',
    units: [{ unit_id: 'oa-1', oa_id: 'OA-202608-001', oa_apply_type: '支付申请', expense_item_id: '', project_id: 'p-1', project_name: '云南溯源科技', expense_type: '原 OA 材料费用', expense_content: '设备安装项目材料采购', oa_applicant: '测试申请人', oa_original_amount: '600.00' }],
    bank_events: [
      { transaction_id: 'bank-a', event_kind: 'outflow', amount: '350.00', trade_time: '2026-08-15', counterparty_name: '设备供应商', bank_account_label: '建设银行 8106', bank_tag_code: options.missingTag ? '' : 'material', bank_tag_primary_label: options.missingTag ? '' : '采购', bank_tag_sub_label: options.missingTag ? '' : '材料款', tags: options.missingTag ? [] : ['采购', '材料款'] },
      { transaction_id: 'bank-b', event_kind: 'outflow', amount: '250.00', trade_time: '2026-09-03', counterparty_name: '设备供应商', bank_account_label: '民生银行 9486', bank_tag_code: 'material', bank_tag_primary_label: '采购', bank_tag_sub_label: '材料款', tags: ['采购', '材料款'] },
    ],
    allocations: [{ unit_id: 'oa-1', amount: '600.00' }], source_allocations: null as unknown,
    non_cost_amount: '0.00', non_cost_reason: '', version: 0, updated_by: '', updated_at: '', can_save: options.canSave !== false,
  };
  let writes = 0; let details = 0; let savedBody: Record<string, any> | null = null;
  await page.route('**/api/cost-statistics/manual-allocations**', async route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'PUT') {
      writes++; savedBody = route.request().postDataJSON();
      if (options.conflict) return route.fulfill({ status: 409, json: { error: 'cost_statistics_manual_allocation_conflict', message: '关联事实已变化，请保留草稿并重新核对。' } });
      task.source_allocations = savedBody!.source_allocations;
      task.version++; task.status = options.missingTag ? 'pending' : 'allocated';
      task.pending_reasons = options.missingTag ? ['bank_tag_missing'] : [];
      return route.fulfill({ json: task });
    }
    if (url.pathname.endsWith('/source-case')) { details++; return route.fulfill({ json: task }); }
    const { units, bank_events, allocations, source_allocations, ...summary } = task;
    return route.fulfill({ json: {
      items: url.searchParams.get('status') === task.status ? [{ ...summary, project_names: ['云南溯源科技'], unit_count: 1, bank_event_count: 2 }] : [],
      row_count: 1, counts: { pending: task.status === 'pending' ? 1 : 0, allocated: task.status === 'allocated' ? 1 : 0 }, next_cursor: null,
    } });
  });
  await page.goto('/cost-statistics');
  await expect(page.getByRole('heading', { name: '成本统计' })).toBeVisible();
  expect(details).toBe(0);
  await page.getByRole('button', { name: '打开成本人工分配' }).click();
  const drawer = page.getByRole('dialog', { name: '成本人工分配' });
  await expect(drawer.getByText('银行流水证据')).toBeVisible();
  const unit = drawer.locator('.cost-source-unit').filter({ hasText: '原 OA 材料费用' });
  return { drawer, unit, task, writes: () => writes, body: () => savedBody };
}

async function fillSources(page: Page, unit: ReturnType<Page['locator']>) {
  for (const [index, amount] of ['350', '250'].entries()) {
    await unit.getByRole('button', { name: '新增来源', exact: true }).click();
    const source = unit.getByRole('button', { name: new RegExp(`来源流水 ${index + 1}`) });
    await expect(source).toBeFocused();
    await source.press('ArrowDown');
    await page.getByRole('option', { name: new RegExp(`${amount}.00`) }).click();
    await unit.getByRole('textbox', { name: `分配金额 ${index + 1}`, exact: true }).fill(amount);
  }
}

test('splits 600 across real bank accounts, moves only completed tasks, and preserves the source matrix', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const scene = await sourceScenario(page);
  await fillSources(page, scene.unit);
  await expect(scene.drawer.locator('.cost-source-evidence-card').getByText('剩余 0.00', { exact: false })).toHaveCount(2);
  await expect(scene.unit.getByText('2026-08-15', { exact: true }).last()).toBeVisible();
  await expect(scene.unit.getByText('2026-09-03', { exact: true }).last()).toBeVisible();
  await page.screenshot({ path: '/tmp/cost-source-app-1440.png', fullPage: false, animations: "disabled" });
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('当前没有待分配任务')).toBeVisible();
  expect(scene.writes()).toBe(1);
  expect(scene.body()!.source_allocations).toEqual({ cost_lines: [
    { unit_id: 'oa-1', bank_transaction_id: 'bank-a', amount: '350.00' },
    { unit_id: 'oa-1', bank_transaction_id: 'bank-b', amount: '250.00' },
  ], refund_links: [], non_cost_lines: [] });
  await scene.drawer.getByRole('radio', { name: '已完成 1' }).click();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 1', exact: true })).toHaveValue('350.00');
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 2', exact: true })).toHaveValue('250.00');
  await expectNoUnexpectedSuccessUiErrors(page);
});

test('keeps a saved task pending when a bank tag is missing and rehydrates after reopening', async ({ page }) => {
  const scene = await sourceScenario(page, { missingTag: true });
  await fillSources(page, scene.unit);
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('来源分配已保存，仍有银行信息待完善')).toBeVisible();
  await expect(scene.drawer.getByRole('radio', { name: '待分配 1' })).toBeVisible();
  await scene.drawer.getByRole('button', { name: /关闭/ }).click();
  await page.getByRole('button', { name: '打开成本人工分配' }).click();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 2', exact: true })).toHaveValue('250.00');
  await expectNoUnexpectedSuccessUiErrors(page);
});

test('retains input after a stale-version conflict and blocks incomplete amounts locally', async ({ page }) => {
  const scene = await sourceScenario(page, { conflict: true });
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  expect(scene.writes()).toBe(0);
  await fillSources(page, scene.unit);
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('关联事实已变化，请保留草稿并重新核对。')).toBeVisible();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 2', exact: true })).toHaveValue('250');
  await expect(scene.drawer.getByRole('button', { name: '重新读取当前事实' })).toBeVisible();
});

test('preserves read-only controls and fits narrow screens without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const scene = await sourceScenario(page, { canSave: false });
  await expect(scene.drawer.getByRole('button', { name: '保存分配' })).toBeDisabled();
  await expect(scene.unit.getByRole('button', { name: '新增来源', exact: true })).toBeDisabled();
  expect(await scene.drawer.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: '/tmp/cost-source-app-390.png', fullPage: false, animations: "disabled" });
  expect(scene.writes()).toBe(0);
  const box = await scene.drawer.boundingBox();
  expect(box!.x).toBeCloseTo(0, 0); expect(box!.width).toBeCloseTo(390, 0);
});
