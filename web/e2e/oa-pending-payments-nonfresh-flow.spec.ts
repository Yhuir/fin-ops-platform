import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";

const ROWS_PATH = "GET /api/oa-pending-payments/rows";

function createOaPendingLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    module: "oa-pending-payments",
  });
}

function waitForRows(page: Page) {
  return page.waitForResponse((response) =>
    response.request().method() === "GET"
    && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/rows"),
  );
}

test.describe("OA pending payments canonical page states", () => {
  test("uses one stable response without legacy runtime metadata or polling", async ({ page }, testInfo) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);
    const rowsResponse = waitForRows(page);

    await recordLatency({
      operationId: "oa-pending-payments.open-canonical-rows",
      visibleLabel: "OA待付款核对",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });
      await mark("apiLatencyMs", rowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /浏览器付款申请人/ })).toBeVisible());
    });

    const response = await rowsResponse;
    const payload = await response.json() as Record<string, unknown>;
    expect(response.status()).toBe(200);
    expect(payload).not.toHaveProperty("readModelStatus");
    expect(payload).not.toHaveProperty("read_model_status");
    expect(payload).not.toHaveProperty("sourceVersions");
    expect(payload).not.toHaveProperty("source_versions");
    const settledRowsCount = api.count(ROWS_PATH);
    await page.waitForTimeout(650);
    expect(api.count(ROWS_PATH)).toBe(settledRowsCount);
    expect(api.count("GET /api/oa-pending-payments/filter-options")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    diagnostics.dispose();
  });

  test("keeps a canonical load error visible until manual refresh recovers", async ({ page }, testInfo) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });
    await expect(page.getByText("OA 待付款核对加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("OA 待付款核对加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    const failedRowsCount = api.count(ROWS_PATH);
    await page.waitForTimeout(650);
    expect(api.count(ROWS_PATH)).toBe(failedRowsCount);

    await recordLatency({
      operationId: "oa-pending-payments.manual-refresh-after-canonical-error",
      visibleLabel: "刷新 OA 待付款核对",
      actionType: "click",
    }, async (mark) => {
      const successfulRowsResponse = page.waitForResponse((response) => (
        response.status() === 200
        && response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/rows")
      ));
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const rowsResponse = waitForRows(page);
        await page.getByRole("button", { name: "刷新 OA 待付款核对" }).click();
        if ((await rowsResponse).status() === 200) break;
      }
      const response = await mark("apiLatencyMs", successfulRowsResponse);
      expect(response.status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /浏览器付款申请人/ })).toBeVisible());
    });

    expect(api.count(ROWS_PATH)).toBeGreaterThan(failedRowsCount);
    expect(api.count(ROWS_PATH)).toBeLessThanOrEqual(failedRowsCount + 2);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    diagnostics.dispose();
  });
});
