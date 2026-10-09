import { expect, test, setCheckbox } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test("payment fact hierarchy, usage parents and rule edits retain scope and server summary", async ({ page }, info) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const first = page.waitForResponse(response => new URL(response.url()).pathname === "/api/input-invoice-usage/rows");
  await page.goto("/input-invoice-usage");
  const payload = await (await first).json();
  let version = 2;
  let rules = [{ id: "r1", statusCode: "custom_review", label: "待核对", description: "", priority: 1, enabled: true, conditions: { hasOa: true, applicantNames: ["陈秀云"], hasBank: false, invoiceNetSign: "negative" } }];
  let rejectSave = true;
  const writes: Array<Record<string, unknown>> = [];
  await page.route("**/api/input-invoice-usage/rows?*", route => route.fulfill({ json: { ...payload,
    summary: { invoiceCount: 13, totalWithTax: "8765.43", taxAmount: "350.10", missingTaxAmountCount: 2, unclassifiedCount: 0 },
    classification: { all: { id: "all", label: "全部发票", count: 13 }, used: { id: "used", label: "已使用", count: 13 }, unused: { id: "unused", label: "待使用", count: 0 }, groups: [
      { id: "paid", label: "已付款", count: 4, tone: "paid", children: [] },
      { id: "unpaid", label: "未付款", count: 9, tone: "unpaid", children: rules.length ? [{ id: "category:custom_review", label: rules[0].label, count: 9 }] : [] },
    ] },
  } }));
  await page.route("**/api/input-invoice-usage/payment-status-rules", async route => {
    if (route.request().method() === "PUT") {
      const request = route.request().postDataJSON(); writes.push(request);
      if (rejectSave) { rejectSave = false; return route.fulfill({ status: 409, json: { error: { code: "payment_status_rules_version_conflict", message: "规则版本冲突" } } }); }
      rules = request.rules; version += 1;
    }
    return route.fulfill({ json: { version, rules, readOnly: false, permissions: { canSave: true }, applicantOptions: [
      { userId: "u1", name: "陈秀云", account: "TEST001", enabled: true, matchName: "陈秀云" },
      { userId: "u2", name: "周洁莹", account: "TEST002", enabled: false, matchName: "周洁莹" },
    ] } });
  });
  await page.reload();
  const classification = page.getByRole("region", { name: "进项发票使用分类" });
  await expect(classification.getByRole("button", { name: /待使用|已使用/ })).toHaveCount(2);
  await expect(classification.getByRole("button", { name: "未付款 9 张", exact: true })).toBeVisible();
  await expect(page.getByLabel("当前筛选发票汇总")).toHaveText("13 张价税合计 8765.43税额合计 350.10（缺失 2 张）");
  await classification.getByRole("button", { name: "待使用 0 张", exact: true }).click();
  const categoryRequest = page.waitForRequest(request => request.url().includes("/api/input-invoice-usage/rows?"));
  await classification.getByRole("button", { name: "待核对 9 张", exact: true }).click();
  expect(JSON.parse(decodeURIComponent(new URL((await categoryRequest).url()).searchParams.get("filters")!))).toEqual(expect.arrayContaining([
    { field: "usage_status", operator: "in", values: ["used"] }, { field: "payment_group", operator: "in", values: ["unpaid"] }, { field: "payment_status", operator: "in", values: ["custom_review"] },
  ]));
  await page.screenshot({ animations: "disabled", path: info.outputPath("input-invoice-main.png") });
  if (await page.getByRole("button", { name: "更多页面操作" }).isVisible()) await page.getByRole("button", { name: "更多页面操作" }).click();
  await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
  const drawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
  await expect(drawer.getByRole("grid", { name: "支付状态规则" })).toBeVisible();
  await expect(drawer.getByRole("columnheader")).toHaveText(["启用", "优先级", "标签", "OA 申请人", "流水", "发票净额", "发票付款比较", "更多条件", "操作"]);
  await drawer.getByRole("textbox", { name: "标签 1" }).fill("人工复核");
  await drawer.getByRole("button", { name: "复制规则 人工复核" }).click();
  await expect(drawer.getByRole("textbox", { name: "标签 2" })).toHaveValue("人工复核");
  await setCheckbox(drawer.getByRole("checkbox", { name: "启用规则 人工复核" }).nth(1), false);
  await expect(drawer.getByRole("checkbox", { name: "启用规则 人工复核" }).nth(1)).not.toBeChecked();
  await page.screenshot({ animations: "disabled", path: info.outputPath("input-invoice-rules.png") });
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("alert")).toContainText("规则已被其他人更新");
  await expect(drawer.getByRole("textbox", { name: "标签 1" })).toHaveValue("人工复核");
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByText("规则已保存。", { exact: true })).toBeVisible();
  expect(writes[1]).toMatchObject({ expectedVersion: 2, rules: [expect.objectContaining({ statusCode: "custom_review", label: "人工复核" }), expect.objectContaining({ statusCode: "custom_review", label: "人工复核", enabled: false })] });
  await drawer.getByRole("button", { name: "删除规则 人工复核" }).first().click();
  await drawer.getByRole("button", { name: "删除规则 人工复核" }).click();
  await drawer.getByRole("button", { name: "保存", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await drawer.getByRole("button", { name: "关闭支付状态规则抽屉" }).click();
  await expect(classification.getByRole("button", { name: "未付款 9 张" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /使用状态/ })).toHaveCount(0);
  await expectNoUnexpectedSuccessUiErrors(page);
});
