import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("pending invoice canonical read states", () => {
  test("loads canonical rows once without read-model diagnostics or polling", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeEnabled();
    await expect(page.getByText(/数据刷新中|读模型 stale/)).toHaveCount(0);
    const settledRequestCount = api.count("GET /api/pending-invoices/rows");
    expect(settledRequestCount).toBeGreaterThan(0);
    await page.waitForTimeout(500);
    expect(api.count("GET /api/pending-invoices/rows")).toBe(settledRequestCount);
  });

  test("treats a successful canonical zero-row response as a true empty set", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      pendingInvoiceRowsEmpty: true,
      sessionMode: "full_access",
    });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expect(page.getByText("当前条件下没有待找发票流水。")).toBeVisible();
    await expect(page.getByText(/数据刷新中|读模型 stale/)).toHaveCount(0);
  });
});
