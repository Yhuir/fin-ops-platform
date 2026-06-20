import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relation browser flow", () => {
  test("confirms a relation in workbench and reflects it in bank details", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowBefore).toBeVisible();
    await expect(bankRowBefore.getByText("候选oa")).toBeVisible();
    await expect(bankRowBefore.getByText("候选发票")).toBeVisible();
    const bankTransactionRequestCountBefore = api.count("GET /api/bank-details/transactions");

    await confirmWorkbenchRelation(page);

    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);

    await page.getByRole("link", { name: "银行明细" }).click();
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowAfter.getByText("有oa")).toBeVisible();
    await expect(bankRowAfter.getByText("有发票")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/bank-details/transactions")).toBeGreaterThan(bankTransactionRequestCountBefore);
  });
});
