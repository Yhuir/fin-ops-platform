import { expect, test } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("pending invoices browser flow", () => {
  test("reflects workbench confirmed invoice relation in pending invoices", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    const pendingRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowBefore).toBeVisible();
    await expect(pendingRowBefore.getByText("已支付待开票")).toBeVisible();
    await expect(pendingRowBefore.getByText("12561048")).toHaveCount(0);
    const pendingRowsBefore = api.count("GET /api/pending-invoices/rows");

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "待找发票" }).click();
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    const pendingRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowAfter.getByText("已支付已开票")).toBeVisible();
    await expect(pendingRowAfter.getByText("12561048")).toBeVisible();
    await expect(pendingRowAfter.getByText("陈涛")).toBeVisible();
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore);
  });
});
