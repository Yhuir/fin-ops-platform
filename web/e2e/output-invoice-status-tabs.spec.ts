import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const states = [
  ["pending_collection", "收款待核对"], ["partial_collected", "部分收款"], ["collected", "已收款"],
  ["reversed_by_red", "蓝票已被红冲"], ["reverses_blue", "红票已关联蓝票"], ["unmatched_red", "红票待核对"],
] as const;

test("all status tabs use invoice counts, one query, and the same export filters", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user", outputInvoiceCollectionListInteractions: true });
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  const response = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/rows");
  await page.goto("/output-invoice-collections");
  const initial = await (await response).json();
  const scopeCount = initial.pagination.total;
  const tabs = page.getByRole("tablist", { name: "销项发票状态分类" });
  await expect(tabs.getByRole("tab", { name: `全部 ${scopeCount} 张` })).toBeVisible();
  for (const [code, label] of states) {
    const count = initial.filter_options.find((f: {field:string}) => f.field === "collection_status").options.find((o: {value:string}) => o.value === code).count;
    const requestsBefore = api.count("GET /api/output-invoice-collections/rows");
    const next = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/rows");
    await tabs.getByRole("tab", { name: `${label} ${count} 张` }).click();
    const result = await next;
    const payload = await result.json();
    expect(result.status()).toBe(200);
    expect(payload.pagination.total).toBe(count);
    expect(payload.rows.every((row: {collection_status:{code:string}}) => row.collection_status.code === code)).toBe(true);
    await expect(tabs.getByRole("tab", { name: `${label} ${count} 张` })).toHaveAttribute("aria-selected", "true");
    await expect(tabs.getByRole("tab", { name: `全部 ${scopeCount} 张` })).toBeVisible();
    expect(api.count("GET /api/output-invoice-collections/rows") - requestsBefore).toBe(1);
  }
  await tabs.getByRole("tab", { name: /全部/ }).click();
  await expect(tabs.getByRole("tab", { name: `全部 ${scopeCount} 张` })).toHaveAttribute("aria-selected", "true");
  await page.setViewportSize({ width: 1600, height: 1000 });
  expect(await tabs.evaluate(el => el.scrollWidth <= el.parentElement!.clientWidth + 1)).toBe(true);
  await expect(tabs.locator('[data-slot="tabs-indicator"]')).toHaveCount(1);
  await page.screenshot({ path: info.outputPath("output-status-tabs-wide.png"), animations: "disabled" });
  await page.setViewportSize({ width: 960, height: 900 });
  await page.screenshot({ path: info.outputPath("output-status-tabs-narrow.png"), animations: "disabled" });
  const toolbar = page.locator(".output-invoice-collections-query");
  expect(await toolbar.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await tabs.getByRole("tab", { name: /蓝票已被红冲/ }).click();
  await expect(tabs.getByRole("tab", { name: /蓝票已被红冲/ })).toHaveAttribute("aria-selected", "true");
  const previewResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/output-invoice-collections/export-preview");
  await page.getByRole("button", { name: "筛选内容导出" }).click();
  const previewUrl = new URL((await previewResponse).url());
  expect(JSON.parse(decodeURIComponent(previewUrl.searchParams.get("filters")!))).toEqual([{field:"collection_status",operator:"in",values:["reversed_by_red"]}]);
  expect(api.count("GET /api/output-invoice-collections/filter-options")).toBe(0);
  expect(api.calls.some(call => /^(POST|PUT|PATCH|DELETE) /.test(call))).toBe(false);
  expect(errors).toEqual([]);
});
