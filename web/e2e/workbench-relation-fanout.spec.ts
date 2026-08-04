import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relation browser flow", () => {
  test("aligns an exact daily reimbursement invoice while OA items remain selectable", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchOaExpenseItemsScenario: true,
    });

    await page.goto("/");

    await expect(page.getByText("多个项目 · 3")).toBeVisible();
    await expect(page.getByText("¥324.80")).toBeVisible();
    const itemBand = page.getByTestId(
      "candidate-group-segment-unpaired-row:oa-exp-2035-oa-exp-2035:item:1",
    );
    const projectItem = itemBand.getByText("云南溯源科技", { exact: true });
    await expect(projectItem).toBeVisible();
    await expect(itemBand.getByText("中国石油云南销售公司", { exact: true })).toBeVisible();

    const unmatchedItemBand = page.getByTestId(
      "candidate-group-segment-unpaired-row:oa-exp-2035-oa-exp-2035:item:0",
    );
    await expect(unmatchedItemBand.getByText("中国石油云南销售公司", { exact: true })).toHaveCount(0);
    const invoicePane = page.getByTestId(
      "candidate-scroll-unpaired-row:oa-exp-2035-oa-exp-2035:item:1-invoice",
    );
    const oaItemPane = page.getByTestId(
      "candidate-scroll-unpaired-row:oa-exp-2035-oa-exp-2035:item:1-oa",
    );
    const attachmentInvoice = invoicePane.getByText("中国石油云南销售公司", { exact: true });
    await expect(attachmentInvoice).toBeVisible();
    const [oaItemPaneBox, invoicePaneBox, invoiceRowBox] = await Promise.all([
      oaItemPane.boundingBox(),
      invoicePane.boundingBox(),
      invoicePane.getByRole("row").boundingBox(),
    ]);
    expect(oaItemPaneBox).not.toBeNull();
    expect(invoicePaneBox).not.toBeNull();
    expect(invoiceRowBox).not.toBeNull();
    expect(Math.abs((invoicePaneBox?.height ?? 0) - (oaItemPaneBox?.height ?? 0))).toBeLessThanOrEqual(2);
    expect(Math.abs((invoiceRowBox?.height ?? 0) - (invoicePaneBox?.height ?? 0))).toBeLessThanOrEqual(2);

    const compositeBand = page.getByTestId(
      "candidate-group-segment-unpaired-row:oa-exp-2035-oa-exp-2035:item:2",
    );
    const compositeOaPane = page.getByTestId(
      "candidate-scroll-unpaired-row:oa-exp-2035-oa-exp-2035:item:2-oa",
    );
    const compositeInvoicePane = page.getByTestId(
      "candidate-scroll-unpaired-row:oa-exp-2035-oa-exp-2035:item:2-invoice",
    );
    await expect(compositeBand.getByText("76.80", { exact: true })).toBeVisible();
    await expect(compositeInvoicePane.getByText("29.00", { exact: true })).toBeVisible();
    await expect(compositeInvoicePane.getByText("47.80", { exact: true })).toBeVisible();
    const [compositeOaBox, compositeInvoiceBox, compositeInvoiceRowBoxes] = await Promise.all([
      compositeOaPane.boundingBox(),
      compositeInvoicePane.boundingBox(),
      compositeInvoicePane.getByRole("row").evaluateAll((rows) => rows.map((row) => {
        const box = row.getBoundingClientRect();
        return { y: box.y, height: box.height };
      })),
    ]);
    expect(compositeOaBox).not.toBeNull();
    expect(compositeInvoiceBox).not.toBeNull();
    expect(compositeInvoiceRowBoxes).toHaveLength(2);
    expect(Math.abs((compositeInvoiceBox?.height ?? 0) - (compositeOaBox?.height ?? 0))).toBeLessThanOrEqual(2);
    expect(Math.abs(
      compositeInvoiceRowBoxes.reduce((height, row) => height + row.height, 0)
      - (compositeInvoiceBox?.height ?? 0),
    )).toBeLessThanOrEqual(4);

    await projectItem.click();
    await expect(page.getByText("OA 1 / 324.80")).toBeVisible();
  });

  test("confirms a relation in workbench and reflects it in bank details", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchConfirmPreviewDelayMs: 250,
    });
    const recordLatency = createOperationLatencyRecorder(page, testInfo, {
      route: "/",
      pageKey: "reconciliation-workbench",
      module: "reconciliation-workbench",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    const bankRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowBefore).toBeVisible();
    await expect(bankRowBefore.getByText("无oa")).toBeVisible();
    await expect(bankRowBefore.getByText("无发票")).toBeVisible();
    const bankTransactionRequestCountBefore = api.count("GET /api/bank-details/transactions");

    await confirmWorkbenchRelation(page, recordLatency, async () => {
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeVisible();
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeDisabled();
    });

    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(1);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);

    await recordLatency({
      route: "/bank-details",
      pageKey: "bank-details",
      module: "bank-details",
      operationId: "bank-details.open-after-workbench-confirm",
      visibleLabel: "银行明细",
      actionType: "click",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return url.pathname === "/api/bank-details/transactions" && response.request().method() === "GET";
      });
      await page.getByRole("link", { name: "银行明细" }).click();
      await mark("apiLatencyMs", rowsResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("bank-details-page")).toBeVisible());
      await mark(
        "finalSettledLatencyMs",
        expect(page.getByRole("row", { name: /智能工厂设备商/ }).getByText("有发票")).toBeVisible(),
      );
    });
    const bankRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(bankRowAfter.getByText("有oa")).toBeVisible();
    await expect(bankRowAfter.getByText("有发票")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/bank-details/transactions")).toBeGreaterThan(bankTransactionRequestCountBefore);
  });
});
