import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

for (const route of ['oa-pending-payments', 'output-invoice-collections', 'pending-invoices']) {
  test(`${route} query controls align and remain usable at desktop and narrow widths`, async ({ page }, info) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`/${route}`);
    await expect(page.locator('.finance-table__scroll').first()).toBeVisible();
    if (route === 'oa-pending-payments') {
      await expect(page.getByRole('group', { name: '已完成 OA', exact: true }).getByRole('button', { name: /^已关联流水/ })).toBeVisible();
      await expect(page.getByRole('group', { name: '已完成 OA', exact: true }).getByRole('button', { name: /^未关联流水/ })).toBeVisible();
      await expect(page.getByTestId('oa-pending-payments-table-frame').getByRole('search')).toHaveCount(0);
    }
    if (route === 'pending-invoices') await expect(page.getByText(/^当前范围 .*笔流水/)).toHaveCount(0);
    for (const width of [1800, 1280, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      if (route === 'oa-pending-payments') {
        // Stress count-label width without changing query or business state.
        await page.getByRole('region', { name: 'OA 核对分类' }).locator('.stable-count').evaluateAll(labels => labels.forEach(label => {
          label.textContent = label.textContent!.replace(/\d+ 条/, '99999 条');
        }));
      }
      const toolbar = page.locator(route === 'pending-invoices' ? '.pending-invoices-toolbar' : `.${route}-query`);
      const toolbarBox = await toolbar.boundingBox();
      expect(toolbarBox!.x).toBeGreaterThanOrEqual(0);
      expect(toolbarBox!.x + toolbarBox!.width).toBeLessThanOrEqual(width);
      expect(await toolbar.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      const search = toolbar.getByRole('search');
      await expect(search.getByRole('button', { name: '查询' })).toBeInViewport();
      const searchBox = await search.boundingBox();
      expect(searchBox!.x + searchBox!.width).toBeLessThanOrEqual(width);
      expect(searchBox!.x).toBeGreaterThanOrEqual(0);
      if (route !== 'pending-invoices') {
        const boxes = await toolbar.locator('.business-period-picker, .query-search__field, .query-search > button').evaluateAll(elements => elements.map(el => {
          const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, height: r.height, right: r.right };
        }));
        for (const box of boxes) expect(Math.abs(box.height - 46)).toBeLessThanOrEqual(1);
        expect(Math.abs(boxes[1].y - boxes[2].y)).toBeLessThanOrEqual(1);
        if (width === 1800) {
          expect(Math.abs(boxes[0].y - boxes[1].y)).toBeLessThanOrEqual(1);
          expect(boxes[0].right).toBeLessThanOrEqual(boxes[1].x);
          const header = page.locator('.table-classification');
          const headerBox = await header.boundingBox();
          expect(headerBox!.y + headerBox!.height).toBeLessThanOrEqual(boxes[0].y);
        }
      }
      await page.screenshot({ path: info.outputPath(`${route}-${width}.png`), animations: 'disabled' });
    }
  });
}

test('OA toolbar preserves payment and month filters when searching and clearing', async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.goto('/oa-pending-payments');
  await expect(page.locator('.finance-table__scroll')).toBeVisible();
  const nextRows = () => page.waitForResponse(r => new URL(r.url()).pathname === '/api/oa-pending-payments/rows');
  let response = nextRows();
  await page.getByRole('group', { name: '已完成 OA', exact: true }).getByRole('button', { name: /^已关联流水/ }).click();
  await (await response).finished();
  await page.getByRole('button', { name: 'OA月份筛选：年月' }).click();
  response = nextRows();
  await page.getByRole('dialog', { name: 'OA月份筛选选择器' }).getByRole('button', { name: '四月', exact: true }).click();
  const monthUrl = new URL((await response).url());
  const month = monthUrl.searchParams.get('month');
  const search = page.getByRole('search');
  const before = api.count('GET /api/oa-pending-payments/rows');
  await search.getByRole('searchbox').fill('付款申请人');
  expect(api.count('GET /api/oa-pending-payments/rows')).toBe(before);
  response = nextRows();
  await search.getByRole('searchbox').press('Enter');
  let url = new URL((await response).url());
  expect(url.searchParams.get('keyword')).toBe('付款申请人');
  expect(url.searchParams.get('month')).toBe(month);
  expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual([{ field: 'payment_status', operator: 'in', values: ['paid'] }]);
  expect(url.searchParams.get('page')).toBe('1');
  response = nextRows();
  await search.getByRole('button', { name: '清除查询' }).click();
  url = new URL((await response).url());
  expect(url.searchParams.has('keyword')).toBe(false);
  expect(url.searchParams.get('month')).toBe(month);
  expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))[0].values).toEqual(['paid']);
  expect(api.count('GET /api/oa-pending-payments/rows') - before).toBe(2);
});

