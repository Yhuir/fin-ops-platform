import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1920, height: 1000 } });

test('production cost explorer verifies five identity filters, stable pagination and layouts without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(300_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: number[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => { if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(response.status()); });
  const read = async (params: Record<string, string>) => {
    const response = await page.request.get(`/fin-ops-api/api/cost-statistics/explorer?${new URLSearchParams(params)}`);
    expect(response.status()).toBe(200); return response.json();
  };
  const waitDetail = () => page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/cost-statistics/explorer') && url.searchParams.get('include_statistics') === 'false';
  });
  await page.goto('/fin-ops/cost-statistics');
  await expect(page.getByRole('heading', { name: '成本', exact: true })).toBeVisible();
  const metrics: object[] = [];
  for (const [view, label] of [['project', '按项目'], ['cost_tag', '按成本标签'], ['bank_account', '按银行账户'], ['bank_tag', '按标签'], ['time', '按时间']]) {
    await page.getByRole('radio', { name: label, exact: true }).click();
    const q: Record<string, string> = { view, scope: 'all', page_size: '200', include_statistics: 'false' };
    let payload = await read(q);
    const choose = async (title: string, field: string, value: string) => {
      q[field] = value;
      await page.getByRole('option', { name: `选择${title} ${value}`, exact: true }).click();
      payload = await read(q);
    };
    if (view === 'bank_account') {
      const account = [...payload.facets.bank_accounts].sort((a, b) => Number(b.total_amount) - Number(a.total_amount))[0];
      q.bank_account_label = account.bank_account_label;
      await page.getByRole('option', { name: `选择银行账户 ${account.bank_account_display_label}`, exact: true }).click();
      payload = await read(q);
    }
    if (view === 'project' || view === 'bank_account') await choose('项目名', 'project_name', payload.facets.projects[0].project_name);
    if (['project', 'cost_tag', 'bank_account'].includes(view)) {
      const main = payload.facets.cost_tag_primary[0];
      q.bank_tag_primary_key = main.key;
      await page.getByRole('option', { name: `选择成本主标签 ${main.label}`, exact: true }).click(); payload = await read(q);
      const sub = payload.facets.cost_tag_sub[0]; q.bank_tag_sub_key = sub.key;
      await page.getByRole('option', { name: `选择成本子标签 ${sub.label}`, exact: true }).click(); payload = await read(q);
    }
    if (view === 'bank_tag') {
      await choose('主标签', 'bank_tag_primary_label', payload.facets.bank_tag_primary[0].primary_label);
      await choose('子标签', 'bank_tag_sub_label', payload.facets.bank_tag_sub[0].sub_label);
    }
    const scopeSummary = payload.summary;
    const allRows = [...payload.rows];
    let cursor = payload.next_cursor;
    while (cursor) {
      const next = await read({ ...q, cursor }); allRows.push(...next.rows); cursor = next.next_cursor;
      expect(allRows.length).toBeLessThanOrEqual(payload.row_count);
    }
    expect(allRows.length).toBe(payload.row_count);
    expect(new Set(allRows.map(row => row.entry_id)).size).toBe(allRows.length);
    const bank = view === 'bank_tag' || view === 'time';
    const identity = bank ? '对方户名' : '申请人';
    const field = bank ? 'counterparty_name' : 'oa_applicant';
    expect(payload.identity_options).toEqual([...new Set<string>(allRows.map(row => String(row[field] || '')))].sort());
    const grid = page.getByRole('grid', { name: bank ? `${label}银行流水表` : '成本明细表' });
    await expect(grid.locator('.cost-entry-time').first()).toBeVisible();
    const candidates: string[] = payload.identity_options;
    expect(candidates.length).toBeGreaterThan(0);
    const selected = candidates.slice(0, 2);
    await grid.getByRole('button', { name: `筛选${identity}`, exact: true }).click();
    const menu = page.getByRole('dialog', { name: `筛选${identity}`, exact: true });
    for (const name of selected) {
      await menu.getByText(name || '未填写', { exact: true }).click();
      await expect(menu.getByRole('checkbox', { name: name || '未填写', exact: true })).toBeChecked();
    }
    let pending = waitDetail();
    await menu.getByRole('button', { name: '应用', exact: true }).click();
    let result = await (await pending).json();
    const expectedRows = allRows.filter(row => selected.includes(String(row[field] || '')));
    expect(result.row_count).toBe(expectedRows.length);
    expect(result.summary).toEqual(scopeSummary);
    expect(result.identity_options).toEqual(candidates);
    await expect(grid.getByRole('button', { name: `筛选${identity}，已选${selected.length}项`, exact: true })).toBeVisible();
    pending = waitDetail();
    await grid.getByRole('button', { name: '时间倒序，点击切换正序', exact: true }).click();
    result = await (await pending).json();
    const asc = [...result.rows]; cursor = result.next_cursor;
    while (cursor) {
      const next = await read({ ...q, page_size: '20', sort_order: 'asc', identity_names: JSON.stringify(selected), cursor });
      asc.push(...next.rows); cursor = next.next_cursor;
      expect(asc.length).toBeLessThanOrEqual(result.row_count);
    }
    expect(asc.map(row => row.entry_id).sort()).toEqual(expectedRows.map(row => row.entry_id).sort());
    const dated = asc.filter(row => row.occurred_at).map(row => row.occurred_at);
    expect(dated).toEqual([...dated].sort());
    const firstMissing = asc.findIndex(row => !row.occurred_at);
    if (firstMissing >= 0) expect(asc.slice(firstMissing).every(row => !row.occurred_at)).toBe(true);
    await expect(grid.locator('.cost-entry-time').first()).toBeVisible();
    if (await page.getByRole('button', { name: '下一页', exact: true }).isEnabled()) {
      pending = waitDetail(); await page.getByRole('button', { name: '下一页', exact: true }).click();
      const next = await (await pending).json();
      expect(next.rows.map((row: { entry_id: string }) => row.entry_id)).toEqual(asc.slice(20, 40).map(row => row.entry_id));
    }
    await grid.getByRole('button', { name: `筛选${identity}，已选${selected.length}项`, exact: true }).click();
    await menu.getByRole('button', { name: '清空', exact: true }).click();
    pending = waitDetail(); await menu.getByRole('button', { name: '应用', exact: true }).click();
    result = await (await pending).json(); expect(result.row_count).toBe(allRows.length);
    await expect(grid.locator('.cost-entry-time').first()).toBeVisible();
    await page.screenshot({ path: info.outputPath(`${view}-desktop.png`) });
    await page.setViewportSize({ width: 1024, height: 600 });
    await grid.getByRole('button', { name: `筛选${identity}`, exact: true }).click();
    const bounds = (await menu.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(1024);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(600);
    await expect(menu.getByRole('button', { name: '清空', exact: true })).toBeInViewport({ ratio: 1 });
    await expect(menu.getByRole('button', { name: '应用', exact: true })).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: info.outputPath(`${view}-compact-menu.png`), animations: 'disabled' });
    await menu.getByRole('button', { name: '清空', exact: true }).click();
    await menu.getByRole('button', { name: '应用', exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.setViewportSize({ width: 1920, height: 1000 });
    metrics.push({ view, total: allRows.length, candidateCount: candidates.length, filtered: expectedRows.length, ascendingRows: asc.length });
  }
  expect(writes).toEqual([]); expect(failures).toEqual([]);
  await info.attach('production-cost-explorer', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
});
