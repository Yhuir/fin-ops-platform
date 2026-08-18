import type {
  WorkbenchRelationGroup,
  WorkbenchGroupsPageQuery,
  WorkbenchPaneRows,
  WorkbenchRecord,
  WorkbenchRecordType,
  WorkbenchSourceKind,
} from "./types";
import { normalizeMoneySearchQuery } from "../money";
import { parseWorkbenchAmountCents, workbenchComparableAmountCents } from "./selectionModel";

const workbenchPaneIds: WorkbenchRecordType[] = ["oa", "bank", "invoice"];
const compactBankNameByPrefix: Record<string, string> = {
  中国工商银行: "工行",
  工商银行: "工行",
  中国建设银行: "建行",
  建设银行: "建行",
  中国农业银行: "农行",
  农业银行: "农行",
  中国银行: "中行",
  招商银行: "招行",
  交通银行: "交行",
  中国光大银行: "光大",
  光大银行: "光大",
  中国民生银行: "民生",
  民生银行: "民生",
  平安银行: "平安",
};

export type WorkbenchGroupDisplaySegment = {
  id: string;
  rows: WorkbenchPaneRows;
};

export type WorkbenchGroupDisplayLayout = {
  segments: WorkbenchGroupDisplaySegment[];
  segmentedPaneIds: WorkbenchRecordType[];
};

export type WorkbenchPaneTimeFilter =
  | { mode: "none" }
  | { mode: "year"; year: string }
  | { mode: "month"; month: string };

export type WorkbenchZoneDisplayState = {
  activePaneId: WorkbenchRecordType | null;
  searchQuery: string;
  filtersByPaneAndColumn: Record<WorkbenchRecordType, Record<string, string[]>>;
  sortByPane: Record<WorkbenchRecordType, "asc" | "desc" | null>;
  timeFilterByPane: Record<WorkbenchRecordType, WorkbenchPaneTimeFilter>;
};

export function createEmptyWorkbenchZoneDisplayState(): WorkbenchZoneDisplayState {
  return {
    activePaneId: null,
    searchQuery: "",
    filtersByPaneAndColumn: {
      oa: {},
      bank: {},
      invoice: {},
    },
    sortByPane: {
      oa: null,
      bank: null,
      invoice: null,
    },
    timeFilterByPane: {
      oa: { mode: "none" },
      bank: { mode: "none" },
      invoice: { mode: "none" },
    },
  };
}

export function buildWorkbenchDisplayGroups(
  groups: WorkbenchRelationGroup[],
  state: WorkbenchZoneDisplayState,
  options: { serverFiltered?: boolean } = {},
): WorkbenchRelationGroup[] {
  if (options.serverFiltered) {
    return groups;
  }
  const activePaneId = resolveWorkbenchActivePane(state, state.activePaneId);
  const sortDirection = activePaneId ? state.sortByPane[activePaneId] : null;
  const hasPaneCriteria = Boolean(normalizeWorkbenchSearchText(state.searchQuery))
    || workbenchPaneIds.some((paneId) => paneHasWorkbenchRowCriteria(state, paneId));
  const hasPaneRowCriteria = workbenchPaneIds.some((paneId) => paneHasWorkbenchRowCriteria(state, paneId));

  const displayGroups = !hasPaneCriteria
    ? groups
    : groups.flatMap((group) => {
      if (!groupMatchesPaneCriteria(group, state)) {
        return [];
      }

      if (isCollapsedSummaryGroup(group)) {
        return [group];
      }

      const filteredGroup = applyPaneCriteriaToGroup(group, state);
      if (hasPaneRowCriteria && !groupHasRowsInCriteriaPanes(filteredGroup, state)) {
        return [];
      }

      return [filteredGroup];
    });

  if (!sortDirection || !activePaneId) {
    return displayGroups;
  }

  return sortWorkbenchGroups(displayGroups, activePaneId, sortDirection);
}

export function buildWorkbenchPaneRows(groups: WorkbenchRelationGroup[]): WorkbenchPaneRows {
  return {
    oa: groups.flatMap((group) => group.rows.oa),
    bank: groups.flatMap((group) => group.rows.bank),
    invoice: groups.flatMap((group) => group.rows.invoice),
  };
}

