import { expect, test, type Page } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from './fixtures/apiMocks';

async function sourceScenario(page: Page, options: { alignmentCase?: boolean; many?: boolean; longMenu?: boolean; screenshotCase?: boolean; prefill?: boolean; missingTag?: boolean; conflict?: boolean; canSave?: boolean; interrupted?: boolean; detailFailure?: boolean; large?: boolean; performance?: boolean; refreshFailure?: boolean } = {}) {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const task = {
    relation_case_id: 'source-case', relation_version: 1, source_fingerprint: 'a'.repeat(64),
    status: 'pending', pending_reasons: options.missingTag ? ['bank_tag_missing'] : ['source_required'], amounts_fixed: true,
    oa_total: '600.00', gross_outflow_total: '600.00', wrong_payment_refund_total: '0.00', net_outflow_total: '600.00',
    units: [{ unit_id: 'oa-1', oa_id: 'OA-202608-001', oa_apply_type: '支付申请', expense_item_id: '', project_id: 'p-1', project_name: '云南溯源科技', expense_type: '原 OA 材料费用', expense_content: '设备安装项目材料采购', oa_applicant: '测试申请人', oa_original_amount: '600.00' }],
    bank_events: [
      { transaction_id: 'bank-a', event_kind: 'outflow', amount: '350.00', trade_time: '2026-08-15T00:00:00Z', counterparty_name: '设备供应商', bank_account_label: '建设银行 8106', bank_tag_code: options.missingTag ? '' : 'material', bank_tag_primary_label: options.missingTag ? '' : '采购', bank_tag_sub_label: options.missingTag ? '' : '材料款', tags: options.missingTag ? [] : ['采购', '材料款'] },
      { transaction_id: 'bank-b', event_kind: 'outflow', amount: '250.00', trade_time: '2026-09-03', counterparty_name: '设备供应商', bank_account_label: '民生银行 9486', bank_tag_code: 'material', bank_tag_primary_label: '采购', bank_tag_sub_label: '材料款', tags: ['采购', '材料款'] },
    ],
    allocations: [{ unit_id: 'oa-1', amount: '600.00' }], suggested_source_allocations: null as unknown, source_allocations: null as unknown,
    non_cost_amount: '0.00', non_cost_reason: '', version: 0, updated_by: '', updated_at: '', can_save: options.canSave !== false,
  };
  if (options.large) {
    task.oa_total = task.net_outflow_total = task.gross_outflow_total = '1000.00';
    task.units = Array.from({ length: 100 }, (_, i) => ({ ...task.units[0], unit_id: `unit-${i}`, oa_id: `doc-${Math.floor(i / 2)}`, expense_content: `成本项目 ${i + 1}`, oa_original_amount: '10.00' }));
    task.bank_events = Array.from({ length: 10 }, (_, i) => ({ ...task.bank_events[0], transaction_id: `source-${i}`, bank_account_label: `测试银行 ${i + 1}`, amount: '100.00' }));
    task.allocations = task.units.map(unit => ({ unit_id: unit.unit_id, amount: '10.00' }));
    task.source_allocations = { cost_lines: task.units.map((unit, i) => ({ unit_id: unit.unit_id, bank_transaction_id: task.bank_events[i % 10].transaction_id, amount: '10.00' })), refund_links: [], non_cost_lines: [] };
  }
  if (options.performance && !options.large) {
    task.units = task.bank_events.map((bank, i) => ({ ...task.units[0], unit_id: `unit-${i}`, oa_original_amount: bank.amount }));
    task.allocations = task.units.map(unit => ({ unit_id: unit.unit_id, amount: unit.oa_original_amount }));
    task.source_allocations = { cost_lines: task.units.map((unit, i) => ({ unit_id: unit.unit_id, bank_transaction_id: task.bank_events[i].transaction_id, amount: unit.oa_original_amount })), refund_links: [], non_cost_lines: [] };
  }
  if (options.prefill) task.suggested_source_allocations = {
    cost_lines: task.bank_events.map(bank => ({unit_id: task.units[0].unit_id, bank_transaction_id: bank.transaction_id, amount: bank.amount})),
    refund_links: [], non_cost_lines: [],
  };
  if (options.screenshotCase) {
    task.oa_total = task.net_outflow_total = task.gross_outflow_total = '587000.00';
    task.units = ['88050.00', '29350.00', '469600.00'].map((amount, i) => ({ ...task.units[0],
      unit_id: `oa-${i + 1}`, oa_id: `oa-pay-${i + 1}`, project_name: '大理卷烟厂余热综合利用项目',
      oa_original_amount: amount, expense_content: ['设备预付款', '设备定金', '设备尾款'][i] }));
    task.bank_events = [
      ['bank-a', '64996.69', '交通银行 3847', '2026-04-23'],
      ['bank-b', '23053.31', '光大银行 8826', '2026-04-23'],
      ['bank-c', '29350.00', '建设银行 8106', '2026-03-27'],
      ['bank-d', '469600.00', '交通银行 3847', '2026-05-13'],
    ].map(([transaction_id, amount, bank_account_label, trade_time]) => ({ ...task.bank_events[0], transaction_id,
      amount, bank_account_label, trade_time, bank_tag_primary_label: '货款', bank_tag_sub_label: '设备采购', tags: ['货款', '设备采购'] }));
    task.allocations = task.units.map(unit => ({ unit_id: unit.unit_id, amount: unit.oa_original_amount }));
    task.suggested_source_allocations = { cost_lines: task.bank_events.map((bank, i) => ({
      unit_id: task.units[Math.max(0, i - 1)].unit_id, bank_transaction_id: bank.transaction_id, amount: bank.amount,
    })), refund_links: [], non_cost_lines: [] };
  }
  if (options.alignmentCase) {
    const amounts = ['210042.00','95000.00','14848.00','50376.00','117546.00','13735.00','5536.00'];
    task.oa_total = task.net_outflow_total = task.gross_outflow_total = '507083.00';
    task.units = amounts.map((amount, i) => ({...task.units[0], unit_id:`unit-${i}`, oa_id:`oa-${i}`, oa_original_amount:amount, expense_content:`采购成本 ${i + 1}`}));
    const order = [4,5,6,1,0,2,3];
    task.bank_events = order.map((unit, i) => ({...task.bank_events[0], transaction_id:`bank-${i}`, amount:amounts[unit], bank_account_label:`${i >= 3 && i <= 5 ? '建设银行 8106' : '交通银行 3847'}`}));
    task.allocations = task.units.map(unit => ({unit_id:unit.unit_id,amount:unit.oa_original_amount}));
    task.suggested_source_allocations = {cost_lines:order.map((unit,i)=>({unit_id:task.units[unit].unit_id,bank_transaction_id:`bank-${i}`,amount:amounts[unit]})),refund_links:[],non_cost_lines:[]};
  }
  if (options.many) {
    task.units = [0,1].map(i=>({...task.units[0],unit_id:`unit-${i}`,oa_original_amount:'300.00'}));
    task.allocations = task.units.map(unit=>({unit_id:unit.unit_id,amount:'300.00'}));
    task.suggested_source_allocations = {cost_lines:task.units.flatMap(unit=>task.bank_events.map(bank=>({unit_id:unit.unit_id,bank_transaction_id:bank.transaction_id,amount:bank.transaction_id==='bank-a'?'175.00':'125.00'}))),refund_links:[],non_cost_lines:[]};
  }
  if (options.longMenu) task.bank_events.forEach(bank => {
    bank.counterparty_name = '云南设备采购安装与节能改造工程服务有限公司'.repeat(3);
    bank.bank_account_label = `云南省大理白族自治州项目结算专用${bank.bank_account_label}`;
    bank.bank_tag_sub_label = '设备采购安装与运输综合费用';
  });
  let writes = 0; let details = 0; let savedBody: Record<string, any> | null = null;
  await page.route('**/api/cost-statistics/manual-allocations**', async route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'PUT') {
      writes++; savedBody = route.request().postDataJSON();
      if (options.conflict) return route.fulfill({ status: 409, json: { error: 'cost_statistics_manual_allocation_conflict', message: '数据已变化，请重新核对；修改已保留' } });
      task.source_allocations = savedBody!.source_allocations;
      task.suggested_source_allocations = null;
      task.allocations = savedBody!.allocations;
      task.version++; task.status = options.missingTag ? 'pending' : 'allocated';
      task.pending_reasons = options.missingTag ? ['bank_tag_missing'] : [];
      if (options.interrupted) return route.fulfill({ status: 502, json: { message: 'upstream response lost after commit' } });
      return route.fulfill({ json: task });
    }
    if (url.pathname.endsWith('/source-case')) { details++; if (options.detailFailure && details === 1) return route.fulfill({ status: 503, json: { message: 'unavailable' } }); return route.fulfill({ json: task }); }
    const { units, bank_events, allocations, source_allocations, suggested_source_allocations, ...summary } = task;
    return route.fulfill({ json: {
      items: url.searchParams.get('status') === task.status ? [{ ...summary, project_names: [...new Set(task.units.map(unit => unit.project_name))], unit_count: task.units.length, bank_event_count: task.bank_events.length }, ...(options.prefill ? [2,3,4].map(i => ({...summary, relation_case_id: `color-block-${i}`, project_names: [`配色验证项目 ${i}`], unit_count: 1, bank_event_count: 2})) : [])] : [],
      row_count: options.prefill ? 4 : 1, counts: { pending: task.status === 'pending' ? (options.prefill ? 4 : 1) : 0, allocated: task.status === 'allocated' ? (options.prefill ? 4 : 1) : 0 }, next_cursor: null,
    } });
  });
  if (options.refreshFailure) await page.route('**/api/cost-statistics/explorer**', route => writes > 0 ? route.fulfill({ status: 503, json: { error: 'temporarily_unavailable', message: '统计刷新暂不可用' } }) : route.fallback());
  await page.goto('/cost-statistics');
  await expect(page.getByRole('heading', { name: '成本统计' })).toBeVisible();
  expect(details).toBe(0);
  await page.evaluate(() => {
    const observer = new MutationObserver(() => {
      if (document.querySelector('.cost-source-table')) { performance.mark('cost-source-first-table'); observer.disconnect(); }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
  await page.getByRole('button', { name: '打开成本人工分配' }).click();
  const drawer = page.getByRole('dialog', { name: '成本人工分配' });
  if (!options.detailFailure) await expect(drawer.getByRole('heading', { name: /银行流水/ })).toBeVisible();
  const unit = drawer.locator('.cost-source-table tbody').first();
  return { drawer, unit, task, writes: () => writes, body: () => savedBody, details: () => details };
}

async function fillSources(page: Page, unit: ReturnType<Page['locator']>) {
  for (const [index, amount] of ['350', '250'].entries()) {
    await unit.getByRole('button', { name: '新增来源', exact: true }).click();
    const source = unit.getByRole('combobox', { name: `来源流水 ${index + 1}`, exact: true });
    await expect(source).toBeFocused();
    await source.click();
    await page.getByRole('option', { name: index === 0 ? /建设银行 8106/ : /民生银行 9486/ }).click();
    await unit.getByRole('textbox', { name: `分配金额 ${index + 1}`, exact: true }).fill(amount);
  }
}

test('splits 600 across real bank accounts, moves only completed tasks, and preserves the source matrix', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const scene = await sourceScenario(page);
  await fillSources(page, scene.unit);
  await expect(scene.drawer.getByText(/剩余|已分 |bank-a|bank-b|source-case|OA-202608-001/)).toHaveCount(0);
  expect(scene.details()).toBe(1);
  expect(scene.writes()).toBe(0);
  const evidence = scene.drawer.locator('.cost-source-evidence');
  const left = await evidence.locator('tbody').first().locator('td').first().boundingBox();
  const right = await evidence.locator('tbody').first().locator('td.cost-evidence-bank').first().boundingBox();
  expect(right!.x).toBeGreaterThan(left!.x);
  expect(right!.y).toBeCloseTo(left!.y, 0);
  await expect(scene.drawer.locator('.cost-source-evidence').getByText('2026-08-15 08:00:00', { exact: true })).toBeVisible();
  await expect(scene.drawer.locator('.cost-source-evidence').getByText('2026-09-03', { exact: true })).toBeVisible();
  await page.screenshot({ path: '/tmp/cost-drawer-app-1440.png', fullPage: false, animations: "disabled" });
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('暂无待分配任务')).toBeVisible();
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
  await expect(scene.drawer.getByText('已保存，银行信息待完善')).toBeVisible();
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
  await page.keyboard.press('Escape');
  await fillSources(page, scene.unit);
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('数据已变化，请重新核对；修改已保留')).toBeVisible();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 2', exact: true })).toHaveValue('250.00');
  await expect(scene.drawer.getByRole('button', { name: '重新加载' })).toBeVisible();
});

