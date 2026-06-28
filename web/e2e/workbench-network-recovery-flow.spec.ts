import { expect, type Locator, type Page, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

const workbenchRowIds = [
  "oa-o-202603-001",
  "bk-o-202603-001",
  "iv-o-202603-001",
];

async function clickTwiceAtCenter(page: Page, locator: Locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) {
    throw new Error("Target button is not visible for double-submit guard test.");
  }
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.click(x, y);
  await page.mouse.click(x, y);
}

async function selectAllOpenRows(page: Page) {
  const openZone = page.getByTestId("zone-open");
  const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();

  await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(openZone.getByText("已选 3")).toBeVisible();

  return { openZone, openGroup };
}

async function openConfirmRelationPreview(page: Page) {
  const { openZone, openGroup } = await selectAllOpenRows(page);
  await openZone.getByRole("button", { name: "确认关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await expect(previewDialog).toBeVisible();
  await expect(previewDialog.getByText("确认关联预览")).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("智能工厂设备商").first()).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联").first()).toBeVisible();
  return { openZone, openGroup, previewDialog };
}

async function openSplitCandidatePreview(page: Page) {
  const openZone = page.getByTestId("zone-open");
  const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();

  await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await expect(openZone.getByText("已选 1")).toBeVisible();
  await expect(openZone.getByText("带入 2")).toBeVisible();

  await openZone.getByRole("button", { name: "撤回关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await expect(previewDialog).toBeVisible();
  await expect(previewDialog.getByText("拆分候选预览")).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("待找流水与发票").first()).toBeVisible();
  return { openZone, openGroup, previewDialog };
}

async function openWithdrawRelationPreview(page: Page) {
  const pairedZone = page.getByTestId("zone-paired");
  const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
  await expect(pairedZone).toBeVisible();
  await expect(pairedGroup).toBeVisible();

  await pairedGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await pairedGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(pairedZone.getByText("已选 3")).toBeVisible();

  await pairedZone.getByRole("button", { name: "撤回关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await expect(previewDialog).toBeVisible();
  await expect(previewDialog.getByText("撤回关联预览")).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("完全关联").first()).toBeVisible();
  return { pairedGroup, pairedZone, previewDialog };
}

test.describe("workbench network recovery and duplicate submit browser flow", () => {
  test("recovers from a transient confirm-link network failure through the same preview", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmSubmitFailuresBeforeSuccess: 1,
    });

    await page.goto("/");
    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);

    await previewDialog.getByRole("button", { name: "确认关联" }).click();
    await expect(previewDialog.getByRole("alert")).toContainText("网络暂时失败，请重试。");
    await expect(previewDialog.getByRole("button", { name: "重试" })).toBeEnabled();
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    const workbenchGroupCallsBeforeRetry = api.count("GET /api/workbench/groups");
    await previewDialog.getByRole("button", { name: "重试" }).click();

    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toBeVisible();
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(2);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(workbenchGroupCallsBeforeRetry);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("does not retry a stale confirm-link preview after a 409 conflict", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmSubmitConflict: true,
    });

    await page.goto("/");
    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);

    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog.getByRole("alert")).toContainText("关联预览已失效，请重新预览。");
    await expect(previewDialog.getByRole("button", { name: "重试" })).toHaveCount(0);
    await expect(previewDialog.getByRole("button", { name: "确认关联" })).toHaveCount(0);
    await expect(previewDialog.getByRole("button", { name: "取消" })).toHaveCount(0);
    await expect(previewDialog.getByRole("button", { name: "关闭", exact: true })).toBeEnabled();
    await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
  });

  test("prevents duplicate confirm-link submissions while the preview is submitting", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmSubmitDelayMs: 500,
    });

    await page.goto("/");
    const { previewDialog } = await openConfirmRelationPreview(page);
    const submitButton = previewDialog.getByRole("button", { name: "确认关联" });

    await clickTwiceAtCenter(page, submitButton);

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(submitButton).toBeDisabled();
    await expect(previewDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toBeVisible();
    const submitBody = api.lastBody("POST /api/workbench/actions/confirm-link");
    expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("prevents duplicate split-candidate submissions while the preview is submitting", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchWithdrawSubmitDelayMs: 500,
    });

    await page.goto("/");
    const { openGroup, previewDialog } = await openSplitCandidatePreview(page);
    const submitButton = previewDialog.getByRole("button", { name: "确认拆分" });

    await clickTwiceAtCenter(page, submitButton);

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(submitButton).toBeDisabled();
    await expect(openGroup).toBeVisible();
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    const submitBody = api.lastBody("POST /api/workbench/actions/withdraw-link");
    expect(submitBody).toMatchObject({
      operation_type: "split_candidate",
      preview_id: "split_candidate:CASE-202603-101",
    });
    expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("prevents duplicate withdraw-link submissions while the preview is submitting", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchWithdrawSubmitDelayMs: 500,
    });

    await page.goto("/");
    await confirmWorkbenchRelation(page);
    const { pairedGroup, previewDialog } = await openWithdrawRelationPreview(page);
    const submitButton = previewDialog.getByRole("button", { name: "确认撤回" });

    await clickTwiceAtCenter(page, submitButton);

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(submitButton).toBeDisabled();
    await expect(pairedGroup).toBeVisible();
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    const submitBody = api.lastBody("POST /api/workbench/actions/withdraw-link");
    expect(submitBody).toMatchObject({
      operation_type: "withdraw_relation",
      preview_id: "withdraw_relation:CASE-202603-101",
    });
    expect(submitBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(submitBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/withdraw-link")).toBe(1);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
