import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test("payment rules support pointer and keyboard group ordering, cancellation and persisted readback", async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  let rules = [
    { id: "p1", statusCode: "custom_p1", label: "付款一", enabled: true, conditions: { hasBank: true } },
    { id: "p2", statusCode: "custom_p2", label: "付款二", enabled: false, conditions: { hasBank: true } },
    { id: "u1", statusCode: "custom_u1", label: "未付一", enabled: true, conditions: { hasBank: false } },
    { id: "u2", statusCode: "custom_u2", label: "未付二", enabled: true, conditions: { hasBank: false } },
  ];
  let version = 4;
  const writes: Array<{ rules: typeof rules; expectedVersion: number }> = [];
  await page.route("**/api/input-invoice-usage/payment-status-rules", async route => {
    if (route.request().method() === "PUT") {
      const request = route.request().postDataJSON(); writes.push(request); rules = request.rules; version += 1;
    }
    await route.fulfill({ json: { version, rules, readOnly: false, permissions: { canSave: true }, applicantOptions: [] } });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/input-invoice-usage");
  await expect(page.getByRole("region", { name: "进项发票使用分类" })).toHaveAttribute("aria-busy", "false");
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  const drawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
  const ids = () => drawer.locator(".payment-rule-sortable-row").evaluateAll(nodes => nodes.map(node => node.getAttribute("data-key")));
  const handle = (name: string) => drawer.getByRole("button", { name: new RegExp(`调整规则 ${name} 的顺序`) });
  const drag = async (source: string, target: string) => {
    const from = await handle(source).boundingBox(); const to = await handle(target).boundingBox();
    await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
    await page.mouse.down(); await page.mouse.move(to!.x + to!.width / 2, to!.y + to!.height / 2, { steps: 12 }); await page.mouse.up();
  };
  await expect(handle("付款二")).toHaveText("2");
  await drag("付款二", "付款一");
  await expect.poll(ids).toEqual(["p2", "p1", "u1", "u2"]);
  expect(writes).toHaveLength(0);
  await drag("付款二", "未付二");
  await expect.poll(ids).toEqual(["p2", "p1", "u1", "u2"]);
  await handle("未付二").focus(); await page.keyboard.press("Space"); await page.keyboard.press("ArrowUp"); await page.keyboard.press("Space");
  await expect.poll(ids).toEqual(["p2", "p1", "u2", "u1"]);
  await expect(handle("未付二")).toBeFocused();
  await handle("付款一").focus(); await page.keyboard.press("Space"); await page.keyboard.press("ArrowUp"); await page.keyboard.press("Escape");
  await expect.poll(ids).toEqual(["p2", "p1", "u2", "u1"]);
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByText("规则已保存。", { exact: true })).toBeVisible();
  expect(writes[0].expectedVersion).toBe(4);
  expect(writes[0].rules.map(rule => rule.id)).toEqual(["p2", "p1", "u2", "u1"]);
  expect(writes[0].rules[0].enabled).toBe(false);
  await drawer.getByRole("button", { name: "关闭支付状态规则抽屉" }).click();
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  await expect.poll(ids).toEqual(["p2", "p1", "u2", "u1"]);
  await drag("付款一", "付款二");
  await drawer.getByRole("button", { name: "还原", exact: true }).click();
  await expect.poll(ids).toEqual(["p2", "p1", "u2", "u1"]);
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await expectNoUnexpectedSuccessUiErrors(page);
  await page.screenshot({ path: info.outputPath("payment-rule-order.png"), animations: "disabled" });
});
