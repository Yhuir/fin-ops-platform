import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("workbench relation non-fresh diagnostics", () => {
  test("keeps pending invoice rows inspectable while relation-backed data is refreshing", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      pendingInvoiceReadModelStatus: "refreshing",
      sessionMode: "full_access",
    });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expect(page.getByText("数据刷新中")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("已支付待开票")).toBeVisible();
    await row.getByRole("checkbox", { name: "选择流水 智能工厂设备商" }).check();
    await expect(page.getByRole("button", { name: "选择发票" })).toBeEnabled();
  });

  test("surfaces stale diagnostics instead of silently treating empty relation-backed rows as true empty", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      pendingInvoiceReadModelStatus: "stale",
      pendingInvoiceRowsEmpty: true,
      sessionMode: "full_access",
    });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expect(page.getByText("读模型 stale，写入和导出已暂停")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    await expect(page.getByText("当前条件下没有待找发票流水。")).toBeVisible();
  });
});
