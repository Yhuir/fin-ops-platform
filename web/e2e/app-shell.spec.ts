import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function startStrictBrowserErrorCapture(page: Page, options: { allowExpectedAuthResourceError?: boolean } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      if (
        options.allowExpectedAuthResourceError
        && message.text().includes("Failed to load resource: the server responded with a status of 401 (Unauthorized)")
      ) {
        return;
      }
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

function waitForAppHealthDashboard(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/operations/app-health-dashboard")
      && response.status() === 200);
}

function createAppHealthLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/operations/app-health",
    pageKey: "app-health-operations",
    module: "app-health-operations",
  });
}

test.describe("app shell browser smoke", () => {
  test("renders authenticated admin shell, navigation, and AppHealth dashboard", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
    const recordLatency = createAppHealthLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "app-health.open-admin-dashboard",
      visibleLabel: "系统状态",
      actionType: "navigate",
    }, async (mark) => {
      const dashboardResponse = waitForAppHealthDashboard(page);
      await page.goto("/operations/app-health");
      await mark("apiLatencyMs", dashboardResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByTestId("app-health-requests")).toBeVisible());
    });

    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "银行明细" })).toBeVisible();
    await expect(page.getByRole("link", { name: "系统状态" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toBeVisible();
    await expect(page.getByRole("button", { name: "刷新" })).toBeVisible();
    expect(api.count("GET /api/session/me")).toBeGreaterThan(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);

    const dashboardCountBeforeRefresh = api.count("GET /api/operations/app-health-dashboard");
    await recordLatency({
      operationId: "app-health.refresh-dashboard",
      visibleLabel: "刷新",
      actionType: "click",
    }, async (mark) => {
      const dashboardResponse = waitForAppHealthDashboard(page);
      await page.getByRole("button", { name: "刷新" }).click();
      await mark("apiLatencyMs", dashboardResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("app-health-runtime")).toBeVisible());
    });
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(dashboardCountBeforeRefresh);

    const auditPanel = page.getByTestId("app-health-system-audit");
    await auditPanel.getByLabel("Audit 全系统 App 内部合同").click();
    await expect(auditPanel).toContainText("pass");
    await expect(auditPanel).toContainText("Blocking samples");
    await expect(auditPanel).toContainText("外部证据 unknown");
    await expect(auditPanel).not.toContainText("Blocking issues");
    expect(api.count("GET /api/operations/app-health/page-audit")).toBe(1);
    expect(api.count("POST /api/operations/app-health/page-audit")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page, { allowText: /Read model/gi });
    expect(browserErrors).toEqual([]);
  });

  test("keeps AppHealth dashboard admin-only for read-export users", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });
    const recordLatency = createAppHealthLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "app-health.open-read-export-admin-gate",
      visibleLabel: "系统状态",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/operations/app-health");
      await mark("finalSettledLatencyMs", expect(page.getByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。")).toBeVisible());
    });

    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("shows session-denied state without rendering the protected dashboard", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "forbidden" });
    const recordLatency = createAppHealthLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "app-shell.open-forbidden-session-gate",
      visibleLabel: "系统状态",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/operations/app-health");
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByText("当前 OA 账号未开通访问权限，请联系管理员处理。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("shows expired session state and does not call protected page APIs", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, { allowExpectedAuthResourceError: true });
    const api = await installDeterministicApiMocks(page, { sessionMode: "expired" });
    const recordLatency = createAppHealthLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "app-shell.open-expired-session-gate",
      visibleLabel: "系统状态",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/operations/app-health");
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "OA 会话已失效" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "OA 会话已失效" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });
});
