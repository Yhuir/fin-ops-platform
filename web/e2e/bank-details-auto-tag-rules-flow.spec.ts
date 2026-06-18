import { expect, test, type Page } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady } from "./fixtures/pageReady";

const SAVE_RULES_PATH = "PUT /api/bank-details/auto-tag-rules";
const REAPPLY_RULES_PATH = "POST /api/bank-details/auto-tag-rules/reapply";
const OPERATION_BARRIER_PATH = "POST /api/operation-barrier/status";
const TRANSACTIONS_PATH = "GET /api/bank-details/transactions";

async function openAutoTagRulesDrawer(page: Page) {
  await page.getByRole("button", { name: /自动标签规则/ }).click();
  const drawer = page.getByRole("dialog", { name: "自动标签规则" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("table", { name: "自动标签规则表格" })).toBeVisible();
  return drawer;
}

function barrierTargets(body: Record<string, unknown>) {
  return Array.isArray(body.targets) ? body.targets : [];
}

test.describe("bank details auto tag rules browser flow", () => {
  test("saves edited automatic tag rules with the visible date scope and waits for fresh bank detail rows", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");
    const initialTransactionRequests = api.count(TRANSACTIONS_PATH);

    const drawer = await openAutoTagRulesDrawer(page);
    await drawer.getByRole("textbox", { name: "费用 / 工资 子标签" }).fill("规则刷新测试");
    await expect(drawer.getByRole("button", { name: "保存" })).toBeEnabled();

    await drawer.getByRole("button", { name: "保存" }).click();

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

    await expect.poll(() => api.count(OPERATION_BARRIER_PATH)).toBeGreaterThanOrEqual(1);
    expect(barrierTargets(api.lastBody(OPERATION_BARRIER_PATH))).toEqual(expect.arrayContaining([
      expect.objectContaining({ read_model_key: "bank_detail", scope_key: "2026-03" }),
    ]));
    await expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests);
    await expect(page.getByText("规则已保存，银行明细已刷新。").first()).toBeVisible();
    await expect(page.getByRole("dialog", { name: "操作失败" })).toHaveCount(0);
  });

  test("reapplies existing automatic tag rules without saving a draft and refreshes bank detail rows", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");
    const initialTransactionRequests = api.count(TRANSACTIONS_PATH);

    const drawer = await openAutoTagRulesDrawer(page);
    await expect(drawer.getByRole("button", { name: "保存" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "重新应用规则" })).toBeEnabled();

    await drawer.getByRole("button", { name: "重新应用规则" }).click();

    await expect.poll(() => api.count(REAPPLY_RULES_PATH)).toBe(1);
    expect(api.lastBody(REAPPLY_RULES_PATH)).toEqual({});
    expect(api.count(SAVE_RULES_PATH)).toBe(0);
    await expect.poll(() => api.count(OPERATION_BARRIER_PATH)).toBeGreaterThanOrEqual(1);
    expect(barrierTargets(api.lastBody(OPERATION_BARRIER_PATH))).toEqual(expect.arrayContaining([
      expect.objectContaining({ read_model_key: "bank_detail", scope_key: "2026-03" }),
    ]));
    await expect.poll(() => api.count(TRANSACTIONS_PATH)).toBeGreaterThan(initialTransactionRequests);
    await expect(page.getByText("重新应用已完成，银行明细已刷新。").first()).toBeVisible();
    await expect(page.getByRole("dialog", { name: "操作失败" })).toHaveCount(0);
  });

  test("keeps a successful save as a warning instead of a failure when the post-save sync is blocked", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      operationBarrierMode: "blocked",
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/bank-details", "bank-details-page");

    const drawer = await openAutoTagRulesDrawer(page);
    await drawer.getByRole("textbox", { name: "费用 / 工资 子标签" }).fill("同步阻断测试");
    await drawer.getByRole("button", { name: "保存" }).click();

    await expect.poll(() => api.count(SAVE_RULES_PATH)).toBe(1);
    await expect.poll(() => api.count(OPERATION_BARRIER_PATH)).toBeGreaterThanOrEqual(1);
    expect(api.lastBody(SAVE_RULES_PATH)).toEqual(expect.objectContaining({
      expected_version: 1,
    }));
    await expect(page.getByText("规则已保存，后台同步尚未完成，请稍后刷新。").first()).toBeVisible();
    await expect(page.getByRole("dialog", { name: "操作失败" })).toHaveCount(0);
  });
});
