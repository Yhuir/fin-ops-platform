import { Buffer } from "node:buffer";

import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("invoice import browser flow", () => {
  test("previews and confirms input/output invoice files, then refreshes the workbench state", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/imports/invoices");
    await expect(page.getByTestId("import-workflow-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "发票导入" })).toBeVisible();

    await page.locator('input[type="file"]').setInputFiles([
      {
        name: "一月发票.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("invoice-import-e2e-output"),
      },
      {
        name: "二月发票.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("invoice-import-e2e-input"),
      },
    ]);

    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeDisabled();
    await page.getByLabel("票据方向 一月发票.xlsx").selectOption("output_invoice");
    await page.getByLabel("票据方向 二月发票.xlsx").selectOption("input_invoice");
    await expect(previewButton).toBeEnabled();
    await previewButton.click();

    await expect(page.getByText("已完成 2 个文件的预览识别。")).toBeVisible();
    await expect(page.getByLabel("审计汇总 原始 28")).toBeVisible();
    await expect(page.getByLabel("审计汇总 可导入 22")).toBeVisible();
    await expect(page.getByLabel("审计汇总 异常 1")).toBeVisible();
    await expect(page.getByRole("grid", { name: "导入预览结果" })).toBeVisible();
    await expect(page.getByText("将导入 22 条唯一记录，跳过 4 条重复，2 条需复核。")).toBeVisible();
    expect(api.count("POST /imports/files/preview")).toBe(1);

    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已确认导入")).toBeVisible();
    await expect(page.getByText("当前还没有选择文件。")).toBeVisible();
    expect(api.count("POST /imports/files/confirm")).toBe(1);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(0);
  });
});
