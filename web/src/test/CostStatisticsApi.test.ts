import { afterEach, describe, expect, test, vi } from "vitest";

import {
  clearCostStatisticsExplorerCache,
  exportCostStatisticsView,
  fetchCostStatisticsExplorer,
  fetchCostStatisticsExportPreview,
  fetchCostStatisticsTagRules,
  getCachedCostStatisticsExplorer,
  saveCostStatisticsTagRules,
} from "../features/cost-statistics/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  clearCostStatisticsExplorerCache();
  vi.restoreAllMocks();
});

describe("Cost statistics export API", () => {
  test("prefers RFC 5987 filename* from content disposition for exports", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(new Blob(["xlsx"]), {
        status: 200,
        headers: {
          "Content-Disposition":
            "attachment; filename=\"cost_statistics_export.xlsx\"; filename*=UTF-8''%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx",
        },
      }),
    ) as typeof fetch;

    const result = await exportCostStatisticsView({
      month: "2026-03",
      view: "time",
    });

    expect(result.fileName).toBe("成本统计_2026-03_按时间统计.xlsx");
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
      view: "time",
    })).rejects.toThrow("导出结果超过 20000 行，请缩小筛选范围后重试。");
  });

  test("passes project scope to explorer, export preview, and export requests", async () => {
    global.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/cost-statistics/explorer")) {
        return new Response(JSON.stringify({
          month: "all",
          summary: {
            row_count: 0,
            transaction_count: 0,
            total_amount: "0.00",
          },
          time_rows: [],
          bank_accounts: [],
          project_rows: [],
          expense_type_rows: [],
        }), { status: 200 });
      }
      if (url.startsWith("/api/cost-statistics/export-preview")) {
        return new Response(JSON.stringify({
          view: "time",
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

    await fetchCostStatisticsExplorer("all", undefined, "all");
    await fetchCostStatisticsExportPreview({
      month: "all",
      view: "time",
      projectScope: "all",
    });
    await exportCostStatisticsView({
      month: "all",
      view: "time",
      projectScope: "all",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/explorer?month=all&project_scope=all",
      expect.any(Object),
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/export-preview?month=all&view=time&project_scope=all",
      expect.any(Object),
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/export?month=all&view=time&project_scope=all",
      expect.any(Object),
    );
  });

  test("maps read model status metadata from explorer payloads", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        month: "2026-03",
        summary: {
          row_count: 0,
          transaction_count: 0,
          total_amount: "0.00",
        },
        time_rows: [],
        bank_accounts: [],
        project_rows: [],
        expense_type_rows: [],
        read_model_status: "refreshing",
        read_model_scope_key: "active:2026-03",
        read_model_generated_at: "2026-06-01T00:00:00",
        read_model_stale_reasons: ["workbench_scope_key"],
      }), { status: 202 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorer("2026-03", undefined, "active");

    expect(payload.readModelStatus).toBe("refreshing");
    expect(payload.readModelScopeKey).toBe("active:2026-03");
    expect(payload.readModelGeneratedAt).toBe("2026-06-01T00:00:00");
    expect(payload.readModelStaleReasons).toEqual(["workbench_scope_key"]);
  });

  test("maps bank tag fields from explorer time rows", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        month: "2026-03",
        summary: {
          row_count: 1,
          transaction_count: 1,
          total_amount: "145.00",
        },
        time_rows: [
          {
            transaction_id: "cost-txn-145",
            trade_time: "2026-03-18 17:02:09",
            direction: "支出",
            project_name: "云南溯源科技",
            expense_type: "交通费",
            expense_content: "项目现场往返交通",
            amount: "145.00",
            counterparty_name: "陈佳玉",
            payment_account_label: "建行 8106",
            remark: "报销",
            bank_tag_code: "travel_transport",
            bank_tag_label: "交通费",
            bank_tag_primary_label: "差旅交通",
            bank_tag_sub_label: "交通费",
            bank_tag_label_path: ["差旅交通", "交通费"],
          },
        ],
        bank_accounts: [
          {
            bank_name: "民生银行",
            account_last4: "9486",
            payment_account_label: "民生银行 账户 9486",
            source: "settings",
          },
        ],
        project_rows: [],
        expense_type_rows: [],
      }), { status: 200 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorer("2026-03", undefined, "active");

    expect(payload.timeRows[0]).toMatchObject({
      bankTagCode: "travel_transport",
      bankTagLabel: "交通费",
      bankTagPrimaryLabel: "差旅交通",
      bankTagSubLabel: "交通费",
      bankTagLabelPath: ["差旅交通", "交通费"],
    });
    expect(payload.bankAccounts).toEqual([
      {
        paymentAccountLabel: "民生银行 账户 9486",
        bankName: "民生银行",
        accountLast4: "9486",
        source: "settings",
      },
    ]);
  });

  test("maps bank flow time rows separately from OA paired time rows", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        month: "2026-03",
        summary: {
          row_count: 1,
          transaction_count: 1,
          total_amount: "100.00",
        },
        time_rows: [
          {
            transaction_id: "oa-fee",
            trade_time: "2026-03-18 17:02:09",
            direction: "支出",
            project_name: "云南溯源科技",
            expense_type: "材料",
            expense_content: "设备",
            amount: "100.00",
            counterparty_name: "供应商",
            payment_account_label: "建行 8106",
            remark: "",
            bank_tag_code: "fee",
          },
        ],
        bank_flow_summary: {
          row_count: 3,
          transaction_count: 3,
          total_amount: "330.00",
          expense_amount: "130.00",
          income_amount: "200.00",
          expense_transaction_count: 2,
          income_transaction_count: 1,
        },
        bank_flow_time_rows: [
          {
            transaction_id: "oa-fee",
            trade_time: "2026-03-18 17:02:09",
            direction: "支出",
            project_name: "云南溯源科技",
            expense_type: "材料",
            expense_content: "设备",
            amount: "100.00",
            counterparty_name: "供应商",
            payment_account_label: "建行 8106",
            remark: "",
            bank_tag_code: "fee",
          },
          {
            transaction_id: "income-fee",
            trade_time: "2026-03-20 09:00:00",
            direction: "收入",
            project_name: "未配对OA",
            expense_type: "退款",
            expense_content: "供应商退款",
            amount: "200.00",
            counterparty_name: "供应商",
            payment_account_label: "建行 8106",
            remark: "",
            bank_tag_code: "income_refund",
          },
          {
            transaction_id: "flow-fee",
            trade_time: "2026-03-19 09:00:00",
            direction: "支出",
            project_name: "未配对OA",
            expense_type: "材料",
            expense_content: "耗材",
            amount: "30.00",
            counterparty_name: "供应商",
            payment_account_label: "建行 8106",
            remark: "",
            bank_tag_code: "fee",
          },
        ],
        bank_accounts: [],
        project_rows: [],
        expense_type_rows: [],
      }), { status: 200 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorer("2026-03", undefined, "active");

    expect(payload.summary.totalAmount).toBe("100.00");
    expect(payload.bankFlowSummary.expenseAmount).toBe("130.00");
    expect(payload.bankFlowSummary.incomeAmount).toBe("200.00");
    expect(payload.bankFlowSummary.expenseTransactionCount).toBe(2);
    expect(payload.bankFlowSummary.incomeTransactionCount).toBe(1);
    expect(payload.timeRows.map((row) => row.transactionId)).toEqual(["oa-fee"]);
    expect(payload.bankFlowTimeRows.map((row) => row.transactionId)).toEqual(["oa-fee", "income-fee", "flow-fee"]);
  });

  test("loads and saves cost statistics tag rules with operation barrier targets", async () => {
    global.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url === "/api/cost-statistics/tag-rules" && init?.method === "PUT") {
        return new Response(JSON.stringify({
          version: 2,
          bank_auto_tag_rules_version: 8,
          default_selection_applied: false,
          selected_tag_codes: ["fee"],
          effective_selected_tag_codes: ["fee"],
          inactive_selected_tag_codes: [],
          active_tags: [
            {
              code: "fee",
              label: "费用",
              path: ["费用", "材料"],
              output_primary_label: "费用",
              output_sub_label: "材料",
            },
          ],
          can_save: true,
          operation_barrier_targets: [
            {
              read_model_key: "cost_statistics",
              scope_key: "active:2026-03",
              scope_type: "cost_statistics",
            },
          ],
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        version: 1,
        bank_auto_tag_rules_version: 8,
        default_selection_applied: true,
        selected_tag_codes: ["fee", "__uncategorized__"],
        effective_selected_tag_codes: ["fee", "__uncategorized__"],
        inactive_selected_tag_codes: [],
        active_tags: [
          {
            code: "fee",
            label: "费用",
            path: ["费用", "材料"],
            output_primary_label: "费用",
            output_sub_label: "材料",
          },
          {
            code: "__uncategorized__",
            label: "未分类",
            path: ["未分类", "未分类"],
            output_primary_label: "未分类",
            output_sub_label: "未分类",
          },
        ],
        can_save: true,
      }), { status: 200 });
    }) as typeof fetch;

    const rules = await fetchCostStatisticsTagRules();
    const saved = await saveCostStatisticsTagRules({
      expectedVersion: rules.version,
      selectedTagCodes: ["fee"],
      currentScopeKey: "active:2026-03",
    });

    expect(rules.activeTags.map((tag) => tag.label)).toEqual(["费用", "未分类"]);
    expect(saved.selectedTagCodes).toEqual(["fee"]);
    expect(saved.operationBarrierTargets).toEqual([
      {
        readModelKey: "cost_statistics",
        scopeKey: "active:2026-03",
        scopeType: "cost_statistics",
      },
    ]);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/tag-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 1,
          selected_tag_codes: ["fee"],
          current_scope_key: "active:2026-03",
        }),
      }),
    );
  });

  test("caches explorer payloads by month and project scope for fast page re-entry", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        month: "2026-03",
        summary: {
          row_count: 0,
          transaction_count: 0,
          total_amount: "0.00",
        },
        time_rows: [],
        bank_accounts: [],
        project_rows: [],
        expense_type_rows: [],
      }), { status: 200 }),
    ) as typeof fetch;

    expect(getCachedCostStatisticsExplorer("2026-03", "active")).toBeNull();
    const payload = await fetchCostStatisticsExplorer("2026-03", undefined, "active");

    expect(getCachedCostStatisticsExplorer("2026-03", "active")).toEqual(payload);
    expect(getCachedCostStatisticsExplorer("2026-03", "all")).toBeNull();
  });
});
