import { afterEach, describe, expect, test, vi } from "vitest";

import {
  assignWorkbenchInvoiceExpenseItems,
  cancelWorkbenchCashSpecial,
  cancelWorkbenchLink,
  confirmWorkbenchCashPassThrough,
  confirmWorkbenchCashTicketPurchase,
  confirmWorkbenchLink,
  confirmWorkbenchPersonalAdvanceRepayment,
  fetchWorkbenchGroupDetail,
  fetchWorkbenchFilterOptions,
  fetchWorkbenchGroupsPage,
  fetchWorkbenchInitialPage,
  fetchWorkbenchOaSyncStatus,
  fetchWorkbenchRowDetail,
  getManualOaImportAttachmentRefreshStatus,
  importManualOaRows,
  listWorkbenchOaSupportingDocumentGallery,
  previewWorkbenchConfirmLink,
  previewWorkbenchManualInvoices,
  previewWorkbenchWithdrawLink,
  refreshManualOaImportAttachments,
  removeManualOaImport,
  reviewWorkbenchAnomaly,
  resolveWorkbenchActionErrorMessage,
  uploadWorkbenchOaSupportingDocuments,
  withdrawWorkbenchLink,
  WorkbenchApiError,
  WORKBENCH_GROUP_PAGE_SIZE,
} from "../features/workbench/api";
import {
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  countWorkbenchGroupRows,
  createEmptyWorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchRelationGroup, WorkbenchRecord, WorkbenchRecordType } from "../features/workbench/types";

const workbenchPanes: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

test("keeps the combined initial and subsequent group pages at a 10-group first screen", () => {
  expect(WORKBENCH_GROUP_PAGE_SIZE).toBe(10);
});

test("submits explicit invoice ownership through the dedicated command contract", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await assignWorkbenchInvoiceExpenseItems({
    caseId: "CASE-1",
    invoiceRowId: "invoice-27.05",
    targets: [
      { oaRowId: "oa-1", expenseItemId: "item-1" },
      { oaRowId: "oa-1", expenseItemId: "item-2" },
    ],
    anomalyFingerprint: "a".repeat(64),
    idempotencyKey: "assign-ownership-1",
  });

  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/workbench/actions/assign-invoice-expense-items",
    expect.objectContaining({ method: "POST" }),
  );
  expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({
    case_id: "CASE-1",
    invoice_row_id: "invoice-27.05",
    targets: [
      { oa_row_id: "oa-1", expense_item_id: "item-1" },
      { oa_row_id: "oa-1", expense_item_id: "item-2" },
    ],
    anomaly_fingerprint: "a".repeat(64),
    idempotency_key: "assign-ownership-1",
  });
  fetchSpy.mockRestore();
});

test("does not infer a safe OA write state when the status contract is missing", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ dirty_scopes: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  await expect(fetchWorkbenchOaSyncStatus()).resolves.toMatchObject({
    status: "unknown",
    message: "OA 同步状态异常",
    dirtyScopes: [],
  });
  fetchSpy.mockRestore();
});

test("maps supplemental evidence validation errors to an actionable message", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    error: "supporting_document_signature_invalid",
    message: "raw backend message",
    requestId: "request-upload-1",
  }), {
    status: 400,
    headers: { "Content-Type": "application/json" },
  }));

  let captured: unknown;
  try {
    await uploadWorkbenchOaSupportingDocuments(
      { caseId: "CASE-1", oaRowId: "oa-1", expenseItemId: "oa-1:item:0" },
      [new File(["invalid"], "voucher.jpg", { type: "image/jpeg" })],
    );
  } catch (error) {
    captured = error;
  }

  expect(captured).toBeInstanceOf(WorkbenchApiError);
  expect(resolveWorkbenchActionErrorMessage(captured, "fallback")).toBe(
    "文件内容与扩展名不一致，请重新选择有效文件。（请求编号：request-upload-1）",
  );
});

test("reads the supporting document gallery through one bounded cursor page", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    documents: [{
      id: "00000000-0000-4000-8000-000000000001",
      relation_case_id: "CASE-1",
      oa_row_id: "oa-1",
      expense_item_id: "oa-1:item:0",
      file_name: "voucher.pdf",
      content_type: "application/pdf",
      sha256: "sha",
      size_bytes: 1024,
      created_by: "finance-user",
      created_at: "2026-08-23T08:00:00+08:00",
      content_url: "/api/documents/1/content",
      thumbnail_url: "/api/documents/1/thumbnail",
    }],
    page_size: 9,
    has_more: true,
    next_cursor: "cursor-2",
  }), { status: 200, headers: { "Content-Type": "application/json" } }));
  const controller = new AbortController();

  const page = await listWorkbenchOaSupportingDocumentGallery({
    cursor: "cursor-1",
    signal: controller.signal,
  });

  expect(page).toEqual({
    documents: [expect.objectContaining({
      id: "00000000-0000-4000-8000-000000000001",
      createdBy: "finance-user",
      thumbnailUrl: "/api/documents/1/thumbnail",
    })],
    pageSize: 9,
    hasMore: true,
    nextCursor: "cursor-2",
  });
  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/workbench/oa-invoice-supplements/gallery?page_size=9&cursor=cursor-1",
    expect.objectContaining({ signal: controller.signal }),
  );
});

test("previews OA-item invoice entry through the dedicated create-or-link endpoint", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    values: [{
      invoice_direction: "input",
      invoice_nature: "blue",
      seller_name: "云南天谷科技开发有限公司",
      seller_tax_no: "91530112799862049E",
      buyer_name: "云南溯源科技有限公司",
      buyer_tax_no: "915300007194052520",
      invoice_number: "2653700000268955191",
      invoice_code: "",
      invoice_date: "2026-04-14",
      net_amount: "26.26",
      tax_rate: "3",
      tax_amount: "0.79",
      total_with_tax: "27.05",
    }],
    file_ids: ["manual_file_existing_27_05"],
    import_session: {
      session: {
        id: "manual_session_existing_27_05",
        imported_by: "web_finance_user",
        file_count: 1,
        status: "awaiting_confirmation",
        created_at: "2026-08-21T14:00:00+08:00",
      },
      files: [{
        id: "manual_file_existing_27_05",
        file_name: "发票录入",
        template_code: "manual_invoice_entry",
        batch_type: "input_invoice",
        status: "preview_ready",
        message: "命中已有发票",
        row_count: 1,
        success_count: 0,
        error_count: 0,
        duplicate_count: 1,
        suspected_duplicate_count: 0,
        updated_count: 0,
        row_results: [],
      }],
    },
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  const preview = await previewWorkbenchManualInvoices([{
    invoiceDirection: "input",
    invoiceNature: "blue",
    sellerName: "云南天谷科技开发有限公司",
    sellerTaxNo: "91530112799862049E",
    buyerName: "云南溯源科技有限公司",
    buyerTaxNo: "915300007194052520",
    invoiceNumber: "2653700000268955191",
    invoiceCode: "",
    invoiceDate: "2026-04-14",
    netAmount: "26.26",
    taxRate: "3",
    taxAmount: "0.79",
    totalWithTax: "27.05",
  }]);

  expect(preview.fileIds).toEqual(["manual_file_existing_27_05"]);
  expect(preview.importSession.files[0]?.duplicateCount).toBe(1);
  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/workbench/oa-invoice-supplements/manual/preview",
    expect.objectContaining({ method: "POST" }),
  );
  fetchSpy.mockRestore();
});