for (const [route, scope, peers, endpoint] of [
  ['cost-statistics', '.cost-section-heading-actions', '.query-search__field, .query-search > button', '/api/cost-statistics/explorer'],
  ['bank-details', '.bank-header-controls', '.bank-auto-rules-button', '/api/bank-details/transactions'],
  ['bank-flow-rule-batches', '.bank-flow-rule-batches-filter', '.app-segments', '/api/bank-flow-rule-batches'],
]) {
  test(`${route} period picker matches its toolbar without changing filter requests`, async ({ page }, info) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`/${route}`);
    const toolbar = page.locator(scope).first();
    const picker = toolbar.locator('.business-period-picker');
    await expect(picker).toBeVisible();
    for (const width of [1800, 1280, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      const controls = await toolbar.locator(`.business-period-picker, ${peers}`).evaluateAll(nodes => nodes.map(node => {
        const r = node.getBoundingClientRect(); return { height: r.height, y: r.y, right: r.right, x: r.x };
      }));
      expect(controls.length).toBeGreaterThan(1);
      for (const r of controls) {
        expect(Math.abs(r.height - 46)).toBeLessThanOrEqual(1);
        expect(r.x).toBeGreaterThanOrEqual(0);
        expect(r.right).toBeLessThanOrEqual(width + 1);
      }
      if (width === 1800) expect(Math.max(...controls.map(r => r.y)) - Math.min(...controls.map(r => r.y))).toBeLessThanOrEqual(1);
      await page.screenshot({ path: info.outputPath(`${route}-${width}.png`), animations: 'disabled' });
    }
    await page.setViewportSize({ width: 1800, height: 1000 });
    const requests: string[] = [];
    page.on('request', request => { if (new URL(request.url()).pathname === endpoint) requests.push(request.url()); });
    await picker.locator('.business-period-trigger').click();
    await expect(page.getByRole('dialog').last()).toBeVisible();
    expect(requests).toHaveLength(0);
    if (route !== 'bank-flow-rule-batches') await page.getByRole('dialog').last().getByRole('radio', { name: '按月', exact: true }).click();
    expect(requests).toHaveLength(0);
    const response = page.waitForResponse(r => new URL(r.url()).pathname === endpoint);
    await page.getByRole('dialog').last().getByRole('button', { name: '四月', exact: true }).click();
    expect((await response).ok()).toBe(true);
    await expect(picker.locator('.business-period-trigger')).toContainText('4月');
    const reset = page.waitForResponse(r => new URL(r.url()).pathname === endpoint);
    await picker.getByRole('button', { name: '全部', exact: true }).click();
    expect((await reset).ok()).toBe(true);
    await expect(picker.getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true');
    if (route === 'bank-details') {
      await toolbar.getByRole('button', { name: '自动标签规则' }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
    }
  });
}

test('redundant copy is absent while payment rules remain editable', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.goto('/input-invoice-usage');
  await page.getByRole('button', { name: '发票与支付状态规则设置' }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText(/按优先级从小到大匹配/)).toHaveCount(0);
  await expect(drawer.getByRole('button', { name: '新增规则' })).toBeVisible();
  const before = await drawer.getByRole('listitem').count();
  await drawer.getByRole('button', { name: '新增规则' }).click();
  await expect(drawer.getByRole('listitem')).toHaveCount(before + 1);
});
