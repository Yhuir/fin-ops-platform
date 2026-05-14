import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchBankDetailTransactions, saveBankTransactionCategories } from "../features/bankDetails/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("bank details API", () => {
  test("maps manual, auto, and effective category fields from transaction rows", async () => {
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
    });
    expect(payload.categoryCounts.fee).toBe(1);
  });

  test("reports HTML API responses as a routing problem instead of a JSON parse error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!DOCTYPE HTML><html><body>Unsupported method</body></html>", {
        status: 501,
        headers: { "Content-Type": "text/html;charset=utf-8" },
      })),
    );

    await expect(
      saveBankTransactionCategories({
        updates: [
          {
            transactionId: "bank-detail-001",
            categoryCode: "borrow_in_company_pending_repayment",
            expectedVersion: 1,
          },
        ],
      }),
    ).rejects.toThrow("接口返回了 HTML 页面");
  });
});
