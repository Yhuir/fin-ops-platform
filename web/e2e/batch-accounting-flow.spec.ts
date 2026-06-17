import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("batch accounting browser flow", () => {
  test("submits and withdraws daily reimbursement rows through the relation freshness barrier", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/batch-accounting");
    await expect(page.getByRole("heading", { name: "日常报销批量账务管理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();

    const bankPanel = page.getByRole("region", { name: "批量账务流水" });
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const oaTable = page.getByRole("table", { name: "可关联OA项" });
    await oaTable.getByRole("checkbox", { name: "选择 刘晨 2026-04-02" }).check();
    await oaTable.getByRole("checkbox", { name: "选择 王青 2026-04-03" }).check();
    await expect(page.getByText("已选 OA 2 项")).toBeVisible();
    await expect(page.getByText("已选 OA 金额 1,200.00")).toBeVisible();
    await expect(page.getByText("差额 0.00")).toBeVisible();

    const batchAccountingGetsBeforeSubmit = api.count("GET /api/batch-accounting");
    await page.getByRole("button", { name: "关联OA项与流水" }).click();

    await expect(page.getByText("已关联批量账务流水与 2 项 OA。")).toBeVisible();
    expect(api.count("POST /api/batch-accounting/submit")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);
    expect(api.count("GET /api/batch-accounting")).toBeGreaterThan(batchAccountingGetsBeforeSubmit);
    await expect(page.getByRole("button", { name: "已提交 1" })).toBeVisible();

    await page.getByRole("button", { name: "已提交 1" }).click();
    await expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const submittedTable = page.getByRole("table", { name: "已关联OA项" });
    await expect(submittedTable.getByRole("row", { name: /刘晨.*品牌广告投放.*700.00/ })).toBeVisible();
    await expect(submittedTable.getByRole("row", { name: /王青.*客户拜访差旅报销.*500.00/ })).toBeVisible();
    await expect(page.getByText("银行流水金额 1,200.00")).toBeVisible();
    await expect(page.getByText("已选 OA 2 项")).toBeVisible();
    await expect(page.getByText("差额 0.00")).toBeVisible();

    const barrierCallsBeforeWithdraw = api.count("POST /api/operation-barrier/status");
    await page.getByRole("button", { name: "撤回关联" }).click();
    const withdrawDialog = page.getByRole("dialog", { name: "撤回关联" });
    await expect(withdrawDialog).toBeVisible();
    await withdrawDialog.getByLabel("撤回原因").fill("浏览器回归验证撤回");
    await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();

    await expect(page.getByText("已撤回批量账务关联。")).toBeVisible();
    expect(api.count("POST /api/batch-accounting/BA-REL-202604-001/withdraw")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeWithdraw);
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByText("当前年份暂无批量账务流水")).toBeVisible();

    await page.getByRole("button", { name: "未提交 1" }).click();
    await expect(bankPanel.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-04-03 09:20:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("table", { name: "可关联OA项" }).getByRole("checkbox", { name: "选择 刘晨 2026-04-02" })).toBeVisible();
  });
});
