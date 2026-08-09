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
  await zoneLocator
    .getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })
    .getByRole("cell")
    .first()
    .click();
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
    await expect(page.getByRole("dialog", { name: /确认关联|撤回关联/ })).toHaveCount(0);
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
    await expect(pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();

    await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "取消关联" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
    await expect(page.getByRole("menuitem", { name: "取消关联" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: /确认关联|撤回关联/ })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("keeps OA invoice anomalies readable without mutation APIs", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "read_export_only",
      workbenchAmountMismatchScenario: true,
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");

    const unpairedZone = page.getByTestId("zone-unpaired");
    await expect(unpairedZone).toBeVisible();

    await unpairedZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(exceptionDrawer).toBeVisible();
    await exceptionDrawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await expect(exceptionDrawer.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    await expect(exceptionDrawer.getByText("金额不一致").first()).toBeVisible();
    await expect(exceptionDrawer.getByRole("button", { name: "忽略" })).toHaveCount(0);

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

    await expect(page.getByRole("button", { name: "写操作暂不可用" })).toBeVisible();
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

    await expect(page.getByRole("button", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator: unpairedZone, group: unpairedGroup } = await selectWorkbenchGroupRows(page, "unpaired");
    await expect(unpairedGroup.getByRole("button", { name: "详情" }).first()).toBeVisible();
    await expect(unpairedZone.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "异常处理" })).toBeDisabled();
    await expect(unpairedZone.getByRole("button", { name: "撤回关联" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "忽略", exact: true })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "标记异常" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "异常处理" })).toHaveCount(0);
    await expect(unpairedGroup.getByRole("button", { name: "确认关联" })).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: /确认关联|撤回关联/ })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });

  test("blocks admin paired and recovery writes without hiding readable states", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "admin",
      workbenchInitialRelationConfirmed: true,
      workbenchAmountMismatchScenario: true,
    });

    await page.goto("/");

    await expect(page.getByRole("button", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator: pairedZone, group: pairedGroup } = await selectWorkbenchGroupRows(page, "paired");
    await expect(pairedGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    await expect(pairedZone.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    await expect(pairedGroup.getByRole("button", { name: "更多" })).toHaveCount(0);
    await expect(pairedGroup.getByRole("button", { name: "取消关联" })).toHaveCount(0);

    const unpairedZone = page.getByTestId("zone-unpaired");
    await unpairedZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(exceptionDrawer).toBeVisible();
    await exceptionDrawer.getByRole("button", { name: "展开异常明细" }).first().click();
    await expect(exceptionDrawer.getByText("金额不一致").first()).toBeVisible();
    await expect(exceptionDrawer.getByRole("button", { name: "忽略" })).toHaveCount(0);

    expectNoWorkbenchMutationCalls(api);
  });
});
