import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

function createInputInvoiceUsageFanoutLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/input-invoice-usage",
    pageKey: "input-invoice-usage",
    module: "input-invoice-usage",
  });
}

test.describe("input invoice usage relation browser fan-out", () => {
  test("keeps an unpaired invoice selectable and refreshes formal downstream relations after workbench confirm", async ({ page }, testInfo) => {
    const browserErrors: string[] = [];
    page.on("pageerror", (error) => {
      browserErrors.push(`pageerror: ${error.stack || error.message}`);
    });
    page.on("console", (message) => {
      if (message.type() === "error") {
        browserErrors.push(`console.error: ${message.text()}`);
      }
    });
    page.on("requestfailed", (request) => {
      const failure = request.failure()?.errorText ?? "";
      if (failure !== "net::ERR_ABORTED") {
        browserErrors.push(`requestfailed: ${request.method()} ${request.url()} ${failure}`.trim());
      }
    });
    page.on("dialog", async (dialog) => {
      browserErrors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
      await dialog.dismiss().catch(() => undefined);
    });
    const api = await installDeterministicApiMocks(page, {
      costStatisticsRelationFanout: true,
      inputInvoiceUsageRelationFanout: true,
      oaPendingPaymentRelationFanout: true,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageFanoutLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-relation-fanout-before-confirm",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) =>
        response.url().includes("/api/input-invoice-usage/rows") && response.request().method() === "GET",
      );
      await page.goto("/input-invoice-usage");
      await mark("apiLatencyMs", rowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();

    const relationRowBefore = page.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(relationRowBefore).toBeVisible();
    await expect(relationRowBefore).toContainText("智能工厂设备商");
    await expect(relationRowBefore).toContainText("待处理");
    await expect(relationRowBefore).not.toContainText("关联台已确认");

    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await recordLatency({
      operationId: "input-invoice-usage.open-oa-reverse-before-confirm",
      visibleLabel: "以发票反提 OA",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = page.waitForResponse((response) =>
        response.url().includes("/api/input-invoice-usage/oa-reverse/preview")
          && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "以发票反提 OA" }).click();
      await mark("apiLatencyMs", previewResponse);
      await mark("finalSettledLatencyMs", expect(workflow).toBeVisible());
    });
    await expect(workflow).toBeVisible();
    const candidateInvoice = workflow.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(candidateInvoice).toBeVisible();
    await expect(candidateInvoice.getByText("未关联oa")).toBeVisible();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-REL-001")).toBeChecked();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).toBeChecked();
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);

    await recordLatency({
      operationId: "input-invoice-usage.close-oa-reverse-before-confirm",
      visibleLabel: "关闭以发票反提 OA 工作流",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
      await mark("finalSettledLatencyMs", expect(workflow).toBeHidden());
    });
    await expect(workflow).toBeHidden();

    const rowsRequestCountBeforeConfirm = api.count("GET /api/input-invoice-usage/rows");
    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "input-invoice-usage.reopen-after-workbench-confirm",
      visibleLabel: "进项发票使用情况",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "进项发票使用情况" }).click();
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThan(rowsRequestCountBeforeConfirm));
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThan(rowsRequestCountBeforeConfirm);

    const relationRowAfter = page.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(relationRowAfter).toBeVisible();
    await expect(relationRowAfter).toContainText("已支付");
    await expect(relationRowAfter).toContainText("陈涛");
    await expect(relationRowAfter).toContainText("设备尾款已闭环");
    await expect(relationRowAfter).toContainText("关联台已确认");
    await expectNoUnexpectedSuccessUiErrors(page);

    const refreshedWorkflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await recordLatency({
      operationId: "input-invoice-usage.open-oa-reverse-after-confirm",
      visibleLabel: "以发票反提 OA",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = page.waitForResponse((response) =>
        response.url().includes("/api/input-invoice-usage/oa-reverse/preview")
          && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "以发票反提 OA" }).click();
      await mark("apiLatencyMs", previewResponse);
      await mark("finalSettledLatencyMs", expect(refreshedWorkflow).toBeVisible());
    });
    await expect(refreshedWorkflow).toBeVisible();
    const linkedInvoice = refreshedWorkflow.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(linkedInvoice).toBeVisible();
    await expect(linkedInvoice.getByText("已关联oa")).toBeVisible();
    await expect(refreshedWorkflow.getByLabel("已关联 OA 发票 SD-INV-E2E-REL-001 不可选择")).toBeDisabled();
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);

    await recordLatency({
      operationId: "input-invoice-usage.close-oa-reverse-after-confirm",
      visibleLabel: "关闭以发票反提 OA 工作流",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
      await mark("finalSettledLatencyMs", expect(refreshedWorkflow).toBeHidden());
    });
    await expect(refreshedWorkflow).toBeHidden();

    const oaPendingRowsBefore = api.count("GET /api/oa-pending-payments/rows");
    await recordLatency({
      route: "/oa-pending-payments",
      pageKey: "oa-pending-payments",
      module: "oa-pending-payments",
      operationId: "oa-pending-payments.open-after-input-invoice-confirm",
      visibleLabel: "OA待付款核对",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "OA待付款核对" }).click();
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThan(oaPendingRowsBefore));
      await mark("finalSettledLatencyMs", expect(page.getByTestId("oa-pending-payments-page")).toBeVisible());
    });
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThan(oaPendingRowsBefore);
    const oaPendingRow = page.getByRole("row", { name: /陈涛/ });
    await expect(oaPendingRow).toBeVisible();
    await expect(oaPendingRow.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("已支付");
    await expect(oaPendingRow.getByText("候选")).toHaveCount(0);
    await expect(oaPendingRow).toContainText("关联台已确认");
    await expect(oaPendingRow).toContainText("智能工厂设备商");
    await expect(oaPendingRow).toContainText("12561048");
    await expectNoUnexpectedSuccessUiErrors(page);

    const costExplorerRowsBefore = api.count("GET /api/cost-statistics/explorer");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-input-invoice-confirm",
      visibleLabel: "成本统计",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "成本统计" }).click();
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRowsBefore));
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRowsBefore);
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.switch-project-view-after-input-invoice-confirm",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按项目" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("option", { name: /智能工厂项目/ })).toBeVisible());
    });
    const linkedProject = page.getByRole("option", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58000.00");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.expand-linked-project-after-input-invoice-confirm",
      visibleLabel: "智能工厂项目",
      actionType: "click",
    }, async (mark) => {
      await linkedProject.click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("option", { name: /设备货款及材料费/ })).toBeVisible());
    });
    const linkedExpenseType = page.getByRole("option", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58000.00");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.expand-linked-expense-type-after-input-invoice-confirm",
      visibleLabel: "设备货款及材料费",
      actionType: "click",
    }, async (mark) => {
      await linkedExpenseType.click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "项目成本明细表" })).toContainText("智能工厂设备尾款"));
    });
    const projectRows = page.getByRole("grid", { name: "项目成本明细表" });
    await expect(projectRows).toContainText("智能工厂设备尾款");
    await expect(projectRows).toContainText("浏览器成本申请人");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
  });
});
