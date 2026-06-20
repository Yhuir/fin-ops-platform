import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const workbenchRowIds = [
  "oa-o-202603-001",
  "bk-o-202603-001",
  "iv-o-202603-001",
];

test.describe("workbench automatic candidate split browser flow", () => {
  test("splits an open automatic candidate through preview, freshness barrier, and fresh refetch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const openZone = page.getByTestId("zone-open");
    const pairedZone = page.getByTestId("zone-paired");
    const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
    await expect(openZone).toBeVisible();
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);

    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await expect(openZone.getByText("带入 2")).toBeVisible();

    await openZone.getByRole("button", { name: "撤回关联" }).click();
    const previewDialog = page.getByRole("dialog", { name: "关联预览" });
    await expect(previewDialog).toBeVisible();
    await expect(previewDialog.getByText("拆分候选预览")).toBeVisible();
    await expect(previewDialog.getByText("该组是自动候选，确认后会拆分并隐藏这条候选。")).toBeVisible();
    await expect(previewDialog.getByTestId("relation-preview-before").getByText("待找流水与发票").first()).toBeVisible();
    await expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联")).toHaveCount(0);
    await expect(previewDialog.getByRole("button", { name: "确认拆分" })).toBeEnabled();

    const previewBody = api.lastBody("POST /api/workbench/actions/withdraw-link/preview");
    expect(previewBody).toMatchObject({ month: "all" });
    expect(previewBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(previewBody.row_ids).toHaveLength(workbenchRowIds.length);

    const barrierCallsBeforeSplit = api.count("POST /api/operation-barrier/status");
    const workbenchGroupCallsBeforeSplit = api.count("GET /api/workbench/groups");
    await previewDialog.getByRole("textbox", { name: "备注" }).fill("浏览器拆分候选主链路回归");
    await previewDialog.getByRole("button", { name: "确认拆分" }).click();

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(previewDialog.getByText("正在确认拆分...")).toBeVisible();
    await expect(previewDialog.getByRole("button", { name: "确认拆分" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "关闭关联预览" })).toBeDisabled();
    await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(openGroup).toBeVisible();

    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    await expect(openZone.getByText("已选 0")).toBeVisible();
    await expect(pairedZone.getByText("已选 0")).toBeVisible();

    const submitBody = api.lastBody("POST /api/workbench/actions/withdraw-link");
    expect(submitBody).toMatchObject({
      month: "all",
      note: "浏览器拆分候选主链路回归",
      operation_type: "split_candidate",
      preview_id: "split_candidate:CASE-202603-101",
      expected_versions: { "decision:CASE-202603-101": 1 },
    });
    expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeSplit);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(workbenchGroupCallsBeforeSplit);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
