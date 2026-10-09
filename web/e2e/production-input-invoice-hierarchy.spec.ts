import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const rowsPath = '/fin-ops-api/api/input-invoice-usage/rows';
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production hierarchy preserves counts and search without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const errors: string[] = [];
  const writes: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  const first = page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
  await page.goto('/fin-ops/input-invoice-usage');
  const initial = await (await first).json();
  const panel = page.getByRole('region', { name: '进项发票使用分类' });
  await expect(panel).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByRole('button', { name: /使用状态/ })).toHaveCount(0);
  for (const width of [1920, 1440, 1024]) {
    await page.setViewportSize({ width, height: 1100 });
    const used = await panel.getByRole('group', { name: '已使用', exact: true }).boundingBox();
    const unused = await panel.getByRole('button', { name: /^待使用/ }).boundingBox();
    expect(Math.abs(unused!.y - used!.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(unused!.height - used!.height)).toBeLessThanOrEqual(1);
    expect(unused!.x).toBeGreaterThanOrEqual(used!.x + used!.width - 1);
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`production-hierarchy-${width}.png`), animations: 'disabled' });
  }
  const evidence: Record<string, unknown> = { classification: initial.classification };
  for (const [id, label] of [['used', '已使用'], ['unused', '待使用']] as const) {
    const response = page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
    await panel.getByRole('button', { name: new RegExp(`^${label}`) }).click();
    const selected = await response;
    expect(selected.status()).toBe(200);
    const payload = await selected.json();
    expect(payload.classification).toEqual(initial.classification);
    expect(payload.summary.invoiceCount).toBe(initial.classification[id].count);
    expect(JSON.parse(decodeURIComponent(new URL(selected.url()).searchParams.get('filters')!))).toEqual([{ field: 'usage_status', operator: 'in', values: [id] }]);
    await expect(panel.getByRole('button', { name: new RegExp(`^${label}`) })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByLabel('当前筛选发票汇总')).toContainText(`${payload.summary.invoiceCount} 张`);
    evidence[id] = payload.summary;
  }
  const reset = page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
  await panel.getByRole('button', { name: /^全部发票/ }).click();
  expect((await reset).status()).toBe(200);
  await page.getByRole('searchbox').fill('2986');
  const search = page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
  await page.getByRole('button', { name: '查询', exact: true }).click();
  const searched = await (await search).json();
  evidence.search2986 = { classification: searched.classification, summary: searched.summary };
  for (const label of ['已使用', '待使用']) {
    const response = page.waitForResponse(response => new URL(response.url()).pathname === rowsPath);
    await panel.getByRole('button', { name: new RegExp(`^${label}`) }).click();
    const selected = await response;
    expect(selected.status()).toBe(200);
    expect(new URL(selected.url()).searchParams.get('keyword')).toBe('2986');
    const payload = await selected.json();
    expect(payload.classification).toEqual(searched.classification);
    evidence[`search2986-${label}`] = payload.summary;
  }
  expect(errors).toEqual([]);
  expect(writes).toEqual([]);
  await info.attach('production-hierarchy-readonly', { body: JSON.stringify(evidence), contentType: 'application/json' });
});
