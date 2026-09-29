import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production bank actions and all invoice statuses remain usable without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(180_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: number[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => {
    if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(response.status());
  });
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto('/fin-ops/output-invoice-collections');
  const tabs = page.getByRole('tablist', { name: '销项发票状态分类' });
  await expect(tabs.getByRole('tab')).toHaveCount(7, { timeout: 25_000 });
  for (const width of [1920, 1440, 960, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await tabs.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    for (const tab of await tabs.getByRole('tab').all()) {
      await expect(tab).toBeInViewport({ ratio: 1 });
      await expect(tab).toHaveCSS('height', '34px');
      expect(await tab.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    }
    await expect(page.getByRole('search').getByRole('button', { name: '查询', exact: true })).toBeInViewport();
    await page.screenshot({ path: info.outputPath(`production-statuses-${width}.png`), animations: 'disabled' });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const tab of await tabs.getByRole('tab').all()) {
    if (await tab.getAttribute('aria-selected') === 'true') continue;
    const response = page.waitForResponse(r => new URL(r.url()).pathname === '/fin-ops-api/output-invoice-collections/rows');
    await tab.click();
    expect((await response).status()).toBe(200);
    await expect(tab).toHaveAttribute('aria-selected', 'true');
  }
  await page.goto('/fin-ops/');
  const bank = page.locator('.record-card-bank');
  await expect(bank.first()).toBeVisible({ timeout: 25_000 });
  await expect(bank.getByRole('button', { name: /更多/ })).toHaveCount(0);
  await expect(bank.getByText('关联情况', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('production-workbench.png'), animations: 'disabled' });
  await page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first().click();
  const drawer = page.locator('[role="dialog"].source-detail-drawer');
  await expect(drawer.getByRole('heading', { name: '银行流水详情', exact: true })).toBeVisible();
  await expect(drawer.locator('.entity-detail-table').first()).toBeVisible();
  await drawer.getByRole('button', { name: /关闭.*抽屉|关闭详情/ }).click();
  await expect(drawer).toBeHidden();
  expect(writes).toEqual([]);
  expect(failures).toEqual([]);
});
