import { expect, test, type Download, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { readXlsxText } from "./fixtures/xlsx";

function rowsResponse(response: { url: () => string; request: () => { method: () => string } }) {
  const url = new URL(response.url());
  return response.request().method() === "GET"
    && url.pathname.endsWith("/api/output-invoice-collections/rows");
}

function captureBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("status of 503")) {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  return errors;
}

test.describe("销项发票收款情况", () => {
  test("只展示统一事实源三栏并支持查询与导出", async ({ page }, testInfo) => {
    const browserErrors = captureBrowserErrors(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionListInteractions: true,
      sessionMode: "read_export_only",
    });

    await page.goto("/output-invoice-collections");
    const table = page.getByRole("table", { name: "销项发票收款情况表" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "销项发票" })).toHaveAttribute("colspan", "4");
    await expect(table.locator('th[scope="colgroup"]', { hasText: "收款状态" })).toHaveCount(1);
    await expect(table.getByRole("columnheader", { name: "收入流水" })).toHaveAttribute("colspan", "3");
    await expect(table.getByText("已被红冲")).toBeVisible();
    await expect(table.getByText("已冲销蓝票")).toBeVisible();
    await expect(table.getByRole("button", { name: "红蓝票 · 2" })).toHaveCount(2);
    await expect(page.getByRole("button", { name: "收款状态规则" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "收据编号设置" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "状态/提醒" })).toHaveCount(0);

    const rowsBeforeSearch = api.count("GET /api/output-invoice-collections/rows");
    await page.getByRole("searchbox", { name: "搜索销项发票收款情况" }).fill("XSFP-E2E-0002");
    const searchResponse = page.waitForResponse(rowsResponse);
    await page.getByRole("button", { name: "查询", exact: true }).click();
    expect((await searchResponse).status()).toBe(200);
    await expect(page.getByRole("row", { name: /XSFP-E2E-0002/ })).toBeVisible();
    await expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeSearch);

    const previewResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/export-preview")
      && response.request().method() === "GET");
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    expect((await previewResponse).status()).toBe(200);
    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(exportDrawer).toBeVisible();
    await expect(exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" }))
      .toContainText("自动红蓝票关系");

    let download: Download | undefined;
    const downloadPromise = page.waitForEvent("download");
    await exportDrawer.getByRole("button", { name: "下载导出" }).click();
    download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("output-invoice-collections.xlsx");
    const savePath = testInfo.outputPath("output-invoice-collections.xlsx");
    await download.saveAs(savePath);
    expect(await readXlsxText(savePath)).toContain("output_invoice_reversal");

    expect(api.calls.some((call) => /^(POST|PUT|PATCH|DELETE) /.test(call))).toBe(false);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("短暂读取失败后刷新可恢复且不会伪装为空数据", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionRowsFailuresBeforeSuccess: 2,
      sessionMode: "read_export_only",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByRole("alert")).toContainText("销项发票收款情况加载暂时失败");
    await expect(page.getByText("当前条件下没有销项发票收款记录。")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = page.waitForResponse(rowsResponse);
      await page.getByRole("button", { name: "刷新" }).click();
      if ((await response).status() === 200) {
        recovered = true;
        break;
      }
    }
    expect(recovered).toBe(true);
    await expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toBeVisible();
    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThanOrEqual(2);
  });
});