test('preserves read-only controls and fits narrow screens without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const scene = await sourceScenario(page, { canSave: false });
  await expect(scene.drawer.getByRole('button', { name: '保存分配' })).toBeDisabled();
  await expect(scene.unit.getByRole('button', { name: '新增来源', exact: true })).toBeDisabled();
  expect(await scene.drawer.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: '/tmp/cost-drawer-app-390.png', fullPage: false, animations: "disabled" });
  expect(scene.writes()).toBe(0);
  const box = await scene.drawer.boundingBox();
  expect(box!.x).toBeCloseTo(0, 0); expect(box!.width).toBeCloseTo(390, 0);
});


test('reads a failed detail again without showing an empty task as fact', async ({ page }) => {
  const scene = await sourceScenario(page, { detailFailure: true });
  await expect(scene.drawer.getByText('任务读取失败，请重试')).toBeVisible();
  await expect(scene.drawer.locator('.cost-source-table')).toHaveCount(0);
  await scene.drawer.getByRole('button', { name: '重新加载' }).click();
  await expect(scene.drawer.getByRole('heading', { name: /银行流水/ })).toBeVisible();
  expect(scene.details()).toBe(2);
  expect(scene.writes()).toBe(0);
});

test('reconciles a committed write with a lost response using GET and never submits twice', async ({ page }) => {
  const scene = await sourceScenario(page, { interrupted: true });
  await fillSources(page, scene.unit);
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await expect(scene.drawer.getByText('保存结果待核实，修改已保留')).toBeVisible();
  await expect(scene.drawer.getByRole('button', { name: '保存分配' })).toBeDisabled();
  await scene.drawer.getByRole('button', { name: '核实保存结果' }).click();
  await expect(scene.drawer.getByText('暂无待分配任务')).toBeVisible();
  expect(scene.writes()).toBe(1);
  expect(scene.details()).toBe(2);
});

