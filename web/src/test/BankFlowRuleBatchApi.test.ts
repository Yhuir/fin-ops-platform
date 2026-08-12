import { afterEach, describe, expect, test, vi } from "vitest";

import {
  fetchBankFlowRuleBatchDetail,
  fetchBankFlowRuleBatchTagSelection,
  fetchBankFlowRuleBatches,
  saveBankFlowRuleBatchTagSelection,
  submitBankFlowRuleBatch,
  submitBankFlowRuleBatchSelection,
  withdrawBankFlowRuleBatch,
} from "../features/bankFlowRuleBatches/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("bank flow rule batch API", () => {
  test("omits month and all filters when requesting the complete batch scope", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      summary: { categories: [] },
      batches: [],
      pagination: { page: 1, page_size: 50, total: 0 },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchBankFlowRuleBatches({
      month: "",
      type: "all",
      status: "all",
      bucket: "all",
      page: 1,
      pageSize: 50,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bank-flow-rule-batches?page=1&page_size=50",
      expect.objectContaining({ method: "GET" }),
    );
  });

  test("maps tag selection rules and saves paired requirements", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules" && (!init?.method || init.method === "GET")) {
        return new Response(JSON.stringify({
          version: 3,
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
          rules: [
            { tag_code: "fee", requires_oa: false, requires_invoice: false },
          ],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        version: 4,
        active_tags: [],
        rules: [],
        requirement_changed_tag_codes: ["fee"],
        recalculation_job: { job_id: "job-recalculate-1" },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = await fetchBankFlowRuleBatchTagSelection();
    const saved = await saveBankFlowRuleBatchTagSelection({
      expectedVersion: payload.version,
      rules: [
        { tagCode: "fee", requiresOa: false, requiresInvoice: false },
        { tagCode: "custom_no_sub", requiresOa: true, requiresInvoice: false },
      ],
    });

    expect(payload).toMatchObject({
      version: 3,
      rules: [
        { tagCode: "fee", requiresOa: false, requiresInvoice: false },
        { tagCode: "custom_no_sub", requiresOa: true, requiresInvoice: true },
      ],
      activeTags: [
        { code: "fee", label: "手续费", outputPrimaryLabel: "费用", outputSubLabel: "手续费", status: "active" },
        { code: "custom_no_sub", label: "主标签本身", outputPrimaryLabel: "其他免OA", outputSubLabel: "", status: "active" },
      ],
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/bank-flow-rule-batches/tag-rules",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 3,
          rules: [
            { tag_code: "fee", requires_oa: false, requires_invoice: false },
            { tag_code: "custom_no_sub", requires_oa: true, requires_invoice: false },
          ],
        }),
      }),
    );
    expect(saved.version).toBe(4);
    expect(saved.requirementChangedTagCodes).toEqual(["fee"]);
    expect(saved.recalculationJobId).toBe("job-recalculate-1");
    expect(saved).not.toHaveProperty("refreshEnqueued");
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
          total_row_count: 12,
          draftRowCount: 12,
          submitted_row_count: 0,
          withdrawnRowCount: 0,
          total_amount: "12345.67",
          categories: [
            { code: "fee", label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_row_count: 12, draft_row_count: 12, submitted_row_count: 0, withdrawn_row_count: 0, total_amount: "88.00" },
            { code: "bonus", label: "奖金", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_row_count: 0, draft_row_count: 0, submitted_row_count: 0, withdrawn_row_count: 0, total_amount: "0.00" },
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
        pagination: { page: 2, page_size: 50, total: 125 },
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankFlowRuleBatches({
      month: "2026-05",
      type: "all",
      bucket: "unsubmitted",
      accountKey: "ccb:8106",
      page: 2,
      pageSize: 50,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/bank-flow-rule-batches?month=2026-05&bucket=unsubmitted&account_key=ccb%3A8106&page=2&page_size=50",
      expect.objectContaining({ method: "GET" }),
    );
    expect(payload.summary).toEqual({
      draftCount: 1,
      submittedCount: 2,
      withdrawnCount: 3,
      conflictCount: 4,
      staleCount: 5,
      totalRowCount: 12,
      draftRowCount: 12,
      submittedRowCount: 0,
      withdrawnRowCount: 0,
      totalAmount: "12345.67",
      categories: [
        { code: "fee", label: "手续费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, totalRowCount: 12, draftRowCount: 12, submittedRowCount: 0, withdrawnRowCount: 0, totalAmount: "88.00" },
        { code: "bonus", label: "奖金", total: 0, draft: 0, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, totalRowCount: 0, draftRowCount: 0, submittedRowCount: 0, withdrawnRowCount: 0, totalAmount: "0.00" },
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
    expect(payload.pagination).toEqual({ page: 2, pageSize: 50, total: 125 });
    expect(payload).not.toHaveProperty("readModelStatus");
  });

  test("maps legacy unsubmitted batch status to draft in the unsubmitted bucket", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        summary: {
          draft_count: 1,
          submitted_count: 0,
          withdrawn_count: 0,
          conflict_count: 0,
          stale_count: 0,
          total_amount: "40.50",
          categories: [],
        },
        batches: [
          {
            batch_id: "batch-legacy-unsubmitted-fee",
            batch_type: "fee",
            batch_label: "手续费",
            scope_month: "2026-01",
            account_key: "ccb:8106",
            bank_name: "建设银行",
            account_last4: "8106",
            status: "unsubmitted",
            status_bucket: "unsubmitted",
            row_count: 14,
            total_amount: "40.50",
            tag_counts: { fee: 14 },
            direction_counts: { expense: 14 },
            can_submit: false,
            can_withdraw: false,
            blocked_reason: "",
            version: 3,
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankFlowRuleBatches({ bucket: "unsubmitted" });

    expect(payload.batches[0]).toMatchObject({
      batchId: "batch-legacy-unsubmitted-fee",
      status: "draft",
      statusBucket: "unsubmitted",
      canSubmit: true,
      blockedReason: "",
    });
  });

  test("maps relation-backed stale batches as submitted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        summary: {
          draft_count: 0,
          submitted_count: 1,
          withdrawn_count: 0,
          conflict_count: 0,
          stale_count: 0,
          total_amount: "86.00",
          categories: [],
        },
        batches: [
          {
            batch_id: "batch-stale-submitted",
            batch_type: "fee",
            batch_label: "手续费",
            scope_month: "2026-03",
            status: "stale",
            status_bucket: "submitted",
            blocked_reason: "源流水或分类已变化，需要复核后处理。",
            can_submit: true,
            can_withdraw: true,
            version: 4,
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankFlowRuleBatches({ bucket: "submitted" });

    expect(payload.batches[0]).toMatchObject({
      batchId: "batch-stale-submitted",
      status: "submitted",
      statusBucket: "submitted",
      blockedReason: "",
      canSubmit: false,
      canWithdraw: true,
    });
  });

  test("filters non-public exception batch statuses from list payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        summary: {
          draft_count: 1,
          submitted_count: 1,
          withdrawn_count: 0,
          conflict_count: 0,
          stale_count: 0,
          total_amount: "2.00",
          categories: [],
        },
        batches: [
          {
            batch_id: "batch-draft-fee",
            batch_type: "fee",
            status: "draft",
            status_bucket: "unsubmitted",
            can_submit: true,
            version: 1,
          },
          {
            batch_id: "batch-conflict-transfer",
            batch_type: "internal_transfer",
            status: "conflict",
            status_bucket: "unsubmitted",
            conflict_reason: "内部往来存在多解，不能自动形成可提交批次。",
            can_submit: false,
            version: 1,
          },
          {
            batch_id: "batch-stale-fee",
            batch_type: "fee",
            status: "stale",
            status_bucket: "unsubmitted",
            blocked_reason: "源流水或分类已变化，需要复核后处理。",
            can_submit: false,
            version: 2,
          },
          {
            batch_id: "batch-stale-submitted",
            batch_type: "fee",
            status: "stale",
            status_bucket: "submitted",
            can_withdraw: true,
            version: 3,
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const payload = await fetchBankFlowRuleBatches();

    expect(payload.batches.map((batch) => batch.batchId)).toEqual(["batch-draft-fee", "batch-stale-submitted"]);
    expect(payload.batches[1]).toMatchObject({
      status: "submitted",
      statusBucket: "submitted",
      canWithdraw: true,
    });
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
            category_primary_label: "费用",
            category_sub_label: "手续费",
            category_label_path: ["费用", "手续费"],
            category_source: "auto",
            relation_status: "linked",
            relation_case_ids: ["case-no-oa-001"],
            linked_oa_count: 2,
            linked_invoice_count: 1,
          },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );

    const detail = await fetchBankFlowRuleBatchDetail("batch-fee-2026-05", "2026-05");

    expect(fetch).toHaveBeenCalledWith(
      "/api/bank-flow-rule-batches/batch-fee-2026-05?scope_month=2026-05",
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
      categoryPrimaryLabel: "费用",
      categorySubLabel: "手续费",
      categoryLabelPath: ["费用", "手续费"],
      relationStatus: "linked",
      relationCaseIds: ["case-no-oa-001"],
      linkedOaCount: 2,
      linkedInvoiceCount: 1,
    });
    expect(detail.tagCounts).toEqual({ fee: 1 });
    expect(detail.directionCounts).toEqual({ expense: 1 });
  });

  test("submits and withdraws with expected version payloads", async () => {
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
      results: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const submit = await submitBankFlowRuleBatch({ batchId: "batch-fee-2026-05", expectedVersion: 1, note: "确认" });
    await withdrawBankFlowRuleBatch({ batchId: "batch-fee-2026-05", expectedVersion: 2, reason: "撤回重核" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/bank-flow-rule-batches/batch-fee-2026-05/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_version: 1, note: "确认" }),
      }),
    );
    expect(submit).not.toHaveProperty("affectedScopeKeys");
    expect(submit).not.toHaveProperty("operationBarrierTargets");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/bank-flow-rule-batches/batch-fee-2026-05/withdraw",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_version: 2, reason: "撤回重核" }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
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
      results: [{ batch_id: "batch-selected-fee", status: "submitted" }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await submitBankFlowRuleBatchSelection({ transactionIds: ["row-1", "row-2"], scopeMonth: "2026-05", note: "提交选中" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bank-flow-rule-batches/submit-selection",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ transaction_ids: ["row-1", "row-2"], scope_month: "2026-05", note: "提交选中" }),
      }),
    );
    expect(result.batch?.batchId).toBe("batch-selected-fee");
    expect(result).not.toHaveProperty("operationBarrierTargets");
    expect(result.results).toEqual([{ batch_id: "batch-selected-fee", status: "submitted" }]);
  });

  test("preserves bank flow rule selection and persistence error codes", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      error: "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
      message: "internal transfer selection requires a matched pair",
    }), { status: 400, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(submitBankFlowRuleBatchSelection({ transactionIds: ["row-1"], scopeMonth: "2026-05" })).rejects.toMatchObject({
      code: "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
      message: "internal transfer selection requires a matched pair",
    });

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      error: "bank_flow_rule_batch_persistence_failed",
      message: "流水规则批次保存失败，请稍后重试。",
    }), { status: 500, headers: { "Content-Type": "application/json" } }));

    await expect(submitBankFlowRuleBatch({ batchId: "batch-fee", expectedVersion: 1 })).rejects.toMatchObject({
      code: "bank_flow_rule_batch_persistence_failed",
      message: "流水规则批次保存失败，请稍后重试。",
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

    await expect(fetchBankFlowRuleBatches()).rejects.toThrow("接口返回了 HTML 页面");
  });
});
