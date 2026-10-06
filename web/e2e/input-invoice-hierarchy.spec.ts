import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("hierarchy wraps ten categories and combines selection with the OA header filter", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const first = page.waitForResponse(response => new URL(response.url()).pathname === "/api/input-invoice-usage/rows");
  await page.goto("/input-invoice-usage");
  const payload = await (await first).json();
  const custom = Array.from({ length: 10 }, (_, i) => ({ id: `category:custom_${i}`, label: `规则分类 ${i + 1}`, count: 0 }));
  payload.classification.groups[0].children.push(...custom);
  await page.route("**/api/input-invoice-usage/rows?*", route => route.fulfill({ json: payload }));
  await page.reload();
  const panel = page.getByRole("region", { name: "进项发票使用分类" });
  await expect(panel.getByRole("button", { name: "规则分类 10 0 张", exact: true })).toBeVisible();
  for (const width of [1920, 1440, 1024]) {
    await page.setViewportSize({ width, height: 1100 });
    expect(await panel.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    const parent = panel.getByRole("group", { name: "已付款", exact: true });
    const parentBox = await parent.boundingBox();
    for (const child of await parent.getByRole("button").all()) {
      const box = await child.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(parentBox!.x - 1);
      expect(box!.x + box!.width).toBeLessThanOrEqual(parentBox!.x + parentBox!.width + 1);
    }
    await page.screenshot({ path: testInfo.outputPath(`invoice-hierarchy-${width}.png`), animations: "disabled" });
  }
  await page.setViewportSize({ width: 1920, height: 1100 });
  await panel.getByRole("button", { name: "规则分类 10 0 张", exact: true }).click();
  await expect(panel.getByRole("button", { name: "规则分类 10 0 张", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "OA 关联筛选", exact: true }).click();
  const requested = page.waitForRequest(request => request.url().includes("/api/input-invoice-usage/rows?"));
  await page.getByRole("menuitemradio", { name: "未关联 OA", exact: true }).click();
  const filters = JSON.parse(decodeURIComponent(new URL((await requested).url()).searchParams.get("filters")!));
  expect(filters).toEqual(expect.arrayContaining([
    { field: "usage_status", operator: "in", values: ["used"] },
    { field: "payment_status", operator: "in", values: ["custom_9"] },
    { field: "oa_relation", operator: "in", values: ["unlinked"] },
  ]));
  await expect(page.getByRole("menuitemradio", { name: "未关联 OA", exact: true })).toHaveCount(0);
  payload.classification.groups[0].children = payload.classification.groups[0].children.filter((item: { id: string }) => item.id !== "category:custom_9");
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(panel.getByRole("button", { name: "规则分类 10 0 张", exact: true })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: /^已使用/ })).toHaveAttribute("aria-pressed", "true");
});