test('keeps the current full source selectable and restores focus after row deletion', async ({ page }) => {
  const scene = await sourceScenario(page);
  await fillSources(page, scene.unit);
  const selected = scene.unit.getByRole('combobox', { name: '来源流水 1', exact: true });
  await selected.click();
  await expect(page.getByRole('option', { name: /建设银行 8106/ })).toBeEnabled();
  await expect(page.getByRole('option', { name: /民生银行 9486/ })).toBeDisabled();
  await page.keyboard.press('Escape');
  await scene.unit.getByRole('button', { name: '删除来源行 1', exact: true }).click();
  await expect(scene.unit.getByRole('combobox', { name: '来源流水 1', exact: true })).toBeFocused();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 1', exact: true })).toHaveValue('250.00');
  await scene.unit.getByRole('button', { name: '删除来源行 1', exact: true }).click();
  await expect(scene.unit.getByRole('button', { name: '新增来源', exact: true })).toBeFocused();
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  expect(scene.writes()).toBe(0);
});


for (const large of [false, true]) {
  test(`measures local editing with ${large ? '100' : '2'} valid source rows without extra requests`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const scene = await sourceScenario(page, { large, performance: true });
    const table = scene.drawer.getByRole('table', { name: '成本分配明细', exact: true });
    await expect(table.getByRole('combobox')).toHaveCount(large ? 100 : 2);
    const measurements = await table.evaluate(async element => {
      const input = element.querySelector('input')!;

      const durations: number[] = [];
      for (let i = 0; i < 20; i++) {
        const start = performance.now();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, i % 2 ? '10.00' : '10.01');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        durations.push(performance.now() - start);
      }
      const addDelete: number[] = [];
      const unit = element.querySelector('tbody')!;
      for (let i = 0; i < 20; i++) {
        const start = performance.now();
        if (i % 2 === 0) unit.querySelector<HTMLButtonElement>('.cost-source-add')!.click();
        else [...unit.querySelectorAll<HTMLButtonElement>('.cost-source-icon')].at(-1)!.click();
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        addDelete.push(performance.now() - start);
      }
      const resource = performance.getEntriesByType('resource').find(entry => entry.name.endsWith('/manual-allocations/source-case')) as PerformanceResourceTiming | undefined;
      const painted = performance.getEntriesByName('cost-source-first-table')[0];
      const dataToTableMs = resource && painted ? Number((painted.startTime - resource.responseEnd).toFixed(2)) : null;
      const p95 = (values: number[]) => Number([...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1].toFixed(2));
      return { inputSamples: durations.length, inputP50Ms: [...durations].sort((a,b) => a-b)[9], inputP95Ms: p95(durations), inputMaxMs: Math.max(...durations), addDeleteSamples: addDelete.length, addDeleteP50Ms: [...addDelete].sort((a,b) => a-b)[9], addDeleteP95Ms: p95(addDelete), addDeleteMaxMs: Math.max(...addDelete), dataToTableMs };
    });
    // Editing the second row frees a real alternative source; measure actual changes, not same-value events.
    await table.getByRole('textbox').nth(1).fill('0');
    const opening: number[] = []; const selection: number[] = [];
    for (let i = 0; i < 20; i++) {
      const trigger = table.getByRole('combobox').first();
      const recordNextClick = () => page.evaluate(() => {
        (window as any).__costInteraction = null;
        document.addEventListener('pointerdown', () => {
          const start = performance.now();
          requestAnimationFrame(() => requestAnimationFrame(() => { (window as any).__costInteraction = performance.now() - start; }));
        }, { once: true, capture: true });
      });
      const readDuration = async () => { await expect.poll(() => page.evaluate(() => (window as any).__costInteraction)).not.toBeNull(); return page.evaluate(() => (window as any).__costInteraction as number); };
      await recordNextClick(); await trigger.click(); opening.push(await readDuration());
      await recordNextClick(); await page.getByRole('listbox', { name: '来源流水 1', exact: true }).getByRole('option').nth(i % 2 === 0 ? 1 : 0).click(); selection.push(await readDuration());
    }
    const distribution = (values: number[]) => { const sorted = [...values].sort((a,b) => a-b); return { samples: values.length, p50: sorted[Math.ceil(values.length * .5)-1], p95: sorted[Math.ceil(values.length * .95)-1], max: sorted.at(-1) }; };
    console.log(JSON.stringify({ costDrawerPerformance: { rows: large ? 100 : 2, ...measurements, dropdownOpen: distribution(opening), sourceChange: distribution(selection) } }));
    expect(scene.details()).toBe(1);
    expect(scene.writes()).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
}

