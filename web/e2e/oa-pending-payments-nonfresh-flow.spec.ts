import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";

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

function createOaPendingLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    module: "oa-pending-payments",
  });
}

test.describe("OA pending payments read model freshness browser flow", () => {
  test("shows rows refreshing diagnostics instead of a true empty state", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentReadModelStatus: "refreshing",
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "oa-pending-payments.open-refreshing-rows",
      visibleLabel: "OA待付款核对",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("OA 待付款核对数据正在刷新")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeVisible());
    });

    await expect(page.getByText("OA 待付款核对数据正在刷新")).toBeVisible();
    await expect(page.getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("oa_pending_payment_source_version_missing")).toHaveCount(0);
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/oa-pending-payments/filter-options")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("shows detail unavailable state while the detail read model refreshes", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentDetailReadModelRefreshing: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "oa-pending-payments.open-detail-refreshing-page",
      visibleLabel: "OA待付款核对",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /浏览器付款申请人/ })).toBeVisible());
    });

    const row = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(row).toBeVisible();
    await recordLatency({
      operationId: "oa-pending-payments.open-unavailable-oa-detail",
      visibleLabel: "查看 OA 浏览器付款申请人 详情",
      actionType: "click",
    }, async (mark) => {
      const detailResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/oa/oa-payment-e2e-001/detail"),
      );
      await row.getByRole("button", { name: "查看 OA 浏览器付款申请人 详情" }).click();
      await mark("apiLatencyMs", detailResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "OA详情" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("详情暂不可用")).toBeVisible());
    });
    await expect(page.getByText("详情暂不可用")).toBeVisible();
    await expect(page.getByText("详情数据正在刷新，请稍后重试。")).toBeVisible();
    expect(api.count("GET /api/oa-pending-payments/oa/oa-payment-e2e-001/detail")).toBe(1);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