function createWorkbenchRow(paneId: WorkbenchRecordType, id: string, counterparty: string): WorkbenchRecord {
  return {
    id,
    recordType: paneId,
    label: `${paneId}-${counterparty}`,
    status: "待处理",
    statusCode: "pending",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "100.00",
    counterparty,
    tableValues: {
      applicant: counterparty,
      counterparty,
      projectName: `${counterparty}项目`,
      applicationTime: "2026-03-01",
      transactionTime: "2026-03-01",
      issueDate: "2026-03-01",
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function createWorkbenchGroup(id: string, hitPanes: WorkbenchRecordType[]): WorkbenchRelationGroup {
  return {
    id,
    groupType: "paired",
    rawGroupType: "relation",
    matchConfidence: "high",
    reason: "active_formal_relation",
    rows: {
      oa: [createWorkbenchRow("oa", `${id}-oa`, hitPanes.includes("oa") ? "张三" : "上下文OA")],
      bank: [createWorkbenchRow("bank", `${id}-bank`, hitPanes.includes("bank") ? "张三" : "上下文银行")],
      invoice: [createWorkbenchRow("invoice", `${id}-invoice`, hitPanes.includes("invoice") ? "张三" : "上下文发票")],
    },
  };
}

function createContextSearchGroups(activePaneId: WorkbenchRecordType) {
  const supplementPanes = workbenchPanes.filter((paneId) => paneId !== activePaneId);
  return [
    createWorkbenchGroup(`${activePaneId}-anchor`, [activePaneId]),
    createWorkbenchGroup(`${supplementPanes[0]}-supplement`, [supplementPanes[0]]),
    createWorkbenchGroup(`${supplementPanes[1]}-supplement`, [supplementPanes[1]]),
    createWorkbenchGroup("multi-pane-hit", workbenchPanes),
    createWorkbenchGroup("unmatched", []),
  ];
}

describe("workbench api bank amount mapping", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("maps withdraw relation preview lock fields", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          operation: "withdraw_link",
          operation_type: "withdraw_relation",
          preview_id: "withdraw_relation:abc123",
          submit_expected_versions: { "relation:relation-1": 3 },
          can_submit: true,
          requires_note: false,
          message: "将撤回该关联",
          before: { groups: [] },
          after: {
            groups: [{
              group_id: "selected",
              group_type: "selection",
              match_confidence: "none",
              reason: "selected_rows",
              zone: "unpaired",
              status: "unpaired",
              oa_rows: [],
              bank_rows: [],
              invoice_rows: [],
            }],
          },
          amount_summary: {
            before: { oa_total: "100.00", bank_total: "100.00", invoice_total: "100.00" },
            after: { oa_total: "100.00", bank_total: "100.00", invoice_total: "100.00" },
            status: "matched",
            direction: "payment",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const preview = await previewWorkbenchWithdrawLink({
      month: "all",
      rowIds: ["bank-candidate"],
      rowTypes: ["bank"],
    });

    expect(preview.operation).toBe("withdraw_link");
    expect(preview.operationType).toBe("withdraw_relation");
    expect(preview.previewId).toBe("withdraw_relation:abc123");
    expect(preview.submitExpectedVersions).toEqual({ "relation:relation-1": 3 });
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toMatchObject({
      row_ids: ["bank-candidate"],
      row_types: ["bank"],
    });
    expect(preview.after.groups[0]).toMatchObject({
      groupType: "unpaired",
      rawGroupType: "selection",
    });
  });

  test("sends all members for large confirm and withdraw previews", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => (
      new Response(
        JSON.stringify({
          operation: "confirm_link",
          can_submit: true,
          requires_note: false,
          message: "",
          before: { groups: [] },
          after: { groups: [] },
          amount_summary: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      )
    ));
    const rowIds = Array.from({ length: 500 }, (_, index) => `invoice-${index}`);
    const rowTypes = rowIds.map(() => "invoice" as const);

    await previewWorkbenchConfirmLink({ month: "all", rowIds, rowTypes });
    await previewWorkbenchWithdrawLink({ month: "all", rowIds, rowTypes });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    for (const call of fetchSpy.mock.calls) {
      const body = JSON.parse(String(call[1]?.body));
      expect(body.row_ids).toEqual(rowIds);
      expect(body.row_types).toEqual(rowTypes);
    }
  });

  test("maps preview-only selection groups from their unpaired zone without widening page group types", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          operation: "confirm_link",
          before: {
            groups: [{
              group_id: "selected",
              group_type: "selection",
              match_confidence: "none",
              reason: "selected_rows",
              zone: "unpaired",
              status: "unpaired",
              oa_rows: [],
              bank_rows: [],
              invoice_rows: [],
            }],
          },
          after: {
            groups: [{
              group_id: "case:CASE-1",
              group_type: "relation",
              match_confidence: "high",
              reason: "active_formal_relation",
              exception_state: "processed",
              workbench_anomaly: {
                code: "workbench_anomaly",
                fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                review_decision: "accept_paired",
                review_note: "财务已核对",
                reviewed_by_account: "YNSYLP007",
                reviewed_by_name: "杨丽萍",
                reviewed_at: "2026-08-19 01:00:00+08",
                items: [{
                  code: "oa_bank_equal_invoice_less",
                  label: "OA 流水一致，票少",
                  display_label: "OA 流水一致，票少",
                  fingerprint: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                  comparison_unit_id: "case:CASE-1",
                  oa_total: "100.00",
                  invoice_total: "99.00",
                  amount_delta: "1.00",
                  invoice_row_ids: [],
                  attachment_file_count: 0,
                }],
              },
              zone: "paired",
              status: "paired",
              oa_rows: [],
              bank_rows: [],
              invoice_rows: [],
            }],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const preview = await previewWorkbenchConfirmLink({
      month: "all",
      rowIds: ["oa-1", "bank-1"],
      rowTypes: ["oa", "bank"],
    });

    expect(preview.before.groups[0]).toMatchObject({
      groupType: "unpaired",
      rawGroupType: "selection",
    });
    expect(preview.after.groups[0]).toMatchObject({
      groupType: "paired",
      rawGroupType: "relation",
    });
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toMatchObject({
      row_ids: ["oa-1", "bank-1"],
      row_types: ["oa", "bank"],
    });
  });

  test.each([
    { zone: "unpaired", status: undefined, label: "missing status" },
    { zone: "paired", status: "paired", label: "paired selection" },
  ])("rejects invalid preview selection groups: $label", async ({ zone, status }) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          operation: "withdraw_link",
          after: {
            groups: [{
              group_id: "selected",
              group_type: "selection",
              match_confidence: "none",
              reason: "selected_rows",
              zone,
              ...(status ? { status } : {}),
              oa_rows: [],
              bank_rows: [],
              invoice_rows: [],
            }],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(previewWorkbenchWithdrawLink({
      month: "all",
      rowIds: ["oa-1"],
      rowTypes: ["oa"],
    })).rejects.toThrow("Invalid Workbench relation preview group");
  });

  test("ordinary Workbench group pages still reject preview-only selection groups", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "unpaired",
          page: 1,
          page_size: 50,
          total: 1,
          row_counts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
          has_more: false,
          next_cursor: null,
          groups: [{
            group_id: "selected",
            group_type: "selection",
            match_confidence: "none",
            reason: "selected_rows",
            zone: "unpaired",
            status: "unpaired",
            oa_rows: [],
            bank_rows: [],
            invoice_rows: [],
          }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.toThrow(
      "Unsupported Workbench group type: selection",
    );
  });

  test("maps processed exception groups into the unpaired page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "unpaired",
          page: 1,
          page_size: 50,
          total: 1,
          row_counts: { oa: 1, bank: 0, invoice: 0, rows: 1 },
          has_more: false,
          groups: [{
            group_id: "processed-exception",
            group_type: "processed_exception",
            match_confidence: "medium",
            reason: "processed_exception",
            oa_rows: [{
              id: "oa-processed",
              type: "oa",
              available_actions: ["detail"],
            }],
            bank_rows: [],
            invoice_rows: [],
          }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const page = await fetchWorkbenchGroupsPage("all", "unpaired", null, 50);

    expect(page.groups[0]?.groupType).toBe("unpaired");
    expect(page.groups[0]?.rawGroupType).toBe("processed_exception");
  });

  test("preserves machine fields but never exposes an unknown backend message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "internal_server_error",
          message: "INTERNAL ENGLISH SENTINEL: postgres relation details",
          requestId: "req-500-audit",
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      ),
    );

    const error = await fetchWorkbenchGroupsPage("all", "unpaired", null, 50).catch((caught) => caught);

    expect(error).toBeInstanceOf(WorkbenchApiError);
    expect(error).toMatchObject({
      status: 500,
      code: "internal_server_error",
      requestId: "req-500-audit",
    });
    expect(error.message).toBe("关联台服务暂时不可用，请稍后重试。");
    expect(error.message).not.toContain("INTERNAL ENGLISH SENTINEL");
  });

  test.each([
    ["canonical_selection_conflict", 409, "关联台数据已变化，请刷新后重新预览。"],
    ["workbench_relation_preview_stale", 409, "关联预览已失效，请重新预览。"],
    ["workbench_row_not_found", 404, "所选关联台记录已不可用，请刷新后重新选择。"],
    ["workbench_row_detail_invariant_broken", 503, "关联台详情数据不完整，请稍后重试或联系管理员。"],
    ["workbench_detail_unavailable", 503, "关联台详情暂时不可用，请稍后重试。"],
    ["workbench_anomaly_changed", 409, "异常内容已变化，请刷新后重新审阅。"],
    ["workbench_anomaly_review_blocked", 409, "该关系仍有未解决的配对条件，不能进入已配对。"],
    ["relation_preview_rows_missing", 400, "关联预览无效，请刷新后重新选择。"],
    ["relation_preview_rows_ambiguous", 409, "所选关联台记录内容不一致，请刷新后重试。"],
    ["unknown_auth_error", 401, "登录状态已失效，请重新登录。"],
    ["unknown_permission_error", 403, "当前账号无权执行此操作。"],
    ["unknown_conflict", 409, "关联台数据已变化，请刷新后重新预览。"],
    ["unknown_server_error", 503, "关联台服务暂时不可用，请稍后重试。"],
  ])("maps %s/%i to an approved Chinese message", async (code, status, expectedMessage) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: code,
          message: "RAW BACKEND SENTINEL",
        }),
        { status, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.toThrow(expectedMessage);
    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.not.toThrow("RAW BACKEND SENTINEL");
  });

  test.each([
    ["canonical_selection_changed", "所选 OA、流水或发票已变化，请刷新后重新预览。"],
    ["canonical_selection_ambiguous", "所选 OA 身份存在歧义，无法安全撤回；请刷新后重新选择。"],
    ["stale_relation_identity", "关联关系成员已变化，请刷新后重新预览。"],
    ["stale_relation_version", "关联关系版本已更新，请刷新后重新预览。"],
  ])("maps workbench_write_conflict reason %s precisely", async (reason, expectedMessage) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "workbench_write_conflict",
          message: "RAW BACKEND SENTINEL",
          conflict: { action: "withdraw_link", reason },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.toThrow(expectedMessage);
    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.not.toThrow("RAW BACKEND SENTINEL");
  });

  test.each([
    ["workbench_relation_restore_case_reused", "历史关联关系身份已被占用，无法安全撤回。"],
    ["workbench_relation_restore_owner_conflict", "历史关联成员已被其他关系占用，无法安全撤回。"],
    ["invalid_restored_member_type", "历史关联关系成员类型无效，无法安全撤回。"],
    ["unknown_restore_conflict", "历史关联关系已发生冲突，无法安全撤回。"],
  ])("maps relation restore conflict reason %s precisely", async (reason, expectedMessage) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "workbench_relation_restore_conflict",
          message: "RAW BACKEND SENTINEL",
          reason,
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.toThrow(expectedMessage);
    await expect(fetchWorkbenchGroupsPage("all", "unpaired", null, 50)).rejects.not.toThrow("RAW BACKEND SENTINEL");
  });

  test("never exposes a non-JSON response body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("RAW PARSER SENTINEL", {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const error = await fetchWorkbenchGroupsPage("all", "unpaired", null, 50).catch((caught) => caught);

    expect(error).toBeInstanceOf(WorkbenchApiError);
    expect(error.message).toBe("关联台服务暂时不可用，请稍后重试。");
    expect(error.message).not.toContain("RAW PARSER SENTINEL");
  });

  test("accepts any two canonical members in a successful direct confirm response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          action: "confirm_link",
          month: "2026-05",
          affected_row_ids: ["oa-partial", "bank-partial"],
          affected_months: ["2026-05"],
          affected_scope_keys: ["2026-05"],
          message: "已确认 2 条记录关联。",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await confirmWorkbenchLink({
      month: "2026-05",
      rowIds: ["oa-partial", "bank-partial"],
      rowTypes: ["oa", "bank"],
      caseId: "CASE-PARTIAL",
      idempotencyKey: "confirm-partial-1",
    });

    expect(result.affected_row_ids).toEqual(["oa-partial", "bank-partial"]);
    expect(result).not.toHaveProperty("operationBarrierTargets");
  });

  test("returns affected scopes without a client-side topology projection", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          action: "confirm_link",
          month: "all",
          affected_row_ids: ["bank-only", "invoice-only"],
          affected_scope_keys: ["2026-06", "2026-07"],
          message: "已确认 2 条记录关联。",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await confirmWorkbenchLink({
      month: "all",
      rowIds: ["bank-only", "invoice-only"],
      rowTypes: ["bank", "invoice"],
      caseId: "CASE-TWO-PANE",
      idempotencyKey: "confirm-two-pane-1",
    });

    expect(result.affected_row_ids).toEqual(["bank-only", "invoice-only"]);
    expect(result.affectedScopeKeys).toEqual(["2026-06", "2026-07"]);
  });

  test("keeps typed row identity order in confirm and withdraw submissions", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(
      new Response(
        JSON.stringify({ success: true, affected_row_ids: ["same-id", "same-id"] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ));

    await confirmWorkbenchLink({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["bank", "invoice"],
      idempotencyKey: "typed-confirm-1",
    });
    await withdrawWorkbenchLink({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["bank", "invoice"],
      operationType: "withdraw_relation",
      previewId: "withdraw-relation-1",
      expectedVersions: { "relation:1": 2 },
      idempotencyKey: "typed-withdraw-1",
    });

    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toMatchObject({
      row_ids: ["same-id", "same-id"],
      row_types: ["bank", "invoice"],
    });
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toMatchObject({
      row_ids: ["same-id", "same-id"],
      row_types: ["bank", "invoice"],
    });
  });

  test("keeps typed identity on every supported Workbench row mutation", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(
      new Response(
        JSON.stringify({ success: true, affected_row_ids: ["same-id", "same-id"] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ));

    await cancelWorkbenchLink({
      month: "all",
      rowId: "same-id",
      rowType: "bank",
      idempotencyKey: "typed-cancel-1",
    });
    await confirmWorkbenchPersonalAdvanceRepayment({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["oa", "bank"],
    });
    await confirmWorkbenchCashPassThrough({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["oa", "bank"],
    });
    await confirmWorkbenchCashTicketPurchase({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["oa", "bank"],
      cashAmount: "100.00",
      ticketCostAmount: "20.00",
    });
    await cancelWorkbenchCashSpecial({
      month: "all",
      rowIds: ["same-id", "same-id"],
      rowTypes: ["oa", "bank"],
    });

    const bodiesByPath = Object.fromEntries(fetchSpy.mock.calls.map(([input, init]) => [
      String(input),
      JSON.parse(String(init?.body)),
    ]));
    expect(bodiesByPath["/api/workbench/actions/cancel-link"]).toMatchObject({
      row_id: "same-id",
      row_type: "bank",
    });
    for (const path of [
      "/api/workbench/actions/confirm-personal-advance-repayment",
      "/api/workbench/actions/confirm-cash-pass-through",
      "/api/workbench/actions/confirm-cash-ticket-purchase",
      "/api/workbench/actions/cancel-cash-special",
    ]) {
      expect(bodiesByPath[path]).toMatchObject({
        row_ids: ["same-id", "same-id"],
        row_types: ["oa", "bank"],
      });
    }
  });

  test("coalesces concurrent identical direct combined initial loads", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/workbench?")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              scope_key: "all",
              summary: {
                oa_count: 1,
                bank_count: 1,
                invoice_count: 0,
                paired_count: 1,
                unpaired_count: 1,
                unpaired_exception_count: 0,
                paired_exception_count: 3,
                zone_counts: {
                  paired: { groups: 1, oa: 0, bank: 7, invoice: 0, rows: 7 },
                  unpaired: { groups: 1, oa: 3, bank: 0, invoice: 5, rows: 8 },
                },
              },
              statistics: {
                oa_count: "800",
                bank_transaction_count: 900,
                invoice_total_count: 1300,
                input_invoice_count: 700,
                output_invoice_count: 600,
                completed_oa_count: 780,
                in_progress_oa_count: 20,
                expense_transaction_count: 700,
                income_transaction_count: 200,
                manual_import_invoice_count: 650,
                oa_parse_created_invoice_count: 50,
              },
              paired: {
                month: "all",
                zone: "paired",
                page: 1,
                page_size: 200,
                total: 1,
                has_more: false,
                next_cursor: null,
                row_counts: { oa: 0, bank: 7, invoice: 0, rows: 7 },
                groups: [
                  {
                    group_id: "case:paired",
                    group_type: "relation",
                    match_confidence: "high",
                    reason: "已确认",
                    oa_rows: [],
                    bank_rows: [{ id: "bank-paired", type: "bank", available_actions: ["detail"] }],
                    invoice_rows: [],
                  },
                ],
              },
              unpaired: {
                month: "all",
                zone: "unpaired",
                page: 1,
                page_size: 200,
                total: 1,
                has_more: false,
                next_cursor: null,
                row_counts: { oa: 3, bank: 0, invoice: 5, rows: 8 },
                groups: [
                  {
                    group_id: "row:oa-unpaired",
                    group_type: "unpaired",
                    match_confidence: "medium",
                    reason: "候选",
                    oa_rows: [{ id: "oa-unpaired", type: "oa", available_actions: ["detail", "confirm_link"] }],
                    bank_rows: [],
                    invoice_rows: [],
                  },
                ],
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.includes("zone=paired")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              zone: "paired",
              page: 1,
              page_size: 200,
              total: 1,
              has_more: false,
              row_counts: { oa: 0, bank: 7, invoice: 0, rows: 7 },
              groups: [
                {
                  group_id: "case:paired",
                  group_type: "relation",
                  match_confidence: "high",
                  reason: "已确认",
                  oa_rows: [],
                  bank_rows: [{ id: "bank-paired", type: "bank", available_actions: ["detail"] }],
                  invoice_rows: [],
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.includes("zone=unpaired")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              zone: "unpaired",
              page: 1,
              page_size: 200,
              total: 1,
              has_more: false,
              row_counts: { oa: 3, bank: 0, invoice: 5, rows: 8 },
              groups: [
                {
                  group_id: "row:oa-unpaired",
                  group_type: "unpaired",
                  match_confidence: "medium",
                  reason: "候选",
                  oa_rows: [{ id: "oa-unpaired", type: "oa", available_actions: ["detail", "confirm_link"] }],
                  bank_rows: [],
                  invoice_rows: [],
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`unexpected url ${url}`));
    });

    const zoneQueries = {
      paired: { sort: "bank:desc" },
      unpaired: { search: "供应商" },
    };
    const [result, duplicateResult] = await Promise.all([
      fetchWorkbenchInitialPage("all", undefined, undefined, zoneQueries),
      fetchWorkbenchInitialPage("all", undefined, undefined, zoneQueries),
    ]);

    expect(result.data.summary.pairedCount).toBe(1);
    expect(result.data.summary.pairedExceptionCount).toBe(3);
    expect(duplicateResult).toEqual(result);
    expect(result.data.summary.zoneCounts.paired.bank).toBe(7);
    expect(result.pages.paired.rowCounts.bank).toBe(7);
    expect(result.data.paired.groups[0].id).toBe("case:paired");
    expect(result.data.unpaired.groups[0].id).toBe("row:oa-unpaired");
    expect(result.data.unpaired.groups[0].rows.oa[0]).toMatchObject({
      actionVariant: "detail-only",
      availableActions: ["detail"],
    });
    expect(result.data).not.toHaveProperty("invoiceInventory");
    expect(result.data).not.toHaveProperty("oaStatus");
    expect(result.statistics).toEqual(expect.objectContaining({
      oaCount: 800,
      bankTransactionCount: 900,
      invoiceTotalCount: 1300,
      inputInvoiceCount: 700,
      outputInvoiceCount: 600,
      completedOaCount: 780,
      inProgressOaCount: 20,
      expenseTransactionCount: 700,
      incomeTransactionCount: 200,
      manualImportInvoiceCount: 650,
      oaParseCreatedInvoiceCount: 50,
    }));
    expect(result.pages.unpaired.hasMore).toBe(false);
    expect(result.pages.paired.nextCursor).toBeNull();
    expect(result.pages.unpaired.nextCursor).toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const initialUrl = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(initialUrl.pathname).toBe("/api/workbench");
    expect(JSON.parse(initialUrl.searchParams.get("paired_query") ?? "{}")).toEqual({ sort: "bank:desc" });
    expect(JSON.parse(initialUrl.searchParams.get("unpaired_query") ?? "{}")).toEqual({
      search: "供应商",
    });
    expect(await fetchWorkbenchInitialPage("all", undefined, undefined, zoneQueries)).toEqual(result);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  test("forces a non-coalesced no-store direct reread while an identical pre-commit read is in flight", async () => {
    let resolvePreCommit!: (response: Response) => void;
    const preCommitResponse = new Promise<Response>((resolve) => {
      resolvePreCommit = resolve;
    });
    const initialPayload = (marker: string) => ({
      month: "race",
      scope_key: "race",
      summary: {
        oa_count: 0,
        bank_count: 0,
        invoice_count: 0,
        paired_count: 0,
        unpaired_count: 0,
        unpaired_exception_count: 0,
        paired_exception_count: 0,
      },
      paired: {
        page_size: 50,
        total: 0,
        row_counts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
        has_more: false,
        next_cursor: null,
        groups: [],
      },
      unpaired: {
        page_size: 50,
        total: 0,
        row_counts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
        has_more: false,
        next_cursor: null,
        groups: [],
      },
      marker,
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => preCommitResponse)
      .mockResolvedValueOnce(new Response(JSON.stringify(initialPayload("post-commit")), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));

    const preCommitRead = fetchWorkbenchInitialPage("race");
    const postCommitRead = fetchWorkbenchInitialPage(
      "race",
      undefined,
      undefined,
      {},
      { forceFresh: true },
    );

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls[1][1]).toMatchObject({
      method: "GET",
      cache: "no-store",
    });
    expect(new Headers(fetchSpy.mock.calls[1][1]?.headers).get("Cache-Control")).toBe("no-cache");
    await expect(postCommitRead).resolves.toMatchObject({ data: { month: "race" } });

    resolvePreCommit(new Response(JSON.stringify(initialPayload("pre-commit")), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    await expect(preCommitRead).resolves.toMatchObject({ data: { month: "race" } });
  });

  test("maps formal relation groups from workbench group pages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-05",
          zone: "paired",
          page: 1,
          page_size: 50,
          total: 1,
          has_more: false,
          groups: [
            {
              group_id: "case:formal-paired",
              group_type: "relation",
              formal_member_ids: ["oa-paired", "bank-paired"],
              formal_member_types: ["oa", "bank"],
              match_confidence: "high",
              reason: "active_formal_relation",
              completion: { is_complete: false, missing_row_types: ["oa", "invoice"] },
              amount_check: {
                status: "mismatch",
                direction: "expense",
                oa_total: "100.00",
                bank_total: "100.00",
                invoice_total: "99.00",
                amount_delta: "1.00",
                requires_note: true,
              },
              workbench_anomaly: {
                code: "workbench_anomaly",
                fingerprint: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                review_decision: "accept_paired",
                review_note: "财务已核对",
                reviewed_by_account: "YNSYLP007",
                reviewed_by_name: "杨丽萍",
                reviewed_at: "2026-08-19 01:00:00+08",
                items: [{
                  code: "oa_bank_equal_invoice_less",
                  label: "OA 流水一致，票少",
                  display_label: "OA 流水一致，票少",
                  fingerprint: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                  comparison_unit_id: "oa-paired:item:1",
                  source_oa_ids: ["oa-paired"],
                  source_expense_item_ids: ["oa-paired:item:1"],
                  oa_total: "60.00",
                  invoice_total: "59.00",
                  amount_delta: "1.00",
                  invoice_row_ids: ["invoice-paired"],
                  attachment_file_count: 1,
                  display_scope: "row",
                  display_pane: "invoice",
                  display_row_id: "invoice-paired",
                }],
              },
              oa_rows: [
                {
                  id: "oa-paired",
                  type: "oa",
                  applicant: "张三",
                  apply_time: "2026-08-12 16:11:07+08",
                  amount: "100.00",
                  expense_type: "交通费",
                  expense_items: [
                    {
                      id: "oa-paired:item:0",
                      row_index: "0",
                      project_name: "曲靖项目",
                      amount: "40.00",
                      expense_type: "交通费",
                      fee_content: "差旅费",
                      fee_description: "曲靖出差",
                      attachment_file_count: 0,
                    },
                    {
                      id: "oa-paired:item:1",
                      row_index: 1,
                      project_name: "大理项目",
                      amount: 60,
                      expense_type: "住宿费",
                      fee_content: "住宿费",
                      fee_description: null,
                      attachment_file_count: 1,
                    },
                  ],
                  available_actions: ["detail", "cancel_link"],
                },
              ],
              bank_rows: [
                {
                  id: "bank-paired",
                  type: "bank",
                  trade_time: "2026-08-12 16:11:07+08",
                  debit_amount: "100.00",
                  category_label: "设备采购",
                  category_label_path: ["货款", "设备采购"],
                  category_resolution_status: "manual_confirmed",
                  invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
                  available_actions: ["detail"],
                },
              ],
              invoice_rows: [
                {
                  id: "invoice-paired",
                  type: "invoice",
                  seller_name: "供应商A",
                  total_with_tax: "99.00",
                  derived_from_oa_id: "legacy-oa:item:1",
                  source_oa_id: "oa-paired",
                  source_kinds: [
                    "manual_invoice_import",
                    "oa_attachment_invoice",
                    "oa_expense_item_invoice",
                    "manual_invoice_import",
                  ],
                  source_expense_item_ids: ["oa-paired:item:1"],
                  source_links: [{
                    source_type: "oa_attachment_invoice",
                    derived_from_oa_id: "oa-paired-historical",
                    source_expense_item_id: "oa-paired-historical:item:1:old-fingerprint",
                  }],
                  invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
                  available_actions: ["detail"],
                },
              ],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("2026-05", "paired", null, 50);
    const group = result.groups[0];
    expect(group.groupType).toBe("paired");
    expect(group.rawGroupType).toBe("relation");
    expect(group.reason).toBe("active_formal_relation");
    expect(group.formalMemberIdentities).toEqual([
      { id: "oa-paired", recordType: "oa" },
      { id: "bank-paired", recordType: "bank" },
    ]);
    expect(group.completion).toEqual({
      isComplete: false,
      missingRecordTypes: ["oa", "invoice"],
      blockingReasons: [],
    });
    expect(group.rows.oa.map((row) => row.id)).toEqual(["oa-paired"]);
    expect(group.rows.oa[0]).toMatchObject({
      actionVariant: "detail-only",
      availableActions: ["detail"],
      expenseType: "交通费",
      tableValues: { applicationTime: "2026-08-12 16:11:07" },
    });
    expect(group.rows.oa[0].expenseItems).toEqual([
      {
        id: "oa-paired:item:0",
        rowIndex: "0",
        projectName: "曲靖项目",
        amount: "40",
        expenseType: "交通费",
        feeContent: "差旅费",
        feeDescription: "曲靖出差",
        attachmentFileCount: 0,
      },
      {
        id: "oa-paired:item:1",
        rowIndex: "1",
        projectName: "大理项目",
        amount: "60",
        expenseType: "住宿费",
        feeContent: "住宿费",
        feeDescription: "",
        attachmentFileCount: 1,
      },
    ]);
    expect(group.rows.bank[0]).toMatchObject({
      categoryLabel: "设备采购",
      categoryLabelPath: ["货款", "设备采购"],
      categoryResolutionStatus: "manual_confirmed",
      tableValues: { transactionTime: "2026-08-12 16:11:07" },
    });
    expect(group.rows.invoice[0].sourceOaId).toBe("oa-paired");
    expect(group.rows.invoice[0].sourceKinds).toEqual([
      "manual_invoice_import",
      "oa_attachment_invoice",
      "oa_expense_item_invoice",
    ]);
    expect(group.rows.invoice[0].sourceExpenseItemIds).toEqual(["oa-paired:item:1"]);
    expect(group.rows.invoice[0].displayOnly).toBeUndefined();
    expect(group.workbenchAnomaly).toMatchObject({ reviewDecision: "accept_paired" });
    expect(group.amountCheck).toMatchObject({ oaTotal: "100.00", bankTotal: "100.00", invoiceTotal: "99.00" });
    expect(group.rows.oa[0].relationAmountCheck).toEqual(group.amountCheck);
    expect(group.rows.bank[0].relationAmountCheck).toEqual(group.amountCheck);
    expect(group.rows.invoice[0].relationAmountCheck).toEqual(group.amountCheck);
    expect(group.rows.invoice[0].workbenchAnomalies?.[0]).toMatchObject({
      displayLabel: "OA 流水一致，票少",
      amountDelta: "1.00",
      reviewDecision: "accept_paired",
      reviewNote: "财务已核对",
      reviewedByAccount: "YNSYLP007",
      reviewedByName: "杨丽萍",
      reviewedAt: "2026-08-19 01:00:00+08",
    });
  });

  test("fails the formal-member mapping closed when relation identity arrays disagree", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        month: "all",
        zone: "paired",
        page: 1,
        page_size: 50,
        total: 1,
        has_more: false,
        groups: [{
          group_id: "case:invalid-formal-members",
          group_type: "relation",
          match_confidence: "high",
          reason: "active_formal_relation",
          formal_member_ids: ["oa-1", "bank-1"],
          formal_member_types: ["oa"],
          oa_rows: [{ id: "oa-1", type: "oa" }],
          bank_rows: [{ id: "bank-1", type: "bank" }],
          invoice_rows: [{
            id: "display-invoice",
            type: "invoice",
            workbench_membership_role: "source_owned_display",
          }],
        }],
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    const result = await fetchWorkbenchGroupsPage("all", "paired", null, 50);

    expect(result.groups[0].formalMemberIdentities).toEqual([]);
    expect(result.groups[0].rows.invoice[0].displayOnly).toBeUndefined();
  });

  test("serializes workbench group page SQL query controls", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "unpaired",
          page: 2,
          page_size: 25,
          total: 0,
          has_more: false,
          next_cursor: null,
          selected_exception_code: "oa_bank_equal_invoice_less",
          exception_counts: {
            total: 9,
            amount_total: 7,
            document_only: 2,
            by_code: {
              oa_bank_equal_invoice_more: 1,
              oa_bank_equal_invoice_less: 2,
              oa_invoice_equal_bank_more: 1,
              oa_invoice_equal_bank_less: 1,
              bank_invoice_equal_oa_less: 1,
              bank_invoice_equal_oa_more: 1,
              all_amounts_different: 0,
            },
          },
          groups: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("all", "unpaired", "opaque-page-2", 25, undefined, {
      search: "供应商A",
      status: "unpaired",
      sourceKind: "bank_transaction",
      sort: "bank:desc",
      detailLevel: "summary",
      filtersByPaneAndColumn: {
        bank: {
          amount: ["direction:expense", "account:8106"],
          counterparty: ["云南溯源科技有限公司"],
        },
      },
      timeFilterByPane: {
        bank: { mode: "month", month: "2026-04" },
      },
      exceptionBucket: "unpaired",
      exceptionView: "amount",
      exceptionCode: "oa_bank_equal_invoice_less",
    }, 2);

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("unpaired");
    expect(url.searchParams.has("page")).toBe(false);
    expect(url.searchParams.get("cursor")).toBe("opaque-page-2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("search")).toBe("供应商A");
    expect(url.searchParams.has("search_mode")).toBe(false);
    expect(url.searchParams.has("search_by_pane")).toBe(false);
    expect(url.searchParams.get("status")).toBe("unpaired");
    expect(url.searchParams.get("source_kind")).toBe("bank_transaction");
    expect(url.searchParams.get("sort")).toBe("bank:desc");
    expect(url.searchParams.get("detail_level")).toBe("summary");
    expect(url.searchParams.get("exception_bucket")).toBe("unpaired");
    expect(url.searchParams.get("exception_view")).toBe("amount");
    expect(url.searchParams.get("exception_code")).toBe("oa_bank_equal_invoice_less");
    expect(result.selectedExceptionCode).toBe("oa_bank_equal_invoice_less");
    expect(result.exceptionCounts).toEqual({
      total: 9,
      amountTotal: 7,
      documentOnly: 2,
      byCode: {
        oa_bank_equal_invoice_more: 1,
        oa_bank_equal_invoice_less: 2,
        oa_invoice_equal_bank_more: 1,
        oa_invoice_equal_bank_less: 1,
        bank_invoice_equal_oa_less: 1,
        bank_invoice_equal_oa_more: 1,
        all_amounts_different: 0,
      },
    });
    expect(JSON.parse(url.searchParams.get("column_filters") ?? "{}")).toEqual({
      bank: { amount: ["account:8106", "direction:expense"], counterparty: ["云南溯源科技有限公司"] },
    });
    expect(JSON.parse(url.searchParams.get("time_filters") ?? "{}")).toEqual({
      bank: { mode: "month", month: "2026-04" },
    });
  });

  test("serializes the direct cursor filter facet query and maps missing labels", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        page_size: 100,
        has_more: true,
        next_cursor: "filter-cursor-2",
        options: [
          { value: "applicant:杨丽萍", label: "杨丽萍", missing: false, group: "申请人" },
          { value: "applicant:__workbench_missing__", label: "未填写", missing: true, group: "申请人" },
        ],
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    const result = await fetchWorkbenchFilterOptions("all", "unpaired", {
      pane: "oa",
      facet: "column",
      column: "applicant",
      optionSearch: "杨",
      cursor: "filter-cursor-1",
    }, {
      search: "1320",
      filtersByPaneAndColumn: { oa: { applicant: ["applicant:杨丽萍"], projectName: ["project:大理项目"] } },
      timeFilterByPane: { bank: { mode: "year", year: "2026" } },
    });

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/filter-options");
    expect(url.searchParams.get("pane")).toBe("oa");
    expect(url.searchParams.get("facet")).toBe("column");
    expect(url.searchParams.get("column")).toBe("applicant");
    expect(url.searchParams.get("option_search")).toBe("杨");
    expect(url.searchParams.has("page")).toBe(false);
    expect(url.searchParams.get("cursor")).toBe("filter-cursor-1");
    expect(url.searchParams.get("page_size")).toBe("100");
    expect(JSON.parse(url.searchParams.get("column_filters") ?? "{}")).toEqual({
      oa: { applicant: ["applicant:杨丽萍"], projectName: ["project:大理项目"] },
    });
    expect(result).toMatchObject({
      hasMore: true,
      nextCursor: "filter-cursor-2",
      options: [
        { value: "applicant:杨丽萍", label: "杨丽萍", missing: false, group: "申请人" },
        { value: "applicant:__workbench_missing__", label: "未填写", missing: true, group: "申请人" },
      ],
    });
  });

  test("posts an anomaly review without a client supplied actor", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          affected_scope_keys: ["2026-05"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await reviewWorkbenchAnomaly({
      month: "all",
      zone: "paired",
      groupId: "case:CASE-1",
      detailKey: "case:CASE-1",
      fingerprint: "a".repeat(64),
      decision: "accept_paired",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/workbench/exceptions/review",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          zone: "paired",
          group_id: "case:CASE-1",
          detail_key: "case:CASE-1",
          fingerprint: "a".repeat(64),
          decision: "accept_paired",
        }),
      }),
    );
  });

  test("preserves a canonical selection conflict for mutation callers", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "canonical_selection_conflict",
          message: "所选记录的 canonical 关系已变化，请重新预览。",
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    const error = await confirmWorkbenchLink({
      month: "all",
      rowIds: ["oa-1", "bank-1"],
      rowTypes: ["oa", "bank"],
      idempotencyKey: "canonical-conflict-1",
    }).catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(Error);
    expect(error).toMatchObject({ status: 409, code: "canonical_selection_conflict" });
  });

  test("loads the latest committed row detail without a read-model version", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          row: {
            id: "bank-1",
            source_kind: "bank_transaction",
            source_id: "bank-1",
            amount: "120.00",
            occurred_on: "2026-05-02",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const row = await fetchWorkbenchRowDetail("bank-1", {
      month: "all",
      rowType: "bank",
    });

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/rows/bank-1");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("row_type")).toBe("bank");
    expect(row.id).toBe("bank-1");
  });

  test("builds server page query from column and time filters", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      amount: ["direction:expense", "account:8106"],
    };
    state.timeFilterByPane.bank = { mode: "year", year: "2026" };

    expect(buildWorkbenchServerPageQuery(state)).toEqual({
      filtersByPaneAndColumn: {
        bank: { amount: ["direction:expense", "account:8106"] },
      },
      timeFilterByPane: {
        bank: { mode: "year", year: "2026" },
      },
    });
  });

  test("builds one zone search query", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.searchQuery = "花";

    expect(buildWorkbenchServerPageQuery(state)).toEqual({
      search: "花",
    });
  });

  test("keeps server filtered summary groups without local preview exclusion", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = { counterparty: ["未出现在摘要预览的供应商"] };
    const groups = createContextSearchGroups("bank");

    expect(buildWorkbenchDisplayGroups(groups, state, { serverFiltered: true })).toBe(groups);
  });

  test("validates full collapsed group detail per pane", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          scope_key: "all",
          zone: "paired",
          group_id: "case:etc",
          group: {
            group_id: "case:etc",
            group_type: "relation",
            match_confidence: "high",
            reason: "ETC批次",
            display_mode: "collapsed_summary",
            oa_rows: [{ id: "oa-1", type: "oa" }],
            bank_rows: [{ id: "bank-1", type: "bank" }],
            invoice_rows: [{ id: "etc-summary", type: "invoice", source_kind: "etc_invoice_summary" }],
            row_counts: { oa: 1, bank: 1, invoice: 35, rows: 37 },
            display_row_counts: { oa: 1, bank: 1, invoice: 1, rows: 3 },
            collapsed_rows: {
              invoice: Array.from({ length: 34 }, (_item, index) => ({
                id: `etc-invoice-${index + 1}`,
                type: "invoice",
                source_kind: "etc_invoice",
              })),
            },
            collapsed_row_counts: { invoice: 34 },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const group = await fetchWorkbenchGroupDetail("all", "paired", "case:etc", "CASE-ETC-1");

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups/detail");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("paired");
    expect(url.searchParams.get("group_id")).toBe("case:etc");
    expect(url.searchParams.get("detail_key")).toBe("CASE-ETC-1");
    expect(group.id).toBe("case:etc");
    expect(group.rows.oa).toHaveLength(1);
    expect(group.rows.bank).toHaveLength(1);
    expect(group.collapsedRows?.invoice).toHaveLength(34);
  });

  test("rejects sparse workbench group detail responses before the shared group mapper", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          group: {
            group_id: "case:no-oa",
            group_type: "relation",
            match_confidence: "high",
            reason: "免OA批次",
            display_mode: "collapsed_summary",
            bank_rows: [{ id: "summary", type: "bank" }],
            row_counts: { bank: 1 },
            collapsed_rows: { bank: [{ id: "bank-1", type: "bank" }] },
            collapsed_row_counts: { bank: 1 },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(
      fetchWorkbenchGroupDetail("all", "paired", "case:no-oa", "CASE-NO-OA"),
    ).rejects.toThrow("invalid_workbench_group_detail_contract");
  });

  test("rejects incomplete collapsed workbench group detail responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          group: {
            group_id: "case:no-oa",
            group_type: "relation",
            match_confidence: "high",
            reason: "免OA批次",
            display_mode: "collapsed_summary",
            oa_rows: [],
            bank_rows: [{ id: "summary", type: "bank" }],
            invoice_rows: [],
            row_counts: { bank: 4 },
            collapsed_rows: { bank: [{ id: "bank-1", type: "bank" }] },
            collapsed_row_counts: { bank: 4 },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(
      fetchWorkbenchGroupDetail("all", "paired", "case:no-oa", "CASE-NO-OA"),
    ).rejects.toThrow("incomplete_workbench_group_detail");
  });

  test("keeps collapsed no-OA bank groups searchable when the hit is inside collapsed no-OA bank detail rows", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.searchQuery = "企业网银年费";

    const displayGroups = buildWorkbenchDisplayGroups(
      [
        {
          id: "nooa-group",
          groupType: "paired",
          rawGroupType: "relation",
          matchConfidence: "high",
          reason: "免OA批次",
          relationMode: "no_oa_bank_batch",
          displayMode: "collapsed_summary",
          defaultCollapsed: true,
          rows: {
            oa: [],
            bank: [createWorkbenchRow("bank", "nooa-summary", "免OA手续费批次")],
            invoice: [],
          },
          collapsedRows: {
            bank: [
              {
                ...createWorkbenchRow("bank", "nooa-detail", "网银服务费"),
                tableValues: {
                  ...createWorkbenchRow("bank", "nooa-detail", "网银服务费").tableValues,
                  note: "摘要：企业网银年费",
                  amount: "20.00",
                },
              },
            ],
          },
        },
      ],
      state,
    );

    expect(displayGroups.map((group) => group.id)).toEqual(["nooa-group"]);
    expect(displayGroups).toHaveLength(1);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["nooa-summary"]);
    expect(displayGroups[0].collapsedRows?.bank?.map((row) => row.id)).toEqual(["nooa-detail"]);
  });

  test("keeps collapsed no-OA detail filter hits as one summary row", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      paymentAccount: ["民生银行 0933"],
    };

    const displayGroups = buildWorkbenchDisplayGroups(
      [
        {
          id: "nooa-salary-group",
          groupType: "paired",
          rawGroupType: "relation",
          matchConfidence: "high",
          reason: "免OA工资批次",
          relationMode: "no_oa_bank_batch",
          displayMode: "collapsed_summary",
          defaultCollapsed: true,
          rows: {
            oa: [],
            bank: [createWorkbenchRow("bank", "nooa-salary-summary", "免OA工资批次")],
            invoice: [],
          },
          collapsedRows: {
            bank: [
              {
                ...createWorkbenchRow("bank", "nooa-salary-detail", "员工工资"),
                tableValues: {
                  ...createWorkbenchRow("bank", "nooa-salary-detail", "员工工资").tableValues,
                  paymentAccount: "民生银行 0933",
                  note: "工资发放",
                },
              },
            ],
          },
        },
      ],
      state,
    );

    expect(displayGroups.map((group) => group.id)).toEqual(["nooa-salary-group"]);
    expect(displayGroups[0].rows.bank.map((row) => row.id)).toEqual(["nooa-salary-summary"]);
  });

  test("does not locally discard server-owned search results or their relation context", () => {
    const groups = createContextSearchGroups("oa");
    const state = createEmptyWorkbenchZoneDisplayState();
    state.searchQuery = "张丽芬";

    expect(buildWorkbenchDisplayGroups(groups, state)).toBe(groups);
  });

  test("keeps the zone search query as one explicit state value", () => {
    const pairedState = createEmptyWorkbenchZoneDisplayState();
    const unpairedState = createEmptyWorkbenchZoneDisplayState();
    pairedState.searchQuery = "26532000";

    expect(pairedState.searchQuery).toBe("26532000");
    expect(unpairedState.searchQuery).toBe("");
  });

  test("keeps active pane row filters independent from the server-owned search query", () => {
    const groups = createContextSearchGroups("invoice").map((group) => {
      if (group.id !== "invoice-anchor" && group.id !== "multi-pane-hit") {
        return group;
      }
      return {
        ...group,
        rows: {
          ...group.rows,
          bank: group.rows.bank.map((row) => ({
            ...row,
            tableValues: {
              ...row.tableValues,
              direction: "支出",
            },
          })),
        },
      };
    });
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      direction: ["支出"],
    };
    state.searchQuery = "张三";

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual([
      "invoice-anchor",
      "multi-pane-hit",
    ]);
    expect(displayGroups.find((group) => group.id === "invoice-anchor")?.rows.bank.map((row) => row.id)).toEqual([
      "invoice-anchor-bank",
    ]);
    expect(displayGroups.find((group) => group.id === "invoice-anchor")?.rows.invoice.map((row) => row.counterparty)).toEqual([
      "张三",
    ]);
  });

  test("returns the original groups when no pane has search, filter, time filter, or sort criteria", () => {
    const groups = createContextSearchGroups("bank");
    const state = createEmptyWorkbenchZoneDisplayState();

    expect(buildWorkbenchDisplayGroups(groups, state)).toBe(groups);
  });
});

