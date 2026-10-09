import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 900 } });
for (const name of ['pending-invoices', 'oa-pending-payments', 'output-invoice-collections']) {
  test(`production ${name} hierarchy, filters, counts and responsive layout`, async ({ page }, info) => {
    test.skip(!enabled || !token, 'Requires explicit production read-only mode and token.');
    test.setTimeout(180_000);
    await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
    const writes: string[] = []; const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/fin-ops-api/**', async route => {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
        writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
      } else await route.continue();
    });
    const nextRows = () => page.waitForResponse(response => new URL(response.url()).pathname.endsWith(`/${name}/rows`) && !response.url().includes('include_statistics=true'));
    const started = Date.now();
    const first = nextRows(); await page.goto(`https://www.yn-sourcing.com/fin-ops/${name}`);
    expect((await first).status()).toBe(200);
    const header = page.locator('.table-classification');
    await expect(header).toHaveAttribute('aria-busy', 'false');
    const firstVisibleMs = Date.now() - started;
    const root = header.locator('.table-classification__root');
    const count = async (selector: string) => Number((await header.locator(selector).locator('.stable-count').innerText()).match(/\d+/)![0]);
    const groups = await header.getByRole('group').all();
    let groupTotal = 0;
    for (const group of groups) {
      const parent = Number((await group.locator('.table-classification__parent .stable-count').innerText()).match(/\d+/)![0]);
      const childCounts = await group.locator('.table-classification__leaf .stable-count').allTextContents();
      expect(childCounts.reduce((sum, value) => sum + Number(value.match(/\d+/)![0]), 0)).toBe(parent);
      groupTotal += parent;
    }
    expect(await count('.table-classification__root')).toBe(groupTotal);
    const samples: { id: string; count: number; visibleMs: number }[] = [];
    for (const button of await header.locator('.table-classification__leaf').all()) {
      const id = (await button.getAttribute('data-classification-id'))!;
      const expected = Number((await button.locator('.stable-count').innerText()).match(/\d+/)![0]);
      const response = nextRows(); const clickStarted = Date.now(); await button.click();
      const result = await response; expect(result.status()).toBe(200); const payload = await result.json();
      await expect(header).toHaveAttribute('aria-busy', 'false');
      await expect(button).toHaveAttribute('aria-pressed', 'true');
      const actual = name === 'pending-invoices' ? payload.acquisition_summary.bank_count : name === 'oa-pending-payments' ? payload.summary.oaCount : payload.pagination.total;
      expect(actual, id).toBe(expected);
      samples.push({ id, count: expected, visibleMs: Date.now() - clickStarted });
    }
    const reset = nextRows();
    if (name === 'oa-pending-payments') await groups[0].locator('.table-classification__parent').click();
    else await root.click();
    await reset; await expect(header).toHaveAttribute('aria-busy', 'false');
    for (const width of [1920, 1440, 1366, 1024]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await header.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      for (const cell of await header.locator('.table-classification__cell').all()) {
        expect(await cell.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      }
      await page.screenshot({ path: info.outputPath(`${name}-${width}.png`), animations: 'disabled' });
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const zoom of ['1.25', '1.5']) {
      await page.locator('body').evaluate((el, value) => { el.style.zoom = value; }, zoom);
      expect(await header.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      await page.screenshot({ path: info.outputPath(`${name}-zoom-${zoom}.png`), animations: 'disabled' });
    }
    await page.locator('body').evaluate(el => { el.style.zoom = ''; });
    if (name !== 'oa-pending-payments') {
      const firstLeaf = header.locator('.table-classification__leaf').first();
      const response = nextRows(); await firstLeaf.click(); const payload = await (await response).json();
      await expect(header).toHaveAttribute('aria-busy', 'false');
      const expected = name === 'pending-invoices' ? payload.acquisition_summary.bank_count : payload.pagination.total;
      const preview = page.waitForResponse(r => new URL(r.url()).pathname.endsWith(`/${name}/export-summary`));
      await page.getByRole('button', { name: '筛选内容导出', exact: true }).click();
      expect((await (await preview).json()).row_count).toBe(expected);
      if (expected > 0) {
        const download = page.waitForEvent('download');
        await page.getByRole('button', { name: '导出', exact: true }).click();
        expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
      }
      await page.getByRole('button', { name: name === 'pending-invoices' ? '关闭导出待找发票' : '关闭导出销项发票', exact: true }).click();
    }
    expect(writes).toEqual([]); expect(errors).toEqual([]);
    await info.attach('classification-verification', { body: JSON.stringify({ name, firstVisibleMs, groupTotal, samples, writes, errors }), contentType: 'application/json' });
  });
}
