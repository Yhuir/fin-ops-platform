import { expect, test, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const TRANSACTION_ID = "bk-o-202603-001";

function categoryPath(method: "POST" | "DELETE", endpoint: "category-confirmation" | "category-assignment") {
  return `${method} /api/bank-details/transactions/${TRANSACTION_ID}/${endpoint}`;
}

function createBankDetailsLatencyRecorder(page: Parameters<typeof createOperationLatencyRecorder>[0], testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/bank-details",
    pageKey: "bank-details",
    module: "bank-details",
  });
}

function categoryResponse(method: "POST" | "DELETE", endpoint: "category-confirmation" | "category-assignment") {
  return (response: { url(): string; request(): { method(): string } }) => {
    const url = new URL(response.url());
    return response.request().method() === method
      && url.pathname === `/api/bank-details/transactions/${TRANSACTION_ID}/${endpoint}`;
  };
}

test.describe("bank details category confirmation browser flow", () => {
  test("confirms only the current candidate and refreshes the row as manually confirmed", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "needs_confirmation",
      sessionMode: "user",
    });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row.getByRole("button", { name: "待确认" })).toBeEnabled();
    await row.getByRole("button", { name: "待确认" }).click();

    const primaryMenu = page.getByRole("menu", { name: "待确认主标签" });
    await expect(primaryMenu).toBeVisible();
    await expect(primaryMenu.getByRole("menuitem", { name: "成本" })).toBeVisible();
    await expect(primaryMenu.getByRole("menuitem", { name: "内部往来款" })).toBeVisible();
    await expect(primaryMenu.getByRole("menuitem", { name: "费用" })).toHaveCount(0);

    await primaryMenu.getByRole("menuitem", { name: "成本" }).click();
    const candidateMenu = page.getByRole("menu", { name: "成本可选标签" });
    await expect(candidateMenu).toBeVisible();
    await candidateMenu.getByRole("menuitem", { name: "设备款" }).click();

    await expect(row.getByRole("button", { name: "成本 / 设备款" })).toBeEnabled();
    expect(api.count(categoryPath("POST", "category-confirmation"))).toBe(0);
    expect(api.count(categoryPath("POST", "category-assignment"))).toBe(0);

    await recordLatency({
      operationId: "bank-details.save-category-confirmation",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(categoryResponse("POST", "category-confirmation"));
      await page.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(row.getByText("成本 / 设备款")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(row.getByRole("button", { name: "撤销" })).toBeEnabled());
    });

    await expect.poll(() => api.count(categoryPath("POST", "category-confirmation"))).toBe(1);
    expect(api.lastBody(categoryPath("POST", "category-confirmation"))).toEqual({
      category_code: "equipment_payment",
    });
    expect(api.count(categoryPath("POST", "category-assignment"))).toBe(0);
    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThanOrEqual(2);
    await expect(row.getByText("成本 / 设备款")).toBeVisible();
    await expect(row.getByRole("button", { name: "待确认" })).toHaveCount(0);
    await expect(row.getByRole("button", { name: "撤销" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);

    await recordLatency({
      operationId: "bank-details.undo-category-confirmation",
      visibleLabel: "撤销",
      actionType: "click",
    }, async (mark) => {
      const undoResponse = page.waitForResponse(categoryResponse("DELETE", "category-confirmation"));
      await row.getByRole("button", { name: "撤销" }).click();
      await mark("apiLatencyMs", undoResponse);
      await mark("firstVisibleResponseLatencyMs", expect(row.getByRole("button", { name: "待确认" })).toBeEnabled());
      await mark("finalSettledLatencyMs", expect(row.getByRole("button", { name: "待确认" })).toBeEnabled());
    });
    await expect.poll(() => api.count(categoryPath("DELETE", "category-confirmation"))).toBe(1);
    expect(api.count(categoryPath("DELETE", "category-assignment"))).toBe(0);
    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThanOrEqual(3);
    await expect(row.getByRole("button", { name: "待确认" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("assigns an unmatched row from active rules with third-level turnover semantics", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "unmatched",
      sessionMode: "user",
    });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row.getByRole("button", { name: "待分类" })).toBeEnabled();
    await row.getByRole("button", { name: "待分类" }).click();

    const primaryMenu = page.getByRole("menu", { name: "待分类主标签" });
    await expect(primaryMenu).toBeVisible();
    await expect(primaryMenu.getByRole("menuitem", { name: "外部往来款付款" })).toBeVisible();
    await expect(primaryMenu.getByRole("menuitem", { name: "内部往来款" })).toBeVisible();
    await primaryMenu.getByRole("menuitem", { name: "外部往来款付款" }).click();

    const choiceMenu = page.getByRole("menu", { name: "外部往来款付款可选标签" });
    await expect(choiceMenu).toBeVisible();
    await choiceMenu.getByRole("menuitem", { name: "借出款" }).click();

    const thirdMenu = page.getByRole("menu", { name: "借出款可选业务类型" });
    await expect(thirdMenu).toBeVisible();
    await thirdMenu.getByRole("menuitem", { name: "业务往来" }).click();

    await expect(row.getByRole("button", { name: "外部往来款付款 / 借出款 / 业务往来" })).toBeEnabled();
    expect(api.count(categoryPath("POST", "category-assignment"))).toBe(0);
    expect(api.count(categoryPath("POST", "category-confirmation"))).toBe(0);

    await recordLatency({
      operationId: "bank-details.save-category-assignment",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(categoryResponse("POST", "category-assignment"));
      await page.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(row.getByText("外部往来款付款 / 借出款 / 业务往来")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(row.getByRole("button", { name: "撤销" })).toBeEnabled());
    });

    await expect.poll(() => api.count(categoryPath("POST", "category-assignment"))).toBe(1);
    expect(api.lastBody(categoryPath("POST", "category-assignment"))).toEqual({
      category_code: "external_payment",
      category_primary_label: "外部往来款付款",
      category_sub_label: "借出款",
      category_third_label: "业务往来",
      category_label_path: ["外部往来款付款", "借出款", "业务往来"],
      turnover_action_type: "pending_collection",
      turnover_family: "business",
    });
    expect(api.count(categoryPath("POST", "category-confirmation"))).toBe(0);
    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThanOrEqual(2);
    await expect(row.getByText("外部往来款付款 / 借出款 / 业务往来")).toBeVisible();
    await expect(row.getByRole("button", { name: "待分类" })).toHaveCount(0);
    await expect(row.getByRole("button", { name: "撤销" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);

    await recordLatency({
      operationId: "bank-details.undo-category-assignment",
      visibleLabel: "撤销",
      actionType: "click",
    }, async (mark) => {
      const undoResponse = page.waitForResponse(categoryResponse("DELETE", "category-assignment"));
      await row.getByRole("button", { name: "撤销" }).click();
      await mark("apiLatencyMs", undoResponse);
      await mark("firstVisibleResponseLatencyMs", expect(row.getByRole("button", { name: "待分类" })).toBeEnabled());
      await mark("finalSettledLatencyMs", expect(row.getByRole("button", { name: "待分类" })).toBeEnabled());
    });
    await expect.poll(() => api.count(categoryPath("DELETE", "category-assignment"))).toBe(1);
    expect(api.count(categoryPath("DELETE", "category-confirmation"))).toBe(0);
    await expect.poll(() => api.count("GET /api/bank-details/transactions")).toBeGreaterThanOrEqual(3);
    await expect(row.getByRole("button", { name: "待分类" })).toBeEnabled();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("replaces an automatic label with a persistent internal-transfer assignment", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
    });
    const recordLatency = createBankDetailsLatencyRecorder(page, testInfo);

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();

    const row = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(row.getByText("成本 / 设备款")).toBeVisible();
    await row.getByRole("button", { name: "撤销" }).click();

    const primaryMenu = page.getByRole("menu", { name: "重新分类主标签" });
    await expect(primaryMenu).toBeVisible();
    expect(api.count(categoryPath("POST", "category-assignment"))).toBe(0);
    await primaryMenu.getByRole("menuitem", { name: "内部往来款" }).click();
    const choiceMenu = page.getByRole("menu", { name: "内部往来款可选标签" });
    await choiceMenu.getByRole("menuitem", { name: "内部往来款" }).click();

    await recordLatency({
      operationId: "bank-details.override-auto-category",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(categoryResponse("POST", "category-assignment"));
      await page.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(row.getByText("内部往来款")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(row.getByRole("button", { name: "撤销" })).toBeEnabled());
    });

    await expect.poll(() => api.count(categoryPath("POST", "category-assignment"))).toBe(1);
    expect(api.lastBody(categoryPath("POST", "category-assignment"))).toEqual({ category_code: "internal_transfer" });
    expect(api.count(categoryPath("DELETE", "category-assignment"))).toBe(0);
    expect(api.count(categoryPath("POST", "category-confirmation"))).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
