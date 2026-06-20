import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

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
  test("saves expense rules through the pending invoice freshness barrier and refreshes rows", async ({ page }) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRulesSaveFlow: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    const rowsBeforeSave = api.count("GET /api/pending-invoices/rows");

    await page.getByRole("button", { name: "支出待找发票规则设置" }).click();
    await expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible();
    const statementAsInvoiceGroup = page.getByRole("group", { name: "流水代替发票" });
    await statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" }).check();
    await page.getByRole("button", { name: "保存规则" }).click();

    await expect.poll(() => api.count("PUT /api/pending-invoices/rules")).toBe(1);
    expect(api.lastBody("PUT /api/pending-invoices/rules")).toMatchObject({
      direction: "expense",
      groups: {
        bank_statement_as_invoice: { tag_codes: ["equipment_payment"] },
        no_invoice_required: { tag_codes: [] },
      },
      version: 1,
    });

    await expect.poll(() => api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);
    expect(api.lastBody("POST /api/operation-barrier/status")).toMatchObject({
      targets: [
        {
          read_model_key: "pending_invoice",
          scope_key: "expense:requires_invoice",
        },
      ],
    });
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(page.getByRole("status").filter({ hasText: "规则已保存，相关数据正在刷新。" })).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("keeps rule drafts recoverable after a transient save failure", async ({ page }) => {
    const browserErrors = startBrowserRuntimeErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRulesSaveFailuresBeforeSuccess: 1,
      pendingInvoiceRulesSaveFlow: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    const rowsBeforeSave = api.count("GET /api/pending-invoices/rows");
    const barrierBeforeSave = api.count("POST /api/operation-barrier/status");

    await page.getByRole("button", { name: "支出待找发票规则设置" }).click();
    await expect(page.getByTestId("pending-invoice-rules-grid")).toBeVisible();
    const statementAsInvoiceGroup = page.getByRole("group", { name: "流水代替发票" });
    await statementAsInvoiceGroup.getByRole("checkbox", { name: "设备款" }).check();

    await page.getByRole("button", { name: "保存规则" }).click();
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

    await page.getByRole("button", { name: "保存规则" }).click();
    await expect.poll(() => api.count("PUT /api/pending-invoices/rules")).toBe(2);
    await expect.poll(() => api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierBeforeSave);
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeSave);
    await expect(page.getByRole("status").filter({ hasText: "规则已保存，相关数据正在刷新。" })).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
