import { expect, test, type Locator } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 900 } });

test('production shared source drawers preserve complete records across pages without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(300_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: number[] = [], metrics: object[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => { if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(response.status()); });
  const inspect = async (button: Locator, sample: string, multiple = false) => {
    await expect(button).toBeVisible({ timeout: 25_000 });
    const started = Date.now();
    const pending = page.waitForResponse(response => {
      const path = new URL(response.url()).pathname;
      return response.request().method() === 'GET' && path.includes('/fin-ops-api/') && (/\/[^/]*(?:detail|details)$/.test(path) || /\/workbench\/rows\/[^/]+$/.test(path));
    });
    await button.click();
    const response = await pending;
    expect(response.status()).toBe(200);
    const payload = await response.json();
    const sections = payload.row ? payload.row.source_sections : payload.sections;
    expect(Array.isArray(sections)).toBe(true);
    expect(sections.length).toBeGreaterThan(0);
    const drawer = page.locator('[role="dialog"].source-detail-drawer');
    await expect(drawer.locator('.entity-detail-table').first()).toBeVisible();
    const firstPaintMs = Date.now() - started;
    const ids = new Set(sections.map((section: { document_id: string }) => section.document_id));
    if (multiple) expect(ids.size).toBeGreaterThan(1);
    if (ids.size > 1) {
      const nav = drawer.getByRole('navigation', { name: '单据导航' });
      await expect(nav).toBeVisible();
      await nav.getByRole('button', { name: '展开全部', exact: true }).click();
      await expect(drawer.locator('.entity-detail-document__body:visible')).toHaveCount(ids.size);
      const titles = [...new Set<string>(sections.map((section: { document_title: string }) => section.document_title))];
      for (const title of titles) {
        const item = nav.getByRole('button', { name: title, exact: true });
        await expect(item).toHaveCount(1);
        expect(await item.evaluate(el => el.scrollWidth <= el.clientWidth && getComputedStyle(el).textOverflow !== 'ellipsis')).toBe(true);
      }
    }
    const actualLabels = await drawer.locator('.entity-detail-table th[scope="row"]').allTextContents();
    const expectedLabels: string[] = sections.flatMap((section: { fields: { label: string }[] }) => section.fields.map(field => field.label));
    for (const label of new Set(expectedLabels)) {
      expect(actualLabels.filter(text => text === label).length).toBe(expectedLabels.filter(text => text === label).length);
      expect(label).not.toMatch(/^(?:id|source_|row_|case_|normalized_|raw_|状态$)/i);
    }
    expect(await drawer.innerText()).not.toContain('\uFFFD');
    const money = drawer.locator('.entity-detail-row__amount');
    for (let i = 0; i < await money.count(); i++) await expect(money.nth(i)).toHaveCSS('text-align', 'left');
    for (const width of [1440, 480]) {
      await page.setViewportSize({ width, height: 900 });
      const scroll = drawer.locator('.finance-drawer__body');
      expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
      expect(await scroll.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 2)).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ animations: "disabled", path: info.outputPath(`${sample}-${width}.png`) });
    }
    metrics.push({ sample, documents: ids.size, fields: expectedLabels.length, firstPaintMs });
    await drawer.getByRole('button', { name: /关闭.*抽屉|关闭详情/ }).click();
    await expect(drawer).toBeHidden();
    await page.setViewportSize({ width: 1440, height: 900 });
  };
  await page.goto('/fin-ops/bank-details');
  await inspect(page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first(), 'bank');
  await page.goto('/fin-ops/output-invoice-collections');
  await inspect(page.getByRole('button', { name: /^红蓝票 · / }).first(), 'red-blue', true);
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'output-invoice');
  await page.goto('/fin-ops/input-invoice-usage');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'input-invoice');
  await page.goto('/fin-ops/oa-pending-payments');
  await inspect(page.getByRole('button', { name: /^查看 OA .*详情$/ }).first(), 'oa');
  await page.goto('/fin-ops/pending-invoices');
  await inspect(page.getByRole('button', { name: /^流水详情 / }).first(), 'pending-bank');
  await page.goto('/fin-ops/');
  await inspect(page.getByRole('button', { name: /^查看OA .*详情$/ }).first(), 'workbench-oa');
  await inspect(page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first(), 'workbench-bank');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'workbench-invoice');
  await page.goto('/fin-ops/cost-statistics');
  await page.getByRole('radio', { name: '按时间', exact: true }).click();
  await inspect(page.getByRole('grid', { name: '按时间银行流水表' }).getByRole('button', { name: /^查看银行流水 / }).first(), 'cost-bank');
  expect(writes).toEqual([]); expect(failures).toEqual([]);
  await info.attach('production-source-details', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
});
