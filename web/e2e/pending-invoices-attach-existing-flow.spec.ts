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

function waitForInvoiceCandidatesBatch(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname.endsWith("/api/pending-invoices/invoice-candidates/batch");
  });
}

function waitForAttachExistingPreview(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname.endsWith("/api/pending-invoices/attach-existing-invoices/preview");
  });
}

function waitForAttachExistingConfirm(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.pathname === "/api/pending-invoices/attach-existing-invoices";
  });
}

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
  test("previews and confirms selected expense rows with existing input invoices then refreshes rows", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceAttachExistingBatchRows: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-attach-existing",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ }).first()).toBeVisible());
    });
    const rowsBeforeConfirm = api.count("GET /api/pending-invoices/rows");

    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).check();
    await expect(page.getByText("已选 1 条流水")).toBeVisible();
    await expect(page.getByText("流水合计 7540.00")).toBeVisible();
    await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).uncheck();

    await recordLatency({
      operationId: "pending-invoices.select-attach-row-primary",
      visibleLabel: "选择流水 智能工厂设备商",
      actionType: "check",
    }, async (mark) => {
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 1 条流水")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.select-attach-row-secondary",
      visibleLabel: "选择流水 智能工厂设备商二号",
      actionType: "check",
    }, async (mark) => {
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    await expect(page.getByText("已选 2 条流水")).toBeVisible();
    await expect(page.getByText("流水合计 65540.00")).toBeVisible();

    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await recordLatency({
      operationId: "pending-invoices.open-attach-existing-picker",
      visibleLabel: "选择发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "选择发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(picker).toBeVisible());
      await mark("finalSettledLatencyMs", expect(picker.getByRole("table", { name: "发票候选" })).toBeVisible());
    });
    await expect(picker).toBeVisible();
    await expect(picker.getByRole("table", { name: "发票候选" })).toBeVisible();
    await expect(picker.getByRole("columnheader", { name: "流水关联" })).toBeVisible();
    await expect(picker.getByText("未关联流水")).toBeVisible();
    await expect(picker.getByText("已关联流水", { exact: true })).toBeVisible();
    await expect(picker.getByText("1 条已关联流水")).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.fill-attach-candidate-seller",
      visibleLabel: "销方",
      actionType: "fill",
    }, async (mark) => {
      await picker.getByLabel("销方").fill("智能工厂");
      await mark("finalSettledLatencyMs", expect(picker.getByLabel("销方")).toHaveValue("智能工厂"));
    });
    await recordLatency({
      operationId: "pending-invoices.search-attach-candidates",
      visibleLabel: "搜索",
      actionType: "click",
    }, async (mark) => {
      const candidateSearchResponse = waitForInvoiceCandidatesBatch(page);
      await picker.getByRole("button", { name: "搜索" }).click();
      expect((await mark("apiLatencyMs", candidateSearchResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(picker.getByText("未关联流水")).toBeVisible());
    });
    expect(api.lastBody("POST /api/pending-invoices/invoice-candidates/batch")).toMatchObject({
      page_size: 20,
      seller_name: "智能工厂",
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });

    await recordLatency({
      operationId: "pending-invoices.select-attach-invoice-primary",
      visibleLabel: "选择发票 DIG-EQP-001",
      actionType: "check",
    }, async (mark) => {
      await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).locator("xpath=ancestor::label").click();
      await mark("finalSettledLatencyMs", expect(picker.getByText("已选发票金额")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.select-attach-invoice-secondary",
      visibleLabel: "选择发票 DIG-EQP-002",
      actionType: "check",
    }, async (mark) => {
      await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-002" }).locator("xpath=ancestor::label").click();
      await mark("finalSettledLatencyMs", expect(picker.getByText("本次选择差额")).toBeVisible());
    });
    await expect(picker.getByText("已选发票金额")).toBeVisible();
    await expect(picker.getByText("本次选择差额")).toBeVisible();
    await expect(picker.getByText("0.00", { exact: true })).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.preview-attach-existing",
      visibleLabel: "预览关联",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForAttachExistingPreview(page);
      await picker.getByRole("button", { name: "预览关联" }).click();
      expect((await mark("apiLatencyMs", previewResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(picker.getByRole("status")).toContainText("关联后待付 0.00"));
    });
    await expect(picker.getByRole("status")).toContainText("关联后待付 0.00");
    expect(api.lastBody("POST /api/pending-invoices/attach-existing-invoices/preview")).toMatchObject({
      invoice_ids: ["iv-o-202603-001", "iv-o-202603-002"],
      transaction_ids: ["bk-o-202603-001", "bk-o-202603-002"],
    });

    await recordLatency({
      operationId: "pending-invoices.confirm-attach-existing",
      visibleLabel: "确认建立关系",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForAttachExistingConfirm(page);
      await picker.getByRole("button", { name: "确认建立关系" }).click();
      expect((await mark("apiLatencyMs", confirmResponse)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(picker).toBeHidden());
      await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeConfirm);
    });
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

  test("keeps attach-existing confirmation recoverable after a transient relation failure", async ({ page }, testInfo) => {
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
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-attach-existing-failure",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ }).first()).toBeVisible());
    });
    const rowsBeforeConfirm = api.count("GET /api/pending-invoices/rows");

    await recordLatency({
      operationId: "pending-invoices.select-attach-rows-before-failure",
      visibleLabel: "选择流水",
      actionType: "check",
    }, async (mark) => {
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商二号" }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 条流水")).toBeVisible());
    });
    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await recordLatency({
      operationId: "pending-invoices.open-attach-picker-before-failure",
      visibleLabel: "选择发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "选择发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(picker).toBeVisible());
    });
    await expect(picker).toBeVisible();
    await recordLatency({
      operationId: "pending-invoices.select-attach-invoices-before-failure",
      visibleLabel: "选择发票",
      actionType: "check",
    }, async (mark) => {
      await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).locator("xpath=ancestor::label").click();
      await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-002" }).locator("xpath=ancestor::label").click();
      await mark("finalSettledLatencyMs", expect(picker.getByText("本次选择差额")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.preview-attach-before-failure",
      visibleLabel: "预览关联",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForAttachExistingPreview(page);
      await picker.getByRole("button", { name: "预览关联" }).click();
      expect((await mark("apiLatencyMs", previewResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(picker.getByRole("status")).toContainText("关联后待付 0.00"));
    });
    await expect(picker.getByRole("status")).toContainText("关联后待付 0.00");

    await recordLatency({
      operationId: "pending-invoices.confirm-attach-existing-failed",
      visibleLabel: "确认建立关系",
      actionType: "click",
    }, async (mark) => {
      const failedConfirm = waitForAttachExistingConfirm(page);
      await picker.getByRole("button", { name: "确认建立关系" }).click();
      expect((await mark("apiLatencyMs", failedConfirm)).status()).toBe(503);
      await mark("firstVisibleResponseLatencyMs", expect(picker.getByText("选择已有发票关系确认暂时失败，请重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(picker.getByRole("button", { name: "确认建立关系" })).toBeEnabled());
    });
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

    await recordLatency({
      operationId: "pending-invoices.confirm-attach-existing-retry",
      visibleLabel: "确认建立关系",
      actionType: "click",
    }, async (mark) => {
      const recoveredConfirm = waitForAttachExistingConfirm(page);
      await picker.getByRole("button", { name: "确认建立关系" }).click();
      expect((await mark("apiLatencyMs", recoveredConfirm)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(picker).toBeHidden());
      await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(rowsBeforeConfirm);
    });
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

  test("shows preview conflicts and blocks confirm without a half-written relation", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceAttachExistingPreviewConflict: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-attach-conflict",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ }).first()).toBeVisible());
    });
    const rowsBeforePreview = api.count("GET /api/pending-invoices/rows");

    await recordLatency({
      operationId: "pending-invoices.select-attach-row-before-conflict",
      visibleLabel: "选择流水 智能工厂设备商",
      actionType: "check",
    }, async (mark) => {
      await page.getByRole("checkbox", { name: "选择流水 智能工厂设备商", exact: true }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 1 条流水")).toBeVisible());
    });
    const picker = page.getByRole("dialog", { name: "选择已有进项发票" });
    await recordLatency({
      operationId: "pending-invoices.open-attach-picker-before-conflict",
      visibleLabel: "选择发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "选择发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(picker).toBeVisible());
    });
    await expect(picker).toBeVisible();
    await recordLatency({
      operationId: "pending-invoices.select-attach-invoice-before-conflict",
      visibleLabel: "选择发票 DIG-EQP-001",
      actionType: "check",
    }, async (mark) => {
      await picker.getByRole("checkbox", { name: "选择发票 DIG-EQP-001" }).locator("xpath=ancestor::label").click();
      await mark("finalSettledLatencyMs", expect(picker.getByText("本次选择差额")).toBeVisible());
    });
    await recordLatency({
      operationId: "pending-invoices.preview-attach-conflict",
      visibleLabel: "预览关联",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForAttachExistingPreview(page);
      await picker.getByRole("button", { name: "预览关联" }).click();
      expect((await mark("apiLatencyMs", previewResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(picker.getByText("不可确认原因")).toBeVisible());
    });

    await expect(picker.getByText("不可确认原因")).toBeVisible();
    await expect(picker.getByRole("listitem")).toHaveText("所选数据已存在其他关联关系");
    await expect(picker.getByRole("button", { name: "确认建立关系" })).toBeDisabled();
    expect(api.count("POST /api/pending-invoices/attach-existing-invoices")).toBe(0);
    expect(api.count("GET /api/pending-invoices/rows")).toBe(rowsBeforePreview);
    await expect(page.getByRole("row", { name: /智能工厂设备商/ }).getByText("已支付待开票")).toBeVisible();
    await expect(page.getByText("12561048")).toHaveCount(0);

    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
