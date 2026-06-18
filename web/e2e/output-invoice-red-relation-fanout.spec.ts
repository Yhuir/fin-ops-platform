import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";

test.describe("output invoice red relation browser fan-out", () => {
  test("confirms a red invoice relation and reflects the manual evidence after rows refresh", async ({ page }) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceRedRelationCandidate: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/output-invoice-collections", "output-invoice-collections-page", { diagnostics });

    const sourceRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(sourceRow).toBeVisible();
    await expect(sourceRow.getByText("待收款，已收部分款")).toBeVisible();
    await expect(page.getByRole("row", { name: /XSFP-E2E-0002/ })).toBeVisible();

    const rowsBeforeConfirm = api.count("GET /api/output-invoice-collections/rows");
    await sourceRow.getByRole("button", { name: "红蓝票" }).click();
    const relationDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await expect(relationDrawer).toBeVisible();
    await expect(relationDrawer.getByText("已有依据")).toHaveCount(0);

    await relationDrawer.locator("label").filter({ hasText: "XSFP-E2E-0002" }).getByRole("radio").check();
    await relationDrawer.getByLabel("确认依据").fill("浏览器 e2e 红蓝票关系确认");

    const confirmResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")
        && response.request().method() === "POST",
    );
    await relationDrawer.getByRole("button", { name: "确认关系" }).click();
    expect((await confirmResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toBe(1);
    expect(api.lastBody("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toMatchObject({
      relatedInvoiceId: "out-e2e-002",
      relationType: "red_invoice",
      evidence: "浏览器 e2e 红蓝票关系确认",
    });
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeConfirm);
    await expect(page.getByRole("dialog", { name: "红蓝票关系" })).toBeHidden();

    const refreshedRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(refreshedRow.getByText("待冲红")).toBeVisible();
    await refreshedRow.getByRole("button", { name: "红蓝票" }).click();

    const refreshedDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await expect(refreshedDrawer).toBeVisible();
    await expect(refreshedDrawer.getByText("已有依据")).toBeVisible();
    await expect(refreshedDrawer.getByText("XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认")).toBeVisible();
  });
});