export function buildWorkbenchGroupDisplayLayout(
  group: WorkbenchRelationGroup,
  sourceGroup: WorkbenchRelationGroup = group,
): WorkbenchGroupDisplayLayout | null {
  const segments = buildWorkbenchGroupSourceSegments(group);
  const sourceSegments = sourceGroup === group ? segments : buildWorkbenchGroupSourceSegments(sourceGroup);
  if (!segments || !sourceSegments) {
    return null;
  }

  const displayRowsByPane = {
    bank: new Map(group.rows.bank.map((row) => [row.id, row])),
    invoice: new Map([
      ...group.rows.invoice,
      ...segments.flatMap((segment) => segment.rows.invoice.filter((row) => row.displayOnly)),
    ].map((row) => [row.id, row])),
  };
  const alignedRowIdsByPane = {
    bank: findAlignedRowIdsBySegment(sourceGroup, sourceSegments, "bank"),
    invoice: findAlignedRowIdsBySegment(sourceGroup, sourceSegments, "invoice"),
  };
  const hasExpenseClaimItems = segments.some(
    (segment) => segment.rows.oa[0]?.displayRole === "expense-claim-summary",
  );
  const expenseItemIds = new Set(
    segments.flatMap((segment) => segment.rows.oa.flatMap((row) => row.sourceExpenseItemIds ?? [])),
  );
  const hasUnassignedOaAttachmentInvoices = hasExpenseClaimItems && group.rows.invoice.some((row) => (
    row.sourceKind === "oa_attachment_invoice"
    && !rowExpenseItemIds(row).some((itemId) => expenseItemIds.has(itemId))
  ));
  const segmentedPaneIds = (["bank", "invoice"] as const).filter((paneId) => (
    !(paneId === "bank" && hasExpenseClaimItems && sourceGroup.rows.oa.length === 1)
    && (
      (paneId === "invoice" && hasUnassignedOaAttachmentInvoices)
      || Array.from(alignedRowIdsByPane[paneId].values()).some((rowIds) => (
        rowIds.length > 0 && rowIds.every((rowId) => displayRowsByPane[paneId].has(rowId))
      ))
    )
  ));
  if (segmentedPaneIds.length === 0 && !hasExpenseClaimItems) {
    return null;
  }

  const matchedRowIdsByPane = {
    bank: new Set<string>(),
    invoice: new Set<string>(),
  };
  const ownedRowIdsByPane = {
    bank: new Set(segments.flatMap((segment) => segment.rows.bank.map((row) => row.id))),
    invoice: new Set(segments.flatMap((segment) => segment.rows.invoice.map((row) => row.id))),
  };
  const displaySegments: WorkbenchGroupDisplaySegment[] = [];

  segments.forEach((segment) => {
    const alignedRows = {
      bank: [] as WorkbenchRecord[],
      invoice: [] as WorkbenchRecord[],
    };
    segmentedPaneIds.forEach((paneId) => {
      const rowIds = alignedRowIdsByPane[paneId].get(segment.id) ?? [];
      const rows = rowIds.map((rowId) => displayRowsByPane[paneId].get(rowId));
      if (rows.length > 0 && rows.every((row): row is WorkbenchRecord => Boolean(row))) {
        alignedRows[paneId].push(...rows);
        rows.forEach((row) => matchedRowIdsByPane[paneId].add(row.id));
      }
    });
    displaySegments.push({
      id: segment.id,
      rows: {
        oa: segment.rows.oa,
        bank: alignedRows.bank,
        invoice: alignedRows.invoice,
      },
    });

    segmentedPaneIds.forEach((paneId) => {
      const residualRows = segment.rows[paneId].filter((row) => !matchedRowIdsByPane[paneId].has(row.id));
      if (residualRows.length === 0) {
        return;
      }
      displaySegments.push({
        id: `${segment.id}:${paneId}:residual`,
        rows: {
          oa: [],
          bank: paneId === "bank" ? residualRows : [],
          invoice: paneId === "invoice" ? residualRows : [],
        },
      });
    });
  });

  segmentedPaneIds.forEach((paneId) => {
    const residualRows = group.rows[paneId].filter(
      (row) => !matchedRowIdsByPane[paneId].has(row.id) && !ownedRowIdsByPane[paneId].has(row.id),
    );
    if (residualRows.length === 0) {
      return;
    }
    displaySegments.push({
      id: `${group.id}:${paneId}:residual`,
      rows: {
        oa: [],
        bank: paneId === "bank" ? residualRows : [],
        invoice: paneId === "invoice" ? residualRows : [],
      },
    });
  });

  return {
    segments: displaySegments,
    segmentedPaneIds: ["oa", ...segmentedPaneIds],
  };
}

function buildWorkbenchGroupSourceSegments(
  group: WorkbenchRelationGroup,
): WorkbenchGroupDisplaySegment[] | null {
  if (group.displayMode === "collapsed_summary" || group.rows.oa.length === 0) {
    return null;
  }
  const hasExpenseClaimItems = group.rows.oa.some((oaRow) => shouldExpandExpenseClaim(
    oaRow,
    group.rows.invoice.filter((invoiceRow) => normalizeSourceOaId(invoiceRow.sourceOaId) === oaRow.id),
  ));
  if (group.rows.oa.length < 2 && !hasExpenseClaimItems) {
    return null;
  }

  const oaRowsById = new Map(group.rows.oa.map((row) => [row.id, row]));
  const bankRowsBySourceOaId = new Map<string, WorkbenchRecord[]>();
  const invoicesBySourceOaId = new Map<string, WorkbenchRecord[]>();

  group.rows.bank.forEach((bankRow) => {
    const sourceOaId = normalizeSourceOaId(bankRow.sourceOaId);
    if (sourceOaId && oaRowsById.has(sourceOaId)) {
      const rows = bankRowsBySourceOaId.get(sourceOaId) ?? [];
      rows.push(bankRow);
      bankRowsBySourceOaId.set(sourceOaId, rows);
    }
  });

  group.rows.invoice.forEach((invoiceRow) => {
    const sourceOaId = normalizeSourceOaId(invoiceRow.sourceOaId);
    if (sourceOaId && oaRowsById.has(sourceOaId)) {
      const rows = invoicesBySourceOaId.get(sourceOaId) ?? [];
      rows.push(invoiceRow);
      invoicesBySourceOaId.set(sourceOaId, rows);
    }
  });

  const parentSegments = group.rows.oa.map((oaRow) => ({
    id: oaRow.id,
    rows: {
      oa: [oaRow],
      bank: bankRowsBySourceOaId.get(oaRow.id) ?? [],
      invoice: invoicesBySourceOaId.get(oaRow.id) ?? [],
    },
  }));

  const segments = parentSegments.flatMap(expandExpenseClaimSegment);
  if (segments.length < 2) {
    return null;
  }
  return segments;
}

