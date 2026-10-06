import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const states = [
  ["pending_collection", "待收款"], ["partial_collected", "部分收款"], ["collected", "已收款"],
  ["reversed_by_red", "蓝票已被红冲"], ["reverses_blue", "红票已关联蓝票"], ["unmatched_red", "红票未关联蓝票"],
] as const;

test("tax menu and grouped totals stay aligned with invoice and bank columns", async ({page}, info) => {
  const api = await installDeterministicApiMocks(page,{sessionMode:"user",outputInvoiceCollectionListInteractions:true});
  await page.goto('/output-invoice-collections');
  const totals = page.getByLabel('当前筛选合计');
  await expect(totals).toContainText('含税金额合计 1020032.00');
  await expect(totals).toContainText('不含税金额合计 962294.34');
  await expect(page.getByText('税额/税率',{exact:true})).toHaveCount(0);
  for (const width of [1920,1440,960]) {
    await page.setViewportSize({width,height:1000});
    const statusHeader = await page.locator('.output-invoice-collections-col-collectionStatus').boundingBox();
    const statusGroup = await page.locator('.output-invoice-collections-group-header').nth(1).boundingBox();
    const bankHeader = await page.locator('.output-invoice-collections-col-bankCounterparty').boundingBox();
    const bankGroup = await page.locator('.output-invoice-collections-group-header').nth(2).boundingBox();
    expect(Math.abs(statusHeader!.x-statusGroup!.x)).toBeLessThan(3);
    expect(Math.abs(bankHeader!.x-bankGroup!.x)).toBeLessThan(3);
    for (const label of await totals.locator('span[title]').all()) {
      expect(await label.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    }
    await page.screenshot({path:info.outputPath(`output-totals-${width}.png`),animations:'disabled'});
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'筛选 税率',exact:true}).click();
  const changed = page.waitForResponse(r=>new URL(r.url()).pathname==='/api/output-invoice-collections/rows');
  await page.locator('label').filter({has:page.getByRole('checkbox',{name:/6%/})}).click();
  expect(JSON.parse(decodeURIComponent(new URL((await changed).url()).searchParams.get('filters')!))).toEqual([{field:'tax_rate',operator:'in',values:['6%']}]);
  await expect(page.getByRole('checkbox',{name:/6%/})).toBeChecked();
  await page.screenshot({path:info.outputPath('output-tax-menu.png'),animations:'disabled'});
  await page.keyboard.press('Escape');
  const preview = page.waitForResponse(r=>new URL(r.url()).pathname==='/api/output-invoice-collections/export-summary');
  await page.getByRole('button',{name:'筛选内容导出'}).click();
  expect(decodeURIComponent(new URL((await preview).url()).searchParams.get('filters')!)).toContain('tax_rate');
  expect(api.count('GET /api/output-invoice-collections/filter-options')).toBe(0);
});

