import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("OA applicant multiselect saves and reloads without fetching on the list page", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  let version = 5;
  let reads = 0;
  let writes = 0;
  let rules = [{ id: "multi", statusCode: "offset", label: "冲", description: "", enabled: true,
    conditions: { hasBank: false, hasOa: true, applicantNames: ["刘树刚"] } }];
  await page.route("**/api/input-invoice-usage/payment-status-rules", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      expect(body.expectedVersion).toBe(version);
      expect(body.idempotencyKey).toBeTruthy();
      rules = body.rules;
      version += 1;
      writes += 1;
    } else reads += 1;
    await route.fulfill({ json: { version, readOnly: false, permissions: { canSave: true }, rules,
      applicantOptions: [
        { userId: "1", name: "刘树刚", account: "LIU", enabled: true, matchName: "刘树刚" },
        { userId: "2", name: "黄 亮", account: "HUANG", enabled: true, matchName: "黄亮" },
        { userId: "3", name: "刘树刚", account: "LIU_OLD", enabled: false, matchName: "刘树刚" },
        { userId: "4", name: "周洁莹", account: "ZHOU", enabled: false, matchName: "周洁莹" },
      ] } });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/input-invoice-usage");
  await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
  expect(reads).toBe(0);
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  const drawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
  await drawer.getByRole("combobox", { name: "冲 OA 申请人条件" }).click();
  const account = (name: string) => page.getByRole("option", { name, exact: true });
  await expect(account("刘树刚 LIU")).toHaveAttribute("aria-selected", "true");
  await expect(account("刘树刚 LIU_OLD")).toHaveAttribute("aria-selected", "true");
  const search = page.getByRole("searchbox", { name: "搜索申请人姓名或账号" });
  await search.fill("LIU_OLD");
  await expect(page.getByRole("listbox", { name: "OA 申请人账号" }).getByRole("option")).toHaveCount(1);
  await account("刘树刚 LIU_OLD").click();
  await search.fill("");
  await expect(account("刘树刚 LIU")).toHaveAttribute("aria-selected", "false");
  await expect(account("刘树刚 LIU_OLD")).toHaveAttribute("aria-selected", "false");
  await account("刘树刚 LIU").click();
  await expect(account("刘树刚 LIU_OLD")).toHaveAttribute("aria-selected", "true");
  await account("周洁莹 ZHOU").click();
  await account("黄 亮 HUANG").click();
  await expect(account("周洁莹 ZHOU").getByRole("img", { name: "账号已停用" })).toBeVisible();
  await page.screenshot({ path: "../outputs/payment-rule-applicants-open.png", animations: "disabled" });
  await page.keyboard.press("Escape");
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByText("规则已保存。")).toBeVisible();
  expect(rules[0].conditions.applicantNames).toEqual(["刘树刚", "周洁莹", "黄亮"]);
  expect(writes).toBe(1);
  await drawer.getByRole("button", { name: "关闭支付状态规则抽屉" }).click();
  await expect(drawer).toHaveCount(0);
  expect(reads).toBe(1);
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  await expect(drawer.getByRole("combobox", { name: "冲 OA 申请人条件" })).toContainText("刘树刚、周洁莹 +1");
  await page.screenshot({ path: "../outputs/payment-rule-applicants-saved.png", animations: "disabled" });
  await page.setViewportSize({ width: 1024, height: 850 });
  await drawer.getByRole("combobox", { name: "冲 OA 申请人条件" }).click();
  await expect(account("周洁莹 ZHOU")).toHaveAttribute("aria-selected", "true");
  await page.screenshot({ path: "../outputs/payment-rule-applicants-narrow.png", animations: "disabled" });
  await page.keyboard.press("Escape");
  expect(reads).toBe(2);
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("empty rules allow directory verification through a discarded local draft without a write", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  let writes = 0;
  await page.route("**/api/input-invoice-usage/payment-status-rules", route => {
    if (route.request().method() !== "GET") writes += 1;
    return route.fulfill({ json: { version: 1, readOnly: false, permissions: { canSave: true }, rules: [], applicantOptions: [
      { userId: "1", name: "测试停用账号", account: "TEST_DISABLED", enabled: false, matchName: "测试停用账号" },
    ] } });
  });
  await page.goto("/input-invoice-usage");
  await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  const drawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
  await drawer.getByRole("button", { name: "新增规则", exact: true }).click();
  await page.getByRole("button", { name: "添加", exact: true }).click();
  const draft = drawer.getByRole("table", { name: "支付状态规则" }).getByRole("row").last();
  await draft.getByRole("textbox").fill("目录验证草稿");
  await draft.getByRole("combobox", { name: "目录验证草稿 OA 申请人条件" }).click();
  await page.getByRole("option", { name: "指定申请人", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  const search = page.getByRole("searchbox", { name: "搜索申请人姓名或账号" });
  await search.fill("TEST_DISABLED");
  await page.getByRole("option", { name: "测试停用账号 TEST_DISABLED", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(search).not.toBeVisible();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();
  await drawer.getByRole("button", { name: "还原", exact: true }).click();
  await expect(drawer.getByRole("textbox")).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  expect(writes).toBe(0);
  await expectNoUnexpectedSuccessUiErrors(page);
});
