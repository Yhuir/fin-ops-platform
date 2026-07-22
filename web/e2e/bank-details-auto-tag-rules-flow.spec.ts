import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder, type OperationLatencyRecorder } from "./fixtures/operationLatency";
import { gotoAndExpectPageReady } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const SAVE_RULES_PATH = "PUT /api/bank-details/auto-tag-rules";
const REAPPLY_RULES_PATH = "POST /api/bank-details/auto-tag-rules/reapply";
const OPERATION_BARRIER_PATH = "POST /api/operation-barrier/status";
const TRANSACTIONS_PATH = "GET /api/bank-details/transactions";

function createBankDetailsLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/bank-details",
    pageKey: "bank-details",
    module: "bank-details",
  });
}

function responseFor(method: "POST" | "PUT", pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) => {
    const url = new URL(response.url());
    return response.request().method() === method && url.pathname === pathname;
  };
}

async function openAutoTagRulesDrawer(page: Page, recordLatency?: OperationLatencyRecorder) {
  const drawer = page.getByRole("dialog", { name: "自动标签规则" });
  const open = async () => {
    await page.getByRole("button", { name: /自动标签规则/ }).click();
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("table", { name: "自动标签规则表格" })).toBeVisible();
  };
  if (recordLatency) {
    await recordLatency({
      operationId: "bank-details.open-auto-tag-rules-drawer",
      visibleLabel: "自动标签规则",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: /自动标签规则/ }).click();
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("table", { name: "自动标签规则表格" })).toBeVisible());
    });
  } else {
    await open();
  }
  return drawer;
}

function barrierTargets(body: Record<string, unknown>) {
  return Array.isArray(body.targets) ? body.targets : [];
}

test.describe("bank details auto tag rules browser flow", () => {
  test("saves edited automatic tag rules and reloads visible rows without an operation barrier", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");
    const initialTransactionRequests = api.count(TRANSACTIONS_PATH);

    const drawer = await openAutoTagRulesDrawer(page, recordLatency);
    await recordLatency({
      operationId: "bank-details.fill-auto-tag-salary-sub-label",
      visibleLabel: "费用 / 工资 子标签",
      actionType: "fill",
    }, async (mark) => {
      const input = drawer.getByRole("textbox", { name: "费用 / 工资 子标签" });
      await input.fill("规则刷新测试");
      await mark("firstVisibleResponseLatencyMs", expect(drawer.getByRole("button", { name: "保存" })).toBeEnabled());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "保存" })).toBeEnabled());
    });
    await expect(drawer.getByRole("button", { name: "保存" })).toBeEnabled();

    await recordLatency({
      operationId: "bank-details.save-auto-tag-rules",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(responseFor("PUT", "/api/bank-details/auto-tag-rules"));
      await drawer.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("规则已保存。").first()).toBeVisible());
      await mark("finalSettledLatencyMs", expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests));
    });

    await expect.poll(() => api.count(SAVE_RULES_PATH)).toBe(1);
    const saveBody = api.lastBody(SAVE_RULES_PATH);
    expect(saveBody).toEqual(expect.objectContaining({
      expected_version: 1,
      refresh_scope: {
        date_from: "2026-01-01",
        date_to: "2026-12-31",
      },
    }));
    const activeRules = Array.isArray(saveBody.active_rules) ? saveBody.active_rules : [];
    expect(activeRules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        code: "salary",
        output_primary_label: "费用",
        output_sub_label: "规则刷新测试",
        priority: 3,
        rules: expect.objectContaining({
          contains_any: ["工资"],
        }),
      }),
    ]));
    expect(activeRules).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ code: "internal_transfer" }),
    ]));

    expect(api.count(OPERATION_BARRIER_PATH)).toBe(0);
    await expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests);
    await expect(page.getByText("规则已保存。").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("reapplies existing automatic tag rules without saving a draft and refreshes bank detail rows", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");
    const initialTransactionRequests = api.count(TRANSACTIONS_PATH);

    const drawer = await openAutoTagRulesDrawer(page, recordLatency);
    await expect(drawer.getByRole("button", { name: "保存" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "重新应用规则" })).toBeEnabled();

    await recordLatency({
      operationId: "bank-details.reapply-auto-tag-rules",
      visibleLabel: "重新应用规则",
      actionType: "click",
    }, async (mark) => {
      const reapplyResponse = page.waitForResponse(responseFor("POST", "/api/bank-details/auto-tag-rules/reapply"));
      const barrierResponse = page.waitForResponse(responseFor("POST", "/api/operation-barrier/status"));
      await drawer.getByRole("button", { name: "重新应用规则" }).click();
      await mark("apiLatencyMs", reapplyResponse);
      await mark("operationBarrierLatencyMs", barrierResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("重新应用已完成，银行明细已刷新。").first()).toBeVisible());
      await mark("finalSettledLatencyMs", expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests));
    });

    await expect.poll(() => api.count(REAPPLY_RULES_PATH)).toBe(1);
    expect(api.lastBody(REAPPLY_RULES_PATH)).toEqual({});
    expect(api.count(SAVE_RULES_PATH)).toBe(0);
    await expect.poll(() => api.count(OPERATION_BARRIER_PATH)).toBeGreaterThanOrEqual(1);
    expect(barrierTargets(api.lastBody(OPERATION_BARRIER_PATH))).toEqual(expect.arrayContaining([
      expect.objectContaining({ read_model_key: "bank_detail", scope_key: "2026-03" }),
    ]));
    await expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests);
    await expect(page.getByText("重新应用已完成，银行明细已刷新。").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("ordinary save ignores a blocked global barrier because it owns no barrier targets", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      operationBarrierMode: "blocked",
      sessionMode: "full_access",
    });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");
    const initialTransactionRequests = api.count(TRANSACTIONS_PATH);

    const drawer = await openAutoTagRulesDrawer(page, recordLatency);
    await drawer.getByRole("textbox", { name: "费用 / 工资 子标签" }).fill("同步阻断测试");
    await recordLatency({
      operationId: "bank-details.save-auto-tag-rules-sync-blocked",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(responseFor("PUT", "/api/bank-details/auto-tag-rules"));
      await drawer.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("规则已保存。").first()).toBeVisible());
      await mark("finalSettledLatencyMs", expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests));
    });

    await expect.poll(() => api.count(SAVE_RULES_PATH)).toBe(1);
    expect(api.count(OPERATION_BARRIER_PATH)).toBe(0);
    expect(api.lastBody(SAVE_RULES_PATH)).toEqual(expect.objectContaining({
      expected_version: 1,
    }));
    await expect(page.getByText("规则已保存。").first()).toBeVisible();
    await expect(page.getByRole("dialog", { name: "操作失败" })).toHaveCount(0);
  });
});
