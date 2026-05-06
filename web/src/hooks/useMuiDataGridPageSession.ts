import { useCallback, useEffect, useMemo } from "react";
import type {
  GridColumnVisibilityModel,
  GridFilterModel,
  GridPaginationModel,
  GridRowId,
  GridRowSelectionModel,
  GridSortModel,
} from "@mui/x-data-grid";

import { usePageSessionState } from "../contexts/PageSessionStateContext";
import type { PageSessionRestoreState } from "../contexts/pageSessionStorage";

type SerializableRowSelectionModel = {
  type: "include" | "exclude";
  ids: GridRowId[];
};

type SerializableMuiDataGridSession = {
  columnsVersion: string;
  paginationModel: GridPaginationModel;
  sortModel: GridSortModel;
  filterModel: GridFilterModel;
  columnVisibilityModel: GridColumnVisibilityModel;
  rowSelectionModel: SerializableRowSelectionModel;
  columnWidths: Record<string, number>;
  columnOrder: string[];
};

export type MuiDataGridPageSessionOptions = {
  pageKey: string;
  gridKey: string;
  columnsVersion: string | number;
  validRowIds?: Iterable<GridRowId>;
  defaultPaginationModel?: GridPaginationModel;
  defaultSortModel?: GridSortModel;
  defaultFilterModel?: GridFilterModel;
  defaultColumnVisibilityModel?: GridColumnVisibilityModel;
  defaultRowSelectionModel?: GridRowSelectionModel;
  defaultColumnWidths?: Record<string, number>;
  defaultColumnOrder?: string[];
  ttlMs?: number;
  debounceMs?: number;
};

export type MuiDataGridPageSession = {
  paginationModel: GridPaginationModel;
  onPaginationModelChange: (model: GridPaginationModel) => void;
  sortModel: GridSortModel;
  onSortModelChange: (model: GridSortModel) => void;
  filterModel: GridFilterModel;
  onFilterModelChange: (model: GridFilterModel) => void;
  columnVisibilityModel: GridColumnVisibilityModel;
  onColumnVisibilityModelChange: (model: GridColumnVisibilityModel) => void;
  rowSelectionModel: GridRowSelectionModel;
  onRowSelectionModelChange: (model: GridRowSelectionModel) => void;
  columnWidths: Record<string, number>;
  setColumnWidths: (model: Record<string, number>) => void;
  columnOrder: string[];
  setColumnOrder: (model: string[]) => void;
  reset: () => void;
  restoreState: PageSessionRestoreState;
};

const DEFAULT_GRID_SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

function defaultFilterModel(): GridFilterModel {
  return { items: [] };
}

function defaultRowSelectionModel(): GridRowSelectionModel {
  return { type: "include", ids: new Set() };
}

function serializeRowSelectionModel(model: GridRowSelectionModel): SerializableRowSelectionModel {
  return {
    type: model.type,
    ids: Array.from(model.ids),
  };
}

