import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

const workbenchRowIds = [
  "oa-o-202603-001",
  "bk-o-202603-001",
  "iv-o-202603-001",
];

test.describe("workbench withdraw browser flow", () => {
  test("withdraws a paired relation after preview lock and current-page refetch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      costStatisticsRelationFanout: true,
      inputInvoiceUsageRelationFanout: true,
      oaPendingPaymentRelationFanout: true,
      sessionMode: "full_access",
      workbenchWithdrawPreviewDelayMs: 250,
      workbenchWithdrawSubmitDelayMs: 1_000,
    });

    await page.goto("/");
    await confirmWorkbenchRelation(page);

    const pairedZone = page.getByTestId("zone-paired");
    const openZone = page.getByTestId("zone-unpaired");
    const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
    await expect(pairedGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toHaveCount(0);

    await pairedGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
    await expect(pairedZone.getByText("已选 3")).toBeVisible();

    await pairedZone.getByRole("button", { name: "撤回关联" }).click();
    await expect(pairedZone.getByRole("button", { name: "正在准备撤回预览" })).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "正在准备撤回预览" })).toBeDisabled();
    const previewDialog = page.getByRole("dialog", { name: "关联预览" });
    await expect(previewDialog).toBeVisible();
    await expect(previewDialog.getByText("撤回关联预览")).toBeVisible();
    await expect(previewDialog.getByText("所选记录已确认关联，可在此撤回这组配对关系。")).toBeVisible();
    await expect(previewDialog.getByTestId("relation-preview-before").getByText("完全关联").first()).toBeVisible();
    await expect(previewDialog.getByTestId("relation-preview-after").getByText("待找流水与发票").first()).toBeVisible();

    const previewBody = api.lastBody("POST /api/workbench/actions/withdraw-link/preview");
    expect(previewBody).toMatchObject({ month: "all" });
    expect(previewBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(previewBody.row_ids).toHaveLength(workbenchRowIds.length);

    const workbenchLoadsBeforeWithdraw = api.count("GET /api/workbench");
    await previewDialog.getByRole("textbox", { name: "备注" }).fill("浏览器撤回主链路回归");
    await previewDialog.getByRole("button", { name: "确认撤回" }).click();

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(previewDialog.getByText("正在撤回关联...")).toBeVisible();
    await expect(previewDialog.getByRole("button", { name: "确认撤回" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
    await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(pairedGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toHaveCount(0);

    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:bk-o-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    await expect(openZone.getByText("已选 0")).toBeVisible();

    const submitBody = api.lastBody("POST /api/workbench/actions/withdraw-link");
    expect(submitBody).toMatchObject({
      month: "all",
      note: "浏览器撤回主链路回归",
      operation_type: "withdraw_relation",
      preview_id: "withdraw_relation:CASE-202603-101",
      expected_versions: { "CASE-202603-101": 1 },
    });
    expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(workbenchLoadsBeforeWithdraw);

    await page.getByRole("link", { name: "银行明细" }).click();
    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow.getByText("无oa")).toBeVisible();
    await expect(bankRow.getByText("无发票")).toBeVisible();

    await page.getByRole("link", { name: "待找发票" }).click();
    const pendingRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRow.getByText("已支付待开票")).toBeVisible();
    await expect(pendingRow.getByText("12561048")).toHaveCount(0);

    await page.getByRole("link", { name: "进项发票使用情况" }).click();
    const invoiceRow = page.getByRole("row", { name: /SD-INV-E2E-REL-001/ });
    await expect(invoiceRow).toContainText("待处理");
    await expect(invoiceRow).not.toContainText("关联台已确认");

    await page.getByRole("link", { name: "OA待付款核对" }).click();
    const oaRow = page.getByRole("row", { name: /陈涛/ });
    await expect(oaRow.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("未支付");
    await expect(oaRow.getByText("候选")).toHaveCount(0);

    await page.getByRole("link", { name: "成本统计" }).click();
    await page.getByRole("button", { name: "按项目" }).click();
    await expect(page.getByRole("button", { name: /智能工厂项目/ })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("restores withdraw preview controls after a safe error", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchInitialRelationConfirmed: true,
      workbenchWithdrawPreviewDelayMs: 250,
      workbenchWithdrawPreviewError: true,
    });

    await page.goto("/");
    const pairedZone = page.getByTestId("zone-paired");
    const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
    await pairedGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
    await pairedZone.getByRole("button", { name: "撤回关联" }).click();

    await expect(pairedZone.getByRole("button", { name: "正在准备撤回预览" })).toBeDisabled();
    const errorDialog = page.getByRole("dialog", { name: "操作状态弹窗" });
    await expect(errorDialog).toBeVisible();
    await expect(errorDialog).toContainText("操作失败");
    await expect(errorDialog).toContainText("关联台服务暂时不可用，请稍后重试。 · requestId req-withdraw-preview");
    await expect(errorDialog).not.toContainText("INTERNAL WITHDRAW PREVIEW SENTINEL");
    await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeEnabled();
  });
});
