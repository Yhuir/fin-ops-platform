import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const mutationEndpoints = [
  "POST /api/workbench/actions/confirm-link/preview",
  "POST /api/workbench/actions/confirm-link",
  "POST /api/workbench/actions/withdraw-link/preview",
  "POST /api/workbench/actions/withdraw-link",
  "POST /api/workbench/exceptions/review",
];

async function selectWorkbenchGroupRows(page: Page, zone: "unpaired" | "paired") {
  const zoneLocator = page.getByTestId(`zone-${zone}`);
  const group = page.getByTestId(
    zone === "paired"
      ? "candidate-group-paired-case:CASE-202603-101"
      : "candidate-group-unpaired-row:oa-o-202603-001",
  );
  await expect(zoneLocator).toBeVisible();
  await zoneLocator.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await zoneLocator.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await zoneLocator
    .getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })
    .getByRole("cell")
    .first()
    .click();
  return { zoneLocator, group };
}

function expectNoMutations(api: Awaited<ReturnType<typeof installDeterministicApiMocks>>) {
  for (const endpoint of mutationEndpoints) expect(api.count(endpoint), endpoint).toBe(0);
}

test.describe("workbench health write-safety browser flow", () => {
  test("blocks a page-authorized user's writes without blocking diagnosis", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "user",
      allowedPageKeys: ["reconciliation-workbench"],
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator, group } = await selectWorkbenchGroupRows(page, "unpaired");
    await expect(group.getByRole("button", { name: "详情" }).first()).toBeVisible();
    await expect(zoneLocator.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await expect(zoneLocator.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expectNoMutations(api);
  });

  test("blocks administrator writes without hiding paired states", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      appHealthWriteSafetyBlocked: true,
      sessionMode: "admin",
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: "写操作暂不可用" })).toBeVisible();
    const { zoneLocator, group } = await selectWorkbenchGroupRows(page, "paired");
    await expect(group.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    await expect(zoneLocator.getByRole("button", { name: "撤回关联" })).toBeDisabled();
    expectNoMutations(api);
  });
});
