import type { WorkbenchCandidateGroup, WorkbenchPaneRows, WorkbenchRecord, WorkbenchRecordType } from "./types";

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
  groups: WorkbenchCandidateGroup[],
  state: WorkbenchZoneDisplayState,
): WorkbenchCandidateGroup[] {
  const activePaneId = state.activePaneId;
  if (!activePaneId) {
    return groups;
  }

  const normalizedQuery = normalizeWorkbenchSearchText(state.unifiedSearchQuery || state.searchQueryByPane[activePaneId] || "");
  const activeFilters = state.filtersByPaneAndColumn[activePaneId] ?? {};
  const hasActiveFilters = Object.values(activeFilters).some((values) => values.length > 0);
  const sortDirection = state.sortByPane[activePaneId];
  const activeTimeFilter = state.timeFilterByPane[activePaneId] ?? { mode: "none" };
  const hasActiveTimeFilter = activeTimeFilter.mode !== "none";

  const displayGroups = !normalizedQuery && !hasActiveFilters && !hasActiveTimeFilter
    ? groups
    : groups.flatMap((group) => {
      if (normalizedQuery) {
        const groupMatches = (["oa", "bank", "invoice"] as const).some((paneId) =>
          group.rows[paneId].some((row) => matchesWorkbenchRowText(row, normalizedQuery)),
        );
        if (!groupMatches) {
          return [];
        }
      }

      const matchedRows = group.rows[activePaneId].filter((row) =>
        matchesWorkbenchRow(row, activePaneId, "", activeFilters, activeTimeFilter),
      );

      if ((hasActiveFilters || hasActiveTimeFilter) && matchedRows.length === 0) {
        return [];
      }

      return [
        {
          ...group,
          rows: {
            ...group.rows,
            [activePaneId]: hasActiveFilters || hasActiveTimeFilter ? matchedRows : group.rows[activePaneId],
          },
        },
      ];
    });

  if (!sortDirection) {
    return displayGroups;
  }

  return sortWorkbenchGroups(displayGroups, activePaneId, sortDirection);
}

export function buildWorkbenchPaneRows(groups: WorkbenchCandidateGroup[]): WorkbenchPaneRows {
  return {
    oa: groups.flatMap((group) => group.rows.oa),
    bank: groups.flatMap((group) => group.rows.bank),
    invoice: groups.flatMap((group) => group.rows.invoice),
  };
}

export function collectWorkbenchFilterOptions(
  groups: WorkbenchCandidateGroup[],
  paneId: WorkbenchRecordType,
  columnKey: string,
): string[] {
  if (paneId === "bank" && columnKey === "amount") {
    return collectBankAmountFilterOptions(groups);
  }

  const values = new Set<string>();

  groups.forEach((group) => {
    group.rows[paneId].forEach((row) => {
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
  groups: WorkbenchCandidateGroup[],
  paneId: WorkbenchRecordType,
): string[] {
  const years = new Set<string>();

  groups.forEach((group) => {
    group.rows[paneId].forEach((row) => {
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
      return resolveBankAmountFilterValues(row).some((value) => selectedValues.includes(value));
    }
    const currentValue = row.tableValues[columnKey] ?? "";
    return selectedValues.includes(currentValue);
  });
}

function collectBankAmountFilterOptions(groups: WorkbenchCandidateGroup[]) {
  const directionValues = new Set<string>();
  const accountValues = new Set<string>();

  groups.forEach((group) => {
    group.rows.bank.forEach((row) => {
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

function matchesWorkbenchRowText(row: WorkbenchRecord, normalizedQuery: string) {
  const normalizedHaystack = normalizeWorkbenchSearchText(
    [row.label, row.status, row.amount, row.counterparty, ...Object.values(row.tableValues), ...(row.tags ?? [])].join(" "),
  );
  return normalizedHaystack.includes(normalizedQuery);
}

function paneHasWorkbenchCriteria(state: WorkbenchZoneDisplayState, paneId: WorkbenchRecordType) {
  const normalizedQuery = normalizeWorkbenchSearchText(state.unifiedSearchQuery || state.searchQueryByPane[paneId] || "");
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

function sortWorkbenchGroups(
  groups: WorkbenchCandidateGroup[],
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
  group: WorkbenchCandidateGroup,
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
