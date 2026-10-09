import { afterEach, expect, test, vi } from "vitest";
import { fetchOutputInvoiceCollectionRows, fetchOutputInvoiceCollectionExportSummary, downloadOutputInvoiceCollectionExport } from "../features/outputInvoiceCollections/api";
import { normalizeOutputTaxRate } from "../features/outputInvoiceCollections/taxRate";
import { OUTPUT_COLLECTION_STATUS_CODES } from "../features/outputInvoiceCollections/types";

const request = { page: 1, pageSize: 20, keyword: "", invoiceDateFrom: "", invoiceDateTo: "", month: "", filters: [], sortField: "", sortDirection: "" as const };
const options = () => OUTPUT_COLLECTION_STATUS_CODES.map((value, index) => ({ value, label: `状态 ${index}`, count: index === 0 ? 3 : 0 }));
const payload = () => ({ rows: [{ invoiceId: "invoice-1", collectionStatus: { code: "pending_collection", label: "待收款" } }],
  filterOptions: [{ field: "collection_status", options: options() }], pagination: { page: 1, pageSize: 20, total: 3 } });
function mockResponse(value: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } }));
}
afterEach(() => vi.restoreAllMocks());

test.each([["0.13", "13%"], ["13.00%", "13%"], ["0", "0%"], ["", "—"], ["免税", "免税"], ["不征税", "不征税"], ["mixed", "多税率"]])("restores tax rate %s as %s", (raw, expected) => {
  expect(normalizeOutputTaxRate(raw)).toBe(expected);
});

test("maps full-scope signed totals and carries tax/search/status into preview and download", async () => {
  const totals = { invoiceCount: 3, totalWithTax: "-100.00", amountWithoutTax: "-88.50", collectedAmount: "70.00", pendingAmount: "0.00", pendingCollectionCount: 0, partialCollectionCount: 0 };
  const calls: URL[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async input => {
    const url = new URL(String(input), "http://localhost"); calls.push(url);
    if (url.pathname.endsWith('/export')) return new Response('xlsx', {headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','X-Export-Count':'3'}});
    const result = url.pathname.endsWith('/export-summary') ? {row_count:3,filter_options:[{field:'collection_status',options:options()}]} : {...payload(),summary:totals};
    return new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}});
  });
  expect((await fetchOutputInvoiceCollectionRows(request)).summary).toEqual(totals);
  const query = {...request,keyword:'客户',invoiceDateFrom:'2026-01-01',invoiceDateTo:'2026-12-31',filters:[{field:'tax_rate',operator:'in' as const,values:['13%','—']},{field:'collection_status',operator:'in' as const,values:['collected']}],sortField:'total_with_tax',sortDirection:'asc' as const};
  expect((await fetchOutputInvoiceCollectionExportSummary(query,new AbortController().signal)).rowCount).toBe(3);
  await downloadOutputInvoiceCollectionExport(query);
  for (const url of calls.slice(1)) {
    expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual(query.filters);
    expect(url.searchParams.get('keyword')).toBe('客户');
    expect(url.searchParams.get('invoice_date_from')).toBe('2026-01-01');
    expect(url.searchParams.get('sort_field')).toBe('total_with_tax');
  }
});

test("uses full-scope counts instead of current page length and retains real zeros", async () => {
  mockResponse(payload());
  const result = await fetchOutputInvoiceCollectionRows(request);
  expect(result.rows).toHaveLength(1);
  expect(result.filterOptions[0].options.map(option => option.count)).toEqual([3, 0, 0, 0, 0, 0]);
});

test.each([undefined, null, -1, 0.5, "3", Number.MAX_SAFE_INTEGER + 1])("rejects invalid status count %s instead of manufacturing zero", async count => {
  const value = payload();
  (value.filterOptions[0].options[0] as Record<string, unknown>).count = count;
  mockResponse(value);
  await expect(fetchOutputInvoiceCollectionRows(request)).rejects.toThrow("分类统计不完整或无效");
});

test.each(["missing", "duplicate", "unknown"])("rejects %s status category", async kind => {
  const value = payload();
  if (kind === "missing") value.filterOptions[0].options.pop();
  else value.filterOptions[0].options[0] = { ...value.filterOptions[0].options[1], value: (kind === "duplicate" ? "partial_collected" : "invented") as typeof OUTPUT_COLLECTION_STATUS_CODES[number] };
  mockResponse(value);
  await expect(fetchOutputInvoiceCollectionRows(request)).rejects.toThrow("分类统计不完整或无效");
});

test.each(["", "unknown"])("rejects invalid row state %s without a pending fallback", async state => {
  const value = payload();
  if (state) value.rows[0].collectionStatus.code = state;
  else value.rows[0].collectionStatus.label = "";
  mockResponse(value);
  await expect(fetchOutputInvoiceCollectionRows(request)).rejects.toThrow("状态数据无效");
});


test.each([
  {totalWithTax: null, amountWithoutTax: '100.00', taxAmount: '13.00', taxRate: null, taxAmountText: null},
  {totalWithTax: '0.00', amountWithoutTax: '0.00', taxAmount: null, taxRate: '免税', taxAmountText: '*'},
])('preserves source financial fields without filling missing values: %j', async invoice => {
  mockResponse({...payload(), rows: [{...payload().rows[0], invoice}]});
  const response = await fetchOutputInvoiceCollectionRows(request);
  expect(response.rows[0].invoice).toMatchObject({
    totalWithTax: invoice.totalWithTax ?? '', amountWithoutTax: invoice.amountWithoutTax,
    taxAmount: invoice.taxAmount ?? '', taxRate: invoice.taxRate ?? '—', taxAmountText: invoice.taxAmountText ?? '',
  });
});
