import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { readXlsxText } from "./fixtures/xlsx";

test.describe("output invoice red relation browser fan-out", () => {
  test("confirms a red invoice relation, exports relation fields, refreshes tax/cost downstream, and revokes it", async ({ page }, testInfo) => {
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      outputInvoiceDownstreamFanout: true,
      outputInvoiceRedRelationCandidate: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/output-invoice-collections", "output-invoice-collections-page", { diagnostics });

    const sourceRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(sourceRow).toBeVisible();
    await expect(sourceRow.getByText("待收款，已收部分款")).toBeVisible();
    await expect(page.getByRole("row", { name: /XSFP-E2E-0002/ })).toBeVisible();

    const rowsBeforeConfirm = api.count("GET /api/output-invoice-collections/rows");
    await sourceRow.getByRole("button", { name: "红蓝票" }).click();
    const relationDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await expect(relationDrawer).toBeVisible();
    await expect(relationDrawer.getByText("已有依据")).toHaveCount(0);

    await relationDrawer.locator("label").filter({ hasText: "XSFP-E2E-0002" }).getByRole("radio").check();
    await relationDrawer.getByLabel("确认依据").fill("浏览器 e2e 红蓝票关系确认");

    const confirmResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")
        && response.request().method() === "POST",
    );
    await relationDrawer.getByRole("button", { name: "确认关系" }).click();
    expect((await confirmResponse).status()).toBe(200);
    expect(api.count("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toBe(1);
    expect(api.lastBody("POST /api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations")).toMatchObject({
      relatedInvoiceId: "out-e2e-002",
      relationType: "red_invoice",
      evidence: "浏览器 e2e 红蓝票关系确认",
    });
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeConfirm);
    await expect(page.getByRole("dialog", { name: "红蓝票关系" })).toBeHidden();

    const refreshedRow = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(refreshedRow.getByText("待冲红")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    const exportPreviewResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/export-preview")
        && response.request().method() === "GET",
    );
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const exportPreviewResponse = await exportPreviewResponsePromise;
    expect(exportPreviewResponse.status()).toBe(200);
    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(exportDrawer).toBeVisible();
    const exportPreviewTable = exportDrawer.getByRole("table", { name: "销项发票收款情况导出样例" });
    await expect(exportPreviewTable).toContainText("红蓝票关系");
    await expect(exportPreviewTable).toContainText("红蓝票来源");
    await expect(exportPreviewTable).toContainText("红蓝票依据");
    await expect(exportPreviewTable).toContainText("XSFP-E2E-0002");
    await expect(exportPreviewTable).toContainText("manual");
    await expect(exportPreviewTable).toContainText("浏览器 e2e 红蓝票关系确认");

    const exportResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/export")
        && response.request().method() === "GET",
    );
    const downloadPromise = page.waitForEvent("download");
    await exportDrawer.getByRole("button", { name: "下载导出" }).click();
    const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);
    expect(exportResponse.status()).toBe(200);
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
    await exportDrawer.getByLabel("关闭销项发票收款情况导出").click();
    await expect(exportDrawer).toBeHidden();

    const taxOffsetRequestCountBeforeDownstream = api.count("GET /api/tax-offset");
    await page.getByRole("link", { name: "税金抵扣" }).click();
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    expect(api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetRequestCountBeforeDownstream);
    const taxInputPlanGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(taxInputPlanGrid).toBeVisible();
    await expect(taxInputPlanGrid.getByText("智能工厂设备商")).toBeVisible();
    await expect(taxInputPlanGrid.getByRole("row", { name: /91330108MA27B4011D/ })).toContainText("7,540.00");
    await expect(page.getByText("税金抵扣数据加载失败，请稍后重试。")).toHaveCount(0);

    const costExplorerRequestCountBeforeDownstream = api.count("GET /api/cost-statistics/explorer");
    await page.getByRole("link", { name: "成本统计" }).click();
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(costExplorerRequestCountBeforeDownstream);
    await page.getByRole("button", { name: "按项目" }).click();
    const linkedProject = page.getByRole("button", { name: /智能工厂项目/ });
    await expect(linkedProject).toBeVisible();
    await expect(linkedProject).toContainText("58,000.00");
    await linkedProject.click();
    const linkedExpenseType = page.getByRole("button", { name: /设备货款及材料费/ });
    await expect(linkedExpenseType).toBeVisible();
    await expect(linkedExpenseType).toContainText("58,000.00");
    await linkedExpenseType.click();
    const projectRows = page.getByRole("grid", { name: "项目对应流水表" });
    await expect(projectRows).toContainText("智能工厂设备尾款");
    await expect(projectRows).toContainText("智能工厂设备商");

    await gotoAndExpectPageReady(page, "/output-invoice-collections", "output-invoice-collections-page", { diagnostics });
    const rowAfterDownstream = page.getByRole("row", { name: /XSFP-E2E-0001/ });
    await expect(rowAfterDownstream.getByText("待冲红")).toBeVisible();
    await rowAfterDownstream.getByRole("button", { name: "红蓝票" }).click();

    const refreshedDrawer = page.getByRole("dialog", { name: "红蓝票关系" });
    await expect(refreshedDrawer).toBeVisible();
    await expect(refreshedDrawer.getByText("已有依据")).toBeVisible();
    await expect(refreshedDrawer.getByText("XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认")).toBeVisible();

    const rowsBeforeRevoke = api.count("GET /api/output-invoice-collections/rows");
    const revokeResponse = page.waitForResponse((response) =>
      response.url().includes("/api/output-invoice-collections/red-invoice-relations/output-red-relation-e2e-001")
        && response.request().method() === "DELETE",
    );
    await refreshedDrawer.getByRole("button", { name: "撤销人工关系 XSFP-E2E-0002" }).click();
    expect((await revokeResponse).status()).toBe(200);
    expect(api.count("DELETE /api/output-invoice-collections/red-invoice-relations/output-red-relation-e2e-001")).toBe(1);
    await expect.poll(() => api.count("GET /api/output-invoice-collections/rows")).toBeGreaterThan(rowsBeforeRevoke);
    await expect(refreshedDrawer.getByText("已有依据")).toHaveCount(0);
    await expect(refreshedDrawer.getByText("XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认")).toHaveCount(0);
    await expect(rowAfterDownstream.getByText("待收款，已收部分款")).toBeVisible();
    await expect(rowAfterDownstream.getByText("待冲红")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    diagnostics.dispose();
  });
});