function findAlignedRowIdsBySegment(
  group: WorkbenchRelationGroup,
  segments: WorkbenchGroupDisplaySegment[],
  paneId: WorkbenchRecordType,
): Map<string, string[]> {
  const alignedRowsBySegmentId = new Map<string, string[]>();
  const explicitlyOwnedRowIds = new Set(segments.flatMap((segment) => segment.rows[paneId].map((row) => row.id)));

  segments.forEach((segment) => {
    const rows = segment.rows[paneId];
    if (segment.rows.oa.length === 0 && rows.length > 0) {
      alignedRowsBySegmentId.set(segment.id, rows.map((row) => row.id));
      return;
    }
    const segmentItemIds = new Set(
      segment.rows.oa
        .filter((row) => row.displayRole === "expense-claim-item")
        .map((row) => row.sourceExpenseItemIds?.[0] ?? "")
        .filter(Boolean),
    );
    const hasExplicitExpenseItemOwnership = paneId === "invoice"
      && segmentItemIds.size > 0
      && rows.length > 0
      && rows.every((row) => rowExpenseItemIds(row).some((itemId) => segmentItemIds.has(itemId)));
    if (hasExplicitExpenseItemOwnership) {
      alignedRowsBySegmentId.set(segment.id, rows.map((row) => row.id));
      return;
    }
    const targetAmount = segmentTargetAmountCents(segment);
    const rowAmounts = rows.map(workbenchComparableAmountCents);
    const canAlignExplicitBankFanout = paneId === "bank"
      && rows.length > 1
      && segment.rows.oa.length === 1
      && segment.rows.oa[0].displayRole === undefined;
    if (
      (rows.length === 1 || canAlignExplicitBankFanout)
      && targetAmount > 0
      && rowAmounts.every((amount) => amount > 0)
      && rowAmounts.reduce((total, amount) => total + amount, 0) === targetAmount
    ) {
      alignedRowsBySegmentId.set(segment.id, rows.map((row) => row.id));
    }
  });

  const fallbackTargetsByAmount = new Map<number, WorkbenchGroupDisplaySegment[]>();
  segments.forEach((segment) => {
    if (segment.rows[paneId].length > 0) {
      return;
    }
    const amount = segmentTargetAmountCents(segment);
    if (amount <= 0) {
      return;
    }
    const targets = fallbackTargetsByAmount.get(amount) ?? [];
    targets.push(segment);
    fallbackTargetsByAmount.set(amount, targets);
  });

  const fallbackRowsByAmount = new Map<number, WorkbenchRecord[]>();
  group.rows[paneId].forEach((row) => {
    if (explicitlyOwnedRowIds.has(row.id) || !canUseAmountFallback(group, paneId, row)) {
      return;
    }
    const amount = workbenchComparableAmountCents(row);
    if (amount <= 0) {
      return;
    }
    const rows = fallbackRowsByAmount.get(amount) ?? [];
    rows.push(row);
    fallbackRowsByAmount.set(amount, rows);
  });

  fallbackTargetsByAmount.forEach((targets, amount) => {
    const rows = fallbackRowsByAmount.get(amount) ?? [];
    if (targets.length === 1 && rows.length === 1) {
      alignedRowsBySegmentId.set(targets[0].id, [rows[0].id]);
    }
  });

  return alignedRowsBySegmentId;
}

function segmentTargetAmountCents(segment: WorkbenchGroupDisplaySegment) {
  if (segment.rows.oa.length === 0) {
    return 0;
  }
  if (segment.rows.oa.every((row) => row.displayRole === "expense-claim-item")) {
    return segment.rows.oa.reduce(
      (total, row) => total + parseWorkbenchAmountCents(row.tableValues.amount ?? ""),
      0,
    );
  }
  return workbenchComparableAmountCents(segment.rows.oa[0]);
}

function canUseAmountFallback(
  group: WorkbenchRelationGroup,
  paneId: WorkbenchRecordType,
  row: WorkbenchRecord,
) {
  if (paneId === "invoice" && row.sourceKind === "oa_attachment_invoice") {
    return false;
  }
  const direction = group.amountCheck?.direction;
  if (!direction || direction === "unknown") {
    return false;
  }
  if (paneId !== "bank") {
    return true;
  }
  const expectedDirection = direction === "receipt" ? "收入" : "支出";
  return row.tableValues.direction === expectedDirection;
}

