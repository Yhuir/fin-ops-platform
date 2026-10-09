import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("销项发票自动红蓝票关系", () => {
  test("蓝票与红票读取同一正式关系并只打开只读详情", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
    });

    await page.goto("/output-invoice-collections");
    const blueRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    const redRow = page.getByRole("row", { name: /XSFP-E2E-0002/ });
    await expect(blueRow.getByText("已被冲")).toBeVisible();
    await expect(redRow.getByText("已关联蓝字")).toBeVisible();
    await expect(blueRow.getByText("蓝字", { exact: true })).toBeVisible();
    await expect(redRow.getByText("红字", { exact: true })).toBeVisible();

    await blueRow.getByRole("button", {name:"展开配对关系，发票共 2 张"}).click();
    const expansion = page.getByRole("region", {name:"配对关系"});
    await expect(expansion).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const response = page.waitForResponse(response=>response.url().endsWith('/api/output-invoice-collections/invoices/out-e2e-002/detail'));
    await expansion.getByRole("button", {name:"查看发票 XSFP-E2E-0002 详情"}).click();
    expect((await response).status()).toBe(200);
    const drawer = page.getByRole("dialog", {name:"发票详情"});
    await expect(drawer.getByRole("cell", {name:"XSFP-E2E-0002",exact:true})).toBeVisible();
    await expect(drawer.getByRole("cell", {name:"-12345.67",exact:true})).toBeVisible();
    await expect(drawer.getByRole("tablist")).toHaveCount(0);
    await drawer.getByRole("button", {name:"关闭详情抽屉"}).click();
    await expect(drawer).toBeHidden();
    expect(api.calls.some(call=>call.includes('relation-details'))).toBe(false);
    expect(api.calls.some((call) =>
      /^(POST|PUT|PATCH|DELETE) \/api\/output-invoice-collections\//.test(call))).toBe(false);
    expect(api.calls.some((call) => call.includes("red-invoice-relations"))).toBe(false);
  });
});
