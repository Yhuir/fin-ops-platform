import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import ActionStatusModal from "../components/workbench/ActionStatusModal";
import CancelProcessedExceptionModal from "../components/workbench/CancelProcessedExceptionModal";
import DetailDrawer from "../components/workbench/DetailDrawer";
import IgnoredItemsModal from "../components/workbench/IgnoredItemsModal";
import ProcessedExceptionsModal from "../components/workbench/ProcessedExceptionsModal";
import RelationPreviewTriPane from "../components/workbench/RelationPreviewTriPane";
import WorkbenchExceptionModal from "../components/workbench/WorkbenchExceptionModal";
import WorkbenchZone from "../components/workbench/WorkbenchZone";
import type { WorkbenchPane } from "../components/workbench/ResizableTriPane";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus, useCanMutateWithHealth } from "../contexts/AppHealthStatusContext";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  cancelWorkbenchException,
  cancelWorkbenchCashSpecial,
  confirmWorkbenchCashPassThrough,
  confirmWorkbenchCashTicketPurchase,
  confirmWorkbenchLink,
  fetchIgnoredWorkbenchRows,
  fetchWorkbenchGroupDetail,
  fetchWorkbenchGroupsPage,
  fetchWorkbenchInitialPage,
  fetchWorkbenchOaSyncStatus,
  fetchWorkbenchRefreshStatus,
  fetchWorkbenchRowDetail,
  fetchWorkbenchSettings,
  ignoreWorkbenchRow,
  previewWorkbenchConfirmLink,
  previewWorkbenchWithdrawLink,
  saveWorkbenchSettings,
  subscribeWorkbenchRefreshEvents,
  unignoreWorkbenchRow,
  withdrawWorkbenchLink,
  WORKBENCH_GROUP_PAGE_SIZE,
  type WorkbenchActionResult,
  type WorkbenchOperationProjection,
} from "../features/workbench/api";
import { fetchNoOaBankBatchDetail, withdrawNoOaBankBatch } from "../features/noOaBankBatches/api";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  eventAffectedMonths,
} from "../features/domainEvents";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { operationBarrierTargets, waitForOperationFreshness, type OperationBarrierTarget } from "../features/operationBarrier/api";
import {
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  buildWorkbenchPaneRows,
  createEmptyWorkbenchZoneDisplayState,
  hasWorkbenchServerPageCriteria,
  mergeWorkbenchGroupsById,
  resolveWorkbenchActivePane,
  type WorkbenchPaneTimeFilter,
  type WorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import { reorderWorkbenchColumnLayout, type WorkbenchColumnDropPosition } from "../features/workbench/columnLayout";
import { buildWorkbenchSelectionContext } from "../features/workbench/selectionModel";
import type {
  IgnoredWorkbenchData,
  WorkbenchCandidateGroup,
  WorkbenchData,
  WorkbenchExceptionApplyResult,
  WorkbenchGroupsPageQuery,
  WorkbenchInitialPageResult,
  WorkbenchOaSyncStatus,
  WorkbenchRecord,
  WorkbenchRefreshStatus,
  WorkbenchRelationPreview,
  WorkbenchSettings,
  WorkbenchZoneCounts,
  WorkbenchZonePageInfo,
} from "../features/workbench/types";
import { useMonth } from "../contexts/MonthContext";
import useWorkbenchSelection from "../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "../components/workbench/RowActions";

type ActionDialogState = {
  phase: "loading" | "result";
  title: string;
  message: string;
};

type RelationPreviewDialogState = {
  preview: WorkbenchRelationPreview;
  rowIds: string[];
  caseId?: string;
};

type WorkbenchExceptionDialogState = {
  rows: WorkbenchRecord[];
};

type CashTicketPurchaseDialogState = {
  rowIds: string[];
  cashAmount: string;
};

type CancelProcessedExceptionDialogState = {
  group: WorkbenchCandidateGroup;
};

type WorkbenchLoadProgressState = {
  label: string;
  loadedBytes: number;
  totalBytes: number;
  percent: number | null;
  indeterminate: boolean;
};

function createInitialZonePageInfo(zone: "paired" | "open"): WorkbenchZonePageInfo {
  return {
    zone,
    page: 0,
    pageSize: WORKBENCH_GROUP_PAGE_SIZE,
    total: 0,
    rowCounts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
    hasMore: false,
    readModelStatus: "fresh",
  };
}

function createInitialZonePages(): Record<"paired" | "open", WorkbenchZonePageInfo> {
  return {
    paired: createInitialZonePageInfo("paired"),
    open: createInitialZonePageInfo("open"),
  };
}

function resolveZoneItemCount(pageInfo: WorkbenchZonePageInfo, zoneCounts?: WorkbenchZoneCounts) {
  if (pageInfo.rowCounts.rows > 0) {
    return pageInfo.rowCounts.rows;
  }
  return zoneCounts?.rows ?? 0;
}

function isWorkbenchZoneDisplayState(value: unknown): value is WorkbenchZoneDisplayState {
  if (!value || typeof value !== "object") {
    return false;
  }
  const state = value as Record<string, unknown>;
  return (
    Object.prototype.hasOwnProperty.call(state, "activePaneId")
    && Object.prototype.hasOwnProperty.call(state, "searchQueryByPane")
    && Object.prototype.hasOwnProperty.call(state, "filtersByPaneAndColumn")
    && Object.prototype.hasOwnProperty.call(state, "sortByPane")
    && Object.prototype.hasOwnProperty.call(state, "timeFilterByPane")
  );
}

function actionErrorMessage(error: unknown) {
  if (error instanceof Error) {
    if (
      error.message.includes("Unexpected end of JSON input")
      || error.message.includes("Failed to execute 'json' on 'Response'")
      || error.message === "request failed"
      || error.message === "invalid_json_response"
    ) {
      return "操作失败，请稍后重试。";
    }
    try {
      const payload = JSON.parse(error.message) as { message?: string };
      if (payload.message) {
        return payload.message;
      }
    } catch {
      if (error.message.trim()) {
        return error.message;
      }
    }
  }
  return "操作失败，请稍后重试。";
}

function normalizedAmountForInput(value: string) {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized || normalized === "--" || normalized === "—") {
    return "";
  }
  return normalized;
}

const READONLY_ACTION_MESSAGE = "当前账号仅支持查看和导出，不能执行写操作。";
const WORKBENCH_VIEW_MONTH = "all";
const OA_SYNC_POLL_INTERVAL_MS = 3_000;
const OA_SYNC_REFRESH_DEBOUNCE_MS = 120;
const WORKBENCH_REFRESH_POLL_INTERVAL_MS = 5_000;
const WORKBENCH_REFRESH_RELOAD_DEBOUNCE_MS = 300;
const WORKBENCH_OPERATION_FRESH_POLL_MS = 300;
const WORKBENCH_OPERATION_FRESH_TIMEOUT_MS = 2_000;

function createWorkbenchServerPageQueryKey(query: WorkbenchGroupsPageQuery) {
  return JSON.stringify(query);
}

function createWorkbenchZoneServerPageQueryKeys(
  queries: Record<"paired" | "open", WorkbenchGroupsPageQuery>,
) {
  return {
    paired: createWorkbenchServerPageQueryKey(queries.paired),
    open: createWorkbenchServerPageQueryKey(queries.open),
  };
}

function createWorkbenchZoneServerPageQueriesKey(
  queries: Record<"paired" | "open", WorkbenchGroupsPageQuery>,
) {
  return JSON.stringify(createWorkbenchZoneServerPageQueryKeys(queries));
}

function isNoOaSummaryRow(row: WorkbenchRecord) {
  return row.sourceKind === "no_oa_bank_batch_summary" || Boolean(noOaSourceBatchId(row));
}

function noOaSourceBatchId(row: WorkbenchRecord) {
  return readStringMetadata(row.specialMetadata, "source_batch_id");
}

function uniqueNoOaBatchRows(rows: WorkbenchRecord[]) {
  const byBatchId = new Map<string, WorkbenchRecord>();
  rows.forEach((row) => {
    const sourceBatchId = noOaSourceBatchId(row);
    if (sourceBatchId && !byBatchId.has(sourceBatchId)) {
      byBatchId.set(sourceBatchId, row);
    }
  });
  return Array.from(byBatchId.values());
}

function readStringMetadata(metadata: Record<string, unknown> | undefined, key: string) {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readNumberMetadata(metadata: Record<string, unknown> | undefined, key: string) {
  const value = metadata?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cleanWorkbenchScopeList(value: unknown) {
  return Array.isArray(value)
    ? value.map((scope) => String(scope).trim()).filter(Boolean)
    : [];
}

function actionAffectedMonths(result: {
  affectedMonths?: unknown[];
  affected_months?: unknown[];
  changedScopes?: unknown[];
  changed_scopes?: unknown[];
}) {
  const affectedMonths = cleanWorkbenchScopeList(result.affectedMonths);
  if (affectedMonths.length > 0) {
    return affectedMonths;
  }
  const affectedSnakeMonths = cleanWorkbenchScopeList(result.affected_months);
  if (affectedSnakeMonths.length > 0) {
    return affectedSnakeMonths;
  }
  const changedScopes = cleanWorkbenchScopeList(result.changedScopes);
  if (changedScopes.length > 0) {
    return changedScopes;
  }
  const changedSnakeScopes = cleanWorkbenchScopeList(result.changed_scopes);
  if (changedSnakeScopes.length > 0) {
    return changedSnakeScopes;
  }
  return [WORKBENCH_VIEW_MONTH];
}

function actionFreshnessTargets(result: WorkbenchActionResult | null): OperationBarrierTarget[] {
  if (!result) {
    return operationBarrierTargets("workbench_relation", [WORKBENCH_VIEW_MONTH]);
  }
  if (result.freshnessTargets.length > 0) {
    return result.freshnessTargets;
  }
  if (result.affectedScopeKeys.length > 0) {
    if (hasOperationProjection(result.operationProjection)) {
      return operationBarrierTargets("workbench_relation", result.affectedScopeKeys);
    }
    return [
      ...operationBarrierTargets("workbench_relation", result.affectedScopeKeys),
      ...operationBarrierTargets("workbench", result.affectedScopeKeys),
    ];
  }
  if (hasOperationProjection(result.operationProjection)) {
    return operationBarrierTargets("workbench_relation", actionAffectedMonths(result));
  }
  return [
    ...operationBarrierTargets("workbench_relation", actionAffectedMonths(result)),
    ...operationBarrierTargets("workbench", actionAffectedMonths(result)),
  ].filter((target) => target.scopeKey !== "all");
}

function actionResultMessage(result: string | WorkbenchActionResult) {
  return typeof result === "string" ? result : result.message;
}

function workbenchInitialPageIsFresh(result: WorkbenchInitialPageResult | null) {
  return result?.pages.paired.readModelStatus === "fresh" && result.pages.open.readModelStatus === "fresh";
}

function delayWorkbenchOperationPoll() {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, WORKBENCH_OPERATION_FRESH_POLL_MS);
  });
}

