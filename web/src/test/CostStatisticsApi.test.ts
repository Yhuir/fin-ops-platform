import { afterEach, describe, expect, test, vi } from "vitest";

import {
  clearCostStatisticsExplorerCache,
  exportCostStatisticsView,
  fetchCostStatisticsExplorer,
  fetchCostStatisticsExportPreview,
  getCachedCostStatisticsExplorer,
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
