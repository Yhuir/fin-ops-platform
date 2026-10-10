import { Buffer } from "node:buffer";
import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test.describe("special invoice certification", () => {
  test("filters, sorts, paginates and exports only chosen columns without old plan calls", async ({ page }, info) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user", taxOffsetLargeDataset: true });
    await page.goto("/tax-offset");
    await expect(page.getByRole("grid", { name: "专票认证明细" })).toBeVisible();
    await expect(page.getByLabel("未认证统计")).toContainText("92 张");
    await expect(page.getByLabel("进项发票统计", { exact: true })).toContainText("进项发票99张专票92张普票3张通行费1张其他2张");
    await page.screenshot({ animations: "disabled", path: info.outputPath("tax-certification-main.png") });
    await page.getByRole("button", { name: "下一页" }).click();
    await expect(page.getByText("显示 51-92 / 92")).toBeVisible();
    const sortResponse = page.waitForResponse(response => response.url().includes("sort_by=selection_time"));
    await page.getByRole("columnheader", { name: "勾选时间" }).click(); await sortResponse;
    await expect(page.getByText("显示 1-50 / 92")).toBeVisible();
    await page.getByRole("searchbox", { name: "搜索专票" }).fill("设备");
    await page.locator(".tax-certification-page").getByRole("button", { name: "查询", exact: true }).click();
    await expect(page.getByText("显示 1-1 / 1")).toBeVisible();
    await page.getByRole("button", { name: "导出专票清单", exact: true }).click();
    const drawer = page.getByRole("dialog", { name: "导出专票清单" });
    await expect(drawer.getByRole("checkbox", { checked: true })).toHaveCount(8);
    await page.screenshot({ animations: "disabled", path: info.outputPath("tax-certification-export.png") });
    await drawer.getByText("序号", { exact: true }).click();
    await expect(drawer.getByRole("checkbox", { name: "序号", exact: true })).not.toBeChecked();
    await drawer.getByRole("button", { name: "恢复默认" }).click();
    await expect(drawer.getByRole("checkbox", { checked: true })).toHaveCount(8);
    await drawer.getByText("序号", { exact: true }).click();
    const exportRequest = page.waitForRequest(request => request.url().endsWith("/api/tax-offset/export"));
    const download = page.waitForEvent("download"); await drawer.getByRole("button", { name: "导出专票清单" }).click();
    expect((await download).suggestedFilename()).toBe("专票清单.xlsx");
    const body = (await exportRequest).postDataJSON();
    expect(body.filters).toMatchObject({ search: "设备", sort_by: "selection_time", status: "all" });
    expect(body.filters).not.toHaveProperty("page"); expect(body.filters).not.toHaveProperty("page_size");
    expect(body.fields).not.toContain("sequence"); expect(body.fields).toHaveLength(7);
    await expect(drawer.getByRole("button", { name: "关闭抽屉" })).toBeEnabled();
    await page.keyboard.press("Escape"); await expect(drawer).toHaveCount(0);
    await expect(page.getByRole("searchbox", { name: "搜索专票" })).toHaveValue("设备");
    expect(api.count("POST /api/tax-offset/plans")).toBe(0); expect(api.count("POST /api/tax-offset/calculate")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
  test("imports certification in a native drawer and refreshes canonical status", async ({ page }, info) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    await page.goto("/tax-offset"); await expect(page.getByText("11203490")).toBeVisible();
    const inventoryBefore = await page.getByLabel("进项发票统计", { exact: true }).textContent();
    await page.locator(".tax-certification-page").getByRole("button", { name: "导入认证记录", exact: true }).click();
    const drawer = page.getByRole("dialog", { name: "导入认证记录" });
    await drawer.locator('input[type="file"]').setInputFiles({ name: "认证.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture") });
    await drawer.getByRole("button", { name: "识别", exact: true }).click();
    await expect(drawer.getByText("识别 2 条")).toBeVisible();
    await page.screenshot({ animations: "disabled", path: info.outputPath("tax-certification-import.png") });
    await drawer.getByRole("button", { name: "确认导入" }).click();
    await expect(drawer.getByRole("status").filter({ hasText: "已导入 2 条" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "关闭抽屉" })).toBeEnabled();
    await page.keyboard.press("Escape"); await expect(drawer).toHaveCount(0);
    await expect(page.getByLabel("已认证统计")).toContainText("2 张");
    await expect(page.getByLabel("进项发票统计", { exact: true })).toHaveText(inventoryBefore!);
    const row = page.getByRole("grid", { name: "专票认证明细" }).getByRole("row").filter({ hasText: "11203490" });
    await expect(row).toContainText("已认证");
    expect(api.count("POST /api/tax-offset/certified-import/confirm")).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
  test("switches independent month and status filters and keeps management available on empty data", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    await page.goto("/tax-offset"); await expect(page.getByText("11203490")).toBeVisible();
    await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
    await expect(page.locator(".tax-certification-loading")).toHaveCount(0);
    await page.getByRole("radio", { name: "已认证", exact: true }).click();
    await expect(page.getByText("暂无专票")).toBeVisible();
    await expect(page.getByLabel("未认证统计")).toContainText("0 张");
    await expect(page.getByLabel("进项发票统计", { exact: true })).toContainText("进项发票9张专票2张");
    await page.getByRole("button", { name: "勾选月份：年月" }).click();
    const picker = page.getByRole("dialog", { name: "勾选月份选择器" });
    await picker.getByRole("radio", { name: "按月", exact: true }).click();
    await picker.getByRole("button", { name: "三月", exact: true }).click();
    await expect(page.getByRole("button", { name: /勾选月份：.*3月/ })).toBeVisible();
    await expect(page.locator(".tax-certification-page").getByRole("button", { name: "导入认证记录", exact: true })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});

test("conflict correction is explicit and a failed job requires a fresh preview", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  let previews = 0; let submitted: unknown;
  await page.route("**/api/tax-offset/certified-import/preview", route => {
    previews += 1;
    const summary = { blocking_count: 0, recognized_count: 1, invalid_count: 0, ignored_count: 1, matched_invoice_count: 1, outside_invoices_count: 0, conflict_count: 1, duplicate_count: 0 };
    return route.fulfill({ json: { session: { id: `s${previews}`, imported_by: "user", file_count: 1, status: "preview_ready" }, summary,
      files: [{ id: "f1", file_name: "认证.xlsx", month: "2026-03", ...summary, rows: [{ id: "r1", unique_key: "key1", expected_version: 3, month: "2026-03", buyer_tax_no: "buyer", row_status: "recognized", match_status: "matched_invoice", dedupe_status: "conflict", digital_invoice_no: "11203490", seller_name: "设备供应商", source_file_name: "认证.xlsx", source_row_number: 4 }] }] } });
  });
  await page.route("**/api/tax-offset/certified-import/confirm", route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { status: "queued", import_job: { import_job_id: "failed-tax-job", import_type: "tax_certified_import", status: "queued", stage: "queued" } } });
  });
  await page.route("**/api/tax-offset/certified-import/jobs/failed-tax-job", route => route.fulfill({ json: { import_job: { import_job_id: "failed-tax-job", import_type: "tax_certified_import", status: "failed", stage: "failed", last_error: "认证记录已变化" } } }));
  await page.goto("/tax-offset"); await expect(page.getByText("11203490")).toBeVisible();
  await page.locator(".tax-certification-page").getByRole("button", { name: "导入认证记录", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入认证记录" });
  await drawer.locator('input[type="file"]').setInputFiles({ name: "认证.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture") });
  await drawer.getByRole("button", { name: "识别", exact: true }).click();
  await expect(drawer.getByText("非专票 1 条")).toBeVisible();
  await expect(drawer.getByRole("button", { name: "确认导入" })).toBeDisabled();
  await drawer.getByText("更正", { exact: true }).click();
  await expect(drawer.getByRole("checkbox", { name: "更正 11203490" })).toBeChecked();
  await drawer.getByRole("button", { name: "确认导入" }).click();
  await expect(drawer.getByRole("alert")).toContainText("请重新识别");
  expect(submitted).toEqual({ session_id: "s1", corrections: [{ unique_key: "key1", expected_version: 3 }] });
  await expect(drawer.getByRole("button", { name: "确认导入" })).toBeDisabled();
  await drawer.getByRole("button", { name: "识别", exact: true }).click();
  await expect(drawer.getByRole("checkbox", { name: "更正 11203490" })).not.toBeChecked();
  expect(previews).toBe(2);
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("pending records and import batches paginate independently and revoke refreshes both", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  let revoked = false; let revokeBody: unknown;
  await page.route("**/api/tax-offset/certified-imports?*", route => {
    const query = new URL(route.request().url()).searchParams;
    const recordsPage = Number(query.get("records_page")); const batchesPage = Number(query.get("batches_page"));
    return route.fulfill({ json: { records_page: recordsPage, batches_page: batchesPage, page_size: 20, records_total: 21, batches_total: 21,
      records: [{ id: `review-${recordsPage}`, unique_key: `review-${recordsPage}`, needs_review: true, digital_invoice_no: `待核对-${recordsPage}`, invoice_no: null, seller_name: "测试销方", matched_invoice_id: null, status: "active" }],
      batches: [{ id: "batch1", session_id: "s1", imported_by: "user", file_count: 1, months: ["2026-03"], persisted_record_count: 1, duplicate_count: 0, status: revoked ? "revoked" : "confirmed", version: 2, created_at: "2026-03-31" }] } });
  });
  await page.route("**/api/tax-offset/certified-imports/batch1/revoke", route => { revokeBody = route.request().postDataJSON(); revoked = true; return route.fulfill({ json: { status: "revoked" } }); });
  await page.goto("/tax-offset"); await expect(page.getByText("11203490")).toBeVisible();
  await page.locator(".tax-certification-page").getByRole("button", { name: "导入认证记录", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入认证记录" });
  await expect(drawer.getByText("待核对-1")).toBeVisible();
  const pending = drawer.getByRole("region", { name: "待核对记录" });
  await pending.getByRole("button", { name: "下一页" }).click();
  await expect(drawer.getByText("待核对-2")).toBeVisible();
  await drawer.getByRole("button", { name: "撤销", exact: true }).click();
  const confirmation = page.getByRole("alertdialog");
  await confirmation.getByRole("button", { name: "确认撤销" }).click();
  await expect(confirmation).toHaveCount(0); await expect(drawer.getByText("已撤销", { exact: true }).last()).toBeVisible();
  expect(revokeBody).toEqual({ expected_version: 2 });
  await expect(drawer.getByText("待核对-2")).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("large import exceptions render one page and keep corrections across pages", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  let generation = 0;
  await page.route("**/api/tax-offset/certified-import/preview", route => {
    generation += 1;
    const summary = { recognized_count: 60, invalid_count: 0, ignored_count: 0, blocking_count: 0, matched_invoice_count: 0, outside_invoices_count: 60, conflict_count: 2, duplicate_count: 0 };
    const rows = Array.from({ length: 60 }, (_, index) => ({ id: `r${index}`, unique_key: `key${index}`, expected_version: index === 0 || index === 50 ? 3 : null, month: "2026-03", buyer_tax_no: "buyer", row_status: "recognized", match_status: "outside_invoices", dedupe_status: index === 0 || index === 50 ? "conflict" : "new", digital_invoice_no: `票号${index}`, seller_name: "测试销方", source_file_name: "认证.xlsx", source_row_number: index + 4 }));
    return route.fulfill({ json: { session: { id: `s${generation}`, imported_by: "user", file_count: 1, status: "preview_ready" }, summary, files: [{ id: "f1", file_name: "认证.xlsx", month: "2026-03", ...summary, rows }] } });
  });
  await page.goto("/tax-offset"); await expect(page.getByText("11203490")).toBeVisible();
  await page.getByRole("button", { name: "导入认证记录", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入认证记录" });
  await drawer.locator('input[type="file"]').setInputFiles({ name: "认证.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("fixture") });
  await drawer.getByRole("button", { name: "识别", exact: true }).click();
  const preview = drawer.getByRole("region", { name: "识别结果" });
  await expect(preview.getByRole("row")).toHaveCount(51);
  await preview.getByText("更正", { exact: true }).click();
  await preview.getByRole("button", { name: "下一页" }).click();
  await expect(preview.getByRole("row")).toHaveCount(11);
  await preview.getByText("更正", { exact: true }).click();
  await expect(drawer.getByRole("button", { name: "确认导入" })).toBeEnabled();
  await preview.getByRole("button", { name: "上一页" }).click();
  await expect(preview.getByRole("checkbox", { name: "更正 票号0" })).toBeChecked();
  await preview.getByRole("button", { name: "下一页" }).click();
  await drawer.getByRole("button", { name: "识别", exact: true }).click();
  await expect(preview.getByText("显示 1-50 / 60")).toBeVisible();
  await expect(preview.getByRole("checkbox", { name: "更正 票号0" })).not.toBeChecked();
  await expectNoUnexpectedSuccessUiErrors(page);
});


test("compact layout keeps the header and footer fixed while rows scroll", async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", taxOffsetLargeDataset: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/tax-offset");
  await expect(page.getByLabel("未认证统计")).toContainText("92 张");
  const scroll = page.locator(".tax-certification-results .finance-table__scroll");
  const header = page.getByRole("columnheader", { name: "销方名称" });
  const footer = page.locator(".tax-certification-results .finance-table__footer");
  const before = { header: await header.boundingBox(), footer: await footer.boundingBox() };
  await scroll.evaluate(element => { element.scrollTop = 400; });
  await expect.poll(() => scroll.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  expect((await header.boundingBox())!.y).toBeCloseTo(before.header!.y, 0);
  expect((await footer.boundingBox())!.y).toBeCloseTo(before.footer!.y, 0);
  await page.getByRole("columnheader", { name: /开票日期/ }).click();
  await expect.poll(() => scroll.evaluate(element => element.scrollTop)).toBe(0);
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    const statistics = page.getByLabel("进项发票统计", { exact: true });
    await expect(statistics).toBeVisible();
    const titleBox = (await page.getByRole("heading", { name: "专票认证情况" }).boundingBox())!;
    const statisticsBox = (await statistics.boundingBox())!;
    const queryBox = (await page.getByRole("searchbox", { name: "搜索专票" }).boundingBox())!;
    expect(statisticsBox.x).toBeGreaterThanOrEqual(titleBox.x + titleBox.width);
    if (width === 1440) expect(queryBox.x).toBeGreaterThanOrEqual(statisticsBox.x + statisticsBox.width);
    const toolbar = page.locator(".tax-certification-toolbar");
    expect((await toolbar.boundingBox())!.height).toBeLessThanOrEqual(width === 1440 ? 70 : 130);
    const aligned = await page.locator(".tax-certification-summary-group").evaluateAll(groups => groups.every(group => {
      const values = [...group.querySelectorAll(".tax-certification-metric strong")].map(el => el.getBoundingClientRect().y);
      return Math.max(...values) - Math.min(...values) < 2;
    }));
    expect(aligned).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ animations: "disabled", path: info.outputPath(`tax-compact-${width}.png`) });
  }
});

test("inventory kinds open with the keyboard and preserve their total on empty filters", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.goto("/tax-offset");
  const statistics = page.getByRole("button", { name: "进项发票统计", exact: true });
  await expect(statistics).toContainText("进项发票9张");
  await statistics.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "进项发票统计详情" })).toContainText("未识别票种1张");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "进项发票统计详情" })).toHaveCount(0);
  await expect(statistics).toBeFocused();
  await page.getByRole("searchbox", { name: "搜索专票" }).fill("不存在");
  await page.locator(".tax-certification-page").getByRole("button", { name: "查询", exact: true }).click();
  await expect(page.getByText("暂无专票")).toBeVisible();
  await expect(statistics).toContainText("进项发票9张专票2张");
  await expectNoUnexpectedSuccessUiErrors(page);
});
