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
  test("withdraws a paired relation only after preview lock, freshness barrier, and fresh refetch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");
    await confirmWorkbenchRelation(page);

    const pairedZone = page.getByTestId("zone-paired");
    const openZone = page.getByTestId("zone-open");
    const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
    await expect(pairedGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);

    await pairedGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
    await pairedGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
    await expect(pairedZone.getByText("已选 3")).toBeVisible();

    await pairedZone.getByRole("button", { name: "撤回关联" }).click();
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

    const barrierCallsBeforeWithdraw = api.count("POST /api/operation-barrier/status");
    const workbenchGroupCallsBeforeWithdraw = api.count("GET /api/workbench/groups");
    await previewDialog.getByRole("textbox", { name: "备注" }).fill("浏览器撤回主链路回归");
    await previewDialog.getByRole("button", { name: "确认撤回" }).click();

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(previewDialog.getByText("正在撤回关联...")).toBeVisible();
    await expect(previewDialog.getByRole("button", { name: "确认撤回" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
    await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(pairedGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);

    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    const restoredOpenGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
    await expect(restoredOpenGroup).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeVisible();
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
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeWithdraw);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(workbenchGroupCallsBeforeWithdraw);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
