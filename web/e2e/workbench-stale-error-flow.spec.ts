import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function openConfirmRelationPreview(page: Page) {
  const openZone = page.getByTestId("zone-unpaired");
  const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();
  await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(openZone.getByText("已选 3")).toBeVisible();
  await openZone.getByRole("button", { name: "确认关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await expect(previewDialog.getByText("确认关联预览")).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("智能工厂设备商").first()).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联").first()).toBeVisible();
  return { openGroup, previewDialog };
}

test.describe("workbench stale and error browser flow", () => {
  test("shows workbench stale status without globally disabling selected group actions", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchHealthStatus: "stale",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /关联台待刷新/ })).toBeVisible();
    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();

    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeEnabled();
    await expect(openZone.getByRole("button", { name: "异常处理" })).toBeEnabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeEnabled();
  });

  test("shows workbench refreshing status without globally disabling selected group actions", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchHealthStatus: "rebuilding",
      workbenchPageStatus: "refreshing",
      workbenchRefreshStatus: "refreshing",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /关联台刷新中/ })).toBeVisible();
    await expect(page.getByText("当前没有可展示的 OA / 银行流水 / 发票记录。")).toHaveCount(0);

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();
    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();

    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeEnabled();
    await expect(openZone.getByRole("button", { name: "异常处理" })).toBeEnabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeEnabled();
  });

  test("does not present stale empty payload as a true empty workbench", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchHealthStatus: "stale",
      workbenchPageEmpty: true,
      workbenchPageStatus: "stale",
      workbenchRefreshStatus: "stale",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /关联台待刷新/ })).toBeVisible();
    await expect(page.getByText("当前没有可展示的 OA / 银行流水 / 发票记录。")).toHaveCount(0);
    await expect(page.getByTestId("zone-unpaired").getByText("未配对 0 项").first()).toBeVisible();
    await expect(page.getByTestId("zone-paired").getByText("已配对 0 项").first()).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-case:CASE-202603-101")).toHaveCount(0);
  });

  test("blocks Workbench writes while OA sync is dirty", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      oaSyncMode: "dirty",
      workbenchHealthStatus: "ready",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /关联台待刷新/ })).toBeVisible();
    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();

    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(0);
  });

  test("blocks Workbench writes while OA sync is refreshing", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      oaSyncMode: "refreshing",
      workbenchHealthStatus: "ready",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /OA 正在同步/ })).toBeVisible();
    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();

    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(openZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(0);
    expect(api.count("POST /api/workbench/actions/withdraw-link/preview")).toBe(0);
  });

  test("surfaces refresh failure while keeping the current active generation inspectable", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchHealthStatus: "error",
      workbenchRefreshStatus: "failed",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: /关联台刷新失败/ })).toBeVisible();
    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();

    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await expect(openZone.getByRole("button", { name: "确认关联" })).toBeEnabled();
  });

  test("keeps rows in place when confirm submit fails in the preview dialog", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmSubmitError: true,
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();
    await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();

    await openZone.getByRole("button", { name: "确认关联" }).click();
    const previewDialog = page.getByRole("dialog", { name: "关联预览" });
    await expect(previewDialog.getByText("确认关联预览")).toBeVisible();
    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog.getByRole("alert")).toContainText("browser confirm failed");
    await expect(previewDialog.getByRole("button", { name: "重试" })).toBeEnabled();
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
  });

  test("keeps committed preview error when the freshness barrier times out", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-06-18T00:00:00Z") });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      operationBarrierMode: "refreshing",
    });

    await page.goto("/");

    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);
    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog).toHaveAttribute("aria-busy", "true");
    await expect(previewDialog.getByText("关系已写入，正在同步关联台最新数据...")).toBeVisible();
    await page.clock.runFor(21_000);

    await expect(previewDialog.getByRole("alert")).toContainText("关系已写入，关联台刷新未完成");
    await expect(previewDialog.getByRole("alert")).toContainText("操作同步等待超时");
    await expect(previewDialog.getByRole("button", { name: "重试" })).toHaveCount(0);
    await expect(previewDialog.getByRole("button", { name: "关闭", exact: true })).toBeEnabled();
    await expect(previewDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(openGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(1);
  });

  test("keeps projected relation committed when the background fresh refetch fails", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchFreshRefetchError: true,
    });

    await page.goto("/");

    const { openGroup, previewDialog } = await openConfirmRelationPreview(page);
    const groupCallsBeforeSubmit = api.count("GET /api/workbench/groups");
    await previewDialog.getByRole("button", { name: "确认关联" }).click();

    await expect(previewDialog).toHaveCount(0);
    await expect(openGroup).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toBeVisible();
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(groupCallsBeforeSubmit);
  });
});
