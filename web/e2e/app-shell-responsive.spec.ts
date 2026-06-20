import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("app shell responsive browser smoke", () => {
  test("opens the compact navigation drawer and closes it after route navigation", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/cost-statistics");

    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const openMenuButton = page.locator("button[aria-label='打开菜单']");
    await expect(openMenuButton).toBeVisible();
    await openMenuButton.click();

    const drawer = page.getByRole("dialog", { name: "主导航菜单" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "设置" })).toBeVisible();
    await expect(drawer.getByRole("link", { name: "银行流水导入" })).toBeVisible();

    await drawer.getByRole("link", { name: "设置" }).click();

    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
    await expect(drawer).toBeHidden();
  });

  test("keeps embedded OA shell collapsed but expandable on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/?embedded=oa");

    await expect(page.locator(".app-shell.embedded-shell")).toBeVisible();
    await expect(page.locator(".page-body.embedded")).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("button", { name: "展开菜单" })).toBeVisible();
    await expect(page.getByRole("button", { name: "打开菜单" })).toHaveCount(0);

    await page.getByRole("button", { name: "展开菜单" }).click();

    await expect(page.getByText("财务运营平台").first()).toBeVisible();
    await expect(page.getByText("溯源办公系统").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "折叠菜单" })).toBeVisible();
  });
});
