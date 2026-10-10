import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks, pendingInvoiceRowsPayload } from "./fixtures/apiMocks";
import { pendingAcquisitionFixture } from "../src/test/pendingInvoiceFixtures";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { dragSelectVisibleText } from "./fixtures/textSelection";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
}

test.describe("pending invoices browser flow", () => {
  test("allows selecting text in the pending invoice table body", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-text-selection",
      visibleLabel: "流水待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const counterpartyName = page.locator(".pending-invoices-counterparty-name").filter({ hasText: "智能工厂设备商" }).first();
    await expect(counterpartyName).toBeVisible();

    await recordLatency({
      operationId: "pending-invoices.select-counterparty-text",
      visibleLabel: "智能工厂设备商",
      actionType: "select",
    }, async (mark) => {
      await dragSelectVisibleText(page, counterpartyName);
      await mark("finalSettledLatencyMs", expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).toContain("智能工厂设备"));
    });

    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? "")).toContain("智能工厂设备");
  });

  test("reflects workbench confirmed invoice relation in pending invoices", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-fanout",
      visibleLabel: "流水待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
    });
    const pendingRowBefore = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowBefore).toBeVisible();
    await expect(pendingRowBefore.getByText("已支付待开票")).toBeVisible();
    await expect(pendingRowBefore.getByText("12561048")).toHaveCount(0);
    const pendingRowsBefore = api.count("GET /api/pending-invoices/rows");

    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "pending-invoices.return-after-fanout-confirm",
      visibleLabel: "流水待找发票",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "流水待找发票" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
      await expect.poll(() => api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore);
    });
    const pendingRowAfter = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(pendingRowAfter.getByText("已支付已开票")).toBeVisible();
    await expect(pendingRowAfter.getByText("12561048")).toBeVisible();
    await expect(pendingRowAfter.getByText("陈涛")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(pendingRowsBefore);
  });
});

test("transaction time chips remain visible inside identity cells at narrow desktop width", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/pending-invoices");
  const chips = page.locator(".pending-invoices-trade-time");
  await expect(chips.first()).toBeVisible();
  const geometry = await chips.evaluateAll((nodes) => nodes.map((node) => {
    const chip = node.getBoundingClientRect();
    const cell = node.closest("td")!.getBoundingClientRect();
    return { text: node.textContent, fits: chip.left >= cell.left && chip.right <= cell.right && chip.bottom <= cell.bottom };
  }));
  expect(geometry.length).toBeGreaterThan(0);
  expect(geometry.every((item) => item.fits && Boolean(item.text))).toBe(true);
});


test("related invoices stay in nine original columns, use member amounts and preserve case context", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
  const payload = pendingInvoiceRowsPayload(true);
  const row: any = payload.rows[0];
  const firstCase = "CASE-202603-101";
  const secondCase = "CASE-OTHER";
  row.bank_transaction.original_amount = "58000.00";
  row.bank_transactions = {
    primary: { ...row.bank_transaction, relation_case_id: firstCase },
    relation_count: 2, linked_relation_count: 2, has_multiple: true, detail_mode: "list",
    original_amount: "58300.00", original_transaction_count: 2,
    summaries: [{ ...row.bank_transaction, relation_case_id: firstCase },
      { ...row.bank_transaction, id: "bank-extra", counterparty_name: "另一配对供应商", amount: "300.00", original_amount: "300.00", debit_amount: "300.00", relation_case_id: secondCase }],
    payment_summary: { paid_total: "58300.00" },
  };
  const invoice = row.input_invoices.summaries[0];
  row.input_invoices = { ...row.input_invoices, relation_count: 3, has_multiple: true,
    summaries: [invoice,
      { ...invoice, id: "invoice-extra-red", invoice_no: "EXP-RED", total_with_tax: "-20.00" },
      { ...invoice, id: "invoice-extra-other", invoice_no: "EXP-OTHER", seller_name: "另一配对供应商", total_with_tax: "100.00", relation_case_id: secondCase }],
  };
  const oa = row.oa.primary;
  row.oa = { ...row.oa, relation_count: 2, has_multiple: true, summaries: [oa,
    { ...oa, id: "oa-extra", applicant: "另一申请人", relation_case_id: secondCase }],
  };
  row.relation_case_ids = [firstCase, secondCase];
  (payload as any).acquisition_summary = pendingAcquisitionFixture(payload.rows);
  await page.route("**/api/pending-invoices/rows**", route => route.fulfill({ json: payload }));
  await page.goto("/pending-invoices");
  const table = page.getByRole("grid", { name: "待找发票四区表" });
  const invoiceButton = table.getByRole("button", { name: "展开配对关系，发票共 3 张" });
  await expect(invoiceButton).toBeVisible();
  const requests = api.calls.length;
  await invoiceButton.click();
  const rows = table.locator("tr[data-relation-group]");
  await expect(rows).toHaveCount(3);
  await expect(page.getByRole("region", { name: "配对关系" })).toHaveCount(0);
  for (const item of await rows.all()) await expect(item.locator("td,th")).toHaveCount(9);
  await expect(rows.locator(".relation-motion-clip")).toHaveCount(18);
  await expect(rows.nth(1).locator(".pending-invoices-col-invoice-no")).toContainText("EXP-RED");
  await expect(rows.nth(1).locator(".pending-invoices-col-invoice-amount")).toHaveText("-20.00");
  await expect(rows.nth(1).locator(".pending-invoices-col-amount")).toContainText("58000.00");
  await expect(rows.nth(2).locator(".pending-invoices-col-oa-applicant")).toContainText("另一申请人");
  await expect(rows.nth(2).locator(".pending-invoices-col-amount")).toContainText("300.00");
  await expect(rows.nth(2).locator(".pending-invoices-col-invoice-amount")).toHaveText("100.00");
  const geometry = await rows.evaluateAll(nodes => nodes.map(node => [...node.querySelectorAll("td,th")].map(cell => ({ x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width }))));
  expect(geometry[1]).toEqual(geometry[0]);
  expect(geometry[2]).toEqual(geometry[0]);
  expect(api.calls.length).toBe(requests);
  await page.screenshot({ path: info.outputPath("pending-original-column-expansion.png"), animations: "disabled" });
  await table.getByRole("button", { name: "展开配对关系，流水共 2 笔" }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1).locator(".pending-invoices-col-counterparty")).toContainText("另一配对供应商");
  await table.getByRole("button", { name: "展开配对关系，OA共 2 条" }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1).locator(".pending-invoices-col-oa-applicant")).toContainText("另一申请人");
  await table.getByRole("button", { name: "收起配对关系，OA共 2 条" }).click();
  await expect(rows).toHaveCount(0);
  expect(api.calls.length).toBe(requests);
});
