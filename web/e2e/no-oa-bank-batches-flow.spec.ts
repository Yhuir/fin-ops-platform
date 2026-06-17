import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("no-OA bank batches browser flow", () => {
  test("submits a selected no-OA bank row, waits for freshness, and withdraws the submitted batch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/no-oa-bank-batches");
    await expect(page.getByRole("heading", { name: "免OA流水批量处理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "未提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "已提交 0" })).toBeVisible();
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();

    const draftTable = page.getByRole("table", { name: "建设银行8106流水" });
    await expect(draftTable).toBeVisible();
    await expect(draftTable.getByText("网银手续费")).toBeVisible();
    await expect(draftTable.getByText("浏览器 e2e 月结手续费")).toBeVisible();
    await draftTable.getByLabel("选择流水 no-oa-bank-e2e-001").check();
    await expect(page.getByText("已选 1 条")).toBeVisible();

    const submitRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/no-oa-bank-batches/submit-selection")
        && request.method() === "POST",
    );
    const submitResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/no-oa-bank-batches/submit-selection")
        && response.request().method() === "POST",
    );
    const submitBarrierResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/operation-barrier/status")
        && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "提交批次" }).click();
    const submitBody = JSON.parse((await submitRequest).postData() ?? "{}") as {
      transaction_ids?: string[];
    };
    expect(submitBody.transaction_ids).toEqual(["no-oa-bank-e2e-001"]);
    expect((await submitResponse).status()).toBe(200);
    expect((await submitBarrierResponse).status()).toBe(200);
    expect(api.count("POST /api/no-oa-bank-batches/submit-selection")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThanOrEqual(1);
    await expect(page.getByText("选中流水已提交")).toBeVisible();

    await page.getByRole("button", { name: "已提交 1" }).click();
    await expect(page.getByRole("button", { name: "已提交 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "费用 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("button", { name: "手续费 1批 · 1条" })).toBeVisible();
    await expect(page.getByRole("table", { name: "建设银行8106流水" })).toBeVisible();
    await expect(page.getByRole("button", { name: "撤回批次" })).toBeVisible();
    await page.getByRole("button", { name: "撤回批次" }).click();

    const withdrawDialog = page.getByRole("dialog", { name: "撤回批次" });
    await expect(withdrawDialog).toBeVisible();
    await expect(withdrawDialog.getByText("撤回后会取消关联台闭环关系")).toBeVisible();
    await withdrawDialog.getByLabel("撤回原因").fill("浏览器 e2e 复核撤回");

    const withdrawRequest = page.waitForRequest((request) =>
      request.url().endsWith("/api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")
        && request.method() === "POST",
    );
    const withdrawResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")
        && response.request().method() === "POST",
    );
    await withdrawDialog.getByRole("button", { name: "确认撤回" }).click();
    const withdrawBody = JSON.parse((await withdrawRequest).postData() ?? "{}") as {
      expected_version?: number;
      reason?: string;
    };
    expect(withdrawBody).toEqual({ expected_version: 2, reason: "浏览器 e2e 复核撤回" });
    expect((await withdrawResponse).status()).toBe(200);
    expect(api.count("POST /api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw")).toBe(1);
    await expect(page.getByText("批次已撤回")).toBeVisible();

    await page.getByRole("button", { name: "历史 1" }).click();
    await expect(page.getByRole("button", { name: "历史 1" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("已撤回", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "提交批次" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "撤回批次" })).toHaveCount(0);
  });
});