test("all status tabs use invoice counts, one query, and the same export filters", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user", outputInvoiceCollectionListInteractions: true });
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  const response = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/rows");
  await page.goto("/output-invoice-collections");
  const initial = await (await response).json();
  const scopeCount = initial.pagination.total;
  const tabs = page.getByRole("region", { name: "销项发票分类" });
  await expect(tabs.getByRole("button", { name: `全部销项发票 ${scopeCount} 张` })).toBeVisible();
  for (const [code, label] of states) {
    const count = initial.filter_options.find((f: {field:string}) => f.field === "collection_status").options.find((o: {value:string}) => o.value === code).count;
    const requestsBefore = api.count("GET /api/output-invoice-collections/rows");
    const next = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/rows");
    await tabs.getByRole("button", { name: `${label} ${count} 张` }).click();
    const result = await next;
    const payload = await result.json();
    expect(result.status()).toBe(200);
    expect(payload.pagination.total).toBe(count);
    expect(payload.rows.every((row: {collection_status:{code:string}}) => row.collection_status.code === code)).toBe(true);
    if (code === 'pending_collection') {
      // This fixture has no pending invoices; the renamed filter must retain the empty result.
      expect(count).toBe(0);
      await expect(page.locator('.output-invoice-collections-table-cell--status')).toHaveCount(0);
      await expect(page.locator('.output-invoice-collections-group-header').nth(1)).toHaveText('收款状态');
      await page.screenshot({ path: info.outputPath('pending-collection-label.png'), animations: 'disabled' });
    }
    await expect(tabs.getByRole("button", { name: `${label} ${count} 张` })).toHaveAttribute("aria-pressed", "true");
    await expect(tabs.getByRole("button", { name: `全部销项发票 ${scopeCount} 张` })).toBeVisible();
    expect(api.count("GET /api/output-invoice-collections/rows") - requestsBefore).toBe(1);
  }
  await tabs.getByRole("button", { name: /全部/ }).click();
  await expect(tabs.getByRole("button", { name: `全部销项发票 ${scopeCount} 张` })).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 1600, height: 1000 });
  expect(await tabs.evaluate(el => el.scrollWidth <= el.parentElement!.clientWidth + 1)).toBe(true);
  await expect(tabs.getByRole('button', { pressed: true })).toHaveCount(1);
  await expect(tabs.getByRole('button', { pressed: true })).toHaveCSS('background-color', 'rgb(41, 63, 93)');
  await page.screenshot({ path: info.outputPath("output-status-tabs-wide.png"), animations: "disabled" });
  await page.setViewportSize({ width: 960, height: 900 });
  await page.screenshot({ path: info.outputPath("output-status-tabs-narrow.png"), animations: "disabled" });
  const toolbar = page.locator(".output-invoice-collections-query");
  expect(await toolbar.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await tabs.getByRole("button", { name: /蓝票已被红冲/ }).click();
  await expect(tabs.getByRole("button", { name: /蓝票已被红冲/ })).toHaveAttribute("aria-pressed", "true");
  const previewResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/export-summary");
  await page.getByRole("button", { name: "筛选内容导出" }).click();
  const previewUrl = new URL((await previewResponse).url());
  expect(JSON.parse(decodeURIComponent(previewUrl.searchParams.get("filters")!))).toEqual([{field:"collection_status",operator:"in",values:["reversed_by_red"]}]);
  expect(api.count("GET /api/output-invoice-collections/filter-options")).toBe(0);
  expect(api.calls.some(call => /^(POST|PUT|PATCH|DELETE) /.test(call))).toBe(false);
  expect(errors).toEqual([]);
});

test("all seven statuses fit without scrolling at desktop, narrow and scaled widths", async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", outputInvoiceCollectionListInteractions: true });
  await page.goto('/output-invoice-collections');
  const tabs = page.getByRole('region', { name: '销项发票分类' });
  await expect(tabs.getByRole('button')).toHaveCount(9);
  for (const width of [1920, 1440, 1280, 960]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const collapsed of [false, true]) {
      if (collapsed) await page.getByRole('button', { name: '折叠菜单', exact: true }).click();
      const geometry = await tabs.evaluate(el => ({
        width: el.clientWidth, scroll: el.scrollWidth, wrap: getComputedStyle(el).flexWrap,
      }));
      expect(geometry.scroll, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.width + 1);
      for (const tab of await tabs.getByRole('button').all()) {
        await expect(tab).toBeInViewport({ ratio: 1 });
        expect(await tab.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
        expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(32);
      }
      await expect(page.getByRole('search').getByRole('button', { name: '查询', exact: true })).toBeInViewport();
      const tabBox = (await tabs.boundingBox())!;
      const pickerBox = (await page.locator('.output-invoice-collections-query .business-period-picker').boundingBox())!;
      if (pickerBox.y < tabBox.y + tabBox.height) expect(pickerBox.x - tabBox.x - tabBox.width).toBeGreaterThanOrEqual(8);

      await page.screenshot({ path: info.outputPath(`statuses-${width}-${collapsed ? 'collapsed' : 'expanded'}.png`), animations: 'disabled' });
      if (collapsed) await page.getByRole('button', { name: '展开菜单', exact: true }).click();
    }
  }
  // CSS zoom exercises layout at 125%, rather than only changing screenshot pixel density.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('body').evaluate(el => { el.style.zoom = '1.25'; });
  expect(await tabs.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  for (const tab of await tabs.getByRole('button').all()) await expect(tab).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: info.outputPath('statuses-125-percent.png'), animations: 'disabled' });
  await tabs.getByRole('button', { name: /^全部销项发票 / }).focus();
  for (let index = 0; index < 8; index++) await page.keyboard.press('Tab');
  await expect(tabs.getByRole('button', { name: /^红票未关联蓝票 / })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(tabs.getByRole('button', { name: /^红票未关联蓝票 / })).toHaveAttribute('aria-pressed', 'true');
});
