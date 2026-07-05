import { expect, test, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";

function createAppShellLatencyRecorder(page: Parameters<typeof createOperationLatencyRecorder>[0], testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/",
    pageKey: "app-shell-navigation",
    module: "app-shell-navigation",
  });
}

test.describe("app shell responsive browser smoke", () => {
  test("opens the compact navigation drawer and closes it after route navigation", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createAppShellLatencyRecorder(page, testInfo);

    await recordLatency({
      route: "/cost-statistics",
      operationId: "app-shell.open-cost-statistics-mobile",
      visibleLabel: "成本统计",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/cost-statistics");
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const openMenuButton = page.locator("button[aria-label='打开菜单']");
    await expect(openMenuButton).toBeVisible();

    const drawer = page.getByRole("dialog", { name: "主导航菜单" });
    await recordLatency({
      route: "/cost-statistics",
      operationId: "app-shell.open-compact-navigation-drawer",
      visibleLabel: "打开菜单",
      actionType: "click",
    }, async (mark) => {
      await openMenuButton.click();
      await mark("finalSettledLatencyMs", expect(drawer).toBeVisible());
    });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "设置" })).toBeVisible();
    await expect(drawer.getByRole("link", { name: "银行流水导入" })).toBeVisible();

    await recordLatency({
      route: "/settings",
      operationId: "app-shell.navigate-drawer-to-settings",
      visibleLabel: "设置",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("link", { name: "设置" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer).toBeHidden());
    });

    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(drawer).toBeHidden();
  });

  test("keeps embedded OA shell collapsed but expandable on desktop", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createAppShellLatencyRecorder(page, testInfo);

    await recordLatency({
      route: "/",
      operationId: "app-shell.open-embedded-oa-shell",
      visibleLabel: "embedded OA shell",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/?embedded=oa");
      await mark("finalSettledLatencyMs", expect(page.locator(".app-shell.embedded-shell")).toBeVisible());
    });

    await expect(page.locator(".app-shell.embedded-shell")).toBeVisible();
    await expect(page.locator(".page-body.embedded")).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("button", { name: "展开菜单" })).toBeVisible();
    await expect(page.getByRole("button", { name: "打开菜单" })).toHaveCount(0);

    await recordLatency({
      route: "/",
      operationId: "app-shell.expand-embedded-menu",
      visibleLabel: "展开菜单",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "展开菜单" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible());
    });

    await expect(page.getByText("财务运营平台").first()).toBeVisible();
    await expect(page.getByText("溯源办公系统").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
  });
});
