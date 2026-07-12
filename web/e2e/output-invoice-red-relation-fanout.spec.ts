import { expect, test, type Page, type Download, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { readXlsxText } from "./fixtures/xlsx";

function createOutputInvoiceRedRelationLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/output-invoice-collections",
    pageKey: "output-invoice-collections",
    module: "output-invoice-collections",
  });
}

test.describe("output invoice red relation browser fan-out", () => {
  test("confirms a red invoice relation, exports relation fields, refreshes cost downstream, and revokes it", async ({ page }, testInfo) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceDownstreamFanout: true,
      outputInvoiceRedRelationCandidate: true,
      sessionMode: "full_access",
    });
    const recordLatency = createOutputInvoiceRedRelationLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "output-invoice-collections.open-page-red-relation",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) =>
        response.url().includes("/api/output-invoice-collections/rows")
          && response.request().method() === "GET",
      );
      await gotoAndExpectPageReady(page, "/output-invoice-collections", "output-invoice-collections-page", { diagnostics });
      await mark("apiLatencyMs", rowsResponse);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });

    const sourceRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(sourceRow).toBeVisible();
    await expect(sourceRow.getByText("待收款，已收部分款")).toBeVisible();
    await expect(page.getByRole("row", { name: /XSFP-E2E-0002/ })).toBeVisible();

    const rowsBeforeConfirm = api.count("GET /api/output-invoice-collections/rows");
    const relationDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await recordLatency({
      operationId: "output-invoice-collections.open-red-relation-drawer",
      visibleLabel: "红蓝票",
      actionType: "click",
    }, async (mark) => {
      await sourceRow.getByRole("button", { name: "红蓝票" }).click();
      await mark("finalSettledLatencyMs", expect(relationDrawer).toBeVisible());
    });
    await expect(relationDrawer).toBeVisible();
    await expect(relationDrawer.getByText("已有依据")).toHaveCount(0);

    await recordLatency({
      operationId: "output-invoice-collections.edit-red-relation-evidence",
      visibleLabel: "确认依据",
      actionType: "fill",
    }, async (mark) => {
      await relationDrawer.locator("label").filter({ hasText: "XSFP-E2E-0002" }).getByRole("radio").check();
      await relationDrawer.getByLabel("确认依据").fill("浏览器 e2e 红蓝票关系确认");
      await mark("finalSettledLatencyMs", expect(relationDrawer.getByRole("button", { name: "确认关系" })).toBeEnabled());
    });

    await recordLatency({
      operationId: "output-invoice-collections.confirm-red-relation",
      visibleLabel: "确认关系",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = page.waitForResponse((response) =>
        response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")
          && response.request().method() === "POST",
      );
      await relationDrawer.getByRole("button", { name: "确认关系" }).click();
      expect((await mark("apiLatencyMs", confirmResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeConfirm));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "红蓝票关系" })).toBeHidden());
    });
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toBe(1);
    expect(api.lastBody("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toMatchObject({
      relatedInvoiceId: "out-e2e-002",
      relationType: "red_invoice",
      evidence: "浏览器 e2e 红蓝票关系确认",
    });
    await expect(page.getByRole("dialog", { name: "红蓝票关系" })).toBeHidden();

    const refreshedRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(refreshedRow.getByText("待冲红")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await recordLatency({
      operationId: "output-invoice-collections.open-export-preview-red-relation",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const exportPreviewResponsePromise = page.waitForResponse((response) =>
        response.url().includes("/api/output-invoice-collections/export-preview")
          && response.request().method() === "GET",
      );
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      expect((await mark("apiLatencyMs", exportPreviewResponsePromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(exportDrawer).toBeVisible());
    });
    await expect(exportDrawer).toBeVisible();
    const exportPreviewTable = exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" });
    await expect(exportPreviewTable).toContainText("红蓝票关系");
    await expect(exportPreviewTable).toContainText("红蓝票来源");
    await expect(exportPreviewTable).toContainText("红蓝票依据");
    await expect(exportPreviewTable).toContainText("XSFP-E2E-0002");
    await expect(exportPreviewTable).toContainText("manual");
    await expect(exportPreviewTable).toContainText("浏览器 e2e 红蓝票关系确认");

    let exportResponseStatus: number | undefined;
    let download: Download | undefined;
    await recordLatency({
      operationId: "output-invoice-collections.download-export-red-relation",
      visibleLabel: "下载导出",
      actionType: "click",
    }, async (mark) => {
      const exportResponsePromise = page.waitForResponse((response) =>
        response.url().includes("/api/output-invoice-collections/export")
          && response.request().method() === "GET",
      );
      const downloadPromise = page.waitForEvent("download");
      await exportDrawer.getByRole("button", { name: "下载导出" }).click();
      exportResponseStatus = (await mark("apiLatencyMs", exportResponsePromise)).status();
      download = await mark("finalSettledLatencyMs", downloadPromise);
    });
    if (!download) {
      throw new Error("missing output invoice red relation export download");
    }
    expect(exportResponseStatus).toBe(200);
    expect(download.suggestedFilename()).toBe("output-invoice-collections.xlsx");
    const savePath = testInfo.outputPath("output-invoice-collections-red-relation.xlsx");
    await download.saveAs(savePath);
    const downloadedText = await readXlsxText(savePath);
    expect(downloadedText).toContain("红蓝票关系");
    expect(downloadedText).toContain("红蓝票来源");
    expect(downloadedText).toContain("红蓝票依据");
    expect(downloadedText).toContain("XSFP-E2E-0002");
    expect(downloadedText).toContain("manual");
    expect(downloadedText).toContain("浏览器 e2e 红蓝票关系确认");
    await recordLatency({
      operationId: "output-invoice-collections.close-export-red-relation",
      visibleLabel: "关闭销项发票收款情况导出",
      actionType: "click",
    }, async (mark) => {
      await exportDrawer.getByLabel("关闭销项发票收款情况导出").click();
      await mark("finalSettledLatencyMs", expect(exportDrawer).toBeHidden());
    });
    await expect(exportDrawer).toBeHidden();

    const costExplorerRequestCountBeforeDownstream = api.count("GET /api/cost-statistics/explorer");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-output-red-relation",
      visibleLabel: "成本统计",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "成本统计" }).click();
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRequestCountBeforeDownstream));
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRequestCountBeforeDownstream);
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.switch-project-view-after-output-red-relation",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "按项目" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /智能工厂项目/ })).toBeVisible());
    });
    const linkedProject = page.getByRole("button", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58,000.00");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.expand-linked-project-after-output-red-relation",
      visibleLabel: "智能工厂项目",
      actionType: "click",
    }, async (mark) => {
      await linkedProject.click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /设备货款及材料费/ })).toBeVisible());
    });
    const linkedExpenseType = page.getByRole("button", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58,000.00");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.expand-linked-expense-type-after-output-red-relation",
      visibleLabel: "设备货款及材料费",
      actionType: "click",
    }, async (mark) => {
      await linkedExpenseType.click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "项目对应流水表" })).toContainText("智能工厂设备尾款"));
    });
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("智能工厂设备尾款");
    await expect(projectRows).toContainText("智能工厂设备商");

    await recordLatency({
      operationId: "output-invoice-collections.reopen-after-downstream-red-relation",
      visibleLabel: "销项发票收款情况",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/output-invoice-collections", "output-invoice-collections-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect(page.getByTestId("output-invoice-collections-page")).toBeVisible());
    });
    const rowAfterDownstream = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(rowAfterDownstream.getByText("待冲红")).toBeVisible();

    const refreshedDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await recordLatency({
      operationId: "output-invoice-collections.reopen-red-relation-drawer",
      visibleLabel: "红蓝票",
      actionType: "click",
    }, async (mark) => {
      await rowAfterDownstream.getByRole("button", { name: "红蓝票" }).click();
      await mark("finalSettledLatencyMs", expect(refreshedDrawer).toBeVisible());
    });
    await expect(refreshedDrawer).toBeVisible();
    await expect(refreshedDrawer.getByText("已有依据")).toBeVisible();
    await expect(refreshedDrawer.getByText("XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认")).toBeVisible();

    const rowsBeforeRevoke = api.count("GET /api/output-invoice-collections/rows");
    await recordLatency({
      operationId: "output-invoice-collections.revoke-red-relation",
      visibleLabel: "撤销人工关系 XSFP-E2E-0002",
      actionType: "click",
    }, async (mark) => {
      const revokeResponse = page.waitForResponse((response) =>
        response.url().includes("/api/output-invoice-collections/red-invoice-relations/output-red-relation-e2e-001")
          && response.request().method() === "DELETE",
      );
      await refreshedDrawer.getByRole("button", { name: "撤销人工关系 XSFP-E2E-0002" }).click();
      expect((await mark("apiLatencyMs", revokeResponse)).status()).toBe(200);
      await mark("operationBarrierLatencyMs", expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeRevoke));
      await mark("finalSettledLatencyMs", expect(refreshedDrawer.getByText("已有依据")).toHaveCount(0));
    });
    expect(api.count("DELETE /api/output-invoice-collections/red-invoice-relations/output-red-relation-e2e-001")).toBe(1);
    await expect(refreshedDrawer.getByText("已有依据")).toHaveCount(0);
    await expect(refreshedDrawer.getByText("XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认")).toHaveCount(0);
    await expect(rowAfterDownstream.getByText("待收款，已收部分款")).toBeVisible();
    await expect(rowAfterDownstream.getByText("待冲红")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    diagnostics.dispose();
  });
});
