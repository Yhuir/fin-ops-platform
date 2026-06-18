import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("input invoice usage relation browser fan-out", () => {
  test("keeps candidate OA evidence non-selectable and reflects linked evidence after workbench confirm", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRelationFanout: true,
      sessionMode: "full_access",
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

    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const refreshedWorkflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(refreshedWorkflow).toBeVisible();
    const linkedInvoice = refreshedWorkflow.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(linkedInvoice).toBeVisible();
    await expect(linkedInvoice.getByText("已关联oa")).toBeVisible();
    await expect(refreshedWorkflow.getByLabel("已关联 OA 发票 SD-INV-E2E-REL-001 不可选择")).toBeDisabled();
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);
  });
});
