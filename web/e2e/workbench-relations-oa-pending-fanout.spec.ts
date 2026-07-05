import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relations OA pending payment browser fan-out", () => {
  test("refreshes OA pending payment rows after a workbench relation is confirmed", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentRelationFanout: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOperationLatencyRecorder(page, testInfo, {
      route: "/oa-pending-payments",
      pageKey: "oa-pending-payments",
      module: "oa-pending-payments",
    });

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    const rowBefore = page.getByRole("row", { name: /陈涛/ });
    await expect(rowBefore).toBeVisible();
    await expect(rowBefore.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("支付少了");
    expect(await rowBefore.getByText("候选").count()).toBeGreaterThan(0);
    await expect(rowBefore).toContainText("智能工厂设备商");
    await expect(rowBefore).toContainText("12561048");
    const rowsBefore = api.count("GET /api/oa-pending-payments/rows");

    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "oa-pending-payments.open-after-workbench-confirm",
      visibleLabel: "OA待付款核对",
      actionType: "click",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/rows"),
      );
      await page.getByRole("link", { name: "OA待付款核对" }).click();
      await mark("apiLatencyMs", rowsResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("oa-pending-payments-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /陈涛/ })).toContainText("已支付"));
    });
    const rowAfter = page.getByRole("row", { name: /陈涛/ });
    await expect(rowAfter.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("已支付");
    await expect(rowAfter.getByText("候选")).toHaveCount(0);
    await expect(rowAfter).toContainText("关联台已确认");
    await expect(rowAfter).toContainText("智能工厂设备商");
    await expect(rowAfter).toContainText("12561048");
    await expect(rowAfter).toContainText("58000.00");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThan(rowsBefore);
  });
});