test('keeps a successful allocation committed when the statistics refresh fails', async ({ page }) => {
  const scene = await sourceScenario(page, { refreshFailure: true });
  await fillSources(page, scene.unit);
  const failedRead = page.waitForResponse(response => response.url().includes('/cost-statistics/explorer') && response.status() === 503);
  await scene.drawer.getByRole('button', { name: '保存分配' }).click();
  await failedRead;
  await expect(scene.drawer.getByText('暂无待分配任务')).toBeVisible();
  await scene.drawer.getByRole('radio', { name: '已完成 1' }).click();
  await expect(scene.unit.getByRole('textbox', { name: '分配金额 1', exact: true })).toHaveValue('350.00');
  expect(scene.writes()).toBe(1);
});


test('keeps invalid amount feedback within its cell and leaves source geometry stable', async ({ page }) => {
  const scene = await sourceScenario(page);
  await scene.unit.getByRole('button', { name: '新增来源', exact: true }).click();
  const source = scene.unit.getByRole('combobox'); const amount = scene.unit.getByRole('textbox');
  await source.press('ArrowDown');
  await page.getByRole('option', { name: /建设银行 8106/ }).click();
  const before = await source.boundingBox();
  await amount.fill('1.234'); await amount.press('Tab');
  await expect(amount).toHaveAttribute('aria-invalid', 'true');
  await expect(source).toHaveAttribute('aria-invalid', 'false');
  const after = await source.boundingBox();
  expect(after!.y).toBe(before!.y); expect(after!.height).toBe(before!.height);
  await expect(scene.unit.locator('td').nth(2).locator('p')).toHaveCount(0);
  await scene.unit.getByRole('button', { name: '金额须大于 0，最多两位小数' }).click();
  await expect(page.getByRole('dialog', { name: '分配校验' })).toBeVisible();
  await page.screenshot({ path: '/tmp/cost-grid-amount-error.png', animations: 'disabled' });
  await page.keyboard.press('Escape');
  await expect(scene.drawer).toBeVisible();
  expect(scene.writes()).toBe(0);
});


