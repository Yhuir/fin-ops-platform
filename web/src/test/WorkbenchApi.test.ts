import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchWorkbench } from "../features/workbench/api";
import { buildWorkbenchDisplayGroups, createEmptyWorkbenchZoneDisplayState } from "../features/workbench/groupDisplayModel";
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

    expect(bankRow.tableValues.amount).toBe("6,000.00");
    expect(bankRow.amount).toBe("6,000.00");
    expect(bankRow.tableValues.direction).toBe("收入");
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
