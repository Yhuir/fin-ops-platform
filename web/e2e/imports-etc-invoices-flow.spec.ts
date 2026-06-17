import { Buffer } from "node:buffer";

import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("ETC invoice import browser flow", () => {
  test("previews ETC zip files for a ready task and confirms the import job", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/imports/etc-invoices");
    await expect(page.getByTestId("import-workflow-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC发票导入" })).toBeVisible();
    await expect(page.getByText("请选择已确认的 ETC 对账任务后再预览 ETC zip。")).toBeVisible();
    expect(api.count("GET /api/etc/reconciliation-tasks/ready-for-import")).toBeGreaterThan(0);

    const previewButton = page.getByRole("button", { name: "开始预览" });
    await expect(previewButton).toBeDisabled();
    await page.getByLabel("ETC对账任务", { exact: true }).selectOption("etc_task_ready_001");
    await expect(page.getByLabel("已选ETC对账任务")).toContainText("任务 2026-03 ETC 对账");

    await page.locator('input[type="file"]').setInputFiles([
      {
        name: "etc-2026-03.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("etc-import-e2e-a"),
      },
      {
        name: "etc-2026-04.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("etc-import-e2e-b"),
      },
    ]);

    await expect(previewButton).toBeEnabled();
    await previewButton.click();

    await expect(page.getByText("已完成 2 个 ETC zip 文件预览。")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC导入预览" })).toBeVisible();
    await expect(page.getByText("etc_import_session_e2e_001")).toBeVisible();
    await expect(page.getByLabel("审计汇总 原始 4")).toBeVisible();
    await expect(page.getByLabel("审计汇总 可导入 1")).toBeVisible();
    await expect(page.getByText("将导入 1 条唯一记录，跳过 2 条重复，1 条需复核。")).toBeVisible();
    await expect(page.getByRole("grid", { name: "ETC导入预览结果" })).toBeVisible();
    await expect(page.getByText("ETC-2026-005")).toBeVisible();
    await expect(page.getByText("新发票待导入")).toBeVisible();
    await expect(page.getByText("补充凭证匹配")).toBeVisible();
    await expect(page.getByText("XML 解析失败")).toBeVisible();
    expect(api.count("POST /api/etc/import/preview")).toBe(1);
    expect(api.count("POST /imports/files/preview")).toBe(0);

    await page.getByRole("button", { name: "确认导入" }).click();

    await expect(page.getByText("已开始后台导入")).toBeVisible();
    expect(api.count("POST /api/etc/import/confirm")).toBe(1);
    expect(api.count("POST /imports/files/confirm")).toBe(0);
  });
});
