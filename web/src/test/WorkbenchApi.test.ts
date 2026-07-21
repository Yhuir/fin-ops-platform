import { afterEach, describe, expect, test, vi } from "vitest";

import {
  applyWorkbenchException,
  confirmWorkbenchLink,
  fetchWorkbenchGroupDetail,
  fetchWorkbenchGroupsPage,
  fetchWorkbenchInitialPage,
  fetchWorkbenchRowDetail,
  importManualOaRows,
  previewWorkbenchException,
  previewWorkbenchWithdrawLink,
  refreshManualOaImportAttachments,
  removeManualOaImport,
  WORKBENCH_GROUP_PAGE_SIZE,
} from "../features/workbench/api";
import {
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  countWorkbenchGroupRows,
  createEmptyWorkbenchZoneDisplayState,
  workbenchRowMatchesUnifiedSearch,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchRelationGroup, WorkbenchRecord, WorkbenchRecordType } from "../features/workbench/types";

const workbenchPanes: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

test("keeps the combined initial and subsequent group pages at a 50-group first screen", () => {
  expect(WORKBENCH_GROUP_PAGE_SIZE).toBe(50);
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
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
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
          after: { groups: [] },
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
      expectedReadModelVersion: "generation-set-1",
    });

    expect(preview.operation).toBe("withdraw_link");
    expect(preview.operationType).toBe("withdraw_relation");
    expect(preview.previewId).toBe("withdraw_relation:abc123");
    expect(preview.submitExpectedVersions).toEqual({ "relation:relation-1": 3 });
  });

  test("preserves backend requestId in workbench API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "internal_server_error",
          message: "接口处理失败，请联系管理员查看后端日志。",
          requestId: "req-500-audit",
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchWorkbenchGroupsPage("all", "unpaired", 1, 50)).rejects.toThrow(
      "接口处理失败，请联系管理员查看后端日志。 · requestId req-500-audit",
    );
  });

  test("maps two-pane confirm operation projection as a formal relation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          action: "confirm_link",
          month: "2026-05",
          affected_row_ids: ["oa-partial", "bank-partial"],
          affected_months: ["2026-05"],
          affected_scope_keys: ["2026-05"],
          freshness_targets: [{ read_model_key: "workbench_relation", scope_key: "2026-05" }],
          operation_barrier_targets: [{ read_model_key: "workbench_relation", scope_key: "2026-05" }],
          operation_projection: {
            after: {
              paired_groups: [
                {
                  group_id: "case:CASE-PARTIAL",
                  group_type: "relation",
                  relation_mode: "manual_confirmed",
                  match_confidence: "medium",
                  reason: "active_formal_relation",
                  oa_rows: [
                    {
                      id: "oa-partial",
                      type: "oa",
                      applicant: "刘际涛",
                      amount: "400.00",
                      counterparty_name: "云南溯源科技",
                      oa_bank_relation: { code: "manual_confirmed", label: "已关联流水", tone: "success" },
                    },
                  ],
                  bank_rows: [
                    {
                      id: "bank-partial",
                      type: "bank",
                      trade_time: "2026-05-02 10:30",
                      debit_amount: "400.00",
                      counterparty_name: "云南溯源科技",
                      invoice_relation: { code: "manual_confirmed", label: "已关联OA", tone: "success" },
                    },
                  ],
                  invoice_rows: [],
                },
              ],
              unpaired_groups: [],
            },
          },
          message: "已确认 2 条记录关联。",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await confirmWorkbenchLink({
      month: "2026-05",
      rowIds: ["oa-partial", "bank-partial"],
      expectedReadModelVersion: "generation-set-1",
      caseId: "CASE-PARTIAL",
    });

    expect(result.operationProjection?.after.pairedGroups).toHaveLength(1);
    expect(result.operationProjection?.after.pairedGroups[0]).toMatchObject({
      id: "case:CASE-PARTIAL",
      groupType: "paired",
      rawGroupType: "relation",
      relationMode: "manual_confirmed",
    });
    expect(result.operationProjection?.after.pairedGroups[0].rows.oa.map((row) => row.id)).toEqual(["oa-partial"]);
    expect(result.operationProjection?.after.pairedGroups[0].rows.bank.map((row) => row.id)).toEqual(["bank-partial"]);
    expect(result.operationProjection?.after.pairedGroups[0].rows.invoice).toEqual([]);
    expect(result.operationProjection?.after.unpairedGroups).toEqual([]);
    expect(result.operationBarrierTargets).toEqual([{ readModelKey: "workbench_relation", scopeKey: "2026-05" }]);
  });

  test("loads initial workbench page with one versioned request", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/workbench?")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              summary: {
                oa_count: 1,
                bank_count: 1,
                invoice_count: 0,
                paired_count: 1,
                unpaired_count: 1,
                exception_count: 0,
                zone_counts: {
                  paired: { groups: 1, oa: 0, bank: 7, invoice: 0, rows: 7 },
                  unpaired: { groups: 1, oa: 3, bank: 0, invoice: 5, rows: 8 },
                },
              },
              oa_status: { code: "ready", message: "OA 已同步" },
              invoice_inventory: {
                system_total: 9,
                manual_import_total: 7,
                workbench_visible_total: 4,
                hidden_submitted_etc_total: 2,
                extra_etc_total: 1,
                etc_summary_batch_count: 3,
                oa_attachment_total: 5,
              },
              read_model_status: "fresh",
              read_model_version: "generation-set-1",
              generated_at: "2026-05-22T09:30:00+00:00",
              paired: {
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
              },
              unpaired: {
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
                    oa_rows: [{ id: "oa-unpaired", type: "oa", available_actions: ["detail"] }],
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
              read_model_status: "fresh",
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
                  oa_rows: [{ id: "oa-unpaired", type: "oa", available_actions: ["detail"] }],
                  bank_rows: [],
                  invoice_rows: [],
                },
              ],
              read_model_status: "fresh",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`unexpected url ${url}`));
    });

    const result = await fetchWorkbenchInitialPage("all", undefined, undefined, {
      paired: { sort: "bank:desc" },
      unpaired: { search: "供应商" },
    });

    expect(result.data.summary.pairedCount).toBe(1);
    expect(result.data.summary.zoneCounts.paired.bank).toBe(7);
    expect(result.pages.paired.rowCounts.bank).toBe(7);
    expect(result.data.paired.groups[0].id).toBe("case:paired");
    expect(result.data.unpaired.groups[0].id).toBe("row:oa-unpaired");
    expect(result.data.invoiceInventory.systemTotal).toBe(9);
    expect(result.data.invoiceInventory.oaAttachmentTotal).toBe(5);
    expect(result.data.oaStatus.message).toBe("OA 已同步");
    expect(result.pages.unpaired.hasMore).toBe(false);
    expect(result.pages.paired.readModelVersion).toBe("generation-set-1");
    expect(result.pages.unpaired.readModelVersion).toBe("generation-set-1");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const initialUrl = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(initialUrl.pathname).toBe("/api/workbench");
    expect(JSON.parse(initialUrl.searchParams.get("paired_query") ?? "{}")).toEqual({ sort: "bank:desc" });
    expect(JSON.parse(initialUrl.searchParams.get("unpaired_query") ?? "{}")).toEqual({
      search: "供应商",
    });
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
              match_confidence: "high",
              reason: "active_formal_relation",
              completion: { is_complete: true, missing_row_types: [] },
              oa_rows: [
                {
                  id: "oa-paired",
                  type: "oa",
                  applicant: "张三",
                  amount: "100.00",
                  available_actions: ["detail"],
                },
              ],
              bank_rows: [
                {
                  id: "bank-paired",
                  type: "bank",
                  debit_amount: "100.00",
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
                  invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
                  available_actions: ["detail"],
                },
              ],
            },
          ],
          read_model_status: "fresh",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("2026-05", "paired", 1, 50);
    const group = result.groups[0];
    expect(group.groupType).toBe("paired");
    expect(group.rawGroupType).toBe("relation");
    expect(group.reason).toBe("active_formal_relation");
    expect(group.completion).toEqual({ isComplete: true, missingRecordTypes: [] });
    expect(group.rows.oa.map((row) => row.id)).toEqual(["oa-paired"]);
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
          groups: [],
          read_model_status: "fresh",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await fetchWorkbenchGroupsPage("all", "unpaired", 2, 25, undefined, {
      search: "供应商A",
      status: "unpaired",
      sourceKind: "bank_transaction",
      sort: "bank:desc",
      detailLevel: "summary",
      filtersByPaneAndColumn: {
        bank: {
          amount: ["支出", "建行 8106"],
          counterparty: ["云南溯源科技有限公司"],
        },
      },
      timeFilterByPane: {
        bank: { mode: "month", month: "2026-04" },
      },
    }, "generation-set-1");

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("unpaired");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("search")).toBe("供应商A");
    expect(url.searchParams.has("search_mode")).toBe(false);
    expect(url.searchParams.has("search_by_pane")).toBe(false);
    expect(url.searchParams.get("status")).toBe("unpaired");
    expect(url.searchParams.get("source_kind")).toBe("bank_transaction");
    expect(url.searchParams.get("sort")).toBe("bank:desc");
    expect(url.searchParams.get("detail_level")).toBe("summary");
    expect(url.searchParams.get("expected_read_model_version")).toBe("generation-set-1");
    expect(JSON.parse(url.searchParams.get("column_filters") ?? "{}")).toEqual({
      bank: { amount: ["建行 8106", "支出"], counterparty: ["云南溯源科技有限公司"] },
    });
    expect(JSON.parse(url.searchParams.get("time_filters") ?? "{}")).toEqual({
      bank: { mode: "month", month: "2026-04" },
    });
  });

  test("preserves the 409 version conflict contract for callers", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "read_model_version_conflict",
          message: "关联台数据版本已更新，请刷新后重试。",
          read_model_version: "generation-v2",
        }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      ),
    );

    const error = await fetchWorkbenchGroupsPage(
      "all",
      "paired",
      2,
      50,
      undefined,
      {},
      "generation-v1",
    ).catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(Error);
    expect(error).toMatchObject({ status: 409, code: "read_model_version_conflict" });
  });

  test("sends the active generation when loading row detail", async () => {
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
      expectedReadModelVersion: "generation-v1",
    });

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/rows/bank-1");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("expected_read_model_version")).toBe("generation-v1");
    expect(row.id).toBe("bank-1");
  });

  test("builds server page query from column and time filters", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      amount: ["支出", "建行 8106"],
    };
    state.timeFilterByPane.bank = { mode: "year", year: "2026" };

    expect(buildWorkbenchServerPageQuery(state)).toEqual({
      filtersByPaneAndColumn: {
        bank: { amount: ["支出", "建行 8106"] },
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

  test("fetches full workbench group detail for collapsed summary expansion", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          scope_key: "all",
          zone: "paired",
          group_id: "case:no-oa",
          read_model_status: "fresh",
          group: {
            group_id: "case:no-oa",
            group_type: "relation",
            match_confidence: "high",
            reason: "免OA批次",
            relation_mode: "no_oa_bank_batch",
            display_mode: "collapsed_summary",
            oa_rows: [],
            bank_rows: [{ id: "summary", type: "bank", source_kind: "no_oa_bank_batch_summary" }],
            invoice_rows: [],
            row_counts: { bank: 4, rows: 4 },
            display_row_counts: { bank: 1, rows: 1 },
            collapsed_rows: {
              bank: [
                { id: "bank-1", type: "bank", source_kind: "bank_transaction" },
                { id: "bank-2", type: "bank", source_kind: "bank_transaction" },
                { id: "bank-3", type: "bank", source_kind: "bank_transaction" },
                { id: "bank-4", type: "bank", source_kind: "bank_transaction" },
              ],
            },
            collapsed_row_counts: { bank: 4 },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const group = await fetchWorkbenchGroupDetail("all", "paired", "case:no-oa", "generation-set-1");

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups/detail");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("paired");
    expect(url.searchParams.get("group_id")).toBe("case:no-oa");
    expect(url.searchParams.get("expected_read_model_version")).toBe("generation-set-1");
    expect(group.id).toBe("case:no-oa");
    expect(group.rowCounts?.bank).toBe(4);
    expect(group.displayRowCounts?.bank).toBe(1);
    expect(group.collapsedRows?.bank).toHaveLength(4);
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
      fetchWorkbenchGroupDetail("all", "paired", "case:no-oa", "generation-set-1"),
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
      fetchWorkbenchGroupDetail("all", "paired", "case:no-oa", "generation-set-1"),
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

  test.each(workbenchPanes)(
    "keeps full relation context for every group whose %s fixture has a zone-wide hit",
    (activePaneId) => {
      const groups = createContextSearchGroups(activePaneId);
      const state = createEmptyWorkbenchZoneDisplayState();
      state.searchQuery = "张三";

      const displayGroups = buildWorkbenchDisplayGroups(groups, state);
      const displayIds = displayGroups.map((group) => group.id);
      const supplementPanes = workbenchPanes.filter((paneId) => paneId !== activePaneId);

      expect(displayIds).toEqual([
        `${activePaneId}-anchor`,
        ...supplementPanes.map((paneId) => `${paneId}-supplement`),
        "multi-pane-hit",
      ]);
      expect(displayIds.filter((id) => id === "multi-pane-hit")).toHaveLength(1);

      const anchorGroup = displayGroups.find((group) => group.id === `${activePaneId}-anchor`);
      expect(anchorGroup?.rows[activePaneId].map((row) => row.counterparty)).toEqual(["张三"]);
      expect(anchorGroup?.rows[supplementPanes[0]].map((row) => row.counterparty)).toEqual([
        supplementPanes[0] === "bank" ? "上下文银行" : supplementPanes[0] === "oa" ? "上下文OA" : "上下文发票",
      ]);
      expect(anchorGroup?.rows[supplementPanes[1]].map((row) => row.counterparty)).toEqual([
        supplementPanes[1] === "bank" ? "上下文银行" : supplementPanes[1] === "oa" ? "上下文OA" : "上下文发票",
      ]);
    },
  );

  test("keeps the zone search query as one explicit state value", () => {
    const pairedState = createEmptyWorkbenchZoneDisplayState();
    const unpairedState = createEmptyWorkbenchZoneDisplayState();
    pairedState.searchQuery = "26532000";

    expect(pairedState.searchQuery).toBe("26532000");
    expect(unpairedState.searchQuery).toBe("");
  });

  test("intersects another pane search query with active pane row filters", () => {
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

  test("uses server row counts when summary pages only include preview rows", async () => {
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
              collapsed_rows: {
                bank: [{ id: "bank-preview", type: "bank", available_actions: ["detail"] }],
              },
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("all", "paired", 1, 50, undefined, { detailLevel: "summary" });
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
              collapsed_rows: {
                bank: [{ id: "collapsed-bank-1", type: "bank" }],
              },
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await fetchWorkbenchGroupsPage("all", "paired", 1, 50, undefined, { detailLevel: "summary" });

    expect(countWorkbenchGroupRows(result.groups[0])).toBe(10);
  });
});

describe("workbench exception api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("previewWorkbenchException posts selected rows and maps backend-driven preview", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          rule_version: "exception_rules_v1",
          scenario: {
            business_line: "expense",
            scenario_code: "expense_oa_bank_missing_invoice",
            scenario_label: "OA和支出流水一致，缺进项发票",
          },
          amount_summary: {
            oa_total: "100000.00",
            bank_expense_total: "100000.00",
            bank_income_total: "0.00",
            input_invoice_total: "0.00",
            output_invoice_total: "0.00",
            expense_relation: "oa_equals_bank_missing_invoice",
            income_relation: "not_applicable",
          },
          automatic_actions: [
            {
              action_code: "auto_close_when_invoice_arrives",
              label: "补票后自动闭环",
              result_status: "closed",
              required_fields: [],
            },
          ],
          available_actions: [
            {
              action_code: "wait_input_invoice",
              label: "追进项发票",
              result_status: "open",
              required_fields: ["note"],
            },
          ],
          warnings: [
            {
              code: "candidate_invoice_exists",
              severity: "warning",
              message: "已存在补票候选。",
            },
          ],
          workflow_projection: {
            next_status: "open",
          },
          candidate_evidence: [
            {
              id: "candidate-1",
              label: "命中候选分组",
              detail: "OA 与流水来自同一关系组。",
            },
          ],
          can_apply: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const preview = await previewWorkbenchException({
      month: "all",
      rowIds: ["oa-1", "bank-1"],
      expectedReadModelVersion: "generation-set-1",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-1", "bank-1"],
          expected_read_model_version: "generation-set-1",
        }),
      }),
    );
    expect(preview).toEqual({
      ruleVersion: "exception_rules_v1",
      scenario: {
        businessLine: "expense",
        scenarioCode: "expense_oa_bank_missing_invoice",
        scenarioLabel: "OA和支出流水一致，缺进项发票",
      },
      amountSummary: {
        oaTotal: "100000.00",
        bankExpenseTotal: "100000.00",
        bankIncomeTotal: "0.00",
        inputInvoiceTotal: "0.00",
        outputInvoiceTotal: "0.00",
        relation: "oa_equals_bank_missing_invoice",
      },
      automaticActions: [
        {
          actionCode: "auto_close_when_invoice_arrives",
          label: "补票后自动闭环",
          resultStatus: "closed",
          requiredFields: [],
        },
      ],
      availableActions: [
        {
          actionCode: "wait_input_invoice",
          label: "追进项发票",
          resultStatus: "open",
          requiredFields: ["note"],
        },
      ],
      warnings: [
        {
          code: "candidate_invoice_exists",
          severity: "warning",
          message: "已存在补票候选。",
        },
      ],
      workflowProjection: {
        nextStatus: "open",
      },
      candidateEvidence: [
        {
          id: "candidate-1",
          label: "命中候选分组",
          detail: "OA 与流水来自同一关系组。",
        },
      ],
      canApply: true,
    });
  });

  test("applyWorkbenchException posts selected action payload and maps refresh semantics", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          case: { id: "EXC-1" },
          pair_relation: { id: "REL-1" },
          updated_rows: [{ id: "bank-1" }],
          affected_row_ids: ["bank-1"],
          affected_scope_keys: ["2026-05"],
          freshness_targets: [
            {
              read_model_key: "workbench_relation",
              scope_key: "2026-05",
            },
          ],
          operation_barrier_targets: [
            {
              read_model_key: "workbench_relation",
              scope_key: "2026-05",
            },
          ],
          workbench_refresh_required: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await applyWorkbenchException({
      month: "all",
      rowIds: ["bank-1"],
      expectedReadModelVersion: "generation-set-1",
      scenarioCode: "expense_bank_invoice_missing_oa",
      actionCode: "manual_oa_exempt",
      payload: {
        note: "业务确认无需 OA",
        reason_code: "manual_business_exemption",
        due_date: "2026-05-31",
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/apply",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["bank-1"],
          expected_read_model_version: "generation-set-1",
          scenario_code: "expense_bank_invoice_missing_oa",
          action_code: "manual_oa_exempt",
          payload: {
            note: "业务确认无需 OA",
            reason_code: "manual_business_exemption",
            due_date: "2026-05-31",
          },
        }),
      }),
    );
    expect(result).toEqual({
      success: true,
      case: { id: "EXC-1" },
      pairRelation: { id: "REL-1" },
      updatedRows: [{ id: "bank-1" }],
      affectedRowIds: ["bank-1"],
      affectedScopeKeys: ["2026-05"],
      freshnessTargets: [
        {
          readModelKey: "workbench_relation",
          scopeKey: "2026-05",
        },
      ],
      operationBarrierTargets: [
        {
          readModelKey: "workbench_relation",
          scopeKey: "2026-05",
        },
      ],
      workbenchRefreshRequired: true,
    });
  });
});