test('prefill is editable, merged, pending until save, with four distinct block colors', async ({page}) => {
  await page.setViewportSize({width: 1600, height: 1100});
  const scene = await sourceScenario(page, {prefill: true});
  await expect(scene.unit.getByRole('combobox')).toHaveCount(2);
  await expect(scene.unit.locator('td[rowspan="2"]')).toHaveCount(2);
  expect(scene.writes()).toBe(0);
  expect(scene.task.status).toBe('pending');
  const colors = await scene.drawer.locator('.cost-source-task').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).backgroundColor));
  expect(colors).toEqual(['rgb(197, 212, 184)', 'rgb(232, 197, 165)', 'rgb(221, 185, 195)', 'rgb(185, 204, 223)']);
  await scene.drawer.evaluate(async element => { await Promise.all(element.getAnimations({subtree: true}).filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity).map(animation => animation.finished)); });
  await page.screenshot({path: '/tmp/cost-prefill-four-colors.png', fullPage: false, animations: 'disabled'});
  await scene.drawer.getByRole('button', {name: '保存分配', exact: true}).click();
  await expect.poll(scene.writes).toBe(1);
  expect(scene.body()!.source_allocations.cost_lines).toHaveLength(2);
});

test('clearing prefill and collapsing the block does not recreate deleted input', async ({page}) => {
  const scene = await sourceScenario(page, {prefill: true});
  await scene.unit.getByRole('button', {name: '删除来源行 1', exact: true}).click();
  await scene.unit.getByRole('button', {name: '删除来源行 1', exact: true}).click();
  const heading = scene.drawer.locator('.cost-source-task-heading').first();
  await heading.click(); await heading.click();
  await expect(scene.unit.getByRole('combobox')).toHaveCount(0);
  await expect(scene.unit.getByText('未分配')).toBeVisible();
  expect(scene.writes()).toBe(0);
});


