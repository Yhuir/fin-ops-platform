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

async function expectFreshReadModelResponse(responsePromise: Promise<{ json(): Promise<unknown> }>) {
  const payload = await (await responsePromise).json();
  expect(payload).toMatchObject({ read_model_status: "fresh" });
}

async function previewEtcZipFiles(page: Page) {
  await page.goto("/imports/etc-invoices");
  await expect(page.getByTestId("import-workflow-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "ETC发票导入" })).toBeVisible();
  await expect(page.getByText("请选择已确认的 ETC 对账任务后再预览 ETC zip。")).toBeVisible();

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeDisabled();
  await page.getByLabel("ETC对账任务", { exact: true }).selectOption("etc_task_ready_001");
  await expect(page.getByLabel("已选ETC对账任务")).toContainText("任务 2026-03 ETC 对账");

  await page.locator('input[type="file"]').setInputFiles([
    {
      name: "etc-2026-03.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("etc-import-e2e-a"),
    },
    {
      name: "etc-2026-04.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("etc-import-e2e-b"),
    },
  ]);

  await expect(previewButton).toBeEnabled();
  await previewButton.click();

  await expect(page.getByText("已完成 2 个 ETC zip 文件预览。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "ETC导入预览" })).toBeVisible();
  await expect(page.getByText("etc_import_session_e2e_001")).toBeVisible();
  await expect(page.getByLabel("审计汇总 原始 4")).toBeVisible();
  await expect(page.getByLabel("审计汇总 可导入 1")).toBeVisible();
  await expect(page.getByText("将导入 1 条唯一记录，跳过 2 条重复，1 条需复核。")).toBeVisible();
  await expect(page.getByRole("grid", { name: "ETC导入预览结果" })).toBeVisible();
  await expect(page.getByText("ETC-2026-005")).toBeVisible();
  await expect(page.getByText("新发票待导入")).toBeVisible();
  await expect(page.getByText("补充凭证匹配")).toBeVisible();
  await expect(page.getByText("XML 解析失败")).toBeVisible();
}

test.describe("ETC invoice import browser flow", () => {
  test("previews ETC zip files for a ready task and confirms the import job", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await previewEtcZipFiles(page);
    expect(api.count("GET /api/etc/reconciliation-tasks/ready-for-import")).toBeGreaterThan(0);
    expect(api.count("POST /api/etc/import/preview")).toBe(1);
    expect(api.count("POST /imports/files/preview")).toBe(0);

    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已开始后台导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("confirms ETC import and observes downstream read models as fresh", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      etcImportDownstreamFanout: true,
      sessionMode: "full_access",
    });

    await previewEtcZipFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已开始后台导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);

    const etcBatchResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/etc/business-batches")
      && response.status() === 200);
    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    const etcBatchPayload = await (await etcBatchResponse).json() as { items?: unknown[] };
    expect(etcBatchPayload.items).toHaveLength(1);
    const importedBatchRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(importedBatchRow).toBeVisible();
    await expect(importedBatchRow).toContainText("ETC-E2E-2026-03");
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const taxOffsetResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/tax-offset")
      && response.status() === 200);
    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expectFreshReadModelResponse(taxOffsetResponse);
    await expect(page.getByText("ETC导入通行服务商")).toBeVisible();
    await expect(page.getByText("ETC-2026-005")).toBeVisible();
    await expect(page.getByText(/读模型.*刷新|读模型.*失败|read model/i)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const costRowsResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expectFreshReadModelResponse(costRowsResponse);
    await page.getByRole("button", { name: "按项目" }).click();
    const etcCostProject = page.getByRole("button", { name: /ETC导入通行成本项目/ });
    await expect(etcCostProject).toBeVisible();
    await expect(etcCostProject).toContainText("32.26");
    await etcCostProject.click();
    await page.getByRole("button", { name: /通行费/ }).click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("ETC高速通行费");
    await expect(projectRows).toContainText("ETC导入通行服务商");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("surfaces preview stale errors without starting a background import job", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      etcImportConfirmPreviewStale: true,
      sessionMode: "full_access",
    });

    await previewEtcZipFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("预览后数据已变化，请重新预览后再确认。")).toBeVisible();
    await expect(page.getByText("已开始后台导入")).toHaveCount(0);
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/409/])).toEqual([]);
  });

  test("clears stale reconciliation task previews and requires a new preview", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      etcImportConfirmStaleReconciliationTask: true,
      sessionMode: "full_access",
    });

    await previewEtcZipFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("对账任务已更新，请重新预览 ETC zip 后再确认导入。")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC导入预览" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "开始预览" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
    await expect(page.getByText("已开始后台导入")).toHaveCount(0);
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(unexpectedRuntimeErrors(browserErrors, [/409/])).toEqual([]);
  });

  test("keeps confirm failures visible without reporting background import success", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      etcImportConfirmError: true,
      sessionMode: "full_access",
    });

    await previewEtcZipFiles(page);
    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("ETC导入任务创建失败，请稍后重试。")).toBeVisible();
    await expect(page.getByText("已开始后台导入")).toHaveCount(0);
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/500/])).toEqual([]);
  });
});
