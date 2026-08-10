import { expect, setCheckbox, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
}

function waitForIncomeStatusBatch(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "PUT"
      && url.pathname === "/api/pending-invoices/income-statuses";
  });
}

function startBrowserRuntimeErrorCapture(
  page: Page,
  options: { allowedConsoleErrors?: RegExp[] } = {},
) {
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

async function openIncomeDirection(page: Page) {
  await page.getByRole("radio", { name: /^收入 / }).click();
  await expect(page.getByRole("row", { name: /收入批量客户A/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /收入批量客户B/ })).toBeVisible();
}

test.describe("pending invoices income status browser flow", () => {
  test("batch marks selected income rows as cash income with one mutation and a rows refresh", async ({ page }, testInfo) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceIncomeBatchRows: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-income-status",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.open-income-direction",
      visibleLabel: "收入",
      actionType: "click",
    }, async (mark) => {
      await openIncomeDirection(page);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /收入批量客户A/ })).toBeVisible());
    });
    const rowsBeforeSubmit = api.count("GET /api/pending-invoices/rows");
    await expect(page.getByRole("button", { name: "标记现金收入" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "标记无需开票" })).toHaveCount(0);

    await recordLatency({
      operationId: "pending-invoices.select-income-status-rows",
      visibleLabel: "选择收入流水",
      actionType: "check",
    }, async (mark) => {
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户A" }));
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户B" }));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    await expect(page.getByText("已选 2 条流水")).toBeVisible();
    await expect(page.getByText("流水合计 500.00")).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.mark-income-cash",
      visibleLabel: "标记现金收入",
      actionType: "click",
    }, async (mark) => {
      const incomeStatusResponse = waitForIncomeStatusBatch(page);
      await page.getByRole("button", { name: "标记现金收入" }).click();
      expect((await mark("apiLatencyMs", incomeStatusResponse)).status()).toBe(200);
      await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSubmit);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("现金收入")).toBeVisible());
    });
    await expect.poll(() => api.count("PUT /api/pending-invoices/income-statuses")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/income-statuses")).toMatchObject({
      status_code: "cash_income",
      transaction_ids: ["income-batch-a", "income-batch-b"],
    });
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSubmit);

    await expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("现金收入")).toBeVisible();
    await expect(page.getByRole("row", { name: /收入批量客户B/ }).getByText("现金收入")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toHaveCount(0);
    expect(api.count("PUT /api/pending-invoices/rows/income-batch-a/income-status")).toBe(0);
    expect(api.count("PUT /api/pending-invoices/rows/income-batch-b/income-status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("keeps income status batches recoverable after a transient save failure", async ({ page }, testInfo) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceIncomeBatchRows: true,
      pendingInvoiceIncomeStatusFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-income-status-failure",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.prepare-income-status-failure",
      visibleLabel: "收入批量选择",
      actionType: "click",
    }, async (mark) => {
      await openIncomeDirection(page);
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户A" }));
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户B" }));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    const rowsBeforeSubmit = api.count("GET /api/pending-invoices/rows");

    await recordLatency({
      operationId: "pending-invoices.mark-income-cash-failed",
      visibleLabel: "标记现金收入",
      actionType: "click",
    }, async (mark) => {
      const incomeStatusResponse = waitForIncomeStatusBatch(page);
      await page.getByRole("button", { name: "标记现金收入" }).click();
      expect((await mark("apiLatencyMs", incomeStatusResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("收入状态保存暂时失败，请重试。"));
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "标记现金收入" })).toBeEnabled());
    });
    await expect(page.getByRole("alert")).toContainText("收入状态保存暂时失败，请重试。");
    expect(api.count("PUT /api/pending-invoices/income-statuses")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/income-statuses")).toMatchObject({
      status_code: "cash_income",
      transaction_ids: ["income-batch-a", "income-batch-b"],
    });
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforeSubmit);
    await expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("未开票")).toBeVisible();
    await expect(page.getByRole("row", { name: /收入批量客户B/ }).getByText("未开票")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toBeVisible();
    await expect(page.getByRole("button", { name: "标记现金收入" })).toBeEnabled();

    await recordLatency({
      operationId: "pending-invoices.mark-income-cash-retry",
      visibleLabel: "标记现金收入",
      actionType: "click",
    }, async (mark) => {
      const incomeStatusResponse = waitForIncomeStatusBatch(page);
      await page.getByRole("button", { name: "标记现金收入" }).click();
      expect((await mark("apiLatencyMs", incomeStatusResponse)).status()).toBe(200);
      await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSubmit);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("现金收入")).toBeVisible());
    });
    await expect.poll(() => api.count("PUT /api/pending-invoices/income-statuses")).toBe(2);
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSubmit);
    await expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("现金收入")).toBeVisible();
    await expect(page.getByRole("row", { name: /收入批量客户B/ }).getByText("现金收入")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toHaveCount(0);
    expect(api.count("PUT /api/pending-invoices/rows/income-batch-a/income-status")).toBe(0);
    expect(api.count("PUT /api/pending-invoices/rows/income-batch-b/income-status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("surfaces rejected income status batches without clearing selection or changing rows", async ({ page }, testInfo) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceIncomeBatchRows: true,
      pendingInvoiceIncomeStatusError: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-income-status-rejected",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.prepare-income-status-rejected",
      visibleLabel: "收入批量选择",
      actionType: "click",
    }, async (mark) => {
      await openIncomeDirection(page);
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户A" }));
      await setCheckbox(page.getByRole("checkbox", { name: "选择流水 收入批量客户B" }));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    const rowsBeforeSubmit = api.count("GET /api/pending-invoices/rows");

    await recordLatency({
      operationId: "pending-invoices.mark-income-no-invoice-rejected",
      visibleLabel: "标记无需开票",
      actionType: "click",
    }, async (mark) => {
      const incomeStatusResponse = waitForIncomeStatusBatch(page);
      await page.getByRole("button", { name: "标记无需开票" }).click();
      expect((await mark("apiLatencyMs", incomeStatusResponse)).status()).toBe(409);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("收入状态批量校验失败，未写入任何流水。"));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    await expect(page.getByRole("alert")).toContainText("收入状态批量校验失败，未写入任何流水。");
    expect(api.count("PUT /api/pending-invoices/income-statuses")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/income-statuses")).toMatchObject({
      status_code: "income_no_invoice_required",
      transaction_ids: ["income-batch-a", "income-batch-b"],
    });
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforeSubmit);
    await expect(page.getByRole("row", { name: /收入批量客户A/ }).getByText("未开票")).toBeVisible();
    await expect(page.getByRole("row", { name: /收入批量客户B/ }).getByText("未开票")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toBeVisible();
    expect(browserErrors.filter((error) => !error.includes("status of 409"))).toEqual([]);
    diagnostics.dispose();
  });
});
