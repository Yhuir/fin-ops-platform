import { fetchInputInvoiceUsageBankTransactionDetail, fetchInputInvoiceUsageInvoiceDetail, fetchInputInvoiceUsageOaDetail } from "../features/inputInvoiceUsage/api";
import { fetchOutputInvoiceCollectionBankTransactionDetail, fetchOutputInvoiceCollectionInvoiceDetail } from "../features/outputInvoiceCollections/api";

function sourceResponse(payload: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), {
    status: 200, headers: { "Content-Type": "application/json" },
  })));
}

afterEach(() => vi.unstubAllGlobals());

test('OA structured navigation survives the API boundary and never parses a title as source data', async () => {
  const summary = {applicantName: '同名申请人', amount: '0.00', applicationDate: '2026-08-01', workflowNo: '2403'};
  const section = {title: '申请信息', document_id: 'oa-1', document_kind: 'oa', document_title: '错误标题 · 999',
    oa_navigation: summary, fields: [{label: '申请人', value: '同名申请人'}]};
  sourceResponse({sections: [section]});
  expect((await fetchInputInvoiceUsageOaDetail('oa-1')).sections[0].oa_navigation).toEqual(summary);
  for (const invalid of [undefined, {...summary, amount: 0}, {...summary, applicationDate: undefined}]) {
    sourceResponse({sections: [{...section, oa_navigation: invalid}]});
    await expect(fetchInputInvoiceUsageOaDetail('oa-1')).rejects.toThrow('OA导航摘要格式无效');
  }
});

test.each([fetchInputInvoiceUsageInvoiceDetail, fetchOutputInvoiceCollectionInvoiceDetail])("invoice detail preserves every source line without substituting group totals or missing tax", async (loadDetail) => {
  sourceResponse({ id: "internal-id", invoiceNo: "SOURCE-INVOICE", invoiceStatus: "正常", isPositiveInvoice: false,
    sections: [
      {title: "发票信息", fields: [{label: "发票状态", value: "正常"}, {label: "是否正数发票", value: false}]},
      {title: "货物或应税劳务明细 1", fields: [{label: "货物或应税劳务名称", value: "第一条真实项目"}, {label: "金额", value: "100.00"}, {label: "税额", value: "0.00"}]},
      {title: "货物或应税劳务明细 2", fields: [{label: "货物或应税劳务名称", value: "第二条真实项目"}, {label: "金额", value: "50.00"}]},
    ],
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
    sections: [{title: "交易信息", fields: [{label: "交易日期", value: "2026-09-27"}, {label: "金额", value: "0.00"}, {label: "账号", value: "SOURCE-ACCOUNT"}]}],
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
  sourceResponse({ detailAvailable: true, applicantName: "真实申请人", workflowStatus: "completed", detailFields: {}, sections: [{title: "申请信息", fields: [{label: "申请人", value: "真实申请人"}]}] });
  const detail = await fetchInputInvoiceUsageOaDetail("oa-1");
  expect(detail.sections.flatMap(section => section.fields).some(field => field.label === "流程状态")).toBe(false);
});

test.each([fetchInputInvoiceUsageBankTransactionDetail, fetchOutputInvoiceCollectionBankTransactionDetail])("empty relation source sections never reconstruct facts from poisoned business summaries", async loadDetail => {
  sourceResponse({ kind: "bank", sections: [], summaries: [{ id: "private-bank", counterpartyName: "推断对方", amount: "999.00", status: "pending", workflowStatus: "completed" }] });
  const detail = await loadDetail("source-bank");
  expect(detail.sections).toEqual([]);
});

test.each([fetchInputInvoiceUsageBankTransactionDetail, fetchOutputInvoiceCollectionBankTransactionDetail])("relation source sections retain exact bank identity and original zero", async loadDetail => {
  sourceResponse({ kind: "bank", sections: [{ title: "银行流水 1", bank_transaction_id: "source-bank", fields: [
    { label: "备注", value: "原始备注" }, { label: "余额", value: 0 },
  ] }], summaries: [{ id: "wrong-bank", counterpartyName: "不可信摘要" }] });
  const detail = await loadDetail("source-bank");
  expect(detail.sections).toMatchObject([{ title: "银行流水 1", bank_transaction_id: "source-bank", fields: [
    { label: "备注", value: "原始备注" }, { label: "余额", value: 0 },
  ] }]);
});


test("a missing source projection fails visibly instead of reconstructing it from the list DTO", async () => {
  sourceResponse({invoiceNo: "list-only", amount: "999.00"});
  await expect(fetchInputInvoiceUsageInvoiceDetail("invoice")).rejects.toThrow("原始详情响应缺少字段表");
});

test.each([fetchInputInvoiceUsageBankTransactionDetail, fetchOutputInvoiceCollectionBankTransactionDetail])('bank metadata survives the API boundary and invalid labels fail visibly', async loadDetail => {
  const summary = {counterpartyName: '公司', amount: '35.00', direction: '收入', transactionDate: '2026-06-10', labels: ['退款']};
  const sections = [{title: '交易信息', document_id: 'bank', document_kind: 'bank', bank_navigation: summary, fields: [{label: '收入金额', value: '35.00'}]},
    {title: '业务分类', document_id: 'bank', document_kind: 'bank', bank_navigation: summary, fields: [], bank_labels: ['退款']}];
  sourceResponse({sections});
  expect((await loadDetail('bank')).sections).toMatchObject(sections);
  sourceResponse({sections: [{...sections[0], bank_navigation: {...summary, labels: '错误类型'}}]});
  await expect(loadDetail('bank')).rejects.toThrow('流水导航摘要格式无效');
  sourceResponse({sections: [{...sections[0], bank_navigation: undefined}]});
  await expect(loadDetail('bank')).rejects.toThrow('流水导航摘要格式无效');
});
