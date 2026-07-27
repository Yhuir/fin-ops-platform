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

function waitForBatchAccountingList(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/batch-accounting");
  });
}

function createBatchAccountingLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/batch-accounting",
    pageKey: "batch-accounting",
    module: "batch-accounting",
  });
}

function responseFor(method: string, pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === method && new URL(response.url()).pathname.endsWith(pathname);
}

test.describe("batch accounting browser flow", () => {
  test("recovers list after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      batchAccountingFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });
    const recordLatency = createBatchAccountingLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "batch-accounting.open-page-load-failure",
      visibleLabel: "批量账务",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/batch-accounting");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("批量账务数据加载暂时失败，请刷新后重试。")).toBeVisible());
    });
    await expect(page.getByText("批量账务数据加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("当前年份暂无批量账务流水")).toHaveCount(0);
    expect(api.count("GET /api/batch-accounting")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `batch-accounting.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForBatchAccountingList(page);
        await page.getByRole("button", { name: "刷新" }).click();
        const response = await mark("apiLatencyMs", responsePromise);
        recovered = response.status() === 200;
        if (recovered) {
          await mark("finalSettledLatencyMs", expect(page.getByRole("table", { name: "可关联OA项" })).toBeVisible());
        } else {
          await mark("firstVisibleResponseLatencyMs", expect(page.getByText("批量账务数据加载暂时失败，请刷新后重试。")).toBeVisible());
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("批量账务数据加载暂时失败，请刷新后重试。")).toHaveCount(0);
    const bankPanel = page.getByRole("region", { name: "批量账务流水" });
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");
    const oaTable = page.getByRole("table", { name: "可关联OA项" });
    await expect(oaTable.getByRole("checkbox", { name: "选择 刘晨 2026-04-02" })).toBeVisible();
    await expect(page.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();
    expect(api.count("GET /api/batch-accounting")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps the bank rail readable in a narrow desktop viewport", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await page.setViewportSize({ width: 1180, height: 720 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBatchAccountingLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "batch-accounting.open-page-narrow",
      visibleLabel: "批量账务",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/batch-accounting");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("region", { name: "批量账务流水" })).toBeVisible());
    });

    const bankPanel = page.getByRole("region", { name: "批量账务流水" });
    const bankHeader = bankPanel.locator(".batch-accounting-bank-panel__header");
    const title = bankPanel.locator(".batch-accounting-bank-panel__title");
    const subtitle = bankPanel.locator(".batch-accounting-bank-panel__subtitle");
    const yearInput = page.getByLabel("流水年份");
    const pagination = page.getByRole("group", { name: "批量账务流水分页" });

    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*建行 8106/ })).toBeVisible();

    const headerBox = await bankHeader.boundingBox();
    const titleBox = await title.boundingBox();
    const subtitleBox = await subtitle.boundingBox();
    const yearBox = await yearInput.boundingBox();
    const paginationBox = await pagination.boundingBox();

    expect(headerBox).not.toBeNull();
    expect(titleBox).not.toBeNull();
    expect(subtitleBox).not.toBeNull();
    expect(yearBox).not.toBeNull();
    expect(paginationBox).not.toBeNull();
    expect(titleBox!.height).toBeLessThan(38);
    expect(subtitleBox!.height).toBeLessThan(48);

    const headerRight = headerBox!.x + headerBox!.width + 1;
    for (const box of [titleBox!, subtitleBox!, yearBox!, paginationBox!]) {
      expect(box.x).toBeGreaterThanOrEqual(headerBox!.x - 1);
      expect(box.x + box.width).toBeLessThanOrEqual(headerRight);
    }
    expect(browserErrors).toEqual([]);
  });

  test("submits and withdraws daily reimbursement rows through page-access convergence", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBatchAccountingLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "batch-accounting.open-page",
      visibleLabel: "批量账务",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/batch-accounting");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true"));
    });
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();

    const bankPanel = page.getByRole("region", { name: "批量账务流水" });
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const oaTable = page.getByRole("table", { name: "可关联OA项" });
    await recordLatency({
      operationId: "batch-accounting.select-oa-liu",
      visibleLabel: "选择 刘晨 2026-04-02",
      actionType: "check",
    }, async (mark) => {
      await oaTable.getByRole("checkbox", { name: "选择 刘晨 2026-04-02" }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 OA 1 项")).toBeVisible());
    });
    await recordLatency({
      operationId: "batch-accounting.select-oa-wang",
      visibleLabel: "选择 王青 2026-04-03",
      actionType: "check",
    }, async (mark) => {
      await oaTable.getByRole("checkbox", { name: "选择 王青 2026-04-03" }).check();
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 OA 2 项")).toBeVisible());
    });
    await expect(page.getByText("已选 OA 2 项")).toBeVisible();
    await expect(page.getByText("已选 OA 金额 1,200.00")).toBeVisible();
    await expect(page.getByText("差额 0.00")).toBeVisible();

    const batchAccountingGetsBeforeSubmit = api.count("GET /api/batch-accounting");
    await recordLatency({
      operationId: "batch-accounting.submit-relation",
      visibleLabel: "关联OA项与流水",
      actionType: "click",
    }, async (mark) => {
      const submitResponse = page.waitForResponse(responseFor("POST", "/api/batch-accounting/submit"));
      const reloadResponse = waitForBatchAccountingList(page);
      await page.getByRole("button", { name: "关联OA项与流水" }).click();
      await mark("apiLatencyMs", submitResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("已关联批量账务流水与 2 项 OA。")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    await expect(page.getByText("已关联批量账务流水与 2 项 OA。")).toBeVisible();
    expect(api.count("POST /api/batch-accounting/submit")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/batch-accounting")).toBe(batchAccountingGetsBeforeSubmit + 1);
    await expect(page.getByRole("button", { name: "已提交 1" })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    await recordLatency({
      operationId: "batch-accounting.open-submitted-bucket",
      visibleLabel: "已提交 1",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "已提交 1" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true"));
      await mark("finalSettledLatencyMs", expect(page.getByRole("table", { name: "已关联OA项" })).toBeVisible());
    });
    await expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const submittedTable = page.getByRole("table", { name: "已关联OA项" });
    await expect(submittedTable.getByRole("row", { name: /刘晨.*品牌广告投放.*700.00/ })).toBeVisible();
    await expect(submittedTable.getByRole("row", { name: /王青.*客户拜访差旅报销.*500.00/ })).toBeVisible();
    await expect(page.getByText("银行流水金额 1,200.00")).toBeVisible();
    await expect(page.getByText("已选 OA 2 项")).toBeVisible();
    await expect(page.getByText("差额 0.00")).toBeVisible();

    const batchAccountingGetsBeforeWithdraw = api.count("GET /api/batch-accounting");
    const withdrawDialog = page.getByRole("dialog", { name: "撤回关联" });
    await recordLatency({
      operationId: "batch-accounting.open-withdraw-dialog",
      visibleLabel: "撤回关联",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "撤回关联" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(withdrawDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(withdrawDialog.getByLabel("撤回原因")).toBeVisible());
    });
    await recordLatency({
      operationId: "batch-accounting.fill-withdraw-reason",
      visibleLabel: "撤回原因",
      actionType: "fill",
    }, async (mark) => {
      await withdrawDialog.getByLabel("撤回原因").fill("浏览器回归验证撤回");
      await mark("finalSettledLatencyMs", expect(withdrawDialog.getByLabel("撤回原因")).toHaveValue("浏览器回归验证撤回"));
    });
    await recordLatency({
      operationId: "batch-accounting.confirm-withdraw",
      visibleLabel: "确认撤回",
      actionType: "click",
    }, async (mark) => {
      const withdrawResponse = page.waitForResponse(responseFor("POST", "/api/batch-accounting/BA-REL-202604-001/withdraw"));
      const reloadResponse = waitForBatchAccountingList(page);
      await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();
      await mark("apiLatencyMs", withdrawResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("已撤回批量账务关联。")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    await expect(page.getByText("已撤回批量账务关联。")).toBeVisible();
    expect(api.count("POST /api/batch-accounting/BA-REL-202604-001/withdraw")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/batch-accounting")).toBe(batchAccountingGetsBeforeWithdraw + 1);
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByText("当前年份暂无批量账务流水")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    await recordLatency({
      operationId: "batch-accounting.open-unsubmitted-bucket-after-withdraw",
      visibleLabel: "未提交 1",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "未提交 1" }).click();
      await mark("finalSettledLatencyMs", expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true"));
    });
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("table", { name: "可关联OA项" }).getByRole("checkbox", { name: "选择 刘晨 2026-04-02" })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
