import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

const production = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
test.use({ viewport: { width: 1700, height: 1000 }, ...(production ? { trace: 'off' as const, video: 'off' as const, screenshot: 'off' as const } : {}) });

for (const name of ['oa-pending-payments', 'pending-invoices', 'output-invoice-collections', 'input-invoice-usage']) {
  test(`${name}: exact selection, stable geometry and table groups`, async ({ page }, info) => {
    test.setTimeout(120_000);
    const writes: string[] = [];
    let rowsRequests = 0;
    page.on('request', request => { if (new URL(request.url()).pathname.endsWith(`/${name}/rows`)) rowsRequests++; });
    if (production) {
      const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
      expect(token, 'Production token must be supplied through the wrapper').toBeTruthy();
      await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
      await page.route('**/fin-ops-api/**', async route => {
        if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
          writes.push(route.request().method()); await route.abort();
        } else await route.continue();
      });
    } else await installDeterministicApiMocks(page, { sessionMode: 'admin', outputInvoiceCollectionListInteractions: true });
    await page.goto(`${production ? '/fin-ops' : ''}/${name}`);
    const input = name === 'input-invoice-usage';
    const header = page.locator(input ? '.invoice-usage-classification' : '.table-classification');
    await expect(header).toBeVisible();
    await expect(header).toHaveAttribute('aria-busy', 'false');
    const parent = header.locator(input ? '.invoice-usage-classification__group-title' : '.table-classification__parent').first();
    const leaf = header.locator(input ? '.invoice-usage-classification__child' : '.table-classification__leaf').first();
    const samples: { selection: string; selectionMs: number; visibleMs: number; rowsRequests: number; shift: number }[] = [];
    for (const target of [parent, leaf, parent]) {
      const label = target.locator('span').first();
      const before = (await label.boundingBox())!;
      const background = await target.evaluate(el => getComputedStyle(el).backgroundColor);
      const started = Date.now();
      const requestsBefore = rowsRequests;
      await target.click();
      await expect(target).toHaveAttribute('aria-pressed', 'true');
      const selectionMs = Date.now() - started;
      await expect(header.locator('[aria-pressed="true"]')).toHaveCount(1);
      await expect(target.locator('.classification-choice__check')).toBeVisible();
      await expect(header).toHaveAttribute('aria-busy', 'false');
      const after = (await label.boundingBox())!;
      expect(await target.evaluate(el => getComputedStyle(el).backgroundColor)).toBe(background);
      expect(Math.abs(after.x - before.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1);
      samples.push({ selection: (await target.innerText()).replace('✓', '').trim(), selectionMs, visibleMs: Date.now() - started, rowsRequests: rowsRequests - requestsBefore, shift: Math.abs(after.x - before.x) });
    }
    for (const width of [1700, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(await header.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      for (const cell of await header.getByRole('button').all()) {
        expect(await cell.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      }
      if (name === 'oa-pending-payments') {
        for (const label of await page.locator('.oa-pending-payments-table-column-group').all()) {
          const offset = await label.evaluate(el => {
            const r = document.createRange(); r.selectNodeContents(el);
            const text = r.getBoundingClientRect(), group = el.closest('th')!.getBoundingClientRect();
            return Math.abs((text.left + text.right - group.left - group.right) / 2);
          });
          expect(offset).toBeLessThanOrEqual(2);
        }
        expect(await page.locator('.oa-pending-payments-subheader-grid--bank').evaluate(el => parseFloat(getComputedStyle(el).columnGap))).toBeGreaterThanOrEqual(20);
        const bankRows = page.locator('.oa-pending-payments-bank-grid');
        if (await bankRows.count()) expect(await bankRows.first().evaluate(el => parseFloat(getComputedStyle(el).columnGap))).toBeGreaterThanOrEqual(20);
      }
      if (name === 'pending-invoices') {
        const groups = page.locator('.pending-invoices-group-heading');
        await expect(groups).toHaveCount(4);
        const spans = [[0, 2], [3, 3], [4, 6], [7, 8]];
        const columns = page.locator('.pending-invoices-table thead th');
        for (let i = 0; i < spans.length; i++) {
          const box = (await groups.nth(i).boundingBox())!;
          const left = (await columns.nth(spans[i][0]).boundingBox())!;
          const right = (await columns.nth(spans[i][1]).boundingBox())!;
          expect(Math.abs(box.x - left.x)).toBeLessThanOrEqual(2);
          expect(Math.abs(box.x + box.width - right.x - right.width)).toBeLessThanOrEqual(2);
        }
        await expect(page.locator('thead .pending-invoices-col-invoice-amount')).toHaveText('金额↕');
        const scroll = page.locator('.pending-invoices-table .finance-table__scroll');
        await scroll.evaluate(el => { el.scrollTop = 80; });
        const headingBox = (await page.locator('.pending-invoices-group-headings').boundingBox())!;
        const columnBox = (await columns.first().boundingBox())!;
        expect(Math.abs(columnBox.y - headingBox.y - headingBox.height)).toBeLessThanOrEqual(2);
        await scroll.evaluate(el => { el.scrollTop = 0; });
        for (const cell of await page.locator('tbody .pending-invoices-col-invoice-amount').all()) {
          expect(await cell.innerText()).not.toMatch(/已付|待付/);
          expect(await cell.evaluate(el => getComputedStyle(el).textAlign)).toBe('center');
        }
      }
      await page.screenshot({ path: info.outputPath(`${name}-${width}.png`), animations: 'disabled' });
    }
    expect(writes).toEqual([]);
    await info.attach('interaction-measurements', { body: JSON.stringify({ name, production, samples, writes }), contentType: 'application/json' });
  });
}
