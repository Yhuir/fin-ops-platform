import { expect, test, type Page, type Download, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectPageReady, gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";
import { readXlsxText } from "./fixtures/xlsx";

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
}

function startStrictBrowserErrorCapture(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    if (failure === "net::ERR_ABORTED") {
      return;
    }
    errors.push(`requestfailed: ${request.method()} ${request.url()} ${failure}`.trim());
  });
  page.on("dialog", async (dialog) => {
    errors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
    await dialog.dismiss().catch(() => undefined);
  });
  return errors;
}

test.describe("pending invoices export browser download", () => {
  test("downloads current filtered pending invoices with confirmed OA and invoice relation fields", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-export-download",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible());
    });
    const pendingRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowBefore.getByText("已支付待开票")).toBeVisible();
    await expect(pendingRowBefore.getByText("12561048")).toHaveCount(0);

    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "pending-invoices.return-after-workbench-confirm",
      visibleLabel: "待找发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "待找发票" }).click();
      await expectPageReady(page, "pending-invoices-page", {
        diagnostics,
        routeDescription: "return to /pending-invoices after workbench relation confirmation",
      });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ }).getByText("已支付已开票")).toBeVisible());
    });
    const pendingRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowAfter.getByText("已支付已开票")).toBeVisible();
    await expect(pendingRowAfter.getByText("12561048")).toBeVisible();
    await expect(pendingRowAfter.getByText("陈涛")).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.search-before-export",
      visibleLabel: "搜索流水",
      actionType: "fill",
    }, async (mark) => {
      const filteredRowsRequest = page.waitForRequest((request) => {
        const url = new URL(request.url());
        return request.method() === "GET"
          && url.pathname.endsWith("/api/pending-invoices/rows")
          && url.searchParams.get("keyword") === "智能工厂"
          && url.searchParams.get("page") === "1";
      });
      await page.getByRole("searchbox", { name: "搜索流水" }).fill("智能工厂");
      await mark("apiLatencyMs", filteredRowsRequest);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible());
    });

    const previewDialog = page.getByRole("dialog", { name: "导出预览" });
    let previewUrl: URL | undefined;
    await recordLatency({
      operationId: "pending-invoices.open-export-preview",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewRequest = page.waitForRequest((request) => {
        const url = new URL(request.url());
        return request.method() === "GET" && url.pathname.endsWith("/api/pending-invoices/export-preview");
      });
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      await mark("apiLatencyMs", previewRequest);
      await mark("firstVisibleResponseLatencyMs", expect(previewDialog).toBeVisible());
      previewUrl = new URL((await previewRequest).url());
    });
    await expect(previewDialog).toBeVisible();
    if (!previewUrl) {
      throw new Error("missing export preview request");
    }
    expect(previewUrl.searchParams.get("direction")).toBe("expense");
    expect(previewUrl.searchParams.get("filter")).toBe("requires_invoice");
    expect(previewUrl.searchParams.get("keyword")).toBe("智能工厂");
    expect(previewUrl.searchParams.get("sort_field")).toBe("trade_date");
    expect(previewUrl.searchParams.get("sort_direction")).toBe("desc");
    expect(previewUrl.searchParams.get("page")).toBeNull();
    expect(previewUrl.searchParams.get("page_size")).toBeNull();

    const previewTable = previewDialog.getByRole("table", { name: "导出样例" });
    await expect(previewTable).toContainText("OA申请人");
    await expect(previewTable).toContainText("进项发票号码");
    await expect(previewTable).toContainText("陈涛");
    await expect(previewTable).toContainText("12561048");
    await expect(previewTable).toContainText("CASE-202603-101");
    await expect(previewTable).toContainText("linked");

    let exportUrl: URL | undefined;
    let downloaded: Download | undefined;
    await recordLatency({
      operationId: "pending-invoices.download-export",
      visibleLabel: "下载导出",
      actionType: "download",
    }, async (mark) => {
      const exportRequest = page.waitForRequest((request) => {
        const url = new URL(request.url());
        return request.method() === "GET" && url.pathname.endsWith("/api/pending-invoices/export");
      });
      const download = page.waitForEvent("download");
      await previewDialog.getByRole("button", { name: "下载导出" }).click();
      exportUrl = new URL((await mark("apiLatencyMs", exportRequest)).url());
      downloaded = await mark("finalSettledLatencyMs", download);
      await expect(previewDialog.getByText("已生成 pending-invoices.xlsx")).toBeVisible();
    });
    if (!exportUrl) {
      throw new Error("missing export request");
    }
    if (!downloaded) {
      throw new Error("missing export download");
    }
    expect(exportUrl.searchParams.get("direction")).toBe("expense");
    expect(exportUrl.searchParams.get("filter")).toBe("requires_invoice");
    expect(exportUrl.searchParams.get("keyword")).toBe("智能工厂");
    expect(exportUrl.searchParams.get("page")).toBeNull();
    expect(exportUrl.searchParams.get("page_size")).toBeNull();

    expect(downloaded.suggestedFilename()).toBe("pending-invoices.xlsx");
    const downloadPath = testInfo.outputPath(downloaded.suggestedFilename());
    await downloaded.saveAs(downloadPath);
    const content = await readXlsxText(downloadPath);

    expect(content).toContain("bk-o-202603-001");
    expect(content).toContain("智能工厂设备商");
    expect(content).toContain("已支付已开票");
    expect(content).toContain("陈涛");
    expect(content).toContain("12561048");
    expect(content).toContain("CASE-202603-101");
    expect(content).toContain("linked");
    expect(content).toContain("导出筛选");
    expect(content).toContain("expense");
    expect(content).toContain("requires_invoice");
    expect(content).toContain("智能工厂");
    expect(content).toContain("trade_date");
    expect(content).toContain("desc");
    expect(content).not.toContain("已支付待开票");
    await expect(previewDialog.getByText("已生成 pending-invoices.xlsx")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("surfaces backend row-limit errors without creating a download", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceExportRowLimitError: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-export-row-limit",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const previewDialog = page.getByRole("dialog", { name: "导出预览" });
    await recordLatency({
      operationId: "pending-invoices.open-export-preview-row-limit",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(previewDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(previewDialog.getByRole("table", { name: "导出样例" })).toBeVisible());
    });
    await expect(previewDialog.getByRole("table", { name: "导出样例" })).toBeVisible();

    const exportRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return request.method() === "GET" && url.pathname.endsWith("/api/pending-invoices/export");
    });
    const downloadAttempt = page.waitForEvent("download", { timeout: 500 }).then(() => true).catch(() => false);
    await recordLatency({
      operationId: "pending-invoices.download-export-row-limit",
      visibleLabel: "下载导出",
      actionType: "download",
    }, async (mark) => {
      await previewDialog.getByRole("button", { name: "下载导出" }).click();
      await mark("apiLatencyMs", exportRequest);
      await mark("firstVisibleResponseLatencyMs", expect(previewDialog.getByRole("alert")).toContainText("待找发票导出超过 20000 行，请缩小筛选范围后重试。"));
    });

    await expect(previewDialog.getByRole("alert")).toContainText("待找发票导出超过 20000 行，请缩小筛选范围后重试。");
    await expect(previewDialog.getByText("已生成 pending-invoices.xlsx")).toHaveCount(0);
    expect(await downloadAttempt).toBe(false);
    expect(api.count("GET /api/pending-invoices/export")).toBe(1);
    expect(browserErrors.filter((error) => !error.includes("status of 400"))).toEqual([]);
    diagnostics.dispose();
  });
});
