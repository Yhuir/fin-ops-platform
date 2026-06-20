import { expect, type Page } from "./strictTest";

import { expectNoUnexpectedSuccessUiErrors } from "./successAssertions";

export async function confirmWorkbenchRelation(page: Page) {
  await page.getByRole("link", { name: "关联台" }).click();
  const openZone = page.getByTestId("zone-open");
  await expect(openZone).toBeVisible();
  const openGroup = page.getByTestId("candidate-group-open-case:CASE-202603-101");
  await expect(openGroup).toBeVisible();

  await openGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
  await openGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
  await expect(openZone.getByText("已选 3")).toBeVisible();

  await openZone.getByRole("button", { name: "确认关联" }).click();
  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await expect(previewDialog).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-before").getByText("智能工厂设备商").first()).toBeVisible();
  await expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联").first()).toBeVisible();

  await previewDialog.getByRole("button", { name: "确认关联" }).click();
  await expect(page.getByTestId("candidate-group-paired-case:CASE-202603-101")).toBeVisible();
  await expectNoUnexpectedSuccessUiErrors(page);
}