function expandExpenseClaimSegment(segment: WorkbenchGroupDisplaySegment): WorkbenchGroupDisplaySegment[] {
  const parent = segment.rows.oa[0];
  const items = parent?.expenseItems ?? [];
  if (!parent || !shouldExpandExpenseClaim(parent, segment.rows.invoice)) {
    return [segment];
  }

  const itemIds = new Set(items.map((item) => item.id));
  const itemOrder = new Map(items.map((item, index) => [item.id, index]));
  const linkedInvoiceRows = segment.rows.invoice.map((row) => ({
    row,
    itemIds: rowExpenseItemIds(row).filter((itemId) => itemIds.has(itemId)),
  }));
  const residualInvoices = linkedInvoiceRows
    .filter(({ itemIds: linkedItemIds }) => linkedItemIds.length === 0)
    .map(({ row }) => row);
  const invoicesByItemId = new Map<string, WorkbenchRecord[]>();
  linkedInvoiceRows.forEach(({ row, itemIds: linkedItemIds }) => {
    linkedItemIds.forEach((itemId) => {
      const rows = invoicesByItemId.get(itemId) ?? [];
      rows.push(row);
      invoicesByItemId.set(itemId, rows);
    });
  });
  const summaryRow: WorkbenchRecord = {
    ...parent,
    displayRole: "expense-claim-summary",
    tableValues: {
      ...parent.tableValues,
      projectName: expenseItemSummaryLabel(items),
      amount: "—",
    },
  };
  const remainingItemIds = new Set(items.map((item) => item.id));
  const itemSegments: WorkbenchGroupDisplaySegment[] = [];
  while (remainingItemIds.size > 0) {
    const firstItemId = [...remainingItemIds].sort(
      (left, right) => (itemOrder.get(left) ?? 0) - (itemOrder.get(right) ?? 0),
    )[0];
    const pendingItemIds = [firstItemId];
    const componentItemIds = new Set<string>();
    const componentInvoiceRows = new Map<string, WorkbenchRecord>();
    while (pendingItemIds.length > 0) {
      const itemId = pendingItemIds.pop();
      if (!itemId || componentItemIds.has(itemId)) {
        continue;
      }
      componentItemIds.add(itemId);
      (invoicesByItemId.get(itemId) ?? []).forEach((invoiceRow) => {
        componentInvoiceRows.set(invoiceRow.id, invoiceRow);
        rowExpenseItemIds(invoiceRow)
          .filter((linkedItemId) => itemIds.has(linkedItemId) && !componentItemIds.has(linkedItemId))
          .forEach((linkedItemId) => pendingItemIds.push(linkedItemId));
      });
    }
    componentItemIds.forEach((itemId) => remainingItemIds.delete(itemId));
    const componentItems = items.filter((item) => componentItemIds.has(item.id));
    const componentId = componentItems.map((item) => item.id).join("+");
    itemSegments.push({
      id: componentId,
      rows: {
        oa: componentItems.map((item) => ({
          ...parent,
          amount: item.amount,
          expenseType: item.expenseType,
          sourceExpenseItemIds: [item.id],
          displayRole: "expense-claim-item" as const,
          ...(item.workbenchAnomalies?.some((anomaly) => ![
            "oa_invoice_attachment_absent",
            "oa_invoice_attachment_unparsed",
          ].includes(anomaly.code)) ? {
            workbenchAnomalies: item.workbenchAnomalies.filter((anomaly) => ![
              "oa_invoice_attachment_absent",
              "oa_invoice_attachment_unparsed",
            ].includes(anomaly.code)),
          } : {}),
          tableValues: {
            ...parent.tableValues,
            applicant: "—",
            applicationTime: "—",
            applicationType: "—",
            projectName: item.projectName,
            amount: item.amount,
            counterparty: "—",
            reason: [
              item.feeContent ? `费用内容：${item.feeContent}` : "",
              item.feeDescription ? `费用说明：${item.feeDescription}` : "",
            ].filter(Boolean).join("；") || "—",
            reconciliationStatus: "—",
          },
          availableActions: [],
        })),
        bank: [],
        invoice: [
          ...Array.from(componentInvoiceRows.values()),
          ...componentItems.flatMap((item) => supportingDocumentRows(parent, item)),
          ...(componentInvoiceRows.size > 0 ? [] : missingInvoicePlaceholder(parent, componentItems[0])),
        ],
      },
    });
  }

  const expandedSegments = [
    {
      id: `${parent.id}:summary`,
      rows: {
        oa: [summaryRow],
        bank: segment.rows.bank,
        invoice: [],
      },
    },
    ...itemSegments,
  ];
  if (residualInvoices.length > 0) {
    expandedSegments.push({
      id: `${parent.id}:invoice:unassigned`,
      rows: { oa: [], bank: [], invoice: residualInvoices },
    });
  }
  return expandedSegments;
}

function missingInvoicePlaceholder(
  parent: WorkbenchRecord,
  item: NonNullable<WorkbenchRecord["expenseItems"]>[number],
) {
  const anomaly = item.workbenchAnomalies?.find((candidate) => [
    "oa_invoice_attachment_absent",
    "oa_invoice_attachment_unparsed",
  ].includes(candidate.code));
  if (!anomaly || ![
    "oa_invoice_attachment_absent",
    "oa_invoice_attachment_unparsed",
  ].includes(anomaly.code)) {
    return [];
  }
  const label = anomaly.code === "oa_invoice_attachment_unparsed"
    ? "OA发票附件未解析"
    : "无OA附件";
  return [{
    id: `${parent.id}:missing-invoice:${item.id}`,
    caseId: parent.caseId,
    recordType: "invoice" as const,
    sourceKind: "oa_attachment_unknown" as const,
    sourceOaId: parent.id,
    sourceExpenseItemIds: [item.id],
    externalUrl: "/oa/#/normal/32?formId=32",
    label,
    status: "待处理",
    statusCode: anomaly.code,
    statusTone: "danger",
    exceptionHandled: false,
    amount: "—",
    counterparty: "—",
    tableValues: {
      sellerName: "—",
      sellerTaxId: "—",
      buyerName: "—",
      buyerTaxId: "—",
      grossAmount: "—",
      amount: "—",
    },
    detailFields: [],
    actionVariant: "detail-only" as const,
    availableActions: anomaly.code === "oa_invoice_attachment_unparsed" ? ["enter_invoice"] : [],
    workbenchAnomalies: [anomaly],
    displayOnly: true,
  }];
}

