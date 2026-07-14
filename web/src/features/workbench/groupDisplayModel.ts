import type {
  WorkbenchRelationGroup,
  WorkbenchGroupsPageQuery,
  WorkbenchPaneRows,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "./types";

const workbenchPaneIds: WorkbenchRecordType[] = ["oa", "bank", "invoice"];

export type WorkbenchGroupDisplaySegment = {
  id: string;
  rows: WorkbenchPaneRows;
};

export type WorkbenchPaneTimeFilter =
  | { mode: "none" }
  | { mode: "year"; year: string }
  | { mode: "month"; month: string };

export type WorkbenchZoneDisplayState = {
  activePaneId: WorkbenchRecordType | null;
  openSearchPaneId: WorkbenchRecordType | null;
  unifiedSearchQuery: string;
  draftSearchQueryByPane: Record<WorkbenchRecordType, string>;
  searchQueryByPane: Record<WorkbenchRecordType, string>;
  filtersByPaneAndColumn: Record<WorkbenchRecordType, Record<string, string[]>>;
  sortByPane: Record<WorkbenchRecordType, "asc" | "desc" | null>;
  timeFilterByPane: Record<WorkbenchRecordType, WorkbenchPaneTimeFilter>;
};

export function createEmptyWorkbenchZoneDisplayState(): WorkbenchZoneDisplayState {
  return {
    activePaneId: null,
    openSearchPaneId: null,
    unifiedSearchQuery: "",
    draftSearchQueryByPane: {
      oa: "",
      bank: "",
      invoice: "",
    },
    searchQueryByPane: {
      oa: "",
      bank: "",
      invoice: "",
    },
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
  if (!activePaneId) {
    return groups;
  }

  const sortDirection = state.sortByPane[activePaneId];
  const linkedSearchContext = resolveWorkbenchSearchContext(state);
  const hasPaneCriteria = Boolean(linkedSearchContext) || workbenchPaneIds.some((paneId) => paneHasWorkbenchRowCriteria(state, paneId));
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

  if (!sortDirection) {
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

export function buildWorkbenchGroupDisplaySegments(
  group: WorkbenchRelationGroup,
): WorkbenchGroupDisplaySegment[] | null {
  if (group.displayMode === "collapsed_summary" || group.rows.oa.length < 2) {
    return null;
  }

  const oaRowsById = new Map(group.rows.oa.map((row) => [row.id, row]));
  const bankRowsBySourceOaId = new Map<string, WorkbenchRecord[]>();
  const unlinkedBankRows: WorkbenchRecord[] = [];
  const invoicesBySourceOaId = new Map<string, WorkbenchRecord[]>();
  const unlinkedInvoiceRows: WorkbenchRecord[] = [];

  group.rows.bank.forEach((bankRow) => {
    const sourceOaId = normalizeSourceOaId(bankRow.sourceOaId);
    if (sourceOaId && oaRowsById.has(sourceOaId)) {
      const rows = bankRowsBySourceOaId.get(sourceOaId) ?? [];
      rows.push(bankRow);
      bankRowsBySourceOaId.set(sourceOaId, rows);
      return;
    }
    unlinkedBankRows.push(bankRow);
  });

  group.rows.invoice.forEach((invoiceRow) => {
    const sourceOaId = normalizeSourceOaId(invoiceRow.sourceOaId);
    if (sourceOaId && oaRowsById.has(sourceOaId)) {
      const rows = invoicesBySourceOaId.get(sourceOaId) ?? [];
      rows.push(invoiceRow);
      invoicesBySourceOaId.set(sourceOaId, rows);
      return;
    }
    unlinkedInvoiceRows.push(invoiceRow);
  });

  const remainingUnlinkedBankRows = assignRowsByAmountFallback(group.rows.oa, unlinkedBankRows, bankRowsBySourceOaId);
  const remainingUnlinkedInvoiceRows = assignRowsByAmountFallback(group.rows.oa, unlinkedInvoiceRows, invoicesBySourceOaId);

  const hasSegmentedBankRows = Array.from(bankRowsBySourceOaId.values()).some((rows) => rows.length > 0);
  const hasSegmentedInvoiceRows = Array.from(invoicesBySourceOaId.values()).some((rows) => rows.length > 0);
  if (!hasSegmentedBankRows && !hasSegmentedInvoiceRows) {
    return null;
  }

  const segments = group.rows.oa.map((oaRow) => ({
    id: oaRow.id,
    rows: {
      oa: [oaRow],
      bank: bankRowsBySourceOaId.get(oaRow.id) ?? [],
      invoice: invoicesBySourceOaId.get(oaRow.id) ?? [],
    },
  }));

  const groupLevelBankRows = hasSegmentedBankRows ? remainingUnlinkedBankRows : [];
  const groupLevelInvoiceRows = hasSegmentedInvoiceRows ? remainingUnlinkedInvoiceRows : [];
  if (groupLevelBankRows.length > 0 || groupLevelInvoiceRows.length > 0) {
    segments.push({
      id: "unlinked-source-rows",
      rows: {
        oa: [],
        bank: groupLevelBankRows,
        invoice: groupLevelInvoiceRows,
      },
    });
  }

  return segments.length > 1 ? segments : null;
}

function assignRowsByAmountFallback(
  oaRows: WorkbenchRecord[],
  candidateRows: WorkbenchRecord[],
  rowsByOaId: Map<string, WorkbenchRecord[]>,
): WorkbenchRecord[] {
  if (candidateRows.length === 0) {
    return [];
  }

  let remainingRows = [...candidateRows];
  const oaAmountById = new Map<string, bigint>();
  const oaIdsByAmount = new Map<string, string[]>();

  oaRows.forEach((oaRow) => {
    const amount = parseAmountCents(oaRow.amount);
    if (amount === null) {
      return;
    }
    oaAmountById.set(oaRow.id, amount);
    const amountKey = amount.toString();
    const ids = oaIdsByAmount.get(amountKey) ?? [];
    ids.push(oaRow.id);
    oaIdsByAmount.set(amountKey, ids);
  });

  const exactAssignedRows = new Set<WorkbenchRecord>();
  remainingRows.forEach((row) => {
    const amount = parseAmountCents(row.amount);
    if (amount === null) {
      return;
    }
    const matchingOaIds = (oaIdsByAmount.get(amount.toString()) ?? []).filter((oaId) => !rowsByOaId.has(oaId));
    if (matchingOaIds.length !== 1) {
      return;
    }
    const oaId = matchingOaIds[0];
    rowsByOaId.set(oaId, [row]);
    exactAssignedRows.add(row);
  });
  remainingRows = remainingRows.filter((row) => !exactAssignedRows.has(row));

  oaRows.forEach((oaRow) => {
    if (rowsByOaId.has(oaRow.id)) {
      return;
    }
    const targetAmount = oaAmountById.get(oaRow.id);
    if (targetAmount === undefined) {
      return;
    }
    const matchedRows = findUniqueAmountSubset(remainingRows, targetAmount);
    if (!matchedRows) {
      return;
    }
    const matchedRowSet = new Set(matchedRows);
    rowsByOaId.set(oaRow.id, matchedRows);
    remainingRows = remainingRows.filter((row) => !matchedRowSet.has(row));
  });

  return remainingRows;
}

function parseAmountCents(value: string): bigint | null {
  const normalizedValue = value.trim().replace(/,/g, "");
  const unsignedValue = normalizedValue.replace(/^[-+]/, "");
  if (!/^\d+(?:\.\d{1,4})?$/.test(unsignedValue)) {
    return null;
  }
  const [integerPart, decimalPart = ""] = unsignedValue.split(".");
  const amount = BigInt(integerPart) * 100n + BigInt((decimalPart + "00").slice(0, 2));
  return amount > 0n ? amount : null;
}

function findUniqueAmountSubset(rows: WorkbenchRecord[], targetAmount: bigint): WorkbenchRecord[] | null {
  const rowsWithAmount = rows
    .map((row) => ({ row, amount: parseAmountCents(row.amount) }))
    .filter((item): item is { row: WorkbenchRecord; amount: bigint } => item.amount !== null);
  const matches: WorkbenchRecord[][] = [];
  const maxRowsPerAmountMatch = 6;

  function search(startIndex: number, selectedRows: WorkbenchRecord[], selectedAmount: bigint): void {
    if (matches.length > 1 || selectedRows.length >= maxRowsPerAmountMatch || selectedAmount >= targetAmount) {
      if (selectedAmount === targetAmount && selectedRows.length > 1) {
        matches.push([...selectedRows]);
      }
      return;
    }

    for (let index = startIndex; index < rowsWithAmount.length; index += 1) {
      const item = rowsWithAmount[index];
      search(index + 1, [...selectedRows, item.row], selectedAmount + item.amount);
      if (matches.length > 1) {
        return;
      }
    }
  }

  search(0, [], 0n);
  return matches.length === 1 ? matches[0] : null;
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
  const searchByPane = Object.fromEntries(
    workbenchPaneIds
      .map((paneId) => [paneId, (state.searchQueryByPane[paneId] ?? "").trim()] as const)
      .filter(([, value]) => Boolean(value)),
  );
  if (Object.keys(searchByPane).length > 0) {
    query.searchByPane = searchByPane;
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
    || (query.searchByPane && Object.keys(query.searchByPane).length > 0)
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

function resolveWorkbenchSearchContext(state: WorkbenchZoneDisplayState) {
  if (state.activePaneId) {
    const activePaneRawQuery = (state.searchQueryByPane[state.activePaneId] || "").trim();
    const activePaneQuery = normalizeWorkbenchSearchText(activePaneRawQuery);
    if (activePaneQuery) {
      return {
        paneId: state.activePaneId,
        rawQuery: activePaneRawQuery,
        normalizedQuery: activePaneQuery,
      };
    }
  }

  const paneId = workbenchPaneIds.find((candidatePaneId) =>
    normalizeWorkbenchSearchText(state.searchQueryByPane[candidatePaneId] || ""),
  );
  if (!paneId) {
    return null;
  }

  return {
    paneId,
    rawQuery: (state.searchQueryByPane[paneId] || "").trim(),
    normalizedQuery: normalizeWorkbenchSearchText(state.searchQueryByPane[paneId] || ""),
  };
}

function groupMatchesPaneCriteria(group: WorkbenchRelationGroup, state: WorkbenchZoneDisplayState) {
  const linkedSearchContext = resolveWorkbenchSearchContext(state);
  if (
    linkedSearchContext
    && !getWorkbenchGroupPaneRowsForCriteria(group, linkedSearchContext.paneId).some((row) =>
      matchesWorkbenchRowText(row, linkedSearchContext.normalizedQuery),
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
    return selectedValues.every((value) => value === currentValue);
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
  return value.replace(/\s+/g, "").trim().toLowerCase();
}

export function workbenchRowMatchesUnifiedSearch(row: WorkbenchRecord, query: string) {
  const normalizedQuery = normalizeWorkbenchSearchText(query);
  return normalizedQuery ? matchesWorkbenchRowText(row, normalizedQuery) : false;
}

export function resolveWorkbenchLinkedSearchQuery(state: WorkbenchZoneDisplayState) {
  return resolveWorkbenchSearchContext(state)?.rawQuery ?? "";
}

function matchesWorkbenchRowText(row: WorkbenchRecord, normalizedQuery: string) {
  const normalizedHaystack = normalizeWorkbenchSearchText(
    [row.label, row.status, row.amount, row.counterparty, ...Object.values(row.tableValues), ...(row.tags ?? [])].join(" "),
  );
  return normalizedHaystack.includes(normalizedQuery);
}

function paneHasWorkbenchCriteria(state: WorkbenchZoneDisplayState, paneId: WorkbenchRecordType) {
  const normalizedQuery = normalizeWorkbenchSearchText(state.searchQueryByPane[paneId] || "");
  if (normalizedQuery) {
    return true;
  }

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
