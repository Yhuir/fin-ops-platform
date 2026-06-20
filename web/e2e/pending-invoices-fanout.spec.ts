import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("pending invoices browser flow", () => {
  test("allows selecting text in the pending invoice table body", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    const counterpartyName = page.locator(".pending-invoices-counterparty-name").filter({ hasText: "智能工厂设备商" }).first();
    await expect(counterpartyName).toBeVisible();

    const box = await counterpartyName.boundingBox();
    expect(box).not.toBeNull();
    if (!box) {
      return;
    }

    await page.mouse.move(box.x + 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width - 2, box.y + box.height / 2, { steps: 12 });
    await page.mouse.up();

    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).toContain("智能工厂设备");
  });

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
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore);
  });
});
