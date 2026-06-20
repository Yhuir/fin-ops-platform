import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const CONFIRM_PAID_PATH = "POST /api/oa-pending-payments/confirm-paid";
const ROWS_PATH = "GET /api/oa-pending-payments/rows";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    errors.push(error.message);
  });
  return errors;
}

function unexpectedRuntimeErrors(errors: string[], allowed: RegExp[] = []) {
  return errors.filter((error) => !allowed.some((pattern) => pattern.test(error)));
}

async function openInProgressView(page: Page) {
  await page.goto("/oa-pending-payments");
  await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();

  const inProgressRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/api/oa-pending-payments/rows")
      && url.searchParams.get("view_mode") === "in_progress";
  });
  await page.getByRole("button", { name: /进行中 OA/ }).click();
  await inProgressRequest;
}

test.describe("OA pending payments in-progress confirm-paid browser flow", () => {
  test("confirms an eligible in-progress OA payment once and refreshes the writeback read model", async ({ page }) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentConfirmPaidDelayMs: 300,
      oaPendingPaymentConfirmPaidFlow: true,
      sessionMode: "full_access",
    });

    await openInProgressView(page);

    const row = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("流程状态：进行中");
    await expect(row).toContainText("已支付");
    await expect(row).toContainText("未写回");
    await expect(row).toContainText("进行中写回供应商");
    await expect(row).toContainText("9800.00");

    const rowsBeforeConfirm = api.count(ROWS_PATH);
    await row.getByRole("button", { name: "确认已支付并写回" }).click();
    await expect(row.getByRole("button", { name: "确认中" })).toBeDisabled();
    await expect.poll(() => api.count(CONFIRM_PAID_PATH)).toBe(1);
    expect(api.lastBody(CONFIRM_PAID_PATH)).toMatchObject({
      oa_row_id: "oa-confirm-paid-e2e-001",
      bank_transaction_ids: ["bank-confirm-paid-e2e-001"],
    });

    await expect(page.getByText("已确认支付并写回 OA。")).toBeVisible();
    await expect.poll(() => api.count(ROWS_PATH)).toBeGreaterThan(rowsBeforeConfirm);

    const refreshedRow = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(refreshedRow).toContainText("已写回");
    await expect(refreshedRow.getByRole("button", { name: /确认已支付并写回|写回 OA/ })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count(CONFIRM_PAID_PATH)).toBe(1);
    expect(unexpectedRuntimeErrors(runtimeErrors)).toEqual([]);
  });

  test("keeps the row unmodified when confirm-paid is rejected", async ({ page }) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentConfirmPaidError: true,
      oaPendingPaymentConfirmPaidFlow: true,
      sessionMode: "full_access",
    });

    await openInProgressView(page);

    const row = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("未写回");
    const rowsBeforeConfirm = api.count(ROWS_PATH);

    await row.getByRole("button", { name: "确认已支付并写回" }).click();
    await expect(page.getByRole("alert")).toContainText("OA 写回校验失败，未写入支付状态。");
    await expect(row.getByRole("button", { name: "确认已支付并写回" })).toBeEnabled();

    expect(api.count(CONFIRM_PAID_PATH)).toBe(1);
    expect(api.lastBody(CONFIRM_PAID_PATH)).toMatchObject({
      oa_row_id: "oa-confirm-paid-e2e-001",
      bank_transaction_ids: ["bank-confirm-paid-e2e-001"],
    });
    expect(api.count(ROWS_PATH)).toBe(rowsBeforeConfirm);
    await expect(row).toContainText("未写回");
    await expect(row).not.toContainText("已写回");
    expect(unexpectedRuntimeErrors(runtimeErrors, [/409 \(Conflict\)/])).toEqual([]);
  });
});
