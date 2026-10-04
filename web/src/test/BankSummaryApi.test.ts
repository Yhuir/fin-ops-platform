import { afterEach, expect, test, vi } from "vitest";
import { fetchBankDetailTransactions } from "../features/bankDetails/api";
import { fetchTurnoverLedger, fetchTurnoverRelationDetail } from "../features/turnoverLedger/api";
import { fetchInputInvoiceUsageRows } from "../features/inputInvoiceUsage/api";
import { fetchOutputInvoiceCollectionRows } from "../features/outputInvoiceCollections/api";
import { OUTPUT_COLLECTION_STATUS_CODES } from "../features/outputInvoiceCollections/types";
import { fetchOaPendingPaymentRows } from "../features/oaPendingPayments/api";

const request = { page: 1, pageSize: 20, keyword: "", invoiceDateFrom: "", invoiceDateTo: "", month: "",
  filters: [{ field: "bank_name", operator: "in" as const, values: ["建设银行"] }],
  sortField: "", sortDirection: "" as const };

afterEach(() => vi.restoreAllMocks());

test.each(["camel", "snake"])("invoice bank APIs preserve %s source names, leading zero suffixes and explicit short names", async casing => {
  const bank = casing === "camel"
    ? { id: "bank-1", bankName: "建设银行", bankShortName: "建行", accountLast4: "0012", bankAccount: "建设银行 0012" }
    : { id: "bank-1", bank_name: "建设银行", bank_short_name: "建行", account_last4: "0012", bank_account: "建设银行 0012" };
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({
    rows: [{ id: "row-1", invoiceId: "invoice-1", bankTransactions: { ...bank, summaries: [bank] },
      collectionStatus: { code: "pending_collection", label: "待收款" } }],
    pagination: { page: 1, pageSize: 20, total: 1 },
    filterOptions: [{ field: "collection_status", options: OUTPUT_COLLECTION_STATUS_CODES.map(value => ({ value, label: value, count: 0 })) }],
  }), { headers: { "Content-Type": "application/json" } }));
  for (const load of [fetchInputInvoiceUsageRows, fetchOutputInvoiceCollectionRows]) {
    const result = await load(request);
    expect(result.rows[0].bank.primary).toMatchObject({ bankName: "建设银行", bankShortName: "建行", accountLast4: "0012" });
    expect(result.rows[0].bank.summaries[0]).toMatchObject({ bankName: "建设银行", bankShortName: "建行", accountLast4: "0012" });
  }
  expect(fetch).toHaveBeenCalledTimes(2);
  for (const [input] of fetch.mock.calls) {
    const url = new URL(String(input), "http://localhost");
    expect(JSON.parse(decodeURIComponent(url.searchParams.get("filters")!))).toEqual(request.filters);
    expect(url.pathname).not.toContain("settings");
  }
});

test("missing invoice short name does not manufacture a name or alter the source bank", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    rows: [{ bankTransactions: { id: "bank-1", bankName: "完整银行名称", accountLast4: "0000" } }],
  }), { headers: { "Content-Type": "application/json" } }));
  const result = await fetchInputInvoiceUsageRows(request);
  expect(result.rows[0].bank.primary).toMatchObject({ bankName: "完整银行名称", bankShortName: "", accountLast4: "0000" });
});

test("OA bank display receives snapshot short names in its existing rows response", async () => {
  const bank = { bankName: "建设银行", bankShortName: "建行", accountLast4: "0012" };
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    rows: [{ bankTransaction: { ...bank, summaries: [bank] } }], pagination: { total: 1 },
    summary: { rowCount: 1, oaCount: 1, statusCounts: { paid: 1, unpaid: 0 }, viewCounts: { completed: 1, in_progress: 0 } },
  }), { headers: { "Content-Type": "application/json" } }));
  const result = await fetchOaPendingPaymentRows({ ...request, sortDirection: "desc", tradeDateFrom: "", tradeDateTo: "", viewMode: "completed" });
  expect(result.rows[0].bankTransaction).toMatchObject({ ...bank, summaries: [bank] });
  expect(fetch).toHaveBeenCalledTimes(1);
});


test("bank detail API carries an explicit short name with original bank and zero-prefixed account", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({rows: [{
    id: "bank-1", same_time_order_status: "time", bank_name: "中国建设银行", bank_short_name: "建行", account_last4: "0012",
  }]}));
  const result = await fetchBankDetailTransactions({accountKey: "original-account"});
  expect(result.rows[0]).toMatchObject({bankName: "中国建设银行", bankShortName: "建行", accountLast4: "0012"});
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0][0])).toContain("account_key=original-account");
});

test("turnover API keeps original account labels alongside configured display labels", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({rows: [{
    bank_account_labels: ["中国建设银行 0012", "完整银行名称 0001"],
    bank_account_display_labels: ["建行 0012", "完整银行名称 0001"],
  }]}));
  const result = await fetchTurnoverLedger({family: "personal", page: 1, pageSize: 20});
  expect(result.rows[0]).toMatchObject({
    bankAccountLabels: ["中国建设银行 0012", "完整银行名称 0001"],
    bankAccountDisplayLabels: ["建行 0012", "完整银行名称 0001"],
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0][0])).toContain("family=personal");
});


test("turnover detail rejects a missing relation instead of manufacturing display data", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({}));
  await expect(fetchTurnoverRelationDetail("relation-1")).rejects.toThrow("往来关系详情缺少关系数据");
});
