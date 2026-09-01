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
    expectedAudit?: { importable: number; existing: number };
    recordLatency?: OperationLatencyRecorder;
  } = {},
) {
  const expectedAudit = options.expectedAudit ?? {
    importable: 14,
    existing: 2,
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

async function stageBankStatementFilesForPreview(
  page: Page,
  recordLatency?: OperationLatencyRecorder,
) {
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
  test("clear discards the current preview and returns to a fresh page", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      bankImportNoAccountConflict: true,
      sessionMode: "user",
    });

    await previewBankStatementFiles(page);
    await page.getByRole("button", { name: "清空" }).click();

    await expect(page.getByText("当前还没有选择文件。")).toBeVisible();
    await expect(page.getByLabel("新增 14")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "清空" })).toBeDisabled();
    expect(api.count("POST /imports/files/discard")).toBe(1);
  });

  test("shows an all-existing bank preview as a no-op without creating an import job", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportAllExisting: true,
      bankImportNoAccountConflict: true,
      sessionMode: "user",
    });

    await previewBankStatementFiles(page, {
      expectedAudit: { importable: 0, existing: 48 },
    });

    await expect(page.getByLabel("新增 0")).toBeVisible();
    await expect(page.getByLabel("APP 已存在 48")).toBeVisible();
    await expect(page.getByText("已检查 48 笔流水，全部已存在于 APP，无需重复导入。")).toHaveCount(0);
    await expect(page.getByLabel("文件处理结果")).toContainText("无需导入");
    await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
    expect(api.count("POST /imports/files/preview")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("previews and confirms bank statement files, then reflects the imported row in bank details", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportNoAccountConflict: true,
      sessionMode: "user",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });
    expect(api.count("GET /imports/files/sessions/import_session_e2e_bank/review-rows")).toBe(0);
    await page.getByRole("button", { name: "查看未处理明细" }).click();
    await expect(page.getByRole("tab", { name: /重复项 2/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("同文件重复");
    await expect(page.getByRole("grid", { name: "重复项明细" })).toContainText("导入浏览器测试客户");
    expect(api.count("GET /imports/files/sessions/import_session_e2e_bank/review-rows")).toBe(1);
    await page.getByRole("button", { name: "关闭抽屉" }).click();
    expect(api.count("POST /imports/files/preview")).toBe(1);

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
    await expect(importedRow.getByText("1688.00")).toBeVisible();
    await expect(importedRow.getByText("银行流水导入 browser e2e")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("confirms bank statement import without polluting OA cost allocation", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportDownstreamFanout: true,
      bankImportNoAccountConflict: true,
      sessionMode: "user",
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
      operationId: "cost-statistics.verify-project-view-after-bank-import",
      visibleLabel: "按项目统计",
      actionType: "read",
    }, async (mark) => {
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible());
    });
    await expect(page.getByRole("button", { name: /银行导入成本项目/ })).toHaveCount(0);
    await expect(page.getByText("银行流水导入成本")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("blocks confirmation when the selected bank account conflicts with the detected account", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, { recordLatency });

    await expect(page.getByText(/已阻止确认导入/)).toContainText("识别账户与所选账户不一致");
    await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
    await expect(page.getByRole("dialog", { name: "银行账户冲突确认" })).toHaveCount(0);
    await expect(page.getByText("已确认导入")).toHaveCount(0);
    await expect(page.getByRole("grid", { name: "导入预览结果" })).toHaveCount(0);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(unexpectedRuntimeErrors(browserErrors)).toEqual([]);
  });

  test("keeps corrupt files as file-level errors while confirming only valid bank statements", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankImportIncludeCorruptFile: true,
      bankImportNoAccountConflict: true,
      sessionMode: "user",
    });
    const recordLatency = createBankImportLatencyRecorder(page, testInfo);

    await previewBankStatementFiles(page, {
      expectedAudit: { importable: 7, existing: 0 },
      recordLatency,
    });

    const fileResults = page.getByLabel("文件处理结果");
    await expect(fileResults).toContainText("historydetail14080.xlsx");
    await expect(fileResults).toContainText("无法识别");
    await expect(fileResults).toContainText("文件损坏，无法读取银行流水模板。");
    await expect(fileResults).toContainText("2026-01-01至2026-01-31交易明细.xlsx");
    await expect(fileResults).toContainText("待确认");
    await page.getByRole("button", { name: "查看未处理明细" }).click();
    await expect(page.getByRole("tab", { name: /未处理项 3/ })).toBeVisible();
    await recordLatency({
      operationId: "imports-bank-transactions.open-skipped-files-tab",
      visibleLabel: "未处理项 3",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("tab", { name: /未处理项 3/ }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "未处理项明细" })).toContainText("文件损坏，无法读取银行流水模板。"));
    });
    await expect(page.getByRole("grid", { name: "未处理项明细" })).toContainText("文件损坏，无法读取银行流水模板。");
    await page.getByRole("button", { name: "关闭抽屉" }).click();

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
      bankImportNoAccountConflict: true,
      sessionMode: "user",
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
      await mark("finalSettledLatencyMs", expect(page.getByLabel("新增 14")).toBeVisible());
    });
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await expect(page.getByLabel("新增 14")).toBeVisible();
    await expect(page.getByRole("button", { name: "开始预览" })).toBeDisabled();
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
      sessionMode: "user",
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
      sessionMode: "user",
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
