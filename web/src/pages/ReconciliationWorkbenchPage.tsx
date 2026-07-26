import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../components/common/AppDrawer";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
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
import { useAppHealthStatus } from "../contexts/AppHealthStatusContext";
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
  fetchWorkbenchRowDetail,
  fetchWorkbenchSettings,
  ignoreWorkbenchRow,
  previewWorkbenchConfirmLink,
  previewWorkbenchWithdrawLink,
  saveWorkbenchSettings,
  unignoreWorkbenchRow,
  withdrawWorkbenchLink,
  WorkbenchApiError,
  WORKBENCH_GROUP_PAGE_SIZE,
  type WorkbenchActionResult,
  type WorkbenchOperationProjection,
} from "../features/workbench/api";
import { fetchBankFlowRuleBatchDetail, withdrawBankFlowRuleBatch } from "../features/bankFlowRuleBatches/api";
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
import { resolveWorkbenchWriteGate } from "../features/workbench/writeGate";
import type {
  IgnoredWorkbenchData,
  WorkbenchRelationGroup,
  WorkbenchData,
  WorkbenchExceptionApplyResult,
  WorkbenchGroupsPageQuery,
  WorkbenchInitialPageResult,
  WorkbenchOaSyncStatus,
  WorkbenchRecord,
  WorkbenchRelationPreview,
  WorkbenchSettings,
  WorkbenchStatistics,
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

type RelationPreviewRequestKind = "confirm" | "withdraw";

type WorkbenchActionProgressPhase = "submitting" | "rereading" | "loading";

type WorkbenchActionProgress = {
  phase: WorkbenchActionProgressPhase;
  message: string;
  committed: boolean;
};

type WorkbenchActionProgressHandler = (progress: WorkbenchActionProgress) => void;

type WorkbenchExceptionDialogState = {
  rows: WorkbenchRecord[];
};

type CashTicketPurchaseDialogState = {
  rowIds: string[];
  cashAmount: string;
};

type CancelProcessedExceptionDialogState = {
  group: WorkbenchRelationGroup;
};

type WorkbenchLoadProgressState = {
  label: string;
  loadedBytes: number;
  totalBytes: number;
  percent: number | null;
  indeterminate: boolean;
};

function createInitialZonePageInfo(zone: "paired" | "unpaired"): WorkbenchZonePageInfo {
  return {
    zone,
    page: 0,
    pageSize: WORKBENCH_GROUP_PAGE_SIZE,
    total: 0,
    rowCounts: { oa: 0, bank: 0, invoice: 0, rows: 0 },
    hasMore: false,
  };
}

function createInitialZonePages(): Record<"paired" | "unpaired", WorkbenchZonePageInfo> {
  return {
    paired: createInitialZonePageInfo("paired"),
    unpaired: createInitialZonePageInfo("unpaired"),
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
    && typeof state.searchQuery === "string"
    && Object.prototype.hasOwnProperty.call(state, "filtersByPaneAndColumn")
    && Object.prototype.hasOwnProperty.call(state, "sortByPane")
    && Object.prototype.hasOwnProperty.call(state, "timeFilterByPane")
  );
}

function actionErrorMessage(error: unknown) {
  if (error instanceof WorkbenchApiError) {
    return error.message;
  }
  return "操作失败，请稍后重试。";
}

function isRelationPreviewRetryableSubmitError(message: string) {
  const normalizedMessage = message.trim().toLowerCase();
  if (!normalizedMessage) {
    return true;
  }
  return !(
    normalizedMessage.includes("重新预览")
    || normalizedMessage.includes("预览已失效")
    || normalizedMessage.includes("版本冲突")
    || normalizedMessage.includes("version conflict")
    || normalizedMessage.includes("preview stale")
    || normalizedMessage.includes("stale preview")
    || normalizedMessage.includes("conflict")
  );
}

function relationPreviewNonRetryableMessage(message: string) {
  if (message.includes("重新预览")) {
    return message;
  }
  return `${message} 请关闭后重新选择记录并重新预览。`;
}

function normalizedAmountForInput(value: string) {
  const normalized = value.replace(/,/g, "").trim();
  if (!normalized || normalized === "--" || normalized === "—") {
    return "";
  }
  return normalized;
}

const WORKBENCH_VIEW_MONTH = "all";
const OA_SYNC_POLL_INTERVAL_MS = 3_000;
const OA_SYNC_REFRESH_DEBOUNCE_MS = 120;

function createWorkbenchServerPageQueryKey(query: WorkbenchGroupsPageQuery) {
  return JSON.stringify(query);
}

function createWorkbenchZoneServerPageQueryKeys(
  queries: Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>,
) {
  return {
    paired: createWorkbenchServerPageQueryKey(queries.paired),
    unpaired: createWorkbenchServerPageQueryKey(queries.unpaired),
  };
}

function createWorkbenchZoneServerPageQueriesKey(
  queries: Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>,
) {
  return JSON.stringify(createWorkbenchZoneServerPageQueryKeys(queries));
}

function isBankFlowRuleBatchSummaryRow(row: WorkbenchRecord) {
  return row.sourceKind === "bank_flow_rule_batch_summary"
    || readStringMetadata(row.specialMetadata, "relation_mode") === "bank_flow_rule_batch";
}

function bankFlowRuleBatchSourceBatchId(row: WorkbenchRecord) {
  return readStringMetadata(row.specialMetadata, "source_batch_id");
}

function uniqueBankFlowRuleBatchRows(rows: WorkbenchRecord[]) {
  const byBatchId = new Map<string, WorkbenchRecord>();
  rows.forEach((row) => {
    const sourceBatchId = bankFlowRuleBatchSourceBatchId(row);
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

function actionResultMessage(result: string | WorkbenchActionResult) {
  return typeof result === "string" ? result : result.message;
}

export default function ReconciliationWorkbenchPage() {
  const { currentMonth } = useMonth();
  const { setWorkbenchStatus } = useAppChrome();
  const healthStatus = useAppHealthStatus();
  const { runOperation } = useGlobalOperationOverlay();
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const { active, activationGeneration } = useOptionalPageActivation("reconciliation-workbench");
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
  const [statistics, setStatistics] = useState<WorkbenchStatistics | null>(null);
  const [loadedZoneServerPageQueryKeys, setLoadedZoneServerPageQueryKeys] = useState<
    Record<"paired" | "unpaired", string> | null
  >(null);
  const [selectionSourceGroups, setSelectionSourceGroups] = useState<Record<"paired" | "unpaired", WorkbenchRelationGroup[]>>({
    paired: [],
    unpaired: [],
  });
  const [zonePages, setZonePages] = useState<Record<"paired" | "unpaired", WorkbenchZonePageInfo>>(() => createInitialZonePages());
  const [oaSyncStatus, setOaSyncStatus] = useState<WorkbenchOaSyncStatus | null>(null);
  const oaSyncWriteBlocked = oaSyncStatus
    ? oaSyncStatus.status === "refreshing" || oaSyncStatus.dirtyScopes.length > 0
    : healthStatus.sources.oaSync === "dirty" || healthStatus.sources.oaSync === "refreshing";
  const workbenchWriteGate = resolveWorkbenchWriteGate({
    canMutateData,
    mutationsBlocked: healthStatus.blocksMutations,
    oaSyncWriteBlocked,
  });
  const canWriteWorkbench = workbenchWriteGate.allowed;
  const [loadingMoreByZone, setLoadingMoreByZone] = useState<Record<"paired" | "unpaired", boolean>>({
    paired: false,
    unpaired: false,
  });
  const [loadMoreErrorByZone, setLoadMoreErrorByZone] = useState<Record<"paired" | "unpaired", string | null>>({
    paired: null,
    unpaired: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadProgress, setLoadProgress] = useState<WorkbenchLoadProgressState>({
    label: "正在加载关联台数据",
    loadedBytes: 0,
    totalBytes: 0,
    percent: null,
    indeterminate: true,
  });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [backgroundLoadError, setBackgroundLoadError] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRequestSeqRef = useRef(0);
  const loadRequestSeqRef = useRef(0);
  const loadMoreRequestSeqRef = useRef<Record<"paired" | "unpaired", number>>({ paired: 0, unpaired: 0 });
  const loadMoreInFlightRef = useRef<Record<"paired" | "unpaired", boolean>>({ paired: false, unpaired: false });
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);
  const [expandedZoneId, setExpandedZoneId] = useState<"paired" | "unpaired" | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialogState | null>(null);
  const [relationPreviewDialog, setRelationPreviewDialog] = useState<RelationPreviewDialogState | null>(null);
  const [relationPreviewRequestKind, setRelationPreviewRequestKind] = useState<RelationPreviewRequestKind | null>(null);
  const relationPreviewRequestKindRef = useRef<RelationPreviewRequestKind | null>(null);
  const relationPreviewContextKeyRef = useRef("");
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
    version: 2,
    initialValue: createEmptyWorkbenchZoneDisplayState(),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isWorkbenchZoneDisplayState,
    debounceMs: 100,
  });
  const openDisplaySession = usePageSessionState<WorkbenchZoneDisplayState>({
    pageKey: "reconciliation-workbench",
    stateKey: "openDisplayState",
    version: 2,
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
  const zoneServerPageQueries = useMemo<Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>>(
    () => ({
      paired: pairedServerPageQuery,
      unpaired: openServerPageQuery,
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
    zoneId: "paired" | "unpaired",
    updater: (current: WorkbenchZoneDisplayState) => WorkbenchZoneDisplayState,
  ) => {
    loadMoreRequestSeqRef.current[zoneId] += 1;
    loadMoreInFlightRef.current[zoneId] = false;
    setLoadingMoreByZone((current) => current[zoneId] ? { ...current, [zoneId]: false } : current);
    setLoadMoreErrorByZone((current) => current[zoneId] ? { ...current, [zoneId]: null } : current);
    if (zoneId === "paired") {
      setPairedDisplayState((current) => updater(current));
      return;
    }
    setOpenDisplayState((current) => updater(current));
  }, []);

  const handleSearchQueryChange = useCallback((zoneId: "paired" | "unpaired", query: string) => {
    updateZoneDisplayState(zoneId, (current) => ({ ...current, searchQuery: query.slice(0, 200) }));
  }, [updateZoneDisplayState]);

  const handleColumnFilterChange = useCallback(
    (
      zoneId: "paired" | "unpaired",
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
    (zoneId: "paired" | "unpaired", paneId: "oa" | "bank" | "invoice") => {
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
      zoneId: "paired" | "unpaired",
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

    setOaSyncStatus(status);

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

  const withdrawBankFlowRuleBatchSummaryRow = useCallback(async (row: WorkbenchRecord) => {
    const sourceBatchId = readStringMetadata(row.specialMetadata, "source_batch_id");
    if (!sourceBatchId) {
      throw new Error("流水规则批次来源缺失，无法撤回。");
    }

    let expectedVersion = readNumberMetadata(row.specialMetadata, "batch_version");
    if (expectedVersion === null) {
      const detail = await fetchBankFlowRuleBatchDetail(sourceBatchId);
      expectedVersion = typeof detail.batch.version === "number" ? detail.batch.version : null;
    }
    if (expectedVersion === null) {
      throw new Error("流水规则批次版本缺失，无法撤回。");
    }

    await withdrawBankFlowRuleBatch({
      batchId: sourceBatchId,
      expectedVersion,
      reason: "由关联台撤回流水规则批次",
    });
    clearPairedSelection();
    return "已撤回流水规则批次。";
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

  function applyWorkbenchInitialPageResult(
    workbenchPayload: WorkbenchInitialPageResult,
    resolvedZoneQueries: Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>,
  ) {
    loadMoreRequestSeqRef.current.paired += 1;
    loadMoreRequestSeqRef.current.unpaired += 1;
    loadMoreInFlightRef.current = { paired: false, unpaired: false };
    setLoadingMoreByZone({ paired: false, unpaired: false });
    setLoadMoreErrorByZone({ paired: null, unpaired: null });
    setWorkbenchData(workbenchPayload.data);
    setStatistics(workbenchPayload.statistics ?? null);
    setLoadedZoneServerPageQueryKeys(createWorkbenchZoneServerPageQueryKeys(resolvedZoneQueries));
    setZonePages(workbenchPayload.pages);
  }

  async function loadWorkbenchData(
    month: string,
    signal?: AbortSignal,
    options?: {
      background?: boolean;
      includeAuxiliary?: boolean;
      zoneQueries?: Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>;
      propagateError?: boolean;
      deferStateApply?: boolean;
    },
  ): Promise<WorkbenchInitialPageResult | null> {
    const requestSeq = loadRequestSeqRef.current + 1;
    loadRequestSeqRef.current = requestSeq;
    const background = options?.background ?? false;
    const includeAuxiliary = options?.includeAuxiliary ?? false;
    const deferStateApply = options?.deferStateApply ?? false;
    const resolvedZoneQueries = options?.zoneQueries ?? zoneServerPageQueries;

    if (background) {
      setIsRefreshing(true);
      setBackgroundLoadError(null);
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
      if (signal?.aborted || loadRequestSeqRef.current !== requestSeq) {
        return null;
      }
      if (!deferStateApply) {
        applyWorkbenchInitialPageResult(workbenchPayload, resolvedZoneQueries);
      }
      setBackgroundLoadError(null);
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
      if (signal?.aborted || loadRequestSeqRef.current !== requestSeq) {
        return null;
      }
      const normalizedError = error instanceof Error && error.message
        ? error
        : new Error("工作台数据加载失败，请稍后重试。");
      if (!background) {
        setWorkbenchData(null);
        setStatistics(null);
        setLoadedZoneServerPageQueryKeys(null);
        setZonePages(createInitialZonePages());
        setIgnoredData({ month, rows: [] });
        setLoadError(normalizedError.message);
        setIsLoading(false);
      } else {
        setIsRefreshing(false);
        setLastActionMessage(null);
        setBackgroundLoadError(normalizedError.message);
      }
      if (options?.propagateError) {
        throw normalizedError;
      }
      return null;
    }
  }

  const reloadWorkbenchAfterOperation = useCallback(async (options?: {
    deferStateApply?: boolean;
  }) => {
    const deferStateApply = options?.deferStateApply ?? false;
    return loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
      background: true,
      includeAuxiliary: false,
      zoneQueries: zoneServerPageQueries,
      propagateError: true,
      deferStateApply,
    });
  }, [zoneServerPageQueries]);

  const handleLoadMoreZone = useCallback(async (zone: "paired" | "unpaired") => {
    const pageInfo = zonePages[zone];
    const displayStatePending = zone === "paired"
      ? pairedDisplayState !== deferredPairedDisplayState
      : openDisplayState !== deferredOpenDisplayState;
    if (
      !workbenchData
      || !pageInfo.hasMore
      || displayStatePending
      || loadedZoneServerPageQueryKeys?.[zone] !== zoneServerPageQueryKeys[zone]
      || loadMoreInFlightRef.current[zone]
    ) {
      return;
    }
    const requestSeq = loadMoreRequestSeqRef.current[zone] + 1;
    loadMoreRequestSeqRef.current[zone] = requestSeq;
    loadMoreInFlightRef.current[zone] = true;
    setLoadingMoreByZone((current) => ({ ...current, [zone]: true }));
    setLoadMoreErrorByZone((current) => current[zone] ? { ...current, [zone]: null } : current);
    try {
      const result = await fetchWorkbenchGroupsPage(
        WORKBENCH_VIEW_MONTH,
        zone,
        pageInfo.page + 1,
        pageInfo.pageSize,
        undefined,
        { ...zoneServerPageQueries[zone], detailLevel: "summary" },
      );
      if (loadMoreRequestSeqRef.current[zone] !== requestSeq) {
        return;
      }
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
      if (loadMoreRequestSeqRef.current[zone] !== requestSeq) {
        return;
      }
      setLoadMoreErrorByZone((current) => ({
        ...current,
        [zone]: "自动加载下一页失败，请重试。",
      }));
    } finally {
      if (loadMoreRequestSeqRef.current[zone] === requestSeq) {
        loadMoreInFlightRef.current[zone] = false;
        setLoadingMoreByZone((current) => current[zone] ? { ...current, [zone]: false } : current);
      }
    }
  }, [
    deferredOpenDisplayState,
    deferredPairedDisplayState,
    loadedZoneServerPageQueryKeys,
    openDisplayState,
    pairedDisplayState,
    workbenchData,
    zonePages,
    zoneServerPageQueries,
    zoneServerPageQueryKeys,
  ]);

  const handleEnsureGroupDetail = useCallback(async (zone: "paired" | "unpaired", groupId: string) => {
    const normalizedGroupId = groupId.trim();
    if (!normalizedGroupId) {
      throw new Error("invalid_workbench_group_detail_request");
    }
    const detailKey = workbenchData?.[zone].groups.find(
      (candidate) => candidate.id === normalizedGroupId,
    )?.detailKey;
    let group: WorkbenchRelationGroup;
    try {
      group = await fetchWorkbenchGroupDetail(
        WORKBENCH_VIEW_MONTH,
        zone,
        normalizedGroupId,
        detailKey,
      );
    } catch {
      setLastActionMessage("加载完整明细失败，请稍后重试。");
      throw new Error("workbench_group_detail_load_failed");
    }
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
  }, [workbenchData]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    if (!workbenchData || isLoading) {
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
      unpaired: mergeWorkbenchGroupsByIdReplacingExisting(current.unpaired, workbenchData.unpaired.groups),
    }));
  }, [workbenchData]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    clearSelection();
    setLastActionMessage(null);
    setDetailError(null);
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, controller.signal, { includeAuxiliary: true });
    return () => controller.abort();
  }, [active, activationGeneration]);

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
    workbenchData?.oaStatus?.code,
    workbenchData?.oaStatus?.message,
  ]);

  useEffect(() => () => setWorkbenchStatus(null), [setWorkbenchStatus]);

  const processedExceptionRows = useMemo(
    () => flattenGroups(collectProcessedExceptionGroups(workbenchData?.unpaired.groups ?? [])),
    [workbenchData],
  );

  const visibleOpenGroups = useMemo(
    () => removeProcessedExceptionRows(workbenchData?.unpaired.groups ?? []),
    [workbenchData],
  );

  const processedExceptionGroups = useMemo(
    () => collectProcessedExceptionGroups(workbenchData?.unpaired.groups ?? []),
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
          loadedZoneServerPageQueryKeys?.unpaired === zoneServerPageQueryKeys.unpaired
          && hasWorkbenchServerPageCriteria(openServerPageQuery),
      },
    ),
    [
      deferredOpenDisplayState,
      loadedZoneServerPageQueryKeys?.unpaired,
      openServerPageQuery,
      visibleOpenGroups,
      zoneServerPageQueryKeys.unpaired,
    ],
  );

  const sourceAllGroups = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchRelationGroup[];
    }
    return [...workbenchData.paired.groups, ...visibleOpenGroups];
  }, [visibleOpenGroups, workbenchData]);

  const sourceAllRows = useMemo(() => flattenGroups(sourceAllGroups), [sourceAllGroups]);
  const openSelectionSourceGroups = useMemo(
    () => mergeWorkbenchGroupsByIdReplacingExisting(selectionSourceGroups.unpaired, workbenchData?.unpaired.groups ?? []),
    [selectionSourceGroups.unpaired, workbenchData?.unpaired.groups],
  );
  const pairedSelectionSourceGroups = useMemo(
    () => mergeWorkbenchGroupsByIdReplacingExisting(selectionSourceGroups.paired, workbenchData?.paired.groups ?? []),
    [selectionSourceGroups.paired, workbenchData?.paired.groups],
  );

  const openSelectionContext = useMemo(
    () => buildWorkbenchSelectionContext({
      explicitRows: explicitSelectedOpenRows,
      sourceGroups: openSelectionSourceGroups,
      zoneId: "unpaired",
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
  relationPreviewContextKeyRef.current = [
    WORKBENCH_VIEW_MONTH,
    openSelectionContext.includedRowIds.join(","),
    pairedSelectionContext.includedRowIds.join(","),
  ].join("|");
  const getWorkbenchRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "unpaired") => {
    const explicitState = getRowState(row, zoneId);
    if (explicitState !== "idle") {
      return explicitState;
    }
    return (zoneId === "unpaired" ? contextualOpenRowIds : contextualPairedRowIds).has(row.id) ? "related" : "idle";
  }, [contextualOpenRowIds, contextualPairedRowIds, getRowState]);

  const canConfirmOpenSelection = openSelectionSummary.bank > 0 && openSelectionSummary.oa + openSelectionSummary.invoice > 0;
  const canHandleOpenSelectionException = openSelectionSummary.total > 0;
  const selectedPairedGroupsForUnifiedAction = useMemo(() => {
    const selectedRowIdSet = new Set(pairedSelectionContext.includedRowIds);
    return pairedSelectionSourceGroups.filter((group) => flattenGroups([group]).some((row) => selectedRowIdSet.has(row.id)));
  }, [pairedSelectionContext.includedRowIds, pairedSelectionSourceGroups]);
  const isOpenConfirmSelectionDisabled = !canConfirmOpenSelection;
  const isOpenExceptionSelectionDisabled = openSelectionSummary.total < 1;
  const isPairedCancelSelectionDisabled = pairedSelectionSummary.total < 1;
  const pairedSelectionActionNotice = pairedSelectionSummary.total > 0 && !workbenchWriteGate.allowed
    ? workbenchWriteGate.message
    : null;
  const openSelectionActionNotice = openSelectionSummary.total < 1
    ? null
    : !workbenchWriteGate.allowed
      ? workbenchWriteGate.message
      : !canConfirmOpenSelection
        ? "确认关联至少需要 1 条银行流水，以及 1 条 OA 或发票。"
        : null;

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

  const handleOpenDetail = useCallback((row: WorkbenchRecord) => {
    const requestSeq = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestSeq;
    setDetailError(null);
    setIsDetailLoading(true);
    openDetail(row);

    void fetchWorkbenchRowDetail(row.id, {
      month: WORKBENCH_VIEW_MONTH,
    })
      .then((detailedRow) => {
        if (detailRequestSeqRef.current === requestSeq) {
          replaceDetailRow(detailedRow);
        }
      })
      .catch(() => {
        if (detailRequestSeqRef.current === requestSeq) {
          setDetailError("详情加载失败，请稍后重试。");
        }
      })
      .finally(() => {
        if (detailRequestSeqRef.current === requestSeq) {
          setIsDetailLoading(false);
        }
      });
  }, [openDetail, replaceDetailRow]);

  const handleCloseDetail = useCallback(() => {
    detailRequestSeqRef.current += 1;
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
    if (!workbenchWriteGate.allowed) {
      openActionResultDialog(workbenchWriteGate.message ?? "关联台当前不可执行写操作。");
      return false;
    }
    return true;
  }, [openActionResultDialog, workbenchWriteGate]);

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
        unpaired: {
          groups: applyOperationProjectionToGroups(
            current.unpaired.groups,
            projection?.after.unpairedGroups ?? [],
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
      unpaired: applyOperationProjectionToGroups(
        current.unpaired,
        projection?.after.unpairedGroups ?? [],
        affectedRowIds,
      ),
    }));
    return true;
  }, []);

  const executeWorkbenchAction = useCallback(async ({
    loadingMessage,
    action,
    onProgress,
    deferWorkbenchApply = false,
    onWorkbenchPayload,
  }: {
    loadingMessage: string;
    action: () => Promise<string | WorkbenchActionResult>;
    onProgress?: WorkbenchActionProgressHandler;
    deferWorkbenchApply?: boolean;
    onWorkbenchPayload?: (payload: WorkbenchInitialPageResult) => void;
  }) => {
    onProgress?.({ phase: "submitting", message: loadingMessage, committed: false });
    const result = await action();
    const actionResult = typeof result === "string" ? null : result;
    const committed = Boolean(actionResult);
    if (actionResult) {
      applyWorkbenchOperationProjection(actionResult);
    }
    onProgress?.({ phase: "loading", message: "正在加载关联台最新数据...", committed });
    const workbenchPayload = await reloadWorkbenchAfterOperation({
      deferStateApply: deferWorkbenchApply,
    });
    if (deferWorkbenchApply && workbenchPayload) {
      onWorkbenchPayload?.(workbenchPayload);
    }
    return actionResultMessage(result);
  }, [applyWorkbenchOperationProjection, reloadWorkbenchAfterOperation]);

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
        return executeWorkbenchAction({
          loadingMessage,
          action,
          onProgress: (progress) => setMessage(progress.message),
        });
      },
      errorMessage: actionErrorMessage,
    });
    if (outcome.status === "success") {
      setLastActionMessage(outcome.value);
    }
  }, [executeWorkbenchAction, handleCloseDetail, runOperation]);

  const openRelationPreviewErrorDialog = useCallback((error: unknown) => {
    openActionResultDialog(actionErrorMessage(error), "操作失败");
  }, [openActionResultDialog]);

  const handleWorkbenchExceptionApplied = useCallback(async (
    result: WorkbenchExceptionApplyResult,
    onProgress: WorkbenchActionProgressHandler,
  ) => {
    onProgress({
      phase: "loading",
      message: "正在加载关联台最新数据...",
      committed: true,
    });
    await reloadWorkbenchAfterOperation();
    clearOpenSelection();
    setLastActionMessage(result.message ?? "已提交统一异常处理。");
  }, [clearOpenSelection, reloadWorkbenchAfterOperation]);

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
      await loadWorkbenchAuxiliaryData(WORKBENCH_VIEW_MONTH);
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
      if (isBankFlowRuleBatchSummaryRow(row)) {
        await runBlockingAction({
          loadingMessage: "正在撤回流水规则批次...",
          action: () => withdrawBankFlowRuleBatchSummaryRow(row),
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
    withdrawBankFlowRuleBatchSummaryRow,
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

  const handleSelectRow = useCallback((row: WorkbenchRecord, zoneId: "paired" | "unpaired") => {
    if (zoneId === "unpaired") {
      toggleOpenRowSelection(row);
      return;
    }
    togglePairedRowSelection(row);
  }, [toggleOpenRowSelection, togglePairedRowSelection]);

  const resolveSelectedCaseId = (rows: WorkbenchRecord[]) => {
    const caseIds = Array.from(new Set(rows.map((row) => row.caseId).filter((caseId): caseId is string => Boolean(caseId))));
    return caseIds.length === 1 ? caseIds[0] : undefined;
  };

  const openRelationPreview = async (kind: RelationPreviewRequestKind, rows: WorkbenchRecord[]) => {
    if (relationPreviewRequestKindRef.current) {
      return;
    }
    const rowIds = rows.map((row) => row.id);
    const requestContextKey = relationPreviewContextKeyRef.current;
    relationPreviewRequestKindRef.current = kind;
    setRelationPreviewRequestKind(kind);
    try {
      const preview = kind === "confirm"
          ? await previewWorkbenchConfirmLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
          })
        : await previewWorkbenchWithdrawLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
          });
      if (relationPreviewContextKeyRef.current !== requestContextKey) {
        return;
      }
      setRelationPreviewDialog({
        preview,
        rowIds,
        caseId: kind === "withdraw" ? resolveSelectedCaseId(rows) : undefined,
      });
    } finally {
      if (relationPreviewRequestKindRef.current === kind) {
        relationPreviewRequestKindRef.current = null;
        setRelationPreviewRequestKind(null);
      }
    }
  };

  const openConfirmPreview = async (rows: WorkbenchRecord[]) => {
    await openRelationPreview("confirm", rows);
  };

  const openWithdrawPreview = async (rows: WorkbenchRecord[]) => {
    await openRelationPreview("withdraw", rows);
  };

  const handleSubmitRelationPreview = async (note: string, onProgress: WorkbenchActionProgressHandler) => {
    if (!relationPreviewDialog) {
      return;
    }
    if (!ensureCanWriteWorkbench()) {
      throw new Error("当前状态不允许执行写操作。");
    }
    const { preview, rowIds, caseId } = relationPreviewDialog;
    if (preview.operation === "confirm_link") {
      let submittedResult: WorkbenchActionResult | null = null;
      const message = await executeWorkbenchAction({
        loadingMessage: "正在确认关联...",
        onProgress,
        action: async () => {
          const result = await confirmWorkbenchLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            caseId,
            note,
          });
          submittedResult = result;
          return result;
        },
      });
      if (submittedResult) {
        clearOpenSelection();
      }
      setLastActionMessage(message);
      setRelationPreviewDialog(null);
      return;
    }

    const operationCopy = relationPreviewOperationCopy(preview);
    let submittedResult: WorkbenchActionResult | null = null;
    let deferredWorkbenchApplied = false;
    const message = await executeWorkbenchAction({
      loadingMessage: operationCopy.submittingMessage,
      onProgress,
      deferWorkbenchApply: true,
      onWorkbenchPayload: (workbenchPayload) => {
        deferredWorkbenchApplied = true;
        setRelationPreviewDialog(null);
        applyWorkbenchInitialPageResult(workbenchPayload, zoneServerPageQueries);
      },
      action: async () => {
        const result = await withdrawWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds,
          note,
          operationType: "withdraw_relation",
          previewId: preview.previewId,
          expectedVersions: preview.submitExpectedVersions,
        });
        submittedResult = result;
        return result;
      },
    });
    if (submittedResult) {
      clearPairedSelection();
      clearOpenSelection();
    }
    setLastActionMessage(message);
    if (!deferredWorkbenchApplied) {
      setRelationPreviewDialog(null);
    }
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
    const selectedBankFlowRuleBatchRows = uniqueBankFlowRuleBatchRows(
      selectedPairedRows.filter(isBankFlowRuleBatchSummaryRow),
    );
    if (selectedBankFlowRuleBatchRows.length > 0) {
      await runBlockingAction({
        loadingMessage: "正在撤回流水规则批次...",
        action: async () => {
          for (const row of selectedBankFlowRuleBatchRows) {
            await withdrawBankFlowRuleBatchSummaryRow(row);
          }
          return selectedBankFlowRuleBatchRows.length === 1
            ? "已撤回流水规则批次。"
            : `已撤回 ${selectedBankFlowRuleBatchRows.length} 个流水规则批次。`;
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
    await loadWorkbenchAuxiliaryData(WORKBENCH_VIEW_MONTH);
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
      const totals = zonePages.unpaired.rowCounts.rows > 0
        ? zonePages.unpaired.rowCounts
        : workbenchData?.summary.zoneCounts.unpaired;
      return [
        { id: "oa", title: "OA", rows: paneRows.oa, totalRows: totals?.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank, totalRows: totals?.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice, totalRows: totals?.invoice },
      ];
    },
    [displayOpenGroups, workbenchData?.summary.zoneCounts.unpaired, zonePages.unpaired.rowCounts],
  );

  const togglePairedExpand = useCallback(() => {
    setExpandedZoneId((current) => (current === "paired" ? null : "paired"));
  }, []);

  const toggleOpenExpand = useCallback(() => {
    setExpandedZoneId((current) => (current === "unpaired" ? null : "unpaired"));
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
  const isUnpairedVisible = expandedZoneId === null || expandedZoneId === "unpaired";
  const pairedZoneItemCount = resolveZoneItemCount(zonePages.paired, workbenchData?.summary.zoneCounts.paired);
  const unpairedZoneItemCount = resolveZoneItemCount(zonePages.unpaired, workbenchData?.summary.zoneCounts.unpaired);
  const pairedSearchPending = pairedDisplayState !== deferredPairedDisplayState
    || (isRefreshing && loadedZoneServerPageQueryKeys?.paired !== zoneServerPageQueryKeys.paired);
  const unpairedSearchPending = openDisplayState !== deferredOpenDisplayState
    || (isRefreshing && loadedZoneServerPageQueryKeys?.unpaired !== zoneServerPageQueryKeys.unpaired);
  const pairedSearchError = backgroundLoadError && loadedZoneServerPageQueryKeys?.paired !== zoneServerPageQueryKeys.paired
    ? backgroundLoadError
    : null;
  const unpairedSearchError = backgroundLoadError && loadedZoneServerPageQueryKeys?.unpaired !== zoneServerPageQueryKeys.unpaired
    ? backgroundLoadError
    : null;
  const retryCurrentSearch = () => {
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
      background: true,
      zoneQueries: zoneServerPageQueries,
    });
  };
  const pairedZoneElement = (
    <WorkbenchZone
      canMutateData={canWriteWorkbench}
      getRowState={getWorkbenchRowState}
      isExpanded={expandedZoneId === "paired"}
      isVisible={isPairedVisible}
      onClearSelection={handleClearPairedSelection}
      onOpenDetail={handleOpenDetail}
      onEnsureGroupDetail={handleEnsureGroupDetail}
      onRequestNextPage={handleLoadMoreZone}
      onPrimarySelectionAction={handleCancelPairedSelection}
      primarySelectionActionDisabled={
        isPairedCancelSelectionDisabled || !canWriteWorkbench || relationPreviewRequestKind !== null
      }
      primarySelectionActionPending={relationPreviewRequestKind === "withdraw"}
      primarySelectionActionPendingLabel="正在准备撤回预览"
      selectionActionNotice={pairedSelectionActionNotice}
      onRowAction={handleRowAction}
      onSelectRow={handleSelectRow}
      onToggleExpand={togglePairedExpand}
      displayState={pairedDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onSearchQueryChange={(query) => handleSearchQueryChange("paired", query)}
      onRetrySearch={retryCurrentSearch}
      searchError={pairedSearchError}
      searchPending={pairedSearchPending}
      searchQuery={pairedDisplayState.searchQuery}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayPairedGroups}
      sourceGroups={workbenchData?.paired.groups ?? []}
      invoiceInventory={workbenchData?.invoiceInventory}
      loadingMore={loadingMoreByZone.paired}
      loadMoreError={loadMoreErrorByZone.paired}
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

  const unpairedZoneElement = (
    <WorkbenchZone
      auxiliaryHeaderActions={openAuxiliaryHeaderActions}
      canMutateData={canWriteWorkbench}
      getRowState={getWorkbenchRowState}
      isExpanded={expandedZoneId === "unpaired"}
      isVisible={isUnpairedVisible}
      onClearSelection={handleClearOpenSelection}
      onOpenDetail={handleOpenDetail}
      onEnsureGroupDetail={handleEnsureGroupDetail}
      onRequestNextPage={handleLoadMoreZone}
      onPrimarySelectionAction={handleConfirmOpenSelection}
      primarySelectionActionDisabled={
        isOpenConfirmSelectionDisabled || !canWriteWorkbench || relationPreviewRequestKind !== null
      }
      primarySelectionActionPending={relationPreviewRequestKind === "confirm"}
      primarySelectionActionPendingLabel="正在准备确认预览"
      onRowAction={handleRowAction}
      onSelectRow={handleSelectRow}
      onSecondarySelectionAction={handleOpenSelectionException}
      secondarySelectionActionDisabled={isOpenExceptionSelectionDisabled || !canWriteWorkbench}
      selectionActionNotice={openSelectionActionNotice}
      onToggleExpand={toggleOpenExpand}
      displayState={openDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onSearchQueryChange={(query) => handleSearchQueryChange("unpaired", query)}
      onRetrySearch={retryCurrentSearch}
      searchError={unpairedSearchError}
      searchPending={unpairedSearchPending}
      searchQuery={openDisplayState.searchQuery}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayOpenGroups}
      sourceGroups={visibleOpenGroups}
      invoiceInventory={workbenchData?.invoiceInventory}
      loadingMore={loadingMoreByZone.unpaired}
      loadMoreError={loadMoreErrorByZone.unpaired}
      pageInfo={zonePages.unpaired}
      highlightedRowId={null}
      panes={openPanes}
      primarySelectionActionLabel="确认关联"
      secondarySelectionActionLabel="异常处理"
      selectionSummary={openSelectionSummary}
      title={`未配对 ${unpairedZoneItemCount} 项`}
      tone="warning"
      zoneId="unpaired"
    />
  );

  return (
    <div className="workbench-shell">
      <div className={`page-stack${expandedZoneId ? " zone-expanded-layout" : ""}`}>
        <header className="page-header">
          <div className="page-title-row">
            <h1 className="page-title">关联台</h1>
            <div className="page-title-accessory">
              <div className="page-title-accessory-group">
                <PageStatisticsPopover
                  ariaLabel="关联台数据统计"
                  loading={isLoading && !workbenchData}
                  coreItems={[
                    { label: "OA", value: statistics?.oaCount, unit: "条" },
                    { label: "流水", value: statistics?.bankTransactionCount, unit: "笔" },
                    { label: "进项", value: statistics?.inputInvoiceCount, unit: "张" },
                    { label: "销项", value: statistics?.outputInvoiceCount, unit: "张" },
                  ]}
                  detailItems={[
                    { label: "已配对组", value: statistics?.pairedGroupCount, unit: "组", tone: "success" },
                    { label: "未配对对象", value: statistics?.unpairedObjectCount, unit: "个", tone: "warning" },
                    { label: "支出流水", value: statistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
                    { label: "收入流水", value: statistics?.incomeTransactionCount, unit: "笔", tone: "income" },
                    { label: "已配对 OA", value: statistics?.pairedOaCount, unit: "条" },
                    { label: "已配对流水", value: statistics?.pairedBankTransactionCount, unit: "笔" },
                    { label: "已配对发票", value: statistics?.pairedInvoiceCount, unit: "张" },
                    { label: "不完整关系组", value: statistics?.incompleteGroupCount, unit: "组", tone: "warning" },
                    { label: "缺 OA 关系组", value: statistics?.missingOaGroupCount, unit: "组", tone: "warning" },
                    { label: "缺流水关系组", value: statistics?.missingBankGroupCount, unit: "组", tone: "warning" },
                    { label: "缺发票关系组", value: statistics?.missingInvoiceGroupCount, unit: "组", tone: "warning" },
                  ]}
                />
                {canAdminAccess ? (
                <PageBusinessAuditIcon
                  ariaLabel="Audit 关联台"
                  pageKey="reconciliation-workbench"
                  label="关联台"
                  auditContextKey={`canonical:${statistics?.pairedGroupCount ?? 0}:${statistics?.unpairedObjectCount ?? 0}`}
                />
                ) : null}
              </div>
            </div>
          </div>
        </header>
        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {!loadError && oaStatusPanelMessage ? (
          <div className={`state-panel${oaStatus?.code === "error" ? " error" : ""}`}>{oaStatusPanelMessage}</div>
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
              className={`workbench-zone-slot workbench-zone-slot-bottom${isUnpairedVisible ? "" : " workbench-zone-slot-hidden"}`}
            >
              {unpairedZoneElement}
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

type RelationPreviewSubmitState =
  | { phase: "idle"; message: string; committed: false }
  | { phase: WorkbenchActionProgressPhase; message: string; committed: boolean }
  | { phase: "error"; message: string; committed: boolean; retryable: boolean };

function countRelationPreviewRows(groups: WorkbenchRelationGroup[]) {
  return groups.reduce(
    (counts, group) => ({
      oa: counts.oa + group.rows.oa.length,
      bank: counts.bank + group.rows.bank.length,
      invoice: counts.invoice + group.rows.invoice.length,
    }),
    { oa: 0, bank: 0, invoice: 0 },
  );
}

function relationPreviewOperationCopy(preview: WorkbenchRelationPreview) {
  if (preview.operation === "withdraw_link") {
    return {
      title: "撤回关联预览",
      submitLabel: "确认撤回",
      submittingMessage: "正在撤回关联...",
      statusLabel: "待撤回",
    };
  }
  return {
    title: "确认关联预览",
    submitLabel: "确认关联",
    submittingMessage: "正在确认关联...",
    statusLabel: "待确认",
  };
}

function relationPreviewPhaseLabel(phase: RelationPreviewSubmitState["phase"]) {
  if (phase === "submitting") {
    return "提交中";
  }
  if (phase === "rereading") {
    return "重新读取中";
  }
  if (phase === "loading") {
    return "加载中";
  }
  if (phase === "error") {
    return "需处理";
  }
  return "待操作";
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
  onSubmit: (note: string, onProgress: WorkbenchActionProgressHandler) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [submitState, setSubmitState] = useState<RelationPreviewSubmitState>({
    phase: "idle",
    message: "",
    committed: false,
  });
  const operationCopy = relationPreviewOperationCopy(preview);
  const noteRequired = preview.requiresNote;
  const isBusy = submitState.phase === "submitting" || submitState.phase === "rereading" || submitState.phase === "loading";
  const isCommittedError = submitState.phase === "error" && submitState.committed;
  const isNonRetryableError = submitState.phase === "error" && !submitState.retryable;
  const canSubmit = preview.canSubmit && (!noteRequired || note.trim().length > 0);
  const primaryDisabled = !canSubmit || isBusy || isCommittedError || isNonRetryableError;
  const rowCounts = countRelationPreviewRows(preview.after.groups);
  const closePreview = () => {
    if (!isBusy) {
      onClose();
    }
  };
  const handleSubmitClick = async () => {
    if (primaryDisabled) {
      return;
    }
    let committed = false;
    const setProgress: WorkbenchActionProgressHandler = (progress) => {
      committed = committed || progress.committed;
      setSubmitState({ ...progress, committed });
    };
    setProgress({ phase: "submitting", message: operationCopy.submittingMessage, committed: false });
    try {
      await onSubmit(note.trim(), setProgress);
    } catch (error) {
      const message = actionErrorMessage(error);
      const retryable = !committed && isRelationPreviewRetryableSubmitError(message);
      setSubmitState({
        phase: "error",
        committed,
        retryable,
        message: committed
          ? `关系已写入，页面重新读取失败：${message}`
          : retryable
            ? message
            : relationPreviewNonRetryableMessage(message),
      });
    }
  };

  useEffect(() => {
    setNote("");
    setSubmitState({ phase: "idle", message: "", committed: false });
  }, [preview.previewId]);

  const headerAside = (
    <span className={`relation-preview-phase-pill relation-preview-phase-${submitState.phase}`}>
      {isBusy || submitState.phase === "error" ? relationPreviewPhaseLabel(submitState.phase) : operationCopy.statusLabel}
    </span>
  );
  const subtitle = (
    <div className="relation-preview-title-block">
      <span className="relation-preview-operation-title">{operationCopy.title}</span>
      <span className="relation-preview-subtitle">
        <span>OA {rowCounts.oa}</span>
        <span>流水 {rowCounts.bank}</span>
        <span>发票 {rowCounts.invoice}</span>
      </span>
    </div>
  );
  const footer = (
    <div className="detail-modal-actions relation-preview-actions">
      {isCommittedError || isNonRetryableError ? (
        <button className="secondary-btn" type="button" onClick={closePreview}>
          关闭
        </button>
      ) : (
        <>
          <button className="secondary-btn" disabled={isBusy} type="button" onClick={closePreview}>
            取消
          </button>
          <button className="primary-action-btn" disabled={primaryDisabled} type="button" onClick={handleSubmitClick}>
            {submitState.phase === "error" ? "重试" : operationCopy.submitLabel}
          </button>
        </>
      )}
    </div>
  );

  return (
    <AppDrawer
      ariaBusy={isBusy}
      className={`relation-preview-drawer${isBusy ? " relation-preview-drawer-busy" : ""}`}
      closeDisabled={isBusy}
      closeLabel="关闭关联预览"
      footer={footer}
      headerAside={headerAside}
      open
      subtitle={subtitle}
      title="关联预览"
      width="min(1080px, 100vw)"
      onClose={closePreview}
    >
      <div className="relation-preview-body">
        {preview.message ? <div className={`relation-preview-message ${preview.requiresNote ? "warning" : ""}`}>{preview.message}</div> : null}
        {submitState.phase !== "idle" ? (
          <div
            className={`relation-preview-progress-panel relation-preview-progress-${submitState.phase}`}
            role={submitState.phase === "error" ? "alert" : "status"}
          >
            {isBusy ? <span aria-hidden="true" className="relation-preview-spinner" /> : null}
            <div>
              <strong>{relationPreviewPhaseLabel(submitState.phase)}</strong>
              <span>{submitState.message}</span>
            </div>
          </div>
        ) : null}
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
          <textarea
            aria-label="备注"
            disabled={isBusy || isCommittedError || isNonRetryableError}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
      </div>
    </AppDrawer>
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

function collectProcessedExceptionGroups(groups: WorkbenchRelationGroup[]) {
  return groups.flatMap((group) => {
    const nextGroup: WorkbenchRelationGroup = {
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

function removeProcessedExceptionRows(groups: WorkbenchRelationGroup[]) {
  return groups.flatMap((group) => {
    const nextGroup: WorkbenchRelationGroup = {
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

function flattenGroups(groups: WorkbenchRelationGroup[]) {
  return groups.flatMap((group) => [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice]);
}

function mergeWorkbenchGroupsByIdReplacingExisting(
  existingGroups: WorkbenchRelationGroup[],
  incomingGroups: WorkbenchRelationGroup[],
) {
  const byId = new Map(existingGroups.map((group) => [group.id, group]));
  incomingGroups.forEach((group) => byId.set(group.id, group));
  return Array.from(byId.values());
}

function applyOperationProjectionToGroups(
  existingGroups: WorkbenchRelationGroup[],
  incomingGroups: WorkbenchRelationGroup[],
  affectedRowIds: Set<string>,
) {
  const filteredGroups = existingGroups.flatMap((group) => {
    const nextGroup: WorkbenchRelationGroup = {
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
          ...result.operationProjection.after.unpairedGroups,
        ]).map((row) => row.id)
        : []),
    ].filter(Boolean),
  );
}

function hasOperationProjection(projection: WorkbenchOperationProjection | undefined) {
  return Boolean(projection && (
    projection.after.pairedGroups.length > 0
    || projection.after.unpairedGroups.length > 0
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
