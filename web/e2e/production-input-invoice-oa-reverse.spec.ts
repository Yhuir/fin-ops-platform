import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const api = '/fin-ops-api/api/input-invoice-usage';
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production reverse candidates match unused invoices and reject used selections without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [];
  await page.route('**/*', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && !(request.method() === 'POST' && path === `${api}/oa-reverse/preview`)) {
      writes.push(`${request.method()} ${path}`);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  await page.goto('/fin-ops/input-invoice-usage');
  await expect(page.locator('.invoice-usage-classification')).toHaveAttribute('aria-busy', 'false');
  const previewResponse = page.waitForResponse(response => new URL(response.url()).pathname === `${api}/oa-reverse/preview`);
  await page.getByRole('button', { name: '以发票反提 OA', exact: true }).click();
  expect((await previewResponse).status()).toBe(200);
  const drawer = page.getByLabel('以发票反提 OA 工作流', { exact: true });
  await expect(drawer.getByText('待使用发票', { exact: true })).toBeVisible();
  await expect(drawer.getByRole('button', { name: /筛选流水关联状态/ })).toHaveCount(0);

  const candidateIds = new Set<string>();
  const unusedIds = new Set<string>();
  let candidateTotal = 0;
  let unusedTotal = 0;
  let candidateAmount = '';
  let unusedAmount = '';
  for (let index = 1; index === 1 || (index - 1) * 200 < Math.max(candidateTotal, unusedTotal); index++) {
    const preview = await page.request.post(`${api}/oa-reverse/preview`, { data: { page: index, pageSize: 200 } });
    expect(preview.status()).toBe(200);
    const candidates = await preview.json();
    expect(candidates).not.toHaveProperty('relationCounts');
    candidateTotal = candidates.pagination.total;
    candidateAmount = candidates.totalWithTax;
    for (const row of candidates.invoiceRows) {
      candidateIds.add(row.invoiceId);
      expect(row.oaRelationStatus).toBe('unlinked');
      expect(row.bankRelationStatus).toBe('unlinked');
    }
    const response = await page.request.get(`${api}/rows`, { params: { page: index, page_size: 200,
      filters: JSON.stringify([{ field: 'usage_status', operator: 'in', values: ['unused'] }]) } });
    expect(response.status()).toBe(200);
    const unused = await response.json();
    unusedTotal = unused.pagination.total;
    unusedAmount = unused.summary.totalWithTax;
    for (const row of unused.rows) for (const invoice of row.invoiceRelations.summaries) unusedIds.add(invoice.invoiceId);
  }
  expect([...candidateIds].sort()).toEqual([...unusedIds].sort());
  expect(candidateIds.size).toBe(candidateTotal);
  expect(candidateAmount).toBe(unusedAmount);

  const usedResponse = await page.request.get(`${api}/rows`, { params: { page_size: 1,
    filters: JSON.stringify([{ field: 'usage_status', operator: 'in', values: ['used'] }]) } });
  expect(usedResponse.status()).toBe(200);
  const used = await usedResponse.json();
  expect(used.rows.length).toBeGreaterThan(0);
  const rejectedResponse = await page.request.post(`${api}/oa-reverse/preview`, { data: { invoiceIds: [used.rows[0].invoiceId] } });
  expect(rejectedResponse.status()).toBe(200);
  const rejected = await rejectedResponse.json();
  expect(rejected.invoiceRows).toEqual([]);
  expect(rejected.canCreateDraft).toBe(false);
  expect(rejected.rejectedInvoices).toHaveLength(1);
  expect(['already_has_active_oa', 'already_has_active_bank']).toContain(rejected.rejectedInvoices[0].reasonCode);
  expect(writes).toEqual([]);
  await info.attach('reverse-unused-readonly-verification', { body: JSON.stringify({ candidateCount: candidateIds.size,
    unusedCount: unusedIds.size, totalWithTax: candidateAmount, usedSelectionRejected: true, writes: writes.length }), contentType: 'application/json' });
});
