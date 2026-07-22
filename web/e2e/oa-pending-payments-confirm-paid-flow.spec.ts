import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder, type OperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const WRITEBACK_PAID_PATH = "POST /api/oa-pending-payments/writeback-paid";
const ROWS_PATH = "GET /api/oa-pending-payments/rows";

function createOaPendingLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    module: "oa-pending-payments",
  });
}

function responseFor(method: string, pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === method && new URL(response.url()).pathname.endsWith(pathname);
}

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

async function openInProgressView(page: Page, recordLatency?: OperationLatencyRecorder) {
  await page.goto("/oa-pending-payments");
  await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();

  await recordLatency?.({
    operationId: "oa-pending-payments.switch-in-progress-view",
    visibleLabel: "进行中 OA",
    actionType: "click",
  }, async (mark) => {
    const inProgressRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("view_mode") === "in_progress";
    });
    await page.getByRole("button", { name: /进行中 OA/ }).click();
    await mark("apiLatencyMs", inProgressRequest);
    await mark("firstVisibleResponseLatencyMs", expect(page.getByText("流程状态：进行中").first()).toBeVisible());
    await mark("finalSettledLatencyMs", expect(page.getByText("流程状态：进行中").first()).toBeVisible());
  });
  if (!recordLatency) {
    const inProgressRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("view_mode") === "in_progress";
    });
    await page.getByRole("button", { name: /进行中 OA/ }).click();
    await inProgressRequest;
  }
}

test.describe("OA pending payments in-progress paid writeback browser flow", () => {
  test("writes back a paid in-progress OA payment once and refreshes the writeback read model", async ({ page }, testInfo) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentWritebackPaidDelayMs: 300,
      oaPendingPaymentWritebackPaidFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await openInProgressView(page, recordLatency);

    const row = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("流程状态：进行中");
    await expect(row).toContainText("已支付");
    await expect(row).toContainText("进行中写回供应商");
    await expect(row).toContainText("9800.00");
    await expect(row.getByRole("button", { name: "写回 OA 进行中付款申请人" })).toBeVisible();
    await expect(page.getByRole("button", { name: "自动匹配并写回 OA 待付款" })).toHaveCount(0);

    const rowsBeforeWriteback = api.count(ROWS_PATH);
    const barriersBeforeWriteback = api.count("POST /api/operation-barrier/status");
    expect(api.count(WRITEBACK_PAID_PATH)).toBe(0);
    const writebackResponse = page.waitForResponse(responseFor("POST", "/api/oa-pending-payments/writeback-paid"));
    await recordLatency({
      operationId: "oa-pending-payments.writeback-paid",
      visibleLabel: "写回 OA 进行中付款申请人",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "写回 OA 进行中付款申请人" }).click();
      await mark("apiLatencyMs", writebackResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("已写回 1 条 OA。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /进行中付款申请人/ })).toContainText("已写回"));
    });
    await expect.poll(() => api.count(WRITEBACK_PAID_PATH)).toBe(1);
    expect(api.lastBody(WRITEBACK_PAID_PATH)).toMatchObject({
      oa_row_ids: ["oa-writeback-paid-e2e-001"],
    });

    await expect(page.getByText("已写回 1 条 OA。")).toBeVisible();

    const refreshedRow = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(refreshedRow).toContainText("已写回");
    expect(api.count(ROWS_PATH)).toBeGreaterThanOrEqual(rowsBeforeWriteback);
    await expect(refreshedRow.getByRole("button", { name: /确认已支付并写回|写回 OA/ })).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count(WRITEBACK_PAID_PATH)).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(barriersBeforeWriteback);
    expect(unexpectedRuntimeErrors(runtimeErrors)).toEqual([]);
  });

  test("keeps the row unmodified when paid writeback is rejected", async ({ page }, testInfo) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentWritebackPaidDelayMs: 300,
      oaPendingPaymentWritebackPaidError: true,
      oaPendingPaymentWritebackPaidFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await openInProgressView(page, recordLatency);

    const row = page.getByRole("row", { name: /进行中付款申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("未写回");
    await expect(row.getByRole("button", { name: "写回 OA 进行中付款申请人" })).toBeVisible();
    const rowsBeforeWriteback = api.count(ROWS_PATH);

    expect(api.count(WRITEBACK_PAID_PATH)).toBe(0);
    const writebackResponse = page.waitForResponse(responseFor("POST", "/api/oa-pending-payments/writeback-paid"));
    await recordLatency({
      operationId: "oa-pending-payments.writeback-paid-rejected",
      visibleLabel: "写回 OA 进行中付款申请人",
      actionType: "click",
    }, async (mark) => {
      await row.getByRole("button", { name: "写回 OA 进行中付款申请人" }).click();
      await mark("apiLatencyMs", writebackResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("OA 写回校验失败，未写入支付状态。"));
      await mark("finalSettledLatencyMs", expect(row).toContainText("未写回"));
    });
    await expect.poll(() => api.count(WRITEBACK_PAID_PATH)).toBe(1);
    await expect(page.getByRole("alert")).toContainText("OA 写回校验失败，未写入支付状态。");
    expect(api.lastBody(WRITEBACK_PAID_PATH)).toMatchObject({
      oa_row_ids: ["oa-writeback-paid-e2e-001"],
    });
    expect(api.count(ROWS_PATH)).toBe(rowsBeforeWriteback);
    await expect(row).toContainText("未写回");
    await expect(row).not.toContainText("已写回");
    expect(unexpectedRuntimeErrors(runtimeErrors, [/409 \(Conflict\)/])).toEqual([]);
  });
});