describe("workbench OA manual import API targets", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const targetEnvelope = {
    affected_scope_keys: ["all", "2025-12", "active:2025-12", "all:2025-12"],
    read_model_scope_keys: ["all", "2025-12", "active:2025-12", "all:2025-12"],
    freshness_targets: [
      { read_model_key: "workbench", scope_key: "all" },
      { read_model_key: "workbench", scope_key: "2025-12" },
      { read_model_key: "workbench_relation", scope_key: "2025-12" },
      { read_model_key: "cost_statistics", scope_key: "active:2025-12" },
      { read_model_key: "cost_statistics", scope_key: "all:2025-12" },
    ],
    operation_barrier_targets: [
      { read_model_key: "workbench", scope_key: "all" },
      { read_model_key: "workbench", scope_key: "2025-12" },
      { read_model_key: "workbench_relation", scope_key: "2025-12" },
      { read_model_key: "cost_statistics", scope_key: "active:2025-12" },
      { read_model_key: "cost_statistics", scope_key: "all:2025-12" },
    ],
  };

  test("maps attachment refresh target envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          rows: [
            {
              row_id: "oa-exp-1981",
              attachment_file_count: 3,
              importable_invoice_count: 2,
              unrecognized_attachment_count: 1,
            },
          ],
          errors: [],
          ...targetEnvelope,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await refreshManualOaImportAttachments(["oa-exp-1981"]);

    expect(result.rows[0]).toMatchObject({
      rowId: "oa-exp-1981",
      attachmentFileCount: 3,
      importableInvoiceCount: 2,
      unrecognizedAttachmentCount: 1,
    });
    expect(result.affectedScopeKeys).toEqual(["2025-12", "active:2025-12", "all:2025-12"]);
    expect(result.operationBarrierTargets).toEqual([
      { readModelKey: "workbench", scopeKey: "2025-12" },
      { readModelKey: "workbench_relation", scopeKey: "2025-12" },
      { readModelKey: "cost_statistics", scopeKey: "active:2025-12" },
      { readModelKey: "cost_statistics", scopeKey: "all:2025-12" },
    ]);
  });

  test("maps import and delete target envelopes", async () => {
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
    expect(importResult.operationBarrierTargets).toContainEqual({
      readModelKey: "workbench_relation",
      scopeKey: "2025-12",
    });
    expect(deleteResult).toMatchObject({
      removed: true,
      rowId: "oa-exp-1981",
      readModelScopeKeys: ["2025-12", "active:2025-12", "all:2025-12"],
    });
    expect(deleteResult.operationBarrierTargets).toContainEqual({
      readModelKey: "cost_statistics",
      scopeKey: "active:2025-12",
    });
  });
});
