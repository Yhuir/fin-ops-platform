import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const workbenchRowIds = [
  "oa-o-202603-001",
  "bk-o-202603-001",
  "iv-o-202603-001",
];

async function selectOpenWorkbenchGroup(page: Page) {
  const openZone = page.getByTestId("zone-unpaired");
  const openGroup = page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();

  await openZone.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openZone.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openZone.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(openZone.getByText("已选 3")).toBeVisible();

  return { openZone, openGroup };
}

test.describe("workbench exception browser flow", () => {
  test("keeps canonical rows visible and excludes legacy decisions from the anomaly drawer", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const { openZone, openGroup } = await selectOpenWorkbenchGroup(page);
    await openZone.getByRole("button", { name: "异常处理" }).click();

    const exceptionDialog = page.getByRole("dialog", { name: "统一异常处理" });
    await expect(exceptionDialog).toBeVisible();
    await expect(exceptionDialog.getByText("OA和支出流水一致，缺进项发票")).toBeVisible();
    await expect(exceptionDialog.getByText("命中候选分组")).toBeVisible();
    await expect(exceptionDialog.getByText("CASE-202603-101")).toHaveCount(0);

    await exceptionDialog.getByRole("radio", { name: /追进项发票/ }).click();
    await exceptionDialog.getByRole("textbox", { name: "备注" }).fill("浏览器异常备注");

    const workbenchLoadsBeforeApply = api.count("GET /api/workbench");
    await exceptionDialog.getByRole("button", { name: "提交处理" }).click();

    await expect(exceptionDialog).toHaveAttribute("aria-busy", "true");
    await expect(exceptionDialog.getByRole("button", { name: "提交中..." })).toBeDisabled();
    await expect(exceptionDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(exceptionDialog.getByRole("button", { name: "关闭统一异常处理" })).toBeDisabled();
    await expect(exceptionDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(openGroup).toBeVisible();

    await expect(page.getByRole("dialog", { name: "统一异常处理" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:bk-o-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001")).toBeVisible();
    await expect(openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ })).toBeVisible();

    const previewBody = api.lastBody("POST /api/workbench/exception/preview");
    expect(previewBody).toMatchObject({ month: "all" });
    expect(previewBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(previewBody.row_ids).toHaveLength(workbenchRowIds.length);

    const applyBody = api.lastBody("POST /api/workbench/exception/apply");
    expect(applyBody).toMatchObject({
      month: "all",
      scenario_code: "expense_oa_bank_missing_invoice",
      action_code: "wait_input_invoice",
      payload: { note: "浏览器异常备注" },
    });
    expect(applyBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(applyBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/exception/preview")).toBeGreaterThanOrEqual(1);
    expect(api.count("POST /api/workbench/exception/apply")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(workbenchLoadsBeforeApply);
    await expectNoUnexpectedSuccessUiErrors(page);

    await openZone.getByRole("button", { name: /异常 \d+ \| 已忽略 \d+/ }).click();
    const exceptionDrawer = page.getByRole("dialog", { name: "异常处理" });
    await expect(exceptionDrawer).toBeVisible();
    await exceptionDrawer.getByRole("radio", { name: "已忽略的异常" }).click();
    await expect(exceptionDrawer.getByText("当前没有已忽略的异常。")).toBeVisible();
    await expect(exceptionDrawer.getByText("追进项发票")).toHaveCount(0);
    expect(api.count("POST /api/workbench/actions/cancel-exception")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("keeps row-ignore state out of the OA invoice anomaly drawer", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    const openGroup = page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001");
    await expect(openGroup).toBeVisible();
    const invoiceRow = openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ });
    await expect(invoiceRow).toBeVisible();

    const workbenchLoadsBeforeIgnore = api.count("GET /api/workbench");
    await invoiceRow.getByRole("button", { name: "忽略" }).click();

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
