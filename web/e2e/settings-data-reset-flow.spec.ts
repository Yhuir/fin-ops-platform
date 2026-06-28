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

function responsePathMatches(responseUrl: string, pathname: string) {
  return new URL(responseUrl).pathname === pathname;
}

type RowsPayload = {
  rows?: unknown[];
};

test.describe("settings data reset browser flow", () => {
  test("runs data reset through impact confirmation, OA password review, job polling, and settings reload", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(page.getByRole("tree", { name: "设置分类" })).toBeVisible();
    await expect(page.getByRole("treeitem", { name: /数据重置/ })).toBeVisible();

    await page.getByRole("treeitem", { name: /数据重置/ }).click();
    const dataResetRegion = page.getByRole("region", { name: "数据重置" });
    await expect(dataResetRegion).toBeVisible();
    await expect(dataResetRegion.getByText("高风险操作")).toBeVisible();

    await dataResetRegion.getByRole("button", { name: "清除所有银行流水数据" }).click();
    const impactDialog = page.getByRole("dialog", { name: "确认数据重置" });
    await expect(impactDialog).toBeVisible();
    await expect(impactDialog.getByText("已导入银行流水会被清空")).toBeVisible();
    await impactDialog.getByRole("button", { name: "继续" }).click();

    const passwordDialog = page.getByRole("dialog", { name: "OA 密码复核" });
    await expect(passwordDialog).toBeVisible();
    await passwordDialog.getByLabel("当前 OA 用户密码").fill("oa-password-e2e");

    const settingsFetchCountBeforeReset = api.count("GET /api/workbench/settings");
    const createJobResponse = page.waitForResponse((response) =>
      response.url().includes("/api/workbench/settings/data-reset/jobs") && response.request().method() === "POST",
    );
    await passwordDialog.getByRole("button", { name: "确认清理" }).click();
    expect((await createJobResponse).status()).toBe(202);

    await expect.poll(() => api.count("POST /api/workbench/settings/data-reset/jobs")).toBe(1);
    await expect(dataResetRegion.getByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    await expect.poll(() =>
      api.count("GET /api/workbench/settings/data-reset/jobs/settings-reset-job-e2e-001"),
    ).toBeGreaterThanOrEqual(2);
    await expect.poll(() => api.count("GET /api/workbench/settings")).toBeGreaterThan(settingsFetchCountBeforeReset);
    await expect(page.getByRole("status").filter({ hasText: "已完成数据重置。" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "OA 密码复核" })).toBeHidden();
    await expectNoUnexpectedSuccessUiErrors(page);

    const bankRowsAfterResetResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/bank-details/transactions")
      && response.status() === 200);
    await page.getByRole("link", { name: "银行明细" }).click();
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRowsAfterReset = await (await bankRowsAfterResetResponse).json() as RowsPayload & Record<string, unknown>;
    expect("read_model_status" in bankRowsAfterReset).toBe(false);
    expect(bankRowsAfterReset.rows).toEqual([]);
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("智能工厂设备商")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const pendingRowsAfterResetResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/pending-invoices/rows")
      && response.status() === 200);
    await page.getByRole("link", { name: "待找发票" }).click();
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    const pendingRowsAfterReset = await (await pendingRowsAfterResetResponse).json() as RowsPayload & Record<string, unknown>;
    expect("read_model_status" in pendingRowsAfterReset).toBe(false);
    expect(pendingRowsAfterReset.rows?.length).toBeGreaterThan(0);
    await expect(page.getByText("智能工厂设备商").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
  });

  test("marks a project completed and verifies cost statistics active/all project scopes refresh", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "admin",
      settingsProjectScopeFanout: true,
    });
    const projectName = "昆明卷烟厂动力设备控制系统升级改造项目";

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await page.getByRole("treeitem", { name: /项目状态/ }).click();
    const projectsRegion = page.getByRole("region", { name: "项目状态管理" });
    await expect(projectsRegion).toBeVisible();
    const activeProjects = page.getByRole("table", { name: "进行中项目" });
    const completedProjects = page.getByRole("table", { name: "已完成项目" });
    await expect(activeProjects.getByText(projectName)).toBeVisible();

    await activeProjects.getByLabel(`${projectName} 标记完成`).click();
    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings")
      && request.method() === "POST");
    const saveResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/workbench/settings")
      && response.request().method() === "POST");
    await page.getByRole("button", { name: "保存设置" }).click();
    const saveBody = JSON.parse((await saveRequest).postData() ?? "{}") as {
      completed_project_ids?: string[];
    };
    expect(saveBody.completed_project_ids).toEqual(["settings-cost-project-e2e"]);
    expect((await saveResponse).status()).toBe(200);
    await expect(page.getByText("已保存关联台设置。")).toBeVisible();
    await expect(completedProjects.getByText(projectName)).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const activeCostExplorerResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
        && url.searchParams.get("project_scope") === "active"
        && response.status() === 200;
    });
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const activePayload = await (await activeCostExplorerResponse).json() as Record<string, unknown>;
    expect("read_model_status" in activePayload).toBe(false);
    await page.getByRole("button", { name: "按项目" }).click();
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByText(projectName)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const allScopeResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
        && url.searchParams.get("project_scope") === "all"
        && response.status() === 200;
    });
    await page.getByRole("button", { name: "项目范围：进行中" }).click();
    const allPayload = await (await allScopeResponse).json() as Record<string, unknown>;
    expect("read_model_status" in allPayload).toBe(false);
    await expect(page.getByRole("button", { name: "项目范围：所有项目" })).toBeVisible();
    const allProject = page.getByRole("button", { name: new RegExp(projectName) });
    await expect(allProject).toBeVisible();
    await expect(allProject).toContainText("4,800.00");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(api.count("POST /api/workbench/settings")).toBe(1);
    expect(browserErrors).toEqual([]);
  });
});
