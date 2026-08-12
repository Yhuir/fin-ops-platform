import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

test.describe("workbench exception browser flow", () => {
  test("keeps row-ignore state out of the OA invoice anomaly drawer", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001");
    await expect(openGroup).toBeVisible();
    const invoiceRow = openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ });
    await expect(invoiceRow).toBeVisible();

    const workbenchLoadsBeforeIgnore = api.count("GET /api/workbench");
    await invoiceRow.getByRole("button", { name: "更多操作" }).click();
    await page.getByRole("menuitem", { name: "忽略" }).click();

    await expect(openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })).toBeVisible();
    expect(api.count("POST /api/workbench/actions/ignore-row")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/ignore-row")).toMatchObject({
      month: "all",
      row_id: "iv-o-202603-001",
      comment: "由关联台忽略发票：iv-o-202603-001",
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(workbenchLoadsBeforeIgnore);
    await expectNoUnexpectedSuccessUiErrors(page);

    await openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(exceptionDrawer).toBeVisible();
    await exceptionDrawer.getByRole("radio", { name: "已忽略的异常" }).click();
    await expect(exceptionDrawer.getByText("当前没有已忽略的异常。")).toBeVisible();
    await expect(exceptionDrawer.getByText("智能工厂设备商")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/unignore-row")).toBe(0);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("ignores and restores an exact-cent OA invoice amount mismatch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchAmountMismatchScenario: true,
      workbenchInitialRelationConfirmed: true,
    });

    await page.goto("/");

    const pairedZone = page.getByTestId("zone-paired");
    await expect(pairedZone.getByText("金额不一致")).toBeVisible();
    await page
      .getByTestId("zone-unpaired")
      .getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })
      .click();

    const drawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(drawer.getByText("金额不一致").first()).toBeVisible();
    await drawer.getByRole("button", { name: "忽略" }).click();

    await expect(pairedZone.getByText("已忽略：金额不一致")).toBeVisible();
    expect(api.count("POST /api/workbench/exceptions/amount-mismatch/ignore")).toBe(1);
    expect(api.lastBody("POST /api/workbench/exceptions/amount-mismatch/ignore")).toMatchObject({
      month: "all",
      zone: "paired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    });

    await drawer.getByRole("radio", { name: "已忽略的异常" }).click();
    await expect(drawer.getByText("已忽略：金额不一致").first()).toBeVisible();
    await drawer.getByRole("button", { name: "撤回忽略" }).click();

    await expect(pairedZone.getByText("金额不一致")).toBeVisible();
    expect(api.count("POST /api/workbench/exceptions/amount-mismatch/restore")).toBe(1);
    expect(api.lastBody("POST /api/workbench/exceptions/amount-mismatch/restore")).toMatchObject({
      month: "all",
      zone: "paired",
      group_id: "case:CASE-202603-101",
      fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
