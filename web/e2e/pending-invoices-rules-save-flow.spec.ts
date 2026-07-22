import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

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

function waitForPendingInvoiceRulesSave(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "PUT"
      && url.pathname === "/api/pending-invoices/rules";
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

test.describe("pending invoices rules save browser flow", () => {
  test("saves expense rules without a write-time barrier and reloads the current page", async ({ page }, testInfo) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRulesSaveFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-rules-save",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible());
    });
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    const rowsBeforeSave = api.count("GET /api/pending-invoices/rows");
    const barriersBeforeSave = api.count("POST /api/operation-barrier/status");

    await recordLatency({
      operationId: "pending-invoices.open-expense-rules-drawer",
      visibleLabel: "支出待找发票规则设置",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "支出待找发票规则设置" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible());
    });
    await expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible();
    const statementAsInvoiceGroup = page.getByRole("group", { name: "流水代替发票" });
    await recordLatency({
      operationId: "pending-invoices.check-rule-equipment-payment",
      visibleLabel: "设备款",
      actionType: "check",
    }, async (mark) => {
      await statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" }).check();
      await mark("finalSettledLatencyMs", expect(statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" })).toBeChecked());
    });
    await recordLatency({
      operationId: "pending-invoices.save-expense-rules",
      visibleLabel: "保存规则",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = waitForPendingInvoiceRulesSave(page);
      await page.getByRole("button", { name: "保存规则" }).click();
      expect((await mark("apiLatencyMs", saveResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave));
    });

    await expect.poll(() => api.count("PUT /api/pending-invoices/rules")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/rules")).toMatchObject({
      direction: "expense",
      groups: {
        bank_statement_as_invoice: { tag_codes: ["equipment_payment"] },
        no_invoice_required: { tag_codes: [] },
      },
      version: 1,
    });

    expect(api.count("POST /api/operation-barrier/status")).toBe(barriersBeforeSave);
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(page.getByRole("status").filter({ hasText: "规则已保存。" })).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("keeps rule drafts recoverable after a transient save failure", async ({ page }, testInfo) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRulesSaveFailuresBeforeSuccess: 1,
      pendingInvoiceRulesSaveFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-rules-save-failure",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const rowsBeforeSave = api.count("GET /api/pending-invoices/rows");
    const barrierBeforeSave = api.count("POST /api/operation-barrier/status");

    await recordLatency({
      operationId: "pending-invoices.open-expense-rules-drawer-before-failure",
      visibleLabel: "支出待找发票规则设置",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "支出待找发票规则设置" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible());
    });
    await expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible();
    const statementAsInvoiceGroup = page.getByRole("group", { name: "流水代替发票" });
    await recordLatency({
      operationId: "pending-invoices.check-rule-equipment-before-failure",
      visibleLabel: "设备款",
      actionType: "check",
    }, async (mark) => {
      await statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" }).check();
      await mark("finalSettledLatencyMs", expect(statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" })).toBeChecked());
    });

    await recordLatency({
      operationId: "pending-invoices.save-expense-rules-failed",
      visibleLabel: "保存规则",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = waitForPendingInvoiceRulesSave(page);
      await page.getByRole("button", { name: "保存规则" }).click();
      expect((await mark("apiLatencyMs", saveResponse)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("待找发票规则保存暂时失败，请重试。"));
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "保存规则" })).toBeEnabled());
    });
    await expect.poll(() => api.count("PUT /api/pending-invoices/rules")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/rules")).toMatchObject({
      direction: "expense",
      groups: {
        bank_statement_as_invoice: { tag_codes: ["equipment_payment"] },
        no_invoice_required: { tag_codes: [] },
      },
      version: 1,
    });
    await expect(page.getByRole("alert")).toContainText("待找发票规则保存暂时失败，请重试。");
    await expect(page.getByRole("button", { name: "保存规则" })).toBeEnabled();
    await expect(statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" })).toBeChecked();
    expect(api.count("POST /api/operation-barrier/status")).toBe(barrierBeforeSave);
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforeSave);
    await expect(page.getByRole("status").filter({ hasText: "规则已保存" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "全局操作进度" })).toHaveCount(0);

    await recordLatency({
      operationId: "pending-invoices.save-expense-rules-retry",
      visibleLabel: "保存规则",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = waitForPendingInvoiceRulesSave(page);
      await page.getByRole("button", { name: "保存规则" }).click();
      expect((await mark("apiLatencyMs", saveResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave));
    });
    await expect.poll(() => api.count("PUT /api/pending-invoices/rules")).toBe(2);
    expect(api.count("POST /api/operation-barrier/status")).toBe(barrierBeforeSave);
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(page.getByRole("status").filter({ hasText: "规则已保存。" })).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