describe("workbench groups summary contract", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("uses server row counts when summary pages omit collapsed detail rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "paired",
          page: 1,
          page_size: 50,
          total: 1,
          has_more: false,
          groups: [
            {
              group_id: "case-summary",
              group_type: "unpaired",
              match_confidence: "medium",
              reason: "summary preview",
              row_counts: { oa: 5, bank: 8, invoice: 2, rows: 15 },
              display_row_counts: { oa: 5, bank: 0, invoice: 2, rows: 7 },
              collapsed_row_counts: { bank: 8 },
              oa_rows: Array.from({ length: 5 }, (_item, index) => ({
                id: `oa-preview-${index + 1}`,
                type: "oa",
                available_actions: ["detail"],
              })),
              bank_rows: [],
              invoice_rows: [{ id: "invoice-preview", type: "invoice", available_actions: ["detail"] }],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("all", "paired", null, 50, undefined, { detailLevel: "summary" });
    const group = result.groups[0];

    expect(group.rowCounts).toEqual({ oa: 5, bank: 8, invoice: 2 });
    expect(group.displayRowCounts).toEqual({ oa: 5, bank: 0, invoice: 2 });
    expect(group.collapsedRowCounts).toEqual({ bank: 8 });
    expect(group.rows.oa).toHaveLength(5);
    expect(countWorkbenchGroupRows(group)).toBe(15);
  });

  test("prefers authoritative row counts over collapsed-only fallback counts", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "paired",
          page: 1,
          page_size: 50,
          total: 1,
          has_more: false,
          groups: [
            {
              group_id: "case-mixed",
              group_type: "unpaired",
              match_confidence: "medium",
              row_counts: { oa: 0, bank: 10, invoice: 0, rows: 10 },
              display_row_counts: { oa: 0, bank: 2, invoice: 0, rows: 2 },
              collapsed_row_counts: { bank: 8 },
              oa_rows: [],
              bank_rows: [{ id: "visible-bank-1", type: "bank" }, { id: "visible-bank-2", type: "bank" }],
              invoice_rows: [],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("all", "paired", null, 50, undefined, { detailLevel: "summary" });

    expect(countWorkbenchGroupRows(result.groups[0])).toBe(10);
  });
});

describe("workbench OA manual import affected scopes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const targetEnvelope = {
    affected_scope_keys: ["all", "2025-12", "active:2025-12", "all:2025-12"],
  };

  test("maps attachment refresh affected scopes", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            event_id: "refresh-event-1",
            status: "queued",
            row_ids: ["oa-exp-1981"],
            ...targetEnvelope,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            event_id: "refresh-event-1",
            status: "done",
            row_ids: ["oa-exp-1981"],
            result: {
              rows: [
                {
                  row_id: "oa-exp-1981",
                  attachment_file_count: 3,
                  importable_invoice_count: 2,
                  unrecognized_attachment_count: 1,
                },
              ],
              errors: [],
              promotion_summary: { affected_invoice_count: 1 },
            },
            ...targetEnvelope,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    const request = await refreshManualOaImportAttachments(["oa-exp-1981"]);
    const result = await getManualOaImportAttachmentRefreshStatus(request.eventId, request.rowIds);

    expect(request).toMatchObject({
      eventId: "refresh-event-1",
      status: "queued",
      rowIds: ["oa-exp-1981"],
    });
    expect(result.result?.rows[0]).toMatchObject({
      rowId: "oa-exp-1981",
      attachmentFileCount: 3,
      importableInvoiceCount: 2,
      unrecognizedAttachmentCount: 1,
    });
    expect(result.affectedScopeKeys).toEqual(["2025-12", "active:2025-12", "all:2025-12"]);
  });

  test("rejects malformed or mismatched attachment refresh terminal results", async () => {
    const basePayload = {
      event_id: "refresh-event-1",
      status: "done",
      row_ids: ["oa-exp-1981"],
      result: {
        rows: [
          {
            row_id: "oa-exp-1981",
            importable_invoice_count: 2,
            unrecognized_attachment_count: 0,
          },
        ],
        errors: [],
        promotion_summary: {},
      },
      ...targetEnvelope,
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(basePayload)))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...basePayload,
        event_id: "other-event",
        result: {
          ...basePayload.result,
          rows: [{ ...basePayload.result.rows[0], attachment_file_count: 2 }],
        },
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ...basePayload,
        result: {
          ...basePayload.result,
          rows: [{
            row_id: "other-row",
            attachment_file_count: 2,
            importable_invoice_count: 2,
            unrecognized_attachment_count: 0,
          }],
        },
      })));

    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("attachment_file_count");
    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("event_id 与请求不一致");
    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("rows 与请求不一致");
  });

  test("rejects duplicate refresh result rows and each incomplete row-error field", async () => {
    const validRow = {
      row_id: "oa-exp-1981",
      attachment_file_count: 2,
      importable_invoice_count: 2,
      unrecognized_attachment_count: 0,
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        event_id: "refresh-event-1",
        status: "done",
        row_ids: ["oa-exp-1981", "oa-exp-2002"],
        result: {
          rows: [validRow, validRow],
          errors: [],
          promotion_summary: {},
        },
        ...targetEnvelope,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        event_id: "refresh-event-1",
        status: "done",
        row_ids: ["oa-exp-1981"],
        result: {
          rows: [validRow],
          errors: [{ row_id: "", code: "attachment_parse_failed", message: "OCR 失败" }],
          promotion_summary: {},
        },
        ...targetEnvelope,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        event_id: "refresh-event-1",
        status: "done",
        row_ids: ["oa-exp-1981"],
        result: {
          rows: [validRow],
          errors: [{ row_id: "oa-exp-1981", code: "", message: "OCR 失败" }],
          promotion_summary: {},
        },
        ...targetEnvelope,
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        event_id: "refresh-event-1",
        status: "done",
        row_ids: ["oa-exp-1981"],
        result: {
          rows: [validRow],
          errors: [{ row_id: "oa-exp-1981", code: "attachment_parse_failed", message: "" }],
          promotion_summary: {},
        },
        ...targetEnvelope,
      })));

    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981", "oa-exp-2002"],
    )).rejects.toThrow("rows 与请求不一致");
    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("error.row_id");
    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("error.code");
    await expect(getManualOaImportAttachmentRefreshStatus(
      "refresh-event-1",
      ["oa-exp-1981"],
    )).rejects.toThrow("error.message");
  });

  test("maps import and delete affected scopes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            imported: ["oa-exp-1981"],
            already_imported: [],
            failed: [],
            rows: [{ row_id: "oa-exp-1981", status: "completed", can_import: false }],
            ...targetEnvelope,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            removed: true,
            row_id: "oa-exp-1981",
            ...targetEnvelope,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    const importResult = await importManualOaRows(["oa-exp-1981"]);
    const deleteResult = await removeManualOaImport("oa-exp-1981");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/workbench/settings/oa/manual-imports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ row_ids: ["oa-exp-1981"], actor_id: "settings_manual_import" }),
      }),
    );
    expect(importResult.imported).toEqual(["oa-exp-1981"]);
    expect(importResult.affectedScopeKeys).toEqual(["2025-12", "active:2025-12", "all:2025-12"]);
    expect(deleteResult).toMatchObject({
      removed: true,
      rowId: "oa-exp-1981",
      affectedScopeKeys: ["2025-12", "active:2025-12", "all:2025-12"],
    });
  });
});
