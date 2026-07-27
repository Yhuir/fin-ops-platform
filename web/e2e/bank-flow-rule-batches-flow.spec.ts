import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function startStrictBrowserErrorCapture(page: Page, options: { allowedConsoleErrors?: RegExp[] } = {}) {
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

function responsePathMatches(responseUrl: string, pathname: string) {
  return new URL(responseUrl).pathname === pathname;
}

function waitForBankFlowRuleBatches(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname === "/api/bank-flow-rule-batches";
  });
}

function createBankFlowRuleBatchLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/bank-flow-rule-batches",
    pageKey: "bank-flow-rule-batches",
    module: "bank-flow-rule-batches",
  });
}

function postResponse(pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === "POST" && responsePathMatches(response.url(), pathname);
}

function putResponse(pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === "PUT" && responsePathMatches(response.url(), pathname);
}

const ordinaryBankFlowRuleCheckboxCases = [
  {
    primaryButton: "费用 1批 · 1条",
    subButton: "手续费 1批 · 1条",
    tableName: "建设银行8106流水",
    transactionId: "bank-flow-rule-e2e-fee",
  },
  {
    primaryButton: "人工成本 1批 · 1条",
    subButton: "工资 1批 · 1条",
    tableName: "工商银行6386流水",
    transactionId: "bank-flow-rule-e2e-salary",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "过节费 1批 · 1条",
    tableName: "中国银行7001流水",
    transactionId: "bank-flow-rule-e2e-holiday_bonus",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "奖金 1批 · 1条",
    tableName: "招商银行9988流水",
    transactionId: "bank-flow-rule-e2e-bonus",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "税款 1批 · 1条",
    tableName: "农业银行2211流水",
    transactionId: "bank-flow-rule-e2e-tax_payment",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "国库税款 1批 · 1条",
    tableName: "交通银行3344流水",
    transactionId: "bank-flow-rule-e2e-treasury_tax_collection",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "社保 1批 · 1条",
    tableName: "民生银行5566流水",
    transactionId: "bank-flow-rule-e2e-social_security",
  },
];

