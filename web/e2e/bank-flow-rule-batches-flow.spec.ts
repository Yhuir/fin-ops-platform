import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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

function waitForNoOaBankBatches(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname === "/api/bank-flow-rule-batches";
  });
}

const ordinaryNoOaCheckboxCases = [
  {
    primaryButton: "费用 1批 · 1条",
    subButton: "手续费 1批 · 1条",
    tableName: "建设银行8106流水",
    transactionId: "no-oa-bank-e2e-fee",
  },
  {
    primaryButton: "人工成本 1批 · 1条",
    subButton: "工资 1批 · 1条",
    tableName: "工商银行6386流水",
    transactionId: "no-oa-bank-e2e-salary",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "过节费 1批 · 1条",
    tableName: "中国银行7001流水",
    transactionId: "no-oa-bank-e2e-holiday_bonus",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "奖金 1批 · 1条",
    tableName: "招商银行9988流水",
    transactionId: "no-oa-bank-e2e-bonus",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "税款 1批 · 1条",
    tableName: "农业银行2211流水",
    transactionId: "no-oa-bank-e2e-tax_payment",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "国库税款 1批 · 1条",
    tableName: "交通银行3344流水",
    transactionId: "no-oa-bank-e2e-treasury_tax_collection",
  },
  {
    primaryButton: "薪资社保福利 3批 · 3条",
    subButton: "社保 1批 · 1条",
    tableName: "民生银行5566流水",
    transactionId: "no-oa-bank-e2e-social_security",
  },
];

