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
      && url.pathname === "/api/no-oa-bank-batches";
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
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "工资 1批 · 1条",
    tableName: "工商银行6386流水",
    transactionId: "no-oa-bank-e2e-salary",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "过节费 1批 · 1条",
    tableName: "中国银行7001流水",
    transactionId: "no-oa-bank-e2e-holiday_bonus",
  },
  {
    primaryButton: "薪资社保福利 4批 · 4条",
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
    primaryButton: "薪资社保福利 4批 · 4条",
    subButton: "社保 1批 · 1条",
    tableName: "民生银行5566流水",
    transactionId: "no-oa-bank-e2e-social_security",
  },
];

test.describe("no-OA bank batches browser flow", () => {
  test("recovers list after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      noOaBankBatchFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
    await expect(page.getByText("免OA流水批次加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    let recovered = false;
    for (let attempt = 0; attempt < 4 && !recovered; attempt += 1) {
      const responsePromise = waitForNoOaBankBatches(page);
      await page.getByRole("button", { name: "刷新" }).click();
      const response = await responsePromise;
      recovered = response.status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("免OA流水批次加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toBeDisabled();
    expect(api.count("GET /api/no-oa-bank-batches")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps visible rows while a stale no-OA read model refreshes to fresh", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      noOaBankBatchReadModelStatuses: ["stale", "fresh"],
      sessionMode: "full_access",
    });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);

    await expect.poll(() => api.count("GET /api/no-oa-bank-batches"), {
      timeout: 3_000,
    }).toBeGreaterThanOrEqual(2);

    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(page.getByText("当前标签下暂无流水")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("shows selectable checkboxes for every ordinary draft no-OA batch type", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      noOaBankBatchScenario: "ordinaryDraftMatrix",
      sessionMode: "full_access",
    });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
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

  test("saves tag scope through the freshness barrier and reloads the no-OA list", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");

    await page.getByRole("button", { name: "免OA流水标签管理" }).click();
    const tagDrawer = page.getByRole("dialog", { name: "免OA流水标签管理" });
    await expect(tagDrawer).toBeVisible();
    await expect(tagDrawer.getByLabel("费用 / 手续费")).toBeChecked();
    await tagDrawer.getByLabel("人工成本 / 工资").check();

    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/no-oa-bank-batches/tag-selection")
      && request.method() === "PUT",
    );
    const saveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/no-oa-bank-batches/tag-selection")
      && response.request().method() === "PUT",
    );
    const barrierRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/operation-barrier/status")
      && request.method() === "POST",
    );
    await tagDrawer.getByRole("button", { name: "保存" }).click();

    const saveBody = JSON.parse((await saveRequest).postData() ?? "{}") as {
      expected_version?: number;
      selected_tag_codes?: string[];
    };
    expect(saveBody).toEqual({
      expected_version: 3,
      selected_tag_codes: ["fee", "salary"],
    });
    expect((await saveResponse).status()).toBe(200);
    const barrierBody = JSON.parse((await barrierRequest).postData() ?? "{}") as {
      targets?: Array<{ read_model_key?: string; readModelKey?: string; scope_key?: string; scopeKey?: string }>;
    };
    expect(barrierBody.targets).toEqual([
      { read_model_key: "no_oa_bank_batch", scope_key: "all" },
    ]);
    await expect(page.getByText("免OA流水标签范围已保存")).toBeVisible();
    await expect(tagDrawer).toHaveCount(0);
    expect(api.count("PUT /api/no-oa-bank-batches/tag-selection")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/no-oa-bank-batches")).toBeGreaterThanOrEqual(2);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("submits a selected no-OA bank row, waits for freshness, and withdraws the submitted batch", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      noOaCostFanout: true,
      sessionMode: "full_access",
    });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
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
      request.url().endsWith("/api/no-oa-bank-batches/submit-selection")
        && request.method() === "POST",
    );
    const submitResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/no-oa-bank-batches/submit-selection")
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
    expect(api.count("POST /api/no-oa-bank-batches/submit-selection")).toBe(1);
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

    await page.goto("/no-oa-bank-batches");
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
      request.url().endsWith("/api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")
        && request.method() === "POST",
    );
    const withdrawResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")
        && response.request().method() === "POST",
    );
    await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();
    const withdrawBody = JSON.parse((await withdrawRequest).postData() ?? "{}") as {
      expected_version?: number;
      reason?: string;
    };
    expect(withdrawBody).toEqual({ expected_version: 2, reason: "浏览器 e2e 复核撤回" });
    expect((await withdrawResponse).status()).toBe(200);
    expect(api.count("POST /api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")).toBe(1);
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
});
