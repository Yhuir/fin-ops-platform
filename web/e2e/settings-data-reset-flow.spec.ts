import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
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

function createSettingsLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/settings",
    pageKey: "settings",
    module: "settings",
  });
}

function waitForSettings(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/workbench/settings"));
}

function waitForDataResetJobCreate(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/workbench/settings/data-reset/jobs") && response.request().method() === "POST");
}

function waitForBankDetailRows(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/bank-details/transactions")
      && response.status() === 200);
}

function waitForPendingInvoiceRows(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/pending-invoices/rows")
      && response.status() === 200);
}

function waitForSettingsSave(page: Page) {
  return page.waitForResponse((response) =>
    response.url().endsWith("/api/workbench/settings")
      && response.request().method() === "POST");
}

type RowsCanonicalPayload = {
  rows?: unknown[];
};

function expectDirectCanonicalPayload(payload: Record<string, unknown>) {
  expect(payload).not.toHaveProperty("read_model_status");
  expect(payload).not.toHaveProperty("source_versions");
  expect(payload).not.toHaveProperty("refresh_enqueued");
}

test.describe("settings data reset browser flow", () => {
  test("runs data reset through impact confirmation, OA password review, job polling, and settings reload", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
    const recordLatency = createSettingsLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "settings.open-page-data-reset",
      visibleLabel: "设置",
      actionType: "navigate",
    }, async (mark) => {
      const settingsResponse = waitForSettings(page);
      await page.goto("/settings");
      expect((await mark("apiLatencyMs", settingsResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(page.getByRole("tree", { name: "设置分类" })).toBeVisible();
    await expect(page.getByRole("treeitem", { name: /数据重置/ })).toBeVisible();

    const dataResetRegion = page.getByRole("region", { name: "数据重置" });
    await recordLatency({
      operationId: "settings.open-data-reset-section",
      visibleLabel: "数据重置",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("treeitem", { name: /数据重置/ }).click();
      await mark("finalSettledLatencyMs", expect(dataResetRegion).toBeVisible());
    });
    await expect(dataResetRegion).toBeVisible();
    await expect(dataResetRegion.getByText("高风险操作")).toBeVisible();

    const impactDialog = page.getByRole("dialog", { name: "确认数据重置" });
    await recordLatency({
      operationId: "settings.open-bank-data-reset-impact",
      visibleLabel: "清除所有银行流水数据",
      actionType: "click",
    }, async (mark) => {
      await dataResetRegion.getByRole("button", { name: "清除所有银行流水数据" }).click();
      await mark("finalSettledLatencyMs", expect(impactDialog).toBeVisible());
    });
    await expect(impactDialog).toBeVisible();
    await expect(impactDialog.getByText("已导入银行流水会被清空")).toBeVisible();

    const passwordDialog = page.getByRole("dialog", { name: "OA 密码复核" });
    await recordLatency({
      operationId: "settings.continue-data-reset-impact",
      visibleLabel: "继续",
      actionType: "click",
    }, async (mark) => {
      await impactDialog.getByRole("button", { name: "继续" }).click();
      await mark("finalSettledLatencyMs", expect(passwordDialog).toBeVisible());
    });
    await expect(passwordDialog).toBeVisible();
    await recordLatency({
      operationId: "settings.fill-data-reset-oa-password",
      visibleLabel: "当前 OA 用户密码",
      actionType: "fill",
    }, async (mark) => {
      await passwordDialog.getByLabel("当前 OA 用户密码").fill("oa-password-e2e");
      await mark("finalSettledLatencyMs", expect(passwordDialog.getByRole("button", { name: "确认清理" })).toBeEnabled());
    });

    const settingsFetchCountBeforeReset = api.count("GET /api/workbench/settings");
    await recordLatency({
      operationId: "settings.confirm-data-reset",
      visibleLabel: "确认清理",
      actionType: "click",
    }, async (mark) => {
      const createJobResponse = waitForDataResetJobCreate(page);
      await passwordDialog.getByRole("button", { name: "确认清理" }).click();
      expect((await mark("apiLatencyMs", createJobResponse)).status()).toBe(202);
      await mark("firstVisibleResponseLatencyMs", expect(dataResetRegion.getByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled());
    });

    await expect.poll(() => api.count("POST /api/workbench/settings/data-reset/jobs")).toBe(1);
    await expect(dataResetRegion.getByRole("button", { name: /正在清理 app 内部状态。 25%/ })).toBeDisabled();
    await expect.poll(() =>
      api.count("GET /api/workbench/settings/data-reset/jobs/settings-reset-job-e2e-001"),
    ).toBeGreaterThanOrEqual(2);
    await expect.poll(() => api.count("GET /api/workbench/settings")).toBeGreaterThan(settingsFetchCountBeforeReset);
    await recordLatency({
      operationId: "settings.wait-data-reset-complete",
      visibleLabel: "settings_data_reset job polling",
      actionType: "poll",
    }, async (mark) => {
      await mark("finalSettledLatencyMs", expect(page.getByRole("status").filter({ hasText: "已完成数据重置。" })).toBeVisible());
    });
    await expect(page.getByRole("dialog", { name: "OA 密码复核" })).toBeHidden();
    await expectNoUnexpectedSuccessUiErrors(page);

    let bankRowsAfterReset: RowsCanonicalPayload | undefined;
    await recordLatency({
      route: "/bank-details",
      pageKey: "bank-details",
      module: "bank-details",
      operationId: "bank-details.open-after-settings-data-reset",
      visibleLabel: "银行明细",
      actionType: "click",
    }, async (mark) => {
      const bankRowsAfterResetResponse = waitForBankDetailRows(page);
      await page.getByRole("link", { name: "银行明细" }).click();
      const response = await mark("apiLatencyMs", bankRowsAfterResetResponse);
      bankRowsAfterReset = await response.json() as RowsCanonicalPayload;
      await mark("finalSettledLatencyMs", expect(page.getByTestId("bank-details-page")).toBeVisible());
    });
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    if (!bankRowsAfterReset) {
      throw new Error("missing bank rows after settings data reset");
    }
    expectDirectCanonicalPayload(bankRowsAfterReset as Record<string, unknown>);
    expect(bankRowsAfterReset.rows).toEqual([]);
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("智能工厂设备商")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    let pendingRowsAfterReset: RowsCanonicalPayload | undefined;
    await recordLatency({
      route: "/pending-invoices",
      pageKey: "pending-invoices",
      module: "pending-invoices",
      operationId: "pending-invoices.open-after-settings-data-reset",
      visibleLabel: "待找发票",
      actionType: "click",
    }, async (mark) => {
      const pendingRowsAfterResetResponse = waitForPendingInvoiceRows(page);
      await page.getByRole("link", { name: "待找发票" }).click();
      const response = await mark("apiLatencyMs", pendingRowsAfterResetResponse);
      pendingRowsAfterReset = await response.json() as RowsCanonicalPayload;
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    if (!pendingRowsAfterReset) {
      throw new Error("missing pending invoice rows after settings data reset");
    }
    expectDirectCanonicalPayload(pendingRowsAfterReset as Record<string, unknown>);
    expect(pendingRowsAfterReset.rows?.length).toBeGreaterThan(0);
    await expect(page.getByText("智能工厂设备商").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
  });

  test("marks a project completed and verifies cost statistics active project scope refresh", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "admin",
      settingsProjectScopeFanout: true,
    });
    const recordLatency = createSettingsLatencyRecorder(page, testInfo);
    const projectName = "昆明卷烟厂动力设备控制系统升级改造项目";

    await recordLatency({
      operationId: "settings.open-page-project-scope",
      visibleLabel: "设置",
      actionType: "navigate",
    }, async (mark) => {
      const settingsResponse = waitForSettings(page);
      await page.goto("/settings");
      expect((await mark("apiLatencyMs", settingsResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    const projectsRegion = page.getByRole("region", { name: "项目状态管理" });
    await recordLatency({
      operationId: "settings.open-project-status-section",
      visibleLabel: "项目状态",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("treeitem", { name: /项目状态/ }).click();
      await mark("finalSettledLatencyMs", expect(projectsRegion).toBeVisible());
    });
    await expect(projectsRegion).toBeVisible();
    const activeProjects = page.getByRole("table", { name: "进行中项目" });
    const completedProjects = page.getByRole("table", { name: "已完成项目" });
    await expect(activeProjects.getByText(projectName)).toBeVisible();

    await recordLatency({
      operationId: "settings.mark-project-complete",
      visibleLabel: `${projectName} 标记完成`,
      actionType: "click",
    }, async (mark) => {
      await activeProjects.getByLabel(`${projectName} 标记完成`).click();
      await mark("finalSettledLatencyMs", expect(completedProjects.getByText(projectName)).toBeVisible());
    });
    const saveRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/workbench/settings")
      && request.method() === "POST");
    let saveResponseStatus: number | undefined;
    await recordLatency({
      operationId: "settings.save-project-scope",
      visibleLabel: "保存设置",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = waitForSettingsSave(page);
      await page.getByRole("button", { name: "保存设置" }).click();
      saveResponseStatus = (await mark("apiLatencyMs", saveResponse)).status();
      await mark("finalSettledLatencyMs", expect(page.getByText("已保存关联台设置。")).toBeVisible());
    });
    const saveBody = JSON.parse((await saveRequest).postData() ?? "{}") as {
      completed_project_ids?: string[];
    };
    expect(saveBody.completed_project_ids).toEqual(["settings-cost-project-e2e"]);
    expect(saveResponseStatus).toBe(200);
    await expect(page.getByText("已保存关联台设置。")).toBeVisible();
    await expect(completedProjects.getByText(projectName)).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    let activePayload: Record<string, unknown> | undefined;
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-settings-project-scope-save",
      visibleLabel: "成本统计",
      actionType: "click",
    }, async (mark) => {
      const activeCostExplorerResponse = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return response.request().method() === "GET"
          && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
          && url.searchParams.get("project_scope") === "active"
          && response.status() === 200;
      });
      await page.getByRole("link", { name: "成本统计" }).click();
      const response = await mark("apiLatencyMs", activeCostExplorerResponse);
      activePayload = await response.json() as Record<string, unknown>;
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    if (!activePayload) {
      throw new Error("missing cost statistics active payload after settings project scope save");
    }
    expectDirectCanonicalPayload(activePayload);
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.switch-project-view-after-settings-project-scope-save",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "按项目" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    await expect(page.getByText(projectName)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    await expect(page.getByRole("button", { name: /项目范围：/ })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(api.count("POST /api/workbench/settings")).toBe(1);
    expect(browserErrors).toEqual([]);
  });
});
