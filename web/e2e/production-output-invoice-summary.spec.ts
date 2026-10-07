import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot:'off', trace:'off', video:'off', viewport:{width:1600,height:1000} });

test('production output tax filters, totals, details and export remain consistent', async ({page},info) => {
  test.skip(!enabled || !token, 'Requires production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{name:'Admin-Token',value:token!,domain:'www.yn-sourcing.com',path:'/',secure:true,sameSite:'Lax'}]);
  const writes:string[] = [];
  await page.route('**/fin-ops-api/**',async route=>{
    if (!['GET','HEAD','OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
    } else await route.continue();
  });
  const rowsResponse = () => page.waitForResponse(response => new URL(response.url()).pathname === '/fin-ops-api/api/output-invoice-collections/rows');
  const first = rowsResponse();
  const started = Date.now();
  await page.goto('/fin-ops/output-invoice-collections');
  const payload = await (await first).json();
  const totals = page.getByLabel('当前筛选合计');
  await expect(totals).toContainText(`含税金额合计 ${payload.summary.totalWithTax}`);
  await expect(totals).toContainText(`不含税金额合计 ${payload.summary.amountWithoutTax}`);
  await expect(totals).toContainText(`收入合计 ${payload.summary.collectedAmount}`);
  const firstVisibleMs = Date.now()-started;
  await expect(page.getByRole('button',{name:/红票未关联蓝票/})).toBeVisible();
  const statusOptions = payload.filterOptions.find((item:{field:string})=>item.field==='collection_status').options;
  const pendingOption = statusOptions.find((item:{value:string})=>item.value==='pending_collection');
  expect(pendingOption.label).toBe('待收款');
  const pendingResponse = rowsResponse();
  await page.getByRole('button',{name:`待收款 ${pendingOption.count} 张`,exact:true}).click();
  const pendingHttp = await pendingResponse;
  expect(JSON.parse(decodeURIComponent(new URL(pendingHttp.url()).searchParams.get('filters')!))).toEqual([
    {field:'collection_status',operator:'in',values:['pending_collection']},
  ]);
  const pending = await pendingHttp.json();
  expect(pending.pagination.total).toBe(pendingOption.count);
  const statusCells = page.locator('.output-invoice-collections-table-cell--status');
  await expect(statusCells).toHaveCount(pending.rows.length);
  for (const [index,row] of pending.rows.entries()) {
    expect(row.collectionStatus.code).toBe('pending_collection');
    expect(row.collectionStatus.label).toBe('待收款');
    expect(Number(row.collectionStatus.collectedAmount)).toBe(0);
    expect(Number(row.collectionStatus.pendingAmount)).toBe(Math.abs(Number(row.invoice.totalWithTax)));
    await expect(statusCells.nth(index).getByText('待收款',{exact:true})).toBeVisible();
    await expect(statusCells.nth(index)).toContainText(`已收 ${row.collectionStatus.collectedAmount}`);
    await expect(statusCells.nth(index)).toContainText(`待收 ${row.collectionStatus.pendingAmount}`);
  }
  await expect(page.locator('.output-invoice-collections-group-header').nth(1)).toHaveText('收款状态');
  await page.screenshot({path:info.outputPath('production-pending-collection.png'),animations:'disabled'});
  const allResponse = rowsResponse();
  await page.getByRole('button',{name:/^全部销项发票 \d+ 张$/}).click();
  await allResponse;
  for (const width of [1920,1440,960]) {
    await page.setViewportSize({width,height:1000});
    const group = await page.locator('.output-invoice-collections-group-header').nth(1).boundingBox();
    const header = await page.locator('.output-invoice-collections-col-collectionStatus').boundingBox();
    expect(Math.abs(group!.x-header!.x)).toBeLessThan(3);
    await page.screenshot({path:info.outputPath(`production-output-${width}.png`),animations:'disabled'});
  }
  await page.setViewportSize({width:1600,height:1000});
  const rates = payload.filterOptions.find((item:{field:string})=>item.field==='tax_rate').options;
  expect(rates.some((item:{value:string})=>/^0\.\d+$/.test(item.value))).toBe(false);
  expect(rates.some((item:{value:string})=>item.value.includes('（推算）'))).toBe(false);
  const selected = rates.find((item:{value:string})=>item.value==='13%');
  expect(selected).toBeTruthy();
  await page.getByRole('button',{name:'筛选 税率',exact:true}).click();
  const filteredResponse = rowsResponse();
  const filterStarted = Date.now();
  await page.locator('label').filter({has:page.getByRole('checkbox',{name:`${selected.label} ${selected.count}`,exact:true})}).click();
  const filtered = await (await filteredResponse).json();
  await expect(totals).toContainText(`含税金额合计 ${filtered.summary.totalWithTax}`);
  const filterVisibleMs = Date.now()-filterStarted;
  expect(filtered.pagination.total).toBe(selected.count);
  expect(filtered.rows.every((row:{invoice:{taxRate:string}})=>row.invoice.taxRate===selected.value)).toBe(true);
  expect(filtered.filterOptions.find((item:{field:string})=>item.field==='tax_rate').options).toEqual(rates);
  await page.screenshot({path:info.outputPath('production-tax-menu.png'),animations:'disabled'});
  await page.keyboard.press('Escape');
  const preview = page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/output-invoice-collections/export-summary'));
  await page.getByRole('button',{name:'筛选内容导出'}).click();
  expect((await (await preview).json()).row_count).toBe(filtered.pagination.total);
  const download = page.waitForEvent('download');
  await page.getByRole('button',{name:'下载 Excel',exact:true}).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  await page.getByRole('button',{name:'关闭导出销项发票',exact:true}).click();
  const detail = page.waitForResponse(response=>new URL(response.url()).pathname.includes('/output-invoice-collections/invoices/') && response.url().endsWith('/detail'));
  await page.locator('.output-invoice-collections-table-cell').getByRole('button',{name:/详情/}).first().click();
  expect((await detail).status()).toBe(200);
  await expect(page.getByRole('dialog').getByLabel('金额与税额详情').getByRole('rowheader',{name:'税额',exact:true})).toBeVisible();
  expect(writes).toEqual([]);
  await info.attach('output-summary-verification',{body:JSON.stringify({firstVisibleMs,filterVisibleMs,total:payload.pagination.total,filtered:filtered.pagination.total,summary:payload.summary,writes}),contentType:'application/json'});
});


test('production source tax rate remains consistent across rows, filters, source detail and export', async ({page}, info) => {
  test.skip(!enabled || !token, 'Requires production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{name:'Admin-Token',value:token!,domain:'www.yn-sourcing.com',path:'/',secure:true,sameSite:'Lax'}]);
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET','HEAD','OPTIONS'].includes(route.request().method())) throw new Error('Production verification must remain read-only');
    await route.continue();
  });
  await page.setViewportSize({width:1600,height:1000});
  const first = page.waitForResponse(r => new URL(r.url()).pathname === '/fin-ops-api/api/output-invoice-collections/rows');
  await page.goto('/fin-ops/output-invoice-collections');
  const payload = await (await first).json();
  const sample = payload.rows.find((r:{invoice:{invoiceNo:string; digitalInvoiceNo:string}})=>[r.invoice.invoiceNo,r.invoice.digitalInvoiceNo].includes('26532000001691977231'));
  expect(sample.invoice.taxRate).toBe('13%');
  expect(sample.invoice.totalWithTax).toBe('2129682.59');
  await expect(page.getByText('13%',{exact:true}).first()).toBeVisible();
  await page.screenshot({path:info.outputPath('production-source-rate-list.png'),animations:'disabled'});
  await page.getByRole('button',{name:'查看发票 26532000001691977231 详情',exact:true}).click();
  const drawer = page.getByRole('dialog',{name:'发票详情',exact:true});
  await expect(drawer.getByRole('cell',{name:'13%',exact:true}).first()).toBeVisible();
  await expect(drawer.getByRole('cell',{name:'1884674.86',exact:true}).first()).toBeVisible();
  await page.screenshot({path:info.outputPath('production-source-rate-detail.png'),animations:'disabled'});
  await drawer.getByRole('button',{name:'关闭详情抽屉'}).click();
  const option = payload.filterOptions.find((f:{field:string})=>f.field==='tax_rate').options.find((o:{value:string})=>o.value==='13%');
  await page.getByRole('button',{name:'筛选 税率',exact:true}).click();
  const selected = page.waitForResponse(r=>new URL(r.url()).pathname==='/fin-ops-api/api/output-invoice-collections/rows');
  await page.locator('label').filter({has:page.getByRole('checkbox',{name:`${option.label} ${option.count}`,exact:true})}).click();
  const filtered = await (await selected).json();
  expect(filtered.pagination.total).toBe(option.count);
  for (const row of filtered.rows) expect(row.invoice.taxRate).toBe('13%');
  await page.screenshot({path:info.outputPath('production-source-rate-filter.png'),animations:'disabled'});
  await page.keyboard.press('Escape');
  const preview = page.waitForResponse(r=>new URL(r.url()).pathname==='/fin-ops-api/api/output-invoice-collections/export-summary');
  await page.getByRole('button',{name:'筛选内容导出'}).click();
  const response = await preview;
  expect(decodeURIComponent(new URL(response.url()).searchParams.get('filters')!)).toContain('13%');
  expect((await response.json()).row_count).toBe(option.count);
});
