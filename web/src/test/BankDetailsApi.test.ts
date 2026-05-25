import { afterEach, describe, expect, test, vi } from "vitest";

import { downloadBankDetailTransactionsExport, fetchBankDetailTransactions } from "../features/bankDetails/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("bank details API", () => {
  test("maps relation tags from transaction rows and defaults missing tags to unlinked labels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        rows: [
          {
            id: "bank-detail-linked",
            trade_time: "2026-05-01 10:30:00+08:00",
            counterparty_name: "云南溯源科技有限公司",
            direction: "income",
            direction_label: "收",
            amount: "20000.00",
            balance: "130500.50",
            summary: "项目回款",
            purpose: "货款",
            purpose_text: "交易用途",
            summary_text: "项目回款摘要",
            note_text: "客户附言",
            bank_name: "工商银行",
            account_last4: "6386",
            oa_relation_tag: "有oa",
            invoice_relation_tag: "有发票",
            relation_tags: ["有oa", "有发票"],
            relation_case_id: "CASE-202605-001",
          },
          {
            id: "bank-detail-unlinked",
            trade_time: "2026-05-02 10:30:00",
            counterparty_name: "杭州张三广告有限公司",
            direction: "expense",
            direction_label: "支",
            amount: "100.00",
            balance: "130400.50",
            summary: "广告费",
            purpose: "",
            bank_name: "工商银行",
            account_last4: "6386",
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankDetailTransactions({});

    expect(payload.rows[0]).toMatchObject({
      oaRelationTag: "有oa",
      invoiceRelationTag: "有发票",
      relationTags: ["有oa", "有发票"],
      relationCaseId: "CASE-202605-001",
      tradeTime: "2026-05-01 10:30:00",
      purposeText: "交易用途",
      summaryText: "项目回款摘要",
      noteText: "客户附言",
    });
    expect(payload.rows[1]).toMatchObject({
      oaRelationTag: "无oa",
      invoiceRelationTag: "无发票",
      relationTags: ["无oa", "无发票"],
      relationCaseId: null,
    });
  });

  test("maps auto category and bank text display fields from transaction rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        account_key: "icbc:6386",
        date_from: "2026-05-01",
        date_to: "2026-05-31",
        rows: [
          {
            id: "bank-detail-001",
            trade_time: "2026-05-01 10:30:00",
            counterparty_name: "云南溯源科技有限公司",
            direction: "expense",
            direction_label: "支",
            amount: "88.00",
            balance: "130412.50",
            summary: "网银手续费",
            purpose: "结算服务",
            purpose_text: "工行用途",
            summary_text: "工行摘要",
            note_text: "工行附言",
            bank_name: "工商银行",
            account_last4: "6386",
            category_code: null,
            category_label: null,
            category_path: [],
            category_source: "",
            category_version: null,
            auto_category_code: "fee",
            auto_category_label: "手续费",
            auto_category_path: ["自动识别", "手续费"],
            auto_category_source: "bank_transaction_auto_category_service",
            auto_category_reason: "摘要包含手续费",
            auto_category_confidence: "high",
            effective_category_code: "fee",
            effective_category_label: "手续费",
            effective_category_path: ["自动识别", "手续费"],
            effective_category_source: "auto",
          },
        ],
        category_counts: {
          fee: 1,
          uncategorized: 0,
        },
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankDetailTransactions({
      accountKey: "icbc:6386",
      dateFrom: "2026-05-01",
      dateTo: "2026-05-31",
    });

    expect(payload.rows[0]).toMatchObject({
      categoryCode: null,
      categoryLabel: null,
      categoryPath: [],
      categorySource: "",
      categoryVersion: null,
      autoCategoryCode: "fee",
      autoCategoryLabel: "手续费",
      autoCategoryPath: ["自动识别", "手续费"],
      autoCategorySource: "bank_transaction_auto_category_service",
      autoCategoryReason: "摘要包含手续费",
      autoCategoryConfidence: "high",
      effectiveCategoryCode: "fee",
      effectiveCategoryLabel: "手续费",
      effectiveCategoryPath: ["自动识别", "手续费"],
      effectiveCategorySource: "auto",
      purposeText: "工行用途",
      summaryText: "工行摘要",
      noteText: "工行附言",
    });
    expect(payload.categoryCounts.fee).toBe(1);
  });

  test("sends keyword when fetching bank detail transactions", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      rows: [],
      pagination: {
        page: 1,
        page_size: 100,
        total: 0,
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchBankDetailTransactions({
      accountKey: "icbc:6386",
      dateFrom: "2026-04-01",
      dateTo: "2026-04-30",
      keyword: "跨页目标",
      page: 1,
      pageSize: 100,
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/bank-details/transactions");
    expect(url.searchParams.get("account_key")).toBe("icbc:6386");
    expect(url.searchParams.get("date_from")).toBe("2026-04-01");
    expect(url.searchParams.get("date_to")).toBe("2026-04-30");
    expect(url.searchParams.get("keyword")).toBe("跨页目标");
    expect(url.searchParams.get("page")).toBe("1");
    expect(url.searchParams.get("page_size")).toBe("100");
  });

  test("maps refreshing read model responses without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        rows: [],
        pagination: {
          page: 1,
          page_size: 100,
          total: 0,
        },
        category_counts: {
          uncategorized: 0,
        },
        read_model_status: "refreshing",
        cache_status: "bypass",
      }), { status: 202, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankDetailTransactions({ page: 1, pageSize: 100 });

    expect(payload.rows).toEqual([]);
    expect(payload.readModelStatus).toBe("refreshing");
    expect(payload.cacheStatus).toBe("bypass");
  });

  test("downloads bank detail export with current filters and encoded filename", async () => {
    const fetchMock = vi.fn(async () => new Response("xlsx", {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": "attachment; filename=\"__.xlsx\"; filename*=UTF-8''%E9%93%B6%E8%A1%8C%E6%98%8E%E7%BB%86.xlsx",
      },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await downloadBankDetailTransactionsExport({
      mode: "account",
      accountKey: "工商银行:6386",
      dateFrom: "2026-04-01",
      dateTo: "2026-05-18",
      keyword: "手续费",
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/bank-details/transactions/export");
    expect(url.searchParams.get("mode")).toBe("account");
    expect(url.searchParams.get("account_key")).toBe("工商银行:6386");
    expect(url.searchParams.get("date_from")).toBe("2026-04-01");
    expect(url.searchParams.get("date_to")).toBe("2026-05-18");
    expect(url.searchParams.get("keyword")).toBe("手续费");
    expect(result.fileName).toBe("银行明细.xlsx");
    expect(result.blob).toBeInstanceOf(Blob);
  });

  test("maps bank detail export API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        error: "bank_detail_export_account_required",
      }), { status: 400, headers: { "Content-Type": "application/json" } })),
    );

    await expect(downloadBankDetailTransactionsExport({ mode: "account" })).rejects.toThrow("请选择具体银行账户后再导出当前账户。");
  });

  test("rejects successful HTML responses from bank detail export", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!doctype html><html></html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      })),
    );

    await expect(downloadBankDetailTransactionsExport({ mode: "all" })).rejects.toThrow("接口返回了 HTML 页面");
  });

});
