import { expect, test } from './fixtures/strictTest';
import { WORKBENCH_AMOUNT_ANOMALY_CODES, WORKBENCH_AMOUNT_ANOMALY_LABELS } from '../src/features/workbench/types';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 1000 } });

test('production exception groups agree across summary, classifications, pagination and drawer', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(180_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: string[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => {
    if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  const initialResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/fin-ops-api/api/workbench');
  await page.goto('/fin-ops/');
  const initial = await (await initialResponse).json();
  const summary = initial.summary;
  const metrics: object[] = [];
  await page.getByRole('button', { name: /^未配对异常 \d+组 \| 已配对异常 \d+组$/ }).click();
  const drawer = page.getByRole('dialog', { name: '异常处理' });
  await expect(drawer).toBeVisible();
  for (const bucket of ['unpaired', 'paired'] as const) {
    const label = bucket === 'unpaired' ? '未配对异常' : '已配对异常';
    const params = new URLSearchParams({ month: 'all', zone: bucket, exception_bucket: bucket, page_size: '10', detail_level: 'summary' });
    const response = await page.request.get(`/fin-ops-api/api/workbench/groups?${params}`);
    expect(response.status()).toBe(200);
    const base = await response.json(), counts = base.exception_counts;
    for (const count of [counts.total, counts.amount_total, counts.document_only, ...Object.values(counts.by_code)]) {
      expect(Number.isSafeInteger(count)).toBe(true);
      expect(count).toBeGreaterThanOrEqual(0);
    }
    expect(counts.total).toBe(counts.amount_total + counts.document_only);
    expect(Object.values<number>(counts.by_code).reduce((sum, count) => sum + count, 0)).toBe(counts.amount_total);
    expect(base.total).toBe(counts.total);
    expect(summary[`${bucket}_exception_counts`]).toBe(counts.total);
    const ids = new Set<string>();
    let cursor: string | null = null;
    let pages = 0;
    do {
      if (cursor) params.set('cursor', cursor);
      const body = pages === 0 ? base : await (await page.request.get(`/fin-ops-api/api/workbench/groups?${params}`)).json();
      expect(body.exception_counts).toEqual(counts);
      expect(body.total).toBe(counts.total);
      for (const group of body.groups) {
        expect(ids.has(group.group_id)).toBe(false);
        ids.add(group.group_id);
      }
      cursor = body.next_cursor;
      expect(Boolean(cursor)).toBe(body.has_more);
      pages += 1;
      expect(pages).toBeLessThan(100);
    } while (cursor);
    expect(ids.size).toBe(counts.total);
    await drawer.getByRole('radio', { name: `${label} ${counts.total}组`, exact: true }).click();
    await expect(drawer.getByRole('radio', { name: `金额异常 ${counts.amount_total}组`, exact: true })).toBeVisible();
    for (const code of WORKBENCH_AMOUNT_ANOMALY_CODES) {
      const category = drawer.getByRole('radio', { name: `${WORKBENCH_AMOUNT_ANOMALY_LABELS[code]} ${counts.by_code[code]}组`, exact: true });
      await category.click();
      await expect(drawer.getByText(/当前结果/)).toHaveCount(0);
      await expect(drawer.getByText('正在加载异常关系…', { exact: true })).toHaveCount(0);
      expect(await drawer.locator('.workbench-anomaly-drawer__group').count()).toBe(Math.min(counts.by_code[code], 10));
    }
    await drawer.getByRole('radio', { name: `仅资料异常 ${counts.document_only}组`, exact: true }).click();
    await expect(drawer.getByText(/当前结果/)).toHaveCount(0);
    await expect(drawer.getByText('正在加载异常关系…', { exact: true })).toHaveCount(0);
    await drawer.getByRole('radio', { name: `金额异常 ${counts.amount_total}组`, exact: true }).click();
    await expect(drawer.getByText('正在加载异常关系…', { exact: true })).toHaveCount(0);
    await expect(drawer.locator('.workbench-anomaly-drawer__filters')).not.toContainText(/OA \d+条|流水 \d+笔|发票 \d+张/);
    if (counts.amount_total > 0) {
      const detail = page.waitForResponse(response => new URL(response.url()).pathname === '/fin-ops-api/api/workbench/groups/detail');
      await drawer.getByRole('button', { name: '展开异常明细', exact: true }).first().click();
      expect((await detail).status()).toBe(200);
      await expect(drawer.locator('.workbench-anomaly-drawer__detail-grid')).toBeVisible();
      await expect(drawer.locator('.detail-state-panel.error')).toHaveCount(0);
      await page.setViewportSize({ width: 1440, height: 600 });
      const scroller = drawer.locator('.workbench-anomaly-drawer__content');
      await expect.poll(() => scroller.evaluate(node => node.scrollHeight - node.clientHeight)).toBeGreaterThan(0);
      await scroller.hover(); await page.mouse.wheel(0, 12000);
      await expect.poll(() => scroller.evaluate(node => Math.abs(node.scrollHeight - node.clientHeight - node.scrollTop))).toBeLessThanOrEqual(2);
      await page.screenshot({ path: info.outputPath(`${bucket}-expanded-bottom.png`) });
      await page.mouse.wheel(0, -12000);
      await expect.poll(() => scroller.evaluate(node => node.scrollTop)).toBe(0);
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    metrics.push({ bucket, counts, pages, distinctGroups: ids.size });
  }
  await info.attach('exception-group-counts', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('exception-groups.png') });
  expect(writes).toEqual([]);
  expect(failures).toEqual([]);
});
