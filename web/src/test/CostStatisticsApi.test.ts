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
