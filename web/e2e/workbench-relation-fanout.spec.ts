import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relation browser flow", () => {
  test("confirms a relation in workbench and reflects it in bank details", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmPreviewDelayMs: 250,
    });
    const recordLatency = createOperationLatencyRecorder(page, testInfo, {
      route: "/",
      pageKey: "reconciliation-workbench",
      module: "reconciliation-workbench",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowBefore).toBeVisible();
    await expect(bankRowBefore.getByText("无oa")).toBeVisible();
    await expect(bankRowBefore.getByText("无发票")).toBeVisible();
    const bankTransactionRequestCountBefore = api.count("GET /api/bank-details/transactions");

    await confirmWorkbenchRelation(page, recordLatency, async () => {
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeVisible();
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeDisabled();
    });

    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await recordLatency({
      route: "/bank-details",
      pageKey: "bank-details",
      module: "bank-details",
      operationId: "bank-details.open-after-workbench-confirm",
      visibleLabel: "银行明细",
      actionType: "click",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return url.pathname === "/api/bank-details/transactions" && response.request().method() === "GET";
      });
      await page.getByRole("link", { name: "银行明细" }).click();
      await mark("apiLatencyMs", rowsResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("bank-details-page")).toBeVisible());
      await mark(
        "finalSettledLatencyMs",
        expect(page.getByRole("row", { name: /智能工厂设备商/ }).getByText("有发票")).toBeVisible(),
      );
    });
    const bankRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowAfter.getByText("有oa")).toBeVisible();
    await expect(bankRowAfter.getByText("有发票")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/bank-details/transactions")).toBeGreaterThan(bankTransactionRequestCountBefore);
  });
});
