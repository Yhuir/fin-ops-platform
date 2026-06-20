import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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

test.describe("OA pending payments read model freshness browser flow", () => {
  test("shows rows refreshing diagnostics instead of a true empty state", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentReadModelStatus: "refreshing",
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });

    await expect(page.getByText("OA 待付款核对数据正在刷新")).toBeVisible();
    await expect(page.getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("oa_pending_payment_source_version_missing")).toHaveCount(0);
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/oa-pending-payments/filter-options")).toBeGreaterThanOrEqual(1);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });

  test("shows detail unavailable state while the detail read model refreshes", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentDetailReadModelRefreshing: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/oa-pending-payments", "oa-pending-payments-page", { diagnostics });

    const row = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "查看 OA 浏览器付款申请人 详情" }).click();
    await expect(page.getByRole("heading", { name: "OA详情" })).toBeVisible();
    await expect(page.getByText("详情暂不可用")).toBeVisible();
    await expect(page.getByText("详情数据正在刷新，请稍后重试。")).toBeVisible();
    expect(api.count("GET /api/oa-pending-payments/oa/oa-payment-e2e-001/detail")).toBe(1);
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
