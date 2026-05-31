import { afterEach, describe, expect, test, vi } from "vitest";

import {
  fetchNoOaBankBatchDetail,
  fetchNoOaBankBatchTagSelection,
  fetchNoOaBankBatches,
  saveNoOaBankBatchTagSelection,
  submitNoOaBankBatch,
  submitNoOaBankBatches,
  submitNoOaBankBatchSelection,
  withdrawNoOaBankBatch,
} from "../features/noOaBankBatches/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("no OA bank batch API", () => {
  test("maps tag selection payload and saves selected tag codes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify({
          version: 3,
          selected_tag_codes: ["fee"],
          inactive_selected_tag_codes: ["archived_fee"],
          active_tags: [
            {
              code: "fee",
              label: "手续费",
              output_primary_label: "费用",
              output_sub_label: "手续费",
              status: "active",
            },
            {
              code: "custom_no_sub",
              label: "主标签本身",
              output_primary_label: "其他免OA",
              output_sub_label: "",
              status: "active",
            },
          ],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        version: 4,
        selected_tag_codes: ["fee", "custom_no_sub"],
        inactive_selected_tag_codes: [],
        active_tags: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchNoOaBankBatchTagSelection();
    const saved = await saveNoOaBankBatchTagSelection({ expectedVersion: payload.version, selectedTagCodes: ["fee", "custom_no_sub"] });

    expect(payload).toMatchObject({
      version: 3,
      selectedTagCodes: ["fee"],
      inactiveSelectedTagCodes: ["archived_fee"],
      activeTags: [
        { code: "fee", label: "手续费", outputPrimaryLabel: "费用", outputSubLabel: "手续费", status: "active" },
        { code: "custom_no_sub", label: "主标签本身", outputPrimaryLabel: "其他免OA", outputSubLabel: "", status: "active" },
      ],
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/no-oa-bank-batches/tag-selection",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ expected_version: 3, selected_tag_codes: ["fee", "custom_no_sub"] }),
      }),
    );
    expect(saved.version).toBe(4);
  });

  test("maps snake_case and camelCase batch payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        summary: {
          draft_count: 1,
          submittedCount: 2,
          withdrawn_count: 3,
          conflictCount: 4,
          stale_count: 5,
          total_amount: "12345.67",
          categories: [
            { code: "fee", label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "88.00" },
            { code: "bonus", label: "奖金", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "0.00" },
          ],
        },
        batches: [
          {
            batch_id: "batch-fee-2026-05",
            batch_type: "fee",
            batch_label: "手续费",
            scope_month: "2026-05",
            account_key: "ccb:8106",
            bank_name: "建设银行",
            account_last4: "8106",
            status: "draft",
            status_bucket: "unsubmitted",
            row_count: 12,
            total_amount: "88.00",
            submitted_by: "",
            submitted_at: null,
            withdrawn_by: "",
            withdrawn_at: null,
            conflict_reason: "",
            blocked_reason: "",
            tag_counts: { fee: 12 },
            direction_counts: { expense: 12 },
            can_submit: true,
            can_withdraw: false,
            version: 7,
          },
          {
            batchId: "batch-salary-2026-05",
            batchType: "salary",
            batchLabel: "工资",
            scopeMonth: "2026-05",
            accountKey: "icbc:6386",
            bankName: "工商银行",
            accountLast4: "6386",
            status: "submitted",
            rowCount: 4,
            totalAmount: "10000.00",
            submittedBy: "finance-user",
            submittedAt: "2026-05-10T09:30:00",
            withdrawnBy: "",
            withdrawnAt: null,
            blockedReason: "已提交批次不可重复提交",
            tagCounts: { salary: 4 },
            directionCounts: { expense: 4 },
            canSubmit: false,
            canWithdraw: true,
            version: 2,
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchNoOaBankBatches({
      month: "2026-05",
      type: "all",
      bucket: "unsubmitted",
      accountKey: "ccb:8106",
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/no-oa-bank-batches?month=2026-05&bucket=unsubmitted&account_key=ccb%3A8106",
      expect.objectContaining({ method: "GET" }),
    );
    expect(payload.summary).toEqual({
      draftCount: 1,
      submittedCount: 2,
      withdrawnCount: 3,
      conflictCount: 4,
      staleCount: 5,
      totalAmount: "12345.67",
      categories: [
        { code: "fee", label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, totalAmount: "88.00" },
        { code: "bonus", label: "奖金", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, totalAmount: "0.00" },
      ],
    });
    expect(payload.batches).toEqual([
      expect.objectContaining({
        batchId: "batch-fee-2026-05",
        batchType: "fee",
        batchLabel: "手续费",
        scopeMonth: "2026-05",
        accountKey: "ccb:8106",
        bankName: "建设银行",
        accountLast4: "8106",
        status: "draft",
        statusBucket: "unsubmitted",
        rowCount: 12,
        totalAmount: "88.00",
        tagCounts: { fee: 12 },
        directionCounts: { expense: 12 },
        canSubmit: true,
        canWithdraw: false,
        blockedReason: "",
        version: 7,
      }),
      expect.objectContaining({
        batchId: "batch-salary-2026-05",
        batchType: "salary",
        batchLabel: "工资",
        submittedBy: "finance-user",
        submittedAt: "2026-05-10T09:30:00",
        canSubmit: false,
        canWithdraw: true,
      }),
    ]);
  });

  test("maps batch detail rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        batch: {
          batch_id: "batch-fee-2026-05",
          batch_type: "fee",
          batch_label: "手续费",
          scope_month: "2026-05",
          account_key: "ccb:8106",
          bank_name: "建设银行",
          account_last4: "8106",
          status: "draft",
          row_count: 1,
          total_amount: "8.80",
          tag_counts: { fee: 1 },
          direction_counts: { expense: 1 },
          can_submit: true,
          can_withdraw: false,
          version: 1,
        },
        tag_counts: { fee: 1 },
        direction_counts: { expense: 1 },
        rows: [
          {
            transaction_id: "bank-row-001",
            trade_time: "2026-05-03 10:20:00",
            counterparty_name: "建设银行",
            direction: "expense",
            direction_label: "支",
            amount: "8.80",
            bank_name: "建设银行",
            account_last4: "8106",
            account_key: "建设银行:8106",
            summary: "网银手续费",
            purpose: "结算",
            remark: "月结",
            category_code: "fee",
            category_label: "手续费",
            category_source: "auto",
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const detail = await fetchNoOaBankBatchDetail("batch-fee-2026-05");

    expect(fetch).toHaveBeenCalledWith(
      "/api/no-oa-bank-batches/batch-fee-2026-05",
      expect.objectContaining({ method: "GET" }),
    );
    expect(detail.rows[0]).toMatchObject({
      transactionId: "bank-row-001",
      tradeTime: "2026-05-03 10:20:00",
      counterpartyName: "建设银行",
      directionLabel: "支",
      amount: "8.80",
      bankName: "建设银行",
      accountLast4: "8106",
      accountKey: "建设银行:8106",
      summary: "网银手续费",
      purpose: "结算",
      remark: "月结",
      categorySource: "auto",
      categoryCode: "fee",
      categoryLabel: "手续费",
    });
    expect(detail.tagCounts).toEqual({ fee: 1 });
    expect(detail.directionCounts).toEqual({ expense: 1 });
  });

  test("submits, withdraws, and bulk submits with expected version payloads", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      batch: {
        batch_id: "batch-fee-2026-05",
        batch_type: "fee",
        batch_label: "手续费",
        scope_month: "2026-05",
        account_key: "ccb:8106",
        bank_name: "建设银行",
        account_last4: "8106",
        status: "submitted",
        row_count: 1,
        total_amount: "8.80",
        version: 2,
      },
      affected_months: ["2026-05"],
      workbench_rebuild_queued: true,
      results: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await submitNoOaBankBatch({ batchId: "batch-fee-2026-05", expectedVersion: 1, note: "确认" });
    await withdrawNoOaBankBatch({ batchId: "batch-fee-2026-05", expectedVersion: 2, reason: "撤回重核" });
    await submitNoOaBankBatches({
      batches: [
        { batchId: "batch-fee-2026-05", expectedVersion: 1 },
        { batchId: "batch-bonus-2026-05", expectedVersion: 3 },
      ],
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/no-oa-bank-batches/batch-fee-2026-05/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_version: 1, note: "确认" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/no-oa-bank-batches/batch-fee-2026-05/withdraw",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_version: 2, reason: "撤回重核" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/no-oa-bank-batches/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          batches: [
            { batch_id: "batch-fee-2026-05", expected_version: 1 },
            { batch_id: "batch-bonus-2026-05", expected_version: 3 },
          ],
        }),
      }),
    );
  });

  test("submits selected transaction ids as one batch", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      batch: {
        batch_id: "batch-selected-fee",
        batch_type: "fee",
        batch_label: "手续费",
        scope_month: "2026-05",
        account_key: "ccb:8106",
        bank_name: "建设银行",
        account_last4: "8106",
        status: "submitted",
        row_count: 2,
        total_amount: "27.00",
        version: 2,
      },
      affected_months: ["2026-05"],
      workbench_rebuild_queued: true,
      results: [{ batch_id: "batch-selected-fee", status: "submitted" }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitNoOaBankBatchSelection({ transactionIds: ["row-1", "row-2"], note: "提交选中" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/no-oa-bank-batches/submit-selection",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ transaction_ids: ["row-1", "row-2"], note: "提交选中" }),
      }),
    );
    expect(result.batch?.batchId).toBe("batch-selected-fee");
    expect(result.results).toEqual([{ batch_id: "batch-selected-fee", status: "submitted" }]);
  });

  test("preserves no OA selection and persistence error codes", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      error: "no_oa_bank_batch_selection_internal_transfer_requires_pair",
      message: "internal transfer selection requires a matched pair",
    }), { status: 400, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(submitNoOaBankBatchSelection({ transactionIds: ["row-1"] })).rejects.toMatchObject({
      code: "no_oa_bank_batch_selection_internal_transfer_requires_pair",
      message: "internal transfer selection requires a matched pair",
    });

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      error: "no_oa_bank_batch_persistence_failed",
      message: "免OA流水批次保存失败，请稍后重试。",
    }), { status: 500, headers: { "Content-Type": "application/json" } }));

    await expect(submitNoOaBankBatch({ batchId: "batch-fee", expectedVersion: 1 })).rejects.toMatchObject({
      code: "no_oa_bank_batch_persistence_failed",
      message: "免OA流水批次保存失败，请稍后重试。",
    });
  });

  test("reports HTML responses as a backend routing problem", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<!DOCTYPE html><html><body>vite fallback</body></html>", {
        status: 200,
        headers: { "Content-Type": "text/html;charset=utf-8" },
      })),
    );

    await expect(fetchNoOaBankBatches()).rejects.toThrow("接口返回了 HTML 页面");
  });
});