function workbenchRefreshStatusVersionKey(status: WorkbenchRefreshStatus) {
  const version = status.readModelVersion ?? status.generatedAt;
  return version === null || version === undefined ? "" : String(version);
}

function workbenchRefreshStatusMessage(status: WorkbenchRefreshStatus | null) {
  if (!status) {
    return null;
  }
  if (status.readModelStatus === "failed") {
    return `关联台刷新失败${status.lastError ? `：${status.lastError}` : ""}`;
  }
  if (status.readModelStatus === "unavailable") {
    return "关联台读模型不可用";
  }
  return null;
}

function workbenchRefreshStatusPanelTone(status: WorkbenchRefreshStatus | null) {
  if (!status) {
    return "";
  }
  if (status.readModelStatus === "failed" || status.readModelStatus === "unavailable") {
    return " error";
  }
  if (status.readModelStatus === "refreshing" || status.readModelStatus === "stale") {
    return " pending";
  }
  return "";
}

export default function ReconciliationWorkbenchPage() {
  const { currentMonth } = useMonth();
  const { setWorkbenchStatus } = useAppChrome();
  const healthStatus = useAppHealthStatus();
  const canMutateWithHealth = useCanMutateWithHealth();
  const { runOperation } = useGlobalOperationOverlay();
  const { canMutateData } = useSessionPermissions();
  const { active } = useOptionalPageActivation("reconciliation-workbench");
  const isOaSyncWriteBlocked = healthStatus.sources.oaSync === "dirty" || healthStatus.sources.oaSync === "refreshing";
  const canWriteWorkbench = canMutateData && canMutateWithHealth && !isOaSyncWriteBlocked;
  const {
    detailRow,
    getRowState,
    openDetail,
    replaceDetailRow,
    closeDetail,
    clearSelection,
    clearPairedSelection,
    clearOpenSelection,
    selectedPairedRows: explicitSelectedPairedRows,
    togglePairedRowSelection,
    selectedOpenRowIds,
    selectedOpenRows: explicitSelectedOpenRows,
    toggleOpenRowSelection,
  } =
    useWorkbenchSelection();
  const [workbenchData, setWorkbenchData] = useState<WorkbenchData | null>(null);
  const [loadedZoneServerPageQueryKeys, setLoadedZoneServerPageQueryKeys] = useState<
    Record<"paired" | "open", string> | null
  >(null);
  const [selectionSourceGroups, setSelectionSourceGroups] = useState<Record<"paired" | "open", WorkbenchCandidateGroup[]>>({
    paired: [],
    open: [],
  });
  const [zonePages, setZonePages] = useState<Record<"paired" | "open", WorkbenchZonePageInfo>>(() => createInitialZonePages());
  const [loadingMoreZone, setLoadingMoreZone] = useState<"paired" | "open" | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadProgress, setLoadProgress] = useState<WorkbenchLoadProgressState>({
    label: "正在加载关联台数据",
    loadedBytes: 0,
    totalBytes: 0,
    percent: null,
    indeterminate: true,
  });
  const [workbenchRefreshStatus, setWorkbenchRefreshStatus] = useState<WorkbenchRefreshStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);
  const [expandedZoneId, setExpandedZoneId] = useState<"paired" | "open" | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialogState | null>(null);
  const [relationPreviewDialog, setRelationPreviewDialog] = useState<RelationPreviewDialogState | null>(null);
  const [ignoredData, setIgnoredData] = useState<IgnoredWorkbenchData>({ month: WORKBENCH_VIEW_MONTH, rows: [] });
  const [workbenchSettings, setWorkbenchSettings] = useState<WorkbenchSettings | null>(null);
  const [ignoredModalOpen, setIgnoredModalOpen] = useState(false);
  const [processedExceptionsModalOpen, setProcessedExceptionsModalOpen] = useState(false);
  const [workbenchExceptionDialog, setWorkbenchExceptionDialog] = useState<WorkbenchExceptionDialogState | null>(null);
  const [cashTicketPurchaseDialog, setCashTicketPurchaseDialog] = useState<CashTicketPurchaseDialogState | null>(null);
  const [cancelProcessedExceptionDialog, setCancelProcessedExceptionDialog] = useState<CancelProcessedExceptionDialogState | null>(null);
  const pairedDisplaySession = usePageSessionState<WorkbenchZoneDisplayState>({
    pageKey: "reconciliation-workbench",
    stateKey: "pairedDisplayState",
    version: 1,
    initialValue: createEmptyWorkbenchZoneDisplayState(),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isWorkbenchZoneDisplayState,
    debounceMs: 100,
  });
  const openDisplaySession = usePageSessionState<WorkbenchZoneDisplayState>({
    pageKey: "reconciliation-workbench",
    stateKey: "openDisplayState",
    version: 1,
    initialValue: createEmptyWorkbenchZoneDisplayState(),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isWorkbenchZoneDisplayState,
    debounceMs: 100,
  });
  const pairedDisplayState = pairedDisplaySession.value;
  const setPairedDisplayState = pairedDisplaySession.setValue;
  const openDisplayState = openDisplaySession.value;
  const setOpenDisplayState = openDisplaySession.setValue;
  const columnLayoutSaveRequestIdRef = useRef(0);
  const oaSyncRefreshTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const workbenchRefreshReloadTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const lastWorkbenchRefreshVersionRef = useRef<string>("");
  const previousOaSyncStatusRef = useRef<WorkbenchOaSyncStatus | null>(null);
  const deferredPairedDisplayState = useDeferredValue(pairedDisplayState);
  const deferredOpenDisplayState = useDeferredValue(openDisplayState);
  const pairedServerPageQuery = useMemo(
    () => buildWorkbenchServerPageQuery(deferredPairedDisplayState),
    [deferredPairedDisplayState],
  );
  const openServerPageQuery = useMemo(
    () => buildWorkbenchServerPageQuery(deferredOpenDisplayState),
    [deferredOpenDisplayState],
  );
  const zoneServerPageQueries = useMemo<Record<"paired" | "open", WorkbenchGroupsPageQuery>>(
    () => ({
      paired: pairedServerPageQuery,
      open: openServerPageQuery,
    }),
    [openServerPageQuery, pairedServerPageQuery],
  );
  const zoneServerPageQueryKeys = useMemo(
    () => createWorkbenchZoneServerPageQueryKeys(zoneServerPageQueries),
    [zoneServerPageQueries],
  );
  const zoneServerPageQueryKey = useMemo(
    () => createWorkbenchZoneServerPageQueriesKey(zoneServerPageQueries),
    [zoneServerPageQueries],
  );
  const lastZoneServerPageQueryKeyRef = useRef(zoneServerPageQueryKey);
  const [oaSyncShellStatus, setOaSyncShellStatus] = useState<{ level: "ok" | "pending" | "error"; reason: string } | null>(null);

  const updateZoneDisplayState = useCallback((
    zoneId: "paired" | "open",
    updater: (current: WorkbenchZoneDisplayState) => WorkbenchZoneDisplayState,
  ) => {
    if (zoneId === "paired") {
      setPairedDisplayState((current) => updater(current));
      return;
    }
    setOpenDisplayState((current) => updater(current));
  }, []);

  const handleTogglePaneSearch = useCallback((zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => {
    updateZoneDisplayState(zoneId, (current) => {
      const isOpen = current.openSearchPaneId === paneId;
      const nextState: WorkbenchZoneDisplayState = {
        ...current,
        openSearchPaneId: isOpen ? null : paneId,
        draftSearchQueryByPane: {
          ...current.draftSearchQueryByPane,
          [paneId]: isOpen ? current.draftSearchQueryByPane[paneId] : current.searchQueryByPane[paneId],
        },
      };
      return {
        ...nextState,
        activePaneId: resolveWorkbenchActivePane(nextState, paneId),
      };
    });
  }, [updateZoneDisplayState]);

  const handleClosePaneSearch = useCallback((zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => {
    updateZoneDisplayState(zoneId, (current) => {
      if (current.openSearchPaneId !== paneId) {
        return current;
      }
      const nextState: WorkbenchZoneDisplayState = {
        ...current,
        openSearchPaneId: null,
        draftSearchQueryByPane: {
          ...current.draftSearchQueryByPane,
          [paneId]: current.searchQueryByPane[paneId],
        },
      };
      return {
        ...nextState,
        activePaneId: resolveWorkbenchActivePane(nextState, paneId),
      };
    });
  }, [updateZoneDisplayState]);

  const handleClearPaneSearch = useCallback((zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => {
    updateZoneDisplayState(zoneId, (current) => {
      const nextState: WorkbenchZoneDisplayState = {
        ...current,
        draftSearchQueryByPane: {
          ...current.draftSearchQueryByPane,
          [paneId]: "",
        },
        searchQueryByPane: {
          ...current.searchQueryByPane,
          [paneId]: "",
        },
        unifiedSearchQuery: "",
      };
      return {
        ...nextState,
        activePaneId: resolveWorkbenchActivePane(nextState),
      };
    });
  }, [updateZoneDisplayState]);

  const handlePaneSearchQueryChange = useCallback(
    (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice", query: string) => {
      updateZoneDisplayState(zoneId, (current) => {
        const nextState: WorkbenchZoneDisplayState = {
          ...current,
          draftSearchQueryByPane: {
            ...current.draftSearchQueryByPane,
            [paneId]: query,
          },
          searchQueryByPane: {
            ...current.searchQueryByPane,
            [paneId]: query,
          },
          unifiedSearchQuery: "",
        };
        return {
          ...nextState,
          activePaneId: resolveWorkbenchActivePane(nextState, paneId),
        };
      });
    },
    [updateZoneDisplayState],
  );

  const handleColumnFilterChange = useCallback(
    (
      zoneId: "paired" | "open",
      paneId: "oa" | "bank" | "invoice",
      columnKey: string,
      selectedValues: string[],
    ) => {
      updateZoneDisplayState(zoneId, (current) => {
        const nextPaneFilters = {
          ...current.filtersByPaneAndColumn[paneId],
          [columnKey]: selectedValues,
        };
        if (selectedValues.length === 0) {
          delete nextPaneFilters[columnKey];
        }
        const nextState: WorkbenchZoneDisplayState = {
          ...current,
          filtersByPaneAndColumn: {
            ...current.filtersByPaneAndColumn,
            [paneId]: nextPaneFilters,
          },
        };
        return {
          ...nextState,
          activePaneId: resolveWorkbenchActivePane(nextState, paneId),
        };
      });
    },
    [updateZoneDisplayState],
  );

  const handleTogglePaneSort = useCallback(
    (zoneId: "paired" | "open", paneId: "oa" | "bank" | "invoice") => {
      updateZoneDisplayState(zoneId, (current) => {
        const nextDirection = current.sortByPane[paneId] === "desc" ? "asc" : "desc";
        const nextState: WorkbenchZoneDisplayState = {
          ...current,
          sortByPane: {
            oa: paneId === "oa" ? nextDirection : null,
            bank: paneId === "bank" ? nextDirection : null,
            invoice: paneId === "invoice" ? nextDirection : null,
          },
        };
        return {
          ...nextState,
          activePaneId: resolveWorkbenchActivePane(nextState, paneId),
        };
      });
    },
    [updateZoneDisplayState],
  );

  const handlePaneTimeFilterChange = useCallback(
    (
      zoneId: "paired" | "open",
      paneId: "oa" | "bank" | "invoice",
      filter: WorkbenchPaneTimeFilter,
    ) => {
      updateZoneDisplayState(zoneId, (current) => {
        const nextState: WorkbenchZoneDisplayState = {
          ...current,
          timeFilterByPane: {
            ...current.timeFilterByPane,
            [paneId]: filter,
          },
        };
        return {
          ...nextState,
          activePaneId: resolveWorkbenchActivePane(nextState, paneId),
        };
      });
    },
    [updateZoneDisplayState],
  );

  const handleReorderPaneColumns = useCallback((
    paneId: "oa" | "bank" | "invoice",
    activeKey: string,
    overKey: string,
    position: WorkbenchColumnDropPosition,
  ) => {
    setWorkbenchSettings((current) => {
      if (!current) {
        return current;
      }
      const nextLayouts = reorderWorkbenchColumnLayout(current.workbenchColumnLayouts, paneId, activeKey, overKey, position);
      if (nextLayouts === current.workbenchColumnLayouts) {
        return current;
      }

      const nextSettings = {
        ...current,
        workbenchColumnLayouts: nextLayouts,
      };

      const requestId = ++columnLayoutSaveRequestIdRef.current;
      void saveWorkbenchSettings({
        completedProjectIds: nextSettings.projects.completedProjectIds,
        bankAccountMappings: nextSettings.bankAccountMappings,
        allowedUsernames: nextSettings.accessControl.allowedUsernames,
        readonlyExportUsernames: nextSettings.accessControl.readonlyExportUsernames,
        adminUsernames: nextSettings.accessControl.adminUsernames,
        workbenchColumnLayouts: nextLayouts,
        oaRetention: nextSettings.oaRetention,
        oaImport: nextSettings.oaImport,
        oaInvoiceOffset: nextSettings.oaInvoiceOffset,
      }).then((saved) => {
        if (columnLayoutSaveRequestIdRef.current === requestId) {
          setWorkbenchSettings(saved);
        }
      }).catch(() => undefined);

      return nextSettings;
    });
  }, []);

  const refreshWorkbenchDataInBackground = useCallback((month: string) => {
    void loadWorkbenchData(month, undefined, { background: true, includeAuxiliary: false });
  }, []);

  const scheduleOaSyncWorkbenchRefresh = useCallback(() => {
    if (oaSyncRefreshTimeoutRef.current !== null) {
      window.clearTimeout(oaSyncRefreshTimeoutRef.current);
    }
    oaSyncRefreshTimeoutRef.current = window.setTimeout(() => {
      oaSyncRefreshTimeoutRef.current = null;
      refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
    }, OA_SYNC_REFRESH_DEBOUNCE_MS);
  }, [refreshWorkbenchDataInBackground]);

  const oaSyncScopesAffectWorkbench = useCallback((scopes: string[]) => {
    return scopes.includes("all") || scopes.includes(WORKBENCH_VIEW_MONTH) || scopes.includes(currentMonth);
  }, [currentMonth]);

  const applyOaSyncStatus = useCallback((status: WorkbenchOaSyncStatus) => {
    const previousStatus = previousOaSyncStatusRef.current;
    const message = status.message || (status.status === "refreshing" ? "OA 正在同步" : "OA 已同步");

    if (status.status === "refreshing") {
      setOaSyncShellStatus({ level: "pending", reason: message });
    } else if (status.status === "error") {
      setOaSyncShellStatus({ level: "error", reason: message || "OA 同步失败" });
    } else {
      setOaSyncShellStatus({ level: "ok", reason: message });
    }

    if (previousStatus && status.status !== "refreshing") {
      const versionChanged = status.version !== null && status.version !== previousStatus.version;
      const lastSyncedAtChanged = status.lastSyncedAt !== previousStatus.lastSyncedAt;
      const affectedScopes = status.changedScopes.length > 0
        ? status.changedScopes
        : status.dirtyScopes.length > 0
          ? status.dirtyScopes
          : previousStatus.dirtyScopes;
      if ((status.changedScopes.length > 0 || versionChanged || lastSyncedAtChanged) && oaSyncScopesAffectWorkbench(affectedScopes)) {
        scheduleOaSyncWorkbenchRefresh();
      }
    }

    previousOaSyncStatusRef.current = status;
  }, [oaSyncScopesAffectWorkbench, scheduleOaSyncWorkbenchRefresh]);

  const withdrawNoOaSummaryRow = useCallback(async (row: WorkbenchRecord) => {
    const sourceBatchId = readStringMetadata(row.specialMetadata, "source_batch_id");
    if (!sourceBatchId) {
      throw new Error("免OA批次来源缺失，无法撤回。");
    }

    let expectedVersion = readNumberMetadata(row.specialMetadata, "batch_version");
    if (expectedVersion === null) {
      const detail = await fetchNoOaBankBatchDetail(sourceBatchId);
      expectedVersion = typeof detail.batch.version === "number" ? detail.batch.version : null;
    }
    if (expectedVersion === null) {
      throw new Error("免OA批次版本缺失，无法撤回。");
    }

    const result = await withdrawNoOaBankBatch({
      batchId: sourceBatchId,
      expectedVersion,
      reason: "由关联台撤回免OA批次",
    });
    const affectedMonths = result.affectedMonths.length > 0
      ? result.affectedMonths
      : readStringMetadata(row.specialMetadata, "scope_month")
        ? [readStringMetadata(row.specialMetadata, "scope_month") as string]
        : [];
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths,
      source: "workbench_no_oa_withdraw",
    });
    clearPairedSelection();
    return "已撤回免OA批次。";
  }, [clearPairedSelection]);

  async function loadWorkbenchAuxiliaryData(month: string, signal?: AbortSignal) {
    try {
      const [ignoredRows, settings] = await Promise.all([
        fetchIgnoredWorkbenchRows(month, signal),
        fetchWorkbenchSettings(signal),
      ]);
      if (signal?.aborted) {
        return;
      }
      setIgnoredData(ignoredRows);
      setWorkbenchSettings(settings);
    } catch {
      if (signal?.aborted) {
        return;
      }
    }
  }

  async function loadWorkbenchData(
    month: string,
    signal?: AbortSignal,
    options?: {
      background?: boolean;
      includeAuxiliary?: boolean;
      zoneQueries?: Record<"paired" | "open", WorkbenchGroupsPageQuery>;
      propagateError?: boolean;
    },
  ): Promise<WorkbenchInitialPageResult | null> {
    const background = options?.background ?? false;
    const includeAuxiliary = options?.includeAuxiliary ?? false;
    const resolvedZoneQueries = options?.zoneQueries ?? zoneServerPageQueries;

    if (background) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
      setLoadError(null);
      setLoadProgress({
        label: "读 OA 中",
        loadedBytes: 0,
        totalBytes: 0,
        percent: null,
        indeterminate: true,
      });
    }

    try {
      const workbenchPayload = await fetchWorkbenchInitialPage(
        month,
        signal,
        (progress) => {
          setLoadProgress(progress);
        },
        resolvedZoneQueries,
      );
      if (signal?.aborted) {
        return null;
      }
      setWorkbenchData(workbenchPayload.data);
      setLoadedZoneServerPageQueryKeys(createWorkbenchZoneServerPageQueryKeys(resolvedZoneQueries));
      setZonePages(workbenchPayload.pages);
      if (!background) {
        setIsLoading(false);
      } else {
        setIsRefreshing(false);
        setLastActionMessage(null);
      }
      if (includeAuxiliary) {
        void loadWorkbenchAuxiliaryData(month, signal);
      }
      return workbenchPayload;
    } catch (error) {
      if (signal?.aborted) {
        return null;
      }
      const normalizedError = error instanceof Error && error.message
        ? error
        : new Error("工作台数据加载失败，请稍后重试。");
      if (!background) {
        setWorkbenchData(null);
        setLoadedZoneServerPageQueryKeys(null);
        setZonePages(createInitialZonePages());
        setIgnoredData({ month, rows: [] });
        setLoadError(normalizedError.message);
        setIsLoading(false);
      } else {
        setIsRefreshing(false);
        setLastActionMessage(null);
      }
      if (options?.propagateError) {
        throw normalizedError;
      }
      return null;
    }
  }

  const waitForWorkbenchFreshAfterOperation = useCallback(async () => {
    const startedAt = Date.now();
    let lastReadModelStatus = "";

    while (Date.now() - startedAt <= WORKBENCH_OPERATION_FRESH_TIMEOUT_MS) {
      const result = await loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
        background: true,
        includeAuxiliary: false,
        zoneQueries: zoneServerPageQueries,
        propagateError: true,
      });
      const pairedStatus = result?.pages.paired.readModelStatus ?? "unknown";
      const openStatus = result?.pages.open.readModelStatus ?? "unknown";
      lastReadModelStatus = pairedStatus === openStatus ? pairedStatus : `${pairedStatus}/${openStatus}`;
      if (workbenchInitialPageIsFresh(result)) {
        return;
      }
      await delayWorkbenchOperationPoll();
    }

    throw new Error(`关联台最新数据同步超过 ${Math.round(WORKBENCH_OPERATION_FRESH_TIMEOUT_MS / 1000)} 秒，当前状态：${lastReadModelStatus || "unknown"}。`);
  }, [zoneServerPageQueries]);

  const scheduleWorkbenchReadModelReload = useCallback(() => {
    if (workbenchRefreshReloadTimeoutRef.current !== null) {
      window.clearTimeout(workbenchRefreshReloadTimeoutRef.current);
    }
    workbenchRefreshReloadTimeoutRef.current = window.setTimeout(() => {
      workbenchRefreshReloadTimeoutRef.current = null;
      void loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
        background: true,
        includeAuxiliary: false,
        zoneQueries: zoneServerPageQueries,
      });
    }, WORKBENCH_REFRESH_RELOAD_DEBOUNCE_MS);
  }, [zoneServerPageQueries]);

  const applyWorkbenchRefreshStatus = useCallback((status: WorkbenchRefreshStatus) => {
    setWorkbenchRefreshStatus(status);
    const nextVersionKey = workbenchRefreshStatusVersionKey(status);
    const previousVersionKey = lastWorkbenchRefreshVersionRef.current;
    if (nextVersionKey) {
      lastWorkbenchRefreshVersionRef.current = nextVersionKey;
    }
    if (
      status.readModelStatus === "fresh"
      && nextVersionKey
      && previousVersionKey
      && previousVersionKey !== nextVersionKey
    ) {
      scheduleWorkbenchReadModelReload();
    }
  }, [scheduleWorkbenchReadModelReload]);

  const handleLoadMoreZone = useCallback(async (zone: "paired" | "open") => {
    const pageInfo = zonePages[zone];
    if (!workbenchData || !pageInfo.hasMore || loadingMoreZone) {
      return;
    }
    setLoadingMoreZone(zone);
    try {
      const result = await fetchWorkbenchGroupsPage(
        WORKBENCH_VIEW_MONTH,
        zone,
        pageInfo.page + 1,
        pageInfo.pageSize,
        undefined,
        { ...zoneServerPageQueries[zone], detailLevel: "summary" },
      );
      setWorkbenchData((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          [zone]: {
            groups: mergeWorkbenchGroupsById(current[zone].groups, result.groups),
          },
        };
      });
      setZonePages((current) => ({
        ...current,
        [zone]: result.page,
      }));
    } catch {
      setLastActionMessage("加载更多候选组失败，请稍后重试。");
    } finally {
      setLoadingMoreZone(null);
    }
  }, [loadingMoreZone, workbenchData, zonePages, zoneServerPageQueries]);

  const handleEnsureGroupDetail = useCallback(async (zone: "paired" | "open", groupId: string) => {
    const normalizedGroupId = groupId.trim();
    if (!normalizedGroupId) {
      return;
    }
    try {
      const group = await fetchWorkbenchGroupDetail(WORKBENCH_VIEW_MONTH, zone, normalizedGroupId);
      setWorkbenchData((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          [zone]: {
            groups: current[zone].groups.map((candidate) => (
              candidate.id === group.id ? group : candidate
            )),
          },
        };
      });
    } catch {
      setLastActionMessage("加载完整明细失败，请稍后重试。");
      throw new Error("workbench_group_detail_load_failed");
    }
  }, []);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    if (!workbenchData || isLoading) {
      lastZoneServerPageQueryKeyRef.current = zoneServerPageQueryKey;
      return;
    }
    if (lastZoneServerPageQueryKeyRef.current === zoneServerPageQueryKey) {
      return;
    }
    lastZoneServerPageQueryKeyRef.current = zoneServerPageQueryKey;
    const controller = new AbortController();
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, controller.signal, {
      background: true,
      zoneQueries: zoneServerPageQueries,
    });
    return () => controller.abort();
  }, [active, isLoading, workbenchData, zoneServerPageQueries, zoneServerPageQueryKey]);

  useEffect(() => {
    if (!workbenchData) {
      return;
    }
    setSelectionSourceGroups((current) => ({
      paired: mergeWorkbenchGroupsByIdReplacingExisting(current.paired, workbenchData.paired.groups),
      open: mergeWorkbenchGroupsByIdReplacingExisting(current.open, workbenchData.open.groups),
    }));
  }, [workbenchData]);

  useEffect(() => {
    const controller = new AbortController();
    clearSelection();
    setLastActionMessage(null);
    setDetailError(null);
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, controller.signal, { includeAuxiliary: true });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    let isActive = true;
    let pollIntervalId: number | null = null;
    let pollController: AbortController | null = null;
    let subscription: { close: () => void } | null = null;

    const pollRefreshStatus = () => {
      pollController?.abort();
      const controller = new AbortController();
      pollController = controller;
      void fetchWorkbenchRefreshStatus(WORKBENCH_VIEW_MONTH, controller.signal)
        .then((status) => {
          if (!isActive || controller.signal.aborted) {
            return;
          }
          applyWorkbenchRefreshStatus(status);
        })
        .catch(() => undefined);
    };

    const startPolling = () => {
      if (pollIntervalId !== null) {
        return;
      }
      pollRefreshStatus();
      pollIntervalId = window.setInterval(pollRefreshStatus, WORKBENCH_REFRESH_POLL_INTERVAL_MS);
    };

    subscription = subscribeWorkbenchRefreshEvents(
      WORKBENCH_VIEW_MONTH,
      ({ status }) => {
        if (isActive) {
          applyWorkbenchRefreshStatus(status);
        }
      },
      () => {
        subscription?.close();
        subscription = null;
        startPolling();
      },
    );

    if (!subscription) {
      startPolling();
    }

    const handleFocus = () => {
      pollRefreshStatus();
    };
    window.addEventListener("focus", handleFocus);

    return () => {
      isActive = false;
      subscription?.close();
      if (pollIntervalId !== null) {
        window.clearInterval(pollIntervalId);
      }
      pollController?.abort();
      if (workbenchRefreshReloadTimeoutRef.current !== null) {
        window.clearTimeout(workbenchRefreshReloadTimeoutRef.current);
        workbenchRefreshReloadTimeoutRef.current = null;
      }
      window.removeEventListener("focus", handleFocus);
    };
  }, [active, applyWorkbenchRefreshStatus]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    let isActive = true;
    let pollController: AbortController | null = null;

    const pollOaSyncStatus = () => {
      pollController?.abort();
      const controller = new AbortController();
      pollController = controller;
      void fetchWorkbenchOaSyncStatus(controller.signal)
        .then((status) => {
          if (!isActive || controller.signal.aborted) {
            return;
          }
          applyOaSyncStatus(status);
        })
        .catch(() => undefined);
    };

    pollOaSyncStatus();
    const intervalId = window.setInterval(pollOaSyncStatus, OA_SYNC_POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      window.clearInterval(intervalId);
      pollController?.abort();
      if (oaSyncRefreshTimeoutRef.current !== null) {
        window.clearTimeout(oaSyncRefreshTimeoutRef.current);
        oaSyncRefreshTimeoutRef.current = null;
      }
    };
  }, [active, applyOaSyncStatus]);

  const handleRelationUpdated = useCallback(() => {
    refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
  }, [refreshWorkbenchDataInBackground]);
  const handleBankCategoryUpdated = useCallback((event: Event) => {
    const affectedMonths = eventAffectedMonths(event);
    if (
      affectedMonths.length === 0
      || WORKBENCH_VIEW_MONTH === "all"
      || affectedMonths.includes("all")
      || affectedMonths.includes(WORKBENCH_VIEW_MONTH)
      || affectedMonths.includes(currentMonth)
    ) {
      refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
    }
  }, [currentMonth, refreshWorkbenchDataInBackground]);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, handleRelationUpdated);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, handleRelationUpdated);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleBankCategoryUpdated);

  useEffect(() => {
    document.body.classList.toggle("workbench-focus-mode", expandedZoneId !== null);
    document.body.classList.add("workbench-page-mode");
    return () => {
      document.body.classList.remove("workbench-focus-mode");
      document.body.classList.remove("workbench-page-mode");
    };
  }, [expandedZoneId]);

  useEffect(() => {
    if (loadError) {
      setWorkbenchStatus({ level: "error", reason: loadError });
      return;
    }
    if (lastActionMessage) {
      setWorkbenchStatus({ level: "pending", reason: lastActionMessage });
      return;
    }
    if (workbenchData?.oaStatus?.code === "error" && workbenchData.oaStatus.message) {
      setWorkbenchStatus({ level: "error", reason: workbenchData.oaStatus.message });
      return;
    }
    if (workbenchRefreshStatus?.readModelStatus === "failed" || workbenchRefreshStatus?.readModelStatus === "unavailable") {
      setWorkbenchStatus({
        level: "error",
        reason: workbenchRefreshStatusMessage(workbenchRefreshStatus) ?? "关联台刷新失败",
      });
      return;
    }
    if (oaSyncShellStatus) {
      setWorkbenchStatus(oaSyncShellStatus);
      return;
    }
    if (isLoading || isRefreshing) {
      const reason = loadProgress.percent === null
        ? `${loadProgress.label}...`
        : `${loadProgress.label} ${loadProgress.percent}%`;
      setWorkbenchStatus({ level: "pending", reason });
      return;
    }
    if (workbenchData?.oaStatus?.message) {
      setWorkbenchStatus({
        level: workbenchData.oaStatus.code === "error" ? "error" : workbenchData.oaStatus.code === "ready" ? "ok" : "pending",
        reason: workbenchData.oaStatus.message,
      });
      return;
    }
    setWorkbenchStatus(null);
  }, [
    isLoading,
    isRefreshing,
    lastActionMessage,
    loadError,
    loadProgress.label,
    loadProgress.percent,
    oaSyncShellStatus,
    setWorkbenchStatus,
    workbenchRefreshStatus,
    workbenchData?.oaStatus?.code,
    workbenchData?.oaStatus?.message,
  ]);

  useEffect(() => () => setWorkbenchStatus(null), [setWorkbenchStatus]);

  const processedExceptionRows = useMemo(
    () => flattenGroups(collectProcessedExceptionGroups(workbenchData?.open.groups ?? [])),
    [workbenchData],
  );

  const visibleOpenGroups = useMemo(
    () => removeProcessedExceptionRows(workbenchData?.open.groups ?? []),
    [workbenchData],
  );

  const processedExceptionGroups = useMemo(
    () => collectProcessedExceptionGroups(workbenchData?.open.groups ?? []),
    [workbenchData],
  );

  const displayPairedGroups = useMemo(
    () => buildWorkbenchDisplayGroups(
      workbenchData?.paired.groups ?? [],
      deferredPairedDisplayState,
      {
        serverFiltered:
          loadedZoneServerPageQueryKeys?.paired === zoneServerPageQueryKeys.paired
          && hasWorkbenchServerPageCriteria(pairedServerPageQuery),
      },
    ),
    [
      deferredPairedDisplayState,
      loadedZoneServerPageQueryKeys?.paired,
      pairedServerPageQuery,
      workbenchData,
      zoneServerPageQueryKeys.paired,
    ],
  );

  const displayOpenGroups = useMemo(
    () => buildWorkbenchDisplayGroups(
      visibleOpenGroups,
      deferredOpenDisplayState,
      {
        serverFiltered:
          loadedZoneServerPageQueryKeys?.open === zoneServerPageQueryKeys.open
          && hasWorkbenchServerPageCriteria(openServerPageQuery),
      },
    ),
    [
      deferredOpenDisplayState,
      loadedZoneServerPageQueryKeys?.open,
      openServerPageQuery,
      visibleOpenGroups,
      zoneServerPageQueryKeys.open,
    ],
  );

  const sourceAllGroups = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchCandidateGroup[];
    }
    return [...workbenchData.paired.groups, ...visibleOpenGroups];
  }, [visibleOpenGroups, workbenchData]);

  const sourceAllRows = useMemo(() => flattenGroups(sourceAllGroups), [sourceAllGroups]);
  const openSelectionSourceGroups = useMemo(
    () => mergeWorkbenchGroupsByIdReplacingExisting(selectionSourceGroups.open, workbenchData?.open.groups ?? []),
    [selectionSourceGroups.open, workbenchData?.open.groups],
  );
  const pairedSelectionSourceGroups = useMemo(
    () => mergeWorkbenchGroupsByIdReplacingExisting(selectionSourceGroups.paired, workbenchData?.paired.groups ?? []),
    [selectionSourceGroups.paired, workbenchData?.paired.groups],
  );

  const openSelectionContext = useMemo(
    () => buildWorkbenchSelectionContext({
      explicitRows: explicitSelectedOpenRows,
      sourceGroups: openSelectionSourceGroups,
      zoneId: "open",
    }),
    [explicitSelectedOpenRows, openSelectionSourceGroups],
  );

  const pairedSelectionContext = useMemo(
    () => buildWorkbenchSelectionContext({
      explicitRows: explicitSelectedPairedRows,
      sourceGroups: pairedSelectionSourceGroups,
      zoneId: "paired",
    }),
    [explicitSelectedPairedRows, pairedSelectionSourceGroups],
  );

  const selectedOpenRows = openSelectionContext.includedRows;
  const selectedPairedRows = pairedSelectionContext.includedRows;
  const explicitOpenRows = openSelectionContext.explicitRows;
  const openSelectionSummary = openSelectionContext.summary;
  const pairedSelectionSummary = pairedSelectionContext.summary;
  const contextualOpenRowIds = openSelectionContext.relatedRowIdSet;
  const contextualPairedRowIds = pairedSelectionContext.relatedRowIdSet;
  const getWorkbenchRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "open") => {
    const explicitState = getRowState(row, zoneId);
    if (explicitState !== "idle") {
      return explicitState;
    }
    return (zoneId === "open" ? contextualOpenRowIds : contextualPairedRowIds).has(row.id) ? "related" : "idle";
  }, [contextualOpenRowIds, contextualPairedRowIds, getRowState]);

  const canConfirmOpenSelection = openSelectionSummary.bank > 0 && openSelectionSummary.oa + openSelectionSummary.invoice > 0;
  const canHandleOpenSelectionException = openSelectionSummary.total > 0;
  const selectedOpenGroupsForUnifiedAction = useMemo(() => {
    const selectedRowIdSet = new Set(openSelectionContext.includedRowIds);
    return openSelectionSourceGroups.filter((group) => flattenGroups([group]).some((row) => selectedRowIdSet.has(row.id)));
  }, [openSelectionContext.includedRowIds, openSelectionSourceGroups]);
  const selectedPairedGroupsForUnifiedAction = useMemo(() => {
    const selectedRowIdSet = new Set(pairedSelectionContext.includedRowIds);
    return pairedSelectionSourceGroups.filter((group) => flattenGroups([group]).some((row) => selectedRowIdSet.has(row.id)));
  }, [pairedSelectionContext.includedRowIds, pairedSelectionSourceGroups]);
  const canWithdrawOpenSelection = useMemo(() => {
    if (openSelectionSummary.total === 0) {
      return false;
    }
    return selectedOpenGroupsForUnifiedAction.length === 1;
  }, [openSelectionSummary.total, selectedOpenGroupsForUnifiedAction.length]);
  const isOpenConfirmSelectionDisabled = !canConfirmOpenSelection;
  const isOpenExceptionSelectionDisabled = openSelectionSummary.total < 1;
  const isPairedCancelSelectionDisabled = pairedSelectionSummary.total < 1;
  const isOpenWithdrawSelectionDisabled = openSelectionSummary.total < 1;

  const collectCaseRowIds = useCallback((row: WorkbenchRecord) => {
    const containingGroup = sourceAllGroups.find((group) =>
      [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice].some((candidate) => candidate.id === row.id),
    );
    if (containingGroup) {
      return [...containingGroup.rows.oa, ...containingGroup.rows.bank, ...containingGroup.rows.invoice].map(
        (candidate) => candidate.id,
      );
    }
    if (!row.caseId) {
      return [row.id];
    }
    const relatedIds = sourceAllRows.filter((candidate) => candidate.caseId === row.caseId).map((candidate) => candidate.id);
    return relatedIds.length > 0 ? relatedIds : [row.id];
  }, [sourceAllGroups, sourceAllRows]);

  const handleOpenDetail = useCallback(async (row: WorkbenchRecord) => {
    setDetailError(null);
    setIsDetailLoading(true);
    openDetail(row);
    try {
      const detailedRow = await fetchWorkbenchRowDetail(row.id, { month: WORKBENCH_VIEW_MONTH });
      replaceDetailRow(detailedRow);
    } catch {
      setDetailError("详情加载失败，请稍后重试。");
    } finally {
      setIsDetailLoading(false);
    }
  }, [openDetail, replaceDetailRow]);

  const handleCloseDetail = useCallback(() => {
    setDetailError(null);
    setIsDetailLoading(false);
    closeDetail();
  }, [closeDetail]);

  const handleCloseActionDialog = () => {
    setActionDialog((current) => (current?.phase === "result" ? null : current));
  };

  const handleOpenIgnoredModal = () => {
    setIgnoredModalOpen(true);
  };

  const handleCloseIgnoredModal = () => {
    setIgnoredModalOpen(false);
  };

  const handleOpenProcessedExceptionsModal = () => {
    setProcessedExceptionsModalOpen(true);
  };

  const handleCloseProcessedExceptionsModal = () => {
    setProcessedExceptionsModalOpen(false);
  };

  const openActionResultDialog = useCallback((message: string, title = "操作提示") => {
    setActionDialog({
      phase: "result",
      title,
      message,
    });
  }, []);

  const ensureCanWriteWorkbench = useCallback(() => {
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
      return false;
    }
    if (healthStatus.blocksMutations) {
      openActionResultDialog("登录已失效或系统不可用，请返回 OA 系统重新进入。");
      return false;
    }
    if (isOaSyncWriteBlocked) {
      openActionResultDialog("OA 正在同步，请刷新完成后再操作。");
      return false;
    }
    return true;
  }, [canMutateData, healthStatus.blocksMutations, isOaSyncWriteBlocked, openActionResultDialog]);

  const openCancelProcessedExceptionDialog = useCallback((row: WorkbenchRecord) => {
    const group = processedExceptionGroups.find((candidateGroup) =>
      [...candidateGroup.rows.oa, ...candidateGroup.rows.bank, ...candidateGroup.rows.invoice].some(
        (candidateRow) => candidateRow.id === row.id,
      ),
    );
    if (!group) {
      openActionResultDialog("未找到对应的异常分组。");
      return;
    }
    setProcessedExceptionsModalOpen(false);
    setCancelProcessedExceptionDialog({ group });
  }, [openActionResultDialog, processedExceptionGroups]);

  const handleCloseCancelProcessedExceptionDialog = () => {
    setCancelProcessedExceptionDialog(null);
  };

  const openWorkbenchExceptionDialog = useCallback((rows: WorkbenchRecord[]) => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (rows.length === 0) {
      openActionResultDialog("请先选择待处理记录。");
      return;
    }
    handleCloseDetail();
    setWorkbenchExceptionDialog({ rows });
  }, [ensureCanWriteWorkbench, handleCloseDetail, openActionResultDialog]);

  const handleCloseWorkbenchExceptionDialog = () => {
    setWorkbenchExceptionDialog(null);
  };

  const applyWorkbenchOperationProjection = useCallback((result: WorkbenchActionResult) => {
    const projection = result.operationProjection;
    if (!hasOperationProjection(projection)) {
      return false;
    }
    const affectedRowIds = operationProjectionAffectedRowIds(result);
    setWorkbenchData((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        paired: {
          groups: applyOperationProjectionToGroups(
            current.paired.groups,
            projection?.after.pairedGroups ?? [],
            affectedRowIds,
          ),
        },
        open: {
          groups: applyOperationProjectionToGroups(
            current.open.groups,
            projection?.after.openGroups ?? [],
            affectedRowIds,
          ),
        },
      };
    });
    setSelectionSourceGroups((current) => ({
      paired: applyOperationProjectionToGroups(
        current.paired,
        projection?.after.pairedGroups ?? [],
        affectedRowIds,
      ),
      open: applyOperationProjectionToGroups(
        current.open,
        projection?.after.openGroups ?? [],
        affectedRowIds,
      ),
    }));
    return true;
  }, []);

  const runBlockingAction = useCallback(async ({
    loadingMessage,
    action,
  }: {
    loadingMessage: string;
    action: () => Promise<string | WorkbenchActionResult>;
  }) => {
    handleCloseDetail();
    const outcome = await runOperation({
      loadingMessage,
      action: async ({ setMessage }) => {
        const result = await action();
        const actionResult = typeof result === "string" ? null : result;
        const targets = actionFreshnessTargets(actionResult);
        if (targets.length > 0) {
          setMessage("正在同步关联台最新数据...");
          await waitForOperationFreshness(
            targets,
            { timeoutMs: WORKBENCH_OPERATION_FRESH_TIMEOUT_MS },
          );
        }
        if (actionResult && applyWorkbenchOperationProjection(actionResult)) {
          refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
        } else {
          await waitForWorkbenchFreshAfterOperation();
        }
        return actionResultMessage(result);
      },
      errorMessage: actionErrorMessage,
    });
    if (outcome.status === "success") {
      setLastActionMessage(outcome.value);
    }
  }, [applyWorkbenchOperationProjection, handleCloseDetail, refreshWorkbenchDataInBackground, runOperation, waitForWorkbenchFreshAfterOperation]);

  const openRelationPreviewErrorDialog = useCallback((error: unknown) => {
    openActionResultDialog(actionErrorMessage(error), "操作失败");
  }, [openActionResultDialog]);

  const handleWorkbenchExceptionApplied = useCallback((result: WorkbenchExceptionApplyResult) => {
    clearOpenSelection();
    if (result.workbenchRefreshRequired) {
      refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
    }
    setLastActionMessage(result.message ?? "已提交统一异常处理。");
  }, [clearOpenSelection, refreshWorkbenchDataInBackground]);

  const handleRowAction = useCallback(async (row: WorkbenchRecord, action: WorkbenchInlineAction) => {
    if (action === "relation-status") {
      openActionResultDialog(`当前关联情况：${row.status}`, "关联情况");
      return;
    }

    if (!ensureCanWriteWorkbench()) {
      return;
    }

    if (action === "confirm-match") {
      const rowIds = collectCaseRowIds(row);
      const rowsById = new Map(sourceAllRows.map((candidate) => [candidate.id, candidate]));
      try {
        await openConfirmPreview(rowIds.map((rowId) => rowsById.get(rowId)).filter((candidate): candidate is WorkbenchRecord => Boolean(candidate)));
      } catch (error) {
        openRelationPreviewErrorDialog(error);
      }
      return;
    }

    if (action === "flag-exception") {
      openWorkbenchExceptionDialog([row]);
      return;
    }

    if (action === "ignore-row") {
      await runBlockingAction({
        loadingMessage: "正在忽略记录...",
        action: async () => {
          const result = await ignoreWorkbenchRow({
            month: WORKBENCH_VIEW_MONTH,
            rowId: row.id,
            comment: `由关联台忽略发票：${row.id}`,
          });
          return result;
        },
      });
      return;
    }

    if (action === "confirm-cash-pass-through") {
      const rowIds = collectCaseRowIds(row);
      await runBlockingAction({
        loadingMessage: "正在确认过账...",
        action: async () => {
          const result = await confirmWorkbenchCashPassThrough({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            note: "由关联台确认现金往来过账",
          });
          return result;
        },
      });
      return;
    }

    if (action === "confirm-cash-ticket-purchase") {
      setCashTicketPurchaseDialog({
        rowIds: collectCaseRowIds(row),
        cashAmount: normalizedAmountForInput(row.amount),
      });
      return;
    }

    if (action === "cancel-cash-special") {
      const rowIds = collectCaseRowIds(row);
      await runBlockingAction({
        loadingMessage: "正在取消现金处理...",
        action: async () => {
          const result = await cancelWorkbenchCashSpecial({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            note: "由关联台取消现金往来特殊处理",
          });
          return result;
        },
      });
      return;
    }

    if (action === "unlink") {
      if (isNoOaSummaryRow(row)) {
        await runBlockingAction({
          loadingMessage: "正在撤回免OA批次...",
          action: () => withdrawNoOaSummaryRow(row),
        });
        return;
      }
      const rowIds = collectCaseRowIds(row);
      const rowsById = new Map(sourceAllRows.map((candidate) => [candidate.id, candidate]));
      try {
        await openWithdrawPreview(rowIds.map((rowId) => rowsById.get(rowId)).filter((candidate): candidate is WorkbenchRecord => Boolean(candidate)));
      } catch (error) {
        openRelationPreviewErrorDialog(error);
      }
      return;
    }

    if (action === "handle-exception") {
      openWorkbenchExceptionDialog([row]);
      return;
    }

    if (action === "cancel-exception") {
      openCancelProcessedExceptionDialog(row);
    }
  }, [
    clearOpenSelection,
    collectCaseRowIds,
    ensureCanWriteWorkbench,
    openActionResultDialog,
    openCancelProcessedExceptionDialog,
    openWorkbenchExceptionDialog,
    refreshWorkbenchDataInBackground,
    runBlockingAction,
    withdrawNoOaSummaryRow,
    sourceAllRows,
    openRelationPreviewErrorDialog,
  ]);

  const handleCloseCashTicketPurchaseDialog = useCallback(() => {
    setCashTicketPurchaseDialog(null);
  }, []);

  const handleSubmitCashTicketPurchase = useCallback(async ({
    cashAmount,
    ticketCostAmount,
    projectName,
    expenseType,
    expenseContent,
    note,
  }: {
    cashAmount: string;
    ticketCostAmount: string;
    projectName: string;
    expenseType: string;
    expenseContent: string;
    note: string;
  }) => {
    if (!cashTicketPurchaseDialog || !ensureCanWriteWorkbench()) {
      return;
    }
    const { rowIds } = cashTicketPurchaseDialog;
    setCashTicketPurchaseDialog(null);
    await runBlockingAction({
      loadingMessage: "正在确认买票成本...",
      action: async () => {
        const result = await confirmWorkbenchCashTicketPurchase({
          month: WORKBENCH_VIEW_MONTH,
          rowIds,
          cashAmount,
          ticketCostAmount,
          projectName,
          expenseType,
          expenseContent,
          note,
        });
        return result;
      },
    });
  }, [cashTicketPurchaseDialog, ensureCanWriteWorkbench, runBlockingAction]);

  const handleSelectRow = useCallback((row: WorkbenchRecord, zoneId: "paired" | "open") => {
    if (zoneId === "open") {
      toggleOpenRowSelection(row);
      return;
    }
    togglePairedRowSelection(row);
  }, [toggleOpenRowSelection, togglePairedRowSelection]);

  const resolveSelectedCaseId = (rows: WorkbenchRecord[]) => {
    const caseIds = Array.from(new Set(rows.map((row) => row.caseId).filter((caseId): caseId is string => Boolean(caseId))));
    return caseIds.length === 1 ? caseIds[0] : undefined;
  };

  const openConfirmPreview = async (rows: WorkbenchRecord[]) => {
    const rowIds = rows.map((row) => row.id);
    const caseId = resolveSelectedCaseId(rows);
    const preview = await previewWorkbenchConfirmLink({
      month: WORKBENCH_VIEW_MONTH,
      rowIds,
      caseId,
    });
    setRelationPreviewDialog({ preview, rowIds, caseId });
  };

  const openWithdrawPreview = async (rows: WorkbenchRecord[]) => {
    const rowIds = rows.map((row) => row.id);
    const preview = await previewWorkbenchWithdrawLink({
      month: WORKBENCH_VIEW_MONTH,
      rowIds,
    });
    setRelationPreviewDialog({ preview, rowIds, caseId: resolveSelectedCaseId(rows) });
  };

  const handleSubmitRelationPreview = async (note: string) => {
    if (!relationPreviewDialog) {
      return;
    }
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    const { preview, rowIds, caseId } = relationPreviewDialog;
    setRelationPreviewDialog(null);
    if (preview.operation === "confirm_link") {
      await runBlockingAction({
        loadingMessage: "正在确认关联...",
        action: async () => {
          const result = await confirmWorkbenchLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            caseId,
            note,
          });
          clearOpenSelection();
          emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
            affectedMonths: actionAffectedMonths(result),
            source: "workbench_confirm_link",
          });
          return result;
        },
      });
      return;
    }

    await runBlockingAction({
      loadingMessage: "正在撤回关联...",
      action: async () => {
        const result = await withdrawWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds,
          note,
          operationType: preview.operationType === "split_candidate" ? "split_candidate" : "withdraw_relation",
          previewId: preview.previewId,
          expectedVersions: preview.submitExpectedVersions,
        });
        clearPairedSelection();
        clearOpenSelection();
        emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
          affectedMonths: actionAffectedMonths(result),
          source: preview.operation === "split_candidate" ? "workbench_split_candidate" : "workbench_withdraw_link",
        });
        return result;
      },
    });
  };

  const handleConfirmOpenSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (openSelectionSummary.total === 0) {
      openActionResultDialog("请先选择待处理记录。");
      return;
    }
    if (!canConfirmOpenSelection) {
      openActionResultDialog("确认关联至少需要选择 1 条银行流水，并同时选择 OA 或发票。");
      return;
    }
    try {
      await openConfirmPreview(selectedOpenRows);
    } catch (error) {
      openRelationPreviewErrorDialog(error);
    }
  };

  const handleWithdrawOpenSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (!canWithdrawOpenSelection) {
      openActionResultDialog(
        selectedOpenGroupsForUnifiedAction.length > 1
          ? "一次只能处理一个关联组。"
          : "请先选择一个待处理关联组。",
      );
      return;
    }
    try {
      await openWithdrawPreview(flattenGroups(selectedOpenGroupsForUnifiedAction));
    } catch (error) {
      openRelationPreviewErrorDialog(error);
    }
  };

  const handleClearOpenSelection = () => {
    if (openSelectionSummary.total === 0) {
      setLastActionMessage("当前没有已选记录。");
      return;
    }
    clearOpenSelection();
    setLastActionMessage("已清空当前选择。");
  };

  const handleOpenSelectionException = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (!canHandleOpenSelectionException) {
      openActionResultDialog("请先选择待处理记录。");
      return;
    }
    openWorkbenchExceptionDialog(explicitOpenRows);
  };

  const handleClearPairedSelection = () => {
    if (pairedSelectionSummary.total === 0) {
      setLastActionMessage("当前没有已选记录。");
      return;
    }
    clearPairedSelection();
    setLastActionMessage("已清空当前选择。");
  };

  const handleCancelPairedSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (pairedSelectionSummary.total === 0) {
      openActionResultDialog("请先选择已配对记录。");
      return;
    }

    if (selectedPairedRows.length === 0) {
      openActionResultDialog("请先选择已配对记录。");
      return;
    }
    if (selectedPairedGroupsForUnifiedAction.length > 1) {
      openActionResultDialog("一次只能处理一个关联组。");
      return;
    }
    const selectedNoOaSummaryRows = uniqueNoOaBatchRows(selectedPairedRows.filter(isNoOaSummaryRow));
    if (selectedNoOaSummaryRows.length > 0) {
      await runBlockingAction({
        loadingMessage: "正在撤回免OA批次...",
        action: async () => {
          for (const row of selectedNoOaSummaryRows) {
            await withdrawNoOaSummaryRow(row);
          }
          return selectedNoOaSummaryRows.length === 1 ? "已撤回免OA批次。" : `已撤回 ${selectedNoOaSummaryRows.length} 个免OA批次。`;
        },
      });
      return;
    }
    const selectedPairedRowIds = new Set(selectedPairedRows.map((row) => row.id));
    const selectedRelationRows = pairedSelectionSourceGroups
      .filter((group) => group.canWithdraw && flattenGroups([group]).some((row) => selectedPairedRowIds.has(row.id)))
      .flatMap((group) => flattenGroups([group]));
    try {
      await openWithdrawPreview(selectedRelationRows.length > 0 ? selectedRelationRows : selectedPairedRows);
    } catch (error) {
      openRelationPreviewErrorDialog(error);
    }
  };

  const handleUnignoreRow = async (row: WorkbenchRecord) => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    setIgnoredModalOpen(false);
    await runBlockingAction({
      loadingMessage: "正在撤回忽略...",
      action: async () => {
        const result = await unignoreWorkbenchRow({
          month: WORKBENCH_VIEW_MONTH,
          rowId: row.id,
        });
        return result;
      },
    });
  };

  const handleConfirmCancelProcessedException = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (!cancelProcessedExceptionDialog) {
      return;
    }
    const rows = [
      ...cancelProcessedExceptionDialog.group.rows.oa,
      ...cancelProcessedExceptionDialog.group.rows.bank,
      ...cancelProcessedExceptionDialog.group.rows.invoice,
    ];
    setCancelProcessedExceptionDialog(null);
    await runBlockingAction({
      loadingMessage: "正在取消异常处理...",
      action: async () => {
        const result = await cancelWorkbenchException({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: rows.map((row) => row.id),
          comment: "由已处理异常弹窗撤回异常处理",
        });
        return result;
      },
    });
  };

  const pairedPanes = useMemo<WorkbenchPane[]>(
    () => {
      const paneRows = buildWorkbenchPaneRows(displayPairedGroups);
      const totals = zonePages.paired.rowCounts.rows > 0
        ? zonePages.paired.rowCounts
        : workbenchData?.summary.zoneCounts.paired;
      return [
        { id: "oa", title: "OA", rows: paneRows.oa, totalRows: totals?.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank, totalRows: totals?.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice, totalRows: totals?.invoice },
      ];
    },
    [displayPairedGroups, workbenchData?.summary.zoneCounts.paired, zonePages.paired.rowCounts],
  );

  const openPanes = useMemo<WorkbenchPane[]>(
    () => {
      const paneRows = buildWorkbenchPaneRows(displayOpenGroups);
      const totals = zonePages.open.rowCounts.rows > 0
        ? zonePages.open.rowCounts
        : workbenchData?.summary.zoneCounts.open;
      return [
        { id: "oa", title: "OA", rows: paneRows.oa, totalRows: totals?.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank, totalRows: totals?.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice, totalRows: totals?.invoice },
      ];
    },
    [displayOpenGroups, workbenchData?.summary.zoneCounts.open, zonePages.open.rowCounts],
  );

  const togglePairedExpand = useCallback(() => {
    setExpandedZoneId((current) => (current === "paired" ? null : "paired"));
  }, []);

  const toggleOpenExpand = useCallback(() => {
    setExpandedZoneId((current) => (current === "open" ? null : "open"));
  }, []);

  const openAuxiliaryHeaderActions = useMemo(
    () => [
      {
        label: `已处理异常${processedExceptionRows.length}项`,
        onClick: handleOpenProcessedExceptionsModal,
        tone: "danger" as const,
      },
      {
        label: `已忽略${ignoredData.rows.length}项`,
        onClick: handleOpenIgnoredModal,
        tone: "warning" as const,
      },
    ],
    [handleOpenIgnoredModal, handleOpenProcessedExceptionsModal, ignoredData.rows.length, processedExceptionRows.length],
  );

  const isEmpty = (workbenchData?.summary.totalCount ?? 0) === 0;
  const oaStatus = workbenchData?.oaStatus ?? null;
  const isOaReady = oaStatus?.code === "ready";
  const oaStatusPanelMessage = oaStatus && !isOaReady ? `${oaStatus.message}，本次结果未包含完整 OA 数据。` : null;
  const isPairedVisible = expandedZoneId === null || expandedZoneId === "paired";
  const isOpenVisible = expandedZoneId === null || expandedZoneId === "open";
  const pairedZoneItemCount = resolveZoneItemCount(zonePages.paired, workbenchData?.summary.zoneCounts.paired);
  const openZoneItemCount = resolveZoneItemCount(zonePages.open, workbenchData?.summary.zoneCounts.open);
  const workbenchRefreshPanelMessage = workbenchRefreshStatusMessage(workbenchRefreshStatus);
  const workbenchRefreshPanelTone = workbenchRefreshStatusPanelTone(workbenchRefreshStatus);

  const pairedZoneElement = (
    <WorkbenchZone
      canMutateData={canWriteWorkbench}
      getRowState={getWorkbenchRowState}
      isExpanded={expandedZoneId === "paired"}
      isVisible={isPairedVisible}
      onClearSelection={handleClearPairedSelection}
      onOpenDetail={handleOpenDetail}
      onEnsureGroupDetail={handleEnsureGroupDetail}
      onLoadMore={() => handleLoadMoreZone("paired")}
      onPrimarySelectionAction={handleCancelPairedSelection}
      primarySelectionActionDisabled={isPairedCancelSelectionDisabled || !canWriteWorkbench}
      onRowAction={handleRowAction}
      onClearPaneSearch={handleClearPaneSearch}
      onClosePaneSearch={handleClosePaneSearch}
      onSelectRow={handleSelectRow}
      onToggleExpand={togglePairedExpand}
      displayState={pairedDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onPaneSearchQueryChange={handlePaneSearchQueryChange}
      onTogglePaneSearch={handleTogglePaneSearch}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayPairedGroups}
      sourceGroups={workbenchData?.paired.groups ?? []}
      invoiceInventory={workbenchData?.invoiceInventory}
      loadingMore={loadingMoreZone === "paired"}
      pageInfo={zonePages.paired}
      highlightedRowId={null}
      panes={pairedPanes}
      primarySelectionActionLabel="撤回关联"
      selectionSummary={pairedSelectionSummary}
      title={`已配对 ${pairedZoneItemCount} 项`}
      tone="success"
      zoneId="paired"
    />
  );

  const openZoneElement = (
    <WorkbenchZone
      auxiliaryHeaderActions={openAuxiliaryHeaderActions}
      canMutateData={canWriteWorkbench}
      getRowState={getWorkbenchRowState}
      isExpanded={expandedZoneId === "open"}
      isVisible={isOpenVisible}
      onClearSelection={handleClearOpenSelection}
      onOpenDetail={handleOpenDetail}
      onEnsureGroupDetail={handleEnsureGroupDetail}
      onLoadMore={() => handleLoadMoreZone("open")}
      onPrimarySelectionAction={handleConfirmOpenSelection}
      primarySelectionActionDisabled={isOpenConfirmSelectionDisabled || !canWriteWorkbench}
      onRowAction={handleRowAction}
      onClearPaneSearch={handleClearPaneSearch}
      onClosePaneSearch={handleClosePaneSearch}
      onSelectRow={handleSelectRow}
      onSecondarySelectionAction={handleOpenSelectionException}
      secondarySelectionActionDisabled={isOpenExceptionSelectionDisabled || !canWriteWorkbench}
      onTertiarySelectionAction={handleWithdrawOpenSelection}
      tertiarySelectionActionDisabled={isOpenWithdrawSelectionDisabled || !canWriteWorkbench}
      onToggleExpand={toggleOpenExpand}
      displayState={openDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onPaneSearchQueryChange={handlePaneSearchQueryChange}
      onTogglePaneSearch={handleTogglePaneSearch}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayOpenGroups}
      sourceGroups={visibleOpenGroups}
      invoiceInventory={workbenchData?.invoiceInventory}
      loadingMore={loadingMoreZone === "open"}
      pageInfo={zonePages.open}
      highlightedRowId={null}
      panes={openPanes}
      primarySelectionActionLabel="确认关联"
      secondarySelectionActionLabel="异常处理"
      tertiarySelectionActionLabel="撤回关联"
      selectionSummary={openSelectionSummary}
      title={`未配对 ${openZoneItemCount} 项`}
      tone="warning"
      zoneId="open"
    />
  );

  return (
    <div className="workbench-shell">
      <div className={`page-stack${expandedZoneId ? " zone-expanded-layout" : ""}`}>
        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {!loadError && oaStatusPanelMessage ? (
          <div className={`state-panel${oaStatus?.code === "error" ? " error" : ""}`}>{oaStatusPanelMessage}</div>
        ) : null}
        {!loadError && workbenchRefreshPanelMessage ? (
          <div className={`state-panel workbench-refresh-status${workbenchRefreshPanelTone}`}>
            {workbenchRefreshPanelMessage}
          </div>
        ) : null}
        {!isLoading && !loadError && isEmpty && isOaReady ? (
          <div className="state-panel">当前没有可展示的 OA / 银行流水 / 发票记录。</div>
        ) : null}

        {!loadError ? (
          <div className="workbench-zone-stack">
            <div
              className={`workbench-zone-slot workbench-zone-slot-top${isPairedVisible ? "" : " workbench-zone-slot-hidden"}`}
            >
              {pairedZoneElement}
            </div>
            <div
              className={`workbench-zone-slot workbench-zone-slot-bottom${isOpenVisible ? "" : " workbench-zone-slot-hidden"}`}
            >
              {openZoneElement}
            </div>
          </div>
        ) : null}
      </div>

      <DetailDrawer error={detailError} loading={isDetailLoading} row={detailRow} onClose={handleCloseDetail} />
      {relationPreviewDialog ? (
        <RelationPreviewDialog
          preview={relationPreviewDialog.preview}
          columnLayouts={workbenchSettings?.workbenchColumnLayouts}
          onClose={() => setRelationPreviewDialog(null)}
          onSubmit={handleSubmitRelationPreview}
        />
      ) : null}
      {actionDialog ? (
        <ActionStatusModal
          message={actionDialog.message}
          phase={actionDialog.phase}
          title={actionDialog.title}
          onAcknowledge={handleCloseActionDialog}
        />
      ) : null}
      {ignoredModalOpen ? (
        <IgnoredItemsModal
          canMutateData={canWriteWorkbench}
          highlightedRowId={null}
          rows={ignoredData.rows}
          onClose={handleCloseIgnoredModal}
          onUnignore={handleUnignoreRow}
        />
      ) : null}
      {processedExceptionsModalOpen ? (
        <ProcessedExceptionsModal
          canMutateData={canWriteWorkbench}
          groups={processedExceptionGroups}
          highlightedRowId={null}
          panes={[
            { id: "oa", title: "OA", rows: processedExceptionGroups.flatMap((group) => group.rows.oa) },
            { id: "bank", title: "银行流水", rows: processedExceptionGroups.flatMap((group) => group.rows.bank) },
            { id: "invoice", title: "进销项发票", rows: processedExceptionGroups.flatMap((group) => group.rows.invoice) },
          ]}
          onClose={handleCloseProcessedExceptionsModal}
          onCancelException={openCancelProcessedExceptionDialog}
        />
      ) : null}
      {cancelProcessedExceptionDialog ? (
        <CancelProcessedExceptionModal
          affectedCount={
            cancelProcessedExceptionDialog.group.rows.oa.length
            + cancelProcessedExceptionDialog.group.rows.bank.length
            + cancelProcessedExceptionDialog.group.rows.invoice.length
          }
          onClose={handleCloseCancelProcessedExceptionDialog}
          onConfirm={handleConfirmCancelProcessedException}
        />
      ) : null}
      {workbenchExceptionDialog ? (
        <WorkbenchExceptionModal
          month={WORKBENCH_VIEW_MONTH}
          rows={workbenchExceptionDialog.rows}
          onApplied={handleWorkbenchExceptionApplied}
          onClose={handleCloseWorkbenchExceptionDialog}
        />
      ) : null}
      {cashTicketPurchaseDialog ? (
        <CashTicketPurchaseModal
          defaultCashAmount={cashTicketPurchaseDialog.cashAmount}
          onClose={handleCloseCashTicketPurchaseDialog}
          onSubmit={handleSubmitCashTicketPurchase}
        />
      ) : null}
    </div>
  );
}

