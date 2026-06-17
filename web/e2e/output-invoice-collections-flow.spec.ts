import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("output invoice collections browser flow", () => {
  test("saves collection status and creates a formal receipt through browser drawers", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/output-invoice-collections");
    await expect(page.getByTestId("output-invoice-collections-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "销项发票收款情况" })).toBeVisible();
    await expect(page.getByRole("table", { name: "销项发票收款情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toBeVisible();
    await expect(row.getByText("待出收据").first()).toBeVisible();

    const rowsBeforeStatusSave = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "状态/提醒" }).click();
    const statusDrawer = page.getByRole("dialog", { name: "收款状态和提醒" });
    await expect(statusDrawer).toBeVisible();
    await statusDrawer.getByLabel("手动状态").selectOption("pending_red_invoice");
    await statusDrawer.getByLabel("预计收款日期").fill("2026-06-20");
    await statusDrawer.getByLabel("状态备注").fill("浏览器 e2e 状态备注");
    await statusDrawer.getByLabel("提醒时间").fill("2026-06-18T09:30");
    await statusDrawer.getByLabel("提醒备注").fill("浏览器 e2e 提醒备注");

    const statusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status")
        && response.request().method() === "PUT",
    );
    const reminderResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder")
        && response.request().method() === "PUT",
    );
    await statusDrawer.getByRole("button", { name: "保存" }).click();
    expect((await statusResponse).status()).toBe(200);
    expect((await reminderResponse).status()).toBe(200);
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeStatusSave);
    await expect(page.getByRole("dialog", { name: "收款状态和提醒" })).toBeHidden();
    await expect(row.getByText("待冲红")).toBeVisible();
    await expect(row.getByText("待收款，已收部分款")).toHaveCount(0);

    const rowsBeforeReceiptCreate = api.count("GET /api/output-invoice-collections/rows");
    await row.getByRole("button", { name: "待出收据" }).click();
    const receiptDrawer = page.getByRole("dialog", { name: "待出收据预览" });
    await expect(receiptDrawer).toBeVisible();
    await expect(receiptDrawer.getByText("收 据")).toBeVisible();
    await expect(receiptDrawer.getByText("人民币伍仟元整")).toBeVisible();
    await expect(receiptDrawer.getByText("销项发票 XSFP-E2E-0001")).toBeVisible();

    const createReceiptResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")
        && response.request().method() === "POST",
    );
    await receiptDrawer.getByRole("button", { name: "创建正式收据" }).click();
    expect((await createReceiptResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts")).toBe(1);
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeReceiptCreate);
    await expect(page.getByRole("dialog", { name: "待出收据预览" })).toBeHidden();
    await expect(row.getByTitle("已出收据")).toBeVisible();

    await row.getByRole("button", { name: "已出收据" }).click();
    const historyDrawer = page.getByRole("dialog", { name: "已出收据历史" });
    await expect(historyDrawer).toBeVisible();
    await expect(historyDrawer.getByRole("heading", { name: "SK2026050002" })).toBeVisible();
    await expect(historyDrawer.getByText("issued")).toBeVisible();
  });
});
