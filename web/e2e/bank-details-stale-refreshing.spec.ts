import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("bank details direct canonical query browser behavior", () => {
  test("loads rows once without legacy freshness polling", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();

    const accountReads = api.count("GET /api/bank-details/accounts");
    const transactionReads = api.count("GET /api/bank-details/transactions");
    await page.waitForTimeout(1_200);

    expect(api.count("GET /api/bank-details/accounts")).toBe(accountReads);
    expect(api.count("GET /api/bank-details/transactions")).toBe(transactionReads);
  });

  test("treats a direct empty transaction response as the real empty state", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      bankDetailsTransactionsEmpty: true,
      sessionMode: "user",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();
  });

  test("recovers transaction rows after a transient network failure and user retry", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    const stableTransactionRequests = api.count("GET /api/bank-details/transactions");

    api.failNextBankDetailsTransactions();
    await page.getByRole("searchbox", { name: "搜索流水" }).fill("设备尾款");
    await page.getByRole("button", { name: "查询", exact: true }).click();

    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThan(stableTransactionRequests);
    await expect(page.getByRole("alert")).toContainText("银行流水暂时无法加载，请稍后重试。");
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();

    await page.getByRole("searchbox", { name: "搜索流水" }).fill("智能工厂");
    await page.getByRole("button", { name: "查询", exact: true }).click();

    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThan(stableTransactionRequests + 1);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).not.toBeVisible();
  });
});
