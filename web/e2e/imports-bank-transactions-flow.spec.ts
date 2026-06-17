import { Buffer } from "node:buffer";

import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("bank transaction import browser flow", () => {
  test("previews and confirms bank statement files, then reflects the imported row in bank details", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/imports/bank-transactions");
    await expect(page.getByTestId("import-workflow-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "银行流水导入" })).toBeVisible();

    await page.locator('input[type="file"]').setInputFiles([
      {
        name: "historydetail14080.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("bank-import-e2e-a"),
      },
      {
        name: "2026-01-01至2026-01-31交易明细.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("bank-import-e2e-b"),
      },
    ]);

    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeDisabled();
    await page.getByLabel("对应账户 historydetail14080.xlsx").selectOption("bank_mapping_8826");
    await page.getByLabel("对应账户 2026-01-01至2026-01-31交易明细.xlsx").selectOption("bank_mapping_8826");
    await expect(previewButton).toBeEnabled();
    await previewButton.click();

    await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
    await expect(page.getByLabel("审计汇总 原始 18")).toBeVisible();
    await expect(page.getByLabel("审计汇总 可导入 14")).toBeVisible();
    await expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible();
    await expect(page.getByText("将导入 14 条唯一记录，跳过 4 条重复。")).toBeVisible();
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await page.getByRole("button", { name: "确认导入" }).click();
    const conflictDialog = page.getByRole("dialog", { name: "银行账户冲突确认" });
    await expect(conflictDialog).toBeVisible();
    await expect(conflictDialog.getByText("historydetail14080.xlsx")).toBeVisible();
    await expect(conflictDialog.getByText("后四位选择为8826，系统识别为4080")).toBeVisible();
    await conflictDialog.getByRole("button", { name: "仍按所选账户 建设银行 8826 导入" }).click();

    await expect(page.getByText("已确认导入")).toBeVisible();
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(0);

    await page.getByRole("link", { name: "银行明细" }).click();
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const importedRow = page.getByRole("row", { name: /导入浏览器测试客户/ });
    await expect(importedRow).toBeVisible();
    await expect(importedRow.getByText("1,688.00")).toBeVisible();
    await expect(importedRow.getByText("银行流水导入 browser e2e")).toBeVisible();
  });
});
