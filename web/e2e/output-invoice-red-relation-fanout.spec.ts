import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("销项发票自动红蓝票关系", () => {
  test("蓝票与红票读取同一正式关系并只打开只读详情", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/output-invoice-collections");
    const blueRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    const redRow = page.getByRole("row", { name: /XSFP-E2E-0002/ });
    await expect(blueRow.getByText("已被红冲")).toBeVisible();
    await expect(redRow.getByText("已冲销蓝票")).toBeVisible();

    const detailResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/relation-details")
      && response.request().method() === "GET");
    await blueRow.getByRole("button", { name: "红蓝票 · 2" }).click();
    expect((await detailResponse).status()).toBe(200);
    const drawer = page.getByRole("dialog", { name: "销项发票详情" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("关系数量", { exact: true }).locator("..")).toContainText("2");
    await expect(drawer.getByText("output_invoice_reversal")).toHaveCount(2);

    await drawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(drawer).toBeHidden();
    expect(api.calls.some((call) =>
      /^(POST|PUT|PATCH|DELETE) \/api\/output-invoice-collections\//.test(call))).toBe(false);
    expect(api.calls.some((call) => call.includes("red-invoice-relations"))).toBe(false);
  });
});
