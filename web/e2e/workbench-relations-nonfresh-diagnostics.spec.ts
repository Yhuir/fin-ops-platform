import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
}

test.describe("workbench relation non-fresh diagnostics", () => {
  test("keeps pending invoice rows inspectable while relation-backed data is refreshing", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, {
      pendingInvoiceReadModelStatus: "refreshing",
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-relation-refreshing",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("数据刷新中")).toBeVisible());
    });
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("已支付待开票")).toBeVisible();
    await recordLatency({
      operationId: "pending-invoices.select-row-while-relation-refreshing",
      visibleLabel: "选择流水 智能工厂设备商",
      actionType: "check",
    }, async (mark) => {
      await row.getByRole("checkbox", { name: "选择流水 智能工厂设备商" }).check();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "选择发票" })).toBeEnabled());
    });
    await expect(page.getByRole("button", { name: "选择发票" })).toBeEnabled();
  });

  test("surfaces stale diagnostics instead of silently treating empty relation-backed rows as true empty", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, {
      pendingInvoiceReadModelStatus: "stale",
      pendingInvoiceRowsEmpty: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-relation-stale-empty",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("读模型 stale，写入和导出已暂停")).toBeVisible());
    });
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    await expect(page.getByText("当前条件下没有待找发票流水。")).toBeVisible();
  });
});
