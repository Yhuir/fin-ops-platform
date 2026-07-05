import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder, type OperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const CANDIDATES_PATH = "GET /api/oa-pending-payments/bank-transaction-candidates";
const CONFIRM_PAID_PATH = "POST /api/oa-pending-payments/confirm-paid";
const LINK_BANK_PATH = "POST /api/oa-pending-payments/link-bank-transactions";
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

test.describe("OA pending payments in-progress bank link browser flow", () => {
  test("links only unmatched bank transactions and refreshes rows with automatic OA writeback", async ({ page }, testInfo) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentBankLinkDelayMs: 300,
      oaPendingPaymentBankLinkFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await openInProgressView(page, recordLatency);

    const row = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("流程状态：进行中");
    await expect(row).toContainText("待支付");
    await expect(row).toContainText("未写回");
    await expect(page.getByRole("button", { name: "关联支出流水" })).toBeDisabled();

    await recordLatency({
      operationId: "oa-pending-payments.select-in-progress-oa-for-bank-link",
      visibleLabel: "选择 OA 进行中关联申请人",
      actionType: "check",
    }, async (mark) => {
      await row.getByRole("checkbox", { name: /选择 OA 进行中关联申请人/ }).check();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("button", { name: "关联支出流水" })).toBeEnabled());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "关联支出流水" })).toBeEnabled());
    });
    await expect(page.getByRole("button", { name: "关联支出流水" })).toBeEnabled();

    const rowsBeforeLink = api.count(ROWS_PATH);
    const drawer = page.getByLabel("关联支出流水抽屉", { exact: true });
    await recordLatency({
      operationId: "oa-pending-payments.open-bank-link-drawer",
      visibleLabel: "关联支出流水",
      actionType: "click",
    }, async (mark) => {
      const candidatesResponse = page.waitForResponse(responseFor("GET", "/api/oa-pending-payments/bank-transaction-candidates"));
      await page.getByRole("button", { name: "关联支出流水" }).click();
      await mark("apiLatencyMs", candidatesResponse);
      await mark("firstVisibleResponseLatencyMs", expect(drawer.getByRole("heading", { name: "关联支出流水" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByText("显示 3 / 3 条")).toBeVisible());
    });
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
    await recordLatency({
      operationId: "oa-pending-payments.filter-bank-candidates-linked-in-progress",
      visibleLabel: "已关联进行中OA",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("button", { name: "已关联进行中OA" }).click();
      await mark("apiLatencyMs", linkedFilterRequest);
      await mark("finalSettledLatencyMs", expect(drawer.getByText("显示 1 / 1 条")).toBeVisible());
    });
    await expect(drawer.getByText("显示 1 / 1 条")).toBeVisible();
    await expect(drawer.getByText("已关联进行中供应商")).toBeVisible();

    const allFilterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/bank-transaction-candidates")
        && url.searchParams.get("relation_status") === "all";
    });
    await recordLatency({
      operationId: "oa-pending-payments.filter-bank-candidates-all",
      visibleLabel: "全部",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("button", { name: "全部" }).click();
      await mark("apiLatencyMs", allFilterRequest);
      await mark("finalSettledLatencyMs", expect(drawer.getByText("显示 3 / 3 条")).toBeVisible());
    });
    await expect(drawer.getByText("显示 3 / 3 条")).toBeVisible();

    await recordLatency({
      operationId: "oa-pending-payments.select-bank-candidate",
      visibleLabel: "进行中关联供应商",
      actionType: "check",
    }, async (mark) => {
      await drawer.getByRole("checkbox", { name: /进行中关联供应商/ }).check();
      await mark("firstVisibleResponseLatencyMs", expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled());
    });
    await recordLatency({
      operationId: "oa-pending-payments.confirm-bank-link",
      visibleLabel: "确认关联 1 条流水",
      actionType: "click",
    }, async (mark) => {
      const linkResponse = page.waitForResponse(responseFor("POST", "/api/oa-pending-payments/link-bank-transactions"));
      const barrierResponse = page.waitForResponse(responseFor("POST", "/api/operation-barrier/status"));
      const rowsResponse = page.waitForResponse(responseFor("GET", "/api/oa-pending-payments/rows"));
      await drawer.getByRole("button", { name: "确认关联 1 条流水" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(drawer.getByRole("button", { name: "关联中" })).toBeDisabled());
      await mark("apiLatencyMs", linkResponse);
      await mark("operationBarrierLatencyMs", barrierResponse);
      await mark("finalSettledLatencyMs", rowsResponse);
    });
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

  test("keeps bank link failures visible without refreshing rows or writing OA paid status", async ({ page }, testInfo) => {
    const runtimeErrors = collectRuntimeErrors(page);
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentBankLinkError: true,
      oaPendingPaymentBankLinkFlow: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await openInProgressView(page, recordLatency);

    const row = page.getByRole("row", { name: /进行中关联申请人/ });
    await expect(row).toBeVisible();
    await recordLatency({
      operationId: "oa-pending-payments.select-in-progress-oa-for-bank-link-rejected",
      visibleLabel: "选择 OA 进行中关联申请人",
      actionType: "check",
    }, async (mark) => {
      await row.getByRole("checkbox", { name: /选择 OA 进行中关联申请人/ }).check();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "关联支出流水" })).toBeEnabled());
    });
    const rowsBeforeLink = api.count(ROWS_PATH);

    const drawer = page.getByLabel("关联支出流水抽屉", { exact: true });
    await recordLatency({
      operationId: "oa-pending-payments.open-bank-link-drawer-rejected",
      visibleLabel: "关联支出流水",
      actionType: "click",
    }, async (mark) => {
      const candidatesResponse = page.waitForResponse(responseFor("GET", "/api/oa-pending-payments/bank-transaction-candidates"));
      await page.getByRole("button", { name: "关联支出流水" }).click();
      await mark("apiLatencyMs", candidatesResponse);
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("heading", { name: "关联支出流水" })).toBeVisible());
    });
    await recordLatency({
      operationId: "oa-pending-payments.select-bank-candidate-rejected",
      visibleLabel: "进行中关联供应商",
      actionType: "check",
    }, async (mark) => {
      await drawer.getByRole("checkbox", { name: /进行中关联供应商/ }).check();
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled());
    });
    await recordLatency({
      operationId: "oa-pending-payments.confirm-bank-link-rejected",
      visibleLabel: "确认关联 1 条流水",
      actionType: "click",
    }, async (mark) => {
      const linkResponse = page.waitForResponse(responseFor("POST", "/api/oa-pending-payments/link-bank-transactions"));
      await drawer.getByRole("button", { name: "确认关联 1 条流水" }).click();
      await mark("apiLatencyMs", linkResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("alert")).toContainText("支出流水关联校验失败，未创建关联关系。"));
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled());
    });

    await expect(page.getByRole("alert")).toContainText("支出流水关联校验失败，未创建关联关系。");
    await expect(drawer.getByRole("button", { name: "确认关联 1 条流水" })).toBeEnabled();
    expect(api.count(LINK_BANK_PATH)).toBe(1);
    expect(api.lastBody(LINK_BANK_PATH)).toMatchObject({
      oa_row_ids: ["oa-bank-link-e2e-001"],
      bank_transaction_ids: ["bank-link-e2e-001"],
    });
    expect(api.count(CONFIRM_PAID_PATH)).toBe(0);
    expect(api.count(ROWS_PATH)).toBe(rowsBeforeLink);

    await recordLatency({
      operationId: "oa-pending-payments.close-bank-link-drawer-after-rejection",
      visibleLabel: "关闭关联支出流水抽屉",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭关联支出流水抽屉" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "关联支出流水" })).toHaveCount(0));
    });
    await expect(row).toContainText("待支付");
    await expect(row).toContainText("未写回");
    await expect(row).not.toContainText("进行中关联供应商");
    expect(unexpectedRuntimeErrors(runtimeErrors, [/409 \(Conflict\)/])).toEqual([]);
  });
});
