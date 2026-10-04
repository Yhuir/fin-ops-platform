import { expect, test } from './fixtures/strictTest';
import type { InputInvoiceUsageRowsResponse } from '../src/features/inputInvoiceUsage/types';
import { formatMoney } from '../src/features/money';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({screenshot: 'off', trace: 'off', video: 'off', viewport: {width: 1920, height: 1000}});

test('production input invoice values agree with API across details, pagination and seller filtering', async ({page}, info) => {
  test.skip(!enabled || !token, 'Requires production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax'}]);
  const writes: string[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  const nextRows = () => page.waitForResponse(response => new URL(response.url()).pathname === '/fin-ops-api/api/input-invoice-usage/rows');
  const cells = page.locator('.input-invoice-usage-table-cell--amount').filter({has: page.locator('.input-invoice-usage-tax-rate')});
  const verifyValues = async (payload: InputInvoiceUsageRowsResponse) => {
    expect(payload.rows.length).toBeGreaterThan(0);
    await expect(cells).toHaveCount(payload.rows.length);
    for (const [index, {invoice}] of payload.rows.entries()) {
      expect(invoice.taxRate).not.toBe('');
      expect(invoice.taxRate).not.toContain('（推算）');
      expect(invoice.taxRate).not.toBe('未提供');
      const cell = cells.nth(index);
      const gross = formatMoney(invoice.totalWithTax, '—');
      await expect(cell.locator('.input-invoice-usage-invoice-total')).toHaveText(gross);
      await expect(cell.locator('.input-invoice-usage-tax-rate')).toHaveText(invoice.taxRate);
      // No pretax or tax-amount child is rendered in this list cell.
      await expect(cell.locator(':scope > div')).toHaveCount(2);
      await expect(cell).toHaveText(gross + invoice.taxRate);
    }
    await expect(page.getByRole('button', {name: '刷新', exact: true})).toBeEnabled();
  };

  const initialResponse = nextRows();
  const started = Date.now();
  await page.goto('/fin-ops/input-invoice-usage');
  const initialHttp = await initialResponse;
  expect(initialHttp.status()).toBe(200);
  const initial: InputInvoiceUsageRowsResponse = await initialHttp.json();
  const grid = page.getByRole('grid', {name: '进项发票使用情况表'});
  await expect(grid.getByRole('columnheader', {name: '价税合计/税率', exact: true})).toBeVisible();
  await expect(grid.getByText('不含税/税率税额', {exact: true})).toHaveCount(0);
  await verifyValues(initial);
  const firstVisibleMs = Date.now() - started;
  for (const width of [1920, 1440]) {
    await page.setViewportSize({width, height: 1000});
    await expect(cells.first()).toHaveCSS('text-align', 'right');
    expect(await cells.first().evaluate(el => {
      const first = el.children[0], second = el.children[1];
      return second.getBoundingClientRect().top >= first.getBoundingClientRect().bottom
        && parseFloat(getComputedStyle(second).fontSize) < parseFloat(getComputedStyle(first).fontSize)
        && getComputedStyle(second).color !== getComputedStyle(first).color;
    })).toBe(true);
    await page.screenshot({path: info.outputPath(`production-input-two-lines-${width}.png`), animations: 'disabled'});
  }

  const detailResponse = page.waitForResponse(response => new URL(response.url()).pathname.startsWith('/fin-ops-api/api/input-invoice-usage/invoices/') && new URL(response.url()).pathname.endsWith('/detail'));
  await grid.getByRole('button', {name: /^查看发票 .+ 详情$/}).first().click();
  const detailHttp = await detailResponse;
  expect(detailHttp.status()).toBe(200);
  const detail = await detailHttp.json();
  const financial = detail.sections.find((section: {title: string}) => section.title === '金额与税额');
  expect(financial).toBeTruthy();
  const drawer = page.getByRole('dialog', {name: '发票详情', exact: true});
  const detailAmounts = drawer.getByLabel('金额与税额详情');
  for (const label of ['不含税金额', '税率', '税额', '价税合计']) {
    const field = financial.fields.find((candidate: {label: string}) => candidate.label === label);
    expect(field).toBeTruthy();
    await expect(detailAmounts.getByRole('row', {name: new RegExp(`^${label} `)}).getByRole('cell')).toHaveText(field.value);
    if (label === '税率') expect(field.value).not.toContain('（推算）');
  }
  await page.screenshot({path: info.outputPath('production-input-financial-detail.png'), animations: 'disabled'});
  await drawer.getByRole('button', {name: '关闭详情抽屉'}).click();

  expect(initial.pagination.total).toBeGreaterThan(initial.rows.length);
  const pageResponse = nextRows();
  await page.getByRole('button', {name: '下一页', exact: true}).click();
  const pageHttp = await pageResponse;
  expect(pageHttp.status()).toBe(200);
  expect(new URL(pageHttp.url()).searchParams.get('page')).toBe('2');
  const secondPage: InputInvoiceUsageRowsResponse = await pageHttp.json();
  expect(secondPage.pagination.page).toBe(2);
  expect(secondPage.rows.some(row => initial.rows.some(previous => previous.id === row.id))).toBe(false);
  await verifyValues(secondPage);
  await page.screenshot({path: info.outputPath('production-input-second-page.png'), animations: 'disabled'});

  const seller = initial.filterOptions.find(field => field.field === 'seller_name')?.options.find(option => (option.count ?? 0) > 0 && option.value !== '');
  expect(seller).toBeTruthy();
  await page.getByRole('button', {name: '筛选 销方名称', exact: true}).click();
  const filteredResponse = nextRows();
  await page.locator('label').filter({has: page.getByRole('checkbox', {name: `${seller!.label} ${seller!.count}`, exact: true})}).click();
  const filteredHttp = await filteredResponse;
  expect(filteredHttp.status()).toBe(200);
  expect(JSON.parse(decodeURIComponent(new URL(filteredHttp.url()).searchParams.get('filters')!))).toEqual([
    {field: 'seller_name', operator: 'in', values: [seller!.value]},
  ]);
  const filtered: InputInvoiceUsageRowsResponse = await filteredHttp.json();
  expect(filtered.pagination.page).toBe(1);
  expect(filtered.rows.every(row => row.invoice.sellerName === seller!.value)).toBe(true);
  await page.keyboard.press('Escape');
  await verifyValues(filtered);
  await page.screenshot({path: info.outputPath('production-input-seller-filtered.png'), animations: 'disabled'});
  expect(writes).toEqual([]);
  await info.attach('input-tax-values-verification', {body: JSON.stringify({firstVisibleMs, total: initial.pagination.total, pageTwoRows: secondPage.rows.length, filtered: filtered.pagination.total, writes}), contentType: 'application/json'});
});
