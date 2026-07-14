import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
}

test.describe("pending invoices browser flow", () => {
  test("allows selecting text in the pending invoice table body", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-text-selection",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const counterpartyName = page.locator(".pending-invoices-counterparty-name").filter({ hasText: "智能工厂设备商" }).first();
    await expect(counterpartyName).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.select-counterparty-text",
      visibleLabel: "智能工厂设备商",
      actionType: "select",
    }, async (mark) => {
      await counterpartyName.selectText();
      await mark("finalSettledLatencyMs", expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).toContain("智能工厂设备"));
    });

    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).toContain("智能工厂设备");
  });

  test("reflects workbench confirmed invoice relation in pending invoices", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-fanout",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const pendingRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowBefore).toBeVisible();
    await expect(pendingRowBefore.getByText("已支付待开票")).toBeVisible();
    await expect(pendingRowBefore.getByText("12561048")).toHaveCount(0);
    const pendingRowsBefore = api.count("GET /api/pending-invoices/rows");

    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "pending-invoices.return-after-fanout-confirm",
      visibleLabel: "待找发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "待找发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore));
    });
    const pendingRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowAfter.getByText("已支付已开票")).toBeVisible();
    await expect(pendingRowAfter.getByText("12561048")).toBeVisible();
    await expect(pendingRowAfter.getByText("陈涛")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore);
  });
});
