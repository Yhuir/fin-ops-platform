import { expect, test, type Page, type Download, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { readXlsxText } from "./fixtures/xlsx";

function startStrictBrowserErrorCapture(page: Page, options: { allowedConsoleErrors?: RegExp[] } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (options.allowedConsoleErrors?.some((pattern) => pattern.test(text))) {
        return;
      }
      errors.push(`console.error: ${text}`);
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

const mutationCallPattern = /^(POST|PUT|PATCH|DELETE) /;

function mutationCalls(calls: string[]) {
  return calls.filter((entry) => mutationCallPattern.test(entry));
}

function rowsResponse(response: { url: () => string; request: () => { method: () => string } }) {
  const url = new URL(response.url());
  return response.request().method() === "GET" && url.pathname.endsWith("/api/output-invoice-collections/rows");
}

function createOutputInvoiceCollectionsLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/output-invoice-collections",
    pageKey: "output-invoice-collections",
    module: "output-invoice-collections",
  });
}

function waitForOutputInvoiceRows(page: Page) {
  return page.waitForResponse(rowsResponse);
}

function waitForOutputInvoiceExportPreview(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/output-invoice-collections/export-preview");
  });
}

function waitForOutputInvoiceExport(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/output-invoice-collections/export");
  });
}

function waitForOutputInvoiceStatusSave(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
      && response.request().method() === "PUT",
  );
}

function waitForOutputInvoiceReminderSave(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
      && response.request().method() === "PUT",
  );
}

function waitForOutputInvoiceReceiptCreate(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
      && response.request().method() === "POST",
  );
}

function waitForOutputInvoiceReceiptVoid(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
      && response.request().method() === "POST",
  );
}

function waitForOutputInvoiceReceiptReissue(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
      && response.request().method() === "POST",
  );
}

function filtersFromRowsUrl(url: URL) {
  const rawFilters = url.searchParams.get("filters");
  if (!rawFilters) {
    return [];
  }
  return JSON.parse(decodeURIComponent(rawFilters));
}

