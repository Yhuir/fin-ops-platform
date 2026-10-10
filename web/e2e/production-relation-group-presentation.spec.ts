import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

for (const routeName of ['input-invoice-usage', 'oa-pending-payments', 'pending-invoices', 'output-invoice-collections']) {
  test(`production ${routeName}: grouped expansion is read-only and clears on collapse`, async ({ page }, info) => {
    test.skip(!enabled || !token, 'Requires explicit production read-only verification and controlled local token.');
    await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
    const writes: string[] = [];
    const errors: string[] = [];
    let businessReads = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        writes.push(`${request.method()} ${path}`);
        await route.abort('blockedbyclient');
        return;
      }
      if (path.startsWith('/fin-ops-api/api/') && !['/fin-ops-api/api/app-health', '/fin-ops-api/api/background-jobs/active'].includes(path)) businessReads++;
      await route.continue();
    });
    await page.goto(`/fin-ops/${routeName}`);
    const trigger = page.locator('.relation-count-button').first();
    await expect(trigger).toBeVisible();
    await page.waitForLoadState('networkidle');
    const before = businessReads;
    await trigger.click();
    await page.mouse.move(5, 5);
    await trigger.evaluate(button => (button as HTMLElement).blur());
    const groupedRows = page.locator('tr[data-relation-group]');
    await expect.poll(() => groupedRows.count()).toBeGreaterThan(1);
    const parentId = await trigger.locator('xpath=ancestor::tr').getAttribute('data-relation-group');
    expect(parentId).toBeTruthy();
    await expect.poll(() => groupedRows.evaluateAll(rows => rows.flatMap(row => [...row.children].map(cell => getComputedStyle(cell).backgroundColor))))
      .toEqual(Array(await groupedRows.locator('th,td').count()).fill('rgb(244, 247, 251)'));
    const presentation = await groupedRows.evaluateAll(rows => rows.map(row => ({
      group: row.getAttribute('data-relation-group'),
      line: getComputedStyle(row.firstElementChild!).backgroundImage,
      lineSize: getComputedStyle(row.firstElementChild!).backgroundSize,
    })));
    for (const row of presentation) {
      expect(row.group).toBe(parentId);
      expect(row.line).toContain('rgb(158, 181, 219)');
      expect(row.lineSize).toBe('3px 100%');
    }
    expect(businessReads).toBe(before);
    await page.setViewportSize({ width: 1920, height: 1100 });
    await page.screenshot({ path: info.outputPath(`production-${routeName}-group.png`), animations: 'disabled' });
    await trigger.click();
    await expect(groupedRows).toHaveCount(0);
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(businessReads).toBe(before);
    expect(errors).toEqual([]);
    expect(writes).toEqual([]);
    await info.attach('production-relation-group', { body: JSON.stringify({ routeName, parentId, presentation, additionalBusinessReads: businessReads - before, errors, writes }), contentType: 'application/json' });
  });
}
