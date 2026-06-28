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

function waitForTurnoverLedger(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/turnover-ledger");
  });
}

test.describe("turnover ledger browser flow", () => {
  test("recovers grouped ledger after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      turnoverLedgerFailuresBeforeSuccess: 2,
    });

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
    await expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("暂无往来款台账")).toHaveCount(0);
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      const responsePromise = waitForTurnoverLedger(page);
      await page.getByRole("button", { name: "刷新台账" }).click();
      recovered = (await responsePromise).status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toHaveCount(0);
    const table = page.getByRole("table", { name: "往来款左右双栏台账" });
    await expect(table).toBeVisible();
    await expect(table.getByText("云南建设有限公司")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeDisabled();
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("uses direct grouped ledger data without page-level read model gating", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
    await expect(page.getByText("往来款台账正在刷新，当前展示的是非最新数据。")).toHaveCount(0);

    const table = page.getByRole("table", { name: "往来款左右双栏台账" });
    await expect(table).toBeVisible();
    await expect(table.getByText("云南建设有限公司")).toBeVisible();
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
    await expect(table.getByRole("row", { name: /turnover-bank-expense-1000.*外部往来款付款.*归还借款/ })).toBeVisible();
    await expect(table.getByRole("row", { name: /turnover-bank-income-1000.*外部往来款收款.*收回借款/ })).toBeVisible();

    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" }).check();
    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-income-1000" }).check();
    await expect(page.getByText("已选 2 笔")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeEnabled();
    await page.getByRole("button", { name: "确认闭环" }).click();
    await expect(page.getByRole("dialog", { name: "确认外部往来闭环" })).toBeVisible();
    expect(api.count("POST /api/turnover-ledger/closures/confirm")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves turnover tag selection and directly reloads the ledger", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();
    const ledgerLoadsBeforeSave = api.count("GET /api/turnover-ledger");

    await page.getByRole("button", { name: "外部往来款标签设置" }).click();
    const drawer = page.getByRole("dialog", { name: "外部往来款标签设置" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByLabel("外部往来款付款")).toBeChecked();
    await expect(drawer.getByLabel("外部往来款收款")).toBeChecked();

    await drawer.getByLabel("外部往来款收款").uncheck();
    await drawer.getByRole("button", { name: "保存" }).click();

    await expect(page.getByText("外部往来款标签设置已保存")).toBeVisible();
    await expect(drawer).toHaveCount(0);
    expect(api.lastBody("PUT /api/turnover-ledger/tag-selection")).toEqual({
      expected_version: 1,
      selected_tag_codes: ["external_turnover_payment"],
    });
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThan(ledgerLoadsBeforeSave);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("confirms and withdraws a manual turnover closure through direct reloads", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      turnoverCostFanout: true,
    });

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();

    const table = page.getByRole("table", { name: "往来款左右双栏台账" });
    await expect(table).toBeVisible();
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();

    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" }).check();
    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-income-1000" }).check();
    await expect(page.getByText("已选 2 笔")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeEnabled();
    await page.getByRole("button", { name: "确认闭环" }).click();

    const drawer = page.getByRole("dialog", { name: "确认外部往来闭环" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("turnover-bank-expense-1000")).toBeVisible();
    await expect(drawer.getByText("turnover-bank-income-1000")).toBeVisible();
    await expect(drawer.getByTestId("turnover-closure-delta")).toHaveText("0.00");
    await drawer.getByRole("button", { name: "确定" }).click();

    await expect(page.getByText("外部往来闭环已确认")).toBeVisible();
    await expect(page.getByRole("heading", { name: "操作失败" })).toHaveCount(0);
    await expect(page.getByText("银行流水状态已变化，请刷新后重试。")).toHaveCount(0);
    expect(api.count("POST /api/turnover-ledger/closures/confirm")).toBe(1);
    await expect(page.getByText("收支闭环").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const costExplorerResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const costPayload = await (await costExplorerResponse).json() as Record<string, unknown>;
    expect("read_model_status" in costPayload).toBe(false);
    expect("read_model_scope_key" in costPayload).toBe(false);
    await page.getByRole("button", { name: "按项目" }).click();
    const turnoverCostProject = page.getByRole("button", { name: /外部往来闭环成本项目/ });
    await expect(turnoverCostProject).toBeVisible();
    await expect(turnoverCostProject).toContainText("1,000.00");
    await turnoverCostProject.click();
    await page.getByRole("button", { name: /外部往来款付款 1 条流水/ }).click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("浏览器 e2e 归还借款");
    await expect(projectRows).toContainText("建设银行");
    await expectNoUnexpectedSuccessUiErrors(page);

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(table).toBeVisible();
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" }).check();
    await expect(page.getByRole("button", { name: "撤回闭环" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认闭环" })).toHaveCount(0);
    await page.getByRole("button", { name: "撤回闭环" }).click();

    await expect(page.getByText("外部往来闭环已撤回")).toBeVisible();
    expect(api.count("POST /api/turnover-ledger/relations/turnover_rel_e2e_closure/withdraw")).toBe(1);
    await expect(page.getByText("收支闭环")).toHaveCount(0);
    await expect(table.getByText("未闭环")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