function supportingDocumentRows(
  parent: WorkbenchRecord,
  item: NonNullable<WorkbenchRecord["expenseItems"]>[number],
): WorkbenchRecord[] {
  return (item.supportingDocuments ?? []).map((document) => ({
    id: `supporting-document:${document.id}`,
    caseId: parent.caseId,
    recordType: "invoice",
    sourceKind: "oa_supporting_document",
    sourceOaId: parent.id,
    sourceExpenseItemIds: [item.id],
    externalUrl: document.contentUrl,
    label: document.fileName,
    status: "补充凭证",
    statusCode: "supporting_document",
    statusTone: "info",
    exceptionHandled: true,
    amount: "—",
    counterparty: "—",
    tableValues: {
      sellerName: document.fileName,
      sellerTaxId: "补充凭证（不进入发票池）",
      buyerName: "—",
      buyerTaxId: "—",
      grossAmount: "—",
      amount: "—",
      issueDate: document.createdAt,
    },
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: [],
    displayOnly: true,
  }));
}

function hasExpandableExpenseItems(row: WorkbenchRecord) {
  const items = row.expenseItems ?? [];
  return items.length > 1 || items.some((item) => [
    "oa_invoice_attachment_absent",
    "oa_invoice_attachment_unparsed",
  ].some((code) => item.workbenchAnomalies?.some((anomaly) => anomaly.code === code)));
}

function shouldExpandExpenseClaim(parent: WorkbenchRecord, invoiceRows: WorkbenchRecord[]) {
  return (parent.expenseItems?.length ?? 0) > 0 && (
    hasExpandableExpenseItems(parent)
    || invoiceRows.some((row) => row.sourceKind === "oa_attachment_invoice")
  );
}

function rowExpenseItemIds(row: WorkbenchRecord) {
  return Array.from(new Set((row.sourceExpenseItemIds ?? []).map((itemId) => itemId.trim()).filter(Boolean)));
}

function expenseItemSummaryLabel(items: NonNullable<WorkbenchRecord["expenseItems"]>) {
  const projectNames = new Set(
    items
      .map((item) => item.projectName.trim())
      .filter((projectName) => projectName && projectName !== "--" && projectName !== "—"),
  );
  return projectNames.size > 1 ? `多个项目 · ${projectNames.size}` : `多个明细 · ${items.length}`;
}

export function mergeWorkbenchGroupsById(
  currentGroups: WorkbenchRelationGroup[],
  incomingGroups: WorkbenchRelationGroup[],
): WorkbenchRelationGroup[] {
  const seenGroupIds = new Set(currentGroups.map((group) => group.id));
  const mergedGroups = [...currentGroups];
  incomingGroups.forEach((group) => {
    if (seenGroupIds.has(group.id)) {
      return;
    }
    seenGroupIds.add(group.id);
    mergedGroups.push(group);
  });
  return mergedGroups;
}

export function buildWorkbenchServerPageQuery(state: WorkbenchZoneDisplayState): WorkbenchGroupsPageQuery {
  const query: WorkbenchGroupsPageQuery = {};
  const search = normalizeMoneySearchQuery(state.searchQuery);
  if (search) {
    query.search = search;
  }
  const sortPaneId = workbenchPaneIds.find((paneId) => state.sortByPane[paneId]);
  if (sortPaneId) {
    const direction = state.sortByPane[sortPaneId];
    if (direction) {
      query.sort = `${sortPaneId}:${direction}`;
    }
  }
  const filtersByPaneAndColumn = normalizeServerColumnFilters(state.filtersByPaneAndColumn);
  if (Object.keys(filtersByPaneAndColumn).length > 0) {
    query.filtersByPaneAndColumn = filtersByPaneAndColumn;
  }
  const timeFilterByPane = normalizeServerTimeFilters(state.timeFilterByPane);
  if (Object.keys(timeFilterByPane).length > 0) {
    query.timeFilterByPane = timeFilterByPane;
  }
  return query;
}

export function hasWorkbenchServerPageCriteria(query: WorkbenchGroupsPageQuery) {
  return Boolean(
    query.search
    || query.sort
    || (query.filtersByPaneAndColumn && Object.keys(query.filtersByPaneAndColumn).length > 0)
    || (query.timeFilterByPane && Object.keys(query.timeFilterByPane).length > 0),
  );
}

