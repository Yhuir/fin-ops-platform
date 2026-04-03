import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchWorkbenchSearch } from "../features/search/api";

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("Workbench search API mapping", () => {
  test("normalizes array metadata from backend search payload into joined strings", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          query: "张三",
          summary: {
            total: 1,
            oa: 0,
            bank: 1,
            invoice: 0,
          },
          oa_results: [],
          bank_results: [
            {
              row_id: "bk-001",
              record_type: "bank",
              month: "2026-03",
              zone_hint: "open",
              matched_field: "对方户名",
              title: "杭州张三广告有限公司",
              primary_meta: ["2026-03-12 10:30", "6000.00", "支出"],
              secondary_meta: ["建设银行 8826", "SERIAL-001"],
              status_label: "未配对",
              jump_target: {
                month: "2026-03",
                row_id: "bk-001",
                zone_hint: "open",
                record_type: "bank",
              },
            },
          ],
          invoice_results: [],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    ) as typeof fetch;

    const payload = await fetchWorkbenchSearch({
      q: "张三",
      scope: "all",
      month: "all",
    });

    expect(payload.bankResults[0]?.primaryMeta).toBe("2026-03-12 10:30 / 6000.00 / 支出");
    expect(payload.bankResults[0]?.secondaryMeta).toBe("建设银行 8826 / SERIAL-001");
  });
});
