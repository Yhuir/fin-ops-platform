import { lstat, readFile } from "node:fs/promises";

import { expect, test, type Locator, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import {
  createOperationLatencyRecorder,
  createWorkbenchDirectCommitVisibilityRecorder,
  type WorkbenchDirectCommitVisibilityRunMode,
  type WorkbenchDirectCommitVisibilitySampleBinding,
} from "./fixtures/operationLatency";
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

async function clickCheckbox(checkbox: Locator) {
  const label = checkbox.locator("xpath=ancestor::label[1]");
  await (await label.count() ? label : checkbox).click();
}

const ordinaryBankFlowRuleCheckboxCases = [
  {
    primaryButton: "费用 1批 · 1条",
    subButton: "手续费 1批 · 1条",
    tableName: "建设银行8106流水",
    accessibleName: "选择流水 建设银行 2026-05-03 10:20:00 1.00 建设银行 8106",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "工资 1批 · 1条",
    tableName: "工商银行6386流水",
    accessibleName: "选择流水 工商银行 2026-05-03 10:20:00 2.00 工商银行 6386",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "过节费 1批 · 1条",
    tableName: "中国银行7001流水",
    accessibleName: "选择流水 中国银行 2026-05-03 10:20:00 3.00 中国银行 7001",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "奖金 1批 · 1条",
    tableName: "招商银行9988流水",
    accessibleName: "选择流水 招商银行 2026-05-03 10:20:00 4.00 招商银行 9988",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "税款 1批 · 1条",
    tableName: "农业银行2211流水",
    accessibleName: "选择流水 农业银行 2026-05-03 10:20:00 5.00 农业银行 2211",
  },
  {
    primaryButton: "税款 2批 · 2条",
    subButton: "国库税款 1批 · 1条",
    tableName: "交通银行3344流水",
    accessibleName: "选择流水 交通银行 2026-05-03 10:20:00 6.00 交通银行 3344",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "社保 1批 · 1条",
    tableName: "民生银行5566流水",
    accessibleName: "选择流水 民生银行 2026-05-03 10:20:00 7.00 民生银行 5566",
  },
];

type WorkbenchDirectCommitVisibilityFixture = WorkbenchDirectCommitVisibilitySampleBinding & {
  fixture_ownership: "test_owned";
  submit: { path: string; body: Record<string, unknown> };
  recovery: { path: string; body: Record<string, unknown> };
};

function payloadString(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function browserJsonRequest(
  page: Page,
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>,
) {
  return page.evaluate(async ({ requestMethod, requestPath, requestBody }) => {
    const response = await fetch(requestPath, {
      method: requestMethod,
      credentials: "include",
      headers: requestBody ? { "Content-Type": "application/json" } : undefined,
      body: requestBody ? JSON.stringify(requestBody) : undefined,
    });
    return {
      ok: response.ok,
      status: response.status,
      payload: await response.json() as Record<string, unknown>,
    };
  }, { requestMethod: method, requestPath: path, requestBody: body });
}

async function runWithRecovery<T>(operation: () => Promise<T>, recovery: () => Promise<void>) {
  let result: T | undefined;
  let operationError: unknown;
  try {
    result = await operation();
  } catch (error) {
    operationError = error;
  }
  try {
    await recovery();
  } catch (recoveryError) {
    if (operationError !== undefined) {
      throw new AggregateError([operationError, recoveryError], "operation and recovery both failed");
    }
    throw recoveryError;
  }
  if (operationError !== undefined) throw operationError;
  return result as T;
}

async function recoverWorkbenchDirectCommitVisibilityFixture(
  page: Page,
  mode: WorkbenchDirectCommitVisibilityRunMode,
  sample: WorkbenchDirectCommitVisibilityFixture,
) {
  const detailPath = `/api/bank-flow-rule-batches/${encodeURIComponent(sample.batch_id)}`;
  const request = async (method: "GET" | "POST", path: string, body?: Record<string, unknown>) => {
    if (mode === "isolated") {
      return browserJsonRequest(page, method, path, body);
    }
    const response = method === "GET"
      ? await page.context().request.get(path)
      : await page.context().request.post(path, { data: body });
    return {
      ok: response.ok(),
      status: response.status(),
      payload: await response.json() as Record<string, unknown>,
    };
  };
  const loadStatus = async () => {
    const result = await request("GET", detailPath);
    if (!result.ok || !result.payload || typeof result.payload.batch !== "object" || result.payload.batch === null) {
      throw new Error(`cannot determine exact fixture batch state (${result.status})`);
    }
    const batch = result.payload.batch as Record<string, unknown>;
    const batchId = payloadString(batch, ["id", "batch_id", "batchId"]);
    const status = payloadString(batch, ["status"]).toLowerCase();
    if (batchId !== sample.batch_id || !status) {
      throw new Error("cannot determine exact fixture batch identity or status");
    }
    return status;
  };

  const initialStatus = await loadStatus();
  if (["withdrawn", "unsubmitted", "inactive", "draft"].includes(initialStatus)) return;
  if (!["active", "submitted"].includes(initialStatus)) {
    throw new Error(`unexpected fixture batch status: ${initialStatus}`);
  }
  const recoveryResult = await request("POST", sample.recovery.path, sample.recovery.body);
  if (!recoveryResult.ok) throw new Error(`withdraw recovery failed with ${recoveryResult.status}`);
  if ((await loadStatus()) !== "withdrawn") {
    throw new Error("withdraw recovery did not restore the test-owned fixture to inactive");
  }
}

async function loadWorkbenchDirectCommitVisibilityFixtures(
  mode: WorkbenchDirectCommitVisibilityRunMode,
  requestedSampleCount: number,
) {
  const manifestPath = String(
    process.env.FIN_OPS_E2E_WORKBENCH_DIRECT_COMMIT_VISIBILITY_FIXTURE_MANIFEST ?? "",
  ).trim();
  if (!manifestPath) {
    throw new Error("FIN_OPS_E2E_WORKBENCH_DIRECT_COMMIT_VISIBILITY_FIXTURE_MANIFEST is required");
  }
  const metadata = await lstat(manifestPath);
  const operatorUid = typeof process.getuid === "function" ? process.getuid() : metadata.uid;
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error("Workbench direct commit visibility fixture manifest must be a regular non-symlink file");
  }
  if ((metadata.uid !== 0 && metadata.uid !== operatorUid) || (metadata.mode & 0o077) !== 0) {
    throw new Error("Workbench direct commit visibility fixture manifest must be root/operator-owned with no group/world permissions");
  }
  const manifest = JSON.parse(await readFile(manifestPath, "utf-8")) as {
    fixture_ownership?: string;
    environment?: string;
    isolated_repeat_count?: number;
    samples?: WorkbenchDirectCommitVisibilityFixture[];
  };
  const templates = Array.isArray(manifest.samples) ? manifest.samples : [];
  const isolatedRepeatCount = Number(manifest.isolated_repeat_count ?? templates.length);
  if (manifest.fixture_ownership !== "test_owned" || templates.some((sample) => sample.fixture_ownership !== "test_owned")) {
    throw new Error("Workbench direct commit visibility fixtures must be test_owned");
  }
  if (mode === "production_smoke" && (templates.length !== 1 || isolatedRepeatCount !== 1)) {
    throw new Error("production_smoke requires exactly one fixture sample");
  }
  if (mode === "isolated" && (
    manifest.environment !== "isolated_prod_equivalent_direct_canonical_get"
    || templates.length < 1
    || isolatedRepeatCount !== requestedSampleCount
  )) {
    throw new Error("isolated fixture manifest must explicitly bind the direct combined-read sample count");
  }
  const selected = mode === "production_smoke"
    ? templates
    : Array.from({ length: requestedSampleCount }, (_, index) => ({
        ...templates[index % templates.length],
        sample_id: `${templates[index % templates.length].sample_id}:repeat-${String(index + 1).padStart(3, "0")}`,
      }));
  const identities = new Set<string>();
  for (const sample of selected) {
    const required = [sample.sample_id, sample.batch_id, sample.business_identity, sample.exact_scope];
    if (required.some((value) => !String(value ?? "").trim()) || sample.exact_scope === "all") {
      throw new Error("fixture sample identity and exact_scope are required");
    }
    if (!Array.isArray(sample.transaction_ids) || sample.transaction_ids.length === 0) {
      throw new Error("fixture transaction_ids are required");
    }
    if (!sample.submit?.path.includes("/api/bank-flow-rule-batches/") || !sample.recovery?.path.endsWith("/withdraw")) {
      throw new Error("fixture submit and exact withdraw recovery paths are required");
    }
    const identity = [sample.sample_id, sample.batch_id, ...sample.transaction_ids, sample.business_identity].join("|");
    if (identities.has(identity)) throw new Error("fixture sample identities must be unique");
    identities.add(identity);
  }
  return selected;
}

test.describe("bank flow rule batches browser flow", () => {
  test("recovers list after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      bankFlowRuleBatchFailuresBeforeSuccess: 2,
      sessionMode: "user",
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
    await expect(page.getByRole("radio", { name: "未提交 1" })).toBeChecked();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("grid", { name: "建设银行8106流水" });
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
      sessionMode: "user",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toBeChecked();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("grid", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await expect(draftTable.getByRole("columnheader")).toHaveText([
      "",
      "对方户名",
      "交易时间",
      "金额",
      "摘要/用途/备注",
    ]);
    await expect(draftTable.getByText("建设银行8106", { exact: true })).toHaveCount(0);
    await expect(draftTable.getByText("费用", { exact: true })).toHaveCount(0);
    await expect(draftTable.getByText("手续费", { exact: true })).toHaveCount(0);
    const visibleRowCheckbox = draftTable.getByRole("checkbox", {
      name: "选择流水 建设银行 2026-05-03 10:20:00 8.80 建设银行 8106",
    });
    await expect(visibleRowCheckbox).toBeVisible();
    const checkboxControl = visibleRowCheckbox.locator("xpath=ancestor::label[1]")
      .locator(".bank-flow-rule-batches-checkbox__control");
    await expect(checkboxControl).toBeVisible();
    await expect.poll(async () => (await checkboxControl.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(18);
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    const settledListReads = api.count("GET /api/bank-flow-rule-batches");
    await page.waitForTimeout(1_500);
    expect(api.count("GET /api/bank-flow-rule-batches")).toBe(settledListReads);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await expect(page.getByRole("radio", { name: "未提交 1" })).toBeChecked();
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
      sessionMode: "user",
    });

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 7" })).toBeChecked();

    for (const [index, item] of ordinaryBankFlowRuleCheckboxCases.entries()) {
      await page.getByRole("button", { name: item.primaryButton, exact: true }).click();
      await page.getByRole("button", { name: item.subButton, exact: true }).click();

      const table = page.getByRole("grid", { name: item.tableName });
      await expect(table).toBeVisible();
      const checkbox = table.getByRole("checkbox", { name: item.accessibleName });
      await expect(checkbox).toBeVisible();
      await expect(checkbox).toBeEnabled();
      if (index === 0) {
        await clickCheckbox(checkbox);
        await expect(checkbox).toBeChecked();
        const refreshedCheckbox = page
          .getByRole("grid", { name: item.tableName })
          .getByRole("checkbox", { name: item.accessibleName });
        await clickCheckbox(refreshedCheckbox);
        await expect(refreshedCheckbox).not.toBeChecked();
      }
    }

    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves tag rules and reloads the canonical list once", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toBeChecked();
    const monthReload = waitForBankFlowRuleBatches(page);
    await page.getByRole("button", { name: /批次月份：\d{4}年\d{1,2}月/ }).click();
    await page.getByRole("dialog", { name: "批次月份选择器" }).getByRole("button", { name: "五月" }).click();
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
      await clickCheckbox(checkbox);
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
      sessionMode: "user",
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

  test("submits internal transfer batches without blocking on workbench visibility refresh", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      bankFlowRuleBatchScenario: "internalTransferPairs",
      sessionMode: "user",
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 2" })).toBeChecked();
    await expect(page.getByRole("button", { name: "内部往来款 2批 · 4条" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "主标签本身 2批 · 4条" })).toBeVisible();

    const firstBatch = page.locator(".bank-flow-rule-batches-batch").filter({ hasText: "光大银行8826" });
    await expect(firstBatch).toBeVisible();
    await expect(firstBatch.getByText("2 条 · 合计 50000.00")).toBeVisible();
    await expect(page.getByRole("grid", { name: "光大银行8826流水" })).toBeVisible();
    const secondBatch = page
      .locator(".bank-flow-rule-batches-batch")
      .filter({ hasText: "建设银行8106" })
      .filter({ hasText: "2 条 · 合计 7000.00" });
    await expect(secondBatch.getByText("2 条 · 合计 7000.00")).toBeVisible();

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
      scope_month?: string;
    };
    expect(submitBody).toEqual({ expected_version: 1, note: "", scope_month: "2026-01" });
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
      sessionMode: "user",
      workbenchBankFlowRuleBatchScenario: true,
      bankFlowRuleWorkbenchConvergence: true,
    });
    const recordLatency = createBankFlowRuleBatchLatencyRecorder(page, testInfo);

    await page.goto("/bank-flow-rule-batches");
    await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toBeChecked();
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("grid", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await clickCheckbox(draftTable.getByLabel("选择流水 建设银行 2026-05-03 10:20:00 8.80 建设银行 8106"));
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
    const resolvedSubmitResponse = await submitResponse;
    expect(resolvedSubmitResponse.status()).toBe(200);
    const submitPayload = await resolvedSubmitResponse.json() as Record<string, unknown>;
    expect(submitPayload).not.toHaveProperty("operation_barrier_targets");
    expect(submitPayload).not.toHaveProperty("workbench_refresh_required");
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
    await costExplorerResponse;
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByRole("button", { name: /流水规则手续费成本项目/ })).toHaveCount(0);
    await expect(page.getByText("网银手续费")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const workbenchReadsBeforeVisit = api.count("GET /api/workbench");
    const directInitialResponse = page.waitForResponse((response) => (
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/workbench")
      && response.status() === 200
    ));
    await page.goto("/");
    expect((await directInitialResponse).status()).toBe(200);
    // React StrictMode may remount once in the dev E2E server; both reads are
    // The Workbench opens from one ordinary combined initial read.
    expect(api.count("GET /api/workbench")).toBeGreaterThan(workbenchReadsBeforeVisit);
    expect(api.count("GET /api/workbench")).toBeLessThanOrEqual(workbenchReadsBeforeVisit + 2);
    const canonicalGroup = page.getByTestId(
      "candidate-group-paired-bank-flow-rule-batch:bank_flow_rule_batch_e2e_fee",
    );
    await expect(canonicalGroup).toBeVisible();
    await expect(canonicalGroup).toContainText("流水规则手续费批次");
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    await page.goto("/bank-flow-rule-batches");
    await page.getByRole("radio", { name: "已提交 1" }).click();
    await expect(page.getByRole("radio", { name: "已提交 1" })).toBeChecked();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "建设银行8106流水" })).toBeVisible();
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

    await page.getByRole("radio", { name: "历史 1" }).click();
    await expect(page.getByRole("radio", { name: "历史 1" })).toBeChecked();
    await expect(page.getByText("已撤回", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "撤回批次" })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("renders bank flow rule batches in workbench according to OA and invoice requirements", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
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

    await invoiceRequiredGroup.getByRole("row", { name: /需要发票后才进入已配对/ }).getByRole("cell").first().click();
    await invoiceRequiredGroup.getByRole("row", { name: /BFR-INV-E2E-001/ }).getByRole("cell").first().click();
    await expect(openZone.getByText("已选 2")).toBeVisible();

    const previewResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/actions/confirm-link/preview")
      && response.request().method() === "POST",
    );
    await openZone.getByRole("button", { name: "确认关联" }).click();
    expect((await previewResponse).status()).toBe(200);
    const previewDialog = page.getByRole("dialog", { name: "确认关联" });
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

test.describe("workbench direct commit visibility SLO", () => {
  test("recovers an exact test-owned batch after an ambiguous submit", async ({ page }) => {
    const sample = {
      sample_id: "ambiguous-submit",
      batch_id: "ambiguous-submit-batch",
      business_identity: "AMBIGUOUS-SUBMIT-IDENTITY",
      exact_scope: "2026-05",
      transaction_ids: ["ambiguous-submit-row"],
      fixture_ownership: "test_owned",
      submit: { path: "/api/bank-flow-rule-batches/ambiguous-submit-batch/submit", body: {} },
      recovery: {
        path: "/api/bank-flow-rule-batches/ambiguous-submit-batch/withdraw",
        body: { expected_version: 1, reason: "ambiguous submit recovery" },
      },
    } satisfies WorkbenchDirectCommitVisibilityFixture;
    let status = "draft";
    let submitAttempted = false;
    let recoveryCalls = 0;
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    await page.route("**/api/bank-flow-rule-batches/ambiguous-submit-batch**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      if (request.method() === "POST" && pathname.endsWith("/withdraw")) {
        recoveryCalls += 1;
        status = "withdrawn";
        await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ batch: { id: sample.batch_id, status } }),
      });
    });
    await page.goto("/");

    await expect(runWithRecovery(async () => {
      submitAttempted = true;
      status = "submitted";
      throw new Error("submit response lost after commit");
    }, async () => {
      if (submitAttempted) await recoverWorkbenchDirectCommitVisibilityFixture(page, "isolated", sample);
    })).rejects.toThrow("submit response lost after commit");

    expect(recoveryCalls).toBe(1);
    expect(status).toBe("withdrawn");
  });

  test("preserves both operation and exact-fixture recovery failures", async () => {
    const operationError = new Error("submit response lost");
    const recoveryError = new Error("recovery state unavailable");

    const failure = await runWithRecovery(
      async () => { throw operationError; },
      async () => { throw recoveryError; },
    ).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(AggregateError);
    expect((failure as AggregateError).errors).toEqual([operationError, recoveryError]);
  });

  test("measures direct mutation receipt to canonical GET to DOM visibility on one clock", async ({ page }) => {
    const directCommitVisibilityEnabled = process.env.FIN_OPS_E2E_WORKBENCH_DIRECT_COMMIT_VISIBILITY === "1";
    if (!directCommitVisibilityEnabled) return;
    const mode = String(
      process.env.FIN_OPS_E2E_WORKBENCH_DIRECT_COMMIT_VISIBILITY_MODE ?? "isolated",
    ) as WorkbenchDirectCommitVisibilityRunMode;
    if (mode !== "isolated" && mode !== "production_smoke") {
      throw new Error("invalid Workbench direct commit visibility SLO mode");
    }
    const requestedSampleCount = Number.parseInt(
      String(
        process.env.FIN_OPS_E2E_WORKBENCH_DIRECT_COMMIT_VISIBILITY_SAMPLES
        ?? (mode === "production_smoke" ? "1" : "100"),
      ),
      10,
    );
    if (!Number.isSafeInteger(requestedSampleCount) || requestedSampleCount < 1) {
      throw new Error("invalid Workbench direct commit visibility sample count");
    }
    if (mode === "isolated" && requestedSampleCount < 100) {
      throw new Error("isolated direct commit visibility SLO requires at least 100 samples");
    }
    test.setTimeout(Math.max(60_000, requestedSampleCount * 10_000));
    const samples = await loadWorkbenchDirectCommitVisibilityFixtures(mode, requestedSampleCount);
    const recorder = createWorkbenchDirectCommitVisibilityRecorder(mode, requestedSampleCount);
    if (mode === "isolated") {
      await installDeterministicApiMocks(page, {
        bankFlowRuleWorkbenchConvergence: true,
        sessionMode: "user",
        workbenchBankFlowRuleBatchScenario: true,
      });
    }
    const adminToken = String(process.env.FIN_OPS_E2E_ADMIN_TOKEN ?? "").trim();
    if (mode === "production_smoke" && !adminToken) {
      throw new Error("production_smoke requires FIN_OPS_E2E_ADMIN_TOKEN");
    }
    if (adminToken) {
      await page.context().setExtraHTTPHeaders({
        "Admin-Token": adminToken,
        Authorization: `Bearer ${adminToken}`,
      });
    }

    for (const sample of samples) {
      await page.goto("/bank-flow-rule-batches");
      await expect(page.getByRole("heading", { name: "流水规则批量处理" })).toBeVisible();
      let submitAttempted = false;
      await runWithRecovery(async () => {
        submitAttempted = true;
        const submitResult = mode === "isolated"
          ? await browserJsonRequest(page, "POST", sample.submit.path, sample.submit.body)
          : await (async () => {
              const response = await page.context().request.post(sample.submit.path, { data: sample.submit.body });
              return {
                ok: response.ok(),
                status: response.status(),
                payload: await response.json() as Record<string, unknown>,
              };
            })();
        if (!submitResult.ok) throw new Error(`bank-flow submit failed with ${submitResult.status}`);
        if (!JSON.stringify(submitResult.payload).includes(sample.batch_id)) {
          throw new Error("submit receipt does not bind the exact fixture batch_id");
        }
        const segment = recorder.startAtMutationReceipt(sample);

        const combinedResponse = page.waitForResponse(async (response) => {
          const url = new URL(response.url());
          if (
            response.request().method() !== "GET"
            || url.pathname !== "/api/workbench"
            || url.searchParams.get("month") !== "all"
            || response.status() !== 200
          ) {
            return false;
          }
          const payload = await response.json() as Record<string, unknown>;
          const serialized = JSON.stringify(payload);
          return sample.transaction_ids.every((rowId) => serialized.includes(rowId))
            && serialized.includes(sample.business_identity);
        });
        await page.getByRole("link", { name: "关联台" }).click();
        await combinedResponse;
        segment.markCanonicalReadVisible();

        const identity = page.getByText(sample.business_identity, { exact: true });
        if (await identity.count() !== 1) {
          throw new Error("business_identity must have one unique DOM locator");
        }
        await expect(identity).toBeVisible();
        segment.markDomVisible();
        segment.complete();
      }, async () => {
        if (submitAttempted) {
          await recoverWorkbenchDirectCommitVisibilityFixture(page, mode, sample);
        }
      });
    }
    await recorder.writeReport();
  });
});
