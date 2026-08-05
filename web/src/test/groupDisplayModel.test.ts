import {
  buildWorkbenchGroupDisplayLayout,
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  createEmptyWorkbenchZoneDisplayState,
  mergeWorkbenchGroupsById,
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
  test("builds exact source-aligned rows without requiring every pane to be complete", () => {
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

    const layout = buildWorkbenchGroupDisplayLayout(group);
    const segments = layout?.segments;

    expect(segments?.map((segment) => segment.id)).toEqual(["oa-exp-248", "oa-exp-292"]);
    expect(segments?.[0].rows.oa).toEqual([oa248]);
    expect(segments?.[0].rows.invoice).toEqual([invoice248]);
    expect(segments?.[1].rows.oa).toEqual([oa292]);
    expect(segments?.[1].rows.invoice).toEqual([invoice292]);
    expect(segments?.every((segment) => segment.rows.bank.length === 0)).toBe(true);
    expect(layout?.segmentedPaneIds).toEqual(["oa", "invoice"]);
  });

  test("aligns unique exact amounts and leaves sum-matched rows in a residual segment", () => {
    const oa469600 = buildOaRow("oa-exp-469600", "469600");
    const oa29350 = buildOaRow("oa-exp-29350", "29350");
    const oa88050 = buildOaRow("oa-exp-88050", "88050");
    const bank469600 = { ...buildBankRow("bank-469600", "2026-05-13 11:42"), amount: "469600", tableValues: { direction: "支出" } };
    const bank29350 = { ...buildBankRow("bank-29350", "2026-03-27 15:03"), amount: "29350", tableValues: { direction: "支出" } };
    const bank64996 = { ...buildBankRow("bank-64996", "2026-04-23 15:28"), amount: "64996.69", tableValues: { direction: "支出" } };
    const bank23053 = { ...buildBankRow("bank-23053", "2026-04-23 15:28"), amount: "23053.31", tableValues: { direction: "支出" } };
    const invoice29350 = buildInvoiceRow("invoice-29350", "29350");
    const group: WorkbenchRelationGroup = {
      id: "case:amount-fallback-segment",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "existing_case_group",
      amountCheck: {
        status: "matched",
        direction: "expense",
        bankAmount: "586450.00",
        oaAmount: "586450.00",
        amountDelta: "0.00",
        requiresNote: false,
      },
      rows: {
        oa: [oa469600, oa29350, oa88050],
        bank: [bank469600, bank64996, bank23053, bank29350],
        invoice: [invoice29350],
      },
    };

    const layout = buildWorkbenchGroupDisplayLayout(group);
    const segments = layout?.segments;

    expect(layout?.segmentedPaneIds).toEqual(["oa", "bank", "invoice"]);
    expect(segments?.find((segment) => segment.id === oa469600.id)?.rows.bank).toEqual([bank469600]);
    expect(segments?.find((segment) => segment.id === oa29350.id)?.rows.bank).toEqual([bank29350]);
    expect(segments?.find((segment) => segment.id === oa29350.id)?.rows.invoice).toEqual([invoice29350]);
    expect(segments?.find((segment) => segment.id === oa88050.id)?.rows.bank).toEqual([]);
    expect(segments?.find((segment) => segment.id.endsWith(":bank:residual"))?.rows.bank).toEqual([
      bank64996,
      bank23053,
    ]);
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

    expect(buildWorkbenchGroupDisplayLayout(group)).toBeNull();
  });

  test("does not invent a unique amount match when the unfiltered source group has a duplicate target", () => {
    const oa100Visible = buildOaRow("oa-exp-100-visible", "100.00");
    const oa200 = buildOaRow("oa-exp-200", "200.00");
    const invoice100 = buildInvoiceRow("invoice-100", "100.00");
    const displayGroup: WorkbenchRelationGroup = {
      id: "case:hidden-duplicate",
      groupType: "paired",
      rawGroupType: "relation",
      matchConfidence: "high",
      reason: "existing_case_group",
      amountCheck: {
        status: "matched",
        direction: "expense",
        bankAmount: "0.00",
        oaAmount: "300.00",
        amountDelta: "0.00",
        requiresNote: false,
      },
      rows: { oa: [oa100Visible, oa200], bank: [], invoice: [invoice100] },
    };
    const sourceGroup: WorkbenchRelationGroup = {
      ...displayGroup,
      rows: {
        ...displayGroup.rows,
        oa: [...displayGroup.rows.oa, buildOaRow("oa-exp-100-hidden", "100.00")],
      },
    };

    expect(buildWorkbenchGroupDisplayLayout(displayGroup, sourceGroup)).toBeNull();
  });

  test("aligns exact and explicitly owned composite invoices in the 3061.64 reimbursement shape", () => {
    const amounts = ["127", "1400", "300", "7.84", "450", "400", "12", "100", "14", "16", "76.8", "158"];
    const parent = {
      ...buildOaRow("oa-exp-3061", "3061.64"),
      expenseItems: amounts.map((amount, index) => ({
        id: `oa-exp-3061:item:${index}`,
        rowIndex: String(index),
        projectName: index % 2 === 0 ? "项目甲" : "项目乙",
        amount,
      })),
    };
    const invoice = (id: string, itemIndex: number, amount: string) => ({
      ...buildAttachmentInvoiceRow(id, parent.id, amount),
      sourceExpenseItemId: `oa-exp-3061:item:${itemIndex}`,
      tableValues: { grossAmount: amount },
    });
    const invoices = [
      invoice("iv-127", 0, "127"),
      invoice("iv-1400", 1, "1400"),
      invoice("iv-300", 2, "300"),
      invoice("iv-8", 3, "8"),
      invoice("iv-400", 5, "400"),
      invoice("iv-12", 6, "12"),
      invoice("iv-100", 7, "100"),
      invoice("iv-14", 8, "14"),
      invoice("iv-16", 9, "16"),
      invoice("iv-29", 10, "29"),
      invoice("iv-47.8", 10, "47.8"),
      invoice("iv-158", 11, "158"),
    ];
    const group: WorkbenchRelationGroup = {
      id: "case:oa-exp-3061",
      groupType: "unpaired",
      matchConfidence: "high",
      reason: "canonical_unpaired",
      rows: { oa: [parent], bank: [], invoice: invoices },
    };

    const layout = buildWorkbenchGroupDisplayLayout(group);
    const alignedItemIds = layout?.segments
      .filter((segment) => segment.rows.oa[0]?.displayRole === "expense-claim-item" && segment.rows.invoice.length > 0)
      .map((segment) => segment.id);
    const renderedInvoiceIds = layout?.segments.flatMap((segment) => segment.rows.invoice.map((row) => row.id));

    expect(alignedItemIds).toEqual([0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11].map((index) => `oa-exp-3061:item:${index}`));
    expect(renderedInvoiceIds).toHaveLength(12);
    expect(new Set(renderedInvoiceIds).size).toBe(12);
    expect(layout?.segments.find((segment) => segment.id === "oa-exp-3061:item:3")?.rows.invoice)
      .toEqual([invoices[3]]);
    expect(layout?.segments.find((segment) => segment.id === "oa-exp-3061:item:10")?.rows.invoice)
      .toEqual([invoices[9], invoices[10]]);
    expect(layout?.segments.find((segment) => segment.id === "oa-exp-3061:item:10:invoice:residual"))
      .toBeUndefined();
  });

  test("keeps explicitly bound composite invoices on the expense-item row when totals differ", () => {
    const parent = {
      ...buildOaRow("oa-exp-405", "405.00"),
      expenseItems: [
        { id: "item-405", rowIndex: "0", projectName: "项目甲", amount: "405.00" },
        { id: "item-other", rowIndex: "1", projectName: "项目乙", amount: "10.00" },
      ],
    };
    const invoice350 = {
      ...buildAttachmentInvoiceRow("invoice-350", parent.id, "350.00"),
      sourceExpenseItemId: "item-405",
    };
    const invoice5499 = {
      ...buildAttachmentInvoiceRow("invoice-54.99", parent.id, "54.99"),
      sourceExpenseItemId: "item-405",
    };
    const group: WorkbenchRelationGroup = {
      id: "case:explicit-mismatch",
      groupType: "unpaired",
      matchConfidence: "high",
      reason: "explicit attachment ownership",
      rows: { oa: [parent], bank: [], invoice: [invoice350, invoice5499] },
    };

    const segment = buildWorkbenchGroupDisplayLayout(group)?.segments.find(({ id }) => id === "item-405");

    expect(segment?.rows.invoice).toEqual([invoice350, invoice5499]);
    expect(segment?.rows.oa[0].tableValues.amount).toBe("405.00");
  });

  test("renders one display-only invoice placeholder for an uploaded item with no parsed invoice", () => {
    const missingAnomaly = {
      code: "oa_invoice_attachment_missing" as const,
      label: "OA发票附件缺失",
      displayLabel: "OA发票附件缺失",
      fingerprint: "a".repeat(64),
      comparisonUnitId: "item-missing",
      sourceOaId: "oa-exp-missing",
      sourceExpenseItemId: "item-missing",
      oaTotal: "38.00",
      invoiceRowIds: [],
      attachmentFileCount: 1,
    };
    const parent = {
      ...buildOaRow("oa-exp-missing", "38.00"),
      expenseItems: [{
        id: "item-missing",
        rowIndex: "0",
        projectName: "项目甲",
        amount: "38.00",
        attachmentFileCount: 1,
        oaInvoiceAnomaly: missingAnomaly,
      }],
    };
    const group: WorkbenchRelationGroup = {
      id: "case:missing-attachment",
      groupType: "unpaired",
      matchConfidence: "high",
      reason: "explicit attachment missing",
      rows: { oa: [parent], bank: [], invoice: [] },
    };

    const layout = buildWorkbenchGroupDisplayLayout(group);
    const invoiceRows = layout?.segments.find(({ id }) => id === "item-missing")?.rows.invoice;

    expect(layout?.segmentedPaneIds).toContain("invoice");
    expect(invoiceRows).toHaveLength(1);
    expect(invoiceRows?.[0]).toMatchObject({
      displayOnly: true,
      label: "OA发票附件缺失",
      oaInvoiceAnomaly: missingAnomaly,
    });
  });

  test("does not align a partial display of an explicitly owned composite", () => {
    const parent = {
      ...buildOaRow("oa-exp-partial-composite", "76.80"),
      expenseItems: [
        {
          id: "oa-exp-partial-composite:item:0",
          rowIndex: "0",
          projectName: "项目甲",
          amount: "76.80",
        },
        {
          id: "oa-exp-partial-composite:item:1",
          rowIndex: "1",
          projectName: "项目乙",
          amount: "10.00",
        },
      ],
    };
    const invoice = (id: string, amount: string) => ({
      ...buildAttachmentInvoiceRow(id, parent.id, amount),
      sourceExpenseItemId: "oa-exp-partial-composite:item:0",
      tableValues: { grossAmount: amount },
    });
    const invoice29 = invoice("iv-partial-29", "29.00");
    const invoice47 = invoice("iv-partial-47", "47.80");
    const sourceGroup: WorkbenchRelationGroup = {
      id: "case:partial-composite",
      groupType: "unpaired",
      matchConfidence: "high",
      reason: "canonical_unpaired",
      rows: { oa: [parent], bank: [], invoice: [invoice29, invoice47] },
    };
    const displayGroup: WorkbenchRelationGroup = {
      ...sourceGroup,
      rows: { ...sourceGroup.rows, invoice: [invoice29] },
    };

    const layout = buildWorkbenchGroupDisplayLayout(displayGroup, sourceGroup);

    expect(layout?.segments.find((segment) => segment.id === "oa-exp-partial-composite:item:0")?.rows.invoice)
      .toEqual([]);
    expect(layout?.segmentedPaneIds).not.toContain("invoice");
    expect(displayGroup.rows.invoice).toEqual([invoice29]);
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

  test("normalizes grouped amount queries for server and local workbench search", () => {
    const state = {
      ...createEmptyWorkbenchZoneDisplayState(),
      searchQuery: "4,311.00",
    } as ReturnType<typeof createEmptyWorkbenchZoneDisplayState>;
    const row = buildOaRow("oa-money-search", "4,311.00");

    expect(buildWorkbenchServerPageQuery(state)).toEqual({ search: "4311.00" });
    expect(workbenchRowMatchesUnifiedSearch(row, "4311.00")).toBe(true);
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
