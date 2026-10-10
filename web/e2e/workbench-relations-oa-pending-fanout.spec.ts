import { expect, test } from "./fixtures/strictTest";

import { installDeterministicApiMocks, oaPendingPaymentRowsPayload } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { confirmWorkbenchRelation } from "./fixtures/workbenchFlow";

test.describe("workbench relations OA pending payment browser fan-out", () => {
  test("refreshes OA pending payment rows after a workbench relation is confirmed", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentRelationFanout: true,
      sessionMode: "user",
    });
    const recordLatency = createOperationLatencyRecorder(page, testInfo, {
      route: "/oa-pending-payments",
      pageKey: "oa-pending-payments",
      module: "oa-pending-payments",
    });

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    const rowBefore = page.getByRole("row", { name: /陈涛/ });
    await expect(rowBefore).toBeVisible();
    await expect(rowBefore.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("待支付");
    await expect(rowBefore.getByText("候选")).toHaveCount(0);
    const rowsBefore = api.count("GET /api/oa-pending-payments/rows");

    await confirmWorkbenchRelation(page, recordLatency);
    expect(api.count("POST /api/workbench/actions/confirm-link")).toBe(1);

    await recordLatency({
      operationId: "oa-pending-payments.open-after-workbench-confirm",
      visibleLabel: "OA付款情况",
      actionType: "click",
    }, async (mark) => {
      const rowsResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/rows"),
      );
      await page.getByRole("link", { name: "OA付款情况" }).click();
      await mark("apiLatencyMs", rowsResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("oa-pending-payments-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /陈涛/ })).toContainText("已支付"));
    });
    const rowAfter = page.getByRole("row", { name: /陈涛/ });
    await expect(rowAfter.locator(".oa-pending-payment-status-cell .finance-status-tag")).toHaveText("已支付");
    await expect(rowAfter.getByText("候选")).toHaveCount(0);
    await expect(rowAfter).toContainText("关联台已确认");
    await expect(rowAfter).toContainText("智能工厂设备商");
    await expect(rowAfter).toContainText("12561048");
    await expect(rowAfter).toContainText("58000.00");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThan(rowsBefore);
  });
});


test("OA groups expand real members in original four regions and keep each source amount", async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
  const payload = oaPendingPaymentRowsPayload();
  const row: any = payload.rows[0];
  const firstCase = "OA-EXP-CASE";
  const secondCase = "OA-EXP-OTHER";
  row.oa = { ...row.oa, amount: "15000.00", relationCount: 3, detailMode: "list", hasMultiple: true,
    summaries: [{ ...row.oa, oaId: row.oa.id, amount: "12000.00", workflowStatus: "completed", relationCaseId: firstCase },
      { ...row.oa, oaId: "oa-exp-2", applicantName: "第二申请人", amount: "2000.00", workflowStatus: "completed", relationCaseId: firstCase },
      { ...row.oa, oaId: "oa-exp-3", applicantName: "第三申请人", amount: "1000.00", workflowStatus: "completed", relationCaseId: secondCase }],
  };
  row.bankTransaction = { ...row.bankTransaction, original_amount: "8500.00", original_transaction_count: 2, relationCount: 2, hasMultiple: true, detailMode: "list", nonOutflowRelationEdges: [],
    summaries: [{ ...row.bankTransaction, bankTransactionId: row.bankTransaction.primaryBankTransactionId, original_amount: "8000.00", relationCaseId: firstCase },
      { ...row.bankTransaction, bankTransactionId: "bank-exp-2", counterpartyName: "另一个收款方", original_amount: "500.00", relationCaseId: secondCase }],
  };
  row.invoice = { ...row.invoice, totalWithTax: "12500.00", relationCount: 2, hasMultiple: true, detailMode: "list",
    summaries: [{ ...row.invoice, invoiceId: row.invoice.primaryInvoiceId, totalWithTax: "12000.00", relationCaseId: firstCase },
      { ...row.invoice, invoiceId: "invoice-exp-2", digitalInvoiceNo: "OA-EXP-RED", sellerName: "另一个收款方", totalWithTax: "-500.00", relationCaseId: secondCase }],
  };
  await page.route("**/api/oa-pending-payments/rows**", route => route.fulfill({ json: payload }));
  await page.goto("/oa-pending-payments");
  const table = page.getByRole("grid", { name: "OA待付款核对表格" });
  const opener = table.getByRole("button", { name: "展开配对关系，OA共 3 条" });
  await expect(opener).toBeVisible();
  const requests = api.calls.length;
  await opener.click();
  const rows = table.locator("tr[data-relation-group]");
  await expect(rows).toHaveCount(3);
  await expect(page.getByRole("region", { name: "配对关系" })).toHaveCount(0);
  for (const item of await rows.all()) await expect(item.locator("td,th")).toHaveCount(4);
  await expect(rows.locator(".relation-motion-clip")).toHaveCount(8);
  await expect(rows.nth(1).locator(".oa-pending-payments-oa-grid__amount")).toHaveText("2000.00");
  await expect(rows.nth(1).locator(".oa-pending-payments-bank-amount-line")).toHaveText("8000.00");
  await expect(rows.nth(2).locator(".oa-pending-payments-oa-grid__amount")).toHaveText("1000.00");
  await expect(rows.nth(2).locator(".oa-pending-payments-bank-amount-line")).toHaveText("500.00");
  await expect(rows.nth(2).locator(".oa-pending-payments-invoice-amount-line")).toHaveText("-500.00");
  const geometry = await rows.evaluateAll(nodes => nodes.map(node => [...node.querySelectorAll("td,th")].map(cell => ({ x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width }))));
  expect(geometry[1]).toEqual(geometry[0]);
  expect(geometry[2]).toEqual(geometry[0]);
  expect(api.calls.length).toBe(requests);
  await page.screenshot({ path: info.outputPath("oa-original-column-expansion.png"), animations: "disabled" });
  await table.getByRole("button", { name: "展开配对关系，发票共 2 张" }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1).locator(".oa-pending-payments-invoice-amount-line")).toHaveText("-500.00");
  await expect(rows.nth(1).locator(".oa-pending-payments-oa-grid__applicant")).toContainText("第三申请人");
  await table.getByRole("button", { name: "展开配对关系，流水共 2 笔" }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1).locator(".oa-pending-payments-bank-amount-line")).toHaveText("500.00");
  await table.getByRole("button", { name: "收起配对关系，流水共 2 笔" }).click();
  await expect(rows).toHaveCount(0);
  expect(api.calls.length).toBe(requests);
});