test('COST-E2E-014 screenshot three OA four bank suggestions save as four source rows', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1100 });
  const scene = await sourceScenario(page, { screenshotCase: true });
  const table = scene.drawer.locator('.cost-source-table');
  await expect(table.getByRole('combobox')).toHaveCount(4);
  await expect(table.locator('td[rowspan="2"]')).toHaveCount(2);
  for (const amount of ['64996.69', '23053.31', '29350.00', '469600.00']) {
    await expect(table.locator(`input[value="${amount}"]`)).toBeVisible();
  }
  expect(scene.writes()).toBe(0);
  expect(scene.task.status).toBe('pending');
  await page.screenshot({ path: '/tmp/cost-prefill-repair-screenshot-case.png', fullPage: false, animations: 'disabled' });
  await scene.drawer.getByRole('button', { name: '保存分配', exact: true }).click();
  await expect.poll(scene.writes).toBe(1);
  expect(scene.body()!.allocations.map((line: {amount: string}) => line.amount)).toEqual(['88050.00', '29350.00', '469600.00']);
  expect(scene.body()!.source_allocations.cost_lines.map((line: {amount: string}) => line.amount)).toEqual(['64996.69', '23053.31', '29350.00', '469600.00']);
  await scene.drawer.getByRole('radio', { name: /已完成/ }).click();
  await expect(scene.drawer.locator('.cost-source-table').getByRole('combobox')).toHaveCount(4);
  await expectNoUnexpectedSuccessUiErrors(page);
});