function normalizeServerColumnFilters(
  filtersByPaneAndColumn: WorkbenchZoneDisplayState["filtersByPaneAndColumn"],
): NonNullable<WorkbenchGroupsPageQuery["filtersByPaneAndColumn"]> {
  const result: NonNullable<WorkbenchGroupsPageQuery["filtersByPaneAndColumn"]> = {};
  workbenchPaneIds.forEach((paneId) => {
    const paneFilters = filtersByPaneAndColumn[paneId] ?? {};
    const cleanedEntries = Object.entries(paneFilters)
      .map(([columnKey, selectedValues]) => [
        columnKey,
        Array.from(new Set(selectedValues.map((value) => value.trim()).filter(Boolean))),
      ] as const)
      .filter(([, selectedValues]) => selectedValues.length > 0);
    if (cleanedEntries.length > 0) {
      result[paneId] = Object.fromEntries(cleanedEntries);
    }
  });
  return result;
}

function normalizeServerTimeFilters(
  timeFilterByPane: WorkbenchZoneDisplayState["timeFilterByPane"],
): NonNullable<WorkbenchGroupsPageQuery["timeFilterByPane"]> {
  const result: NonNullable<WorkbenchGroupsPageQuery["timeFilterByPane"]> = {};
  workbenchPaneIds.forEach((paneId) => {
    const filter = timeFilterByPane[paneId] ?? { mode: "none" };
    if (filter.mode === "year" && filter.year.trim()) {
      result[paneId] = { mode: "year", year: filter.year.trim() };
    }
    if (filter.mode === "month" && filter.month.trim()) {
      result[paneId] = { mode: "month", month: filter.month.trim() };
    }
  });
  return result;
}

function normalizeSourceOaId(value: string | undefined) {
  const normalizedValue = value?.trim() ?? "";
  if (!normalizedValue || normalizedValue === "--" || normalizedValue === "—") {
    return null;
  }
  return normalizedValue.replace(/:item:.*$/, "");
}

export function countWorkbenchGroupRows(group: WorkbenchRelationGroup): number {
  return workbenchPaneIds.reduce((total, paneId) => {
    const paneCount = group.rowCounts?.[paneId];
    if (typeof paneCount === "number") {
      return total + paneCount;
    }
    const collapsedPaneCount = group.collapsedRowCounts?.[paneId];
    if (typeof collapsedPaneCount === "number") {
      return total + collapsedPaneCount;
    }
    const collapsedPaneRows = group.collapsedRows?.[paneId] ?? [];
    if (collapsedPaneRows.length > 0) {
      return total + collapsedPaneRows.length;
    }
    return total + group.rows[paneId].length;
  }, 0);
}

export function countWorkbenchGroupsRows(groups: WorkbenchRelationGroup[]): number {
  return groups.reduce((total, group) => total + countWorkbenchGroupRows(group), 0);
}

export function resolveWorkbenchActivePane(
  state: WorkbenchZoneDisplayState,
  preferredPaneId?: WorkbenchRecordType | null,
): WorkbenchRecordType | null {
  if (preferredPaneId && paneHasWorkbenchCriteria(state, preferredPaneId)) {
    return preferredPaneId;
  }

  return (["oa", "bank", "invoice"] as const).find((paneId) => paneHasWorkbenchCriteria(state, paneId)) ?? null;
}

function groupMatchesPaneCriteria(group: WorkbenchRelationGroup, state: WorkbenchZoneDisplayState) {
  const normalizedSearchQuery = normalizeWorkbenchSearchText(state.searchQuery);
  if (
    normalizedSearchQuery
    && !workbenchPaneIds.some((paneId) =>
      getWorkbenchGroupPaneRowsForCriteria(group, paneId).some((row) => matchesWorkbenchRowText(row, normalizedSearchQuery)),
    )
  ) {
    return false;
  }

  const activePanes = workbenchPaneIds.filter((paneId) => paneHasWorkbenchRowCriteria(state, paneId));
  if (activePanes.length === 0) {
    return true;
  }

  return activePanes.every((paneId) => {
    const paneFilters = state.filtersByPaneAndColumn[paneId] ?? {};
    const paneTimeFilter = state.timeFilterByPane[paneId] ?? { mode: "none" };
    return getWorkbenchGroupPaneRowsForCriteria(group, paneId).some((row) =>
      matchesWorkbenchRow(row, paneId, "", paneFilters, paneTimeFilter),
    );
  });
}

function isCollapsedSummaryGroup(group: WorkbenchRelationGroup) {
  return group.displayMode === "collapsed_summary";
}

function applyPaneCriteriaToGroup(
  group: WorkbenchRelationGroup,
  state: WorkbenchZoneDisplayState,
): WorkbenchRelationGroup {
  const rows = Object.fromEntries(
    workbenchPaneIds.map((paneId) => {
      const paneFilters = state.filtersByPaneAndColumn[paneId] ?? {};
      const paneTimeFilter = state.timeFilterByPane[paneId] ?? { mode: "none" };

      if (!paneHasWorkbenchRowCriteria(state, paneId)) {
        return [paneId, group.rows[paneId]];
      }

      return [
        paneId,
        group.rows[paneId].filter((row) => matchesWorkbenchRow(row, paneId, "", paneFilters, paneTimeFilter)),
      ];
    }),
  ) as WorkbenchPaneRows;

  return {
    ...group,
    rows,
  };
}

function groupHasRowsInCriteriaPanes(group: WorkbenchRelationGroup, state: WorkbenchZoneDisplayState) {
  return workbenchPaneIds.every((paneId) => !paneHasWorkbenchRowCriteria(state, paneId) || group.rows[paneId].length > 0);
}

