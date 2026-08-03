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

  const exactRowIdsByPane = {
    bank: findExactRowIdsBySegment(sourceGroup, sourceSegments, "bank"),
    invoice: findExactRowIdsBySegment(sourceGroup, sourceSegments, "invoice"),
  };
  const displayRowsByPane = {
    bank: new Map(group.rows.bank.map((row) => [row.id, row])),
    invoice: new Map(group.rows.invoice.map((row) => [row.id, row])),
  };
  const segmentedPaneIds = (["bank", "invoice"] as const).filter((paneId) => (
    Array.from(exactRowIdsByPane[paneId].values()).some((rowId) => displayRowsByPane[paneId].has(rowId))
  ));
  const hasExpenseClaimItems = segments.some(
    (segment) => segment.rows.oa[0]?.displayRole === "expense-claim-summary",
  );
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
    const exactRows = {
      bank: [] as WorkbenchRecord[],
      invoice: [] as WorkbenchRecord[],
    };
    segmentedPaneIds.forEach((paneId) => {
      const rowId = exactRowIdsByPane[paneId].get(segment.id);
      const row = rowId ? displayRowsByPane[paneId].get(rowId) : undefined;
      if (row) {
        exactRows[paneId].push(row);
        matchedRowIdsByPane[paneId].add(row.id);
      }
    });
    displaySegments.push({
      id: segment.id,
      rows: {
        oa: segment.rows.oa,
        bank: exactRows.bank,
        invoice: exactRows.invoice,
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
  const hasExpenseClaimItems = group.rows.oa.some(hasMultiProjectExpenseItems);
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

function findExactRowIdsBySegment(
  group: WorkbenchRelationGroup,
  segments: WorkbenchGroupDisplaySegment[],
  paneId: WorkbenchRecordType,
): Map<string, string> {
  const exactRowsBySegmentId = new Map<string, string>();
  const explicitlyOwnedRowIds = new Set(segments.flatMap((segment) => segment.rows[paneId].map((row) => row.id)));

  segments.forEach((segment) => {
    const rows = segment.rows[paneId];
    const targetAmount = segmentTargetAmountCents(segment);
    if (
      rows.length === 1
      && targetAmount > 0
      && workbenchComparableAmountCents(rows[0]) === targetAmount
    ) {
      exactRowsBySegmentId.set(segment.id, rows[0].id);
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
      exactRowsBySegmentId.set(targets[0].id, rows[0].id);
    }
  });

  return exactRowsBySegmentId;
}

function segmentTargetAmountCents(segment: WorkbenchGroupDisplaySegment) {
  const row = segment.rows.oa[0];
  if (!row) {
    return 0;
  }
  if (row.displayRole === "expense-claim-item") {
    return parseWorkbenchAmountCents(row.tableValues.amount ?? "");
  }
  return workbenchComparableAmountCents(row);
}

function canUseAmountFallback(
  group: WorkbenchRelationGroup,
  paneId: WorkbenchRecordType,
  row: WorkbenchRecord,
) {
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
  if (!parent || !hasMultiProjectExpenseItems(parent)) {
    return [segment];
  }

  const itemIds = new Set(items.map((item) => item.id));
  const invoicesByItemId = new Map<string, WorkbenchRecord[]>();
  segment.rows.invoice.forEach((row) => {
    if (!row.sourceExpenseItemId || !itemIds.has(row.sourceExpenseItemId)) {
      return;
    }
    const rows = invoicesByItemId.get(row.sourceExpenseItemId) ?? [];
    rows.push(row);
    invoicesByItemId.set(row.sourceExpenseItemId, rows);
  });
  const summaryInvoices = segment.rows.invoice.filter(
    (row) => !row.sourceExpenseItemId || !itemIds.has(row.sourceExpenseItemId),
  );
  const summaryRow: WorkbenchRecord = {
    ...parent,
    displayRole: "expense-claim-summary",
    tableValues: {
      ...parent.tableValues,
      projectName: `多个项目 · ${new Set(items.map((item) => item.projectName)).size}`,
      amount: "—",
    },
  };
  const itemSegments = items.map((item) => ({
    id: item.id,
    rows: {
      oa: [{
        ...parent,
        amount: item.amount,
        displayRole: "expense-claim-item" as const,
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
      }],
      bank: [],
      invoice: invoicesByItemId.get(item.id) ?? [],
    },
  }));

  return [
    {
      id: `${parent.id}:summary`,
      rows: {
        oa: [summaryRow],
        bank: segment.rows.bank,
        invoice: summaryInvoices,
      },
    },
    ...itemSegments,
  ];
}

function hasMultiProjectExpenseItems(row: WorkbenchRecord) {
  const projectNames = new Set(
    (row.expenseItems ?? [])
      .map((item) => item.projectName.trim())
      .filter((projectName) => projectName && projectName !== "--" && projectName !== "—"),
  );
  return projectNames.size > 1;
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

export function collectWorkbenchFilterOptions(
  groups: WorkbenchRelationGroup[],
  paneId: WorkbenchRecordType,
  columnKey: string,
): string[] {
  if (paneId === "bank" && columnKey === "amount") {
    return collectBankAmountFilterOptions(groups);
  }

  const values = new Set<string>();

  groups.forEach((group) => {
    getWorkbenchGroupPaneRowsForCriteria(group, paneId).forEach((row) => {
      const value = row.tableValues[columnKey];
      if (!value || value === "--" || value === "—") {
        return;
      }
      values.add(value);
    });
  });

  return Array.from(values).sort((left, right) => left.localeCompare(right, "zh-CN"));
}

export function collectWorkbenchTimeFilterYears(
  groups: WorkbenchRelationGroup[],
  paneId: WorkbenchRecordType,
): string[] {
  const years = new Set<string>();

  groups.forEach((group) => {
    getWorkbenchGroupPaneRowsForCriteria(group, paneId).forEach((row) => {
      const timeValue = resolveWorkbenchRowSortValue(row, paneId);
      if (!timeValue || timeValue.length < 4) {
        return;
      }
      years.add(timeValue.slice(0, 4));
    });
  });

  return Array.from(years).sort((left, right) => right.localeCompare(left, "zh-CN"));
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
      const rowValues = resolveBankAmountFilterValues(row);
      return selectedValues.every((value) => rowValues.includes(value));
    }
    const currentValue = row.tableValues[columnKey] ?? "";
    return selectedValues.some((value) => value === currentValue);
  });
}

function collectBankAmountFilterOptions(groups: WorkbenchRelationGroup[]) {
  const directionValues = new Set<string>();
  const accountValues = new Set<string>();

  groups.forEach((group) => {
    getWorkbenchGroupPaneRowsForCriteria(group, "bank").forEach((row) => {
      const direction = row.tableValues.direction;
      if (direction && direction !== "--" && direction !== "—") {
        directionValues.add(direction);
      }
      const paymentAccount = row.tableValues.paymentAccount;
      if (paymentAccount && paymentAccount !== "--" && paymentAccount !== "—") {
        accountValues.add(paymentAccount);
      }
    });
  });

  const orderedDirections = ["支出", "收入"].filter((value) => directionValues.has(value));
  const orderedAccounts = Array.from(accountValues).sort((left, right) => left.localeCompare(right, "zh-CN"));
  return [...orderedDirections, ...orderedAccounts];
}

function getWorkbenchGroupPaneRowsForCriteria(group: WorkbenchRelationGroup, paneId: WorkbenchRecordType) {
  return [
    ...group.rows[paneId],
    ...(group.collapsedRows?.[paneId] ?? []),
  ];
}

function resolveBankAmountFilterValues(row: WorkbenchRecord) {
  const values: string[] = [];
  const direction = row.tableValues.direction;
  const paymentAccount = row.tableValues.paymentAccount;

  if (direction && direction !== "--" && direction !== "—") {
    values.push(direction);
  }
  if (paymentAccount && paymentAccount !== "--" && paymentAccount !== "—") {
    values.push(paymentAccount);
  }

  return values;
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
  if (sourceKind === "oa_attachment_unknown") {
    return "未识别附件";
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
