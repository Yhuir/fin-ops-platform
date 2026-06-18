import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("workbench relation candidate semantics", () => {
  test("keeps candidate invoice evidence out of linked-only pending invoice state", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceCandidateRelations: true,
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRow).toBeVisible();
    await expect(bankRow.getByText("候选oa")).toBeVisible();
    await expect(bankRow.getByText("候选发票")).toBeVisible();
    await expect(bankRow.getByText("有oa")).toHaveCount(0);
    await expect(bankRow.getByText("有发票")).toHaveCount(0);

    await page.getByRole("link", { name: "待找发票" }).click();
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    const pendingRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRow).toBeVisible();
    await expect(pendingRow.locator(".pending-invoices-col-status .finance-status-tag")).toHaveText("已支付待开票");
    await expect(pendingRow.getByText("候选")).toHaveCount(2);
    await expect(pendingRow.getByText("12561048")).toBeVisible();
    await expect(pendingRow.getByText("陈涛")).toBeVisible();
    await expect(pendingRow.getByText("已支付已开票")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(0);
  });

  test("keeps candidate payment relations in partially paid state until explicit confirmation", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentCandidateRelations: true,
      sessionMode: "full_access",
    });

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    const row = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("候选")).toHaveCount(3);
    await expect(row.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("支付少了");
    await expect(row.getByRole("button", { name: "确认已支付" })).toBeVisible();
    await expect(row).toContainText("浏览器待付款供应商");
    await expect(row).toContainText("INV-PAY-E2E-001");
    expect(api.count("POST /api/oa-pending-payments/actions/confirm-paid")).toBe(0);
  });
});
