import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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

function filtersFromRowsUrl(url: URL) {
  const rawFilters = url.searchParams.get("filters");
  if (!rawFilters) {
    return [];
  }
  return JSON.parse(decodeURIComponent(rawFilters));
}

test.describe("output invoice collections browser flow", () => {
  test("recovers rows after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("销项发票收款情况加载暂时失败，请刷新后重试。");
    await expect(page.getByText("销项发票收款情况加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("当前条件下没有销项发票收款记录。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      const responsePromise = page.waitForResponse((response) => rowsResponse(response));
      await page.getByRole("button", { name: "刷新" }).click();
      recovered = (await responsePromise).status() === 200;
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

  test("filters, sorts, searches, and changes page size through browser table controls", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionListInteractions: true,
      sessionMode: "read_export_only",
    });

    const initialRowsPromise = page.waitForResponse(rowsResponse);
    await page.goto("/output-invoice-collections");
    const initialRowsUrl = new URL((await initialRowsPromise).url());
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "销项发票收款情况表" })).toBeVisible();
    expect(initialRowsUrl.searchParams.get("page")).toBe("1");
    expect(initialRowsUrl.searchParams.get("page_size")).toBe("20");
    await expect(page.getByText("1-2 / 2")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();

    const searchRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByLabel("搜索销项发票收款情况").fill("E2E-0002");
    await page.getByRole("button", { name: "查询" }).click();
    const searchRowsUrl = new URL((await searchRowsPromise).url());
    expect(searchRowsUrl.searchParams.get("keyword")).toBe("E2E-0002");
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0001")).toHaveCount(0);

    const clearSearchRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByLabel("搜索销项发票收款情况").fill("");
    await page.getByRole("button", { name: "查询" }).click();
    const clearSearchRowsUrl = new URL((await clearSearchRowsPromise).url());
    expect(clearSearchRowsUrl.searchParams.has("keyword")).toBe(false);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toBeVisible();

    const sortRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByRole("button", { name: "发票号码 排序" }).click();
    const sortRowsUrl = new URL((await sortRowsPromise).url());
    expect(sortRowsUrl.searchParams.get("sort_field")).toBe("invoice_no");
    expect(sortRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    const statusFilterRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByRole("button", { name: "筛选 收款状态" }).click();
    await page.getByRole("menuitemcheckbox", { name: "待收款，已收部分款 1" }).click();
    const statusFilterRowsUrl = new URL((await statusFilterRowsPromise).url());
    expect(filtersFromRowsUrl(statusFilterRowsUrl)).toEqual([
      { field: "collection_status", operator: "in", values: ["partial_collected"] },
    ]);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("XSFP-E2E-0002")).toHaveCount(0);
    await page.keyboard.press("Escape");

    const invoiceFilterRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByRole("button", { name: "筛选 发票号码" }).click();
    await page.getByLabel("发票号码筛选值").fill("0001");
    await page.getByRole("button", { name: "应用筛选" }).click();
    const invoiceFilterRowsUrl = new URL((await invoiceFilterRowsPromise).url());
    expect(filtersFromRowsUrl(invoiceFilterRowsUrl)).toEqual([
      { field: "collection_status", operator: "in", values: ["partial_collected"] },
      { field: "invoice_no", operator: "contains", value: "0001" },
    ]);
    await expect(page.getByText("XSFP-E2E-0001")).toBeVisible();
    await expect(page.getByText("1-1 / 1")).toBeVisible();

    const pageSizeRowsPromise = page.waitForResponse(rowsResponse);
    await page.getByLabel("每页行数").selectOption("50");
    const pageSizeRowsUrl = new URL((await pageSizeRowsPromise).url());
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

  test("saves collection status and creates a formal receipt through browser drawers", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "销项发票收款情况" })).toBeVisible();
    await expect(page.getByRole("table", { name: "销项发票收款情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();
    await expect(row.getByText("待出收据").first()).toBeVisible();

    const rowsBeforeStatusSave = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "状态/提醒" }).click();
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 状态备注");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒备注");

    const statusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
        && response.request().method() === "PUT",
    );
    const reminderResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await statusResponse).status()).toBe(200);
    expect((await reminderResponse).status()).toBe(200);
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeStatusSave);
    await expect(page.getByRole("dialog", { name: "收款状态和提醒" })).toBeHidden();
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptCreate = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "待出收据" }).click();
    const receiptDrawer = page.getByRole("dialog", { name: "待出收据预览" });
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("收 据")).toBeVisible();
    await expect(receiptDrawer.getByText("人民币伍仟元整")).toBeVisible();
    await expect(receiptDrawer.getByText("销项发票 XSFP-E2E-0001")).toBeVisible();

    const createReceiptResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && response.request().method() === "POST",
    );
    await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
    expect((await createReceiptResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")).toBe(1);
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptCreate);
    await expect(page.getByRole("dialog", { name: "待出收据预览" })).toBeHidden();
    await expect(row.getByTitle("已出收据")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    await row.getByRole("button", { name: "已出收据" }).click();
    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptVoid = api.count("GET /api/output-invoice-collections/rows");
    await historyDrawer.getByRole("button", { name: "作废收据 SK2026050002" }).click();
    const voidDialog = page.getByRole("dialog", { name: "作废收据原因" });
    await expect(voidDialog).toBeVisible();
    await voidDialog.getByLabel("作废原因").fill("浏览器 e2e 作废收据");
    const voidReceiptRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
        && request.method() === "POST",
    );
    const voidReceiptResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
        && response.request().method() === "POST",
    );
    await voidDialog.getByRole("button", { name: "确认作废" }).click();
    const voidBody = JSON.parse((await voidReceiptRequest).postData() ?? "{}") as { reason?: string };
    expect(voidBody.reason).toBe("浏览器 e2e 作废收据");
    expect((await voidReceiptResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/receipts/receipt-output-e2e-001/void")).toBe(1);
    await expect(page.getByRole("dialog", { name: "作废收据原因" })).toHaveCount(0);
    await expect(historyDrawer.getByText("作废：2026-05-03T11:10:00+08:00 浏览器 e2e 作废收据")).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" })).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptVoid);
    await expectNoUnexpectedSuccessUiErrors(page);

    const rowsBeforeReceiptReissue = api.count("GET /api/output-invoice-collections/rows");
    await historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" }).click();
    const reissueDialog = page.getByRole("dialog", { name: "重开收据原因" });
    await expect(reissueDialog).toBeVisible();
    await reissueDialog.getByLabel("重开原因").fill("浏览器 e2e 重开收据");
    const reissueReceiptRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
        && request.method() === "POST",
    );
    const reissueReceiptResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
        && response.request().method() === "POST",
    );
    await reissueDialog.getByRole("button", { name: "确认重开" }).click();
    const reissueBody = JSON.parse((await reissueReceiptRequest).postData() ?? "{}") as { reason?: string };
    expect(reissueBody.reason).toBe("浏览器 e2e 重开收据");
    expect((await reissueReceiptResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")).toBe(1);
    await expect(page.getByRole("dialog", { name: "重开收据原因" })).toHaveCount(0);
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptReissue);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps collection status edits recoverable after a transient save failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionStatusFailOnce: true,
      sessionMode: "admin",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();

    const rowsBeforeSave = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "状态/提醒" }).click();
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 状态失败后保留");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒失败前保留");

    const failedStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await failedStatusResponse).status()).toBe(503);
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

    const retryStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
        && response.request().method() === "PUT",
    );
    const retryReminderResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await retryStatusResponse).status()).toBe(200);
    expect((await retryReminderResponse).status()).toBe(200);
    await expect(statusDrawer).toBeHidden();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(page.getByText("收款状态保存暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps reminder edits recoverable without resaving status after a transient reminder failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReminderFailOnce: true,
      sessionMode: "admin",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();

    const rowsBeforeSave = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "状态/提醒" }).click();
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 提醒失败后不重复状态");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒失败后保留");

    const statusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
        && response.request().method() === "PUT",
    );
    const failedReminderResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await statusResponse).status()).toBe(200);
    expect((await failedReminderResponse).status()).toBe(503);
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

    const retryReminderResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await retryReminderResponse).status()).toBe(200);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")).toBe(1);
    expect(api.count("PUT /api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")).toBe(2);
    await expect(statusDrawer).toBeHidden();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(page.getByText("收款提醒保存暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps receipt creation recoverable after a transient create failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReceiptCreateFailOnce: true,
      sessionMode: "admin",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待出收据").first()).toBeVisible();

    const rowsBeforeCreate = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "待出收据" }).click();
    const receiptDrawer = page.getByRole("dialog", { name: "待出收据预览" });
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("收 据")).toBeVisible();
    await expect(receiptDrawer.getByText("人民币伍仟元整")).toBeVisible();

    const failedCreateRequest = page.waitForRequest((request) =>
      request.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && request.method() === "POST",
    );
    const failedCreateResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && response.request().method() === "POST",
    );
    await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
    const failedCreateHeaders = (await failedCreateRequest).headers();
    expect(failedCreateHeaders["idempotency-key"]).toBe("receipt:output-collection-row-e2e-001:bank-output-e2e-001");
    expect((await failedCreateResponse).status()).toBe(503);
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("正式收据创建暂时失败，请重试。")).toBeVisible();
    await expect(receiptDrawer.getByRole("button", { name: "创建正式收据" })).toBeEnabled();
    await expect(row.getByText("待出收据").first()).toBeVisible();
    await expect(row.getByTitle("已出收据")).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeCreate);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(0);

    const retryCreateResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && response.request().method() === "POST",
    );
    await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
    expect((await retryCreateResponse).status()).toBe(200);
    await expect(receiptDrawer).toBeHidden();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeCreate);
    await expect(row.getByTitle("已出收据")).toBeVisible();
    await expect(page.getByText("正式收据创建暂时失败，请重试。")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps receipt void and reissue reasons recoverable after transient failures", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionInitialReceiptCreated: true,
      outputInvoiceCollectionReceiptReissueFailOnce: true,
      outputInvoiceCollectionReceiptVoidFailOnce: true,
      sessionMode: "admin",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByTitle("已出收据")).toBeVisible();

    await row.getByRole("button", { name: "已出收据" }).click();
    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    const historyRequestsBeforeVoid = api.count("GET /api/output-invoice-collections/receipts/history");
    const rowsBeforeVoid = api.count("GET /api/output-invoice-collections/rows");

    await historyDrawer.getByRole("button", { name: "作废收据 SK2026050002" }).click();
    const voidDialog = page.getByRole("dialog", { name: "作废收据原因" });
    await expect(voidDialog).toBeVisible();
    await voidDialog.getByLabel("作废原因").fill("浏览器 e2e 作废暂时失败后保留");
    const failedVoidResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
        && response.request().method() === "POST",
    );
    await voidDialog.getByRole("button", { name: "确认作废" }).click();
    expect((await failedVoidResponse).status()).toBe(503);
    await expect(voidDialog).toBeVisible();
    await expect(voidDialog.getByLabel("作废原因")).toHaveValue("浏览器 e2e 作废暂时失败后保留");
    await expect(historyDrawer.getByText("正式收据作废暂时失败，请重试。")).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expect(historyDrawer.getByText(/作废：/)).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(historyRequestsBeforeVoid);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeVoid);

    const retryVoidResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/void")
        && response.request().method() === "POST",
    );
    await voidDialog.getByRole("button", { name: "确认作废" }).click();
    expect((await retryVoidResponse).status()).toBe(200);
    await expect(voidDialog).toHaveCount(0);
    await expect(historyDrawer.getByText("正式收据作废暂时失败，请重试。")).toHaveCount(0);
    await expect(historyDrawer.getByText("作废：2026-05-03T11:10:00+08:00 浏览器 e2e 作废收据")).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" })).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/receipts/history")).toBeGreaterThan(
      historyRequestsBeforeVoid,
    );
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeVoid);

    const historyRequestsBeforeReissue = api.count("GET /api/output-invoice-collections/receipts/history");
    const rowsBeforeReissue = api.count("GET /api/output-invoice-collections/rows");
    await historyDrawer.getByRole("button", { name: "重开收据 SK2026050002" }).click();
    const reissueDialog = page.getByRole("dialog", { name: "重开收据原因" });
    await expect(reissueDialog).toBeVisible();
    await reissueDialog.getByLabel("重开原因").fill("浏览器 e2e 重开暂时失败后保留");
    const failedReissueResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
        && response.request().method() === "POST",
    );
    await reissueDialog.getByRole("button", { name: "确认重开" }).click();
    expect((await failedReissueResponse).status()).toBe(503);
    await expect(reissueDialog).toBeVisible();
    await expect(reissueDialog.getByLabel("重开原因")).toHaveValue("浏览器 e2e 重开暂时失败后保留");
    await expect(historyDrawer.getByText("正式收据重开暂时失败，请重试。")).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toHaveCount(0);
    expect(api.count("GET /api/output-invoice-collections/receipts/history")).toBe(historyRequestsBeforeReissue);
    expect(api.count("GET /api/output-invoice-collections/rows")).toBe(rowsBeforeReissue);

    const retryReissueResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue")
        && response.request().method() === "POST",
    );
    await reissueDialog.getByRole("button", { name: "确认重开" }).click();
    expect((await retryReissueResponse).status()).toBe(200);
    await expect(reissueDialog).toHaveCount(0);
    await expect(historyDrawer.getByText("正式收据重开暂时失败，请重试。")).toHaveCount(0);
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050003" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
    await expect.poll(() => api.count("GET /api/output-invoice-collections/receipts/history")).toBeGreaterThan(
      historyRequestsBeforeReissue,
    );
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReissue);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("shows read model refreshing diagnostics instead of stale rows or a true empty state", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionReadModelStatus: "stale",
      sessionMode: "full_access",
    });

    await page.goto("/output-invoice-collections");
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

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await page.getByLabel("搜索销项发票收款情况").fill("浏览器销项客户");
    await page.getByRole("button", { name: "查询" }).click();
    await expect(page.getByRole("row", { name: /XSFP-E2E-0001/ })).toBeVisible();

    const previewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/output-invoice-collections/export-preview");
    });
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const previewResponse = await previewResponsePromise;
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

    const exportResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/output-invoice-collections/export");
    });
    const downloadPromise = page.waitForEvent("download");
    await drawer.getByRole("button", { name: "下载导出" }).click();
    const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);
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

  test("shows row-limit feedback instead of downloading an oversized export", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 400 \(Bad Request\)/],
    });
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionExportRowLimitError: true,
      sessionMode: "read_export_only",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("alert")).toContainText("销项发票收款情况导出超过 20000 行，请缩小筛选范围后重试。");
    await expect(drawer.getByRole("button", { name: "下载导出" })).toBeDisabled();

    expect(api.count("GET /api/output-invoice-collections/export-preview")).toBe(1);
    expect(api.count("GET /api/output-invoice-collections/export")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("keeps read-export users on read-only and export paths without mutation APIs", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceCollectionInitialReceiptCreated: true,
      sessionMode: "read_export_only",
    });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeVisible();
    await expect(page.getByRole("button", { name: "收款状态规则" })).toBeVisible();
    await expect(page.getByRole("button", { name: "收据编号设置" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "状态/提醒" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "红蓝票" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "待出收据" })).toHaveCount(0);

    await page.getByRole("button", { name: "收款状态规则" }).click();
    const rulesDrawer = page.getByRole("dialog", { name: "收款状态规则" });
    await expect(rulesDrawer).toBeVisible();
    await expect(rulesDrawer.getByRole("table", { name: "Sheet6 销项发票收款情况规则" })).toBeVisible();
    await rulesDrawer.getByLabel("关闭收款状态规则").click();
    await expect(rulesDrawer).toBeHidden();

    await row.getByRole("button", { name: "已出收据" }).click();
    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByRole("button", { name: /作废收据/ })).toHaveCount(0);
    await expect(historyDrawer.getByRole("button", { name: /重开收据/ })).toHaveCount(0);
    await historyDrawer.getByLabel("关闭已出收据历史").click();
    await expect(historyDrawer).toBeHidden();

    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(exportDrawer).toBeVisible();
    await expect(exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" })).toBeVisible();
    await expect(exportDrawer.getByRole("button", { name: "下载导出" })).toBeEnabled();

    expect(mutationCalls(api.calls)).toEqual([]);
    expect(api.count("GET /api/output-invoice-collections/export-preview")).toBe(1);
    expect(api.count("GET /api/output-invoice-collections/receipt-settings")).toBe(0);
    expect(browserErrors).toEqual([]);
  });
});
