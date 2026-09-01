import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relation and tax-offset boundary", () => {
  test("does not invent or remove tax-offset invoice facts after a relation change", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    const inputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(inputPlanGrid).toBeVisible();
    const rowsBeforeConfirm = await inputPlanGrid.getByRole("row").allTextContents();
    const requestCountBeforeConfirm = api.count("GET /api/tax-offset");

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await page.getByRole("link", { name: "税金抵扣" }).click();
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    expect(api.count("GET /api/tax-offset")).toBeGreaterThan(requestCountBeforeConfirm);

    const refreshedInputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(refreshedInputPlanGrid.getByRole("row")).toHaveCount(rowsBeforeConfirm.length);
    expect(await refreshedInputPlanGrid.getByRole("row").allTextContents()).toEqual(rowsBeforeConfirm);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
