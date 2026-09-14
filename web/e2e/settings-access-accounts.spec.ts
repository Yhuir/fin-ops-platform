import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("access accounts preserve drafts, report OA failure, save and render responsive HeroUI selection", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  let version = 12;
  let failSave = true;
  let accounts = ["002", "006", "007", "010", "044", "099"].map((id, index) => ({
    username: `YNSYLP${id}`, display_name: `财务账户${index + 1}`, oa_status: index === 5 ? "missing" : "active",
    page_keys: ["settings", "bank-details", "reconciliation-workbench"],
  }));
  await page.route("**/api/workbench/settings/access-control", async (route) => {
    if (route.request().method() === "PUT") {
      if (failSave) {
        failSave = false;
        return route.fulfill({ status: 502, json: { error: "oa_role_configuration_invalid", message: "internal detail" } });
      }
      const body = route.request().postDataJSON();
      expect(body.expected_version).toBe(version);
      accounts = body.accounts.map((item: {username: string; page_keys: string[]}) => ({ ...accounts.find((old) => old.username === item.username), ...item }));
      version += 1;
    }
    return route.fulfill({ json: { version, administrator: { username: "YNSYLP005", display_name: "权限管理员", protected: true }, accounts } });
  });
  await page.goto("/settings");
  await page.getByRole("tab", { name: /访问账户/ }).click();
  const section = page.getByRole("region", { name: "访问账户" });
  const list = section.getByRole("listbox", { name: "访问账户列表" });
  await expect(list.getByRole("option")).toHaveCount(6);
  await list.getByRole("option", { name: /YNSYLP044/ }).click();
  await section.getByText("银行明细", { exact: true }).click();
  await list.getByRole("option", { name: /YNSYLP002/ }).click();
  await list.getByRole("option", { name: /YNSYLP044/ }).click();
  await expect(section.getByRole("checkbox", { name: "银行明细" })).not.toBeChecked();
  await section.getByRole("button", { name: "保存访问权限" }).click();
  await expect(section.getByRole("alert")).toContainText("OA 入口角色配置不完整");
  await expect(section.getByRole("alert")).not.toContainText("关联台服务");
  await section.getByRole("button", { name: "保存访问权限" }).click();
  await expect(section.getByText("已保存访问账户。", { exact: true })).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(version).toBe(13);
  expect(accounts.find((item) => item.username === "YNSYLP044")?.page_keys).not.toContain("bank-details");
  await section.getByText("银行明细", { exact: true }).click();
  await section.getByRole("button", { name: "取消修改" }).click();
  await expect(section.getByRole("checkbox", { name: "银行明细" })).not.toBeChecked();
  await section.getByRole("searchbox", { name: "筛选已有账户" }).fill("044");
  await expect(list.getByRole("option")).toHaveCount(1);
  await section.getByRole("searchbox", { name: "筛选已有账户" }).fill("");
  for (const width of [1920, 1440, 1280, 768]) {
    await page.setViewportSize({ width, height: 1100 });
    await expect(section.getByRole("button", { name: "保存访问权限" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await section.screenshot({ path: testInfo.outputPath(`access-accounts-${width}.png`) });
  }
  await list.getByRole("option", { name: /YNSYLP044/ }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(list.getByRole("option", { name: /YNSYLP099/ })).toBeFocused();
});
