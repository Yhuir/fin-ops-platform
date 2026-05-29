import { afterEach, describe, expect, test, vi } from "vitest";

import {
  confirmBankDetailCategory,
  downloadBankDetailTransactionsExport,
  fetchBankDetailTransactions,
  reapplyBankAutoTagRules,
  revokeBankDetailCategoryConfirmation,
  saveBankAutoTagRules,
} from "../features/bankDetails/api";

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
            category_primary_label: null,
            category_sub_label: null,
            category_label_path: [],
            category_source: "",
            category_version: null,
            auto_category_code: "fee",
            auto_category_label: "手续费",
            auto_category_path: ["自动识别", "手续费"],
            auto_category_primary_label: "费用",
            auto_category_sub_label: "手续费",
            auto_category_label_path: ["费用", "手续费"],
            auto_category_source: "bank_transaction_auto_category_service",
            auto_category_reason: "摘要包含手续费",
            auto_category_confidence: "high",
            effective_category_code: "fee",
            effective_category_label: "手续费",
            effective_category_path: ["自动识别", "手续费"],
            effective_category_primary_label: "费用",
            effective_category_sub_label: "手续费",
            effective_category_label_path: ["费用", "手续费"],
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
      categoryPrimaryLabel: null,
      categorySubLabel: null,
      categoryLabelPath: [],
      categorySource: "",
      categoryVersion: null,
      autoCategoryCode: "fee",
      autoCategoryLabel: "手续费",
      autoCategoryPath: ["自动识别", "手续费"],
      autoCategoryPrimaryLabel: "费用",
      autoCategorySubLabel: "手续费",
      autoCategoryLabelPath: ["费用", "手续费"],
      autoCategorySource: "bank_transaction_auto_category_service",
      autoCategoryReason: "摘要包含手续费",
      autoCategoryConfidence: "high",
      effectiveCategoryCode: "fee",
      effectiveCategoryLabel: "手续费",
      effectiveCategoryPath: ["自动识别", "手续费"],
      effectiveCategoryPrimaryLabel: "费用",
      effectiveCategorySubLabel: "手续费",
      effectiveCategoryLabelPath: ["费用", "手续费"],
      effectiveCategorySource: "auto",
      purposeText: "工行用途",
      summaryText: "工行摘要",
      noteText: "工行附言",
    });
    expect(payload.categoryCounts.fee).toBe(1);
  });

  test("maps ambiguous automatic category candidates without widening the choice list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        rows: [
          {
            id: "bank-detail-needs-confirmation",
            trade_time: "2026-05-01 10:30:00+08:00",
            counterparty_name: "候选供应商",
            direction: "expense",
            direction_label: "支",
            amount: "88.00",
            balance: "130412.50",
            summary: "网银手续费工资",
            purpose: "手续费工资",
            purpose_text: "手续费工资",
            summary_text: "网银手续费工资",
            note_text: "",
            bank_name: "工商银行",
            account_last4: "6386",
            category_code: null,
            category_label: null,
            category_path: [],
            category_source: "",
            category_version: 1,
            category_resolution_status: "needs_confirmation",
            category_rule_version: "bank-auto-tag-rules:2",
            manual_confirmed_category_code: null,
            auto_category_code: null,
            auto_category_label: null,
            auto_category_path: [],
            auto_candidate_category_codes: ["fee", "salary"],
            auto_candidate_categories: [
              {
                category_code: "fee",
                category_label: "手续费",
                category_primary_label: "费用",
                category_sub_label: "手续费",
                category_label_path: ["费用", "手续费"],
                category_path: ["自动识别", "手续费"],
                rule_code: "fee",
                reason: "摘要命中手续费",
              },
              {
                category_code: "salary",
                category_label: "工资",
                category_primary_label: "费用",
                category_sub_label: "工资",
                category_label_path: ["费用", "工资"],
                category_path: ["自动识别", "工资"],
                rule_code: "salary",
                reason: "摘要命中工资",
              },
            ],
            effective_category_code: null,
            effective_category_label: null,
            effective_category_path: [],
            effective_category_source: "",
          },
        ],
        category_counts: { uncategorized: 1 },
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankDetailTransactions({
      dateFrom: "2026-05-01",
      dateTo: "2026-05-31",
    });

    expect(payload.rows[0]).toMatchObject({
      categoryResolutionStatus: "needs_confirmation",
      categoryRuleVersion: "bank-auto-tag-rules:2",
      autoCategoryCode: null,
      autoCandidateCategoryCodes: ["fee", "salary"],
      autoCandidateCategories: [
        expect.objectContaining({ categoryCode: "fee", categoryLabelPath: ["费用", "手续费"], ruleCode: "fee" }),
        expect.objectContaining({ categoryCode: "salary", categoryLabelPath: ["费用", "工资"], ruleCode: "salary" }),
      ],
      effectiveCategoryCode: null,
    });
  });

  test("confirms and revokes a bank detail category candidate through scoped endpoints", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await confirmBankDetailCategory("bank-detail-001", "fee");
    await revokeBankDetailCategoryConfirmation("bank-detail-001");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/bank-details/transactions/bank-detail-001/category-confirmation", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ category_code: "fee" }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/bank-details/transactions/bank-detail-001/category-confirmation", expect.objectContaining({
      method: "DELETE",
    }));
  });

  test("reapplies saved auto tag rules through a dedicated endpoint", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      version: 3,
      system_rule: { code: "internal_transfer", label: "内部往来款", priority_label: "优先级 1" },
      active_rules: [],
      archived_rules: [],
      field_options: [],
      permissions: { can_save: true },
      read_model_status: "refreshing",
      read_model_scope_keys: ["2026-05"],
      enqueued_jobs: ["bank_detail.read_model.refresh"],
    }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const payload = await reapplyBankAutoTagRules();

    expect(fetchMock).toHaveBeenCalledWith("/api/bank-details/auto-tag-rules/reapply", expect.objectContaining({
      method: "POST",
    }));
    expect(payload.version).toBe(3);
    expect(payload.readModelStatus).toBe("refreshing");
  });

  test("does not copy legacy purpose or summary into split bank text columns", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        rows: [
          {
            id: "bank-detail-legacy",
            trade_time: "2026-04-16 11:09:14",
            counterparty_name: "未知对手方",
            direction: "expense",
            direction_label: "支",
            amount: "4.00",
            balance: "276.63",
            summary: "客户附言内容",
            purpose: "客户附言内容",
            bank_name: "民生银行",
            account_last4: "9486",
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankDetailTransactions({});

    expect(payload.rows[0]).toMatchObject({
      purposeText: "",
      summaryText: "",
      noteText: "",
    });
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
      categoryCode: "fee",
      categoryPrimaryLabel: "费用",
      categorySubLabel: "手续费",
      page: 1,
      pageSize: 100,
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/bank-details/transactions");
    expect(url.searchParams.get("account_key")).toBe("icbc:6386");
    expect(url.searchParams.get("date_from")).toBe("2026-04-01");
    expect(url.searchParams.get("date_to")).toBe("2026-04-30");
    expect(url.searchParams.get("keyword")).toBe("跨页目标");
    expect(url.searchParams.get("category_code")).toBe("fee");
    expect(url.searchParams.get("category_primary_label")).toBe("费用");
    expect(url.searchParams.get("category_sub_label")).toBe("手续费");
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
      categoryCode: "fee",
      categoryPrimaryLabel: "费用",
      categorySubLabel: "手续费",
    });

    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/bank-details/transactions/export");
    expect(url.searchParams.get("mode")).toBe("account");
    expect(url.searchParams.get("account_key")).toBe("工商银行:6386");
    expect(url.searchParams.get("date_from")).toBe("2026-04-01");
    expect(url.searchParams.get("date_to")).toBe("2026-05-18");
    expect(url.searchParams.get("keyword")).toBe("手续费");
    expect(url.searchParams.get("category_code")).toBe("fee");
    expect(url.searchParams.get("category_primary_label")).toBe("费用");
    expect(url.searchParams.get("category_sub_label")).toBe("手续费");
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

  test("includes automatic tag rule field errors in save failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        error: "invalid_auto_tag_rule",
        field_errors: [
          { path: "archived_rules[0].code", message: "停用规则必须包含已有标签 code。" },
        ],
      }), { status: 400, headers: { "Content-Type": "application/json" } })),
    );

    await expect(saveBankAutoTagRules({
      expectedVersion: 1,
      activeRules: [],
      archivedRules: [],
    })).rejects.toThrow("自动标签规则校验失败，请检查规则内容：停用规则必须包含已有标签 code。");
  });

  test("serializes automatic tag rule output primary and sub labels", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      version: 2,
      active_rules: [],
      archived_rules: [],
      permissions: { can_save: true },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await saveBankAutoTagRules({
      expectedVersion: 1,
      activeRules: [
        {
          label: "手续费",
          outputPrimaryLabel: "费用",
          outputSubLabel: "手续费",
          direction: "expense",
          accountScope: { type: "any", values: [] },
          rules: {
            matchFields: ["summary_text"],
            exactAny: [],
            containsAny: ["手续费"],
            containsAll: [],
            noneOf: [],
            regexAny: [],
          },
        },
      ],
      archivedRules: [],
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.active_rules[0].output_primary_label).toBe("费用");
    expect(body.active_rules[0].output_sub_label).toBe("手续费");
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