test.describe("bank flow rule batches browser flow", () => {
  test("recovers list after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      bankFlowRuleBatchFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByText("流水规则批次加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 4 && !recovered; attempt += 1) {
      const responsePromise = waitForBankFlowRuleBatches(page);
      await page.getByRole("button", { name: "刷新" }).click();
      const response = await responsePromise;
      recovered = response.status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("流水规则批次加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toBeDisabled();
    expect(api.count("GET /api/bank-flow-rule-batches")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("loads canonical rows without background polling", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    const settledListReads = api.count("GET /api/bank-flow-rule-batches");
    await page.waitForTimeout(1_500);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(settledListReads);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("shows selectable checkboxes for every ordinary draft flow rule batch type", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      bankFlowRuleBatchScenario: "ordinaryDraftMatrix",
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 7" })).toHaveAttribute("aria-pressed", "true");

    for (const [index, item] of ordinaryBankFlowRuleCheckboxCases.entries()) {
      await page.getByRole("button", { name: item.primaryButton, exact: true }).click();
      await page.getByRole("button", { name: item.subButton, exact: true }).click();

      const table = page.getByRole("table", { name: item.tableName });
      await expect(table).toBeVisible();
      const checkbox = table.getByRole("checkbox", { name: `选择流水 ${item.transactionId}` });
      await expect(checkbox).toBeVisible();
      await expect(checkbox).toBeEnabled();
      if (index === 0) {
        await checkbox.check();
        await expect(checkbox).toBeChecked();
        const refreshedCheckbox = page
          .getByRole("table", { name: item.tableName })
          .getByRole("checkbox", { name: `选择流水 ${item.transactionId}` });
        await refreshedCheckbox.uncheck();
        await expect(refreshedCheckbox).not.toBeChecked();
      }
    }

    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves tag rules and reloads the canonical list once", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    const monthReload = waitForBankFlowRuleBatches(page);
    await page.getByLabel("月份").fill("2026-05");
    await monthReload;

    const tagDrawer = page.getByRole("dialog", { name: "流水规则标签管理" });
    await recordLatency({
      operationId: "bank-flow-rule-batches.open-tag-rules-drawer",
      visibleLabel: "流水规则标签管理",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "流水规则标签管理" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(tagDrawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(tagDrawer.getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).toBeVisible());
    });
    await expect(tagDrawer.getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).not.toBeChecked();
    await expect(tagDrawer.getByRole("checkbox", { name: "费用 / 手续费 需要发票" })).not.toBeChecked();
    await recordLatency({
      operationId: "bank-flow-rule-batches.toggle-salary-requires-oa",
      visibleLabel: "人工成本 / 工资 需要OA",
      actionType: "check",
    }, async (mark) => {
      const checkbox = tagDrawer.getByRole("checkbox", { name: "人工成本 / 工资 需要OA" });
      await checkbox.check();
      await mark("firstVisibleResponseLatencyMs", expect(checkbox).toBeChecked());
      await mark("finalSettledLatencyMs", expect(checkbox).toBeChecked());
    });

    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/tag-rules")
      && request.method() === "PUT",
    );
    const saveResponse = page.waitForResponse(putResponse("/api/bank-flow-rule-batches/tag-rules"));
    const listReadsBeforeSave = api.count("GET /api/bank-flow-rule-batches");
    const listReload = waitForBankFlowRuleBatches(page);
    await recordLatency({
      operationId: "bank-flow-rule-batches.save-tag-rules",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      await tagDrawer.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("流水规则已保存")).toBeVisible());
      await mark("finalSettledLatencyMs", listReload);
    });

    const saveBody = JSON.parse((await saveRequest).postData() ?? "{}") as {
      expected_version?: number;
      rules?: Array<{ tag_code?: string; requires_oa?: boolean; requires_invoice?: boolean }>;
      selected_tag_codes?: unknown;
    };
    expect(saveBody).not.toHaveProperty("selected_tag_codes");
    expect(saveBody).toEqual({
      expected_version: 3,
      rules: [
        { tag_code: "fee", requires_oa: false, requires_invoice: false },
        { tag_code: "salary", requires_oa: true, requires_invoice: false },
      ],
    });
    expect((await saveResponse).status()).toBe(200);
    expect(api.count("PUT /api/bank-flow-rule-batches/tag-rules")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(listReadsBeforeSave + 1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("syncs the rule drawer labels after bank detail tags change", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await page.getByRole("button", { name: /自动标签规则/ }).click();
    const autoTagDrawer = page.getByRole("dialog", { name: "自动标签规则" });
    await expect(autoTagDrawer).toBeVisible();
    await autoTagDrawer.getByRole("textbox", { name: "费用 / 工资 子标签" }).fill("规则同步工资");
    const bankDetailGetsBeforeSave = api.count("GET /api/bank-details/transactions");
    await autoTagDrawer.getByRole("button", { name: "保存" }).click();
    await expect.poll(() => api.count("PUT /api/bank-details/auto-tag-rules")).toBe(1);
    await expect(page.getByText("规则已保存。").first()).toBeVisible();
    await expect.poll(() => api.count("GET /api/bank-details/transactions"))
      .toBeGreaterThan(bankDetailGetsBeforeSave);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await page.getByRole("button", { name: "流水规则标签管理" }).click();
    const ruleDrawer = page.getByRole("dialog", { name: "流水规则标签管理" });
    await expect(ruleDrawer).toBeVisible();
    await expect(ruleDrawer.getByRole("checkbox", { name: "人工成本 / 规则同步工资 需要OA" })).toBeVisible();
    await expect(ruleDrawer.getByRole("checkbox", { name: "人工成本 / 规则同步工资 需要发票" })).toBeVisible();
    await expect(ruleDrawer.getByRole("checkbox", { name: "人工成本 / 工资 需要OA" })).toHaveCount(0);
    expect(api.count("GET /api/bank-flow-rule-batches/tag-rules")).toBeGreaterThanOrEqual(1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("resets submitted flow rule batches back to unsubmitted", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await draftTable.getByLabel("选择流水 bank-flow-rule-e2e-001").check();
    await recordLatency({
      operationId: "bank-flow-rule-batches.submit-selected-before-reset",
      visibleLabel: "提交批次",
      actionType: "click",
    }, async (mark) => {
      const submitResponse = page.waitForResponse(postResponse("/api/bank-flow-rule-batches/submit-selection"));
      const listReload = waitForBankFlowRuleBatches(page);
      await page.getByRole("button", { name: "提交批次" }).click();
      await mark("apiLatencyMs", submitResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("选中流水已提交")).toBeVisible());
      await mark("finalSettledLatencyMs", listReload);
    });

    const resetRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/reset-submitted")
      && request.method() === "POST",
    );
    const resetResponse = page.waitForResponse(postResponse("/api/bank-flow-rule-batches/reset-submitted"));
    const listReadsBeforeReset = api.count("GET /api/bank-flow-rule-batches");
    const resetListReload = waitForBankFlowRuleBatches(page);
    await recordLatency({
      operationId: "bank-flow-rule-batches.reset-submitted",
      visibleLabel: "重置全部已提交",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "重置全部已提交" }).click();
      await mark("apiLatencyMs", resetResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("已重置 1 个已提交批次")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true"));
    });
    await resetListReload;
    const resetBody = JSON.parse((await resetRequest).postData() ?? "{}") as { reason?: string };
    expect(resetBody.reason).toBe("流水规则批量处理：全部已提交批次重新过规则");
    expect((await resetResponse).status()).toBe(200);

    await page.getByRole("button", { name: "查看建设银行8106流水" }).click();
    await expect(page.getByRole("table", { name: "建设银行8106流水" })).toBeVisible();
    expect(api.count("POST /api/bank-flow-rule-batches/reset-submitted")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(listReadsBeforeReset + 1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("submits internal transfer batches without blocking on workbench visibility refresh", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankFlowRuleBatchScenario: "internalTransferPairs",
      sessionMode: "full_access",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 2" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "内部往来款 2批 · 4条" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "主标签本身 2批 · 4条" })).toBeVisible();

    const firstBatch = page.locator(".bank-flow-rule-batches-batch").filter({ hasText: "光大银行8826" });
    await expect(firstBatch).toBeVisible();
    await expect(firstBatch.getByText("2 条 · 合计 50,000.00")).toBeVisible();
    await expect(page.getByRole("table", { name: "光大银行8826流水" })).toBeVisible();
    const secondBatch = page
      .locator(".bank-flow-rule-batches-batch")
      .filter({ hasText: "建设银行8106" })
      .filter({ hasText: "2 条 · 合计 7,000.00" });
    await expect(secondBatch.getByText("2 条 · 合计 7,000.00")).toBeVisible();

    const submitRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/bank-flow-internal-ccb-8106/submit")
      && request.method() === "POST",
    );
    const submitResponse = page.waitForResponse(postResponse("/api/bank-flow-rule-batches/bank-flow-internal-ccb-8106/submit"));
    const listReadsBeforeSubmit = api.count("GET /api/bank-flow-rule-batches");
    const listReload = waitForBankFlowRuleBatches(page);
    const startedAt = Date.now();
    await recordLatency({
      operationId: "bank-flow-rule-batches.submit-internal-transfer-batch",
      visibleLabel: "提交内部往来批次",
      actionType: "click",
    }, async (mark) => {
      await secondBatch.getByRole("button", { name: "提交内部往来批次" }).click();
      await mark("apiLatencyMs", submitResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("内部往来批次已提交")).toBeVisible({ timeout: 3_000 }));
      await mark("finalSettledLatencyMs", listReload);
    });

    const submitBody = JSON.parse((await submitRequest).postData() ?? "{}") as {
      expected_version?: number;
      note?: string;
    };
    expect(submitBody).toEqual({ expected_version: 1, note: "" });
    expect((await submitResponse).status()).toBe(200);
    expect(Date.now() - startedAt).toBeLessThan(3_000);
    expect(api.count("POST /api/bank-flow-rule-batches/bank-flow-internal-ccb-8106/submit")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(listReadsBeforeSubmit + 1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("submits a selected bank row, reloads canonical state, and withdraws the submitted flow rule batch", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankFlowRuleCostFanout: true,
      sessionMode: "full_access",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await draftTable.getByLabel("选择流水 bank-flow-rule-e2e-001").check();
    await expect(page.getByText("已选 1 条")).toBeVisible();

    const submitRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/submit-selection")
        && request.method() === "POST",
    );
    const submitResponse = page.waitForResponse(postResponse("/api/bank-flow-rule-batches/submit-selection"));
    const listReadsBeforeSubmit = api.count("GET /api/bank-flow-rule-batches");
    const submitListReload = waitForBankFlowRuleBatches(page);
    await recordLatency({
      operationId: "bank-flow-rule-batches.submit-selected-bank-row",
      visibleLabel: "提交批次",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "提交批次" }).click();
      await mark("apiLatencyMs", submitResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("选中流水已提交")).toBeVisible());
      await mark("finalSettledLatencyMs", submitListReload);
    });
    const submitBody = JSON.parse((await submitRequest).postData() ?? "{}") as {
      transaction_ids?: string[];
    };
    expect(submitBody.transaction_ids).toEqual(["bank-flow-rule-e2e-001"]);
    expect((await submitResponse).status()).toBe(200);
    expect(api.count("POST /api/bank-flow-rule-batches/submit-selection")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(listReadsBeforeSubmit + 1);
    await expectNoUnexpectedSuccessUiErrors(page);

    const costExplorerResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const costPayload = await (await costExplorerResponse).json() as Record<string, unknown>;
    expect(costPayload).not.toHaveProperty("read_model_status");
    expect(costPayload).not.toHaveProperty("refresh_enqueued");
    await page.getByRole("button", { name: "按项目" }).click();
    const bankFlowRuleCostProject = page.getByRole("button", { name: /流水规则手续费成本项目/ });
    await expect(bankFlowRuleCostProject).toBeVisible();
    await expect(bankFlowRuleCostProject).toContainText("8.80");
    await bankFlowRuleCostProject.click();
    await page.getByRole("button", { name: /手续费 1 条流水/ }).click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("网银手续费");
    await expect(projectRows).toContainText("建设银行");
    await expectNoUnexpectedSuccessUiErrors(page);

    await page.goto("/bank-flow-rule-batches");
    await page.getByRole("button", { name: "已提交 1" }).click();
    await expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("table", { name: "建设银行8106流水" })).toBeVisible();
    await expect(page.getByRole("button", { name: "撤回批次" })).toBeVisible();

    const withdrawDialog = page.getByRole("dialog", { name: "撤回批次" });
    await recordLatency({
      operationId: "bank-flow-rule-batches.open-withdraw-dialog",
      visibleLabel: "撤回批次",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "撤回批次" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(withdrawDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(withdrawDialog.getByText("撤回后会取消关联台闭环关系")).toBeVisible());
    });
    await recordLatency({
      operationId: "bank-flow-rule-batches.fill-withdraw-reason",
      visibleLabel: "撤回原因",
      actionType: "fill",
    }, async (mark) => {
      const reasonInput = withdrawDialog.getByLabel("撤回原因");
      await reasonInput.fill("浏览器 e2e 复核撤回");
      await mark("firstVisibleResponseLatencyMs", expect(reasonInput).toHaveValue("浏览器 e2e 复核撤回"));
      await mark("finalSettledLatencyMs", expect(reasonInput).toHaveValue("浏览器 e2e 复核撤回"));
    });

    const withdrawRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/bank-flow-rule-batch-e2e-001/withdraw")
        && request.method() === "POST",
    );
    const withdrawResponse = page.waitForResponse(postResponse("/api/bank-flow-rule-batches/bank-flow-rule-batch-e2e-001/withdraw"));
    const listReadsBeforeWithdraw = api.count("GET /api/bank-flow-rule-batches");
    const withdrawListReload = waitForBankFlowRuleBatches(page);
    await recordLatency({
      operationId: "bank-flow-rule-batches.confirm-withdraw",
      visibleLabel: "确认撤回",
      actionType: "click",
    }, async (mark) => {
      await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();
      await mark("apiLatencyMs", withdrawResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("批次已撤回")).toBeVisible());
      await mark("finalSettledLatencyMs", withdrawListReload);
    });
    const withdrawBody = JSON.parse((await withdrawRequest).postData() ?? "{}") as {
      expected_version?: number;
      reason?: string;
    };
    expect(withdrawBody).toEqual({ expected_version: 2, reason: "浏览器 e2e 复核撤回" });
    expect((await withdrawResponse).status()).toBe(200);
    expect(api.count("POST /api/bank-flow-rule-batches/bank-flow-rule-batch-e2e-001/withdraw")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(listReadsBeforeWithdraw + 1);
    await expectNoUnexpectedSuccessUiErrors(page);

    await page.getByRole("button", { name: "历史 1" }).click();
    await expect(page.getByRole("button", { name: "历史 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("已撤回", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "撤回批次" })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("renders bank flow rule batches in workbench according to OA and invoice requirements", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchBankFlowRuleBatchScenario: true,
    });

    await page.goto("/");
    const pairedZone = page.getByTestId("zone-paired");
    const openZone = page.getByTestId("zone-unpaired");
    const pairedGroup = page.getByTestId("candidate-group-paired-bank-flow-rule-batch:bank_flow_rule_batch_e2e_fee");

    await expect(pairedGroup).toBeVisible();
    await expect(pairedZone.getByText("流水规则手续费批次")).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "加载更多" })).toHaveCount(0);
    await expect(pairedZone.getByText("流水规则手续费明细 1")).toHaveCount(0);

    const expandButton = pairedZone.getByRole("button", { name: "展开流水规则批次明细，4 条" });
    await expect(expandButton).toBeVisible();
    expect(api.count("GET /api/workbench/groups/detail")).toBe(0);
    await expandButton.click();
    await expect(pairedZone.getByText("流水规则手续费明细 1")).toBeVisible();
    await expect(pairedZone.getByText("流水规则手续费明细 4")).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "收起流水规则批次明细" })).toBeVisible();
    expect(api.count("GET /api/workbench/groups/detail")).toBe(1);

    const invoiceRequiredGroup = page.getByTestId(
      "candidate-group-unpaired-bank-flow-rule-batch:bank_flow_rule_batch_e2e_invoice_required",
    );
    await expect(invoiceRequiredGroup).toBeVisible();
    await expect(openZone.getByText("需要发票后才进入已配对")).toBeVisible();
    await expect(openZone.getByText("BFR-INV-E2E-001")).toBeVisible();
    await expect(pairedZone.getByText("需要发票后才进入已配对")).toHaveCount(0);

    await invoiceRequiredGroup.getByRole("row", { name: /需要发票后才进入已配对/ }).click();
    await invoiceRequiredGroup.getByRole("row", { name: /BFR-INV-E2E-001/ }).click();
    await expect(openZone.getByText("已选 2")).toBeVisible();

    const previewResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/actions/confirm-link/preview")
      && response.request().method() === "POST",
    );
    await openZone.getByRole("button", { name: "确认关联" }).click();
    expect((await previewResponse).status()).toBe(200);
    const previewDialog = page.getByRole("dialog", { name: "关联预览" });
    await expect(previewDialog.getByText("确认后将把 1 条流水和 1 条发票按流水规则闭环。")).toBeVisible();

    const confirmResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/actions/confirm-link")
      && response.request().method() === "POST",
    );
    await previewDialog.getByRole("button", { name: "确认关联" }).click();
    expect((await confirmResponse).status()).toBe(200);

    const completedGroup = page.getByTestId(
      "candidate-group-paired-bank-flow-rule-batch:bank_flow_rule_batch_e2e_invoice_required",
    );
    await expect(completedGroup).toBeVisible();
    await expect(pairedZone.getByText("补齐发票后进入已配对")).toBeVisible();
    await expect(openZone.getByText("需要发票后才进入已配对")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