test.describe("bank flow rule batches browser flow", () => {
  test("recovers list after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      noOaBankBatchFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByText("流水规则批次加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 4 && !recovered; attempt += 1) {
      const responsePromise = waitForNoOaBankBatches(page);
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

  test("keeps visible rows while a stale flow rule read model refreshes to fresh", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      noOaBankBatchReadModelStatuses: ["stale", "fresh"],
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

    await expect.poll(() => api.count("GET /api/bank-flow-rule-batches"), {
      timeout: 3_000,
    }).toBeGreaterThanOrEqual(2);

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
      noOaBankBatchScenario: "ordinaryDraftMatrix",
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 7" })).toHaveAttribute("aria-pressed", "true");

    for (const item of ordinaryNoOaCheckboxCases) {
      await page.getByRole("button", { name: item.primaryButton, exact: true }).click();
      await page.getByRole("button", { name: item.subButton, exact: true }).click();

      const table = page.getByRole("table", { name: item.tableName });
      await expect(table).toBeVisible();
      const checkbox = table.getByRole("checkbox", { name: `选择流水 ${item.transactionId}` });
      await expect(checkbox).toBeVisible();
      await expect(checkbox).toBeEnabled();
      await checkbox.check();
      await expect(checkbox).toBeChecked();
      await checkbox.uncheck();
      await expect(checkbox).not.toBeChecked();
    }

    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves tag rules through the freshness barrier and reloads the flow rule list", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");

    await page.getByRole("button", { name: "流水规则标签管理" }).click();
    const tagDrawer = page.getByRole("dialog", { name: "流水规则标签管理" });
    await expect(tagDrawer).toBeVisible();
    await expect(tagDrawer.getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).not.toBeChecked();
    await expect(tagDrawer.getByRole("checkbox", { name: "费用 / 手续费 需要发票" })).not.toBeChecked();
    await tagDrawer.getByRole("checkbox", { name: "人工成本 / 工资 需要OA" }).check();

    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/tag-rules")
      && request.method() === "PUT",
    );
    const saveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/bank-flow-rule-batches/tag-rules")
      && response.request().method() === "PUT",
    );
    const barrierRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/operation-barrier/status")
      && request.method() === "POST",
    );
    await tagDrawer.getByRole("button", { name: "保存" }).click();

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
    const barrierBody = JSON.parse((await barrierRequest).postData() ?? "{}") as {
      targets?: Array<{ read_model_key?: string; readModelKey?: string; scope_key?: string; scopeKey?: string }>;
    };
    expect(barrierBody.targets).toEqual([
      { read_model_key: "bank_flow_rule_batch", scope_key: "all" },
    ]);
    await expect(page.getByText("流水规则已保存")).toBeVisible();
    await expect(tagDrawer).toHaveCount(0);
    expect(api.count("PUT /api/bank-flow-rule-batches/tag-rules")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBeGreaterThanOrEqual(2);
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
    await autoTagDrawer.getByRole("button", { name: "保存" }).click();
    await expect.poll(() => api.count("PUT /api/bank-details/auto-tag-rules")).toBe(1);
    await expect(page.getByText("规则已保存，银行明细已刷新。").first()).toBeVisible();

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

  test("dry-runs and applies legacy no-OA rebaseline with a manifest", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();

    const dryRunResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/bank-flow-rule-batches/rebaseline-no-oa/dry-run")
      && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "扫描历史免OA" }).click();
    expect((await dryRunResponse).status()).toBe(200);
    await expect(page.getByText("待撤回 1 批 / 1 条 / 2026-05")).toBeVisible();
    await expect(page.getByText("已生成历史免OA重算清单：1 批")).toBeVisible();

    await page.getByLabel("原因").fill("浏览器 e2e 历史免OA重算");
    const applyRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/rebaseline-no-oa/apply")
      && request.method() === "POST",
    );
    const applyResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/bank-flow-rule-batches/rebaseline-no-oa/apply")
      && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "应用重算" }).click();
    const applyBody = JSON.parse((await applyRequest).postData() ?? "{}") as {
      reason?: string;
      manifest?: { batches?: Array<{ batch_id?: string; version?: number }> };
    };
    expect(applyBody.reason).toBe("浏览器 e2e 历史免OA重算");
    expect(applyBody.manifest?.batches).toEqual([
      expect.objectContaining({ batch_id: "legacy-no-oa-batch-e2e-001", version: 2 }),
    ]);
    expect((await applyResponse).status()).toBe(200);
    await expect(page.getByText("历史免OA已撤回 1 批")).toBeVisible();
    expect(api.count("POST /api/bank-flow-rule-batches/rebaseline-no-oa/dry-run")).toBe(1);
    expect(api.count("POST /api/bank-flow-rule-batches/rebaseline-no-oa/apply")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThanOrEqual(1);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("submits a selected bank row, waits for freshness, and withdraws the submitted flow rule batch", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      noOaCostFanout: true,
      sessionMode: "full_access",
    });

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
    await draftTable.getByLabel("选择流水 no-oa-bank-e2e-001").check();
    await expect(page.getByText("已选 1 条")).toBeVisible();

    const submitRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/submit-selection")
        && request.method() === "POST",
    );
    const submitResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/bank-flow-rule-batches/submit-selection")
        && response.request().method() === "POST",
    );
    const submitBarrierResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/operation-barrier/status")
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "提交批次" }).click();
    const submitBody = JSON.parse((await submitRequest).postData() ?? "{}") as {
      transaction_ids?: string[];
    };
    expect(submitBody.transaction_ids).toEqual(["no-oa-bank-e2e-001"]);
    expect((await submitResponse).status()).toBe(200);
    expect((await submitBarrierResponse).status()).toBe(200);
    expect(api.count("POST /api/bank-flow-rule-batches/submit-selection")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThanOrEqual(1);
    await expect(page.getByText("选中流水已提交")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const costExplorerResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const costPayload = await (await costExplorerResponse).json() as { read_model_status?: string };
    expect(costPayload.read_model_status).toBe("fresh");
    await page.getByRole("button", { name: "按项目" }).click();
    const noOaCostProject = page.getByRole("button", { name: /免OA手续费成本项目/ });
    await expect(noOaCostProject).toBeVisible();
    await expect(noOaCostProject).toContainText("8.80");
    await noOaCostProject.click();
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
    await page.getByRole("button", { name: "撤回批次" }).click();

    const withdrawDialog = page.getByRole("dialog", { name: "撤回批次" });
    await expect(withdrawDialog).toBeVisible();
    await expect(withdrawDialog.getByText("撤回后会取消关联台闭环关系")).toBeVisible();
    await withdrawDialog.getByLabel("撤回原因").fill("浏览器 e2e 复核撤回");

    const withdrawRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/bank-flow-rule-batches/no-oa-batch-e2e-001/withdraw")
        && request.method() === "POST",
    );
    const withdrawResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/bank-flow-rule-batches/no-oa-batch-e2e-001/withdraw")
        && response.request().method() === "POST",
    );
    await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();
    const withdrawBody = JSON.parse((await withdrawRequest).postData() ?? "{}") as {
      expected_version?: number;
      reason?: string;
    };
    expect(withdrawBody).toEqual({ expected_version: 2, reason: "浏览器 e2e 复核撤回" });
    expect((await withdrawResponse).status()).toBe(200);
    expect(api.count("POST /api/bank-flow-rule-batches/no-oa-batch-e2e-001/withdraw")).toBe(1);
    await expect(page.getByText("批次已撤回")).toBeVisible();
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
    const openZone = page.getByTestId("zone-open");
    const pairedGroup = page.getByTestId("candidate-group-paired-bank-flow-rule-batch:bank_flow_rule_batch_e2e_fee");

    await expect(pairedGroup).toBeVisible();
    await expect(pairedZone.getByText("流水规则手续费批次")).toBeVisible();
    await expect(pairedZone.getByText("当前显示 1 条摘要")).toBeVisible();
    await expect(pairedZone.getByText("实际 4 条流水")).toBeVisible();
    await expect(pairedZone.getByText("流水规则手续费明细 1")).toHaveCount(0);

    const expandButton = pairedZone.getByRole("button", { name: "展开流水规则批次明细，4 条" });
    await expect(expandButton).toBeVisible();
    await expandButton.click();
    await expect(pairedZone.getByText("流水规则手续费明细 1")).toBeVisible();
    await expect(pairedZone.getByText("流水规则手续费明细 4")).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "收起流水规则批次明细" })).toBeVisible();

    const invoiceRequiredGroup = page.getByTestId(
      "candidate-group-open-bank-flow-rule-batch:bank_flow_rule_batch_e2e_invoice_required",
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
