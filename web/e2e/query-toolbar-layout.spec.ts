import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

const production = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
if (production) test.use({ trace: 'off', video: 'off', screenshot: 'off' });
for (const route of ['oa-pending-payments', 'output-invoice-collections', 'pending-invoices', 'input-invoice-usage']) {
  test(`${route} compact header preserves controls at desktop and narrow widths`, async ({ page }, info) => {
    if (production) {
      const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
      expect(token).toBeTruthy();
      await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
      await page.route('**/fin-ops-api/**', async route => {
        if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) await route.abort();
        else await route.continue();
      });
    } else await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`${production ? '/fin-ops' : ''}/${route}`);
    await expect(page.locator('.finance-table__scroll').first()).toBeVisible();
    const header = page.locator('.page-header');
    await expect(header.getByRole('button', { name: '刷新', exact: true })).toHaveCount(0);
    for (const width of [1920, 1440, 1280, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(header.getByRole('search')).toBeVisible();
      await expect.poll(() => header.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      const search = header.getByRole('search');
      await expect(search.getByRole('button', { name: '查询' })).toBeInViewport();
      const boxes = await header.locator('.business-period-picker, .query-search__field, .query-search > button').evaluateAll(elements => elements.map(el => {
        const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, height: r.height, right: r.right };
      }));
      expect(boxes).toHaveLength(3);
      for (const box of boxes) {
        expect(Math.abs(box.height - 32)).toBeLessThanOrEqual(1);
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.right).toBeLessThanOrEqual(width);
      }
      if (width >= 1440) {
        const title = (await header.locator('.page-title-row').boundingBox())!;
        expect(Math.abs(boxes[0].y - boxes[2].y)).toBeLessThanOrEqual(1);
        expect(boxes[0].x).toBeGreaterThanOrEqual(title.x + title.width);
      }
      await page.screenshot({ path: info.outputPath(`${route}-${width}.png`), animations: 'disabled' });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (route !== 'output-invoice-collections') {
      await header.getByRole('button', { name: '更多页面操作' }).click();
      const menu = page.getByRole('dialog', { name: '更多页面操作' });
      await expect(menu).toBeVisible();
      await menu.getByRole('button').first().click();
      await expect(menu).toHaveCount(0);
      const drawer = page.getByRole('dialog');
      await expect(drawer).toBeVisible();
      await drawer.getByRole('button', { name: /关闭/ }).first().click();
      await expect(drawer).toHaveCount(0);
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
  await page.getByRole('button', { name: '更多页面操作' }).click();
  await page.getByRole('button', { name: '发票与支付状态规则设置' }).click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByText(/按优先级从小到大匹配/)).toHaveCount(0);
  await expect(drawer.getByRole('button', { name: '新增规则' })).toBeVisible();
  const before = await drawer.getByRole('listitem').count();
  await drawer.getByRole('button', { name: '新增规则' }).click();
  await expect(drawer.getByRole('listitem')).toHaveCount(before + 1);
});

for (const name of ['pending-invoices', 'input-invoice-usage']) {
  test(`${name} month search and export use the same scope`, async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`/${name}`);
    const header = page.locator('.page-header');
    await expect(page.locator('.finance-table__scroll').first()).toBeVisible();
    await header.locator('.business-period-trigger').click();
    const response = page.waitForResponse(r => new URL(r.url()).pathname === `/api/${name}/rows`);
    await page.getByRole('dialog').getByRole('button', { name: '四月', exact: true }).click();
    const monthUrl = new URL((await response).url());
    const input = name === 'input-invoice-usage';
    const month = input ? monthUrl.searchParams.get('month')! : monthUrl.searchParams.get('date_from')!.slice(0, 7);
    expect(month).toMatch(/-04$/);
    if (!input) expect(monthUrl.searchParams.get('date_to')).toBe(`${month}-30`);
    const before = api.count(`GET /api/${name}/rows`);
    await header.getByRole('searchbox').fill('测试');
    expect(api.count(`GET /api/${name}/rows`)).toBe(before);
    const search = page.waitForResponse(r => new URL(r.url()).pathname === `/api/${name}/rows`);
    await header.getByRole('button', { name: '查询', exact: true }).click();
    const searchUrl = new URL((await search).url());
    expect(searchUrl.searchParams.get('keyword')).toBe('测试');
    expect(searchUrl.searchParams.get(input ? 'month' : 'date_from')).toBe(input ? month : `${month}-01`);
    await expect(header.locator('.business-period-trigger')).toContainText('4月');
    const preview = page.waitForResponse(r => new URL(r.url()).pathname === `/api/${name}/export-summary`);
    await header.getByRole('button', { name: '筛选内容导出' }).click();
    const url = new URL((await preview).url());
    expect(url.searchParams.get('keyword')).toBe('测试');
    expect(url.searchParams.get(input ? 'invoice_date_from' : 'date_from')).toBe(`${month}-01`);
    expect(url.searchParams.get(input ? 'invoice_date_to' : 'date_to')).toBe(`${month}-30`);
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByLabel('导出开始日期')).toHaveValue(`${month}-01`);
    await drawer.getByRole('button', { name: /关闭/ }).first().click();
    const clear = page.waitForResponse(r => new URL(r.url()).pathname === `/api/${name}/rows`);
    await header.getByRole('button', { name: '清除查询' }).click();
    expect(new URL((await clear).url()).searchParams.has('keyword')).toBe(false);
    const all = page.waitForResponse(r => new URL(r.url()).pathname === `/api/${name}/rows`);
    await header.locator('.business-period-picker').getByRole('button', { name: '全部', exact: true }).click();
    const allUrl = new URL((await all).url());
    expect(allUrl.searchParams.has(input ? 'month' : 'date_from')).toBe(false);
  });
}
