import { afterEach, expect, test, vi } from "vitest";
import { fetchOutputInvoiceCollectionRows } from "../features/outputInvoiceCollections/api";
import { OUTPUT_COLLECTION_STATUS_CODES } from "../features/outputInvoiceCollections/types";

const request = { page: 1, pageSize: 20, keyword: "", invoiceDateFrom: "", invoiceDateTo: "", month: "", filters: [], sortField: "", sortDirection: "" as const };
const options = () => OUTPUT_COLLECTION_STATUS_CODES.map((value, index) => ({ value, label: `状态 ${index}`, count: index === 0 ? 3 : 0 }));
const payload = () => ({ rows: [{ invoiceId: "invoice-1", collectionStatus: { code: "pending_collection", label: "收款待核对" } }],
  filterOptions: [{ field: "collection_status", options: options() }], pagination: { page: 1, pageSize: 20, total: 3 } });
function mockResponse(value: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } }));
}
afterEach(() => vi.restoreAllMocks());

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
