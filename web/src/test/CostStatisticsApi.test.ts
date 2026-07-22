import { afterEach, describe, expect, test, vi } from "vitest";

import {
  exportCostStatisticsView,
  fetchCostStatisticsExplorerPage,
  fetchCostStatisticsExportPreview,
  fetchCostStatisticsTagRules,
  saveCostStatisticsTagRules,
} from "../features/cost-statistics/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
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

  test("passes the isolated cursor-page contract and project scope to explorer, preview, and export requests", async () => {
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
              transaction_count: 1,
              expense_type_count: 1,
              percentage_label: "100.0%",
            }],
          },
          rows: [],
          row_count: 0,
          next_cursor: "cursor-2",
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

    const page = await fetchCostStatisticsExplorerPage({
      scope: "all",
      view: "project",
      projectScope: "all",
      projectName: "云南溯源科技",
      pageSize: 50,
    });
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
      `/api/cost-statistics/explorer?scope=all&view=project&project_scope=all&project_name=${encodeURIComponent("云南溯源科技")}&page_size=50`,
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
    expect(page.availableYears).toEqual(["2026", "2025"]);
    expect(page.facets.projects[0]).toMatchObject({
      projectName: "云南溯源科技",
      totalAmount: "100.00",
    });
    expect(page.nextCursor).toBe("cursor-2");
  });

  test("maps freshness metadata and bank-tag fields from page rows", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        scope: "2026-03",
        view: "time",
        summary: {
          row_count: 1,
          transaction_count: 1,
          total_amount: "145.00",
        },
        statistics: {
          transaction_count: "12000",
          expense_transaction_count: 7000,
          income_transaction_count: 5000,
          cost_group_count: -1,
          tagged_transaction_count: 4.5,
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
          payment_account_label: "建行 8106",
          remark: "报销",
          bank_tag_code: "travel_transport",
          bank_tag_label: "交通费",
          bank_tag_primary_label: "差旅交通",
          bank_tag_sub_label: "交通费",
          bank_tag_label_path: ["差旅交通", "交通费"],
        }],
        row_count: 1,
        next_cursor: null,
        read_model_status: "refreshing",
        read_model_scope_key: "active:2026-03",
        read_model_generated_at: "2026-06-01T00:00:00",
        read_model_stale_reasons: ["workbench_scope_key"],
      }), { status: 202 }),
    ) as typeof fetch;

    const payload = await fetchCostStatisticsExplorerPage({
      scope: "2026-03",
      view: "time",
      projectScope: "active",
    });

    expect(payload.readModelStatus).toBe("refreshing");
    expect(payload.readModelScopeKey).toBe("active:2026-03");
    expect(payload.readModelGeneratedAt).toBe("2026-06-01T00:00:00");
    expect(payload.readModelStaleReasons).toEqual(["workbench_scope_key"]);
    expect(payload.statistics).toEqual(expect.objectContaining({
      transactionCount: 12000,
      expenseTransactionCount: 7000,
      incomeTransactionCount: 5000,
      costGroupCount: undefined,
      taggedTransactionCount: undefined,
    }));
    expect(payload.rows[0]).toMatchObject({
      bankTagCode: "travel_transport",
      bankTagLabel: "交通费",
      bankTagPrimaryLabel: "差旅交通",
      bankTagSubLabel: "交通费",
      bankTagLabelPath: ["差旅交通", "交通费"],
    });
  });

  test("loads and saves cost statistics tag rules without read model barrier targets", async () => {
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
    });

    expect(rules.activeTags.map((tag) => tag.label)).toEqual(["费用", "未分类"]);
    expect(saved.selectedTagCodes).toEqual(["fee"]);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/cost-statistics/tag-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 1,
          selected_tag_codes: ["fee"],
        }),
      }),
    );
  });

  test("does not retain explorer payloads in module memory", async () => {
    global.fetch = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({
        scope: "2026-03",
        view: "time",
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
        read_model_status: "fresh",
      }), { status: 200 }),
    ) as typeof fetch;

    await fetchCostStatisticsExplorerPage({ scope: "2026-03", view: "time", projectScope: "active" });
    await fetchCostStatisticsExplorerPage({ scope: "2026-03", view: "time", projectScope: "active" });

    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
