import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relations tax offset browser fan-out", () => {
  test("refreshes the tax offset read model after a workbench relation is confirmed", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      taxOffsetRelationFanout: true,
    });

    await page.goto("/tax-offset");
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    const inputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(inputPlanGrid).toBeVisible();
    await expect(inputPlanGrid.getByText("智能工厂设备商")).toHaveCount(0);
    const taxOffsetRequestCountBeforeConfirm = api.count("GET /api/tax-offset");

    await confirmWorkbenchRelation(page);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(0);

    await page.getByRole("link", { name: "税金抵扣" }).click();
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    expect(api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetRequestCountBeforeConfirm);

    const refreshedInputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(refreshedInputPlanGrid.getByText("智能工厂设备商")).toBeVisible();
    await expect(refreshedInputPlanGrid.getByRole("row", { name: /91330108MA27B4011D/ })).toContainText("7,540.00");
    await expect(page.getByText("税金抵扣数据加载失败，请稍后重试。")).toHaveCount(0);
    await expect(page.getByText(/读模型.*刷新|读模型.*失败|read model/i)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
