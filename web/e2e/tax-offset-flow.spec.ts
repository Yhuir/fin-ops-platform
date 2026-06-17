import { Buffer } from "node:buffer";

import { expect, test, type Page } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

function statCard(page: Page, label: string) {
  return page.locator(".stat-card").filter({ hasText: label });
}

test.describe("tax offset browser flow", () => {
  test("recalculates and saves a tax plan, then imports certified invoices in the page modal", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(statCard(page, "销项税额").getByText("41,600.00")).toBeVisible();
    await expect(statCard(page, "计划进项税额").getByText("18,240.00")).toBeVisible();
    await expect(page.getByRole("grid", { name: "销项票开票情况" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项票认证计划" })).toBeVisible();

    await page.getByRole("row", { name: /11203491/ }).locator(".checkbox__control").click();
    await expect(statCard(page, "计划进项税额").getByText("12,480.00")).toBeVisible();
    await expect(statCard(page, "本月应纳税额").getByText("29,120.00")).toBeVisible();
    expect(api.count("POST /api/tax-offset/calculate")).toBe(1);

    await page.getByRole("button", { name: "保存计划" }).click();
    await expect(page.getByText("已保存本月税金抵扣计划。")).toBeVisible();
    expect(api.count("POST /api/tax-offset/plans")).toBe(1);

    await page.getByRole("button", { name: "已认证发票导入" }).click();
    const dialog = page.getByRole("dialog", { name: "已认证发票导入" });
    await expect(dialog).toBeVisible();
    await dialog.locator('input[type="file"]').setInputFiles({
      name: "2026年3月 进项认证结果.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: Buffer.from("tax-certified-import-e2e"),
    });
    await expect(dialog.getByText("已选择 1 个文件，当前页面月份为 2026-03。确认导入后会刷新当前税金抵扣页。")).toBeVisible();

    await dialog.getByRole("button", { name: "预览识别结果" }).click();
    await expect(dialog.getByRole("region", { name: "已认证发票预览结果" })).toBeVisible();
    await expect(dialog.getByText("识别记录 2 条")).toBeVisible();
    await expect(dialog.getByText("匹配计划 1 条").first()).toBeVisible();
    await expect(dialog.getByRole("grid", { name: "2026年3月 进项认证结果.xlsx 行级预览结果" })).toBeVisible();
    await expect(dialog.getByText("高速通行服务商")).toBeVisible();
    expect(api.count("POST /api/tax-offset/certified-import/preview")).toBe(1);

    const taxOffsetFetchCountBeforeConfirm = api.count("GET /api/tax-offset");
    const confirmResponse = page.waitForResponse((response) =>
      response.url().includes("/api/tax-offset/certified-import/confirm") && response.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "确认导入" }).click();
    expect((await confirmResponse).status()).toBe(200);
    await expect.poll(() => api.count("POST /api/tax-offset/certified-import/confirm")).toBe(1);
    await expect.poll(() => api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetFetchCountBeforeConfirm);
    await expect(page.getByText("已导入 2 条已认证记录，并已刷新当前税金抵扣页面。")).toBeVisible();
    await expect(statCard(page, "已认证结果进项税额").getByText("14,080.00")).toBeVisible();
    await expect(page.getByRole("complementary", { name: "已认证结果" }).getByText("高速通行服务商")).toBeVisible();
  });
});
