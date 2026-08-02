import {
  buildWorkbenchGroupDisplaySegments,
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  createEmptyWorkbenchZoneDisplayState,
  mergeWorkbenchGroupsById,
  workbenchPaneUsesDisplaySegments,
  workbenchRowMatchesUnifiedSearch,
} from "../features/workbench/groupDisplayModel";
import type { WorkbenchRelationGroup, WorkbenchRecord } from "../features/workbench/types";

function buildBankRow(id: string, transactionTime: string): WorkbenchRecord {
  return {
    id,
    caseId: `case-${id}`,
    recordType: "bank",
    label: `bank-${id}`,
    status: "待处理",
    statusCode: "unpaired",
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
    statusCode: "unpaired",
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
    statusCode: "unpaired",
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

function buildGroup(id: string, transactionTime: string): WorkbenchRelationGroup {
  return {
    id,
    groupType: "unpaired",
    rawGroupType: "unpaired",
    matchConfidence: "low",
    reason: "unpaired_fact",
    rows: {
      oa: [],
      bank: [buildBankRow(id, transactionTime)],
      invoice: [],
    },
  };
}

describe("groupDisplayModel time filter", () => {
  test("builds display segments only for complete one-to-one source coverage", () => {
    const oa248 = buildOaRow("oa-exp-248", "248.00");
    const oa292 = buildOaRow("oa-exp-292", "292.00");
    const invoice248 = buildAttachmentInvoiceRow("invoice-248", "oa-exp-248", "248.00");
    const invoice292 = buildAttachmentInvoiceRow("invoice-292", "oa-exp-292", "292.00");
    const group: WorkbenchRelationGroup = {
      id: "case:source-segment",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "source relation",
      rows: {
        oa: [oa248, oa292],
        bank: [buildBankRow("bank-001", "2026-03-28 10:18")],
        invoice: [invoice248, invoice292],
      },
    };

    const segments = buildWorkbenchGroupDisplaySegments(group);

    expect(segments?.map((segment) => segment.id)).toEqual(["oa-exp-248", "oa-exp-292"]);
    expect(segments?.[0].rows.oa).toEqual([oa248]);
    expect(segments?.[0].rows.invoice).toEqual([invoice248]);
    expect(segments?.[1].rows.oa).toEqual([oa292]);
    expect(segments?.[1].rows.invoice).toEqual([invoice292]);
    expect(segments?.every((segment) => segment.rows.bank.length === 0)).toBe(true);
    expect(workbenchPaneUsesDisplaySegments(group, "bank", segments)).toBe(false);
    expect(workbenchPaneUsesDisplaySegments(group, "invoice", segments)).toBe(true);
  });

  test("keeps unlinked same-amount and sum-matched rows at group level", () => {
    const oa469600 = buildOaRow("oa-exp-469600", "469600");
    const oa29350 = buildOaRow("oa-exp-29350", "29350");
    const oa88050 = buildOaRow("oa-exp-88050", "88050");
    const bank469600 = { ...buildBankRow("bank-469600", "2026-05-13 11:42"), amount: "469600" };
    const bank29350 = { ...buildBankRow("bank-29350", "2026-03-27 15:03"), amount: "29350" };
    const bank64996 = { ...buildBankRow("bank-64996", "2026-04-23 15:28"), amount: "64996.69" };
    const bank23053 = { ...buildBankRow("bank-23053", "2026-04-23 15:28"), amount: "23053.31" };
    const invoice29350 = buildInvoiceRow("invoice-29350", "29350");
    const group: WorkbenchRelationGroup = {
      id: "case:amount-fallback-segment",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [oa469600, oa29350, oa88050],
        bank: [bank469600, bank64996, bank23053, bank29350],
        invoice: [invoice29350],
      },
    };

    const segments = buildWorkbenchGroupDisplaySegments(group);

    expect(segments).toBeNull();
  });

  test("keeps partial and duplicate source coverage at group level", () => {
    const oa100 = buildOaRow("oa-exp-100", "100.00");
    const oa200 = buildOaRow("oa-exp-200", "200.00");
    const group: WorkbenchRelationGroup = {
      id: "case:partial-source-segment",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "existing_case_group",
      rows: {
        oa: [oa100, oa200],
        bank: [],
        invoice: [
          buildAttachmentInvoiceRow("invoice-100-a", oa100.id, "50.00"),
          buildAttachmentInvoiceRow("invoice-100-b", oa100.id, "50.00"),
        ],
      },
    };

    expect(buildWorkbenchGroupDisplaySegments(group)).toBeNull();
  });

  test("dedupes repeated paginated groups for paired and unpaired zones", () => {
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
      searchQuery: "供应商A",
      sortByPane: {
        oa: null,
        bank: "desc",
        invoice: null,
      },
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState>;

    expect(buildWorkbenchServerPageQuery(state)).toEqual({
      search: "供应商A",
      sort: "bank:desc",
    });
  });

  test("matches structured bank note labels and values shown in the grid", () => {
    const row = {
      ...buildBankRow("bank-searchable-text", "2026-07-21 11:30"),
      bankTextFields: [{ label: "客户附言", value: "专项服务费" }],
      tableValues: {
        transactionTime: "2026-07-21 11:30",
        paymentAccount: "建设银行 8106",
      },
    };

    expect(workbenchRowMatchesUnifiedSearch(row, "客户附言")).toBe(true);
    expect(workbenchRowMatchesUnifiedSearch(row, "专项服务费")).toBe(true);
    expect(workbenchRowMatchesUnifiedSearch(row, "建行 8106")).toBe(true);
  });

  test("matches the rendered invoice source label", () => {
    const row = {
      ...buildInvoiceRow("invoice-searchable-source", "100.00"),
      sourceKind: "oa_attachment_invoice" as const,
    };

    expect(workbenchRowMatchesUnifiedSearch(row, "OA附件")).toBe(true);
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
