import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("turnover ledger browser flow", () => {
  test("confirms and withdraws a manual turnover closure through freshness barriers", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/turnover-ledger");
    await expect(page.getByTestId("turnover-ledger-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "外部往来款管理" })).toBeVisible();

    const table = page.getByRole("table", { name: "往来款左右双栏台账" });
    await expect(table).toBeVisible();
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();

    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" }).check();
    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-income-1000" }).check();
    await expect(page.getByText("已选 2 笔")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeEnabled();
    await page.getByRole("button", { name: "确认闭环" }).click();

    const drawer = page.getByRole("dialog", { name: "确认外部往来闭环" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("turnover-bank-expense-1000")).toBeVisible();
    await expect(drawer.getByText("turnover-bank-income-1000")).toBeVisible();
    await expect(drawer.getByTestId("turnover-closure-delta")).toHaveText("0.00");
    await drawer.getByRole("button", { name: "确定" }).click();

    await expect(page.getByText("外部往来闭环已确认")).toBeVisible();
    expect(api.count("POST /api/turnover-ledger/closures/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);
    await expect(page.getByText("已闭环 · 2笔")).toBeVisible();
    await expect(table.getByText("已闭环").first()).toBeVisible();

    const barrierCallsBeforeWithdraw = api.count("POST /api/operation-barrier/status");
    await table.getByRole("checkbox", { name: "选择流水 turnover-bank-expense-1000" }).check();
    await expect(page.getByRole("button", { name: "撤回闭环" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeDisabled();
    await page.getByRole("button", { name: "撤回闭环" }).click();

    await expect(page.getByText("外部往来闭环已撤回")).toBeVisible();
    expect(api.count("POST /api/turnover-ledger/relations/turnover_rel_e2e_closure/withdraw")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeWithdraw);
    await expect(page.getByText("已闭环 · 2笔")).toHaveCount(0);
    await expect(table.getByText("未闭环").first()).toBeVisible();
  });
});