function CashTicketPurchaseModal({
  defaultCashAmount,
  onClose,
  onSubmit,
}: {
  defaultCashAmount: string;
  onClose: () => void;
  onSubmit: (payload: {
    cashAmount: string;
    ticketCostAmount: string;
    projectName: string;
    expenseType: string;
    expenseContent: string;
    note: string;
  }) => void;
}) {
  const [cashAmount, setCashAmount] = useState(defaultCashAmount);
  const [ticketCostAmount, setTicketCostAmount] = useState("");
  const [projectName, setProjectName] = useState("");
  const [expenseType, setExpenseType] = useState("现金往来");
  const [expenseContent, setExpenseContent] = useState("买票成本");
  const [note, setNote] = useState("");
  const canSubmit = Number(normalizedAmountForInput(ticketCostAmount)) > 0 && projectName.trim().length > 0;

  return (
    <div className="detail-modal-backdrop">
      <button aria-label="关闭买票确认" className="detail-modal-backdrop-foreground" type="button" onClick={onClose} />
      <section aria-label="确认买票成本" aria-modal="true" className="detail-modal" role="dialog">
        <header className="detail-modal-header">
          <div>
            <div className="modal-eyebrow">现金往来</div>
            <h2>确认买票情况</h2>
          </div>
          <button aria-label="关闭买票确认" className="detail-close-btn" type="button" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="relation-preview-message">
          此操作只把买票成本计入成本统计，流水全额不会作为成本入账。
        </div>
        <label className="relation-preview-note">
          <span>现金往来金额</span>
          <input value={cashAmount} onChange={(event) => setCashAmount(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>买票成本（必填）</span>
          <input value={ticketCostAmount} onChange={(event) => setTicketCostAmount(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>项目名称（必填）</span>
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>费用类型</span>
          <input value={expenseType} onChange={(event) => setExpenseType(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>费用内容</span>
          <input value={expenseContent} onChange={(event) => setExpenseContent(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>备注</span>
          <textarea aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <footer className="detail-modal-actions">
          <button className="secondary-btn" type="button" onClick={onClose}>
            取消
          </button>
          <button
            className="primary-action-btn"
            disabled={!canSubmit}
            type="button"
            onClick={() =>
              onSubmit({
                cashAmount: normalizedAmountForInput(cashAmount),
                ticketCostAmount: normalizedAmountForInput(ticketCostAmount),
                projectName: projectName.trim(),
                expenseType: expenseType.trim(),
                expenseContent: expenseContent.trim(),
                note: note.trim(),
              })}
          >
            确认买票
          </button>
        </footer>
      </section>
    </div>
  );
}

function RelationPreviewDialog({
  preview,
  columnLayouts,
  onClose,
  onSubmit,
}: {
  preview: WorkbenchRelationPreview;
  columnLayouts?: WorkbenchSettings["workbenchColumnLayouts"];
  onClose: () => void;
  onSubmit: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const isWithdraw = preview.operation === "withdraw_link";
  const isSplitCandidate = preview.operation === "split_candidate";
  const submitLabel = isSplitCandidate ? "确认拆分" : isWithdraw ? "确认撤回" : "确认关联";
  const title = isSplitCandidate ? "拆分候选预览" : isWithdraw ? "撤回关联预览" : "确认关联预览";
  const noteRequired = preview.requiresNote;
  const canSubmit = preview.canSubmit && (!noteRequired || note.trim().length > 0);

  return (
    <div className="detail-modal-backdrop">
      <button aria-label="关闭关联预览" className="detail-modal-backdrop-foreground" type="button" onClick={onClose} />
      <section aria-label="关联预览" aria-modal="true" className="detail-modal relation-preview-modal" role="dialog">
        <header className="detail-modal-header">
          <div>
            <div className="modal-eyebrow">关联预览</div>
            <h2>{title}</h2>
          </div>
          <button aria-label="关闭关联预览" className="detail-close-btn" type="button" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="relation-preview-body">
          {preview.message ? <div className={`relation-preview-message ${preview.requiresNote ? "warning" : ""}`}>{preview.message}</div> : null}
          <div className="relation-preview-stack">
            <RelationPreviewTriPane
              title="操作前"
              testId="relation-preview-before"
              groups={preview.before.groups}
              totals={preview.amountSummary.before}
              status={preview.amountSummary.status}
              mismatchFields={preview.amountSummary.mismatchFields}
              columnLayouts={columnLayouts}
            />
            <RelationPreviewTriPane
              title="操作后"
              testId="relation-preview-after"
              groups={preview.after.groups}
              totals={preview.amountSummary.after}
              status={preview.amountSummary.status}
              mismatchFields={preview.amountSummary.mismatchFields}
              columnLayouts={columnLayouts}
            />
          </div>
          <label className="relation-preview-note">
            <span>备注{noteRequired ? "（必填）" : ""}</span>
            <textarea aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
        </div>
        <footer className="detail-modal-actions relation-preview-actions">
          <button className="secondary-btn" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action-btn" disabled={!canSubmit} type="button" onClick={() => onSubmit(note.trim())}>
            {submitLabel}
          </button>
        </footer>
      </section>
    </div>
  );
}

function isProcessedExceptionRow(row: WorkbenchRecord) {
  if (row.statusCode === "manual_review" || row.status === "待人工核查") {
    return false;
  }
  if (row.exceptionHandled) {
    return true;
  }
  if (row.statusTone !== "danger") {
    return false;
  }
  return LEGACY_HANDLED_EXCEPTION_CODES.has(row.statusCode) || LEGACY_HANDLED_EXCEPTION_LABELS.has(row.status);
}

function collectProcessedExceptionGroups(groups: WorkbenchCandidateGroup[]) {
  return groups.flatMap((group) => {
    const nextGroup: WorkbenchCandidateGroup = {
      ...group,
      rows: {
        oa: group.rows.oa.filter(isProcessedExceptionRow),
        bank: group.rows.bank.filter(isProcessedExceptionRow),
        invoice: group.rows.invoice.filter(isProcessedExceptionRow),
      },
    };
    const visibleCount = nextGroup.rows.oa.length + nextGroup.rows.bank.length + nextGroup.rows.invoice.length;
    return visibleCount > 0 ? [nextGroup] : [];
  });
}

function removeProcessedExceptionRows(groups: WorkbenchCandidateGroup[]) {
  return groups.flatMap((group) => {
    const nextGroup: WorkbenchCandidateGroup = {
      ...group,
      rows: {
        oa: group.rows.oa.filter((row) => !isProcessedExceptionRow(row)),
        bank: group.rows.bank.filter((row) => !isProcessedExceptionRow(row)),
        invoice: group.rows.invoice.filter((row) => !isProcessedExceptionRow(row)),
      },
    };
    const visibleCount = nextGroup.rows.oa.length + nextGroup.rows.bank.length + nextGroup.rows.invoice.length;
    return visibleCount > 0 ? [nextGroup] : [];
  });
}

function flattenGroups(groups: WorkbenchCandidateGroup[]) {
  return groups.flatMap((group) => [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice]);
}

function mergeWorkbenchGroupsByIdReplacingExisting(
  existingGroups: WorkbenchCandidateGroup[],
  incomingGroups: WorkbenchCandidateGroup[],
) {
  const byId = new Map(existingGroups.map((group) => [group.id, group]));
  incomingGroups.forEach((group) => byId.set(group.id, group));
  return Array.from(byId.values());
}

function applyOperationProjectionToGroups(
  existingGroups: WorkbenchCandidateGroup[],
  incomingGroups: WorkbenchCandidateGroup[],
  affectedRowIds: Set<string>,
) {
  const filteredGroups = existingGroups.flatMap((group) => {
    const nextGroup: WorkbenchCandidateGroup = {
      ...group,
      rows: {
        oa: group.rows.oa.filter((row) => !affectedRowIds.has(row.id)),
        bank: group.rows.bank.filter((row) => !affectedRowIds.has(row.id)),
        invoice: group.rows.invoice.filter((row) => !affectedRowIds.has(row.id)),
      },
    };
    return flattenGroups([nextGroup]).length > 0 ? [nextGroup] : [];
  });
  return mergeWorkbenchGroupsByIdReplacingExisting(filteredGroups, incomingGroups);
}

function operationProjectionAffectedRowIds(result: WorkbenchActionResult) {
  return new Set(
    [
      ...cleanWorkbenchScopeList(result.affected_row_ids),
      ...(result.operationProjection
        ? flattenGroups([
          ...result.operationProjection.after.pairedGroups,
          ...result.operationProjection.after.openGroups,
        ]).map((row) => row.id)
        : []),
    ].filter(Boolean),
  );
}

function hasOperationProjection(projection: WorkbenchOperationProjection | undefined) {
  return Boolean(projection && (
    projection.after.pairedGroups.length > 0
    || projection.after.openGroups.length > 0
  ));
}

const LEGACY_HANDLED_EXCEPTION_CODES = new Set([
  "pending_collection",
  "bank_fee",
  "oa_missing_bank",
  "bank_missing_oa_fee",
  "bank_missing_oa_loan",
  "bank_missing_oa_interest",
  "bank_missing_oa_misc",
  "oa_bank_amount_mismatch",
  "oa_one_to_many_bank",
  "oa_many_to_one_bank",
]);

const LEGACY_HANDLED_EXCEPTION_LABELS = new Set([
  "待人工处理",
  "无对应流水（还没付钱）",
  "无对应OA（补手续费）",
  "无对应OA（补贷款）",
  "无对应OA（补利息）",
  "无对应OA（补电信托收薪资保险往来款标灰）",
  "金额不一致，继续异常",
  "一个OA多个流水",
  "多个OA一笔流水",
]);