function matchesWorkbenchRow(
  row: WorkbenchRecord,
  paneId: WorkbenchRecordType,
  normalizedQuery: string,
  activeFilters: Record<string, string[]>,
  timeFilter: WorkbenchPaneTimeFilter,
) {
  if (!matchesWorkbenchTimeFilter(row, paneId, timeFilter)) {
    return false;
  }

  if (normalizedQuery) {
    if (!matchesWorkbenchRowText(row, normalizedQuery)) {
      return false;
    }
  }

  return Object.entries(activeFilters).every(([columnKey, selectedValues]) => {
    if (selectedValues.length === 0) {
      return true;
    }
    if (row.recordType === "bank" && columnKey === "amount") {
      return matchesBankAmountFilters(row, selectedValues);
    }
    if (row.recordType === "oa" && columnKey === "applicant") {
      return matchesOaApplicantFilters(row, selectedValues);
    }
    if (row.recordType === "oa" && columnKey === "projectName") {
      return matchesOaProjectFilters(row, selectedValues);
    }
    const currentValue = row.tableValues[columnKey] ?? "";
    return selectedValues.some((value) => value === currentValue);
  });
}

function getWorkbenchGroupPaneRowsForCriteria(group: WorkbenchRelationGroup, paneId: WorkbenchRecordType) {
  return [
    ...group.rows[paneId],
    ...(group.collapsedRows?.[paneId] ?? []),
  ];
}

function groupedFilterValues(selectedValues: string[], prefix: string) {
  const marker = `${prefix}:`;
  return selectedValues
    .filter((value) => value.startsWith(marker))
    .map((value) => value.slice(marker.length));
}

function matchesEverySelectedGroup(
  selectedValues: string[],
  matchers: Record<string, (value: string) => boolean>,
) {
  const recognizedCount = Object.keys(matchers).reduce(
    (count, prefix) => count + groupedFilterValues(selectedValues, prefix).length,
    0,
  );
  if (recognizedCount !== selectedValues.length) {
    return false;
  }
  return Object.entries(matchers).every(([prefix, matcher]) => {
    const values = groupedFilterValues(selectedValues, prefix);
    return values.length === 0 || values.some(matcher);
  });
}

function matchesBankAmountFilters(row: WorkbenchRecord, selectedValues: string[]) {
  const accountLast4 = row.tableValues.paymentAccount.match(/(\d{4})\s*$/)?.[1] ?? "";
  return matchesEverySelectedGroup(selectedValues, {
    direction: (value) => (
      (value === "expense" && row.tableValues.direction === "支出")
      || (value === "income" && row.tableValues.direction === "收入")
    ),
    account: (value) => value === accountLast4,
    bankTag: (value) => value === row.categoryCode,
  });
}

function matchesOaApplicantFilters(row: WorkbenchRecord, selectedValues: string[]) {
  const rawApplicationType = row.tableValues.applicationType;
  const applicationType = ["payment_request", "供应商付款申请"].includes(rawApplicationType)
    ? "支付申请"
    : rawApplicationType === "expense_claim"
      ? "日常报销"
      : rawApplicationType;
  return matchesEverySelectedGroup(selectedValues, {
    oaType: (value) => value === applicationType,
    workflow: (value) => value === row.tableValues.workflowStatus,
    applicant: (value) => value === "__workbench_missing__"
      ? !row.tableValues.applicant || ["--", "—"].includes(row.tableValues.applicant)
      : value === row.tableValues.applicant,
  });
}

function matchesOaProjectFilters(row: WorkbenchRecord, selectedValues: string[]) {
  const items = row.expenseItems?.length
    ? row.expenseItems
    : [{
      projectName: row.tableValues.projectName,
      expenseType: row.expenseType ?? "",
    }];
  return items.some((item) => matchesEverySelectedGroup(selectedValues, {
    expenseType: (value) => value === (item.expenseType ?? ""),
    project: (value) => value === "__workbench_missing__"
      ? !item.projectName || ["--", "—"].includes(item.projectName)
      : value === item.projectName,
  }));
}

function normalizeWorkbenchSearchText(value: string) {
  return normalizeMoneySearchQuery(value).toLocaleLowerCase("zh-CN");
}

export function workbenchRowMatchesUnifiedSearch(row: WorkbenchRecord, query: string) {
  const normalizedQuery = normalizeWorkbenchSearchText(query);
  return normalizedQuery ? matchesWorkbenchRowText(row, normalizedQuery) : false;
}

function matchesWorkbenchRowText(row: WorkbenchRecord, normalizedQuery: string) {
  const tableValues = Object.entries(row.tableValues)
    .filter(([key]) => !key.startsWith("__detail:"))
    .map(([, value]) => value);
  const bankTextValues = (row.bankTextFields ?? []).flatMap((field) => [field.label, field.value]);
  const displayAliases = workbenchRowDisplaySearchAliases(row);
  const normalizedHaystack = normalizeWorkbenchSearchText(
    [
      row.label,
      row.status,
      row.amount,
      row.counterparty,
      row.categoryLabel,
      ...tableValues,
      ...bankTextValues,
      ...displayAliases,
      ...(row.tags ?? []),
    ].join(" "),
  );
  return (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalizedQuery)
    ? normalizedHaystack.replace(/,/g, "")
    : normalizedHaystack
  ).includes(normalizedQuery);
}

