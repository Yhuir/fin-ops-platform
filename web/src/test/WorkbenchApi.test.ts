import { afterEach, describe, expect, test, vi } from "vitest";

import {
  applyWorkbenchException,
  fetchWorkbench,
  fetchWorkbenchGroupDetail,
  fetchWorkbenchGroupsPage,
  fetchWorkbenchInitialPage,
  previewWorkbenchException,
} from "../features/workbench/api";
import {
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  countWorkbenchGroupRows,
  createEmptyWorkbenchZoneDisplayState,
  workbenchRowMatchesUnifiedSearch,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchCandidateGroup, WorkbenchRecord, WorkbenchRecordType } from "../features/workbench/types";

const workbenchPanes: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

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

function createWorkbenchGroup(id: string, hitPanes: WorkbenchRecordType[]): WorkbenchCandidateGroup {
  return {
    id,
    groupType: "candidate",
    matchConfidence: "medium",
    reason: "测试三栏上下文搜索",
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

  test("does not mark ordinary open candidates withdrawable from row cancel actions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          summary: {
            oa_count: 1,
            bank_count: 1,
            invoice_count: 0,
            paired_count: 0,
            open_count: 2,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "case:ORDINARY-CANDIDATE",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "candidate_match",
                oa_rows: [
                  {
                    id: "oa-open-ordinary",
                    type: "oa",
                    applicant: "刘际涛",
                    project_name: "云南溯源科技",
                    apply_type: "支付申请",
                    amount: "6868.55",
                    counterparty_name: "刘树刚",
                    reason: "代购公车款",
                    oa_bank_relation: { code: "candidate_unclosed", label: "候选未闭环", tone: "warn" },
                    available_actions: ["detail", "confirm_link", "mark_exception"],
                  },
                ],
                bank_rows: [
                  {
                    id: "bank-open-ordinary",
                    type: "bank",
                    trade_time: "2026-04-03 09:00:07",
                    debit_amount: "6868.55",
                    credit_amount: "",
                    counterparty_name: "刘树刚",
                    payment_account_label: "建行 8106",
                    invoice_relation: { code: "candidate_unclosed", label: "候选未闭环", tone: "warn" },
                    remark: "摘要：电子转账 备注：代购公车款",
                    available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("all");

    expect(payload.open.groups[0].canWithdraw).toBe(false);
  });

  test("loads initial workbench page from summary and zone group endpoints", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.startsWith("/api/workbench/summary")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              summary: {
                oa_count: 1,
                bank_count: 1,
                invoice_count: 0,
                paired_count: 1,
                open_count: 1,
                exception_count: 0,
                zone_counts: {
                  paired: { groups: 1, oa: 0, bank: 7, invoice: 0, rows: 7 },
                  open: { groups: 1, oa: 3, bank: 0, invoice: 5, rows: 8 },
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
              generated_at: "2026-05-22T09:30:00+00:00",
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
                  group_type: "manual_confirmed",
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
      if (url.includes("zone=open")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              month: "all",
              zone: "open",
              page: 1,
              page_size: 200,
              total: 1,
              has_more: false,
              row_counts: { oa: 3, bank: 0, invoice: 5, rows: 8 },
              groups: [
                {
                  group_id: "case:open",
                  group_type: "candidate",
                  match_confidence: "medium",
                  reason: "候选",
                  oa_rows: [{ id: "oa-open", type: "oa", available_actions: ["detail"] }],
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

    const result = await fetchWorkbenchInitialPage("all");

    expect(result.data.summary.pairedCount).toBe(1);
    expect(result.data.summary.zoneCounts.paired.bank).toBe(7);
    expect(result.pages.paired.rowCounts.bank).toBe(7);
    expect(result.data.paired.groups[0].id).toBe("case:paired");
    expect(result.data.open.groups[0].id).toBe("case:open");
    expect(result.data.invoiceInventory.systemTotal).toBe(9);
    expect(result.data.invoiceInventory.oaAttachmentTotal).toBe(5);
    expect(result.data.oaStatus.message).toBe("OA 已同步");
    expect(result.pages.open.hasMore).toBe(false);
    expect(fetchSpy.mock.calls.some(([input]) => String(input).startsWith("/api/workbench?"))).toBe(false);
    const groupCalls = fetchSpy.mock.calls
      .map(([input]) => new URL(String(input), "http://localhost"))
      .filter((url) => url.pathname === "/api/workbench/groups");
    expect(groupCalls).toHaveLength(2);
    expect(groupCalls.map((url) => url.searchParams.get("page_size"))).toEqual(["200", "200"]);
    expect(groupCalls.every((url) => url.searchParams.get("detail_level") === "summary")).toBe(true);
  });

  test("serializes workbench group page SQL query controls", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          zone: "open",
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

    await fetchWorkbenchGroupsPage("all", "open", 2, 25, undefined, {
      search: "供应商A",
      status: "open",
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
    });

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("open");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("search")).toBe("供应商A");
    expect(url.searchParams.get("status")).toBe("open");
    expect(url.searchParams.get("source_kind")).toBe("bank_transaction");
    expect(url.searchParams.get("sort")).toBe("bank:desc");
    expect(url.searchParams.get("detail_level")).toBe("summary");
    expect(JSON.parse(url.searchParams.get("column_filters") ?? "{}")).toEqual({
      bank: { amount: ["建行 8106", "支出"], counterparty: ["云南溯源科技有限公司"] },
    });
    expect(JSON.parse(url.searchParams.get("time_filters") ?? "{}")).toEqual({
      bank: { mode: "month", month: "2026-04" },
    });
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
            group_type: "manual_confirmed",
            match_confidence: "high",
            reason: "免OA批次",
            relation_mode: "no_oa_bank_batch",
            display_mode: "collapsed_summary",
            oa_rows: [],
            bank_rows: [{ id: "summary", type: "bank", source_kind: "no_oa_bank_batch_summary" }],
            invoice_rows: [],
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

    const group = await fetchWorkbenchGroupDetail("all", "paired", "case:no-oa");

    const url = new URL(String(fetchSpy.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/workbench/groups/detail");
    expect(url.searchParams.get("month")).toBe("all");
    expect(url.searchParams.get("zone")).toBe("paired");
    expect(url.searchParams.get("group_id")).toBe("case:no-oa");
    expect(group.id).toBe("case:no-oa");
    expect(group.collapsedRows?.bank).toHaveLength(4);
  });

  test("maps summary workbench rows without requiring heavy detail fields", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 1,
            paired_count: 0,
            open_count: 2,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "case:summary-rows",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "summary rows",
                oa_rows: [
                  {
                    id: "oa-summary",
                    type: "oa",
                    applicant: "张三",
                    project_name: "摘要项目",
                    apply_type: "费用报销",
                    amount: "100.00",
                    counterparty_name: "供应商A",
                    reason: "差旅费",
                    summary_fields: { "申请日期": "2026-03-01T08:30:00+08:00" },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [
                  {
                    id: "invoice-summary",
                    type: "invoice",
                    seller_name: "供应商A",
                    buyer_name: "杭州溯源科技有限公司",
                    issue_date: "2026-03-02",
                    amount: "100.00",
                    total_with_tax: "106.00",
                    summary_fields: { "发票代码": "044001", "发票号码": "12345678" },
                    available_actions: ["detail"],
                  },
                ],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.open.groups[0];

    expect(group.rows.oa[0].tableValues.applicationTime).toBe("2026-03-01 08:30:00");
    expect(group.rows.invoice[0].tableValues.invoiceCode).toBe("044001");
    expect(group.rows.invoice[0].tableValues.invoiceNo).toBe("12345678");
  });

  test("normalizes bank row amounts without grouping separators for display search", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 1,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "case:CASE-BANK-AMOUNT-001",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "银行金额搜索口径",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "bank-amount-search-001",
                    type: "bank",
                    trade_time: "2026-03-20 16:05:40",
                    direction: "支出",
                    debit_amount: "19,370.00",
                    credit_amount: "",
                    amount: "19,370.00",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "pending", label: "待处理", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.open.groups[0];
    const bankRow = group.rows.bank[0];

    expect(bankRow.amount).toBe("19370");
    expect(bankRow.tableValues.amount).toBe("19370");
    expect(bankRow.tableValues.debitAmount).toBe("19370");
    expect(workbenchRowMatchesUnifiedSearch(bankRow, "19370")).toBe(true);
  });

  test("normalizes workbench bank timestamps and numeric-scale amounts for display", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-04",
          summary: {
            oa_count: 0,
            bank_count: 2,
            invoice_count: 0,
            paired_count: 0,
            open_count: 2,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "case:scaled-bank-amounts",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "numeric scale display",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "bank-scale-1",
                    type: "bank",
                    trade_time: "2026-04-23T17:33:56+08:00",
                    pay_receive_time: "2026-04-23T17:33:56+08:00",
                    direction: "支出",
                    debit_amount: "1.000000",
                    credit_amount: "",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建行 8106",
                    invoice_relation: { code: "no_oa_bank_batch", label: "免OA批量处理", tone: "success" },
                    available_actions: ["detail"],
                  },
                  {
                    id: "bank-scale-2",
                    type: "bank",
                    trade_time: "2026-04-23T17:22:27+08:00",
                    pay_receive_time: "2026-04-23T17:22:27+08:00",
                    direction: "支出",
                    debit_amount: "4.500000",
                    credit_amount: "",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建行 8106",
                    invoice_relation: { code: "no_oa_bank_batch", label: "免OA批量处理", tone: "success" },
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-04");
    const bankRows = payload.open.groups[0].rows.bank;

    expect(bankRows[0].amount).toBe("1");
    expect(bankRows[0].tableValues.amount).toBe("1");
    expect(bankRows[0].tableValues.transactionTime).toBe("2026-04-23 17:33:56");
    expect(bankRows[0].tableValues.paymentOrReceiptTime).toBe("2026-04-23 17:33:56");
    expect(bankRows[1].amount).toBe("4.5");
    expect(bankRows[1].tableValues.amount).toBe("4.5");
    expect(bankRows[1].tableValues.transactionTime).toBe("2026-04-23 17:22:27");
  });

  test("maps batch accounting relation note and amount check fields", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 1,
            invoice_count: 0,
            paired_count: 1,
            open_count: 0,
            exception_count: 0,
          },
          paired: {
            groups: [
              {
                group_id: "case:CASE-BATCH-txn_imported_202601_batch_001",
                group_type: "manual_confirmed",
                match_confidence: "high",
                reason: "日常报销批量账务管理",
                relation_note: "财务确认差额闭环",
                amount_check: {
                  status: "mismatch",
                  direction: "expense",
                  bank_amount: "3617.41",
                  oa_amount: "3425.41",
                  amount_delta: "192.00",
                  requires_note: true,
                },
                oa_rows: [],
                bank_rows: [
                  {
                    id: "txn_imported_202601_batch_001",
                    type: "bank",
                    trade_time: "2026-03-20 16:05:40",
                    direction: "支出",
                    debit_amount: "3617.41",
                    credit_amount: "",
                    amount: "3617.41",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "matched", label: "已匹配", tone: "success" },
                    relation_note: "财务确认差额闭环",
                    relation_amount_check: {
                      status: "mismatch",
                      direction: "expense",
                      bank_amount: "3617.41",
                      oa_amount: "3425.41",
                      amount_delta: "192.00",
                      requires_note: true,
                    },
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
          open: { groups: [] },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.paired.groups[0];
    const bankRow = group.rows.bank[0];

    expect(group.relationNote).toBe("财务确认差额闭环");
    expect(group.amountCheck?.status).toBe("mismatch");
    expect(group.amountCheck?.direction).toBe("expense");
    expect(group.amountCheck?.requiresNote).toBe(true);
    expect(bankRow.relationNote).toBe("财务确认差额闭环");
    expect(bankRow.relationAmountCheck?.amountDelta).toBe("192.00");
  });

  test("maps invoice inventory stats from the workbench payload", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 0,
            invoice_count: 1,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          invoice_inventory: {
            system_total: 8,
            manual_import_total: 5,
            workbench_visible_total: 3,
            hidden_submitted_etc_total: 2,
            extra_etc_total: 1,
            etc_summary_batch_count: 4,
            oa_attachment_total: 6,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-INVENTORY",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "发票库存统计不依赖可见行",
                oa_rows: [],
                bank_rows: [],
                invoice_rows: [
                  {
                    id: "iv-visible-001",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    seller_name: "可见 OA 附件票",
                    buyer_name: "杭州溯源科技有限公司",
                    issue_date: "2026-03-20",
                    amount: "100.00",
                    tax_rate: "6%",
                    tax_amount: "6.00",
                    total_with_tax: "106.00",
                    invoice_type: "进项专票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");

    expect(payload.invoiceInventory).toEqual({
      systemTotal: 8,
      manualImportTotal: 5,
      workbenchVisibleTotal: 3,
      hiddenSubmittedEtcTotal: 2,
      extraEtcTotal: 1,
      etcSummaryBatchCount: 4,
      oaAttachmentTotal: 6,
    });
  });

  test("maps no-OA collapsed summary groups and preserves collapsed bank detail rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 3,
            invoice_count: 0,
            paired_count: 1,
            open_count: 0,
            exception_count: 0,
          },
          paired: {
            groups: [
              {
                group_id: "no-oa-bank-batch:NOOA-202603-FEE",
                group_type: "manual_confirmed",
                match_confidence: "high",
                reason: "免OA手续费批次",
                relation_mode: "no_oa_bank_batch",
                display_mode: "collapsed_summary",
                default_collapsed: true,
                summary_row: {
                  id: "nooa-summary-NOOA-202603-FEE",
                  type: "bank",
                  source_kind: "no_oa_bank_batch_summary",
                  trade_time: "2026-03",
                  direction: "支出",
                  debit_amount: "30.00",
                  credit_amount: "",
                  counterparty_name: "免OA手续费批次",
                  payment_account_label: "建设银行 8106",
                  invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                  available_actions: ["detail", "withdraw_no_oa_batch"],
                  special_metadata: {
                    source_batch_id: "NOOA-202603-FEE",
                    batch_version: 7,
                  },
                },
                oa_rows: [],
                bank_rows: [
                  {
                    id: "nooa-summary-NOOA-202603-FEE",
                    type: "bank",
                    source_kind: "no_oa_bank_batch_summary",
                    trade_time: "2026-03",
                    direction: "支出",
                    debit_amount: "30.00",
                    credit_amount: "",
                    counterparty_name: "免OA手续费批次",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                    available_actions: ["detail", "withdraw_no_oa_batch"],
                    special_metadata: {
                      source_batch_id: "NOOA-202603-FEE",
                      batch_version: 7,
                    },
                  },
                ],
                invoice_rows: [],
                collapsed_rows: {
                  bank: [
                    {
                      id: "bk-nooa-fee-001",
                      type: "bank",
                      trade_time: "2026-03-08 09:00:00",
                      direction: "支出",
                      debit_amount: "10.00",
                      credit_amount: "",
                      counterparty_name: "建设银行手续费",
                      payment_account_label: "建设银行 8106",
                      invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                      bank_text_fields: [{ label: "摘要", value: "账户管理费" }],
                      available_actions: ["detail"],
                    },
                    {
                      id: "bk-nooa-fee-002",
                      type: "bank",
                      trade_time: "2026-03-09 09:00:00",
                      direction: "支出",
                      debit_amount: "20.00",
                      credit_amount: "",
                      counterparty_name: "网银服务费",
                      payment_account_label: "建设银行 8106",
                      invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                      bank_text_fields: [{ label: "摘要", value: "企业网银年费" }],
                      available_actions: ["detail"],
                    },
                  ],
                },
              },
            ],
          },
          open: { groups: [] },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.paired.groups[0];

    expect(group.relationMode).toBe("no_oa_bank_batch");
    expect(group.displayMode).toBe("collapsed_summary");
    expect(group.defaultCollapsed).toBe(true);
    expect(group.summaryRow?.sourceKind).toBe("no_oa_bank_batch_summary");
    expect(group.summaryRow?.id).toBe("nooa-summary-NOOA-202603-FEE");
    expect(group.rows.bank.map((row) => row.id)).toEqual(["nooa-summary-NOOA-202603-FEE"]);
    expect(group.collapsedRows?.bank.map((row) => row.id)).toEqual(["bk-nooa-fee-001", "bk-nooa-fee-002"]);
    expect(group.collapsedRows?.bank.map((row) => row.id)).not.toContain("nooa-summary-NOOA-202603-FEE");
    expect(group.collapsedRows?.bank[1].tableValues.note).toBe("摘要：企业网银年费");
    expect(payload.summary.pairedCount).toBe(2);
  });

  test("keeps groups searchable when the hit is inside collapsed no-OA bank detail rows", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.searchQueryByPane.bank = "企业网银年费";

    const displayGroups = buildWorkbenchDisplayGroups(
      [
        {
          id: "nooa-group",
          groupType: "manual_confirmed",
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
          groupType: "manual_confirmed",
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

  test("maps submitted salary and internal-transfer no-OA results without old auto-pair modes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 5,
            invoice_count: 0,
            paired_count: 2,
            open_count: 0,
            exception_count: 0,
          },
          paired: {
            groups: [
              {
                group_id: "no-oa-bank-batch:NOOA-202603-SALARY",
                group_type: "manual_confirmed",
                match_confidence: "high",
                reason: "免OA工资批次",
                relation_mode: "no_oa_bank_batch",
                display_mode: "collapsed_summary",
                default_collapsed: true,
                oa_rows: [],
                bank_rows: [
                  {
                    id: "nooa-summary-NOOA-202603-SALARY",
                    type: "bank",
                    source_kind: "no_oa_bank_batch_summary",
                    trade_time: "2026-03",
                    direction: "支出",
                    debit_amount: "80,000.00",
                    credit_amount: "",
                    counterparty_name: "免OA工资批次",
                    payment_account_label: "民生银行 0933",
                    invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                    available_actions: ["detail", "withdraw_no_oa_batch"],
                    special_metadata: { source_batch_id: "NOOA-202603-SALARY", batch_type: "salary" },
                  },
                ],
                invoice_rows: [],
                collapsed_rows: { bank: [] },
              },
              {
                group_id: "no-oa-bank-batch:NOOA-202603-INTERNAL",
                group_type: "manual_confirmed",
                match_confidence: "high",
                reason: "免OA内部往来款批次",
                relation_mode: "no_oa_bank_batch",
                display_mode: "collapsed_summary",
                default_collapsed: true,
                oa_rows: [],
                bank_rows: [
                  {
                    id: "nooa-summary-NOOA-202603-INTERNAL",
                    type: "bank",
                    source_kind: "no_oa_bank_batch_summary",
                    trade_time: "2026-03",
                    direction: "收入",
                    debit_amount: "",
                    credit_amount: "125,000.00",
                    counterparty_name: "免OA内部往来款批次",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "no_oa_bank_batch", label: "免OA批次", tone: "success" },
                    available_actions: ["detail", "withdraw_no_oa_batch"],
                    special_metadata: { source_batch_id: "NOOA-202603-INTERNAL", batch_type: "internal_transfer" },
                  },
                ],
                invoice_rows: [],
                collapsed_rows: { bank: [] },
              },
            ],
          },
          open: { groups: [] },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");

    expect(payload.paired.groups).toHaveLength(2);
    expect(payload.paired.groups.map((group) => group.relationMode)).toEqual([
      "no_oa_bank_batch",
      "no_oa_bank_batch",
    ]);
    expect(payload.paired.groups.map((group) => group.groupType)).toEqual(["manual_confirmed", "manual_confirmed"]);
    expect(payload.paired.groups.map((group) => group.displayMode)).toEqual(["collapsed_summary", "collapsed_summary"]);
    expect(payload.paired.groups.map((group) => group.rows.bank[0].sourceKind)).toEqual([
      "no_oa_bank_batch_summary",
      "no_oa_bank_batch_summary",
    ]);
    expect(payload.paired.groups.map((group) => group.relationMode)).not.toContain("salary_personal_auto_match");
    expect(payload.paired.groups.map((group) => group.relationMode)).not.toContain("internal_transfer_pair");
  });

  test("defaults invoice inventory stats when older workbench payloads omit them", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 0,
            invoice_count: 0,
            paired_count: 0,
            open_count: 0,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: { groups: [] },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");

    expect(payload.invoiceInventory).toEqual({
      systemTotal: 0,
      manualImportTotal: 0,
      workbenchVisibleTotal: 0,
      hiddenSubmittedEtcTotal: 0,
      extraEtcTotal: 0,
      etcSummaryBatchCount: 0,
      oaAttachmentTotal: 0,
    });
  });

  test("maps inflow bank rows into the unified amount column from credit_amount", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 1,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-900",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "收入流水待确认",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "bk-income-001",
                    type: "bank",
                    trade_time: "2026-03-20 16:05:40",
                    direction: "收入",
                    debit_amount: "",
                    credit_amount: "6,000.00",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "manual_review", label: "待人工核查", tone: "danger" },
                    pay_receive_time: "2026-03-20 16:05:40",
                    remark: "收入待核查",
                    category_code: "borrow_in_company_pending_repayment",
                    category_label: "公司暂借款：待还款",
                    category_source: "manual",
                    tags: ["公司暂借款：待还款"],
                    bank_text_fields: [
                      { label: "摘要", value: "电子转账" },
                      { label: "备注", value: "代购公车款" },
                      { label: "用途", value: "货款" },
                    ],
                    repayment_date: "",
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const bankRow = payload.open.groups[0].rows.bank[0];

    expect(bankRow.tableValues.amount).toBe("6000");
    expect(bankRow.amount).toBe("6000");
    expect(bankRow.tableValues.direction).toBe("收入");
    expect((bankRow as any).categoryCode).toBe("borrow_in_company_pending_repayment");
    expect((bankRow as any).categoryLabel).toBe("公司暂借款：待还款");
    expect((bankRow as any).categorySource).toBe("manual");
    expect((bankRow as any).bankTextFields).toEqual([
      { label: "摘要", value: "电子转账" },
      { label: "备注", value: "代购公车款" },
      { label: "用途", value: "货款" },
    ]);
    expect(bankRow.tableValues.note).toBe("摘要：电子转账\n备注：代购公车款\n用途：货款");
  });

  test("maps OA 2035 formal attachment invoices without payment evidence rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 7,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "case:CASE-202603-OA-ATTACHMENT-2035",
                group_type: "source_linked",
                match_confidence: "high",
                reason: "oa_attachment_source_relation",
                oa_rows: [
                  {
                    id: "oa-exp-2035",
                    type: "oa",
                    applicant: "胡瑢",
                    project_name: "OA 2035 报销单",
                    apply_type: "日常报销",
                    amount: "248.00",
                    counterparty_name: "胡瑢",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [
                  {
                    id: "iv-oa-2035-machine-25",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-2035",
                    seller_name: "昆玉高速公路收费站",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "25.00",
                    total_with_tax: "25.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                  },
                  {
                    id: "iv-oa-2035-machine-23",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-2035",
                    seller_name: "玉昆高速公路收费站",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "23.00",
                    total_with_tax: "23.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                  },
                  {
                    id: "iv-oa-2035-fuel-200",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-2035",
                    seller_name: "中国石油云南销售公司",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "200.00",
                    total_with_tax: "200.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.open.groups[0];

    expect(group.id).toBe("case:CASE-202603-OA-ATTACHMENT-2035");
    expect(group.rows.oa.map((row) => row.id)).toEqual(["oa-exp-2035"]);
    expect(group.rows.invoice.map((row) => row.id)).toEqual([
      "iv-oa-2035-machine-25",
      "iv-oa-2035-machine-23",
      "iv-oa-2035-fuel-200",
    ]);
    expect(group.rows.invoice.map((row) => row.sourceKind)).toEqual([
      "oa_attachment_invoice",
      "oa_attachment_invoice",
      "oa_attachment_invoice",
    ]);
    expect(group.rows.invoice.map((row) => row.label)).toEqual([
      "OA附件",
      "OA附件",
      "OA附件",
    ]);
  });

  test("keeps all-time CCB bank rows visible across paired and open groups by default", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "all",
          summary: {
            oa_count: 0,
            bank_count: 4,
            invoice_count: 1,
            paired_count: 1,
            open_count: 3,
            exception_count: 0,
          },
          paired: {
            groups: [
              {
                group_id: "case:CASE-CCB-PAIRED-001",
                group_type: "manual_confirmed",
                match_confidence: "high",
                reason: "relation_snapshot",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "ccb-apr-paired",
                    type: "bank",
                    trade_time: "2026-04-08 09:00:00",
                    direction: "支出",
                    debit_amount: "40.00",
                    credit_amount: "",
                    counterparty_name: "建设银行可见性测试供应商",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [
                  {
                    id: "invoice-apr-paired",
                    type: "invoice",
                    seller_name: "建设银行配对供应商",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-04-08",
                    amount: "40.00",
                    total_with_tax: "40.00",
                    invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
                    available_actions: ["detail"],
                  },
                ],
              },
            ],
          },
          open: {
            groups: [
              {
                group_id: "row:ccb-jan-open",
                group_type: "candidate",
                match_confidence: "low",
                reason: "single_open_row",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "ccb-jan-open",
                    type: "bank",
                    trade_time: "2026-01-08 09:00:00",
                    direction: "支出",
                    debit_amount: "10.00",
                    credit_amount: "",
                    counterparty_name: "建设银行可见性测试供应商",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "pending_invoice_match", label: "待关联发票", tone: "warn" },
                    available_actions: ["detail"],
                  },
                  {
                    id: "ccb-feb-open",
                    type: "bank",
                    trade_time: "2026-02-08 09:00:00",
                    direction: "支出",
                    debit_amount: "20.00",
                    credit_amount: "",
                    counterparty_name: "建设银行可见性测试供应商",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "pending_invoice_match", label: "待关联发票", tone: "warn" },
                    available_actions: ["detail"],
                  },
                  {
                    id: "ccb-mar-open",
                    type: "bank",
                    trade_time: "2026-03-08 09:00:00",
                    direction: "支出",
                    debit_amount: "30.00",
                    credit_amount: "",
                    counterparty_name: "建设银行可见性测试供应商",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "pending_invoice_match", label: "待关联发票", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("all");
    const state = createEmptyWorkbenchZoneDisplayState();
    const displayGroups = buildWorkbenchDisplayGroups([...payload.paired.groups, ...payload.open.groups], state);
    const pairedBankRows = payload.paired.groups.flatMap((group) => group.rows.bank);
    const openBankRows = payload.open.groups.flatMap((group) => group.rows.bank);
    const displayBankRows = displayGroups.flatMap((group) => group.rows.bank);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench?month=all",
      expect.objectContaining({ method: "GET", signal: undefined, credentials: "include" }),
    );
    expect(payload.summary.bankCount).toBe(4);
    expect(pairedBankRows.map((row) => row.id)).toEqual(["ccb-apr-paired"]);
    expect(openBankRows.map((row) => row.id)).toEqual(["ccb-jan-open", "ccb-feb-open", "ccb-mar-open"]);
    expect(openBankRows).toHaveLength(3);
    expect(pairedBankRows.length + openBankRows.length).toBe(4);
    expect(displayBankRows.map((row) => row.id)).toEqual([
      "ccb-apr-paired",
      "ccb-jan-open",
      "ccb-feb-open",
      "ccb-mar-open",
    ]);
    expect(displayBankRows.every((row) => row.tableValues.paymentAccount === "建设银行 8106")).toBe(true);
  });

  test("keeps aggregated OA detail fields available for the detail drawer", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-OA-AGG",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "聚合 OA 待确认",
                oa_rows: [
                  {
                    id: "oa-exp-1994",
                    type: "oa",
                    applicant: "张敏",
                    project_name: "现场报销项目",
                    apply_type: "日常报销",
                    amount: "1,549.00",
                    counterparty_name: "张敏",
                    reason: "聚合报销单",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    detail_fields: {
                      明细摘要: "交通费 800.00；住宿费 749.00",
                      明细金额合计: "1,549.00",
                      费用内容摘要: "项目现场交通；项目住宿",
                      附件发票摘要: "滴滴出行发票 800.00；酒店发票 749.00",
                      金额差异: "主表 1,549.00；明细合计 1,548.99；差异 0.01",
                    },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const oaRow = payload.open.groups[0].rows.oa[0];

    expect(oaRow.detailFields).toEqual(
      expect.arrayContaining([
        { label: "明细摘要", value: "交通费 800.00；住宿费 749.00" },
        { label: "费用内容摘要", value: "项目现场交通；项目住宿" },
        { label: "附件发票摘要", value: "滴滴出行发票 800.00；酒店发票 749.00" },
        { label: "明细金额合计", value: "1,549.00" },
        { label: "金额差异", value: "主表 1,549.00；明细合计 1,548.99；差异 0.01" },
      ]),
    );
  });

  test("maps OA attachment invoice source detail fields without splitting OA rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 3,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-OA-ATTACHMENT-248",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "OA 附件发票按付款项归属展示",
                oa_rows: [
                  {
                    id: "oa-exp-248",
                    type: "oa",
                    applicant: "胡瑢",
                    project_name: "2024-2026年度红塔集团工作证管理系统维护项目",
                    apply_type: "日常报销",
                    amount: "248.00",
                    counterparty_name: "胡瑢",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    detail_fields: {
                      明细摘要: "付款项 1 120.00；付款项 2 128.00",
                    },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [
                  {
                    id: "iv-oa-attachment-248-001",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-248",
                    seller_name: "附件销方 A",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "120.00",
                    tax_amount: "0.00",
                    total_with_tax: "120.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                    detail_fields: {
                      derived_from_oa_id: "oa-exp-248",
                      source_expense_row_index: "1",
                      source_expense_item_id: "oa-exp-248:item:1",
                      source_attachment_name: "付款项1-交通费.pdf",
                      source_attachment_key: "oa-exp-248/item-1/traffic.pdf",
                    },
                  },
                  {
                    id: "iv-oa-attachment-248-002",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-248",
                    seller_name: "附件销方 B",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "128.00",
                    tax_amount: "0.00",
                    total_with_tax: "128.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                    detail_fields: {
                      derived_from_oa_id: "oa-exp-248",
                      source_expense_row_index: "2",
                      source_expense_item_id: "oa-exp-248:item:2",
                      source_attachment_name: "付款项2-住宿费.pdf",
                      source_attachment_key: "oa-exp-248/item-2/hotel.pdf",
                    },
                  },
                  {
                    id: "iv-oa-attachment-248-003",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-248",
                    seller_name: "附件销方 C",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-04",
                    amount: "0.00",
                    tax_amount: "0.00",
                    total_with_tax: "0.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                    detail_fields: {
                      derived_from_oa_id: "oa-exp-248",
                      source_expense_row_index: "1",
                      source_expense_item_id: "oa-exp-248:item:1",
                      source_attachment_name: "付款项1-补充说明.pdf",
                      source_attachment_key: "oa-exp-248/item-1/supplement.pdf",
                    },
                  },
                ],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.open.groups[0];
    const firstAttachmentInvoice = group.rows.invoice[0];

    expect(group.rows.oa).toHaveLength(1);
    expect(group.rows.oa.map((row) => row.id)).toEqual(["oa-exp-248"]);
    expect(group.rows.invoice).toHaveLength(3);
    expect(group.rows.invoice.every((row) => row.sourceKind === "oa_attachment_invoice")).toBe(true);
    expect(firstAttachmentInvoice.detailFields).toEqual(
      expect.arrayContaining([
        { label: "来源OA单号", value: "oa-exp-248" },
        { label: "来源OA明细行号", value: "1" },
        { label: "来源付款项ID", value: "oa-exp-248:item:1" },
        { label: "来源附件文件名", value: "付款项1-交通费.pdf" },
        { label: "来源附件Key", value: "oa-exp-248/item-1/traffic.pdf" },
      ]),
    );
    expect(firstAttachmentInvoice.detailFields.map((field) => field.label)).not.toContain("source_expense_item_id");
  });

  test("maps the 292 OA attachment fixture as one OA row and one attachment invoice", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 1,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-OA-ATTACHMENT-292",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "单付款项 OA 附件发票不重复",
                oa_rows: [
                  {
                    id: "oa-exp-292",
                    type: "oa",
                    applicant: "胡瑢",
                    project_name: "红云红河烟草能源管理运维项目",
                    apply_type: "日常报销",
                    amount: "292.00",
                    counterparty_name: "胡瑢",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [
                  {
                    id: "iv-oa-attachment-292-001",
                    type: "invoice",
                    source_kind: "oa_attachment_invoice",
                    case_id: "CASE-202603-OA-ATTACHMENT-292",
                    seller_name: "附件销方",
                    buyer_name: "云南溯源科技有限公司",
                    issue_date: "2026-03-24",
                    amount: "292.00",
                    total_with_tax: "292.00",
                    invoice_type: "进项普票",
                    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
                    available_actions: ["detail"],
                    detail_fields: {
                      derived_from_oa_id: "oa-exp-292",
                      source_expense_row_index: "1",
                      source_expense_item_id: "oa-exp-292:item:1",
                      source_attachment_name: "付款项1-发票.pdf",
                      source_attachment_key: "oa-exp-292/item-1/invoice.pdf",
                    },
                  },
                ],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const group = payload.open.groups[0];

    expect(group.rows.oa).toHaveLength(1);
    expect(group.rows.invoice).toHaveLength(1);
    expect(group.rows.invoice[0].id).toBe("iv-oa-attachment-292-001");
  });

  test("includes aggregated OA detail fields in pane search values", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-OA-AGG",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "聚合 OA 待确认",
                oa_rows: [
                  {
                    id: "oa-exp-1994",
                    type: "oa",
                    applicant: "张敏",
                    project_name: "现场报销项目",
                    apply_type: "日常报销",
                    amount: "1,549.00",
                    counterparty_name: "张敏",
                    reason: "聚合报销单",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    detail_fields: {
                      费用内容摘要: "项目现场交通；项目住宿",
                      附件发票摘要: "滴滴出行发票 800.00；酒店发票 749.00",
                    },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "oa";
    state.searchQueryByPane.oa = "酒店发票";

    expect(buildWorkbenchDisplayGroups(payload.open.groups, state).map((group) => group.id)).toEqual([
      "CASE-202603-OA-AGG",
    ]);

    state.searchQueryByPane.oa = "项目住宿";

    expect(buildWorkbenchDisplayGroups(payload.open.groups, state).map((group) => group.id)).toEqual([
      "CASE-202603-OA-AGG",
    ]);
  });

  test("uses OA project display label without losing real project search values", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 1,
            bank_count: 0,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-OA-MULTI-PROJECT",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "多项目 OA 待确认",
                oa_rows: [
                  {
                    id: "oa-exp-multi-project",
                    type: "oa",
                    applicant: "刘树刚",
                    project_name: "云南溯源科技；玉烟维护项目",
                    project_name_display: "多个项目",
                    project_names: ["云南溯源科技", "玉烟维护项目"],
                    apply_type: "日常报销",
                    amount: "1,549.00",
                    counterparty_name: "刘树刚",
                    reason: "多项目报销单",
                    oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                    detail_fields: {
                      项目名称汇总: "云南溯源科技；玉烟维护项目",
                      明细数量: "4",
                    },
                    available_actions: ["detail"],
                  },
                ],
                bank_rows: [],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const oaRow = payload.open.groups[0].rows.oa[0];
    expect(oaRow.tableValues.projectName).toBe("多个项目");

    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "oa";
    state.searchQueryByPane.oa = "玉烟维护项目";

    expect(buildWorkbenchDisplayGroups(payload.open.groups, state).map((group) => group.id)).toEqual([
      "CASE-202603-OA-MULTI-PROJECT",
    ]);
  });

  test.each(workbenchPanes)(
    "keeps row context and supplements same-keyword matches when searching the %s pane",
    (activePaneId) => {
      const groups = createContextSearchGroups(activePaneId);
      const state = createEmptyWorkbenchZoneDisplayState();
      state.activePaneId = activePaneId;
      state.searchQueryByPane[activePaneId] = "张三";

      const displayGroups = buildWorkbenchDisplayGroups(groups, state);
      const displayIds = displayGroups.map((group) => group.id);
      const supplementPanes = workbenchPanes.filter((paneId) => paneId !== activePaneId);

      expect(displayIds).toEqual([
        `${activePaneId}-anchor`,
        `${supplementPanes[0]}-supplement`,
        `${supplementPanes[1]}-supplement`,
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

  test("keeps pane search state isolated when only invoice query is set", () => {
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "invoice";
    state.searchQueryByPane.invoice = "26532000";

    expect(state.searchQueryByPane.invoice).toBe("26532000");
    expect(state.searchQueryByPane.oa).toBe("");
    expect(state.searchQueryByPane.bank).toBe("");
  });

  test("uses another pane search query when the active pane has only row filters", () => {
    const groups = createContextSearchGroups("invoice");
    const state = createEmptyWorkbenchZoneDisplayState();
    state.activePaneId = "bank";
    state.filtersByPaneAndColumn.bank = {
      direction: ["支出"],
    };
    state.searchQueryByPane.invoice = "张三";

    const displayGroups = buildWorkbenchDisplayGroups(groups, state);

    expect(displayGroups.map((group) => group.id)).toEqual([
      "invoice-anchor",
      "oa-supplement",
      "bank-supplement",
      "multi-pane-hit",
    ]);
    expect(displayGroups.find((group) => group.id === "invoice-anchor")?.rows.bank).toEqual([]);
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
              group_type: "candidate",
              match_confidence: "medium",
              reason: "summary preview",
              row_counts: { oa: 5, bank: 0, invoice: 2 },
              collapsed_row_counts: { bank: 8 },
              oa_rows: [{ id: "oa-preview", type: "oa", available_actions: ["detail"] }],
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

    expect(group.rowCounts).toEqual({ oa: 5, bank: 0, invoice: 2 });
    expect(group.collapsedRowCounts).toEqual({ bank: 8 });
    expect(group.rows.oa).toHaveLength(1);
    expect(countWorkbenchGroupRows(group)).toBe(15);
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
              detail: "OA 与流水来自同一候选组。",
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
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/exception/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          month: "all",
          row_ids: ["oa-1", "bank-1"],
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
          detail: "OA 与流水来自同一候选组。",
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
          workbench_refresh_required: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await applyWorkbenchException({
      month: "all",
      rowIds: ["bank-1"],
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
      workbenchRefreshRequired: true,
    });
  });
});
