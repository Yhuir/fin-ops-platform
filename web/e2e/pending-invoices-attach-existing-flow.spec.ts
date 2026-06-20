import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function startStrictBrowserErrorCapture(
  page: Page,
  options: { allowedConsoleErrors?: RegExp[]; allowedResponses?: RegExp[] } = {},
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
  page.on("response", (response) => {
    if (response.status() >= 400) {
      const signature = `${response.status()} ${response.request().method()} ${response.url()}`;
      if (options.allowedResponses?.some((pattern) => pattern.test(signature))) {
        return;
      }
      errors.push(`response:${response.status()} ${response.request().method()} ${response.url()}`);
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

test.describe("pending invoices attach existing invoice browser flow", () => {
  test("previews and confirms selected expense rows with existing input invoices then refreshes rows", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceAttachExistingBatchRows: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    const rowsBeforeConfirm = api.count("GET /api/pending-invoices/rows");

    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).check();
    await expect(page.getByText("已选 2 条流水")).toBeVisible();
    await expect(page.getByText("流水合计 65,540.00")).toBeVisible();

    await page.getByRole("button", { name: "选择发票" }).click();
    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await expect(picker).toBeVisible();
    await expect(picker.getByRole("table", { name: "发票候选" })).toBeVisible();
    await expect(picker.getByRole("columnheader", { name: "流水关联" })).toBeVisible();
    await expect(picker.getByText("未关联流水")).toBeVisible();
    await expect(picker.getByText("已关联流水", { exact: true })).toBeVisible();
    await expect(picker.getByText("1 条已关联流水")).toBeVisible();

    const candidateSearchRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      if (request.method() !== "POST" || !url.pathname.endsWith("/api/pending-invoices/invoice-candidates/batch")) {
        return false;
      }
      const body = JSON.parse(request.postData() || "{}") as { seller_name?: string };
      return body.seller_name === "智能工厂";
    });
    await picker.getByLabel("销方").fill("智能工厂");
    await picker.getByRole("button", { name: "搜索" }).click();
    await candidateSearchRequest;
    expect(api.lastBody("POST /api/pending-invoices/invoice-candidates/batch")).toMatchObject({
      page_size: 20,
      seller_name: "智能工厂",
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });

    await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).check();
    await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-002" }).check();
    await expect(picker.getByText("已选发票金额")).toBeVisible();
    await expect(picker.getByText("本次选择差额")).toBeVisible();
    await expect(picker.getByText("0.00", { exact: true })).toBeVisible();

    await picker.getByRole("button", { name: "预览关联" }).click();
    await expect(picker.getByText("pending_invoice_attach_existing:batch")).toBeVisible();
    await expect(picker.getByText("关联后待付 0.00")).toBeVisible();
    expect(api.lastBody("POST /api/pending-invoices/attach-existing-invoices/preview")).toMatchObject({
      invoice_ids: ["iv-o-202603-001", "iv-o-202603-002"],
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });

    await picker.getByRole("button", { name: "确认建立关系" }).click();
    await expect(picker).toBeHidden();
    expect(api.lastBody("POST /api/pending-invoices/attach-existing-invoices")).toMatchObject({
      invoice_ids: ["iv-o-202603-001", "iv-o-202603-002"],
      preview_id: "attach-preview-batch",
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeConfirm);

    const firstRow = page.getByRole("row", { name: /智能工厂设备商/ }).first();
    const secondRow = page.getByRole("row", { name: /智能工厂设备商二号/ });
    await expect(firstRow.getByText("已支付已开票")).toBeVisible();
    await expect(firstRow.getByText("12561048")).toBeVisible();
    await expect(secondRow.getByText("已支付已开票")).toBeVisible();
    await expect(secondRow.getByText("12561049")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("keeps attach-existing confirmation recoverable after a transient relation failure", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
      allowedResponses: [/503 POST .*\/api\/pending-invoices\/attach-existing-invoices$/],
    });
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceAttachExistingBatchRows: true,
      pendingInvoiceAttachExistingConfirmFailuresBeforeSuccess: 1,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    const rowsBeforeConfirm = api.count("GET /api/pending-invoices/rows");

    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).check();
    await page.getByRole("button", { name: "选择发票" }).click();
    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await expect(picker).toBeVisible();
    await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).check();
    await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-002" }).check();
    await picker.getByRole("button", { name: "预览关联" }).click();
    await expect(picker.getByText("pending_invoice_attach_existing:batch")).toBeVisible();
    await expect(picker.getByText("关联后待付 0.00")).toBeVisible();

    const failedConfirm = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "POST"
        && url.pathname === "/api/pending-invoices/attach-existing-invoices";
    });
    await picker.getByRole("button", { name: "确认建立关系" }).click();
    expect((await failedConfirm).status()).toBe(503);
    expect(api.count("POST /api/pending-invoices/attach-existing-invoices")).toBe(1);
    expect(api.lastBody("POST /api/pending-invoices/attach-existing-invoices")).toMatchObject({
      invoice_ids: ["iv-o-202603-001", "iv-o-202603-002"],
      preview_id: "attach-preview-batch",
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });
    await expect(picker).toBeVisible();
    await expect(picker.getByText("选择已有发票关系确认暂时失败，请重试。")).toBeVisible();
    await expect(picker.getByRole("button", { name: "确认建立关系" })).toBeEnabled();
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforeConfirm);
    await expect(page.getByRole("row", { name: /智能工厂设备商/ }).first().getByText("已支付待开票")).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商二号/ }).getByText("已支付待开票")).toBeVisible();
    await expect(page.getByText("12561048")).toHaveCount(0);

    const recoveredConfirm = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "POST"
        && url.pathname === "/api/pending-invoices/attach-existing-invoices";
    });
    await picker.getByRole("button", { name: "确认建立关系" }).click();
    expect((await recoveredConfirm).status()).toBe(200);
    expect(api.count("POST /api/pending-invoices/attach-existing-invoices")).toBe(2);

    await expect(picker).toBeHidden();
    await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeConfirm);
    const firstRow = page.getByRole("row", { name: /智能工厂设备商/ }).first();
    const secondRow = page.getByRole("row", { name: /智能工厂设备商二号/ });
    await expect(firstRow.getByText("已支付已开票")).toBeVisible();
    await expect(firstRow.getByText("12561048")).toBeVisible();
    await expect(secondRow.getByText("已支付已开票")).toBeVisible();
    await expect(secondRow.getByText("12561049")).toBeVisible();
    await expect(page.getByText("已选 2 条流水")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("shows preview conflicts and blocks confirm without a half-written relation", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceAttachExistingPreviewConflict: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    const rowsBeforePreview = api.count("GET /api/pending-invoices/rows");

    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
    await page.getByRole("button", { name: "选择发票" }).click();
    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await expect(picker).toBeVisible();
    await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).check();
    await picker.getByRole("button", { name: "预览关联" }).click();

    await expect(picker.getByText("不可确认原因")).toBeVisible();
    await expect(picker.getByText("关系 CASE-CONFLICT-202603，模式 manual_confirmed，对象 bk-o-202603-001, iv-o-202603-001")).toBeVisible();
    await expect(picker.getByRole("button", { name: "确认建立关系" })).toBeDisabled();
    expect(api.count("POST /api/pending-invoices/attach-existing-invoices")).toBe(0);
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforePreview);
    await expect(page.getByRole("row", { name: /智能工厂设备商/ }).getByText("已支付待开票")).toBeVisible();
    await expect(page.getByText("12561048")).toHaveCount(0);

    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
