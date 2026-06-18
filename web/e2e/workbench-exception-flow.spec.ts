import { expect, test, type Page } from "@playwright/test";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

const workbenchRowIds = [
  "oa-o-202603-001",
  "bk-o-202603-001",
  "iv-o-202603-001",
];

async function selectOpenWorkbenchGroup(page: Page) {
  const openZone = page.getByTestId("zone-open");
  const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
  await expect(openZone).toBeVisible();
  await expect(openGroup).toBeVisible();

  await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(openZone.getByText("已选 3")).toBeVisible();

  return { openZone, openGroup };
}

test.describe("workbench exception browser flow", () => {
  test("applies and then cancels an exception only after freshness barrier and fresh refetch", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const { openZone, openGroup } = await selectOpenWorkbenchGroup(page);
    await openZone.getByRole("button", { name: "异常处理" }).click();

    const exceptionDialog = page.getByRole("dialog", { name: "统一异常处理" });
    await expect(exceptionDialog).toBeVisible();
    await expect(exceptionDialog.getByText("OA和支出流水一致，缺进项发票")).toBeVisible();
    await expect(exceptionDialog.getByText("命中候选分组 CASE-202603-101")).toBeVisible();

    await exceptionDialog.getByRole("radio", { name: /追进项发票/ }).click();
    await exceptionDialog.getByRole("textbox", { name: "备注" }).fill("浏览器异常备注");

    const barrierCallsBeforeApply = api.count("POST /api/operation-barrier/status");
    const groupCallsBeforeApply = api.count("GET /api/workbench/groups");
    await exceptionDialog.getByRole("button", { name: "提交处理" }).click();

    await expect(exceptionDialog).toHaveAttribute("aria-busy", "true");
    await expect(exceptionDialog.getByRole("button", { name: "提交中..." })).toBeDisabled();
    await expect(exceptionDialog.getByRole("button", { name: "取消" })).toBeDisabled();
    await expect(exceptionDialog.getByRole("button", { name: "关闭" })).toBeDisabled();
    await expect(exceptionDialog.getByRole("textbox", { name: "备注" })).toBeDisabled();
    await expect(openGroup).toBeVisible();

    await expect(page.getByRole("dialog", { name: "统一异常处理" })).toHaveCount(0);
    await expect(page.getByTestId("candidate-group-open-case:CASE-202603-101")).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: /已处理异常3项/ })).toBeVisible();

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
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeApply);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(groupCallsBeforeApply);

    await openZone.getByRole("button", { name: /已处理异常3项/ }).click();
    const processedModal = page.getByRole("dialog", { name: "已处理异常弹窗" });
    await expect(processedModal).toBeVisible();
    await expect(processedModal.getByText("追进项发票").first()).toBeVisible();
    await expect(processedModal.getByText("浏览器异常备注").first()).toBeVisible();

    const barrierCallsBeforeCancel = api.count("POST /api/operation-barrier/status");
    const groupCallsBeforeCancel = api.count("GET /api/workbench/groups");
    await processedModal.getByRole("button", { name: "取消异常处理" }).first().click();

    const cancelModal = page.getByRole("dialog", { name: "取消异常处理确认弹窗" });
    await expect(cancelModal.getByText("确认取消异常处理后，这组记录会回到未配对区域。")).toBeVisible();
    await cancelModal.getByRole("button", { name: "确认取消异常处理" }).click();

    const restoredOpenGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
    await expect(restoredOpenGroup).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ })).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ })).toBeVisible();
    await expect(restoredOpenGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeVisible();
    await expect(openZone.getByRole("button", { name: /已处理异常0项/ })).toBeVisible();

    const cancelBody = api.lastBody("POST /api/workbench/actions/cancel-exception");
    expect(cancelBody).toMatchObject({
      month: "all",
      comment: "由已处理异常弹窗撤回异常处理",
    });
    expect(cancelBody.row_ids).toEqual(expect.arrayContaining(workbenchRowIds));
    expect(cancelBody.row_ids).toHaveLength(workbenchRowIds.length);
    expect(api.count("POST /api/workbench/actions/cancel-exception")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeCancel);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(groupCallsBeforeCancel);
  });

  test("moves an ignored invoice through ignored modal and restores it after unignore", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/");

    const openZone = page.getByTestId("zone-open");
    const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
    await expect(openGroup).toBeVisible();
    const invoiceRow = openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ });
    await expect(invoiceRow).toBeVisible();

    const barrierCallsBeforeIgnore = api.count("POST /api/operation-barrier/status");
    const groupCallsBeforeIgnore = api.count("GET /api/workbench/groups");
    await invoiceRow.getByRole("button", { name: "忽略" }).click();

    await expect(openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: /已忽略1项/ })).toBeVisible();
    expect(api.count("POST /api/workbench/actions/ignore-row")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/ignore-row")).toMatchObject({
      month: "all",
      row_id: "iv-o-202603-001",
      comment: "由关联台忽略发票：iv-o-202603-001",
    });
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeIgnore);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(groupCallsBeforeIgnore);

    await openZone.getByRole("button", { name: /已忽略1项/ }).click();
    const ignoredModal = page.getByRole("dialog", { name: "已忽略弹窗" });
    await expect(ignoredModal).toBeVisible();
    await expect(ignoredModal.getByText("智能工厂设备商")).toBeVisible();

    const barrierCallsBeforeUnignore = api.count("POST /api/operation-barrier/status");
    const groupCallsBeforeUnignore = api.count("GET /api/workbench/groups");
    await ignoredModal.getByRole("button", { name: "撤回忽略" }).click();

    await expect(openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ })).toBeVisible();
    await expect(openZone.getByRole("button", { name: /已忽略0项/ })).toBeVisible();
    expect(api.count("POST /api/workbench/actions/unignore-row")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/unignore-row")).toMatchObject({
      month: "all",
      row_id: "iv-o-202603-001",
    });
    expect(api.count("POST /api/operation-barrier/status")).toBeGreaterThan(barrierCallsBeforeUnignore);
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThan(groupCallsBeforeUnignore);
  });
});