function workbenchRowDisplaySearchAliases(row: WorkbenchRecord) {
  if (row.recordType === "bank") {
    return [compactWorkbenchBankAccountLabel(row.tableValues.paymentAccount ?? "")];
  }
  if (row.recordType === "invoice") {
    const invoiceType = row.tableValues.invoiceType ?? "";
    const flowLabel = workbenchInvoiceFlowLabel(invoiceType);
    const sourceLabel = flowLabel || row.sourceKind ? workbenchInvoiceSourceLabel(row.sourceKind) : null;
    return [flowLabel, sourceLabel].filter((value): value is string => Boolean(value));
  }
  return [];
}

export function compactWorkbenchBankAccountLabel(value: string) {
  const normalizedValue = value.replace(/\s+/g, " ").trim();
  for (const [bankName, shortName] of Object.entries(compactBankNameByPrefix)) {
    if (normalizedValue === bankName) {
      return shortName;
    }
    if (normalizedValue.startsWith(`${bankName} `)) {
      return `${shortName}${normalizedValue.slice(bankName.length)}`;
    }
  }
  return value;
}

export function workbenchInvoiceFlowLabel(invoiceType: string) {
  const normalized = invoiceType.trim().toLowerCase();
  if (normalized.includes("销") || normalized.includes("output") || normalized.includes("sale")) {
    return "销";
  }
  if (normalized.includes("进") || normalized.includes("input") || normalized.includes("purchase")) {
    return "进";
  }
  return null;
}

export function workbenchInvoiceSourceLabel(sourceKind: WorkbenchSourceKind | undefined) {
  if (sourceKind === "etc_invoice_summary") {
    return "ETC批次";
  }
  if (sourceKind === "etc_invoice") {
    return "ETC";
  }
  if (sourceKind === "oa_attachment_invoice") {
    return "OA附件";
  }
  if (sourceKind === "oa_attachment_payment_receipt") {
    return "付款凭证";
  }
  if (sourceKind === "oa_supporting_document") {
    return "补充凭证";
  }
  if (sourceKind === "oa_attachment_unknown") {
    return null;
  }
  return "人工导入";
}

function paneHasWorkbenchCriteria(state: WorkbenchZoneDisplayState, paneId: WorkbenchRecordType) {
  if ((state.timeFilterByPane[paneId] ?? { mode: "none" }).mode !== "none") {
    return true;
  }

  if (state.sortByPane[paneId]) {
    return true;
  }

  return Object.values(state.filtersByPaneAndColumn[paneId] ?? {}).some((values) => values.length > 0);
}

function paneHasWorkbenchRowCriteria(state: WorkbenchZoneDisplayState, paneId: WorkbenchRecordType) {
  if ((state.timeFilterByPane[paneId] ?? { mode: "none" }).mode !== "none") {
    return true;
  }

  return Object.values(state.filtersByPaneAndColumn[paneId] ?? {}).some((values) => values.length > 0);
}

function sortWorkbenchGroups(
  groups: WorkbenchRelationGroup[],
  paneId: WorkbenchRecordType,
  direction: "asc" | "desc",
) {
  return groups
    .map((group, index) => ({
      group,
      index,
      sortKey: resolveWorkbenchGroupSortKey(group, paneId, direction),
    }))
    .sort((left, right) => {
      if (!left.sortKey && !right.sortKey) {
        return left.index - right.index;
      }
      if (!left.sortKey) {
        return 1;
      }
      if (!right.sortKey) {
        return -1;
      }

      const comparison = left.sortKey.localeCompare(right.sortKey, "zh-CN");
      if (comparison === 0) {
        return left.index - right.index;
      }
      return direction === "asc" ? comparison : -comparison;
    })
    .map(({ group }) => group);
}

function resolveWorkbenchGroupSortKey(
  group: WorkbenchRelationGroup,
  paneId: WorkbenchRecordType,
  direction: "asc" | "desc",
) {
  const values = group.rows[paneId]
    .map((row) => resolveWorkbenchRowSortValue(row, paneId))
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => left.localeCompare(right, "zh-CN"));

  if (values.length === 0) {
    return null;
  }

  return direction === "asc" ? values[0] : values[values.length - 1];
}

function resolveWorkbenchRowSortValue(row: WorkbenchRecord, paneId: WorkbenchRecordType) {
  if (paneId === "oa") {
    return row.tableValues.applicationTime ?? null;
  }
  if (paneId === "bank") {
    return row.tableValues.transactionTime ?? null;
  }
  if (paneId === "invoice") {
    return row.tableValues.issueDate ?? null;
  }
  return null;
}

function matchesWorkbenchTimeFilter(
  row: WorkbenchRecord,
  paneId: WorkbenchRecordType,
  timeFilter: WorkbenchPaneTimeFilter,
) {
  if (timeFilter.mode === "none") {
    return true;
  }

  const timeValue = resolveWorkbenchRowSortValue(row, paneId);
  if (!timeValue) {
    return false;
  }

  if (timeFilter.mode === "year") {
    return timeValue.startsWith(`${timeFilter.year}-`);
  }

  return timeValue.startsWith(timeFilter.month);
}
