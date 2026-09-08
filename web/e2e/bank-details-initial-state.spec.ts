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
  test("shows confirmed bank order, historical balances and unresolved evidence without a false total", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    await page.route("**/api/bank-details/accounts?*", (route) => route.fulfill({ json: {
      accounts: [
        { account_key: "ccb", bank_name: "建设银行", account_last4: "8106", display_name: "建设银行 8106", currency: "CNY",
          latest_balance: "40512.82", latest_balance_at: "2026-09-08 15:36:50", has_balance: true, balance_status: "confirmed", transaction_count: 2 },
        { account_key: "history", bank_name: "历史银行", account_last4: "1002", display_name: "历史银行 1002", currency: "CNY",
          latest_balance: "60371.45", latest_balance_at: "2026-09-03 17:16:44", has_balance: true, balance_status: "last_known", transaction_count: 1 },
        { account_key: "unknown", bank_name: "待核银行", account_last4: "1003", display_name: "待核银行 1003", currency: null,
          latest_balance: null, latest_balance_at: null, has_balance: false, balance_status: "unresolved", transaction_count: 1 },
      ],
      total_balance: null, total_balances_by_currency: {}, balance_account_count: 2, missing_balance_account_count: 1,
    } }));
    await page.route("**/api/bank-details/transactions?*", (route) => route.fulfill({ json: {
      rows: [
        { id: "payment", trade_time: "2026-09-08 15:36:50", same_time_order_status: "balance_chain", counterparty_name: "转账收款方",
          direction: "expense", direction_label: "支", amount: "54000.00", balance: "40512.82", summary: "转账", purpose: "", bank_name: "建设银行", account_last4: "8106" },
        { id: "fee", trade_time: "2026-09-08 15:36:50", same_time_order_status: "balance_chain", counterparty_name: "银行手续费",
          direction: "expense", direction_label: "支", amount: "1.00", balance: "94512.82", summary: "手续费", purpose: "", bank_name: "建设银行", account_last4: "8106" },
        { id: "unknown", trade_time: "2026-09-03", same_time_order_status: "unresolved", counterparty_name: "待核实对方",
          direction: "expense", direction_label: "支", amount: "2.00", balance: null, summary: "日期来源", purpose: "", bank_name: "待核银行", account_last4: "1003" },
      ],
      pagination: { page: 1, page_size: 100, total: 3 }, category_counts: { uncategorized: 3 },
    } }));
    await page.goto("/bank-details");
    await expect(page.getByText("暂无法确定完整总余额")).toBeVisible();
    await expect(page.locator(".bank-total-balance")).toHaveText("—");
    await expect(page.getByText("最后已知余额 · 2026-09-03")).toBeVisible();
    await expect(page.getByText("余额待核实")).toBeVisible();
    const rows = page.getByRole("grid", { name: "交易流水" }).getByRole("row");
    await expect(rows.nth(1)).toContainText("转账收款方");
    await expect(rows.nth(1)).toContainText("40512.82");
    await expect(rows.nth(2)).toContainText("银行手续费");
    await expect(rows.nth(2)).toContainText("94512.82");
    await expect(page.getByText("2026-09-03", { exact: true })).toBeVisible();
    await expect(rows.nth(3).locator(".bank-col-balance")).toHaveText("—");
    const warning = page.getByLabel("同时间顺序待核实");
    await expect(warning).toHaveCount(1);
    await warning.hover();
    await expect(page.getByRole("tooltip")).toContainText("请通过导入来源核对原银行明细");
    await page.getByRole("heading", { name: "银行明细", exact: true }).hover();
    await warning.focus();
    await expect(page.getByRole("tooltip")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("loads the current-year all-account view with balances, default columns, and relation fields", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

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
    await expect(page.getByRole("button", { name: "银行明细时间范围：2026年" })).toBeVisible();

    await expect(page.getByText("总余额")).toBeVisible();
    await expect(page.getByText("130500.50").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /全部流水 1 条/ })).toHaveAttribute("aria-current", "true");
    await expect(page.getByRole("button", { name: /建设银行 1138 余额 130500.50 1 条/ })).toBeVisible();

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
    await expect(bankRow.getByText("58000.00")).toBeVisible();
    await expect(bankRow.getByText("建设银行 1138")).toBeVisible();
    await expect(bankRow.getByText("130500.50")).toBeVisible();
    await expect(bankRow.getByText("设备尾款", { exact: true })).toBeVisible();
    await expect(bankRow.getByText("设备尾款待进项票")).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).not.toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();
  });

  test("shows a true empty state only when the fresh transaction result is empty", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      bankDetailsTransactionsEmpty: true,
      sessionMode: "user",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    await expect(page.getByText("总余额")).toBeVisible();
    await expect(page.getByText("130500.50").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /建设银行 1138 余额 130500.50 1 条/ })).toBeVisible();
    await expect(page.getByRole("grid", { name: "交易流水" })).toBeVisible();
    await expect(page.getByText("当前时间范围内没有流水。")).toBeVisible();
    await expect(page.getByText("暂无银行流水，请先在银行流水导入页面导入。")).not.toBeVisible();
    await expect(page.getByText("银行明细正在刷新，暂时显示当前可用数据。")).not.toBeVisible();
    await expect(page.getByText("银行明细待刷新，暂时显示当前可用数据。")).not.toBeVisible();
    await expect(page.getByText("银行明细读模型正在初始化，暂时显示当前可用数据。")).not.toBeVisible();
  });
});
