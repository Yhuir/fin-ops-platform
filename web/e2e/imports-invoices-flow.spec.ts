import { Buffer } from "node:buffer";

import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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

async function expectDirectPayloadResponse(responsePromise: Promise<{ json(): Promise<unknown> }>) {
  const payload = await (await responsePromise).json() as Record<string, unknown>;
  expect(payload.read_model_status).toBeUndefined();
  expect(payload.read_model_scope_key).toBeUndefined();
  expect(payload.read_model_stale_reasons).toBeUndefined();
}

async function previewInvoiceFiles(
  page: Page,
  expectedAudit: { error: number; importable: number; original: number; review: number; skipped: number } = {
    error: 1,
    importable: 22,
    original: 28,
    review: 2,
    skipped: 4,
  },
) {
  await stageInvoiceFilesForPreview(page);

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeEnabled();
  await previewButton.click();

  await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
  await expect(page.getByLabel(`审计汇总 原始 ${expectedAudit.original}`)).toBeVisible();
  await expect(page.getByLabel(`审计汇总 可导入 ${expectedAudit.importable}`)).toBeVisible();
  await expect(page.getByLabel(`审计汇总 异常 ${expectedAudit.error}`)).toBeVisible();
  await expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible();
  await expect(page.getByText(new RegExp(`将导入 ${expectedAudit.importable} 条唯一记录，跳过 ${expectedAudit.skipped} 条重复，${expectedAudit.review} 条需复核`))).toBeVisible();
}

async function stageInvoiceFilesForPreview(page: Page) {
  await page.goto("/imports/invoices");
  await expect(page.getByTestId("import-workflow-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "发票导入" })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles([
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
  ]);

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeDisabled();
  await page.getByLabel("票据方向 一月发票.xlsx").selectOption("output_invoice");
  await page.getByLabel("票据方向 二月发票.xlsx").selectOption("input_invoice");
}

test.describe("invoice import browser flow", () => {
  test("previews and confirms input/output invoice files, then refreshes the workbench state", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await previewInvoiceFiles(page);
    await expect(page.getByRole("tab", { name: /重复项 1/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("同文件重复");
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("浏览器销项客户");
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已确认导入")).toBeVisible();
    await expect(page.getByText("当前还没有选择文件。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("confirms invoice import and observes downstream direct payloads", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportDownstreamFanout: true,
      sessionMode: "full_access",
    });

    await previewInvoiceFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();
    await expect(page.getByText("已确认导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);

    const outputRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/output-invoice-collections/rows")
      && response.status() === 200);
    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expectDirectPayloadResponse(outputRowsResponse);
    await expect(page.getByText("XSFP-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入销项客户")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const inputRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/input-invoice-usage/rows")
      && response.status() === 200);
    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expectDirectPayloadResponse(inputRowsResponse);
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入进项供应商")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const taxOffsetResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/tax-offset")
      && response.status() === 200);
    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expectDirectPayloadResponse(taxOffsetResponse);
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByText("发票导入进项供应商")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const pendingRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/pending-invoices/rows")
      && response.status() === 200);
    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expectDirectPayloadResponse(pendingRowsResponse);
    const importedPendingRow = page.getByRole("row", { name: /SD-INV-IMPORT-E2E-001/ });
    await expect(importedPendingRow).toBeVisible();
    await expect(importedPendingRow).toContainText("发票导入进项供应商");
    await expect(importedPendingRow).toContainText("已支付已开票");
    await expectNoUnexpectedSuccessUiErrors(page);

    const oaRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/oa-pending-payments/rows")
      && response.status() === 200);
    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    await expectDirectPayloadResponse(oaRowsResponse);
    await expect(page.getByText("发票导入待付款申请人")).toBeVisible();
    await expect(page.getByText("SD-INV-IMPORT-E2E-001")).toBeVisible();
    await expect(page.getByRole("row", { name: /发票导入待付款申请人/ })).toContainText("已支付");
    await expectNoUnexpectedSuccessUiErrors(page);

    const costRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expectDirectPayloadResponse(costRowsResponse);
    await page.getByRole("button", { name: "按项目" }).click();
    const importedCostProject = page.getByRole("button", { name: /发票导入成本项目/ });
    await expect(importedCostProject).toBeVisible();
    await expect(importedCostProject).toContainText("18,320.00");
    await importedCostProject.click();
    await page.getByRole("button", { name: /设备货款及材料费/ }).click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("发票导入进项成本");
    await expect(projectRows).toContainText("发票导入进项供应商");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("keeps corrupt invoice files as file-level errors while confirming only valid invoice files", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportIncludeCorruptFile: true,
      sessionMode: "full_access",
    });

    await previewInvoiceFiles(page, { error: 1, importable: 11, original: 15, review: 2, skipped: 2 });

    const previewGrid = page.getByRole("grid", { name: "导入预览结果" });
    await expect(previewGrid).toContainText("一月发票.xlsx");
    await expect(previewGrid).toContainText("无法识别");
    await expect(previewGrid).toContainText("文件损坏，无法读取发票明细。");
    await expect(previewGrid).toContainText("二月发票.xlsx");
    await expect(previewGrid).toContainText("待确认");
    await expect(page.getByRole("tab", { name: /未导入项 1/ })).toBeVisible();
    await page.getByRole("tab", { name: /未导入项 1/ }).click();
    await expect(page.getByRole("grid", { name: "未导入项明细" })).toContainText("文件损坏，无法读取发票明细。");

    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已确认导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.lastBody("POST /imports/files/confirm")).toMatchObject({
      selected_file_ids: ["invoice_import_file_e2e_2"],
    });
    expect(api.count("GET /api/workbench")).toBeGreaterThan(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("locks import actions while slow invoice preview is in flight", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportPreviewDelayMs: 500,
      sessionMode: "full_access",
    });

    await stageInvoiceFilesForPreview(page);
    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeEnabled();

    await previewButton.click();
    const previewingButton = page.getByRole("button", { name: "预览中..." });
    await expect(previewingButton).toBeDisabled();
    await expect(page.getByRole("button", { name: "清空" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始预览" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "清空" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeEnabled();
    expect(api.count("POST /imports/files/preview")).toBe(1);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("surfaces preview stale errors without creating an import job or refreshing downstream pages", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportConfirmPreviewStale: true,
      sessionMode: "full_access",
    });

    await previewInvoiceFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("预览后数据已变化，请重新预览后再确认。")).toBeVisible();
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("GET /api/workbench")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/409/])).toEqual([]);
  });

  test("keeps confirm failures visible without reporting import success", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      invoiceImportConfirmError: true,
      sessionMode: "full_access",
    });

    await previewInvoiceFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("发票导入任务创建失败，请稍后重试。")).toBeVisible();
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("GET /api/workbench")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/500/])).toEqual([]);
  });
});
