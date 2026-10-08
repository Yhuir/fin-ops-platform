import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const path = '/fin-ops-api/api/workbench/settings/oa/manual-search';
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production historical OA source search, pagination and statuses are read-only', async ({ page, baseURL }, info) => {
  test.skip(!enabled || !token, 'Requires production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: new URL(baseURL!).hostname,
    path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [];
  await page.route('**/*', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(route.request().method() + ' ' + new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  await page.goto('/fin-ops/settings');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await page.getByLabel('搜索关键字', { exact: true }).fill('胡');
  await page.getByLabel('开始日期', { exact: true }).fill('2025-01-01');
  await page.getByLabel('结束日期', { exact: true }).fill('2025-12-31');
  const response = page.waitForResponse(r => new URL(r.url()).pathname === path);
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  const first = await result.json();
  expect(first.total).toBeGreaterThan(0);
  await expect(page.getByRole('grid', { name: 'OA全量搜索导入结果' })).toContainText(first.rows[0].oa_no);
  const params = { q: '胡', date_from: '2025-01-01', date_to: '2025-12-31',
    form_types: 'payment_request,expense_claim', statuses: 'completed,in_progress', page_size: 100 };
  const all: Array<{ row_id: string; application_date: string; status: string; can_import: boolean }> = [];
  for (let index = 0; index * 100 < first.total; index++) {
    const r = await page.request.get(path, { params: { ...params, page: index } });
    expect(r.status()).toBe(200);
    const payload = await r.json();
    expect(payload.total).toBe(first.total);
    all.push(...payload.rows);
  }
  expect(all.length).toBe(first.total);
  expect(new Set(all.map(r => r.row_id)).size).toBe(first.total);
  expect(all.every(r => r.application_date.startsWith('2025-'))).toBe(true);
  const exact = await page.request.get(path, { params: { q: all[0].row_id, page_size: 2 } });
  expect(exact.status()).toBe(200);
  const exactResult = await exact.json();
  expect(exactResult.rows.map((r: { row_id: string }) => r.row_id)).toEqual([all[0].row_id]);
  const progress = await page.request.get(path, { params: { statuses: 'in_progress', page_size: 20 } });
  expect(progress.status()).toBe(200);
  const progressResult = await progress.json();
  for (const row of progressResult.rows) {
    expect(row.status).toBe('in_progress');
    expect(row.can_import).toBe(false);
  }
  expect(writes).toEqual([]);
  await info.attach('historical-oa-readonly', { body: JSON.stringify({ historicalCount: all.length,
    inProgressCount: progressResult.total, exactIdentityVerified: true, writes: writes.length }), contentType: 'application/json' });
});
