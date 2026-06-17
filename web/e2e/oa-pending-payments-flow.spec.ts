import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

function filtersFromRequest(requestUrl: string) {
  const value = new URL(requestUrl).searchParams.get("filters") ?? "[]";
  return JSON.parse(decodeURIComponent(value)) as Array<{
    field: string;
    operator: string;
    values?: string[];
  }>;
}

test.describe("OA pending payments browser flow", () => {
  test("filters, sorts, and opens OA, bank, invoice, and rules drawers", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "OA 待付款核对" })).toBeVisible();
    await expect(page.getByRole("table", { name: "OA待付款核对表格" })).toBeVisible();

    const row = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("浏览器待付款项目");
    await expect(row).toContainText("支付少了");
    await expect(row).toContainText("浏览器待付款供应商");
    await expect(row).toContainText("INV-PAY-E2E-001");
    await expect(row).toContainText("建设银行 1234");
    await expect(row).toContainText("8000.00");
    await expect(row).toContainText("12000.00");
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/oa-pending-payments/filter-options")).toBeGreaterThanOrEqual(1);

    const searchRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("keyword") === "浏览器付款申请人";
    });
    await page.getByLabel("搜索OA待付款核对").fill("浏览器付款申请人");
    await page.getByRole("button", { name: "查询" }).click();
    expect(new URL((await searchRequest).url()).searchParams.get("page_size")).toBe("20");

    await page.getByRole("button", { name: "筛选 支付状态" }).click();
    await page.getByRole("menuitemcheckbox", { name: "支付状态：支付少了 1" }).click();
    const filterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && (url.searchParams.get("filters") ?? "").includes("partially_paid");
    });
    await page.getByRole("button", { name: "应用筛选" }).click();
    expect(filtersFromRequest((await filterRequest).url())).toContainEqual({
      field: "payment_status",
      operator: "in",
      values: ["partially_paid"],
    });

    const sortRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("sort_field") === "bank_trade_time";
    });
    await page.getByRole("button", { name: "交易时间 排序" }).click();
    expect(new URL((await sortRequest).url()).searchParams.get("sort_direction")).toBe("desc");

    await row.getByRole("button", { name: "查看 OA 浏览器付款申请人 详情" }).click();
    await expect(page.getByRole("heading", { name: "OA详情" })).toBeVisible();
    await expect(page.getByText("浏览器待付款项目").last()).toBeVisible();
    await page.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(page.getByRole("heading", { name: "OA详情" })).toHaveCount(0);

    await row.getByRole("button", { name: "查看流水 浏览器付款申请人 详情" }).click();
    await expect(page.getByRole("heading", { name: "支出流水详情" })).toBeVisible();
    await expect(page.getByText("支出银行")).toBeVisible();
    await expect(page.getByText("8000.00").last()).toBeVisible();
    await page.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(page.getByRole("heading", { name: "支出流水详情" })).toHaveCount(0);

    await row.getByRole("button", { name: "查看发票 浏览器付款申请人 详情" }).click();
    await expect(page.getByRole("heading", { name: "发票详情" })).toBeVisible();
    await expect(page.getByText("进项发票方名称")).toBeVisible();
    await expect(page.getByText("INV-PAY-E2E-001").last()).toBeVisible();
    await page.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(page.getByRole("heading", { name: "发票详情" })).toHaveCount(0);

    await page.getByRole("button", { name: "支出流水无需开票规则设置" }).click();
    await expect(page.getByRole("heading", { name: "支出流水无需开票规则设置" })).toBeVisible();
    expect(api.count("GET /api/pending-invoices/rules")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/oa/oa-payment-e2e-001/detail")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/bank-transactions/bank-payment-e2e-001/detail")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/invoices/invoice-payment-e2e-001/detail")).toBe(1);
  });
});