test.describe("output invoice collections browser flow", () => {
  test("recovers rows after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-load-failure",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/output-invoice-collections");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("alert")).toContainText("销项发票收款情况加载暂时失败，请刷新后重试。"));
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("销项发票收款情况加载暂时失败，请刷新后重试。");
    await expect(page.getByText("销项发票收款情况加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("当前条件下没有销项发票收款记录。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `output-invoice-collections.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForOutputInvoiceRows(page);
        await page.getByRole("button", { name: "刷新" }).click();
        recovered = (await mark("apiLatencyMs", responsePromise)).status() === 200;
        if (recovered) {
          await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toBeVisible());
        } else {
          await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("销项发票收款情况加载暂时失败，请刷新后重试。"));
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("销项发票收款情况加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByText("销项发票收款情况加载失败，请点击刷新重试。")).toHaveCount(0);
    const recoveredRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(recoveredRow).toBeVisible();
    await expect(recoveredRow.getByText("待收款，已收部分款")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeEnabled();
    await expect(page.getByText("1-1 / 1")).toBeVisible();
    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThanOrEqual(3);
    expect(browserErrors).toEqual([]);
  });

  test("filters, sorts, searches, and changes page size through browser table controls", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionListInteractions: true,
      sessionMode: "read_export_only",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    let initialRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.open-page-filter-sort",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const initialRowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      initialRowsUrl = new URL((await mark("apiLatencyMs", initialRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    if (!initialRowsUrl) {
      throw new Error("missing output invoice collection initial rows response");
    }
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "销项发票收款情况表" })).toBeVisible();
    expect(initialRowsUrl.searchParams.get("page")).toBe("1");
    expect(initialRowsUrl.searchParams.get("page_size")).toBe("20");
    await expect(page.getByText("1-2 / 2")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();

    let searchRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.search-invoice-no",
      visibleLabel: "查询",
      actionType: "click",
    }, async (mark) => {
      const searchRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByLabel("搜索销项发票收款情况").fill("E2E-0002");
      await page.getByRole("button", { name: "查询" }).click();
      searchRowsUrl = new URL((await mark("apiLatencyMs", searchRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByText("XSFP-E2E-0002")).toBeVisible());
    });
    if (!searchRowsUrl) {
      throw new Error("missing output invoice collection search rows response");
    }
    expect(searchRowsUrl.searchParams.get("keyword")).toBe("E2E-0002");
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0001")).toHaveCount(0);

    let clearSearchRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.clear-search",
      visibleLabel: "查询",
      actionType: "click",
    }, async (mark) => {
      const clearSearchRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByLabel("搜索销项发票收款情况").fill("");
      await page.getByRole("button", { name: "查询" }).click();
      clearSearchRowsUrl = new URL((await mark("apiLatencyMs", clearSearchRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByText("XSFP-E2E-0001")).toBeVisible());
    });
    if (!clearSearchRowsUrl) {
      throw new Error("missing output invoice collection clear-search rows response");
    }
    expect(clearSearchRowsUrl.searchParams.has("keyword")).toBe(false);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();

    let sortRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.sort-invoice-no",
      visibleLabel: "发票号码 排序",
      actionType: "click",
    }, async (mark) => {
      const sortRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByRole("button", { name: "发票号码 排序" }).click();
      sortRowsUrl = new URL((await mark("apiLatencyMs", sortRowsPromise)).url());
    });
    if (!sortRowsUrl) {
      throw new Error("missing output invoice collection sort rows response");
    }
    expect(sortRowsUrl.searchParams.get("sort_field")).toBe("invoice_no");
    expect(sortRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    await recordLatency({
      operationId: "output-invoice-collections.open-status-filter",
      visibleLabel: "筛选 收款状态",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 收款状态" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("menuitemcheckbox", { name: "待收款，已收部分款 1" })).toBeVisible());
    });
    let statusFilterRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.apply-status-filter",
      visibleLabel: "待收款，已收部分款 1",
      actionType: "click",
    }, async (mark) => {
      const statusFilterRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByRole("menuitemcheckbox", { name: "待收款，已收部分款 1" }).click();
      statusFilterRowsUrl = new URL((await mark("apiLatencyMs", statusFilterRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByText("XSFP-E2E-0001")).toBeVisible());
    });
    if (!statusFilterRowsUrl) {
      throw new Error("missing output invoice collection status-filter rows response");
    }
    expect(filtersFromRowsUrl(statusFilterRowsUrl)).toEqual([
      { field: "collection_status", operator: "in", values: ["partial_collected"] },
    ]);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toHaveCount(0);
    await page.keyboard.press("Escape");

    await recordLatency({
      operationId: "output-invoice-collections.open-invoice-no-filter",
      visibleLabel: "筛选 发票号码",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 发票号码" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByLabel("发票号码筛选值")).toBeVisible());
    });
    let invoiceFilterRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.apply-invoice-no-filter",
      visibleLabel: "应用筛选",
      actionType: "click",
    }, async (mark) => {
      const invoiceFilterRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByLabel("发票号码筛选值").fill("0001");
      await page.getByRole("button", { name: "应用筛选" }).click();
      invoiceFilterRowsUrl = new URL((await mark("apiLatencyMs", invoiceFilterRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByText("1-1 / 1")).toBeVisible());
    });
    if (!invoiceFilterRowsUrl) {
      throw new Error("missing output invoice collection invoice-filter rows response");
    }
    expect(filtersFromRowsUrl(invoiceFilterRowsUrl)).toEqual([
      { field: "collection_status", operator: "in", values: ["partial_collected"] },
      { field: "invoice_no", operator: "contains", value: "0001" },
    ]);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("1-1 / 1")).toBeVisible();

    let pageSizeRowsUrl: URL | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.change-page-size-50",
      visibleLabel: "每页行数",
      actionType: "select",
    }, async (mark) => {
      const pageSizeRowsPromise = waitForOutputInvoiceRows(page);
      await page.getByLabel("每页行数").selectOption("50");
      pageSizeRowsUrl = new URL((await mark("apiLatencyMs", pageSizeRowsPromise)).url());
      await mark("finalSettledLatencyMs", expect(page.getByText("1-1 / 1")).toBeVisible());
    });
    if (!pageSizeRowsUrl) {
      throw new Error("missing output invoice collection page-size rows response");
    }
    expect(pageSizeRowsUrl.searchParams.get("page")).toBe("1");
    expect(pageSizeRowsUrl.searchParams.get("page_size")).toBe("50");
    expect(filtersFromRowsUrl(pageSizeRowsUrl)).toEqual([
      { field: "collection_status", operator: "in", values: ["partial_collected"] },
      { field: "invoice_no", operator: "contains", value: "0001" },
    ]);
    await expect(page.getByText("1-1 / 1")).toBeVisible();

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("saves collection status and creates a formal receipt through browser drawers", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-status-receipt",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "销项发票收款情况" })).toBeVisible();
    await expect(page.getByRole("table", { name: "销项发票收款情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();
    await expect(row.getByText("待出收据").first()).toBeVisible();

    const rowsBeforeStatusSave = api.count("GET /api/output-invoice-collections/rows");
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await recordLatency({
      operationId: "output-invoice-collections.open-status-reminder",
      visibleLabel: "状态/提醒",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "状态/提醒" }).click();
      await mark("finalSettledLatencyMs", expect(statusDrawer).toBeVisible());
    });
    await expect(statusDrawer).toBeVisible();
    await recordLatency({
      operationId: "output-invoice-collections.edit-status-reminder",
      visibleLabel: "收款状态和提醒",
      actionType: "fill",
    }, async (mark) => {
      await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
      await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
      await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 状态备注");
      await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
      await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒备注");
      await mark("finalSettledLatencyMs", expect(statusDrawer.getByRole("button", { name: "保存" })).toBeEnabled());
    });

    await recordLatency({
      operationId: "output-invoice-collections.save-status-reminder",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const statusResponse = waitForOutputInvoiceStatusSave(page);
      const reminderResponse = waitForOutputInvoiceReminderSave(page);
      await statusDrawer.getByRole("button", { name: "保存" }).click();
      expect((await mark("apiLatencyMs", statusResponse)).status()).toBe(200);
      expect((await reminderResponse).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeStatusSave));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "收款状态和提醒" })).toBeHidden());
    });
    await expect(page.getByRole("dialog", { name: "收款状态和提醒" })).toBeHidden();
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptCreate = api.count("GET /api/output-invoice-collections/rows");
    const receiptDrawer = page.getByRole("dialog", { name: "待出收据预览" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-preview",
      visibleLabel: "待出收据",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "待出收据" }).click();
      await mark("finalSettledLatencyMs", expect(receiptDrawer).toBeVisible());
    });
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("收 据")).toBeVisible();
    await expect(receiptDrawer.getByText("人民币伍仟元整")).toBeVisible();
    await expect(receiptDrawer.getByText("销项发票 XSFP-E2E-0001")).toBeVisible();

    await recordLatency({
      operationId: "output-invoice-collections.create-receipt",
      visibleLabel: "创建正式收据",
      actionType: "click",
    }, async (mark) => {
      const createReceiptResponse = waitForOutputInvoiceReceiptCreate(page);
      await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
      expect((await mark("apiLatencyMs", createReceiptResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptCreate));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "待出收据预览" })).toBeHidden());
    });
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")).toBe(1);
    await expect(page.getByRole("dialog", { name: "待出收据预览" })).toBeHidden();
    await expect(row.getByTitle("已出收据")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-history",
      visibleLabel: "已出收据",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "已出收据" }).click();
      await mark("finalSettledLatencyMs", expect(historyDrawer).toBeVisible());
    });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptVoid = api.count("GET /api/output-invoice-collections/rows");
    const voidDialog = page.getByRole("dialog", { name: "作废收据原因" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-void-dialog",
      visibleLabel: "作废收据 SK2026050002",
      actionType: "click",
    }, async (mark) => {
      await historyDrawer.getByRole("button", { name: "作废收据 SK2026050002" }).click();
      await mark("finalSettledLatencyMs", expect(voidDialog).toBeVisible());
    });
    await expect(voidDialog).toBeVisible();
    await voidDialog.getByLabel("作废原因").fill("浏览器 e2e 作废收据");
    const voidReceiptRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
        && request.method() === "POST",
    );
    let voidBody: { reason?: string } | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.confirm-receipt-void",
      visibleLabel: "确认作废",
      actionType: "click",
    }, async (mark) => {
      const voidReceiptResponse = waitForOutputInvoiceReceiptVoid(page);
      await voidDialog.getByRole("button", { name: "确认作废" }).click();
      voidBody = JSON.parse((await voidReceiptRequest).postData() ?? "{}") as { reason?: string };
      expect((await mark("apiLatencyMs", voidReceiptResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptVoid));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "作废收据原因" })).toHaveCount(0));
    });
    if (!voidBody) {
      throw new Error("missing output invoice receipt void body");
    }
    expect(voidBody.reason).toBe("浏览器 e2e 作废收据");
    expect(api.count("POST /api/output-invoice-collections/receipts/receipt-output-e2e-001/void")).toBe(1);
    await expect(page.getByRole("dialog", { name: "作废收据原因" })).toHaveCount(0);
    await expect(historyDrawer.getByText("作废：2026-05-03T11:10:00+08:00 浏览器 e2e 作废收据")).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptReissue = api.count("GET /api/output-invoice-collections/rows");
    const reissueDialog = page.getByRole("dialog", { name: "重开收据原因" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-reissue-dialog",
      visibleLabel: "重开收据 SK2026050002",
      actionType: "click",
    }, async (mark) => {
      await historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" }).click();
      await mark("finalSettledLatencyMs", expect(reissueDialog).toBeVisible());
    });
    await expect(reissueDialog).toBeVisible();
    await reissueDialog.getByLabel("重开原因").fill("浏览器 e2e 重开收据");
    const reissueReceiptRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
        && request.method() === "POST",
    );
    let reissueBody: { reason?: string } | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.confirm-receipt-reissue",
      visibleLabel: "确认重开",
      actionType: "click",
    }, async (mark) => {
      const reissueReceiptResponse = waitForOutputInvoiceReceiptReissue(page);
      await reissueDialog.getByRole("button", { name: "确认重开" }).click();
      reissueBody = JSON.parse((await reissueReceiptRequest).postData() ?? "{}") as { reason?: string };
      expect((await mark("apiLatencyMs", reissueReceiptResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptReissue));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "重开收据原因" })).toHaveCount(0));
    });
    if (!reissueBody) {
      throw new Error("missing output invoice receipt reissue body");
    }
    expect(reissueBody.reason).toBe("浏览器 e2e 重开收据");
    expect(api.count("POST /api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")).toBe(1);
    await expect(page.getByRole("dialog", { name: "重开收据原因" })).toHaveCount(0);
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps collection status edits recoverable after a transient save failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionStatusFailOnce: true,
      sessionMode: "admin",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-status-failure",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();

    const rowsBeforeSave = api.count("GET /api/output-invoice-collections/rows");
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await recordLatency({
      operationId: "output-invoice-collections.open-status-reminder-failure",
      visibleLabel: "状态/提醒",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "状态/提醒" }).click();
      await mark("finalSettledLatencyMs", expect(statusDrawer).toBeVisible());
    });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 状态失败后保留");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒失败前保留");

    await recordLatency({
      operationId: "output-invoice-collections.save-status-failure",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const failedStatusResponse = waitForOutputInvoiceStatusSave(page);
      await statusDrawer.getByRole("button", { name: "保存" }).click();
      expect((await mark("apiLatencyMs", failedStatusResponse)).status()).toBe(503);
      await mark("finalSettledLatencyMs", expect(statusDrawer.getByText("收款状态保存暂时失败，请重试。")).toBeVisible());
    });
    await expect(statusDrawer).toBeVisible();
    await expect(statusDrawer.getByText("收款状态保存暂时失败，请重试。")).toBeVisible();
    await expect(statusDrawer.getByRole("button", { name: "保存" })).toBeEnabled();
    await expect(statusDrawer.getByLabel("手动状态")).toHaveValue("pending_red_invoice");
    await expect(statusDrawer.getByLabel("状态备注")).toHaveValue("浏览器 e2e 状态失败后保留");
    await expect(statusDrawer.getByLabel("提醒备注")).toHaveValue("浏览器 e2e 提醒失败前保留");
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();
    await expect(row.getByText("待冲红")).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeSave);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")).toBe(0);

    await recordLatency({
      operationId: "output-invoice-collections.retry-status-save",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const retryStatusResponse = waitForOutputInvoiceStatusSave(page);
      const retryReminderResponse = waitForOutputInvoiceReminderSave(page);
      await statusDrawer.getByRole("button", { name: "保存" }).click();
      expect((await mark("apiLatencyMs", retryStatusResponse)).status()).toBe(200);
      expect((await retryReminderResponse).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeSave));
      await mark("finalSettledLatencyMs", expect(statusDrawer).toBeHidden());
    });
    await expect(statusDrawer).toBeHidden();
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(page.getByText("收款状态保存暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps reminder edits recoverable without resaving status after a transient reminder failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReminderFailOnce: true,
      sessionMode: "admin",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-reminder-failure",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();

    const rowsBeforeSave = api.count("GET /api/output-invoice-collections/rows");
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await recordLatency({
      operationId: "output-invoice-collections.open-status-reminder-reminder-failure",
      visibleLabel: "状态/提醒",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "状态/提醒" }).click();
      await mark("finalSettledLatencyMs", expect(statusDrawer).toBeVisible());
    });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 提醒失败后不重复状态");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒失败后保留");

    await recordLatency({
      operationId: "output-invoice-collections.save-reminder-failure",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const statusResponse = waitForOutputInvoiceStatusSave(page);
      const failedReminderResponse = waitForOutputInvoiceReminderSave(page);
      await statusDrawer.getByRole("button", { name: "保存" }).click();
      expect((await mark("apiLatencyMs", statusResponse)).status()).toBe(200);
      expect((await failedReminderResponse).status()).toBe(503);
      await mark("finalSettledLatencyMs", expect(statusDrawer.getByText("收款提醒保存暂时失败，请重试。")).toBeVisible());
    });
    await expect(statusDrawer).toBeVisible();
    await expect(statusDrawer.getByText("收款提醒保存暂时失败，请重试。")).toBeVisible();
    await expect(statusDrawer.getByRole("button", { name: "保存" })).toBeEnabled();
    await expect(statusDrawer.getByLabel("手动状态")).toHaveValue("pending_red_invoice");
    await expect(statusDrawer.getByLabel("状态备注")).toHaveValue("浏览器 e2e 提醒失败后不重复状态");
    await expect(statusDrawer.getByLabel("提醒备注")).toHaveValue("浏览器 e2e 提醒失败后保留");
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();
    await expect(row.getByText("待冲红")).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeSave);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")).toBe(1);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")).toBe(1);

    await recordLatency({
      operationId: "output-invoice-collections.retry-reminder-save",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const retryReminderResponse = waitForOutputInvoiceReminderSave(page);
      await statusDrawer.getByRole("button", { name: "保存" }).click();
      expect((await mark("apiLatencyMs", retryReminderResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeSave));
      await mark("finalSettledLatencyMs", expect(statusDrawer).toBeHidden());
    });
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")).toBe(1);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")).toBe(2);
    await expect(statusDrawer).toBeHidden();
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(page.getByText("收款提醒保存暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps receipt creation recoverable after a transient create failure", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReceiptCreateFailOnce: true,
      sessionMode: "admin",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-receipt-create-failure",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待出收据").first()).toBeVisible();

    const rowsBeforeCreate = api.count("GET /api/output-invoice-collections/rows");
    const receiptDrawer = page.getByRole("dialog", { name: "待出收据预览" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-preview-create-failure",
      visibleLabel: "待出收据",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "待出收据" }).click();
      await mark("finalSettledLatencyMs", expect(receiptDrawer).toBeVisible());
    });
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("收 据")).toBeVisible();
    await expect(receiptDrawer.getByText("人民币伍仟元整")).toBeVisible();

    const failedCreateRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && request.method() === "POST",
    );
    await recordLatency({
      operationId: "output-invoice-collections.create-receipt-failure",
      visibleLabel: "创建正式收据",
      actionType: "click",
    }, async (mark) => {
      const failedCreateResponse = waitForOutputInvoiceReceiptCreate(page);
      await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
      expect((await mark("apiLatencyMs", failedCreateResponse)).status()).toBe(503);
      await mark("finalSettledLatencyMs", expect(receiptDrawer.getByText("正式收据创建暂时失败，请重试。")).toBeVisible());
    });
    const failedCreateHeaders = (await failedCreateRequest).headers();
    expect(failedCreateHeaders["idempotency-key"]).toBe("receipt:output-collection-row-e2e-001:bank-output-e2e-001");
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("正式收据创建暂时失败，请重试。")).toBeVisible();
    await expect(receiptDrawer.getByRole("button", { name: "创建正式收据" })).toBeEnabled();
    await expect(row.getByText("待出收据").first()).toBeVisible();
    await expect(row.getByTitle("已出收据")).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeCreate);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(0);

    await recordLatency({
      operationId: "output-invoice-collections.retry-receipt-create",
      visibleLabel: "创建正式收据",
      actionType: "click",
    }, async (mark) => {
      const retryCreateResponse = waitForOutputInvoiceReceiptCreate(page);
      await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
      expect((await mark("apiLatencyMs", retryCreateResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeCreate));
      await mark("finalSettledLatencyMs", expect(receiptDrawer).toBeHidden());
    });
    await expect(receiptDrawer).toBeHidden();
    await expect(row.getByTitle("已出收据")).toBeVisible();
    await expect(page.getByText("正式收据创建暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps receipt void and reissue reasons recoverable after transient failures", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionInitialReceiptCreated: true,
      outputInvoiceCollectionReceiptReissueFailOnce: true,
      outputInvoiceCollectionReceiptVoidFailOnce: true,
      sessionMode: "admin",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-receipt-void-reissue-failure",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByTitle("已出收据")).toBeVisible();

    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-history-void-reissue-failure",
      visibleLabel: "已出收据",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "已出收据" }).click();
      await mark("finalSettledLatencyMs", expect(historyDrawer).toBeVisible());
    });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    const historyRequestsBeforeVoid = api.count("GET /api/output-invoice-collections/receipts/history");
    const rowsBeforeVoid = api.count("GET /api/output-invoice-collections/rows");

    const voidDialog = page.getByRole("dialog", { name: "作废收据原因" });
    await recordLatency({
      operationId: "output-invoice-collections.open-void-dialog-failure",
      visibleLabel: "作废收据 SK2026050002",
      actionType: "click",
    }, async (mark) => {
      await historyDrawer.getByRole("button", { name: "作废收据 SK2026050002" }).click();
      await mark("finalSettledLatencyMs", expect(voidDialog).toBeVisible());
    });
    await expect(voidDialog).toBeVisible();
    await voidDialog.getByLabel("作废原因").fill("浏览器 e2e 作废暂时失败后保留");
    await recordLatency({
      operationId: "output-invoice-collections.confirm-void-failure",
      visibleLabel: "确认作废",
      actionType: "click",
    }, async (mark) => {
      const failedVoidResponse = waitForOutputInvoiceReceiptVoid(page);
      await voidDialog.getByRole("button", { name: "确认作废" }).click();
      expect((await mark("apiLatencyMs", failedVoidResponse)).status()).toBe(503);
      await mark("finalSettledLatencyMs", expect(historyDrawer.getByText("正式收据作废暂时失败，请重试。")).toBeVisible());
    });
    await expect(voidDialog).toBeVisible();
    await expect(voidDialog.getByLabel("作废原因")).toHaveValue("浏览器 e2e 作废暂时失败后保留");
    await expect(historyDrawer.getByText("正式收据作废暂时失败，请重试。")).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expect(historyDrawer.getByText(/作废：/)).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(historyRequestsBeforeVoid);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeVoid);

    await recordLatency({
      operationId: "output-invoice-collections.retry-void",
      visibleLabel: "确认作废",
      actionType: "click",
    }, async (mark) => {
      const retryVoidResponse = waitForOutputInvoiceReceiptVoid(page);
      await voidDialog.getByRole("button", { name: "确认作废" }).click();
      expect((await mark("apiLatencyMs", retryVoidResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeVoid));
      await mark("finalSettledLatencyMs", expect(voidDialog).toHaveCount(0));
    });
    await expect(voidDialog).toHaveCount(0);
    await expect(historyDrawer.getByText("正式收据作废暂时失败，请重试。")).toHaveCount(0);
    await expect(historyDrawer.getByText("作废：2026-05-03T11:10:00+08:00 浏览器 e2e 作废收据")).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" })).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/receipts/history")).toBeGreaterThan(
      historyRequestsBeforeVoid,
    );

    const historyRequestsBeforeReissue = api.count("GET /api/output-invoice-collections/receipts/history");
    const rowsBeforeReissue = api.count("GET /api/output-invoice-collections/rows");
    const reissueDialog = page.getByRole("dialog", { name: "重开收据原因" });
    await recordLatency({
      operationId: "output-invoice-collections.open-reissue-dialog-failure",
      visibleLabel: "重开收据 SK2026050002",
      actionType: "click",
    }, async (mark) => {
      await historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" }).click();
      await mark("finalSettledLatencyMs", expect(reissueDialog).toBeVisible());
    });
    await expect(reissueDialog).toBeVisible();
    await reissueDialog.getByLabel("重开原因").fill("浏览器 e2e 重开暂时失败后保留");
    await recordLatency({
      operationId: "output-invoice-collections.confirm-reissue-failure",
      visibleLabel: "确认重开",
      actionType: "click",
    }, async (mark) => {
      const failedReissueResponse = waitForOutputInvoiceReceiptReissue(page);
      await reissueDialog.getByRole("button", { name: "确认重开" }).click();
      expect((await mark("apiLatencyMs", failedReissueResponse)).status()).toBe(503);
      await mark("finalSettledLatencyMs", expect(historyDrawer.getByText("正式收据重开暂时失败，请重试。")).toBeVisible());
    });
    await expect(reissueDialog).toBeVisible();
    await expect(reissueDialog.getByLabel("重开原因")).toHaveValue("浏览器 e2e 重开暂时失败后保留");
    await expect(historyDrawer.getByText("正式收据重开暂时失败，请重试。")).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(historyRequestsBeforeReissue);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeReissue);

    await recordLatency({
      operationId: "output-invoice-collections.retry-reissue",
      visibleLabel: "确认重开",
      actionType: "click",
    }, async (mark) => {
      const retryReissueResponse = waitForOutputInvoiceReceiptReissue(page);
      await reissueDialog.getByRole("button", { name: "确认重开" }).click();
      expect((await mark("apiLatencyMs", retryReissueResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReissue));
      await mark("finalSettledLatencyMs", expect(reissueDialog).toHaveCount(0));
    });
    await expect(reissueDialog).toHaveCount(0);
    await expect(historyDrawer.getByText("正式收据重开暂时失败，请重试。")).toHaveCount(0);
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/receipts/history")).toBeGreaterThan(
      historyRequestsBeforeReissue,
    );
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("shows read model refreshing diagnostics instead of stale rows or a true empty state", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReadModelStatus: "stale",
      sessionMode: "full_access",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-read-model-stale",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(202);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("销项发票收款情况数据正在刷新")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "销项发票收款情况" })).toBeVisible();

    await expect(page.getByText("销项发票收款情况数据正在刷新")).toBeVisible();
    await expect(page.getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("XSFP-E2E-0001")).toHaveCount(0);
    await expect(page.getByText("output_invoice_collection_stale")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "状态/提醒" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "待出收据" })).toHaveCount(0);

    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/output-invoice-collections/filter-options")).toBeGreaterThanOrEqual(1);
    expect(browserErrors).toEqual([]);
  });

  test("downloads the current filtered output collection rows without paginating the export", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-export-download",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await recordLatency({
      operationId: "output-invoice-collections.search-before-export",
      visibleLabel: "查询",
      actionType: "click",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.getByLabel("搜索销项发票收款情况").fill("浏览器销项客户");
      await page.getByRole("button", { name: "查询" }).click();
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toBeVisible());
    });
    await expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toBeVisible();

    let previewResponse: Awaited<ReturnType<typeof waitForOutputInvoiceExportPreview>> | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.open-export-preview",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForOutputInvoiceExportPreview(page);
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      previewResponse = await mark("apiLatencyMs", previewResponsePromise);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("dialog", { name: "筛选内容导出" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "筛选内容导出" }).getByRole("table", { name: "销项发票收款情况导出样例" })).toBeVisible());
    });
    if (!previewResponse) {
      throw new Error("missing output invoice collection export preview response");
    }
    const previewUrl = new URL(previewResponse.url());
    expect(previewResponse.status()).toBe(200);
    expect(previewUrl.searchParams.get("keyword")).toBe("浏览器销项客户");
    expect(previewUrl.searchParams.has("page")).toBe(false);
    expect(previewUrl.searchParams.has("page_size")).toBe(false);

    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("table", { name: "销项发票收款情况导出样例" })).toBeVisible();
    await expect(drawer.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(drawer.getByRole("cell", { name: "浏览器销项客户" }).first()).toBeVisible();
    await expect(drawer.getByText("待收款，已收部分款")).toBeVisible();

    let exportResponse: Awaited<ReturnType<typeof waitForOutputInvoiceExport>> | undefined;
    let download: Download | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.download-export",
      visibleLabel: "下载导出",
      actionType: "click",
    }, async (mark) => {
      const exportResponsePromise = waitForOutputInvoiceExport(page);
      const downloadPromise = page.waitForEvent("download");
      await drawer.getByRole("button", { name: "下载导出" }).click();
      exportResponse = await mark("apiLatencyMs", exportResponsePromise);
      download = await mark("finalSettledLatencyMs", downloadPromise);
    });
    if (!exportResponse || !download) {
      throw new Error("missing output invoice collection export download response");
    }
    const exportUrl = new URL(exportResponse.url());
    expect(exportResponse.status()).toBe(200);
    expect(exportUrl.searchParams.get("keyword")).toBe("浏览器销项客户");
    expect(exportUrl.searchParams.has("page")).toBe(false);
    expect(exportUrl.searchParams.has("page_size")).toBe(false);
    expect(download.suggestedFilename()).toBe("output-invoice-collections.xlsx");

    const savePath = testInfo.outputPath("output-invoice-collections.xlsx");
    await download.saveAs(savePath);
    const downloadedText = await readXlsxText(savePath);
    expect(downloadedText).toContain("XSFP-E2E-0001");
    expect(downloadedText).toContain("浏览器销项客户");
    expect(downloadedText).toContain("待收款，已收部分款");
    expect(downloadedText).toContain("keyword");
    expect(downloadedText).toContain("page");
    expect(api.count("GET /api/output-invoice-collections/export-preview")).toBe(1);
    expect(api.count("GET /api/output-invoice-collections/export")).toBe(1);
    expect(browserErrors).toEqual([]);
  });

  test("shows row-limit feedback instead of downloading an oversized export", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 400 \(Bad Request\)/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionExportRowLimitError: true,
      sessionMode: "read_export_only",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-export-row-limit",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await recordLatency({
      operationId: "output-invoice-collections.open-export-preview-row-limit",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForOutputInvoiceExportPreview(page);
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      expect((await mark("apiLatencyMs", previewResponsePromise)).status()).toBe(400);
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("alert")).toContainText("销项发票收款情况导出超过 20000 行，请缩小筛选范围后重试。"));
    });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("alert")).toContainText("销项发票收款情况导出超过 20000 行，请缩小筛选范围后重试。");
    await expect(drawer.getByRole("button", { name: "下载导出" })).toBeDisabled();

    expect(api.count("GET /api/output-invoice-collections/export-preview")).toBe(1);
    expect(api.count("GET /api/output-invoice-collections/export")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("keeps read-export users on read-only and export paths without mutation APIs", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionInitialReceiptCreated: true,
      sessionMode: "read_export_only",
    });
    const recordLatency = createOutputInvoiceCollectionsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-read-export",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsPromise = waitForOutputInvoiceRows(page);
      await page.goto("/output-invoice-collections");
      expect((await mark("apiLatencyMs", rowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeVisible();
    await expect(page.getByRole("button", { name: "收款状态规则" })).toBeVisible();
    await expect(page.getByRole("button", { name: "收据编号设置" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "状态/提醒" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "红蓝票" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "待出收据" })).toHaveCount(0);

    const rulesDrawer = page.getByRole("dialog", { name: "收款状态规则" });
    await recordLatency({
      operationId: "output-invoice-collections.open-status-rules-read-export",
      visibleLabel: "收款状态规则",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "收款状态规则" }).click();
      await mark("finalSettledLatencyMs", expect(rulesDrawer).toBeVisible());
    });
    await expect(rulesDrawer).toBeVisible();
    await expect(rulesDrawer.getByRole("table", { name: "Sheet6 销项发票收款情况规则" })).toBeVisible();
    await recordLatency({
      operationId: "output-invoice-collections.close-status-rules-read-export",
      visibleLabel: "关闭收款状态规则",
      actionType: "click",
    }, async (mark) => {
      await rulesDrawer.getByLabel("关闭收款状态规则").click();
      await mark("finalSettledLatencyMs", expect(rulesDrawer).toBeHidden());
    });
    await expect(rulesDrawer).toBeHidden();

    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await recordLatency({
      operationId: "output-invoice-collections.open-receipt-history-read-export",
      visibleLabel: "已出收据",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "已出收据" }).click();
      await mark("finalSettledLatencyMs", expect(historyDrawer).toBeVisible());
    });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: /作废收据/ })).toHaveCount(0);
    await expect(historyDrawer.getByRole("button", { name: /重开收据/ })).toHaveCount(0);
    await recordLatency({
      operationId: "output-invoice-collections.close-receipt-history-read-export",
      visibleLabel: "关闭已出收据历史",
      actionType: "click",
    }, async (mark) => {
      await historyDrawer.getByLabel("关闭已出收据历史").click();
      await mark("finalSettledLatencyMs", expect(historyDrawer).toBeHidden());
    });
    await expect(historyDrawer).toBeHidden();

    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await recordLatency({
      operationId: "output-invoice-collections.open-export-preview-read-export",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForOutputInvoiceExportPreview(page);
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      expect((await mark("apiLatencyMs", previewResponsePromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" })).toBeVisible());
    });
    await expect(exportDrawer).toBeVisible();
    await expect(exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" })).toBeVisible();
    await expect(exportDrawer.getByRole("button", { name: "下载导出" })).toBeEnabled();

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("GET /api/output-invoice-collections/export-preview")).toBe(1);
    expect(api.count("GET /api/output-invoice-collections/receipt-settings")).toBe(0);
    expect(browserErrors).toEqual([]);
  });
});
