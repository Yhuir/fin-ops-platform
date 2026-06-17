import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.describe("ETC ticket management browser flow", () => {
  test("creates an OA draft for an imported ETC batch and moves it to submitted history", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/etc-tickets");
    await expect(page.getByTestId("etc-ticket-management-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "ETC票据" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "ETC批次状态" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "未提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "已提交 0" })).toBeVisible();

    const row = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(row).toBeVisible();
    await expect(row).toContainText("ETC-E2E-2026-03");
    await expect(row).toContainText("ETC票 2 + 补充凭证 0");
    await expect(page.getByRole("table", { name: "ETC发票明细" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "ETC-E2E-001" })).toBeVisible();

    const submitButton = page.getByRole("button", { name: "提交OA" });
    await expect(submitButton).toBeEnabled();
    await submitButton.click();

    const createDialog = page.getByRole("dialog", { name: "创建OA草稿" });
    await expect(createDialog).toBeVisible();
    await expect(createDialog.getByText("为当前批次创建 OA 草稿。")).toBeVisible();
    await expect(createDialog.getByText("批次：ETC-E2E-2026-03")).toBeVisible();

    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/oa-draft")
        && response.request().method() === "POST",
    );
    await createDialog.getByRole("button", { name: "创建草稿" }).click();
    expect((await draftResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/oa-draft")).toBe(1);

    const resultDialog = page.getByRole("dialog", { name: "OA提交确认" });
    await expect(resultDialog).toBeVisible();
    await expect(resultDialog.getByText("OA草稿已创建，等待提交确认。")).toBeVisible();
    await expect(resultDialog.getByRole("button", { name: "打开草稿" })).toBeEnabled();

    const manualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/etc/business-batches/etc-business-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    await resultDialog.getByRole("button", { name: "已提交" }).click();
    expect((await manualStatusResponse).status()).toBe(200);
    expect(api.count("POST /api/etc/business-batches/etc-business-e2e-001/manual-oa-status")).toBe(1);

    await expect(page.getByRole("radio", { name: "已提交 1" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: "提交OA" })).toHaveCount(0);
    const submittedRow = page.getByTestId("etc-batch-row-etc-business-e2e-001");
    await expect(submittedRow).toBeVisible();
    await expect(submittedRow).toContainText("人工确认已提交");
    await expect(submittedRow).toContainText("ETC-E2E-2026-03");
  });
});
