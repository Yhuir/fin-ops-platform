import { afterEach, describe, expect, test, vi } from "vitest";

import {
  fetchBatchAccounting,
  submitBatchAccounting,
} from "../features/batchAccounting/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("batch accounting API", () => {
  test("maps the canonical page response and sends server-side OA search", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      summary: { unsubmitted_count: 0, submitted_count: 2 },
      bank_rows: [],
      oa_rows: [],
      relations_by_bank_row_id: {},
      pagination: {
        bank_rows: { page: 2, page_size: 50, total: 0 },
        oa_rows: { page: 3, page_size: 25, total: 0 },
      },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal(
      "fetch",
      fetchMock,
    );

    const payload = await fetchBatchAccounting({
      bankYear: "2026",
      bucket: "unsubmitted",
      bankPage: 2,
      bankPageSize: 50,
      oaPage: 3,
      oaPageSize: 25,
      oaSearch: "上海客户",
    });

    expect(payload.summary).toEqual({ unsubmittedCount: 0, submittedCount: 2 });
    expect(payload.pagination.bankRows).toEqual({ page: 2, pageSize: 50, total: 0 });
    expect(payload.pagination.oaRows).toEqual({ page: 3, pageSize: 25, total: 0 });
    expect(payload).not.toHaveProperty("readModelStatus");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/batch-accounting?bank_year=2026&bucket=unsubmitted&bank_page=2&bank_page_size=50&oa_page=3&oa_page_size=25&oa_search=%E4%B8%8A%E6%B5%B7%E5%AE%A2%E6%88%B7",
      expect.objectContaining({ method: "GET" }),
    );
  });

  test("maps mutation scopes without page rebuild targets", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-BATCH-001",
        affected_row_ids: ["bank-1", "oa-1"],
        affected_months: ["2026-05"],
        affected_scope_keys: ["2026-05"],
        message: "ok",
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await submitBatchAccounting({
      bankYear: "2026",
      bankRowId: "bank-1",
      oaRowIds: ["oa-1"],
      expectedVersion: 3,
      note: "确认",
    });

    expect(payload.affectedScopeKeys).toEqual(["2026-05"]);
    expect(payload).not.toHaveProperty("operationBarrierTargets");
    expect(fetch).toHaveBeenCalledWith(
      "/api/batch-accounting/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          bank_year: "2026",
          bank_row_id: "bank-1",
          oa_row_ids: ["oa-1"],
          expected_version: 3,
          note: "确认",
        }),
      }),
    );
  });
});
