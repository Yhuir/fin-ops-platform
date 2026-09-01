import { Buffer } from "node:buffer";

import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder, type OperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

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
  page.on("response", (response) => {
    if (response.status() >= 500) {
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

function unexpectedRuntimeErrors(errors: string[], allowed: RegExp[] = []) {
  return errors.filter((error) => !allowed.some((pattern) => pattern.test(error)));
}

function responsePathMatches(responseUrl: string, pathname: string) {
  return new URL(responseUrl).pathname === pathname;
}

function createInvoiceImportLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/imports/invoices",
    pageKey: "imports-invoices",
    module: "imports-invoices",
  });
}

function waitForImportPreview(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "POST"
      && responsePathMatches(response.url(), "/imports/files/preview"));
}

function waitForImportConfirm(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "POST"
      && responsePathMatches(response.url(), "/imports/files/confirm"));
}

async function expectDirectCanonicalResponse(
  responsePromise: Promise<{ json(): Promise<unknown> }>,
) {
  const payload = await (await responsePromise).json() as Record<string, unknown>;
  expect(payload).not.toHaveProperty("read_model_status");
  expect(payload).not.toHaveProperty("source_versions");
  expect(payload).not.toHaveProperty("refresh_enqueued");
  return payload;
}

async function previewInvoiceFiles(
  page: Page,
  options: {
    expectedAudit?: { importable: number; existing: number };
    recordLatency?: OperationLatencyRecorder;
  } = {},
) {
  const expectedAudit = options.expectedAudit ?? {
    importable: 22,
    existing: 2,
  };
  await stageInvoiceFilesForPreview(page, options.recordLatency);

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeEnabled();
  if (options.recordLatency) {
    await options.recordLatency({
      operationId: "imports-invoices.preview-files",
      visibleLabel: "开始预览",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForImportPreview(page);
      await previewButton.click();
      await mark("apiLatencyMs", previewResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByLabel(`新增 ${expectedAudit.importable}`)).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByLabel(`APP 已存在 ${expectedAudit.existing}`)).toBeVisible());
    });
  } else {
    await previewButton.click();
  }

  await expect(page.getByLabel(`新增 ${expectedAudit.importable}`)).toBeVisible();
  await expect(page.getByLabel(`APP 已存在 ${expectedAudit.existing}`)).toBeVisible();
  await expect(page.getByRole("grid", { name: "导入预览结果" })).toHaveCount(0);
  await expect(page.getByText("已完成 2 个文件的预览识别。")).toHaveCount(0);
}

