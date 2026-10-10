import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("销项发票自动红蓝票关系", () => {
  test("共两笔流水在原八列中展示各自金额和摘要", async ({page}) => {
    const api = await installDeterministicApiMocks(page, {sessionMode:'user'});
    await page.goto('/output-invoice-collections');
    const table = page.getByRole('grid', {name:'销项发票收款情况表'});
    const source = table.getByRole('row', {name:/XSFP-E2E-0003/});
    await expect(source).toBeVisible();
    const countBefore = await table.locator('tbody tr').count();
    const readsBefore = api.calls.length;
    await source.getByRole('button', {name:'展开配对关系，流水共 2 笔'}).click();
    const members = table.locator('tr[data-relation-group="output-collection-row-e2e-003"]');
    await expect(members).toHaveCount(2);
    await expect(table.locator('tbody tr')).toHaveCount(countBefore + 1);
    await expect(members.nth(0).locator('td')).toHaveCount(8);
    await expect(members.nth(1).locator('td')).toHaveCount(8);
    await expect(members.nth(0).locator('td').nth(6)).toContainText('600000.00');
    await expect(members.nth(1).locator('td').nth(6)).toContainText('420032.00');
    await expect(members.nth(0).locator('td').nth(7)).toContainText('第一笔客户回款');
    await expect(members.nth(1).locator('td').nth(7)).toContainText('第二笔客户回款');
    expect(api.calls).toHaveLength(readsBefore);
    await members.nth(0).getByRole('button', {name:'收起配对关系，流水共 2 笔'}).click();
    await expect(table.locator('tbody tr')).toHaveCount(countBefore);
  });

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

    const readsBefore = api.calls.length;
    await blueRow.getByRole("button", {name:"展开配对关系，发票共 2 张"}).click();
    const members = page.locator('tr[data-relation-group="output-collection-row-e2e-001"]');
    await expect(members).toHaveCount(2);
    await expect(members.nth(0).locator('td')).toHaveCount(8);
    await expect(members.nth(1).locator('td')).toHaveCount(8);
    await expect(members.nth(1).locator('td').nth(2)).toContainText('-12345.67');
    await expect(members.nth(1).locator('td').nth(0)).toContainText('2026-05-06');
    await expect(members.nth(1).locator('td').nth(3)).toContainText('浏览器 e2e 红字发票');
    await expect(members.nth(1).locator('td').nth(6)).not.toContainText('5000.00');
    await expect(members.nth(1).getByText('红字', {exact:true})).toBeVisible();
    await expect(members.nth(1).getByText('已关联蓝字', {exact:true})).toBeVisible();
    await expect(page.getByRole("region", {name:"配对关系"})).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(api.calls).toHaveLength(readsBefore);
    const response = page.waitForResponse(response=>response.url().endsWith('/api/output-invoice-collections/invoices/out-e2e-002/detail'));
    await members.nth(1).getByRole("button", {name:"查看发票 XSFP-E2E-0002 详情"}).click();
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
