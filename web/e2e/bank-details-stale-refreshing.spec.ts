import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("bank details direct payload browser behavior", () => {
  test("renders direct bank rows without page-level read model diagnostics", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow.getByText("设备款")).toBeVisible();
    await expect(bankRow.getByText("候选oa")).toBeVisible();
    await expect(page.getByText("银行明细正在刷新，暂时显示当前可用数据。")).toHaveCount(0);
    await expect(page.getByText("银行明细读模型正在初始化，暂时显示当前可用数据。")).toHaveCount(0);
    await expect(page.getByText("当前时间范围内没有流水。")).not.toBeVisible();
  });

  test("treats direct empty transaction rows as an empty result and still exports", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      bankDetailsTransactionsEmpty: true,
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expect(exportMenu).toBeVisible();

    const exportResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/bank-details/transactions/export");
    });
    await exportMenu.getByRole("menuitem", { name: "导出全部银行" }).click();

    expect((await exportResponse).status()).toBe(200);
    expect(api.count("GET /api/bank-details/transactions/export")).toBe(1);
    await expect(page.getByText("银行明细正在刷新，请稍后重试导出。")).toHaveCount(0);
  });

  test("recovers transaction rows after a transient network failure and user retry", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
    const stableTransactionRequests = api.count("GET /api/bank-details/transactions");

    api.failNextBankDetailsTransactions();
    await page.getByRole("textbox", { name: "搜索流水" }).fill("设备尾款");

    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThan(stableTransactionRequests);
    await expect(page.getByRole("alert")).toContainText("银行流水暂时无法加载，请稍后重试。");
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();

    await page.getByRole("textbox", { name: "搜索流水" }).fill("智能工厂");

    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThan(stableTransactionRequests + 1);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible();
  });
});
