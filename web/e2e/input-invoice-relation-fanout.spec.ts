import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("input invoice usage relation browser fan-out", () => {
  test("keeps candidate OA evidence non-selectable and refreshes downstream read models after workbench confirm", async ({ page }) => {
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
      sessionMode: "full_access",
      taxOffsetRelationFanout: true,
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();

    const relationRowBefore = page.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(relationRowBefore).toBeVisible();
    await expect(relationRowBefore).toContainText("智能工厂设备商");
    await expect(relationRowBefore).toContainText("陈涛");
    await expect(relationRowBefore).toContainText("待处理");
    await expect(relationRowBefore).toContainText("设备尾款候选关系");

    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(workflow).toBeVisible();
    const candidateInvoice = workflow.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(candidateInvoice).toBeVisible();
    await expect(candidateInvoice.getByText("候选oa")).toBeVisible();
    await expect(workflow.getByLabel("候选 OA 发票 SD-INV-E2E-REL-001 不可选择")).toBeDisabled();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).toBeChecked();
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);

    await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
    await expect(workflow).toBeHidden();

    const rowsRequestCountBeforeConfirm = api.count("GET /api/input-invoice-usage/rows");
    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "进项发票使用情况" }).click();
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThan(rowsRequestCountBeforeConfirm);

    const relationRowAfter = page.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(relationRowAfter).toBeVisible();
    await expect(relationRowAfter).toContainText("已支付");
    await expect(relationRowAfter).toContainText("陈涛");
    await expect(relationRowAfter).toContainText("设备尾款已闭环");
    await expect(relationRowAfter).toContainText("关联台已确认");
    await expectNoUnexpectedSuccessUiErrors(page);

    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const refreshedWorkflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(refreshedWorkflow).toBeVisible();
    const linkedInvoice = refreshedWorkflow.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(linkedInvoice).toBeVisible();
    await expect(linkedInvoice.getByText("已关联oa")).toBeVisible();
    await expect(refreshedWorkflow.getByLabel("已关联 OA 发票 SD-INV-E2E-REL-001 不可选择")).toBeDisabled();
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);

    await page.getByRole("button", { name: "关闭以发票反提 OA 工作流" }).click();
    await expect(refreshedWorkflow).toBeHidden();

    const oaPendingRowsBefore = api.count("GET /api/oa-pending-payments/rows");
    await page.getByRole("link", { name: "OA待付款核对" }).click();
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

    const taxOffsetRowsBefore = api.count("GET /api/tax-offset");
    await page.getByRole("link", { name: "税金抵扣" }).click();
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    expect(api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetRowsBefore);
    const taxInputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(taxInputPlanGrid).toBeVisible();
    await expect(taxInputPlanGrid.getByText("智能工厂设备商")).toBeVisible();
    await expect(taxInputPlanGrid.getByRole("row", { name: /91330108MA27B4011D/ })).toContainText("7,540.00");
    await expect(page.getByText("税金抵扣数据加载失败，请稍后重试。")).toHaveCount(0);
    await expect(page.getByText(/读模型.*刷新|读模型.*失败|read model/i)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    const costExplorerRowsBefore = api.count("GET /api/cost-statistics/explorer");
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRowsBefore);
    await page.getByRole("button", { name: "按项目" }).click();
    const linkedProject = page.getByRole("button", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58,000.00");
    await linkedProject.click();
    const linkedExpenseType = page.getByRole("button", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58,000.00");
    await linkedExpenseType.click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("智能工厂设备尾款");
    await expect(projectRows).toContainText("智能工厂设备商");
    await expectNoUnexpectedSuccessUiErrors(page);

    expect(browserErrors).toEqual([]);
  });
});
