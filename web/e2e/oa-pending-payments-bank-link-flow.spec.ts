import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const CANDIDATES_PATH = "GET /api/oa-pending-payments/bank-transaction-candidates";
const CONFIRM_PAID_PATH = "POST /api/oa-pending-payments/confirm-paid";
const LINK_BANK_PATH = "POST /api/oa-pending-payments/link-bank-transactions";
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

test.describe("OA pending payments in-progress bank link browser flow", () => {
  test("links only unmatched bank transactions and refreshes rows with automatic OA writeback", async ({ page }) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentBankLinkDelayMs: 300,
      oaPendingPaymentBankLinkFlow: true,
      sessionMode: "full_access",
    });

    await openInProgressView(page);

    const row = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("流程状态：进行中");
    await expect(row).toContainText("待支付");
    await expect(row).toContainText("未写回");
    await expect(page.getByRole("button", { name: "关联支出流水" })).toBeDisabled();

    await row.getByRole("checkbox", { name: /选择 OA 进行中关联申请人/ }).check();
    await expect(page.getByRole("button", { name: "关联支出流水" })).toBeEnabled();

    const rowsBeforeLink = api.count(ROWS_PATH);
    await page.getByRole("button", { name: "关联支出流水" }).click();
    const drawer = page.getByLabel("关联支出流水抽屉", { exact: true });
    await expect(drawer.getByRole("heading", { name: "关联支出流水" })).toBeVisible();
    await expect.poll(() => api.count(CANDIDATES_PATH)).toBe(1);
    expect(new URL(page.url()).pathname).toBe("/oa-pending-payments");

    await expect(drawer.getByText("显示 3 / 3 条")).toBeVisible();
    await expect(drawer.getByText("进行中关联供应商")).toBeVisible();
    await expect(drawer.getByRole("checkbox", { name: /已配对供应商/ })).toBeDisabled();
    await expect(drawer.getByRole("checkbox", { name: /已关联进行中供应商/ })).toBeDisabled();

    const linkedFilterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/bank-transaction-candidates")
        && url.searchParams.get("relation_status") === "linked_in_progress";
    });
    await drawer.getByRole("button", { name: "已关联进行中OA" }).click();
    await linkedFilterRequest;
    await expect(drawer.getByText("显示 1 / 1 条")).toBeVisible();
    await expect(drawer.getByText("已关联进行中供应商")).toBeVisible();

    const allFilterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/bank-transaction-candidates")
        && url.searchParams.get("relation_status") === "all";
    });
    await drawer.getByRole("button", { name: "全部" }).click();
    await allFilterRequest;
    await expect(drawer.getByText("显示 3 / 3 条")).toBeVisible();

    await drawer.getByRole("checkbox", { name: /进行中关联供应商/ }).check();
    await drawer.getByRole("button", { name: "确认关联 1 条流水" }).click();
    await expect(drawer.getByRole("button", { name: "关联中" })).toBeDisabled();
    await expect.poll(() => api.count(LINK_BANK_PATH)).toBe(1);
    expect(api.lastBody(LINK_BANK_PATH)).toMatchObject({
      oa_row_ids: ["oa-bank-link-e2e-001"],
      bank_transaction_ids: ["bank-link-e2e-001"],
    });

    await expect(page.getByText("已关联支出流水并写回 OA，等待核对表刷新。")).toBeVisible();
    await expect(page.getByRole("heading", { name: "关联支出流水" })).toHaveCount(0);
    await expect.poll(() => api.count(ROWS_PATH)).toBeGreaterThan(rowsBeforeLink);

    const refreshedRow = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(refreshedRow).toContainText("进行中关联供应商");
    await expect(refreshedRow).toContainText("已支付");
    await expect(refreshedRow).toContainText("已写回");
    await expect(refreshedRow.getByRole("button", { name: /确认已支付并写回|写回 OA/ })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count(CONFIRM_PAID_PATH)).toBe(0);
    expect(unexpectedRuntimeErrors(runtimeErrors)).toEqual([]);
  });

  test("keeps bank link failures visible without refreshing rows or writing OA paid status", async ({ page }) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentBankLinkError: true,
      oaPendingPaymentBankLinkFlow: true,
      sessionMode: "full_access",
    });

    await openInProgressView(page);

    const row = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(row).toBeVisible();
    await row.getByRole("checkbox", { name: /选择 OA 进行中关联申请人/ }).check();
    const rowsBeforeLink = api.count(ROWS_PATH);

    await page.getByRole("button", { name: "关联支出流水" }).click();
    const drawer = page.getByLabel("关联支出流水抽屉", { exact: true });
    await expect(drawer.getByRole("heading", { name: "关联支出流水" })).toBeVisible();
    await drawer.getByRole("checkbox", { name: /进行中关联供应商/ }).check();
    await drawer.getByRole("button", { name: "确认关联 1 条流水" }).click();

    await expect(page.getByRole("alert")).toContainText("支出流水关联校验失败，未创建关联关系。");
    await expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled();
    expect(api.count(LINK_BANK_PATH)).toBe(1);
    expect(api.lastBody(LINK_BANK_PATH)).toMatchObject({
      oa_row_ids: ["oa-bank-link-e2e-001"],
      bank_transaction_ids: ["bank-link-e2e-001"],
    });
    expect(api.count(CONFIRM_PAID_PATH)).toBe(0);
    expect(api.count(ROWS_PATH)).toBe(rowsBeforeLink);

    await page.getByRole("button", { name: "关闭关联支出流水抽屉" }).click();
    await expect(row).toContainText("待支付");
    await expect(row).toContainText("未写回");
    await expect(row).not.toContainText("进行中关联供应商");
    expect(unexpectedRuntimeErrors(runtimeErrors, [/409 \(Conflict\)/])).toEqual([]);
  });
});
