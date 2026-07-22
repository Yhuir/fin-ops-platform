import { expect, type Page } from "./strictTest";

import type { OperationLatencyMark, OperationLatencyMetadata, OperationLatencyRecorder } from "./operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./successAssertions";

async function runOperation(
  recordLatency: OperationLatencyRecorder | undefined,
  metadata: OperationLatencyMetadata,
  run: (mark: OperationLatencyMark) => Promise<void>,
) {
  if (recordLatency) {
    await recordLatency(metadata, run);
    return;
  }
  await run(async (_field, observed) => observed);
}

function isPostTo(pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) => {
    const url = new URL(response.url());
    return url.pathname === pathname && response.request().method() === "POST";
  };
}

export async function confirmWorkbenchRelation(page: Page, recordLatency?: OperationLatencyRecorder) {
  const openZone = page.getByTestId("zone-unpaired");
  const openOaGroup = page.getByTestId("candidate-group-unpaired-row:oa-o-202603-001");
  const openBankGroup = page.getByTestId("candidate-group-unpaired-row:bk-o-202603-001");
  const openInvoiceGroup = page.getByTestId("candidate-group-unpaired-row:iv-o-202603-001");

  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.open-page",
    visibleLabel: "关联台",
    actionType: "click",
  }, async (mark) => {
    await page.getByRole("link", { name: "关联台" }).click();
    await mark("firstVisibleResponseLatencyMs", expect(openZone).toBeVisible());
    await mark("finalSettledLatencyMs", expect(openOaGroup).toBeVisible());
  });

  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.select-oa-row",
    visibleLabel: "陈涛 智能工厂设备商",
    actionType: "click",
  }, async (mark) => {
    await openOaGroup.getByRole("row", { name: /陈涛.*智能工厂设备商/ }).click();
    await mark("firstVisibleResponseLatencyMs", expect(openZone.getByText("已选 1")).toBeVisible());
    await mark("finalSettledLatencyMs", expect(openZone.getByText("已选 1")).toBeVisible());
  });

  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.select-bank-row",
    visibleLabel: "2026-03-28 智能工厂设备商",
    actionType: "click",
  }, async (mark) => {
    await openBankGroup.getByRole("row", { name: /2026-03-28.*智能工厂设备商/ }).click();
    await mark("firstVisibleResponseLatencyMs", expect(openZone.getByText("已选 2")).toBeVisible());
    await mark("finalSettledLatencyMs", expect(openZone.getByText("已选 2")).toBeVisible());
  });

  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.select-invoice-row",
    visibleLabel: "91330108MA27B4011D 杭州溯源科技有限公司",
    actionType: "click",
  }, async (mark) => {
    await openInvoiceGroup.getByRole("row", { name: /91330108MA27B4011D.*杭州溯源科技有限公司/ }).click();
    await mark("firstVisibleResponseLatencyMs", expect(openZone.getByText("已选 3")).toBeVisible());
    await mark("finalSettledLatencyMs", expect(openZone.getByText("已选 3")).toBeVisible());
  });

  const previewDialog = page.getByRole("dialog", { name: "关联预览" });
  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.open-confirm-preview",
    visibleLabel: "确认关联",
    actionType: "click",
  }, async (mark) => {
    const previewResponse = page.waitForResponse(isPostTo("/api/workbench/actions/confirm-link/preview"));
    await openZone.getByRole("button", { name: "确认关联" }).click();
    await mark("apiLatencyMs", previewResponse);
    await mark("firstVisibleResponseLatencyMs", expect(previewDialog).toBeVisible());
    await expect(previewDialog.getByTestId("relation-preview-before").getByText("智能工厂设备商").first()).toBeVisible();
    await mark(
      "finalSettledLatencyMs",
      expect(previewDialog.getByTestId("relation-preview-after").getByText("完全关联").first()).toBeVisible(),
    );
  });

  await runOperation(recordLatency, {
    route: "/",
    pageKey: "reconciliation-workbench",
    module: "reconciliation-workbench",
    operationId: "reconciliation-workbench.confirm-relation",
    visibleLabel: "确认关联",
    actionType: "click",
  }, async (mark) => {
    const confirmResponse = page.waitForResponse(isPostTo("/api/workbench/actions/confirm-link"));
    await previewDialog.getByRole("button", { name: "确认关联" }).click();
    await mark("apiLatencyMs", confirmResponse);
    const pairedGroup = page.getByTestId("candidate-group-paired-case:CASE-202603-101");
    await mark("firstVisibleResponseLatencyMs", expect(pairedGroup).toBeVisible());
    await mark("finalSettledLatencyMs", expect(pairedGroup).toBeVisible());
  });
  await expectNoUnexpectedSuccessUiErrors(page);
}
