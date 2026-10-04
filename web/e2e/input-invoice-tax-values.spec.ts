import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

test('input amount column has two aligned lines and retains its geometry while refreshing', async ({page}) => {
  await installDeterministicApiMocks(page, {sessionMode: 'user'});
  let releaseRefresh: (() => void) | undefined;
  let holdRefresh = false;
  await page.route('**/api/input-invoice-usage/rows*', async route => {
    if (holdRefresh) await new Promise<void>(resolve => { releaseRefresh = resolve; });
    await route.fulfill({json: {
      rows: ['13%', '—', '免税'].map((taxRate, index) => ({
        id: `tax-rate-row-${index}`, invoice: {
          id: `tax-rate-invoice-${index}`, displayNo: `TAX-RATE-${index}`, invoiceNo: `TAX-RATE-${index}`,
          issueDate: '2026-09-22', sellerName: '桌面排版测试供应商', sellerTaxNo: '915300000000000001',
          totalWithTax: index === 0 ? '2129682.59' : index === 1 ? null : '0.00', amountWithoutTax: index === 0 ? '1884674.86' : '1000.00', taxAmount: index === 0 ? '245007.73' : '130.00', taxRate,
          taxableItemName: '设备服务',
        }, paymentStatus: {code: 'waiting_payment', label: '待核对', reason: ''},
        oa: {primary: null, relationCount: 0, summaries: []}, bank: {primary: null, relationCount: 0, summaries: []},
      })), pagination: {page: 1, pageSize: 20, total: 3}, summary: {invoiceCount: 3}, statistics: {invoice_count: 3}, filterOptions: [],
    }});
  });
  await page.goto('/input-invoice-usage');
  const grid = page.getByRole('table', {name: '进项发票使用情况表'});
  await expect(grid.getByRole('columnheader', {name: '价税合计/税率', exact: true})).toBeVisible();
  const cells = page.locator('.input-invoice-usage-table-cell--amount').filter({has: page.locator('.input-invoice-usage-tax-rate')});
  await expect(cells).toHaveCount(3);
  const output = resolve('..', 'outputs', 'tax-rate-correction');
  await mkdir(output, {recursive: true});
  for (const [width, zoom] of [[1440, 1], [1920, 1], [1440, 1.25]]) {
    await page.setViewportSize({width, height: 1000});
    await page.locator('body').evaluate((el, scale) => { el.style.zoom = String(scale); }, zoom);
    for (const [index, rate] of ['13%', '—', '免税'].entries()) {
      const cell = cells.nth(index);
      await expect(cell.locator('.input-invoice-usage-money-primary')).toHaveText(index === 0 ? '2129682.59' : index === 1 ? '—' : '0.00');
      await expect(cell.locator('.input-invoice-usage-tax-rate')).toHaveText(rate);
      await expect(cell).not.toContainText('1000.00');
      await expect(cell).not.toContainText('(130.00)');
      const layout = await cell.evaluate(el => {
        const primary = el.children[0], secondary = el.children[1];
        const first = primary.getBoundingClientRect(), second = secondary.getBoundingClientRect();
        return {aligned: Math.abs(first.right-second.right) < 1, stacked: second.top >= first.bottom,
          smaller: parseFloat(getComputedStyle(secondary).fontSize) < parseFloat(getComputedStyle(primary).fontSize),
          overflow: el.scrollWidth > el.clientWidth+1, align: getComputedStyle(el).textAlign,
          secondaryColor: getComputedStyle(secondary).color, primaryColor: getComputedStyle(primary).color};
      });
      expect(layout.aligned).toBe(true);
      expect(layout.stacked).toBe(true);
      expect(layout.smaller).toBe(true);
      expect(layout.overflow).toBe(false);
      expect(layout.align).toBe('right');
      expect(layout.secondaryColor).not.toBe(layout.primaryColor);
    }
    await page.screenshot({path: resolve(output, `input-two-line-${width}-${zoom}.png`), animations: 'disabled'});
  }
  const geometry = () => cells.evaluateAll(elements => elements.map(el => {
    const {x, y, width, height} = el.getBoundingClientRect(); return {x, y, width, height};
  }));
  const before = await geometry();
  holdRefresh = true;
  await page.getByRole('button', {name: '刷新', exact: true}).click();
  await expect.poll(() => Boolean(releaseRefresh)).toBe(true);
  expect(await geometry()).toEqual(before);
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/input-invoice-usage/rows');
  releaseRefresh!();
  await refreshed;
  await expect(page.getByRole('button', {name: '刷新', exact: true})).toBeEnabled();
  expect(await geometry()).toEqual(before);
});
