import { afterEach, describe, expect, test, vi } from "vitest";

import {
  fetchBatchAccounting,
  submitBatchAccounting,
} from "../features/batchAccounting/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("batch accounting API", () => {
  test("maps empty direct payload without freshness fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        summary: { unsubmitted_count: 0, submitted_count: 0 },
        bank_rows: [],
        oa_rows: [],
        relations_by_bank_row_id: {},
        pagination: {},
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBatchAccounting({
      bankYear: "2026",
      oaYear: "2026",
      bucket: "unsubmitted",
    });

    expect(payload).toMatchObject({
      summary: { unsubmittedCount: 0, submittedCount: 0 },
      bankRows: [],
      oaRows: [],
      relationsByBankRowId: {},
      pagination: {},
    });
  });

  test("maps mutation affected scopes", async () => {
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
      oaYear: "2026",
      bankRowId: "bank-1",
      oaRowIds: ["oa-1"],
      expectedVersion: 3,
      note: "确认",
    });

    expect(payload.affectedScopeKeys).toEqual(["2026-05"]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/batch-accounting/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          bank_year: "2026",
          oa_year: "2026",
          bank_row_id: "bank-1",
          oa_row_ids: ["oa-1"],
          expected_version: 3,
          note: "确认",
        }),
      }),
    );
  });
});
