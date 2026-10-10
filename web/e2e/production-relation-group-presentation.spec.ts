import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

for (const [routeName, columns, kinds] of [
  ['input-invoice-usage', 10, ['invoice', 'oa', 'bank']],
  ['oa-pending-payments', 4, ['invoice', 'oa', 'bank']],
  ['pending-invoices', 9, ['invoice', 'oa', 'bank']],
  ['output-invoice-collections', 8, ['invoice', 'bank']],
] as const) {
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
    const pendingPayload = routeName === 'pending-invoices'
      ? page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname.endsWith('/api/pending-invoices/rows') && url.searchParams.get('include_statistics') !== 'true' && response.ok();
      })
      : null;
    await page.goto(`/fin-ops/${routeName}`);
    const canonicalRows = pendingPayload ? (await (await pendingPayload).json()).rows : [];
    await expect(page.locator('.relation-count-button').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.setViewportSize({ width: 1920, height: 1100 });
    const checked: Array<Record<string, unknown>> = [];
    const absent: string[] = [];
    for (const kind of kinds) {
      const trigger = page.locator('.relation-count-button').filter({ hasText: kind === 'invoice' ? /张/ : kind === 'oa' ? /条/ : /笔/ }).first();
      // Real production can have no multi-member group of a kind on this page;
      // deterministic tests separately exercise all eleven kinds without fabricated production facts.
      if (!await trigger.count()) { absent.push(kind); continue; }
      const count = Number((await trigger.innerText()).match(/\d+/)![0]);
      const before = businessReads;
      const opened = Date.now();
      await trigger.click();
      const groupedRows = page.locator('tr[data-relation-group]');
      await expect(groupedRows).toHaveCount(count);
      await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0);
      await expect.poll(() => page.locator('.relation-motion-clip').evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
      const settledMs = Date.now() - opened;
      await page.mouse.move(5, 5);
      await page.getByRole('heading', { level: 1 }).click();
      await expect.poll(() => groupedRows.evaluateAll(rows => rows.map(row =>
        [...row.children].map(cell => getComputedStyle(cell).backgroundColor),
      ))).toEqual(Array.from({ length: count }, () => Array(columns).fill('rgb(244, 247, 251)')));
      const parentId = await trigger.locator('xpath=ancestor::tr').getAttribute('data-relation-group');
      const presentation = await groupedRows.evaluateAll(rows => rows.map(row => ({
        group: row.getAttribute('data-relation-group'),
        line: getComputedStyle(row.firstElementChild!).backgroundImage,
        lineSize: getComputedStyle(row.firstElementChild!).backgroundSize,
        cells: [...row.children].map(cell => ({ x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width, background: getComputedStyle(cell).backgroundColor })),
      })));
      for (const row of presentation) {
        expect(row.group).toBe(parentId);
        expect(row.line).toContain('rgb(158, 181, 219)');
        expect(row.lineSize).toBe('3px 100%');
        expect(row.cells).toHaveLength(columns);
        expect(row.cells).toEqual(presentation[0].cells);
        expect(row.cells.map(cell => cell.background)).toEqual(Array(columns).fill('rgb(244, 247, 251)'));
      }
      expect(businessReads).toBe(before);
      if (routeName === 'pending-invoices' && kind === 'invoice') {
        const source = canonicalRows.find((row: { id: string }) => row.id === parentId);
        expect(source).toBeDefined();
        const bankMembers = source.bank_transactions.summaries.length
          ? source.bank_transactions.summaries : [source.bank_transactions.primary];
        const oaMembers = source.oa.summaries.length ? source.oa.summaries : [source.oa.primary].filter(Boolean);
        const expectedInvoices = source.input_invoices.summaries;
        expect(expectedInvoices).toHaveLength(count);
        for (let index = 0; index < count; index++) {
          const invoice = expectedInvoices[index];
          const cells = groupedRows.nth(index).locator('th,td');
          await expect(cells.nth(4)).toContainText(invoice.digital_invoice_no || invoice.invoice_no);
          await expect(cells.nth(6)).toContainText(Number(invoice.total_with_tax).toFixed(2));
          const caseIds: string[] = invoice.relation_case_ids;
          expect(caseIds.length).toBeGreaterThan(0);
          const belongs = (member: { relation_case_ids: string[] }) => member.relation_case_ids.some(id => caseIds.includes(id));
          const exactBanks = bankMembers.filter(belongs);
          const exactOas = oaMembers.filter(belongs);
          if (exactBanks.length === 1) {
            await expect(cells.nth(0)).toContainText(exactBanks[0].counterparty_name);
            await expect(cells.nth(1)).toContainText(Number(exactBanks[0].original_amount).toFixed(2));
          }
          if (exactOas.length === 1) {
            await expect(cells.nth(7)).toContainText(exactOas[0].applicant);
            await expect(cells.nth(8)).toContainText(exactOas[0].project_name);
          }
        }
      }
      await page.screenshot({ path: info.outputPath(`production-${routeName}-${kind}-group.png`), animations: 'disabled' });
      let detailReads = 0;
      if (kind === 'invoice') {
        const detail = groupedRows.nth(1).getByRole('button', { name: /(?:查看发票 .* 详情|发票详情 .*)/ });
        const label = (await detail.getAttribute('aria-label'))!;
        const invoiceNumber = label.replace(/^查看发票\s+|\s+详情$/g, '').replace(/^发票详情\s+/, '');
        const response = page.waitForResponse(response => /\/invoices\/[^/]+\/detail(?:\?|$)/.test(response.url()));
        await detail.click();
        expect((await response).ok()).toBe(true);
        const drawer = page.getByRole('dialog', { name: '发票详情', exact: true });
        await expect(drawer.getByText(invoiceNumber, { exact: true }).first()).toBeVisible();
        await expect(drawer.getByRole('alert')).toHaveCount(0);
        detailReads = businessReads - before;
        expect(detailReads).toBe(1);
        await drawer.getByRole('button', { name: '关闭详情抽屉' }).click();
        await expect(drawer).toHaveCount(0);
        await expect(groupedRows).toHaveCount(count);
      }
      await trigger.click();
      await expect(groupedRows).toHaveCount(0);
      await expect(trigger).toHaveAttribute('aria-expanded', 'false');
      expect(businessReads).toBe(before + detailReads);
      checked.push({ kind, parentId, count, columns, settledMs, additionalBusinessReads: businessReads - before - detailReads, clickedDetailReads: detailReads });
    }
    expect(checked.length).toBeGreaterThan(0);
    expect(errors).toEqual([]);
    expect(writes).toEqual([]);
    await info.attach('production-relation-group', { body: JSON.stringify({ routeName, checked, absentKindsOnCurrentPage: absent, errors, writes }), contentType: 'application/json' });
  });
}
