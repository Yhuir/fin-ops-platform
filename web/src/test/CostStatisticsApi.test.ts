import { afterEach, describe, expect, test, vi } from "vitest";

import {
  exportCostStatisticsView,
  fetchCostStatisticsManualAllocations,
  fetchCostStatisticsExplorerPage,
  fetchCostStatisticsExportPreview,
  fetchCostStatisticsNoOaRules,
  saveCostStatisticsNoOaRules,
  saveCostStatisticsManualAllocation,
} from "../features/cost-statistics/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("Cost statistics export API", () => {
  test("maps the unit-allocation and bank-event contract without source-matrix fields", async () => {
    const task = {
      relation_case_id: "relation-1",
      relation_version: 3,
      source_fingerprint: "b".repeat(64),
      status: "pending",
      oa_total: "120.00",
      gross_outflow_total: "125.00",
      wrong_payment_refund_total: "5.00",
      net_outflow_total: "120.00",
      units: [{
        unit_id: "oa-1:parent",
        oa_id: "oa-1",
        oa_apply_type: "支付申请",
        expense_item_id: "",
        project_id: "project-1",
        project_name: "云南溯源科技",
        expense_type: "材料费",
        expense_content: "采购款",
        oa_applicant: "申请人",
        oa_original_amount: "120.00",
      }],
      bank_events: [{
        transaction_id: "bank-1",
        event_kind: "wrong_payment_refund",
        amount: "5.00",
        counterparty_name: "供应商",
        trade_time: "2026-08-27T10:00:00+08:00",
        tags: ["退款"],
      }],
      allocations: [],
      non_cost_amount: "0.00",
      non_cost_reason: "",
      version: 0,
      updated_by: "",
      updated_at: "",
      can_save: true,
    };
    global.fetch = vi.fn(async (_input, init) => new Response(JSON.stringify({
      ...(init?.method === "PUT" ? {
        ...task,
        status: "allocated",
        allocations: [{ unit_id: "oa-1:parent", amount: "120.00" }],
        version: 1,
      } : {
        items: [task],
        row_count: 1,
        counts: { pending: 1, allocated: 0 },
        next_cursor: null,
      }),
    }), { status: 200 })) as typeof fetch;

    const page = await fetchCostStatisticsManualAllocations({ status: "pending", pageSize: 50 });
    expect(page.items[0]).toMatchObject({
      oaTotal: "120.00",
      grossOutflowTotal: "125.00",
      wrongPaymentRefundTotal: "5.00",
      netOutflowTotal: "120.00",
      units: [{ oaApplyType: "支付申请" }],
      bankEvents: [{
        transactionId: "bank-1",
        eventKind: "wrong_payment_refund",
        tags: ["退款"],
      }],
    });
    expect(page.items[0].bankEvents[0]).not.toHaveProperty("summary");

    await saveCostStatisticsManualAllocation({
      relationCaseId: "relation-1",
      expectedVersion: 0,
      sourceFingerprint: "b".repeat(64),
      allocations: [{ unitId: "oa-1:parent", amount: "120.00" }],
      nonCostAmount: "0.00",
      nonCostReason: "",
    });
    const putCall = vi.mocked(global.fetch).mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(putCall?.[1]?.body))).toEqual({
      relation_case_id: "relation-1",
      expected_version: 0,
      source_fingerprint: "b".repeat(64),
      allocations: [{ unit_id: "oa-1:parent", amount: "120.00" }],
      non_cost_amount: "0.00",
      non_cost_reason: "",
    });
  });

  test("prefers RFC 5987 filename* from content disposition for exports", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(new Blob(["xlsx"]), {
        status: 200,
        headers: {
          "Content-Disposition":
            "attachment; filename=\"cost_statistics_export.xlsx\"; filename*=UTF-8''%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%8C%89%E9%93%B6%E8%A1%8C%E8%B4%A6%E6%88%B7.xlsx",
        },
      }),
    ) as typeof fetch;

    const result = await exportCostStatisticsView({
      month: "2026-03",
      view: "bank_account",
      bankAccountLabels: ["建设银行 8106"],
    });

    expect(result.fileName).toBe("成本统计_2026-03_按银行账户.xlsx");
  });

  test("surfaces backend row-limit messages from failed export downloads", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        error: "cost_statistics_export_row_limit_exceeded",
        message: "导出结果超过 20000 行，请缩小筛选范围后重试。",
        details: { total: 20001, limit: 20000 },
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    ) as typeof fetch;

    await expect(exportCostStatisticsView({
      month: "all",
      view: "bank_account",
      bankAccountLabels: ["建设银行 8106"],
    })).rejects.toThrow("导出结果超过 20000 行，请缩小筛选范围后重试。");
  });

  test("passes the isolated cursor-page contract without the removed project scope", async () => {
    global.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/cost-statistics/explorer")) {
        return new Response(JSON.stringify({
          scope: "all",
          view: "project",
          summary: {
            row_count: 0,
            transaction_count: 0,
            total_amount: "0.00",
          },
          available_years: ["2026", "2025"],
          facets: {
            projects: [{
              project_name: "云南溯源科技",
              total_amount: "100.00",
              expense_type_count: 1,
            }],
          },
          rows: [],
          row_count: 0,
          next_cursor: "cursor-2",
        }), { status: 200 });
      }
      if (url.startsWith("/api/cost-statistics/export-preview")) {
        return new Response(JSON.stringify({
          view: "project",
          file_name: "preview.xlsx",
          scope_label: "全部期间",
          summary: {
            row_count: 0,
            transaction_count: 0,
            total_amount: "0.00",
            sheet_count: 1,
          },
          sheet_names: [],
          columns: [],
          rows: [],
        }), { status: 200 });
      }
      return new Response(new Blob(["xlsx"]), {
        status: 200,
        headers: {
          "Content-Disposition": "attachment; filename=\"export.xlsx\"",
        },
      });
    }) as typeof fetch;

    const page = await fetchCostStatisticsExplorerPage({
      scope: "all",
      view: "project",
      projectName: "云南溯源科技",
      query: "PLC",
      pageSize: 50,
      includeStatistics: false,
    });
    await fetchCostStatisticsExportPreview({
      month: "all",
      view: "project",
      projectNames: ["云南溯源科技"],
      aggregateBy: "month",
    });
    await exportCostStatisticsView({
      month: "all",
      view: "project",
      projectNames: ["云南溯源科技"],
      aggregateBy: "month",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/cost-statistics/explorer?scope=all&view=project&project_name=${encodeURIComponent("云南溯源科技")}&query=PLC&page_size=50&include_statistics=false`,
      expect.any(Object),
    );
    expect(global.fetch).toHaveBeenCalledWith(
      `/api/cost-statistics/export-preview?month=all&view=project&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month`,
      expect.any(Object),
    );
    expect(global.fetch).toHaveBeenCalledWith(
      `/api/cost-statistics/export?month=all&view=project&project_name=${encodeURIComponent("云南溯源科技")}&aggregate_by=month&include_oa_details=true&include_invoice_details=true&include_exception_rows=true&include_ignored_rows=true&include_expense_content_summary=true&sort_by=time`,
      expect.any(Object),
    );
    expect(page.availableYears).toEqual(["2026", "2025"]);
    expect(page.facets.projects[0]).toMatchObject({
      projectName: "云南溯源科技",
      totalAmount: "100.00",
    });
    expect(page.nextCursor).toBe("cursor-2");
  });

  test("maps canonical cost statistics and attributed bank account from page rows", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        scope: "2026-03",
        view: "project",
        summary: {
          row_count: 1,
          transaction_count: 1,
          total_amount: "145.00",
        },
        statistics: {
          transaction_count: 12500,
          expense_transaction_count: 11000,
          income_transaction_count: 1500,
          project_count: 4,
          expense_type_count: 8,
          bank_account_count: 3,
          cost_transaction_count: 12000,
        },
        available_years: ["2026"],
        facets: {},
        rows: [{
          transaction_id: "cost-txn-145",
          trade_time: "2026-03-18 17:02:09",
          direction: "支出",
          project_name: "云南溯源科技",
          expense_type: "交通费",
          expense_content: "项目现场往返交通",
          amount: "145.00",
          counterparty_name: "陈佳玉",
          oa_applicant: "报销成员甲",
          payment_account_label: "建行 8106",
          bank_account_label: "建行 8106",
          remark: "报销",
        }],
        row_count: 1,
        next_cursor: null,
      }), { status: 200 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorerPage({
      scope: "2026-03",
      view: "project",
      projectName: "云南溯源科技",
      expenseType: "交通费",
    });

    expect(payload.statistics).toEqual(expect.objectContaining({
      projectCount: 4,
      expenseTypeCount: 8,
      bankAccountCount: 3,
      costTransactionCount: 12000,
      transactionCount: 12500,
      expenseTransactionCount: 11000,
      incomeTransactionCount: 1500,
    }));
    expect(payload.rows[0]).toMatchObject({
      oaApplicant: "报销成员甲",
      bankAccountLabel: "建行 8106",
    });
  });

  test("maps signed bank-flow summaries and tag drill-down filters", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        scope: "2026-08",
        view: "bank_tag",
        summary: {
          row_count: 3,
          transaction_count: 3,
          total_amount: "2100.00",
          expense_amount: "4200.00",
          income_amount: "2100.00",
          expense_transaction_count: 2,
          income_transaction_count: 1,
        },
        statistics: {
          transaction_count: 3,
          expense_transaction_count: 2,
          income_transaction_count: 1,
          untagged_transaction_count: 0,
          bank_tag_count: 1,
        },
        available_years: ["2026"],
        facets: {
          bank_tag_primary: [{
            primary_label: "住宿费",
            expense_amount: "4200.00",
            income_amount: "2100.00",
            net_outflow_amount: "2100.00",
            expense_transaction_count: 2,
            income_transaction_count: 1,
            transaction_count: 3,
            sub_tag_count: 1,
          }],
          bank_tag_sub: [{
            primary_label: "住宿费",
            sub_label: "住宿费",
            expense_amount: "4200.00",
            income_amount: "2100.00",
            net_outflow_amount: "2100.00",
            expense_transaction_count: 2,
            income_transaction_count: 1,
            transaction_count: 3,
          }],
        },
        rows: [{
          entry_id: "bank-out-1",
          row_kind: "bank_transaction",
          transaction_id: "bank-out-1",
          trade_time: "2026-08-03 15:43:00",
          direction: "支出",
          amount: "2100.00",
          counterparty_name: "张丽芬",
          bank_account_label: "建行 8106",
          bank_tag_code: "lodging",
          bank_tag_label: "住宿费",
          bank_tag_primary_label: "住宿费",
          bank_tag_sub_label: "住宿费",
          bank_tag_label_path: ["住宿费"],
          remark: "住宿费",
        }],
        row_count: 3,
        next_cursor: null,
        allocation_quality: null,
      }), { status: 200 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorerPage({
      scope: "2026-08",
      view: "bank_tag",
      bankTagPrimaryLabel: "住宿费",
      bankTagSubLabel: "住宿费",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=2026-08&view=bank_tag&bank_tag_primary_label=%E4%BD%8F%E5%AE%BF%E8%B4%B9&bank_tag_sub_label=%E4%BD%8F%E5%AE%BF%E8%B4%B9",
      expect.any(Object),
    );
    expect(payload.summary).toMatchObject({
      totalAmount: "2100.00",
      expenseAmount: "4200.00",
      incomeAmount: "2100.00",
    });
    expect(payload.facets.bankTagPrimary[0]).toMatchObject({
      primaryLabel: "住宿费",
      netOutflowAmount: "2100.00",
      transactionCount: 3,
    });
    expect(payload.rows[0]).toMatchObject({
      rowKind: "bank_transaction",
      direction: "支出",
      bankTagPrimaryLabel: "住宿费",
    });
  });

  test("maps the bank-account facet contract and sends the project drill-down", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        scope: "all",
        view: "bank_account",
        summary: {
          row_count: 1,
          transaction_count: 1,
          total_amount: "90.00",
        },
        available_years: ["2026"],
        facets: {
          projects: [{
            project_name: "云南溯源科技",
            total_amount: "90.00",
            expense_type_count: 1,
          }],
          bank_accounts: [{
            bank_account_label: "建设银行 8106",
            total_amount: "90.00",
            project_count: 1,
          }],
        },
        rows: [],
        row_count: 0,
        next_cursor: null,
      }), { status: 200 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorerPage({
      scope: "all",
      view: "bank_account",
      bankAccountLabel: "建设银行 8106",
      projectName: "云南溯源科技",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?scope=all&view=bank_account&project_name=%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80&bank_account_label=%E5%BB%BA%E8%AE%BE%E9%93%B6%E8%A1%8C+8106",
      expect.any(Object),
    );
    expect(payload.facets.projects[0].projectName).toBe("云南溯源科技");
    expect(payload.facets.bankAccounts[0]).toEqual({
      bankAccountLabel: "建设银行 8106",
      totalAmount: "90.00",
      projectCount: 1,
    });
  });

  test("loads and saves no-OA rules", async () => {
    global.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url === "/api/cost-statistics/no-oa-rules") {
        return new Response(JSON.stringify({
          version: 3,
          bank_auto_tag_rules_version: 8,
          projects: init?.method === "PUT" ? [{ id: "travel", display_name: "差旅无 OA", tag_codes: ["fee"] }] : [],
          inactive_selected_tag_codes: [],
          available_tags: [{
            code: "fee",
            label: "费用",
            path: ["费用", "材料"],
            output_primary_label: "费用",
            output_sub_label: "材料",
          }],
          can_save: true,
        }), { status: 200 });
      }
      return new Response(null, { status: 404 });
    }) as typeof fetch;

    const noOaRules = await fetchCostStatisticsNoOaRules();
    const savedNoOaRules = await saveCostStatisticsNoOaRules({
      expectedVersion: noOaRules.version,
      projects: [{ id: "travel", displayName: "差旅无 OA", tagCodes: ["fee"] }],
    });

    expect(savedNoOaRules.projects[0]).toEqual({ id: "travel", displayName: "差旅无 OA", tagCodes: ["fee"] });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/no-oa-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 3,
          projects: [{ id: "travel", display_name: "差旅无 OA", tag_codes: ["fee"] }],
        }),
      }),
    );
  });

  test("does not retain explorer payloads in module memory", async () => {
    global.fetch = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({
        scope: "2026-03",
        view: "bank_account",
        summary: {
          row_count: 0,
          transaction_count: 0,
          total_amount: "0.00",
        },
        available_years: ["2026"],
        facets: {},
        rows: [],
        row_count: 0,
        next_cursor: null,
      }), { status: 200 }),
    ) as typeof fetch;

    await fetchCostStatisticsExplorerPage({ scope: "2026-03", view: "bank_account" });
    await fetchCostStatisticsExplorerPage({ scope: "2026-03", view: "bank_account" });

    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
