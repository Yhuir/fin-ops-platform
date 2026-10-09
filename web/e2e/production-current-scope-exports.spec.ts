import { resolve } from 'node:path';
import { expect, test, type Page } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 1000 } });

const scopes: Array<{ module: string; region?: string; group?: string; category: RegExp; button: string; title: string; unit: string }> = [
  { module: 'oa-pending-payments', region: 'OA 核对分类', category: /^进行中 OA \d+ 条$/, button: '导出 OA', title: '导出 OA', unit: '条 OA' },
  { module: 'pending-invoices', region: '待找发票分类', group: '支出流水', category: /^无需发票 \d+ 笔$/, button: '筛选内容导出', title: '导出待找发票', unit: '笔流水' },
  { module: 'input-invoice-usage', region: '进项发票使用分类', category: /^已使用 \d+ 张$/, button: '筛选内容导出', title: '导出进项发票', unit: '张进项发票' },
  { module: 'output-invoice-collections', region: '销项发票分类', category: /^待收款 \d+ 张$/, button: '筛选内容导出', title: '导出销项发票', unit: '张销项发票' },
  { module: 'turnover-ledger', category: /^个人 \d+$/, button: '下载表格', title: '下载往来款台账', unit: '个往来对象' },
];

function rowsResponse(page: Page, module: string) {
  const pathname = `/fin-ops-api/api/${module}${module === 'turnover-ledger' ? '' : '/rows'}`;
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === pathname && url.searchParams.get('include_statistics') !== 'true';
  });
}

// Pagination and statistics affect presentation only. All effective scope/sort parameters must survive export.
function exportConditions(url: string) {
  const query = new URL(url).searchParams;
  for (const key of ['page', 'page_size', 'include_statistics', 'view']) query.delete(key);
  return Object.fromEntries([...query.entries()].filter(([, value]) => value !== '').sort());
}

for (const scope of scopes) {
  test(`production ${scope.module} exports the current category across pages`, async ({ page }, info) => {
    test.skip(!enabled || !token, 'Requires explicit production verification and the local admin token.');
    test.setTimeout(90_000);
    await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
    const writes: string[] = [];
    await page.route('**/fin-ops-api/**', async route => {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
        writes.push(new URL(route.request().url()).pathname);
        await route.abort('blockedbyclient');
      } else await route.continue();
    });

    const initial = rowsResponse(page, scope.module);
    await page.goto(`/fin-ops/${scope.module}`);
    expect((await initial).status()).toBe(200);
    const region = scope.region ? page.getByRole('region', { name: scope.region, exact: true }) : page.getByLabel('往来款账单范围');
    const categoryRegion = scope.group ? region.getByRole('group', { name: scope.group, exact: true }) : region;
    const selected = rowsResponse(page, scope.module);
    await categoryRegion.getByRole('button', { name: scope.category }).click();
    const rows = await selected;
    expect(rows.status()).toBe(200);
    const payload = await rows.json();
    const count: number = scope.module === 'oa-pending-payments' ? payload.summary.oaCount
      : scope.module === 'pending-invoices' ? payload.acquisition_summary.bank_count
        : scope.module === 'turnover-ledger' ? payload.pagination.total : payload.summary.invoiceCount;
    expect(count).toBeGreaterThan(0);

    const summaryRequest = page.waitForResponse(response => new URL(response.url()).pathname === `/fin-ops-api/api/${scope.module}/export-summary`);
    await page.getByRole('button', { name: scope.button, exact: true }).click();
    const summary = await summaryRequest;
    expect(summary.status()).toBe(200);
    expect(await summary.json()).toEqual({ row_count: count });
    expect(exportConditions(summary.url())).toEqual(exportConditions(rows.url()));
    const drawer = page.getByRole('dialog', { name: scope.title, exact: true });
    await expect(drawer).toContainText(`即将导出 ${count.toLocaleString()} ${scope.unit}`);
    await expect(drawer.getByRole('checkbox')).toHaveCount(0);
    await expect(drawer.getByRole('combobox')).toHaveCount(0);
    await expect(drawer.getByRole('textbox')).toHaveCount(0);
    await expect(drawer.getByRole('table')).toHaveCount(0);
    await expect(drawer.getByRole('button', { name: '导出', exact: true })).toHaveCount(1);
    await expect(drawer.getByRole('button')).toHaveCount(2); // One export action plus the drawer close control.
    await page.screenshot({ path: resolve(process.cwd(), '..', 'outputs', 'export-scope', `production-${scope.module}.png`), animations: 'disabled' });

    const downloadEvent = page.waitForEvent('download');
    const fileResponse = page.waitForResponse(response => new URL(response.url()).pathname === `/fin-ops-api/api/${scope.module}/export`);
    await drawer.getByRole('button', { name: '导出', exact: true }).click();
    const file = await fileResponse;
    expect(file.status()).toBe(200);
    expect(file.headers()['x-export-count']).toBe(String(count));
    expect(exportConditions(file.url())).toEqual(exportConditions(rows.url()));
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
    expect(await download.failure()).toBeNull();
    await expect(drawer).toContainText(`已导出 ${count.toLocaleString()} ${scope.unit}`);
    await drawer.getByRole('button', { name: `关闭${scope.title}`, exact: true }).click();
    await expect(drawer).toHaveCount(0);
    expect(writes).toEqual([]);
    await info.attach('current-scope-export', { body: JSON.stringify({ module: scope.module, count, queryPreserved: true, downloadCountMatches: true, writes }), contentType: 'application/json' });
  });
}
