import { afterEach, describe, expect, test, vi } from "vitest";

import {
  fetchBatchAccounting,
  fetchBatchAccountingTagRules,
  saveBatchAccountingTagRules,
  submitBatchAccounting,
  withdrawBatchAccounting,
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
      tag_selection_version: 4,
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
    expect(payload.tagSelectionVersion).toBe(4);
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
      expectedTagSelectionVersion: 4,
      note: "确认",
      idempotencyKey: "batch-submit-1",
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
          expected_tag_selection_version: 4,
          note: "确认",
          idempotency_key: "batch-submit-1",
        }),
      }),
    );
  });

  test("sends the withdraw idempotency key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-BATCH-001",
        affected_months: ["2026-05"],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    await withdrawBatchAccounting({
      relationId: "CASE-BATCH-001",
      expectedVersion: 3,
      reason: "更正",
      idempotencyKey: "batch-withdraw-1",
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/batch-accounting/CASE-BATCH-001/withdraw",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_version: 3,
          reason: "更正",
          idempotency_key: "batch-withdraw-1",
        }),
      }),
    );
  });

  test("maps and saves canonical tag rules with one versioned request", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify({
      version: init?.method === "PUT" ? 3 : 2,
      bank_auto_tag_rules_version: 9,
      selected_tag_codes: ["fee"],
      active_tags: [{
        code: "fee",
        label: "手续费",
        path: ["费用", "手续费"],
        output_primary_label: "费用",
        output_sub_label: "手续费",
      }],
      can_save: true,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const current = await fetchBatchAccountingTagRules();
    const saved = await saveBatchAccountingTagRules({
      expectedVersion: current.version,
      selectedTagCodes: [],
    });

    expect(current.activeTags[0]).toMatchObject({
      code: "fee",
      outputPrimaryLabel: "费用",
      outputSubLabel: "手续费",
    });
    expect(saved.version).toBe(3);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/batch-accounting/tag-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ expected_version: 2, selected_tag_codes: [] }),
      }),
    );
  });
});
