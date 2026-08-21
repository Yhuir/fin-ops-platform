import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function openConfirmRelationPreview(page: Page) {
  const openZone = page.getByTestId("zone-unpaired");
  const openGroup = page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();
  await openZone.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openZone.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openZone
    .getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })
    .getByRole("cell")
    .first()
    .click();
  await expect(openZone.getByText("已选 3")).toBeVisible();
  await openZone.getByRole("button", { name: "确认关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "确认关联" });
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("智能工厂设备商").first()).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-after").getByText("智能工厂设备商").first()).toBeVisible();
  return { openGroup, previewDialog };
}

test.describe("workbench direct error browser flow", () => {
  test("defers one OA canonical reread until a multi-row selection is cleared", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    await expect(openZone.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toBeVisible();
    await expect.poll(() => api.count("GET /api/oa-sync/status")).toBeGreaterThan(0);
    await openZone.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await openZone.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
    await expect(openZone.getByText("已选 2")).toBeVisible();

    const workbenchLoadsBeforeSync = api.count("GET /api/workbench");
    const oaStatusLoadsBeforeSync = api.count("GET /api/oa-sync/status");
    api.advanceOaSyncRevision();
    await expect.poll(
      () => api.count("GET /api/oa-sync/status"),
      { timeout: 5_000 },
    ).toBeGreaterThan(oaStatusLoadsBeforeSync);
    await page.waitForTimeout(250);

    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync);
    await expect(openZone.getByText("已选 2")).toBeVisible();

    await openZone.getByRole("button", { name: "清空选择" }).click();
    await expect.poll(() => api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync + 1);
    await expect(openZone.getByText("已选 0")).toBeVisible();
    await page.waitForTimeout(300);
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync + 1);
  });

  test("keeps a relation preview open across OA sync and rereads once all interactions close", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const { previewDialog } = await openConfirmRelationPreview(page);
    const workbenchLoadsBeforeSync = api.count("GET /api/workbench");
    const oaStatusLoadsBeforeSync = api.count("GET /api/oa-sync/status");
    api.advanceOaSyncRevision();
    await expect.poll(
      () => api.count("GET /api/oa-sync/status"),
      { timeout: 5_000 },
    ).toBeGreaterThan(oaStatusLoadsBeforeSync);
    await page.waitForTimeout(250);

    await expect(previewDialog).toBeVisible();
    await expect(openZone.getByText("已选 3")).toBeVisible();
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync);

    await previewDialog.getByRole("button", { name: "取消" }).click();
    await expect(previewDialog).toHaveCount(0);
    await expect(openZone.getByText("已选 3")).toBeVisible();
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync);

    await openZone.getByRole("button", { name: "清空选择" }).click();
    await expect.poll(() => api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync + 1);
    await expect(openZone.getByText("已选 0")).toBeVisible();
    await page.waitForTimeout(300);
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSync + 1);
  });

  test("blocks Workbench writes while OA sync is dirty", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      oaSyncMode: "dirty",
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
    await expect(openGroup).toBeVisible();
    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(0);
  });

  test("blocks Workbench writes while OA sync is refreshing", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      oaSyncMode: "refreshing",
    });

    await page.goto("/");

    await expect(page.getByRole("button", { name: /OA 正在同步/ })).toBeVisible();
    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
    await expect(openGroup).toBeVisible();
    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(0);
  });

  test("keeps rows in place and allows retry when the mutation itself fails", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmSubmitError: true,
    });

    await page.goto("/");

    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);
    const workbenchLoadsBeforeSubmit = api.count("GET /api/workbench");
    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog.getByRole("alert")).toContainText("关联台服务暂时不可用，请稍后重试。");
    await expect(previewDialog.getByRole("button", { name: "重试确认" })).toBeEnabled();
    await expect(openGroup).toBeVisible();
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSubmit);
  });

  test("does not retry a committed mutation when the single combined reread fails", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchCombinedRereadError: true,
    });

    await page.goto("/");

    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);
    const workbenchLoadsBeforeSubmit = api.count("GET /api/workbench");
    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog.getByRole("alert")).toContainText("关系已写入，页面重新读取失败");
    await expect(previewDialog.getByRole("alert")).toContainText("请勿重复提交");
    await expect(previewDialog.getByRole("button", { name: "关闭", exact: true })).toBeEnabled();
    await expect(previewDialog.getByRole("button", { name: /重试确认|确认关联/ })).toHaveCount(0);
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSubmit + 1);
    await page.waitForTimeout(300);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
  });
});
