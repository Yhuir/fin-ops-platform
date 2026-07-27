import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const DEFAULT_DATE_FROM = "2026-01-01";
const DEFAULT_DATE_TO = "2026-12-31";

function defaultAccountsRequest(url: URL) {
  return url.pathname.endsWith("/api/bank-details/accounts")
    && url.searchParams.get("date_from") === DEFAULT_DATE_FROM
    && url.searchParams.get("date_to") === DEFAULT_DATE_TO;
}

function defaultTransactionsRequest(url: URL) {
  return url.pathname.endsWith("/api/bank-details/transactions")
    && url.searchParams.get("date_from") === DEFAULT_DATE_FROM
    && url.searchParams.get("date_to") === DEFAULT_DATE_TO
    && url.searchParams.get("account_key") === null
    && url.searchParams.get("page") === "1"
    && url.searchParams.get("page_size") === "100";
}

test.describe("bank details initial browser state", () => {
  test("loads the current-year all-account view with balances, default columns, and relation fields", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    const accountsRequest = page.waitForRequest((request) => (
      request.method() === "GET" && defaultAccountsRequest(new URL(request.url()))
    ));
    const transactionsRequest = page.waitForRequest((request) => (
      request.method() === "GET" && defaultTransactionsRequest(new URL(request.url()))
    ));

    await page.goto("/bank-details");
    await accountsRequest;
    await transactionsRequest;

    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "全部流水" })).toBeVisible();
    await expect(page.getByRole("button", { name: /时间选择 2026年/ })).toBeVisible();

    await expect(page.getByText("总余额")).toBeVisible();
    await expect(page.getByText("130,500.50").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /全部流水 1 条/ })).toHaveAttribute("aria-current", "true");
    await expect(page.getByRole("button", { name: /建设银行 1138 余额 130,500.50 1 条/ })).toBeVisible();

    const grid = page.getByRole("grid", { name: "交易流水" });
    await expect(grid).toBeVisible();
    await expect(grid.getByRole("columnheader")).toHaveText([
      "对方户名",
      "类型",
      "金额",
      "余额",
      "用途/交易用途",
      "摘要",
      "备注/附言/客户附言",
    ]);

    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow).toBeVisible();
    await expect(bankRow.getByText("2026-03-28 10:18:00")).toBeVisible();
    await expect(bankRow.getByText("无oa")).toBeVisible();
    await expect(bankRow.getByText("无发票")).toBeVisible();
    await expect(bankRow.getByText("设备款")).toBeVisible();
    await expect(bankRow.getByText("58,000.00")).toBeVisible();
    await expect(bankRow.getByText("建设银行 1138")).toBeVisible();
    await expect(bankRow.getByText("130,500.50")).toBeVisible();
    await expect(bankRow.getByText("设备尾款", { exact: true })).toBeVisible();
    await expect(bankRow.getByText("设备尾款待进项票")).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).not.toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();
  });

  test("shows a true empty state only when the fresh transaction result is empty", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      bankDetailsTransactionsEmpty: true,
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    await expect(page.getByText("总余额")).toBeVisible();
    await expect(page.getByText("130,500.50").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /建设银行 1138 余额 130,500.50 1 条/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "交易流水" })).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();
    await expect(page.getByText("银行明细正在刷新，暂时显示当前可用数据。")).not.toBeVisible();
    await expect(page.getByText("银行明细待刷新，暂时显示当前可用数据。")).not.toBeVisible();
    await expect(page.getByText("银行明细读模型正在初始化，暂时显示当前可用数据。")).not.toBeVisible();
  });
});
