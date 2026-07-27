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

function createBankImportLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/imports/bank-transactions",
    pageKey: "imports-bank-transactions",
    module: "imports-bank-transactions",
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

async function expectDirectCanonicalResponse(responsePromise: Promise<{ json(): Promise<unknown> }>) {
  const payload = await (await responsePromise).json() as Record<string, unknown>;
  expect(payload).not.toHaveProperty("read_model_status");
  expect(payload).not.toHaveProperty("source_versions");
  expect(payload).not.toHaveProperty("refresh_enqueued");
  return payload;
}

async function previewBankStatementFiles(
  page: Page,
  options: {
    expectedAudit?: { importable: number; original: number; skipped: number };
    recordLatency?: OperationLatencyRecorder;
  } = {},
) {
  const expectedAudit = options.expectedAudit ?? {
    importable: 14,
    original: 18,
    skipped: 4,
  };
  await stageBankStatementFilesForPreview(page, options.recordLatency);

  const previewButton = page.getByRole("button", { name: "开始预览" });
  await expect(previewButton).toBeEnabled();
  if (options.recordLatency) {
    await options.recordLatency({
      operationId: "imports-bank-transactions.preview-files",
      visibleLabel: "开始预览",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForImportPreview(page);
      await previewButton.click();
      await mark("apiLatencyMs", previewResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible());
    });
  } else {
    await previewButton.click();
  }

  await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
  await expect(page.getByLabel(`审计汇总 原始 ${expectedAudit.original}`)).toBeVisible();
  await expect(page.getByLabel(`审计汇总 可导入 ${expectedAudit.importable}`)).toBeVisible();
  await expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible();
  await expect(page.getByText(new RegExp(`将导入 ${expectedAudit.importable} 条唯一记录，跳过 ${expectedAudit.skipped} 条重复`))).toBeVisible();
}

async function stageBankStatementFilesForPreview(page: Page, recordLatency?: OperationLatencyRecorder) {
  const openPage = async () => {
    await page.goto("/imports/bank-transactions");
    await expect(page.getByTestId("import-workflow-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "银行流水导入" })).toBeVisible();
  };
  if (recordLatency) {
    await recordLatency({
      operationId: "imports-bank-transactions.open-page",
      visibleLabel: "银行流水导入",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/imports/bank-transactions");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("import-workflow-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "银行流水导入" })).toBeVisible());
    });
  } else {
    await openPage();
  }

  const filePayloads = [
    {
      name: "historydetail14080.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("bank-import-e2e-a"),
    },
    {
      name: "2026-01-01至2026-01-31交易明细.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("bank-import-e2e-b"),
    },
  ];
  if (recordLatency) {
    await recordLatency({
      operationId: "imports-bank-transactions.select-files",
      visibleLabel: "选择文件",
      actionType: "upload",
    }, async (mark) => {
      await page.locator('input[type="file"]').setInputFiles(filePayloads);
      await mark("finalSettledLatencyMs", expect(page.getByLabel("对应账户 historydetail14080.xlsx")).toBeVisible());
    });
  } else {
    await page.locator('input[type="file"]').setInputFiles(filePayloads);
  }

  if (recordLatency) {
    await recordLatency({
      operationId: "imports-bank-transactions.select-bank-account-mapping",
      visibleLabel: "对应账户",
      actionType: "select",
    }, async (mark) => {
      await page.getByLabel("对应账户 historydetail14080.xlsx").selectOption("bank_mapping_8826");
      await page.getByLabel("对应账户 2026-01-01至2026-01-31交易明细.xlsx").selectOption("bank_mapping_8826");
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "开始预览" })).toBeEnabled());
    });
  } else {
    await page.getByLabel("对应账户 historydetail14080.xlsx").selectOption("bank_mapping_8826");
    await page.getByLabel("对应账户 2026-01-01至2026-01-31交易明细.xlsx").selectOption("bank_mapping_8826");
  }
}