function deserializeRowSelectionModel(model: SerializableRowSelectionModel): GridRowSelectionModel {
  return {
    type: model.type,
    ids: new Set(model.ids),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isSerializableGridSession(value: unknown): value is SerializableMuiDataGridSession {
  if (!isRecord(value)) {
    return false;
  }
  const rowSelection = value.rowSelectionModel;
  return (
    typeof value.columnsVersion === "string"
    && isRecord(value.paginationModel)
    && Array.isArray(value.sortModel)
    && isRecord(value.filterModel)
    && isRecord(value.columnVisibilityModel)
    && isRecord(rowSelection)
    && (rowSelection.type === "include" || rowSelection.type === "exclude")
    && Array.isArray(rowSelection.ids)
    && isRecord(value.columnWidths)
    && Array.isArray(value.columnOrder)
  );
}

function createInitialGridSession(options: MuiDataGridPageSessionOptions): SerializableMuiDataGridSession {
  return {
    columnsVersion: String(options.columnsVersion),
    paginationModel: options.defaultPaginationModel ?? { page: 0, pageSize: 100 },
    sortModel: options.defaultSortModel ?? [],
    filterModel: options.defaultFilterModel ?? defaultFilterModel(),
    columnVisibilityModel: options.defaultColumnVisibilityModel ?? {},
    rowSelectionModel: serializeRowSelectionModel(options.defaultRowSelectionModel ?? defaultRowSelectionModel()),
    columnWidths: options.defaultColumnWidths ?? {},
    columnOrder: options.defaultColumnOrder ?? [],
  };
}

function filterRowSelectionModel(model: GridRowSelectionModel, validRowIds?: Iterable<GridRowId>) {
  if (!validRowIds || model.ids.size === 0) {
    return model;
  }
  const validIds = new Set(validRowIds);
  return {
    ...model,
    ids: new Set(Array.from(model.ids).filter((id) => validIds.has(id))),
  };
}

function rowSelectionModelsEqual(left: GridRowSelectionModel, right: GridRowSelectionModel) {
  if (left.type !== right.type || left.ids.size !== right.ids.size) {
    return false;
  }
  for (const id of left.ids) {
    if (!right.ids.has(id)) {
      return false;
    }
  }
  return true;
}

export function useMuiDataGridPageSession(options: MuiDataGridPageSessionOptions): MuiDataGridPageSession {
  const columnsVersion = String(options.columnsVersion);
  const initialValue = useMemo(() => createInitialGridSession(options), [
    columnsVersion,
    options.defaultColumnOrder,
    options.defaultColumnVisibilityModel,
    options.defaultColumnWidths,
    options.defaultFilterModel,
    options.defaultPaginationModel,
    options.defaultRowSelectionModel,
    options.defaultSortModel,
  ]);
  const pageSession = usePageSessionState<SerializableMuiDataGridSession>({
    pageKey: options.pageKey,
    stateKey: `muiDataGrid.${options.gridKey}`,
    version: 1,
    initialValue,
    ttlMs: options.ttlMs ?? DEFAULT_GRID_SESSION_TTL_MS,
    storage: "session",
    validate: isSerializableGridSession,
    debounceMs: options.debounceMs ?? 150,
  });

  const storedValue = pageSession.value.columnsVersion === columnsVersion
    ? pageSession.value
    : initialValue;
  const rawRowSelectionModel = deserializeRowSelectionModel(storedValue.rowSelectionModel);
  const rowSelectionModel = useMemo(() => (
    filterRowSelectionModel(rawRowSelectionModel, options.validRowIds)
  ), [options.validRowIds, rawRowSelectionModel]);

  useEffect(() => {
    if (pageSession.value.columnsVersion !== columnsVersion) {
      pageSession.setValue(initialValue);
      return;
    }
    if (!rowSelectionModelsEqual(rawRowSelectionModel, rowSelectionModel)) {
      pageSession.setValue((current) => ({
        ...current,
        rowSelectionModel: serializeRowSelectionModel(rowSelectionModel),
      }));
    }
  }, [columnsVersion, initialValue, pageSession, rawRowSelectionModel, rowSelectionModel]);

  const update = useCallback((updater: (current: SerializableMuiDataGridSession) => SerializableMuiDataGridSession) => {
    pageSession.setValue((current) => updater(current.columnsVersion === columnsVersion ? current : initialValue));
  }, [columnsVersion, initialValue, pageSession]);

  return {
    paginationModel: storedValue.paginationModel,
    onPaginationModelChange: (model) => update((current) => ({ ...current, paginationModel: model })),
    sortModel: storedValue.sortModel,
    onSortModelChange: (model) => update((current) => ({ ...current, sortModel: model })),
    filterModel: storedValue.filterModel,
    onFilterModelChange: (model) => update((current) => ({ ...current, filterModel: model })),
    columnVisibilityModel: storedValue.columnVisibilityModel,
    onColumnVisibilityModelChange: (model) => update((current) => ({ ...current, columnVisibilityModel: model })),
    rowSelectionModel,
    onRowSelectionModelChange: (model) => update((current) => ({
      ...current,
      rowSelectionModel: serializeRowSelectionModel(filterRowSelectionModel(model, options.validRowIds)),
    })),
    columnWidths: storedValue.columnWidths,
    setColumnWidths: (model) => update((current) => ({ ...current, columnWidths: model })),
    columnOrder: storedValue.columnOrder,
    setColumnOrder: (model) => update((current) => ({ ...current, columnOrder: model })),
    reset: pageSession.reset,
    restoreState: pageSession.restoreState,
  };
}

