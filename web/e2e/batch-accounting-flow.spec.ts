import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("history entry moves to settings, preserves drafts and renders readonly complete detail", async ({ page }, testInfo) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/settings");
  await expect(page.getByRole("tab", { name: "银行账户", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(page.getByRole("region", { name: "银行账户映射" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("settings-bank-1440.png") });
  await page.getByRole("textbox", { name: / 银行名称$/ }).first().fill("测试银行草稿");
  expect(api.count("GET /api/batch-accounting")).toBe(0);
  await page.getByRole("tab", { name: "OA导入设置", exact: true }).click();
  await page.getByLabel("OA导入起始日期").fill("2026-02-01");
  await page.getByRole("tab", { name: "批量账务", exact: true }).click();
  await expect(page.getByRole("grid", { name: "批量账务历史记录" })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存设置", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "批量账务", exact: true })).toHaveCount(0);
  for (const width of [1920, 1440, 900]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const geometry = await page.locator(".settings-layout:visible").evaluate((el) => {
      const outer = el.getBoundingClientRect();
      const workspace = el.querySelector(".settings-workspace")!.getBoundingClientRect();
      return { padding: getComputedStyle(el).paddingLeft, width: outer.width, workspace: workspace.width,
        left: workspace.left - outer.left, right: outer.right - workspace.right };
    });
    expect(geometry.padding).toBe("16px");
    expect(Math.abs(geometry.workspace - Math.min(1280, geometry.width - 32))).toBeLessThan(2);
    expect(Math.abs(geometry.left - geometry.right)).toBeLessThan(2);
    await page.screenshot({ path: testInfo.outputPath(`batch-history-${width}.png`) });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "查看 历史商户 详情" }).click();
  const drawer = page.getByRole("dialog", { name: "批量账务详情" });
  await expect(drawer.getByText("历史流水成员二")).toBeVisible();
  await expect(drawer.getByText("王青", { exact: false })).toBeVisible();
  await expect(drawer.getByRole("button", { name: /提交|撤回|保存|关联/ })).toHaveCount(0);
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished));
  });
  await page.screenshot({ path: testInfo.outputPath("batch-history-detail.png") });
  await page.setViewportSize({ width: 900, height: 1000 });
  await page.screenshot({ path: testInfo.outputPath("batch-history-detail-900.png") });
  await drawer.getByRole("button", { name: "关闭抽屉" }).click();
  await page.getByRole("tab", { name: "OA导入设置", exact: true }).click();
  await expect(page.getByLabel("OA导入起始日期")).toHaveValue("2026-02-01");
  await page.getByRole("tab", { name: "银行账户", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "测试银行草稿 银行名称", exact: true })).toHaveValue("测试银行草稿");
  expect(api.calls.filter((call) => /^(POST|PUT|DELETE)/.test(call) && call.includes("batch-accounting"))).toEqual([]);
  await expectNoUnexpectedSuccessUiErrors(page);
  await page.getByRole("tab", { name: "批量账务", exact: true }).click();
  await expect(page.getByRole("grid", { name: "批量账务历史记录" })).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByRole("region", { name: "银行账户映射" })).toBeVisible();
});

test("history-only permission opens old address without loading other settings", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user", allowedPageKeys: ["batch-accounting"] });
  await page.goto("/batch-accounting");
  await expect(page).toHaveURL(/\/settings\?section=batch-accounting/);
  await expect(page.getByRole("grid", { name: "批量账务历史记录" })).toBeVisible();
  await expect(page.getByRole("tab")).toHaveCount(1);
  expect(api.calls.filter((call) => call.includes("/api/workbench/settings") || call.includes("access-control") || call.includes("/api/background-jobs"))).toEqual([]);
  await page.reload();
  await expect(page.getByText("历史商户", { exact: true })).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("history failure is distinct from empty and explicit retry recovers", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user", allowedPageKeys: ["batch-accounting"] });
  let failing = true;
  await page.route("**/api/batch-accounting?*", (route) => failing
    ? route.fulfill({ status: 503, json: { error: "unavailable", message: "批量账务数据加载暂时失败，请刷新后重试。" } })
    : route.fallback());
  await page.goto("/settings?section=batch-accounting");
  await expect(page.getByText("批量账务数据加载暂时失败，请刷新后重试。")).toBeVisible();
  await expect(page.getByText("暂无已提交记录")).toHaveCount(0);
  failing = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByText("历史商户", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /流水年份/ }).click();
  await page.getByRole("option", { name: "2025", exact: true }).click();
  await expect(page.getByText("暂无已提交记录")).toBeVisible();
});

test("settings-only permission does not expose history", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user", allowedPageKeys: ["settings"] });
  await page.goto("/settings");
  await expect(page.getByRole("tab", { name: "银行账户", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "批量账务", exact: true })).toHaveCount(0);
  expect(api.count("GET /api/batch-accounting")).toBe(0);
});


test("direct history opens independently of unavailable general settings", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.route("**/api/workbench/settings", route => route.fulfill({ status: 503, json: { message: "设置暂时不可用" } }));
  await page.goto("/settings?section=batch-accounting");
  await expect(page.getByRole("grid", { name: "批量账务历史记录" })).toBeVisible();
  expect(api.calls.filter(call => call.includes("/api/workbench/settings"))).toEqual([]);
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toHaveCount(1);
  await expectNoUnexpectedSuccessUiErrors(page);
});
