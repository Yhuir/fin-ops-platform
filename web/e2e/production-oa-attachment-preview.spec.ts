import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_ATTACHMENT_PREVIEW === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const path = '/fin-ops-api/api/workbench/settings/oa/manual-search';
const ids = ['oa-exp-6930257c80b0b57ba8596029', 'oa-exp-6930287280b0b57ba859602a',
  'oa-exp-694b407d80b0b57ba8596055', 'oa-exp-694b409c80b0b57ba8596056'];
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production historical attachment preview resolves files without formal import', async ({ page, baseURL }, info) => {
  test.skip(!enabled || !token, 'Requires explicitly enabled production attachment preview.');
  test.setTimeout(600_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: new URL(baseURL!).hostname,
    path: '/', secure: true, sameSite: 'Lax' }]);
  const params = { q: '胡', date_from: '2025-11-08', date_to: '2025-12-31', page_size: 100 };
  const beforeResponse = await page.request.get(path, { params });
  expect(beforeResponse.status()).toBe(200);
  const before = await beforeResponse.json();
  expect(before.rows.map((row: { row_id: string }) => row.row_id).sort()).toEqual([...ids].sort());
  expect(before.rows.every((row: { import_status: string }) => row.import_status === 'not_imported')).toBe(true);
  const start = Date.now();
  const request = await page.request.post(`${path}/prepare-attachments`, { data: { row_ids: ids } });
  expect(request.status()).toBe(202);
  const accepted = await request.json();
  expect(accepted.affected_scope_keys).toEqual([]);
  let result: any;
  await expect.poll(async () => {
    const statusResponse = await page.request.get(`${path}/refresh-attachments/${accepted.event_id}`);
    expect(statusResponse.status()).toBe(200);
    result = await statusResponse.json();
    expect(['failed', 'dead_lettered']).not.toContain(result.status);
    return result.status;
  }, { timeout: 540_000, intervals: [1000, 2000, 3000, 5000] }).toBe('done');
  expect(result.result.promotion_summary).toEqual({});
  expect(result.result.affected_scope_keys).toEqual([]);
  expect(result.result.errors).toEqual([]);
  const parseMs = Date.now() - start;
  const afterResponse = await page.request.get(path, { params });
  expect(afterResponse.status()).toBe(200);
  const after = await afterResponse.json();
  expect(after.total).toBe(4);
  for (const row of after.rows) {
    expect(row.import_status).toBe('not_imported');
    expect(row.attachment_status).toBe('ready');
    expect(row.pending_attachment_count).toBe(0);
    expect(row.failed_attachment_count).toBe(0);
    const parsed = result.result.rows.find((item: { row_id: string }) => item.row_id === row.row_id);
    for (const key of ['attachment_file_count', 'importable_invoice_count', 'unrecognized_attachment_count',
      'attachment_status', 'pending_attachment_count', 'failed_attachment_count', 'unsupported_attachment_count']) {
      expect(row[key]).toEqual(parsed[key]);
    }
    for (const item of row.items) {
      expect(item.attachment_status).toBe('ready');
      expect(item.pending_attachment_count).toBe(0);
      expect(item.failed_attachment_count).toBe(0);
    }
  }
  expect(after.rows.reduce((sum: number, row: { attachment_file_count: number }) => sum + row.attachment_file_count, 0)).toBe(16);
  expect(after.rows.reduce((sum: number, row: { importable_invoice_count: number }) => sum + row.importable_invoice_count, 0)).toBeGreaterThan(0);
  const timings: number[] = [];
  for (let i = 0; i < 20; i++) {
    const t = Date.now();
    const response = await page.request.get(path, { params });
    expect(response.status()).toBe(200);
    const current = await response.json();
    timings.push(Date.now() - t);
    expect(current.rows).toEqual(after.rows);
  }
  timings.sort((a, b) => a - b);
  await page.goto('/fin-ops/settings');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await page.getByLabel('搜索关键字', { exact: true }).fill('胡');
  await page.getByLabel('开始日期', { exact: true }).fill('2025-11-08');
  await page.getByLabel('结束日期', { exact: true }).fill('2025-12-31');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  const grid = page.getByRole('grid', { name: 'OA全量搜索导入结果' });
  await expect(grid).toContainText('已识别发票');
  await expect(grid).not.toContainText('待解析');
  await page.getByRole('button', { name: '展开 OA 1922 明细', exact: true }).click();
  await expect(grid).toContainText('明细已识别发票');
  await info.attach('attachment-preview-verification', { body: JSON.stringify({ eventId: accepted.event_id,
    parseMs, rows: after.rows, searchTimingMs: { n: timings.length, p50: timings[9], p95: timings[18], max: timings[19] } }),
    contentType: 'application/json' });
});
