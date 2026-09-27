import { fetchInputInvoiceUsageBankTransactionDetail, fetchInputInvoiceUsageInvoiceDetail, fetchInputInvoiceUsageOaDetail, fetchInputInvoiceUsageRowRelationDetail } from "../features/inputInvoiceUsage/api";
import { fetchOutputInvoiceCollectionBankTransactionDetail, fetchOutputInvoiceCollectionInvoiceDetail, fetchOutputInvoiceCollectionRowRelationDetail } from "../features/outputInvoiceCollections/api";

function sourceResponse(payload: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), {
    status: 200, headers: { "Content-Type": "application/json" },
  })));
}

afterEach(() => vi.unstubAllGlobals());

test.each([fetchInputInvoiceUsageInvoiceDetail, fetchOutputInvoiceCollectionInvoiceDetail])("invoice detail preserves every source line without substituting group totals or missing tax", async (loadDetail) => {
  sourceResponse({ id: "internal-id", invoiceNo: "SOURCE-INVOICE", invoiceStatus: "正常", isPositiveInvoice: false,
    amount: "", taxAmount: "", totalWithTax: "", lineItems: [
      { taxableItemName: "第一条真实项目", amount: "100.00", taxAmount: "0.00", totalWithTax: "100.00" },
      { taxableItemName: "第二条真实项目", amount: "50.00", taxAmount: null, totalWithTax: null },
    ],
  });
  const detail = await loadDetail("internal-id");
  const lines = detail.sections.filter(section => section.title.startsWith("货物或应税劳务明细"));
  expect(lines).toHaveLength(2);
  expect(lines[0].fields).toContainEqual({ label: "税额", value: "0.00" });
  expect(lines[1].fields).not.toContainEqual({ label: "税额", value: "0.00" });
  const fields = detail.sections.flatMap(section => section.fields);
  expect(fields).toContainEqual({ label: "发票状态", value: "正常" });
  expect(fields.some(field => field.label === "是否正数发票" && ["false", "否"].includes(String(field.value)))).toBe(true);
  expect(fields.some(field => field.value === "150.00" || field.value === "internal-id")).toBe(false);
});

test.each([fetchInputInvoiceUsageBankTransactionDetail, fetchOutputInvoiceCollectionBankTransactionDetail])("bank detail uses source date and full account instead of configured or inferred display data", async (loadDetail) => {
  sourceResponse({ id: "bank-1", transactionDate: "2026-09-27", accountNo: "SOURCE-ACCOUNT", amount: "0.00",
    tradeTime: "2026-09-27 00:00:00", bankName: "用户设置银行", accountLast4: "1234", status: "pending", remark: "normal" });
  const detail = await loadDetail("bank-1");
  const fields = detail.sections.flatMap(section => section.fields);
  expect(fields).toContainEqual({ label: "交易日期", value: "2026-09-27" });
  expect(fields.some(field => field.value === "SOURCE-ACCOUNT")).toBe(true);
  expect(fields).toContainEqual({ label: "金额", value: "0.00" });
  for (const inferred of ["2026-09-27 00:00:00", "用户设置银行", "1234", "pending"]) {
    expect(fields.some(field => field.value === inferred)).toBe(false);
  }
});

test("OA without source process status does not substitute operational workflow status", async () => {
  sourceResponse({ detailAvailable: true, applicantName: "真实申请人", workflowStatus: "completed", detailFields: {} });
  const detail = await fetchInputInvoiceUsageOaDetail("oa-1");
  expect(detail.sections.flatMap(section => section.fields).some(field => field.label === "流程状态")).toBe(false);
});

test.each([fetchInputInvoiceUsageRowRelationDetail, fetchOutputInvoiceCollectionRowRelationDetail])("empty relation source sections never reconstruct facts from poisoned business summaries", async loadDetail => {
  sourceResponse({ kind: "bank", sections: [], summaries: [{ id: "private-bank", counterpartyName: "推断对方", amount: "999.00", status: "pending", workflowStatus: "completed" }] });
  const detail = await loadDetail({ kind: "relationList", id: "relation-row", relationKind: "bank" });
  expect(detail.sections).toEqual([]);
});

test.each([fetchInputInvoiceUsageRowRelationDetail, fetchOutputInvoiceCollectionRowRelationDetail])("relation source sections retain exact bank identity and original zero", async loadDetail => {
  sourceResponse({ kind: "bank", sections: [{ title: "银行流水 1", bank_transaction_id: "source-bank", fields: [
    { label: "备注", value: "原始备注" }, { label: "余额", value: 0 },
  ] }], summaries: [{ id: "wrong-bank", counterpartyName: "不可信摘要" }] });
  const detail = await loadDetail({ kind: "relationList", id: "relation-row", relationKind: "bank" });
  expect(detail.sections).toEqual([{ title: "银行流水 1", bank_transaction_id: "source-bank", fields: [
    { label: "备注", value: "原始备注" }, { label: "余额", value: "0" },
  ] }]);
});
