import { afterEach, describe, expect, test, vi } from "vitest";
import { downloadInputInvoiceUsageExport, fetchInputInvoiceUsageExportSummary } from "../features/inputInvoiceUsage/api";
import { downloadOaPendingPaymentExport, fetchOaPendingPaymentExportSummary } from "../features/oaPendingPayments/api";
import { downloadOutputInvoiceCollectionExport, fetchOutputInvoiceCollectionExportSummary } from "../features/outputInvoiceCollections/api";
import { downloadPendingInvoiceExport, fetchPendingInvoiceExportSummary } from "../features/pendingInvoices/api";
import { downloadTurnoverLedgerExport, fetchTurnoverLedgerExportSummary } from "../features/turnoverLedger/api";

const base = { page: 3, pageSize: 20, keyword: "客户", month: "2026-05", filters: [], sortField: "", sortDirection: "" as const };
const invoice = { ...base, invoiceDateFrom: "", invoiceDateTo: "" };
const oa = { ...base, viewMode: "in_progress" as const, tradeDateFrom: "2026-05-01", tradeDateTo: "2026-05-31",
  filters: [{ field: "payment_status", operator: "in" as const, values: ["paid"] }], sortField: "amount", sortDirection: "asc" as const };
const pending = { direction: "expense" as const, filter: "all" as const };
const turnover = { family: "company" as const, query: "客户", settlementStatus: "unsettled" as const };
const adapters = [
  { name: "OA", summary: () => fetchOaPendingPaymentExportSummary(oa, new AbortController().signal), download: () => downloadOaPendingPaymentExport(oa) },
  { name: "进项", summary: () => fetchInputInvoiceUsageExportSummary(invoice, new AbortController().signal), download: () => downloadInputInvoiceUsageExport(invoice) },
  { name: "销项", summary: () => fetchOutputInvoiceCollectionExportSummary(invoice, new AbortController().signal), download: () => downloadOutputInvoiceCollectionExport(invoice) },
  { name: "流水", summary: () => fetchPendingInvoiceExportSummary(pending, new AbortController().signal), download: () => downloadPendingInvoiceExport(pending) },
  { name: "往来", summary: () => fetchTurnoverLedgerExportSummary(turnover), download: () => downloadTurnoverLedgerExport(turnover) },
];
afterEach(() => vi.unstubAllGlobals());

for (const adapter of adapters) describe(`${adapter.name}导出数量合同`, () => {
  test.each([undefined, null, -1, 0.5, "2"])("数量 %s 失败，不制造零", async rowCount => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ row_count: rowCount })));
    await expect(adapter.summary()).rejects.toThrow("导出数量不完整或无效");
  });
  test.each([null, "", "-1", "1.5", "9007199254740992"])("下载数量 %s 失败，不开始不完整下载", async count => {
    const headers = new Headers({ "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    if (count !== null) headers.set("X-Export-Count", count);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("xlsx", { headers })));
    await expect(adapter.download()).rejects.toThrow(/导出数量/);
  });
  test("保留真实零统计与下载的实际数量", async () => {
    vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("export-summary")
      ? Response.json({ row_count: 0 })
      : new Response("xlsx", { headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "X-Export-Count": "4" } })));
    expect(await adapter.summary()).toEqual({ rowCount: 0 });
    expect((await adapter.download()).count).toBe(4);
  });
});

test("OA 统计和下载完整继承已生效条件，排除来源选择及分页", async () => {
  const calls: URL[] = [];
  vi.stubGlobal("fetch", vi.fn(async input => {
    const url = new URL(String(input), "http://localhost"); calls.push(url);
    return url.pathname.endsWith("export-summary") ? Response.json({ row_count: 17 })
      : new Response("xlsx", { headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "X-Export-Count": "17" } });
  }));
  await fetchOaPendingPaymentExportSummary(oa, new AbortController().signal);
  await downloadOaPendingPaymentExport(oa);
  expect(calls[0].search).toBe(calls[1].search);
  const params = calls[0].searchParams;
  expect(params.get("view_mode")).toBe("in_progress"); expect(params.get("keyword")).toBe("客户");
  expect(params.get("month")).toBe("2026-05"); expect(params.get("trade_date_from")).toBe("2026-05-01");
  expect(params.get("trade_date_to")).toBe("2026-05-31");
  expect(JSON.parse(decodeURIComponent(params.get("filters")!))).toEqual(oa.filters);
  expect(params.get("sort_field")).toBe("amount"); expect(params.get("sort_direction")).toBe("asc");
  for (const field of ["sources", "page", "page_size"]) expect(params.has(field)).toBe(false);
});
