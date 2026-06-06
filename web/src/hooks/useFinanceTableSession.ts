import { useCallback, useEffect, useMemo, useRef, type MutableRefObject } from "react";

import { usePageSessionState } from "../contexts/PageSessionStateContext";
import type { PageSessionRestoreState } from "../contexts/pageSessionStorage";

export type FinanceTableRowId = string | number;

export type FinanceTablePaginationModel = {
  page: number;
  pageSize: number;
};

export type FinanceTableSortDescriptor = {
  column: string;
  direction: "ascending" | "descending";
} | null;

export type FinanceTableScrollPosition = {
  top: number;
  left: number;
};

type SerializableFinanceTableSession = {
  columnsVersion: string;
  paginationModel: FinanceTablePaginationModel;
  sortDescriptor: FinanceTableSortDescriptor;
  selectedRowIds: FinanceTableRowId[];
  scrollPosition: FinanceTableScrollPosition;
};

export type FinanceTableSessionOptions = {
  pageKey: string;
  tableKey: string;
  columnsVersion: string | number;
  validRowIds?: Iterable<FinanceTableRowId>;
  defaultPaginationModel?: FinanceTablePaginationModel;
  defaultSortDescriptor?: FinanceTableSortDescriptor;
  defaultSelectedRowIds?: Iterable<FinanceTableRowId>;
  defaultScrollPosition?: FinanceTableScrollPosition;
  ttlMs?: number;
  debounceMs?: number;
};

export type FinanceTableSession = {
  paginationModel: FinanceTablePaginationModel;
  onPaginationModelChange: (model: FinanceTablePaginationModel) => void;
  sortDescriptor: FinanceTableSortDescriptor;
  onSortChange: (descriptor: FinanceTableSortDescriptor) => void;
  selectedRowIds: Set<FinanceTableRowId>;
  onSelectedRowIdsChange: (ids: Iterable<FinanceTableRowId>) => void;
  scrollPosition: FinanceTableScrollPosition;
  setScrollPosition: (position: FinanceTableScrollPosition) => void;
  reset: () => void;
  restoreState: PageSessionRestoreState;
};

export type FinanceTableScrollSessionBinding = {
  scrollRef: MutableRefObject<HTMLDivElement | null>;
  initialScrollPosition: FinanceTableScrollPosition;
};

const DEFAULT_FINANCE_TABLE_SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isFinanceTablePaginationModel(value: unknown): value is FinanceTablePaginationModel {
  return (
    isRecord(value)
    && typeof value.page === "number"
    && Number.isFinite(value.page)
    && typeof value.pageSize === "number"
    && Number.isFinite(value.pageSize)
  );
}

function isFinanceTableSortDescriptor(value: unknown): value is FinanceTableSortDescriptor {
  return (
    value === null
    || (
      isRecord(value)
      && typeof value.column === "string"
      && (value.direction === "ascending" || value.direction === "descending")
    )
  );
}

function isFinanceTableScrollPosition(value: unknown): value is FinanceTableScrollPosition {
  return (
    isRecord(value)
    && typeof value.top === "number"
    && Number.isFinite(value.top)
    && typeof value.left === "number"
    && Number.isFinite(value.left)
  );
}

function isSerializableFinanceTableSession(value: unknown): value is SerializableFinanceTableSession {
  return (
    isRecord(value)
    && typeof value.columnsVersion === "string"
    && isFinanceTablePaginationModel(value.paginationModel)
    && isFinanceTableSortDescriptor(value.sortDescriptor)
    && Array.isArray(value.selectedRowIds)
    && isFinanceTableScrollPosition(value.scrollPosition)
  );
}

function createInitialFinanceTableSession(options: FinanceTableSessionOptions): SerializableFinanceTableSession {
  return {
    columnsVersion: String(options.columnsVersion),
    paginationModel: options.defaultPaginationModel ?? { page: 1, pageSize: 50 },
    sortDescriptor: options.defaultSortDescriptor ?? null,
    selectedRowIds: Array.from(options.defaultSelectedRowIds ?? []),
    scrollPosition: options.defaultScrollPosition ?? { top: 0, left: 0 },
  };
}

function restoreFinanceTableSession(raw: unknown): SerializableFinanceTableSession {
  if (!isRecord(raw)) {
    throw new Error("Invalid finance table session payload.");
  }
  return {
    columnsVersion: typeof raw.columnsVersion === "string" ? raw.columnsVersion : "",
    paginationModel: isFinanceTablePaginationModel(raw.paginationModel)
      ? raw.paginationModel
      : { page: 1, pageSize: 50 },
    sortDescriptor: isFinanceTableSortDescriptor(raw.sortDescriptor) ? raw.sortDescriptor : null,
    selectedRowIds: Array.isArray(raw.selectedRowIds) ? raw.selectedRowIds as FinanceTableRowId[] : [],
    scrollPosition: isFinanceTableScrollPosition(raw.scrollPosition) ? raw.scrollPosition : { top: 0, left: 0 },
  };
}

