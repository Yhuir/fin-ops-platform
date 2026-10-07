import { expect, test, type Page, type Locator } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

// Run with a system browser too: headless defaults can hide classic scrollbar reflow.
if (process.env.FIN_OPS_LAYOUT_HEADED === '1') {
  test.use({ launchOptions: { channel: 'chrome', headless: false, args: ['--disable-features=OverlayScrollbar,OverlayScrollbars', '--window-position=-3000,0'] } });
}
test.use({ viewport: { width: 1440, height: 900 } });

async function geometry(page: Page, table: Locator) {
  return { shell: await page.locator('.app-shell-content').boundingBox(),
    header: await page.locator('.page-header,.workbench-page-header').first().boundingBox(),
    table: await table.boundingBox(),
    columns: await table.locator('thead th').evaluateAll(cells => cells.map(cell => {
      const { x, width } = cell.getBoundingClientRect(); return { x, width };
    })) };
}
function stable(before: Awaited<ReturnType<typeof geometry>>, after: Awaited<ReturnType<typeof geometry>>) {
  for (const part of ['shell', 'header', 'table'] as const) {
    expect(before[part]).not.toBeNull(); expect(after[part]).not.toBeNull();
    for (const dim of ['x', 'y', 'width'] as const) expect(Math.abs(after[part]![dim] - before[part]![dim]), `${part}.${dim}`).toBeLessThanOrEqual(1);
  }
  expect(after.columns).toHaveLength(before.columns.length);
  before.columns.forEach((column, i) => {
    expect(Math.abs(after.columns[i].x - column.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(after.columns[i].width - column.width)).toBeLessThanOrEqual(1);
  });
}
function latch() { let resolve!: () => void; const promise = new Promise<void>(r => { resolve = r; }); return { promise, resolve }; }

test('OA retains its frame, horizontal position and errors through delayed classification requests', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.goto('/oa-pending-payments');
  const frame = page.getByTestId('oa-pending-payments-table-frame');
  await expect(frame).toHaveAttribute('aria-busy', 'false');
  const table = page.getByRole('grid', { name: 'OA待付款核对表格' });
  const scroll = frame.locator('.finance-table__scroll');
  await scroll.evaluate(el => { el.scrollLeft = 100; el.setAttribute('data-original-scroll', 'true'); });
  const before = await geometry(page, table);
  const release = latch();
  let fail = false;
  await page.route('**/api/oa-pending-payments/rows?*', async route => {
    await release.promise;
    if (fail) await route.fulfill({ status: 503, json: { error: 'unavailable', message: '布局测试读取失败' } });
    else await route.fallback();
  });
  try {
    await page.getByRole('button', { name: /进行中 OA/ }).click();
    await expect(frame).toHaveAttribute('aria-busy', 'true');
    await expect(scroll).toHaveAttribute('data-original-scroll', 'true');
    stable(before, await geometry(page, table));
    expect(await scroll.evaluate(el => el.scrollLeft)).toBe(100);
  } finally { release.resolve(); }
  await expect(frame).toHaveAttribute('aria-busy', 'false');
  stable(before, await geometry(page, table));
  fail = true;
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('布局测试读取失败');
  stable(before, await geometry(page, table));
  fail = false;
  await page.getByRole('button', { name: '重试', exact: true }).click();
  await expect(frame).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByRole('alert')).toHaveCount(0);
  stable(before, await geometry(page, table));
  await page.getByRole('button', { name: '导出 OA', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  stable(before, await geometry(page, table));
  await page.getByRole('button', { name: '关闭导出 OA 抽屉' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  stable(before, await geometry(page, table));
});

test('turnover register column edges survive loading without depending on row content', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user', turnoverCostFanout: true });
  await page.goto('/turnover-ledger');
  const table = page.getByRole('table', { name: '外部往来款台账' });
  await expect(table).toHaveAttribute('aria-busy', 'false');
  const before = await geometry(page, table);
  const release = latch();
  await page.route('**/api/turnover-ledger?*', async route => { await release.promise; await route.fallback(); });
  try {
    await page.getByRole('searchbox').fill('核对');
    await page.getByRole('button', { name: '查询', exact: true }).click();
    await expect(table).toHaveAttribute('aria-busy', 'true');
    stable(before, await geometry(page, table));
  } finally { release.resolve(); }
  await expect(table).toHaveAttribute('aria-busy', 'false');
  stable(before, await geometry(page, table));
});

test('history retains table header, columns and viewport on empty and failed queries', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  await page.goto('/operations/history');
  const table = page.getByRole('grid', { name: '操作历史' });
  await expect(table.getByText('确认关联', { exact: true })).toBeVisible();
  const before = await geometry(page, table);
  let failed = false;
  await page.route('**/api/operations/history?*', route => route.fulfill(failed
    ? { status: 503, json: { error: 'unavailable', message: '历史读取失败' } }
    : { json: { rows: [], next_cursor: null, limit: 50 } }));
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await expect(table.getByText('暂无操作记录')).toBeVisible();
  stable(before, await geometry(page, table));
  failed = true;
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await expect(table.getByText('历史读取失败')).toBeVisible();
  stable(before, await geometry(page, table));
});

for (const route of ['pending-invoices', 'input-invoice-usage', 'output-invoice-collections']) {
  test(`${route} keeps the contained table reachable at wide and narrow sizes`, async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto('/' + route);
    const frame = page.locator('.finance-page-table-frame');
    await expect(frame).toBeVisible();
    for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 960, height: 600 }]) {
      await page.setViewportSize(size);
      await expect(frame).toBeVisible();
      const metrics = await frame.evaluate(el => ({ height: el.clientHeight, bottom: el.getBoundingClientRect().bottom, documentHeight: document.documentElement.scrollHeight, pageWidth: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
      expect(metrics.height).toBeGreaterThanOrEqual(239);
      if (size.height >= 900) {
        expect(metrics.documentHeight).toBeLessThanOrEqual(size.height + 1);
        expect(metrics.bottom).toBeLessThanOrEqual(size.height);
      }
      expect(metrics.pageWidth).toBeLessThanOrEqual(metrics.viewport + 1);
    }
  });
}

test('workbench failure and retry occupy a stable status region', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  let failed = true;
  await page.route(/\/api\/workbench(\?|$)/, route => failed
    ? route.fulfill({ status: 503, json: { error: 'unavailable', message: '关联台读取失败' } })
    : route.fallback());
  await page.goto('/');
  await expect(page.getByRole('button', { name: '重新读取', exact: true })).toBeVisible();
  const zone = page.locator('.workbench-zone-stack');
  const before = await zone.evaluate(el => { const { x, y, width } = el.getBoundingClientRect(); return { x, y, width }; });
  await expect(zone).toHaveAttribute('inert', '');
  failed = false;
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await expect(page.getByTestId('zone-paired')).toBeVisible();
  const after = await zone.evaluate(el => { const { x, y, width } = el.getBoundingClientRect(); return { x, y, width }; });
  expect(after).toEqual(before);
  await expect(zone).not.toHaveAttribute('inert');
});
