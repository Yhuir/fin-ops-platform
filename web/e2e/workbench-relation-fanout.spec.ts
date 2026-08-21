import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relation browser flow", () => {
  test("opens one OA invoice supplement drawer with invoice entry as the primary mode", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchOaInvoiceUnparsedScenario: true,
    });

    await page.goto("/");

    const unpairedZone = page.getByTestId("zone-unpaired");
    await unpairedZone.getByRole("button", { name: "录入发票" }).click();

    const drawer = page.getByRole("dialog", { name: "录入发票" });
    await expect(drawer).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    const modeTabs = drawer.getByRole("tablist", { name: "录入方式" });
    await expect(modeTabs.getByRole("tab").nth(0)).toHaveText("发票录入");
    await expect(modeTabs.getByRole("tab").nth(1)).toHaveText("补充凭证");
    await expect(modeTabs.getByRole("tab", { name: "发票录入" })).toHaveAttribute("aria-selected", "true");
    await expect(modeTabs.getByRole("tab", { name: "补充凭证" })).toHaveAttribute("aria-selected", "false");
    await expect(drawer.getByRole("tab", { name: "新发票1" })).toBeVisible();
    await drawer.getByRole("button", { name: "添加发票" }).click();
    await expect(drawer.getByRole("tab", { name: "新发票2" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "确认录入并关联" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: "录入发票池并关联" })).toHaveCount(0);
    expect(api.count("GET /api/workbench/oa-invoice-supplements/documents")).toBe(0);

    await modeTabs.getByRole("tab", { name: "补充凭证" }).click();
    await expect(modeTabs.getByRole("tab", { name: "补充凭证" })).toHaveAttribute("aria-selected", "true");
    await expect(drawer.getByText("不进入统一发票池", { exact: false })).toBeVisible();
    await expect(drawer.getByText("尚未上传补充凭证。", { exact: true })).toBeVisible();
    expect(api.count("GET /api/workbench/oa-invoice-supplements/documents")).toBe(1);
  });

  test("aligns an explicitly owned bank fanout with its parent OA", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchExplicitBankFanoutScenario: true,
    });

    await page.goto("/");

    const segment = page.getByTestId(
      "candidate-group-segment-paired-case:CASE-E2E-EXPLICIT-BANK-FANOUT-oa-bank-fanout-88050",
    );
    const oaPane = page.getByTestId(
      "candidate-scroll-paired-case:CASE-E2E-EXPLICIT-BANK-FANOUT-oa-bank-fanout-88050-oa",
    );
    const bankPane = page.getByTestId(
      "candidate-scroll-paired-case:CASE-E2E-EXPLICIT-BANK-FANOUT-oa-bank-fanout-88050-bank",
    );
    await expect(segment.getByText("88050.00", { exact: true })).toBeVisible();
    await expect(bankPane.getByText("64996.69", { exact: true })).toBeVisible();
    await expect(bankPane.getByText("23053.31", { exact: true })).toBeVisible();
    await expect(bankPane.getByRole("row")).toHaveCount(2);
    await expect(page.getByTestId(
      "candidate-group-segment-paired-case:CASE-E2E-EXPLICIT-BANK-FANOUT-oa-bank-fanout-88050:bank:residual",
    )).toHaveCount(0);

    const [oaBox, bankBox, bankRowBoxes] = await Promise.all([
      oaPane.boundingBox(),
      bankPane.boundingBox(),
      bankPane.getByRole("row").evaluateAll((rows) => rows.map((row) => {
        const box = row.getBoundingClientRect();
        return { y: box.y, height: box.height };
      })),
    ]);
    expect(oaBox).not.toBeNull();
    expect(bankBox).not.toBeNull();
    expect(bankRowBoxes).toHaveLength(2);
    expect(Math.abs((bankBox?.height ?? 0) - (oaBox?.height ?? 0))).toBeLessThanOrEqual(2);
    expect(Math.abs(
      bankRowBoxes.reduce((height, row) => height + row.height, 0)
      - (bankBox?.height ?? 0),
    )).toBeLessThanOrEqual(4);
  });

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

    await itemBand.getByRole("row", { name: /云南溯源科技 200/ }).getByRole("cell").first().click();
    await expect(page.getByText("OA 1 / 324.80")).toBeVisible();
  });

  test("assigns a residual invoice through explicit OA-item ownership and canonical reread", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchInvoiceAssignmentScenario: true,
    });

    await page.goto("/");

    const residualSegment = page.getByTestId(
      "candidate-group-segment-unpaired-case:CASE-E2E-INVOICE-ASSIGNMENT-oa-e2e-invoice-assignment:invoice:unassigned",
    );
    await expect(residualSegment.getByText("云南天谷科技开发有限公司", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "录入发票" })).toHaveCount(0);

    const anomalyTrigger = residualSegment.getByRole("button", {
      name: "该发票有 1 项异常，查看详情",
    });
    await anomalyTrigger.hover();
    await page.getByRole("button", { name: "选择 OA 明细" }).click();

    const drawer = page.getByRole("dialog", { name: "选择 OA 明细" });
    await expect(drawer).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    const firstItem = drawer.getByRole("checkbox", { name: /^大理项目，27\.05，/ });
    const secondItem = drawer.getByRole("checkbox", { name: /^曲靖项目，38\.95，/ });
    await expect(firstItem).not.toBeChecked();
    await expect(secondItem).not.toBeChecked();
    await expect(drawer.getByRole("button", { name: "确认归属" })).toBeDisabled();

    await drawer.getByText("大理项目", { exact: true }).click();
    await expect(firstItem).toBeChecked();
    const workbenchReadsBeforeSubmit = api.count("GET /api/workbench");
    await drawer.getByRole("button", { name: "确认归属" }).click();

    await expect(drawer).toBeHidden();
    expect(api.count("POST /api/workbench/actions/assign-invoice-expense-items")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/assign-invoice-expense-items")).toMatchObject({
      case_id: "CASE-E2E-INVOICE-ASSIGNMENT",
      invoice_row_id: "invoice-e2e-unassigned-27-05",
      targets: [{
        oa_row_id: "oa-e2e-invoice-assignment",
        expense_item_id: "oa-e2e-invoice-assignment:item:0",
      }],
      anomaly_fingerprint: "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
      idempotency_key: expect.any(String),
    });
    expect(api.count("GET /api/workbench")).toBe(workbenchReadsBeforeSubmit + 1);
    await expect(residualSegment).toHaveCount(0);
    await expect(page.getByRole("button", { name: "该发票有 1 项异常，查看详情" })).toHaveCount(0);

    const assignedSegment = page.getByTestId(
      "candidate-group-segment-paired-case:CASE-E2E-INVOICE-ASSIGNMENT-oa-e2e-invoice-assignment:item:0",
    );
    const assignedOaPane = page.getByTestId(
      "candidate-scroll-paired-case:CASE-E2E-INVOICE-ASSIGNMENT-oa-e2e-invoice-assignment:item:0-oa",
    );
    const assignedInvoicePane = page.getByTestId(
      "candidate-scroll-paired-case:CASE-E2E-INVOICE-ASSIGNMENT-oa-e2e-invoice-assignment:item:0-invoice",
    );
    await expect(assignedSegment.getByText("云南天谷科技开发有限公司", { exact: true })).toBeVisible();
    const [oaBox, invoiceBox] = await Promise.all([
      assignedOaPane.boundingBox(),
      assignedInvoicePane.boundingBox(),
    ]);
    expect(oaBox).not.toBeNull();
    expect(invoiceBox).not.toBeNull();
    expect(Math.abs((oaBox?.y ?? 0) - (invoiceBox?.y ?? 0))).toBeLessThanOrEqual(2);
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

    let workbenchLoadsBeforeSubmit = 0;
    await confirmWorkbenchRelation(page, recordLatency, async () => {
      workbenchLoadsBeforeSubmit = api.count("GET /api/workbench");
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeVisible();
      await expect(page.getByRole("button", { name: "正在准备确认预览" })).toBeDisabled();
    });

    expect(api.count("POST /api/workbench/actions/confirm-link/preview")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/confirm-link/preview")).toMatchObject({
      row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
      row_types: ["oa", "bank", "invoice"],
    });
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);
    expect(api.lastBody("POST /api/workbench/actions/confirm-link")).toMatchObject({
      row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
      row_types: ["oa", "bank", "invoice"],
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/workbench")).toBe(workbenchLoadsBeforeSubmit + 1);

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
