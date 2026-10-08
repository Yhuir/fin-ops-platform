import { afterEach, describe, expect, test, vi } from "vitest";
import { fetchBatchAccountingHistory, fetchBatchAccountingHistoryDetail } from "../features/batchAccounting/api";

afterEach(() => vi.unstubAllGlobals());

describe("batch accounting history API", () => {
  test("requests server pagination and preserves unknown amounts", async () => {
    const payload = { summary: { bank_year: null, relation_count: 1, transaction_count: 2 }, rows: [{ relation_id: "r1", bank_amount: null }], pagination: { page: 2, page_size: 50, total: 51 }, available_years: ["2026"] };
    const fetch = vi.fn(async () => new Response(JSON.stringify(payload)));
    vi.stubGlobal("fetch", fetch);
    expect(await fetchBatchAccountingHistory({ bankYear: "all", page: 2, pageSize: 50 })).toEqual(payload);
    expect(fetch).toHaveBeenCalledWith("/api/batch-accounting?bank_year=all&page=2&page_size=50", expect.objectContaining({ method: "GET" }));
  });
  test("encodes relation identity and propagates forbidden or missing detail", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ error: "forbidden", message: "没有查看权限" }), { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    await expect(fetchBatchAccountingHistoryDetail("r/1")).rejects.toThrow("没有查看权限");
    expect(fetch).toHaveBeenCalledWith("/api/batch-accounting/relations/r%2F1", expect.objectContaining({ method: "GET" }));
  });
});
