import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const workbenchMutationEndpoints = [
  "POST /api/workbench/actions/confirm-link/preview",
  "POST /api/workbench/actions/confirm-link",
  "POST /api/workbench/actions/withdraw-link/preview",
  "POST /api/workbench/actions/withdraw-link",
  "POST /api/workbench/exception/preview",
  "POST /api/workbench/exception/apply",
  "POST /api/workbench/actions/cancel-exception",
  "POST /api/workbench/actions/ignore-row",
  "POST /api/workbench/actions/unignore-row",
  "POST /api/operation-barrier/status",
];

async function selectWorkbenchGroupRows(page: Page, zone: "unpaired" | "paired") {
  const zoneLocator = page.getByTestId(`zone-${zone}`);
  const group = page.getByTestId(
    zone === "paired"
      ? "candidate-group-paired-case:CASE-202603-101"
      : "candidate-group-unpaired-row:oa-o-202603-001",
  );
  await expect(zoneLocator).toBeVisible();
  await expect(group).toBeVisible();

  await zoneLocator.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await zoneLocator.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await zoneLocator.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(zoneLocator.getByText("已选 3")).toBeVisible();

  return { zoneLocator, group };
}

function expectNoWorkbenchMutationCalls(api: Awaited<ReturnType<typeof installDeterministicApiMocks>>) {
  for (const endpoint of workbenchMutationEndpoints) {
    expect(api.count(endpoint), endpoint).toBe(0);
  }
}

test.describe("workbench read-export permission browser flow", () => {
  test("keeps unpaired write entries disabled or hidden without mutation APIs", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    await page.goto("/");

    const { zoneLocator: unpairedZone, group: unpairedGroup } = await selectWorkbenchGroupRows(page, "unpaired");
    await expect(unpairedGroup.getByRole("button", { name: "详情" }).first()).toBeVisible();

    await expect(unpairedZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "忽略", exact: true })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "标记异常" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "确认关联" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "统一异常处理" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("keeps paired relation withdraw entries disabled or hidden without mutation APIs", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "read_export_only",
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");

    const { zoneLocator: pairedZone, group: pairedGroup } = await selectWorkbenchGroupRows(page, "paired");
    await expect(pairedGroup.getByText("完全关联").first()).toBeVisible();

    await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "取消关联" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
    await expect(page.getByRole("menuitem", { name: "取消关联" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("keeps processed exception and ignored item recovery entries hidden without mutation APIs", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "read_export_only",
      workbenchInitialExceptionApplied: true,
      workbenchInitialRowIgnored: true,
    });

    await page.goto("/");

    const unpairedZone = page.getByTestId("zone-unpaired");
    await expect(unpairedZone).toBeVisible();

    await unpairedZone.getByRole("button", { name: /已处理异常3项/ }).click();
    const processedModal = page.getByRole("dialog", { name: "已处理异常弹窗" });
    await expect(processedModal).toBeVisible();
    await expect(processedModal.getByText("追进项发票").first()).toBeVisible();
    await expect(processedModal.getByText("浏览器异常备注").first()).toBeVisible();
    await expect(processedModal.getByRole("button", { name: "取消异常处理" })).toHaveCount(0);
    await processedModal.getByRole("button", { name: "关闭" }).click();

    await unpairedZone.getByRole("button", { name: /已忽略1项/ }).click();
    const ignoredModal = page.getByRole("dialog", { name: "已忽略弹窗" });
    await expect(ignoredModal).toBeVisible();
    await expect(ignoredModal.getByText("智能工厂设备商")).toBeVisible();
    await expect(ignoredModal.getByRole("button", { name: "撤回忽略" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });
});

test.describe("workbench App Health write-safety browser flow", () => {
  test("keeps read-export workbench readable while write-safety is blocked", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "read_export_only",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator: unpairedZone, group: unpairedGroup } = await selectWorkbenchGroupRows(page, "unpaired");
    await expect(unpairedGroup.getByRole("button", { name: "详情" }).first()).toBeVisible();
    await expect(unpairedZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "忽略", exact: true })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "确认关联" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("blocks full-access unpaired writes without blocking read-side diagnosis", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "full_access",
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator: unpairedZone, group: unpairedGroup } = await selectWorkbenchGroupRows(page, "unpaired");
    await expect(unpairedGroup.getByRole("button", { name: "详情" }).first()).toBeVisible();
    await expect(unpairedZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "忽略", exact: true })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "标记异常" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "确认关联" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "关联预览" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("blocks admin paired and recovery writes without hiding readable states", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "admin",
      workbenchInitialExceptionApplied: true,
      workbenchInitialRelationConfirmed: true,
      workbenchInitialRowIgnored: true,
    });

    await page.goto("/");

    await expect(page.getByRole("status", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator: pairedZone, group: pairedGroup } = await selectWorkbenchGroupRows(page, "paired");
    await expect(pairedGroup.getByText("完全关联").first()).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "取消关联" })).toHaveCount(0);

    const unpairedZone = page.getByTestId("zone-unpaired");
    await unpairedZone.getByRole("button", { name: /已处理异常3项/ }).click();
    const processedModal = page.getByRole("dialog", { name: "已处理异常弹窗" });
    await expect(processedModal).toBeVisible();
    await expect(processedModal.getByText("浏览器异常备注").first()).toBeVisible();
    await expect(processedModal.getByRole("button", { name: "取消异常处理" })).toHaveCount(0);
    await processedModal.getByRole("button", { name: "关闭" }).click();

    await unpairedZone.getByRole("button", { name: /已忽略1项/ }).click();
    const ignoredModal = page.getByRole("dialog", { name: "已忽略弹窗" });
    await expect(ignoredModal).toBeVisible();
    await expect(ignoredModal.getByText("智能工厂设备商")).toBeVisible();
    await expect(ignoredModal.getByRole("button", { name: "撤回忽略" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });
});