for (const width of [1440, 390]) {
  test(`source menu contains multiline options without shrinking at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const scene = await sourceScenario(page, { screenshotCase: true, longMenu: true });
    await scene.unit.getByRole('combobox').first().click();
    const menu = page.getByRole('listbox', { name: '来源流水 1', exact: true });
    await expect(menu.getByRole('option')).toHaveCount(4);
    await expect(menu.getByText('已用完')).toHaveCount(0);
    await expect(menu.getByText('本项已使用')).toHaveCount(0);
    const geometry = await menu.evaluate(element => {
      const options = [...element.querySelectorAll<HTMLElement>('[role="option"]')];
      return {
        scrolls: element.scrollHeight > element.clientHeight,
        fits: element.scrollWidth <= element.clientWidth + 1,
        rows: options.map(option => {
          const box = option.getBoundingClientRect();
          const children = [...option.children].map(child => child.getBoundingClientRect());
          const heading = option.firstElementChild!;
          const name = heading.firstElementChild!.getBoundingClientRect();
          const money = heading.lastElementChild!.getBoundingClientRect();
          return { top: box.top, bottom: box.bottom,
            contains: children.every(child => child.top >= box.top && child.bottom <= box.bottom + 1 && child.left >= box.left && child.right <= box.right + 1),
            moneyFits: money.left >= name.right && money.right <= box.right,
          };
        }),
      };
    });
    expect(geometry.scrolls).toBe(true);
    expect(geometry.fits).toBe(true);
    for (const [index, row] of geometry.rows.entries()) {
      expect(row.contains).toBe(true);
      expect(row.moneyFits).toBe(true);
      if (index) expect(row.top).toBeGreaterThanOrEqual(geometry.rows[index - 1].bottom);
    }
    await menu.getByRole('option').last().scrollIntoViewIfNeeded();
    await expect(menu.getByRole('option').last()).toBeInViewport();
    expect(scene.writes()).toBe(0);
    expect(scene.details()).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
}

test('aligns seven chosen sources and keeps the balance hint legible on every task color', async ({page}, testInfo) => {
  await page.setViewportSize({width:1440,height:1000});
  const scene = await sourceScenario(page, {alignmentCase:true});
  const evidence = scene.drawer.getByRole('table',{name:'OA 与流水对照'});
  const rows = evidence.locator('tbody tr');
  await expect(rows).toHaveCount(7);
  await expect(scene.drawer.getByText('按当前分配对齐，未保存的修改尚未生效')).toHaveCount(0);
  for (let i=0;i<7;i++) {
    const cells = rows.nth(i).locator('td');
    await expect(cells.nth(2)).toHaveText(await cells.nth(5).innerText());
    expect((await cells.nth(0).boundingBox())!.y).toBeCloseTo((await cells.nth(3).boundingBox())!.y,1);
  }
  await expect(rows.first().locator('td').nth(3)).toContainText('5. 建设银行 8106');
  const hint = scene.drawer.getByText('分配金额一致',{exact:true});
  const save = scene.drawer.getByRole('button',{name:'保存分配',exact:true});
  await expect(hint).toBeVisible();
  const ratios=[];
  for (const [index,color] of ['#c5d4b8','#e8c5a5','#ddb9c3','#b9ccdf'].entries()) {
    await scene.drawer.locator('.cost-source-task').first().evaluate((element,color)=>{(element as HTMLElement).style.backgroundColor=color;},color);
    const ratio=await hint.evaluate(element=>{
      const colors=[getComputedStyle(element).color,getComputedStyle(element.closest('.cost-source-task')!).backgroundColor];
      const lum=(value:string)=>{const [r,g,b]=value.match(/[\d.]+/g)!.slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return .2126*r+.7152*g+.0722*b;};
      const values=colors.map(lum).sort((a,b)=>b-a);return (values[0]+.05)/(values[1]+.05);
    });
    expect(ratio).toBeGreaterThanOrEqual(4.5);ratios.push(ratio);
    await scene.drawer.locator('footer').screenshot({path:testInfo.outputPath(`balance-color-${index}.png`),animations:'disabled'});
  }
  console.log(JSON.stringify({balanceContrastRatios:ratios}));
  const before=await save.boundingBox();
  const amount=scene.unit.getByRole('textbox').first();
  await amount.fill('210041'); await save.scrollIntoViewIfNeeded();
  await expect(hint).toHaveCount(0);
  const after=await save.boundingBox();expect(after!.height).toBe(before!.height);expect(after!.x).toBeCloseTo(before!.x,1);expect(after!.y).toBeCloseTo(before!.y,1);
  await amount.fill('210042');await expect(hint).toBeVisible();
  const task=scene.drawer.locator('.cost-source-task').first();
  await task.evaluate(element=>{(element as HTMLElement).style.zoom='1.5';});
  await save.evaluate(element=>element.scrollIntoView({block:'center'}));
  await expect(save).toBeInViewport();await expect(hint).toBeInViewport();
  expect(await hint.evaluate(element=>{const box=element.getBoundingClientRect();return element.contains(document.elementFromPoint(box.x+box.width/2,box.y+box.height/2));})).toBe(true);
  await page.screenshot({path:testInfo.outputPath('balance-150percent.png'),animations:'disabled'});
  await task.evaluate(element=>{(element as HTMLElement).style.zoom='1';});
  await scene.drawer.locator('.cost-source-evidence').screenshot({path:testInfo.outputPath('aligned-seven.png'),animations:'disabled'});
  await page.setViewportSize({width:390,height:844});
  expect(await scene.drawer.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  await save.scrollIntoViewIfNeeded();await expect(save).toBeInViewport();await expect(hint).toBeInViewport();
  expect(scene.writes()).toBe(0);expect(scene.details()).toBe(1);
  await expectNoUnexpectedSuccessUiErrors(page);
});

test('shows many-to-many evidence as one group without duplicating bank facts',async({page},testInfo)=>{
  const scene=await sourceScenario(page,{many:true});
  const evidence=scene.drawer.getByRole('table',{name:'OA 与流水对照'});
  await expect(evidence.locator('tbody')).toHaveCount(1);
  await expect(evidence.getByText('多对多 · 2 项 / 2 笔')).toBeVisible();
  await expect(evidence.getByText('¥350.00',{exact:true})).toHaveCount(1);
  await expect(evidence.getByText('¥250.00',{exact:true})).toHaveCount(1);
  await expect(scene.drawer.getByText('分配金额一致',{exact:true})).toBeVisible();
  await evidence.screenshot({path:testInfo.outputPath('many-to-many.png'),animations:'disabled'});
  await scene.drawer.getByRole('button',{name:'保存分配'}).click();
  expect(scene.writes()).toBe(1);
});