async function stageInvoiceFilesForPreview(page: Page, recordLatency?: OperationLatencyRecorder) {
  if (recordLatency) {
    await recordLatency({
      operationId: "imports-invoices.open-page",
      visibleLabel: "发票导入",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/imports/invoices");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("import-workflow-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "发票导入" })).toBeVisible());
    });
  } else {
    await page.goto("/imports/invoices");
    await expect(page.getByTestId("import-workflow-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "发票导入" })).toBeVisible();
  }

  const filePayloads = [
    {
      name: "一月发票.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("invoice-import-e2e-output"),
    },
    {
      name: "二月发票.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("invoice-import-e2e-input"),
    },
  ];
  if (recordLatency) {
    await recordLatency({
      operationId: "imports-invoices.select-files",
      visibleLabel: "选择文件",
      actionType: "upload",
    }, async (mark) => {
      await page.locator('input[type="file"]').setInputFiles(filePayloads);
      await mark("finalSettledLatencyMs", expect(page.getByLabel("票据方向 一月发票.xlsx")).toBeVisible());
    });
  } else {
    await page.locator('input[type="file"]').setInputFiles(filePayloads);
  }

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeDisabled();
  if (recordLatency) {
    await recordLatency({
      operationId: "imports-invoices.select-invoice-directions",
      visibleLabel: "票据方向",
      actionType: "select",
    }, async (mark) => {
      await page.getByLabel("票据方向 一月发票.xlsx").selectOption("output_invoice");
      await page.getByLabel("票据方向 二月发票.xlsx").selectOption("input_invoice");
      await mark("finalSettledLatencyMs", expect(previewButton).toBeEnabled());
    });
  } else {
    await page.getByLabel("票据方向 一月发票.xlsx").selectOption("output_invoice");
    await page.getByLabel("票据方向 二月发票.xlsx").selectOption("input_invoice");
  }
}

test.describe("invoice import browser flow", () => {
  test("clear discards the current preview and returns to a fresh page", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await previewInvoiceFiles(page);
    await page.getByRole("button", { name: "清空" }).click();

    await expect(page.getByText("当前还没有选择文件。")).toBeVisible();
    await expect(page.getByLabel("新增 22")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "清空" })).toBeDisabled();
    expect(api.count("POST /imports/files/discard")).toBe(1);
  });

  test("previews and confirms input/output invoice files without cross-page barriers", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await previewInvoiceFiles(page, { recordLatency });
    expect(api.count("GET /imports/files/sessions/import_session_e2e_invoice/review-rows")).toBe(0);
    await page.getByRole("button", { name: "查看未处理明细" }).click();
    await expect(page.getByRole("tab", { name: /重复项 2/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("同文件重复");
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("浏览器销项客户");
    expect(api.count("GET /imports/files/sessions/import_session_e2e_invoice/review-rows")).toBe(1);
    await page.getByRole("button", { name: "关闭抽屉" }).click();
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await recordLatency({
      operationId: "imports-invoices.confirm-import",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("当前还没有选择文件。")).toBeVisible());
    });

    await expect(page.getByText("已确认导入")).toBeVisible();
    await expect(page.getByText("当前还没有选择文件。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("confirms invoice import and observes downstream canonical pages", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportDownstreamFanout: true,
      sessionMode: "full_access",
    });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await previewInvoiceFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-invoices.confirm-import-downstream",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("已确认导入")).toBeVisible());
    });
    await expect(page.getByText("已确认导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);

    let outputRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/output-invoice-collections",
      pageKey: "output-invoice-collections",
      module: "output-invoice-collections",
      operationId: "output-invoice-collections.open-after-invoice-import",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const outputRowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/output-invoice-collections/rows")
        && response.status() === 200);
      await page.goto("/output-invoice-collections");
      outputRowsPayload = await mark("apiLatencyMs", outputRowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expectDirectCanonicalResponse(Promise.resolve(outputRowsPayload!));
    await expect(page.getByText("XSFP-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入销项客户")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    let inputRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/input-invoice-usage",
      pageKey: "input-invoice-usage",
      module: "input-invoice-usage",
      operationId: "input-invoice-usage.open-after-invoice-import",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const inputRowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/input-invoice-usage/rows")
        && response.status() === 200);
      await page.goto("/input-invoice-usage");
      inputRowsPayload = await mark("apiLatencyMs", inputRowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expectDirectCanonicalResponse(Promise.resolve(inputRowsPayload!));
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入进项供应商")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    let taxOffsetPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/tax-offset",
      pageKey: "tax-offset",
      module: "tax-offset",
      operationId: "tax-offset.open-after-invoice-import",
      visibleLabel: "税金抵扣",
      actionType: "navigate",
    }, async (mark) => {
      const taxOffsetResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/tax-offset")
        && response.status() === 200);
      await page.goto("/tax-offset");
      taxOffsetPayload = await mark("apiLatencyMs", taxOffsetResponse);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    const taxPayload = await expectDirectCanonicalResponse(Promise.resolve(taxOffsetPayload!));
    expect(taxPayload.canonical_snapshot_version).toEqual(expect.any(String));
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入进项供应商")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    let pendingRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/pending-invoices",
      pageKey: "pending-invoices",
      module: "pending-invoices",
      operationId: "pending-invoices.open-after-invoice-import",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      const pendingRowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/pending-invoices/rows")
        && response.status() === 200);
      await page.goto("/pending-invoices");
      pendingRowsPayload = await mark("apiLatencyMs", pendingRowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expectDirectCanonicalResponse(Promise.resolve(pendingRowsPayload!));
    const importedPendingRow = page
      .getByRole("gridcell", { name: /SD-INV-IMPORT-E2E-001/ })
      .locator("xpath=ancestor::*[@role='row'][1]");
    await expect(importedPendingRow).toBeVisible();
    await expect(importedPendingRow).toContainText("发票导入进项供应商");
    await expect(importedPendingRow).toContainText("已支付已开票");
    await expectNoUnexpectedSuccessUiErrors(page);

    let oaRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/oa-pending-payments",
      pageKey: "oa-pending-payments",
      module: "oa-pending-payments",
      operationId: "oa-pending-payments.open-after-invoice-import",
      visibleLabel: "OA待付款核对",
      actionType: "navigate",
    }, async (mark) => {
      const oaRowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/oa-pending-payments/rows")
        && response.status() === 200);
      await page.goto("/oa-pending-payments");
      oaRowsPayload = await mark("apiLatencyMs", oaRowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("oa-pending-payments-page")).toBeVisible());
    });
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    await expectDirectCanonicalResponse(Promise.resolve(oaRowsPayload!));
    await expect(page.getByText("发票导入待付款申请人")).toBeVisible();
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByRole("row", { name: /发票导入待付款申请人/ })).toContainText("已支付");
    await expectNoUnexpectedSuccessUiErrors(page);

    let costRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-invoice-import",
      visibleLabel: "成本统计",
      actionType: "navigate",
    }, async (mark) => {
      const costRowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
        && response.status() === 200);
      await page.goto("/cost-statistics");
      costRowsPayload = await mark("apiLatencyMs", costRowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expectDirectCanonicalResponse(Promise.resolve(costRowsPayload!));
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.switch-project-view-after-invoice-import",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按项目" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /发票导入成本项目/ })).toHaveCount(0));
    });
    await expect(page.getByText("发票导入进项成本")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("keeps corrupt invoice files as file-level errors while confirming only valid invoice files", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportIncludeCorruptFile: true,
      sessionMode: "full_access",
    });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await previewInvoiceFiles(page, {
      expectedAudit: { importable: 11, existing: 1 },
      recordLatency,
    });

    const fileResults = page.getByLabel("文件处理结果");
    await expect(fileResults).toContainText("一月发票.xlsx");
    await expect(fileResults).toContainText("无法识别");
    await expect(fileResults).toContainText("文件损坏，无法读取发票明细。");
    await expect(fileResults).toContainText("二月发票.xlsx");
    await expect(fileResults).toContainText("待确认");
    await page.getByRole("button", { name: "查看未处理明细" }).click();
    await expect(page.getByRole("tab", { name: /未处理项 4/ })).toBeVisible();
    await recordLatency({
      operationId: "imports-invoices.open-skipped-files-tab",
      visibleLabel: "未处理项 4",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("tab", { name: /未处理项 4/ }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "未处理项明细" })).toContainText("文件损坏，无法读取发票明细。"));
    });
    await expect(page.getByRole("grid", { name: "未处理项明细" })).toContainText("文件损坏，无法读取发票明细。");
    await page.getByRole("button", { name: "关闭抽屉" }).click();

    await recordLatency({
      operationId: "imports-invoices.confirm-import-with-corrupt-file",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("已确认导入")).toBeVisible());
    });

    await expect(page.getByText("已确认导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.lastBody("POST /imports/files/confirm")).toMatchObject({
      selected_file_ids: ["invoice_import_file_e2e_2"],
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("locks import actions while slow invoice preview is in flight", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportPreviewDelayMs: 500,
      sessionMode: "full_access",
    });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await stageInvoiceFilesForPreview(page, recordLatency);
    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeEnabled();

    const previewingButton = page.getByRole("button", { name: "预览中..." });
    await recordLatency({
      operationId: "imports-invoices.preview-files-slow",
      visibleLabel: "开始预览",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForImportPreview(page);
      await previewButton.click();
      await mark("firstVisibleResponseLatencyMs", expect(previewingButton).toBeDisabled());
      await expect(page.getByRole("button", { name: "清空" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
      await mark("apiLatencyMs", previewResponse);
      await mark("finalSettledLatencyMs", expect(page.getByLabel("新增 22")).toBeVisible());
    });
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await expect(page.getByLabel("新增 22")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始预览" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "清空" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeEnabled();
    expect(api.count("POST /imports/files/preview")).toBe(1);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("surfaces preview stale errors without creating an import job or refreshing downstream pages", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportConfirmPreviewStale: true,
      sessionMode: "full_access",
    });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await previewInvoiceFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-invoices.confirm-import-preview-stale",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("预览后数据已变化，请重新预览后再确认。")).toBeVisible());
    });

    await expect(page.getByText("预览后数据已变化，请重新预览后再确认。")).toBeVisible();
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/409/])).toEqual([]);
  });

  test("keeps confirm failures visible without reporting import success", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportConfirmError: true,
      sessionMode: "full_access",
    });
    const recordLatency = createInvoiceImportLatencyRecorder(page, testInfo);

    await previewInvoiceFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-invoices.confirm-import-server-error",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("发票导入任务创建失败，请稍后重试。")).toBeVisible());
    });

    await expect(page.getByText("发票导入任务创建失败，请稍后重试。")).toBeVisible();
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/500/])).toEqual([]);
  });
});