function normalizePaginationModel(model: FinanceTablePaginationModel): FinanceTablePaginationModel {
  return {
    page: Math.max(1, Math.round(model.page)),
    pageSize: Math.max(1, Math.round(model.pageSize)),
  };
}

function normalizeScrollPosition(position: FinanceTableScrollPosition): FinanceTableScrollPosition {
  return {
    top: Math.max(0, Math.round(position.top)),
    left: Math.max(0, Math.round(position.left)),
  };
}

function filterSelectedRowIds(ids: Iterable<FinanceTableRowId>, validRowIds?: Iterable<FinanceTableRowId>) {
  const selectedIds = Array.from(ids);
  if (!validRowIds || selectedIds.length === 0) {
    return selectedIds;
  }
  const validIds = new Set(validRowIds);
  return selectedIds.filter((id) => validIds.has(id));
}

function selectedIdsEqual(left: Iterable<FinanceTableRowId>, right: Iterable<FinanceTableRowId>) {
  const leftIds = Array.from(left);
  const rightIds = Array.from(right);
  if (leftIds.length !== rightIds.length) {
    return false;
  }
  const rightSet = new Set(rightIds);
  return leftIds.every((id) => rightSet.has(id));
}

export function useFinanceTableSession(options: FinanceTableSessionOptions): FinanceTableSession {
  const columnsVersion = String(options.columnsVersion);
  const initialValue = useMemo(() => createInitialFinanceTableSession(options), [
    columnsVersion,
    options.defaultPaginationModel,
    options.defaultScrollPosition,
    options.defaultSelectedRowIds,
    options.defaultSortDescriptor,
  ]);
  const pageSession = usePageSessionState<SerializableFinanceTableSession>({
    pageKey: options.pageKey,
    stateKey: `financeTable.${options.tableKey}`,
    version: 1,
    initialValue,
    ttlMs: options.ttlMs ?? DEFAULT_FINANCE_TABLE_SESSION_TTL_MS,
    storage: "session",
    restore: restoreFinanceTableSession,
    validate: isSerializableFinanceTableSession,
    debounceMs: options.debounceMs ?? 150,
  });

  const storedValue = pageSession.value.columnsVersion === columnsVersion
    ? pageSession.value
    : initialValue;
  const selectedRowIds = useMemo(() => (
    new Set(filterSelectedRowIds(storedValue.selectedRowIds, options.validRowIds))
  ), [options.validRowIds, storedValue.selectedRowIds]);

  useEffect(() => {
    if (pageSession.value.columnsVersion !== columnsVersion) {
      pageSession.setValue(initialValue);
      return;
    }
    if (!selectedIdsEqual(storedValue.selectedRowIds, selectedRowIds)) {
      pageSession.setValue((current) => ({
        ...current,
        selectedRowIds: Array.from(selectedRowIds),
      }));
    }
  }, [columnsVersion, initialValue, pageSession, selectedRowIds, storedValue.selectedRowIds]);

  const update = useCallback((
    updater: (current: SerializableFinanceTableSession) => SerializableFinanceTableSession,
  ) => {
    pageSession.setValue((current) => updater(current.columnsVersion === columnsVersion ? current : initialValue));
  }, [columnsVersion, initialValue, pageSession]);

  return {
    paginationModel: storedValue.paginationModel,
    onPaginationModelChange: (model) => update((current) => ({
      ...current,
      paginationModel: normalizePaginationModel(model),
    })),
    sortDescriptor: storedValue.sortDescriptor,
    onSortChange: (descriptor) => update((current) => ({ ...current, sortDescriptor: descriptor })),
    selectedRowIds,
    onSelectedRowIdsChange: (ids) => update((current) => ({
      ...current,
      selectedRowIds: filterSelectedRowIds(ids, options.validRowIds),
    })),
    scrollPosition: storedValue.scrollPosition,
    setScrollPosition: (position) => update((current) => ({
      ...current,
      scrollPosition: normalizeScrollPosition(position),
    })),
    reset: pageSession.reset,
    restoreState: pageSession.restoreState,
  };
}

export function useFinanceTableScrollSession(session: FinanceTableSession): FinanceTableScrollSessionBinding {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const setScrollPositionRef = useRef(session.setScrollPosition);

  useEffect(() => {
    setScrollPositionRef.current = session.setScrollPosition;
  }, [session.setScrollPosition]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) {
      return undefined;
    }
    node.scrollTop = session.scrollPosition.top;
    node.scrollLeft = session.scrollPosition.left;

    const persistScrollPosition = () => {
      setScrollPositionRef.current({
        top: node.scrollTop,
        left: node.scrollLeft,
      });
    };
    node.addEventListener("scroll", persistScrollPosition, { passive: true });
    return () => {
      persistScrollPosition();
      node.removeEventListener("scroll", persistScrollPosition);
    };
  }, [session.scrollPosition.left, session.scrollPosition.top]);

  return {
    scrollRef,
    initialScrollPosition: session.scrollPosition,
  };
}
