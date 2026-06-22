import {
  buildWorkbenchGroupDisplaySegments,
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  createEmptyWorkbenchZoneDisplayState,
  mergeWorkbenchGroupsById,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchCandidateGroup, WorkbenchRecord } from "../features/workbench/types";

function buildBankRow(id: string, transactionTime: string): WorkbenchRecord {
  return {
    id,
    caseId: `case-${id}`,
    recordType: "bank",
    label: `bank-${id}`,
    status: "待处理",
    statusCode: "open",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "100.00",
    counterparty: `counterparty-${id}`,
    tableValues: {
      transactionTime,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function buildOaRow(id: string, amount = "100.00"): WorkbenchRecord {
  return {
    id,
    caseId: "case-source-segment",
    recordType: "oa",
    label: `oa-${id}`,
    status: "待处理",
    statusCode: "open",
    statusTone: "warn",
    exceptionHandled: false,
    amount,
    counterparty: `applicant-${id}`,
    tableValues: {
      applicant: `applicant-${id}`,
      amount,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function buildAttachmentInvoiceRow(id: string, sourceOaId: string, amount = "100.00"): WorkbenchRecord {
  return {
    id,
    caseId: "case-source-segment",
    recordType: "invoice",
    sourceKind: "oa_attachment_invoice",
    sourceOaId,
    label: `invoice-${id}`,
    status: "OA附件",
    statusCode: "oa_attachment_invoice",
    statusTone: "info",
    exceptionHandled: false,
    amount,
    counterparty: `seller-${id}`,
    tableValues: {
      sellerName: `seller-${id}`,
      amount,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function buildInvoiceRow(id: string, amount = "100.00"): WorkbenchRecord {
  return {
    id,
    caseId: "case-source-segment",
    recordType: "invoice",
    label: `invoice-${id}`,
    status: "待处理",
    statusCode: "open",
    statusTone: "warn",
    exceptionHandled: false,
    amount,
    counterparty: `seller-${id}`,
    tableValues: {
      sellerName: `seller-${id}`,
      amount,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: ["detail"],
  };
}

function buildGroup(id: string, transactionTime: string): WorkbenchCandidateGroup {
  return {
    id,
    groupType: "open",
    rawGroupType: "candidate",
    matchConfidence: "medium",
    reason: "test",
    rows: {
      oa: [],
      bank: [buildBankRow(id, transactionTime)],
      invoice: [],
    },
  };
}

describe("groupDisplayModel time filter", () => {
  test("builds source OA display segments for multi-OA attachment invoice groups", () => {
    const oa248 = buildOaRow("oa-exp-248", "248.00");
    const oa292 = buildOaRow("oa-exp-292", "292.00");
    const invoice120 = buildAttachmentInvoiceRow("invoice-120", "oa-exp-248", "120.00");
    const invoice128 = buildAttachmentInvoiceRow("invoice-128", "oa-exp-248", "128.00");
    const invoice292 = buildAttachmentInvoiceRow("invoice-292", "oa-exp-292", "292.00");
    const group: WorkbenchCandidateGroup = {
      id: "case:source-segment",
      groupType: "open",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "source relation",
      rows: {
        oa: [oa248, oa292],
        bank: [buildBankRow("bank-001", "2026-03-28 10:18")],
        invoice: [invoice120, invoice128, invoice292],
      },
    };

    const segments = buildWorkbenchGroupDisplaySegments(group);

    expect(segments?.map((segment) => segment.id)).toEqual(["oa-exp-248", "oa-exp-292"]);
    expect(segments?.[0].rows.oa).toEqual([oa248]);
    expect(segments?.[0].rows.invoice).toEqual([invoice120, invoice128]);
    expect(segments?.[1].rows.oa).toEqual([oa292]);
    expect(segments?.[1].rows.invoice).toEqual([invoice292]);
    expect(segments?.every((segment) => segment.rows.bank.length === 0)).toBe(true);
  });

  test("builds amount fallback display segments for unlinked rows in multi-OA groups", () => {
    const oa469600 = buildOaRow("oa-exp-469600", "469600");
    const oa29350 = buildOaRow("oa-exp-29350", "29350");
    const oa88050 = buildOaRow("oa-exp-88050", "88050");
    const bank469600 = { ...buildBankRow("bank-469600", "2026-05-13 11:42"), amount: "469600" };
    const bank29350 = { ...buildBankRow("bank-29350", "2026-03-27 15:03"), amount: "29350" };
    const bank64996 = { ...buildBankRow("bank-64996", "2026-04-23 15:28"), amount: "64996.69" };
    const bank23053 = { ...buildBankRow("bank-23053", "2026-04-23 15:28"), amount: "23053.31" };
    const invoice29350 = buildInvoiceRow("invoice-29350", "29350");
    const group: WorkbenchCandidateGroup = {
      id: "case:amount-fallback-segment",
      groupType: "paired",
      rawGroupType: "manual_confirmed",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [oa469600, oa29350, oa88050],
        bank: [bank469600, bank64996, bank23053, bank29350],
        invoice: [invoice29350],
      },
    };

    const segments = buildWorkbenchGroupDisplaySegments(group);

    expect(segments?.map((segment) => segment.id)).toEqual(["oa-exp-469600", "oa-exp-29350", "oa-exp-88050"]);
    expect(segments?.[0].rows.bank).toEqual([bank469600]);
    expect(segments?.[1].rows.bank).toEqual([bank29350]);
    expect(segments?.[1].rows.invoice).toEqual([invoice29350]);
    expect(segments?.[2].rows.bank).toEqual([bank64996, bank23053]);
  });

  test("dedupes repeated paginated groups for paired and open zones", () => {
    const firstPageGroups = [
      buildGroup("case:paired-1", "2026-03-28 10:18"),
      buildGroup("case:paired-2", "2026-03-29 10:18"),
    ];
    const repeatedSecondPage = [
      buildGroup("case:paired-2", "2026-03-29 10:18"),
      buildGroup("case:paired-3", "2026-03-30 10:18"),
    ];

    expect(mergeWorkbenchGroupsById(firstPageGroups, repeatedSecondPage).map((group) => group.id)).toEqual([
      "case:paired-1",
      "case:paired-2",
      "case:paired-3",
    ]);
  });

  test("derives SQL page query controls from applied search and sort state", () => {
    const state = {
      ...createEmptyWorkbenchZoneDisplayState(),
      activePaneId: "bank",
      searchQueryByPane: {
        oa: "",
        bank: "供应商A",
        invoice: "",
      },
      sortByPane: {
        oa: null,
        bank: "desc",
        invoice: null,
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState>;

    expect(buildWorkbenchServerPageQuery(state)).toEqual({
      search: "供应商A",
      searchMode: "linked_context",
      sort: "bank:desc",
    });
  });

  test("filters bank groups by year and month when bank pane is active", () => {
    const groups = [
      buildGroup("group-2025-12", "2025-12-18 10:00"),
      buildGroup("group-2026-03", "2026-03-28 10:18"),
      buildGroup("group-2026-04", "2026-04-20 09:15"),
    ];

    const yearState = {
      ...createEmptyWorkbenchZoneDisplayState(),
      activePaneId: "bank",
      timeFilterByPane: {
        oa: { mode: "none" },
        bank: { mode: "year", year: "2026" },
        invoice: { mode: "none" },
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState> & {
      timeFilterByPane: {
        oa: { mode: "none" };
        bank: { mode: "year"; year: string };
        invoice: { mode: "none" };
      };
    };

    expect(buildWorkbenchDisplayGroups(groups, yearState).map((group) => group.id)).toEqual([
      "group-2026-03",
      "group-2026-04",
    ]);

    const monthState = {
      ...yearState,
      timeFilterByPane: {
        oa: { mode: "none" },
        bank: { mode: "month", month: "2026-04" },
        invoice: { mode: "none" },
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState> & {
      timeFilterByPane: {
        oa: { mode: "none" };
        bank: { mode: "month"; month: string };
        invoice: { mode: "none" };
      };
    };

    expect(buildWorkbenchDisplayGroups(groups, monthState).map((group) => group.id)).toEqual(["group-2026-04"]);
  });
});