test.describe("bank transaction import browser flow", () => {
  test("previews and confirms bank statement files, then reflects the imported row in bank details", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });
    await expect(page.getByRole("tab", { name: /重复项 1/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("同文件重复");
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("导入浏览器测试客户");
    expect(api.count("POST /imports/files/preview")).toBe(1);

    const conflictDialog = page.getByRole("dialog", { name: "银行账户冲突确认" });
    await recordLatency({
      operationId: "imports-bank-transactions.open-account-conflict-dialog",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("finalSettledLatencyMs", expect(conflictDialog).toBeVisible());
    });
    await expect(conflictDialog).toBeVisible();
    await expect(conflictDialog.getByText("historydetail14080.xlsx")).toBeVisible();
    await expect(conflictDialog.getByText("后四位选择为8826，系统识别为4080")).toBeVisible();
    await recordLatency({
      operationId: "imports-bank-transactions.confirm-account-conflict-import",
      visibleLabel: "仍按所选账户 建设银行 8826 导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await conflictDialog.getByRole("button", { name: "仍按所选账户 建设银行 8826 导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("已确认导入")).toBeVisible());
    });

    await expect(page.getByText("已确认导入")).toBeVisible();
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    let accountBalanceResponsePayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/bank-details",
      pageKey: "bank-details",
      module: "bank-details",
      operationId: "bank-details.open-after-bank-import",
      visibleLabel: "银行明细",
      actionType: "click",
    }, async (mark) => {
      const accountBalanceResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/bank-details/accounts")
        && response.status() === 200);
      await page.getByRole("link", { name: "银行明细" }).click();
      accountBalanceResponsePayload = await mark("apiLatencyMs", accountBalanceResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("bank-details-page")).toBeVisible());
    });
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const accountBalancePayload = await expectDirectCanonicalResponse(
      Promise.resolve(accountBalanceResponsePayload!),
    );
    expect(accountBalancePayload.accounts).toEqual(expect.any(Array));
    const importedRow = page.getByRole("row", { name: /导入浏览器测试客户/ });
    await expect(importedRow).toBeVisible();
    await expect(importedRow.getByText("1,688.00")).toBeVisible();
    await expect(importedRow.getByText("银行流水导入 browser e2e")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("confirms bank statement import and observes canonical cost statistics", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportDownstreamFanout: true,
      bankImportNoAccountConflict: true,
      sessionMode: "full_access",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-bank-transactions.confirm-import",
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

    let costRowsPayload: { json(): Promise<unknown> } | undefined;
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-bank-import",
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
      operationId: "cost-statistics.switch-project-view-after-bank-import",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "按项目" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /银行导入成本项目/ })).toBeVisible());
    });
    const importedCostProject = page.getByRole("button", { name: /银行导入成本项目/ });
    await expect(importedCostProject).toBeVisible();
    await expect(importedCostProject).toContainText("1,688.00");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-project-after-bank-import",
      visibleLabel: "银行导入成本项目",
      actionType: "click",
    }, async (mark) => {
      await importedCostProject.click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /经营\/办公费用/ })).toBeVisible());
    });
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-expense-type-after-bank-import",
      visibleLabel: "经营/办公费用",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: /经营\/办公费用/ }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "项目对应流水表" })).toContainText("银行流水导入成本"));
    });
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("银行流水导入成本");
    await expect(projectRows).toContainText("导入浏览器测试客户");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("cancels bank account conflict confirmation without submitting an import", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });

    const conflictDialog = page.getByRole("dialog", { name: "银行账户冲突确认" });
    await recordLatency({
      operationId: "imports-bank-transactions.open-account-conflict-dialog-for-cancel",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("finalSettledLatencyMs", expect(conflictDialog).toBeVisible());
    });
    await expect(conflictDialog).toBeVisible();
    await recordLatency({
      operationId: "imports-bank-transactions.cancel-account-conflict",
      visibleLabel: "取消",
      actionType: "click",
    }, async (mark) => {
      await conflictDialog.getByRole("button", { name: "取消" }).click();
      await mark("finalSettledLatencyMs", expect(conflictDialog).toHaveCount(0));
    });

    await expect(conflictDialog).toHaveCount(0);
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    await expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible();
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await recordLatency({
      operationId: "imports-bank-transactions.reopen-account-conflict-after-cancel",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("finalSettledLatencyMs", expect(conflictDialog).toBeVisible());
    });
    await expect(conflictDialog).toBeVisible();
    await recordLatency({
      operationId: "imports-bank-transactions.confirm-account-conflict-after-cancel",
      visibleLabel: "仍按所选账户 建设银行 8826 导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await conflictDialog.getByRole("button", { name: "仍按所选账户 建设银行 8826 导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("已确认导入")).toBeVisible());
    });
    await expect(page.getByText("已确认导入")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("keeps corrupt files as file-level errors while confirming only valid bank statements", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportIncludeCorruptFile: true,
      bankImportNoAccountConflict: true,
      sessionMode: "full_access",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, {
      expectedAudit: { importable: 7, original: 10, skipped: 1 },
      recordLatency,
    });

    const previewGrid = page.getByRole("grid", { name: "导入预览结果" });
    await expect(previewGrid).toContainText("historydetail14080.xlsx");
    await expect(previewGrid).toContainText("无法识别");
    await expect(previewGrid).toContainText("文件损坏，无法读取银行流水模板。");
    await expect(previewGrid).toContainText("2026-01-01至2026-01-31交易明细.xlsx");
    await expect(previewGrid).toContainText("待确认");
    await expect(page.getByRole("tab", { name: /未导入项 1/ })).toBeVisible();
    await recordLatency({
      operationId: "imports-bank-transactions.open-skipped-files-tab",
      visibleLabel: "未导入项 1",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("tab", { name: /未导入项 1/ }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "未导入项明细" })).toContainText("文件损坏，无法读取银行流水模板。"));
    });
    await expect(page.getByRole("grid", { name: "未导入项明细" })).toContainText("文件损坏，无法读取银行流水模板。");

    await recordLatency({
      operationId: "imports-bank-transactions.confirm-import-with-corrupt-file",
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
      selected_file_ids: ["import_file_e2e_2"],
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("locks import actions while slow bank statement preview is in flight", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportPreviewDelayMs: 500,
      sessionMode: "full_access",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await stageBankStatementFilesForPreview(page, recordLatency);
    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeEnabled();

    const previewingButton = page.getByRole("button", { name: "预览中..." });
    await recordLatency({
      operationId: "imports-bank-transactions.preview-files-slow",
      visibleLabel: "开始预览",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForImportPreview(page);
      await previewButton.click();
      await mark("firstVisibleResponseLatencyMs", expect(previewingButton).toBeDisabled());
      await expect(page.getByRole("button", { name: "清空" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
      await mark("apiLatencyMs", previewResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible());
    });
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始预览" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "清空" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认导入" })).toBeEnabled();
    expect(api.count("POST /imports/files/preview")).toBe(1);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("surfaces preview stale errors without creating an import job or refreshing downstream pages", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportConfirmPreviewStale: true,
      bankImportNoAccountConflict: true,
      sessionMode: "full_access",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-bank-transactions.confirm-import-preview-stale",
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
      bankImportConfirmError: true,
      bankImportNoAccountConflict: true,
      sessionMode: "full_access",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });
    await recordLatency({
      operationId: "imports-bank-transactions.confirm-import-server-error",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForImportConfirm(page);
      await page.getByRole("button", { name: "确认导入" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("finalSettledLatencyMs", expect(page.getByText("导入任务创建失败，请稍后重试。")).toBeVisible());
    });

    await expect(page.getByText("导入任务创建失败，请稍后重试。")).toBeVisible();
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors, [/500/])).toEqual([]);
  });
});
