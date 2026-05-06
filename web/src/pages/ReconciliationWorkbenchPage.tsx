import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import ActionStatusModal from "../components/workbench/ActionStatusModal";
import CancelProcessedExceptionModal from "../components/workbench/CancelProcessedExceptionModal";
import DetailDrawer from "../components/workbench/DetailDrawer";
import IgnoredItemsModal from "../components/workbench/IgnoredItemsModal";
import OaBankExceptionModal from "../components/workbench/OaBankExceptionModal";
import ProcessedExceptionsModal from "../components/workbench/ProcessedExceptionsModal";
import RelationPreviewTriPane from "../components/workbench/RelationPreviewTriPane";
import WorkbenchZone from "../components/workbench/WorkbenchZone";
import type { WorkbenchPane } from "../components/workbench/ResizableTriPane";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus, useCanMutateWithHealth } from "../contexts/AppHealthStatusContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  cancelWorkbenchException,
  confirmWorkbenchLink,
  fetchIgnoredWorkbenchRows,
  fetchWorkbenchOaSyncStatus,
  fetchWorkbenchRowDetail,
  fetchWorkbenchSettings,
  fetchWorkbenchWithProgress,
  ignoreWorkbenchRow,
  markWorkbenchException,
  previewWorkbenchConfirmLink,
  previewWorkbenchWithdrawLink,
  saveWorkbenchSettings,
  submitOaBankException,
  unignoreWorkbenchRow,
  withdrawWorkbenchLink,
} from "../features/workbench/api";
import {
  buildWorkbenchDisplayGroups,
  buildWorkbenchPaneRows,
  createEmptyWorkbenchZoneDisplayState,
  resolveWorkbenchActivePane,
  type WorkbenchPaneTimeFilter,
  type WorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import { reorderWorkbenchColumnLayout, type WorkbenchColumnDropPosition } from "../features/workbench/columnLayout";
import { buildOaBankExceptionOptions } from "../features/workbench/oaBankExceptionOptions";
import type {
  IgnoredWorkbenchData,
  WorkbenchCandidateGroup,
  WorkbenchData,
  WorkbenchOaSyncStatus,
  WorkbenchRecord,
  WorkbenchRelationPreview,
  WorkbenchSettings,
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

type OaBankExceptionDialogState = {
  rows: WorkbenchRecord[];
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

const READONLY_ACTION_MESSAGE = "当前账号仅支持查看和导出，不能执行写操作。";
const WORKBENCH_VIEW_MONTH = "all";
const OA_SYNC_POLL_INTERVAL_MS = 3_000;
const OA_SYNC_REFRESH_DEBOUNCE_MS = 120;

export default function ReconciliationWorkbenchPage() {
  const { currentMonth } = useMonth();
  const { setWorkbenchStatus } = useAppChrome();
  const healthStatus = useAppHealthStatus();
  const canMutateWithHealth = useCanMutateWithHealth();
  const { canMutateData } = useSessionPermissions();
  const isWorkbenchFreshnessBlocked =
    healthStatus.sources.oaSync === "dirty"
    || healthStatus.sources.oaSync === "refreshing"
    || healthStatus.sources.workbench === "stale"
    || healthStatus.sources.workbench === "loading";
  const canWriteWorkbench = canMutateData && canMutateWithHealth && !isWorkbenchFreshnessBlocked;
  const {
    detailRow,
    getRowState,
    openDetail,
    replaceDetailRow,
    closeDetail,
    clearSelection,
    clearPairedSelection,
    clearOpenSelection,
    selectedPairedRowIds,
    togglePairedRowSelection,
    selectedOpenRowIds,
    toggleOpenRowSelection,
  } =
    useWorkbenchSelection();
  const [workbenchData, setWorkbenchData] = useState<WorkbenchData | null>(null);
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
  const [oaBankExceptionDialog, setOaBankExceptionDialog] = useState<OaBankExceptionDialogState | null>(null);
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
  const previousOaSyncStatusRef = useRef<WorkbenchOaSyncStatus | null>(null);
  const deferredPairedDisplayState = useDeferredValue(pairedDisplayState);
  const deferredOpenDisplayState = useDeferredValue(openDisplayState);
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

  const applyLocalConfirmLink = useCallback((rowIds: string[], caseId?: string) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterConfirmLink(current, rowIds, caseId) : current));
  }, []);

  const applyLocalCancelLink = useCallback((rowIds: string[]) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterCancelLink(current, rowIds) : current));
  }, []);

  const applyLocalWithdrawLink = useCallback((rowIds: string[], afterGroups: WorkbenchCandidateGroup[]) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterWithdrawLink(current, rowIds, afterGroups) : current));
  }, []);

  const applyLocalHandledException = useCallback((rowIds: string[], exceptionCode: string, label: string) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterHandledException(current, rowIds, exceptionCode, label) : current));
  }, []);

  const applyLocalCancelException = useCallback((rowIds: string[]) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterCancelException(current, rowIds) : current));
  }, []);

  const applyLocalIgnoreRow = useCallback((row: WorkbenchRecord) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterIgnoreRow(current, row.id) : current));
    setIgnoredData((current) => updateIgnoredDataAfterIgnore(current, row));
  }, []);

  const applyLocalUnignoreRow = useCallback((row: WorkbenchRecord) => {
    setIgnoredData((current) => updateIgnoredDataAfterUnignore(current, row.id));
    setWorkbenchData((current) => (current ? updateWorkbenchAfterUnignoreRow(current, row) : current));
  }, []);

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
    options?: { background?: boolean; includeAuxiliary?: boolean },
  ) {
    const background = options?.background ?? false;
    const includeAuxiliary = options?.includeAuxiliary ?? false;

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
      const workbenchPayload = await fetchWorkbenchWithProgress(month, signal, (progress) => {
        setLoadProgress(progress);
      });
      if (signal?.aborted) {
        return;
      }
      setWorkbenchData(workbenchPayload);
      if (!background) {
        setIsLoading(false);
      } else {
        setIsRefreshing(false);
        setLastActionMessage(null);
      }
      if (includeAuxiliary) {
        void loadWorkbenchAuxiliaryData(month, signal);
      }
    } catch {
      if (signal?.aborted) {
        return;
      }
      if (!background) {
        setWorkbenchData(null);
        setIgnoredData({ month, rows: [] });
        setLoadError("工作台数据加载失败，请稍后重试。");
        setIsLoading(false);
      } else {
        setIsRefreshing(false);
        setLastActionMessage(null);
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    clearSelection();
    setLastActionMessage(null);
    setDetailError(null);
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, controller.signal, { includeAuxiliary: true });
    return () => controller.abort();
  }, []);

  useEffect(() => {
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
  }, [applyOaSyncStatus]);

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
    () => buildWorkbenchDisplayGroups(workbenchData?.paired.groups ?? [], deferredPairedDisplayState),
    [deferredPairedDisplayState, workbenchData],
  );

  const displayOpenGroups = useMemo(
    () => buildWorkbenchDisplayGroups(visibleOpenGroups, deferredOpenDisplayState),
    [deferredOpenDisplayState, visibleOpenGroups],
  );

  const allRows = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchRecord[];
    }
    return [
      ...flattenGroups(displayPairedGroups),
      ...flattenGroups(displayOpenGroups),
    ];
  }, [displayOpenGroups, displayPairedGroups, workbenchData]);

  const allGroups = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchCandidateGroup[];
    }
    return [...displayPairedGroups, ...displayOpenGroups];
  }, [displayOpenGroups, displayPairedGroups, workbenchData]);

  const openRows = useMemo(() => {
    return flattenGroups(displayOpenGroups);
  }, [displayOpenGroups]);

  const pairedRows = useMemo(() => {
    return flattenGroups(displayPairedGroups);
  }, [displayPairedGroups]);

  const selectedOpenRows = useMemo(() => {
    const rowsById = new Map(openRows.map((row) => [row.id, row]));
    return selectedOpenRowIds
      .map((rowId) => rowsById.get(rowId))
      .filter((row): row is WorkbenchRecord => row !== undefined);
  }, [openRows, selectedOpenRowIds]);

  const openSelectionSummary = useMemo(
    () => ({
      total: selectedOpenRows.length,
      oa: selectedOpenRows.filter((row) => row.recordType === "oa").length,
      bank: selectedOpenRows.filter((row) => row.recordType === "bank").length,
      invoice: selectedOpenRows.filter((row) => row.recordType === "invoice").length,
    }),
    [selectedOpenRows],
  );

  const selectedPairedRows = useMemo(() => {
    const rowsById = new Map(pairedRows.map((row) => [row.id, row]));
    return selectedPairedRowIds
      .map((rowId) => rowsById.get(rowId))
      .filter((row): row is WorkbenchRecord => row !== undefined);
  }, [pairedRows, selectedPairedRowIds]);

  const pairedSelectionSummary = useMemo(
    () => ({
      total: selectedPairedRows.length,
      oa: selectedPairedRows.filter((row) => row.recordType === "oa").length,
      bank: selectedPairedRows.filter((row) => row.recordType === "bank").length,
      invoice: selectedPairedRows.filter((row) => row.recordType === "invoice").length,
    }),
    [selectedPairedRows],
  );

  const canConfirmOpenSelection = openSelectionSummary.bank > 0 && openSelectionSummary.oa + openSelectionSummary.invoice > 0;
  const canHandleOpenSelectionException = openSelectionSummary.total > 0;
  const canWithdrawOpenSelection = useMemo(() => {
    if (selectedOpenRowIds.length === 0) {
      return false;
    }
    const selectedRowIdSet = new Set(selectedOpenRowIds);
    return (workbenchData?.open.groups ?? []).some((group) =>
      group.canWithdraw
      && [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice].some((row) => selectedRowIdSet.has(row.id)),
    );
  }, [selectedOpenRowIds, workbenchData?.open.groups]);
  const isOpenConfirmSelectionDisabled = openSelectionSummary.total < 2;
  const isOpenExceptionSelectionDisabled = openSelectionSummary.total < 1;
  const isPairedCancelSelectionDisabled = pairedSelectionSummary.total < 1;

  const collectCaseRowIds = useCallback((row: WorkbenchRecord) => {
    const containingGroup = allGroups.find((group) =>
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
    const relatedIds = allRows.filter((candidate) => candidate.caseId === row.caseId).map((candidate) => candidate.id);
    return relatedIds.length > 0 ? relatedIds : [row.id];
  }, [allGroups, allRows]);

  const handleOpenDetail = useCallback(async (row: WorkbenchRecord) => {
    setDetailError(null);
    setIsDetailLoading(true);
    openDetail(row);
    try {
      const detailedRow = await fetchWorkbenchRowDetail(row.id);
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
    if (isWorkbenchFreshnessBlocked) {
      openActionResultDialog("关联台正在同步，请刷新完成后再操作。");
      return false;
    }
    return true;
  }, [canMutateData, healthStatus.blocksMutations, isWorkbenchFreshnessBlocked, openActionResultDialog]);

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

  const openOaBankExceptionDialog = useCallback((rows: WorkbenchRecord[]) => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    const summary = summarizeOaBankRows(rows);
    const optionState = buildOaBankExceptionOptions(summary);
    if (summary.invoiceCount > 0) {
      openActionResultDialog("OA与银行流水异常处理暂不支持发票，请先取消发票选择。");
      return;
    }
    if (summary.oaCount === 0 && summary.bankCount === 0) {
      openActionResultDialog("请先选择 OA 或银行流水记录。");
      return;
    }
    if (optionState.mode === "invalid" || optionState.options.length === 0) {
      openActionResultDialog("当前选择无法进入 OA/流水异常处理。");
      return;
    }
    handleCloseDetail();
    setOaBankExceptionDialog({ rows });
  }, [ensureCanWriteWorkbench, handleCloseDetail, openActionResultDialog]);

  const handleCloseOaBankExceptionDialog = () => {
    setOaBankExceptionDialog(null);
  };

  const runBlockingAction = useCallback(async ({
    loadingMessage,
    successTitle = "处理完成",
    action,
  }: {
    loadingMessage: string;
    successTitle?: string;
    action: () => Promise<string>;
  }) => {
    handleCloseDetail();
    setActionDialog({
      phase: "loading",
      title: "处理中",
      message: loadingMessage,
    });

    try {
      const message = await action();
      setActionDialog({
        phase: "result",
        title: successTitle,
        message,
      });
    } catch (error) {
      setActionDialog({
        phase: "result",
        title: "操作失败",
        message: actionErrorMessage(error),
      });
    }
  }, [handleCloseDetail]);

  const handleSubmitOaBankException = async ({
    rows,
    exceptionCode,
    exceptionLabel,
    comment,
  }: {
    rows: WorkbenchRecord[];
    exceptionCode: string;
    exceptionLabel: string;
    comment: string;
  }) => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    setOaBankExceptionDialog(null);
    await runBlockingAction({
      loadingMessage: "正在执行异常处理...",
      action: async () => {
        const result = await submitOaBankException({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: rows.map((row) => row.id),
          exceptionCode,
          exceptionLabel,
          comment,
        });
        clearOpenSelection();
        applyLocalHandledException(
          rows.map((row) => row.id),
          exceptionCode,
          exceptionLabel,
        );
        return result.message;
      },
    });
  };

  const handleConfirmFromOaBankException = async (rows: WorkbenchRecord[]) => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    setOaBankExceptionDialog(null);
    await openConfirmPreview(rows);
  };

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
      const rowsById = new Map(allRows.map((candidate) => [candidate.id, candidate]));
      await openConfirmPreview(rowIds.map((rowId) => rowsById.get(rowId)).filter((candidate): candidate is WorkbenchRecord => Boolean(candidate)));
      return;
    }

    if (action === "flag-exception") {
      if (row.recordType !== "invoice") {
        openOaBankExceptionDialog([row]);
        return;
      }
      await runBlockingAction({
        loadingMessage: "正在执行异常处理...",
        action: async () => {
          const result = await markWorkbenchException({
            month: WORKBENCH_VIEW_MONTH,
            rowId: row.id,
            exceptionCode: row.recordType === "invoice" ? "pending_collection" : "manual_review",
            comment: `由关联台标记异常：${row.id}`,
          });
          refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
          return result.message;
        },
      });
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
          applyLocalIgnoreRow(row);
          refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
          return result.message;
        },
      });
      return;
    }

    if (action === "unlink") {
      const rowIds = collectCaseRowIds(row);
      const rowsById = new Map(allRows.map((candidate) => [candidate.id, candidate]));
      await openWithdrawPreview(rowIds.map((rowId) => rowsById.get(rowId)).filter((candidate): candidate is WorkbenchRecord => Boolean(candidate)));
      return;
    }

    if (action === "handle-exception") {
      openOaBankExceptionDialog([row]);
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
    openOaBankExceptionDialog,
    applyLocalCancelException,
    applyLocalConfirmLink,
    applyLocalWithdrawLink,
    applyLocalHandledException,
    applyLocalIgnoreRow,
    refreshWorkbenchDataInBackground,
    runBlockingAction,
    allRows,
  ]);

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
          applyLocalConfirmLink(rowIds, caseId);
          return result.message;
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
        });
        clearPairedSelection();
        clearOpenSelection();
        applyLocalWithdrawLink(rowIds, preview.after.groups);
        return result.message;
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
    await openConfirmPreview(selectedOpenRows);
  };

  const handleWithdrawOpenSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (!canWithdrawOpenSelection) {
      openActionResultDialog("当前选择没有可撤回的关联历史。");
      return;
    }
    const selectedRowIdSet = new Set(selectedOpenRowIds);
    const selectedGroups = (workbenchData?.open.groups ?? []).filter((group) =>
      group.canWithdraw
      && [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice].some((row) => selectedRowIdSet.has(row.id)),
    );
    await openWithdrawPreview(
      selectedGroups.flatMap((group) => [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice]),
    );
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
    const containsInvoice = selectedOpenRows.some((row) => row.recordType === "invoice");
    const containsOaOrBank = selectedOpenRows.some((row) => row.recordType === "oa" || row.recordType === "bank");
    if (containsInvoice && containsOaOrBank) {
      openActionResultDialog("OA与银行流水异常处理暂不支持发票，请先取消发票选择。");
      return;
    }
    if (containsInvoice) {
      await runBlockingAction({
        loadingMessage: "正在执行异常处理...",
        action: async () => {
          await Promise.all(
            selectedOpenRows.map((row) =>
              markWorkbenchException({
                month: WORKBENCH_VIEW_MONTH,
                rowId: row.id,
                exceptionCode: "pending_collection",
                comment: `由关联台批量标记异常：${row.id}`,
              })),
          );
          clearOpenSelection();
          refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
          return `已对 ${selectedOpenRows.length} 条记录执行异常处理。`;
        },
      });
      return;
    }
    openOaBankExceptionDialog(selectedOpenRows);
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

    const selectedRowIds = new Set(selectedPairedRowIds);
    const selectedGroups = (workbenchData?.paired.groups ?? []).filter((group) =>
      [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice].some((row) => selectedRowIds.has(row.id)),
    );

    if (selectedGroups.length === 0) {
      openActionResultDialog("请先选择已配对记录。");
      return;
    }
    await openWithdrawPreview(
      selectedGroups.flatMap((group) => [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice]),
    );
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
        applyLocalUnignoreRow(row);
        refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
        return result.message;
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
        applyLocalCancelException(rows.map((row) => row.id));
        return result.message;
      },
    });
  };

  const pairedPanes = useMemo<WorkbenchPane[]>(
    () => {
      const paneRows = buildWorkbenchPaneRows(displayPairedGroups);
      return [
        { id: "oa", title: "OA", rows: paneRows.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice },
      ];
    },
    [displayPairedGroups],
  );

  const openPanes = useMemo<WorkbenchPane[]>(
    () => {
      const paneRows = buildWorkbenchPaneRows(displayOpenGroups);
      return [
        { id: "oa", title: "OA", rows: paneRows.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice },
      ];
    },
    [displayOpenGroups],
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

  const pairedZoneElement = (
    <WorkbenchZone
      canMutateData={canWriteWorkbench}
      getRowState={getRowState}
      isExpanded={expandedZoneId === "paired"}
      isVisible={isPairedVisible}
      onClearSelection={handleClearPairedSelection}
      onOpenDetail={handleOpenDetail}
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
      highlightedRowId={null}
      panes={pairedPanes}
      primarySelectionActionLabel="撤回关联"
      selectionSummary={pairedSelectionSummary}
      title={`已配对 ${workbenchData?.summary.pairedCount ?? 0} 条`}
      tone="success"
      zoneId="paired"
    />
  );

  const openZoneElement = (
    <WorkbenchZone
      auxiliaryHeaderActions={openAuxiliaryHeaderActions}
      canMutateData={canWriteWorkbench}
      getRowState={getRowState}
      isExpanded={expandedZoneId === "open"}
      isVisible={isOpenVisible}
      onClearSelection={handleClearOpenSelection}
      onOpenDetail={handleOpenDetail}
      onPrimarySelectionAction={handleConfirmOpenSelection}
      primarySelectionActionDisabled={isOpenConfirmSelectionDisabled || !canWriteWorkbench}
      onRowAction={handleRowAction}
      onClearPaneSearch={handleClearPaneSearch}
      onClosePaneSearch={handleClosePaneSearch}
      onSelectRow={handleSelectRow}
      onSecondarySelectionAction={handleOpenSelectionException}
      secondarySelectionActionDisabled={isOpenExceptionSelectionDisabled || !canWriteWorkbench}
      onTertiarySelectionAction={handleWithdrawOpenSelection}
      tertiarySelectionActionDisabled={!canWithdrawOpenSelection || !canWriteWorkbench}
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
      highlightedRowId={null}
      panes={openPanes}
      primarySelectionActionLabel="确认关联"
      secondarySelectionActionLabel="异常处理"
      tertiarySelectionActionLabel="撤回关联"
      selectionSummary={openSelectionSummary}
      title={`未配对 ${workbenchData?.summary.openCount ?? 0} 条`}
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
      {oaBankExceptionDialog ? (
        <OaBankExceptionModal
          rows={oaBankExceptionDialog.rows}
          onClose={handleCloseOaBankExceptionDialog}
          onConfirmLink={() => handleConfirmFromOaBankException(oaBankExceptionDialog.rows)}
          onSubmitException={({ exceptionCode, exceptionLabel, comment }) =>
            handleSubmitOaBankException({
              rows: oaBankExceptionDialog.rows,
              exceptionCode,
              exceptionLabel,
              comment,
            })}
        />
      ) : null}
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
  const submitLabel = isWithdraw ? "确认撤回" : "确认关联";
  const title = isWithdraw ? "撤回关联预览" : "确认关联预览";
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
        {preview.message ? <div className={`relation-preview-message ${preview.requiresNote ? "warning" : ""}`}>{preview.message}</div> : null}
        <div className="relation-preview-stack">
          <RelationPreviewTriPane
            title="操作前"
            testId="relation-preview-before"
            groups={preview.before.groups}
            totals={preview.amountSummary.before}
            mismatchFields={preview.amountSummary.mismatchFields}
            columnLayouts={columnLayouts}
          />
          <RelationPreviewTriPane
            title="操作后"
            testId="relation-preview-after"
            groups={preview.after.groups}
            totals={preview.amountSummary.after}
            mismatchFields={preview.amountSummary.mismatchFields}
            columnLayouts={columnLayouts}
          />
        </div>
        <label className="relation-preview-note">
          <span>备注{noteRequired ? "（必填）" : ""}</span>
          <textarea aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <footer className="detail-modal-actions">
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

function summarizeOaBankRows(rows: WorkbenchRecord[]) {
  return rows.reduce(
    (summary, row) => {
      if (row.recordType === "oa") {
        summary.oaCount += 1;
      } else if (row.recordType === "bank") {
        summary.bankCount += 1;
      } else if (row.recordType === "invoice") {
        summary.invoiceCount += 1;
      }
      return summary;
    },
    { oaCount: 0, bankCount: 0, invoiceCount: 0 },
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

function updateWorkbenchAfterConfirmLink(data: WorkbenchData, rowIds: string[], caseId?: string) {
  const targetRowIds = new Set(rowIds);
  const selectedRows: WorkbenchRecord[] = [];
  const nextOpenGroups = data.open.groups.flatMap((group) => {
    const nextGroup: WorkbenchCandidateGroup = {
      ...group,
      rows: {
        oa: group.rows.oa.filter((row) => {
          const keep = !targetRowIds.has(row.id);
          if (!keep) {
            selectedRows.push(row);
          }
          return keep;
        }),
        bank: group.rows.bank.filter((row) => {
          const keep = !targetRowIds.has(row.id);
          if (!keep) {
            selectedRows.push(row);
          }
          return keep;
        }),
        invoice: group.rows.invoice.filter((row) => {
          const keep = !targetRowIds.has(row.id);
          if (!keep) {
            selectedRows.push(row);
          }
          return keep;
        }),
      },
    };

    return flattenGroups([nextGroup]).length > 0 ? [nextGroup] : [];
  });

  if (selectedRows.length === 0) {
    return data;
  }

  const resolvedCaseId = caseId
    || selectedRows.find((row) => row.caseId)?.caseId
    || `LOCAL-CONFIRM-${selectedRows[0].id}`;
  const nextPairedGroup: WorkbenchCandidateGroup = {
    id: `local-paired-${resolvedCaseId}`,
    groupType: "manual_confirmed",
    matchConfidence: "high",
    reason: "人工确认关联",
    rows: {
      oa: selectedRows
        .filter((row) => row.recordType === "oa")
        .map((row) => updateWorkbenchRowForLinked(row, resolvedCaseId)),
      bank: selectedRows
        .filter((row) => row.recordType === "bank")
        .map((row) => updateWorkbenchRowForLinked(row, resolvedCaseId)),
      invoice: selectedRows
        .filter((row) => row.recordType === "invoice")
        .map((row) => updateWorkbenchRowForLinked(row, resolvedCaseId)),
    },
  };

  return rebuildWorkbenchSummary({
    ...data,
    paired: {
      groups: [nextPairedGroup, ...data.paired.groups],
    },
    open: {
      groups: nextOpenGroups,
    },
  });
}

function updateWorkbenchAfterCancelLink(data: WorkbenchData, rowIds: string[]) {
  const targetRowIds = new Set(rowIds);
  const reopenedGroups: WorkbenchCandidateGroup[] = [];
  const nextPairedGroups = data.paired.groups.flatMap((group) => {
    const groupRows = flattenGroups([group]);
    const shouldMove = groupRows.some((row) => targetRowIds.has(row.id));
    if (!shouldMove) {
      return [group];
    }
    reopenedGroups.push({
      id: `local-open-${group.id}`,
      groupType: "candidate",
      matchConfidence: group.matchConfidence,
      reason: "取消关联后待重新处理",
      rows: {
        oa: group.rows.oa.map((row) => updateWorkbenchRowForOpen(row, "取消关联，待重新处理")),
        bank: group.rows.bank.map((row) => updateWorkbenchRowForOpen(row, "取消关联，待重新处理")),
        invoice: group.rows.invoice.map((row) => updateWorkbenchRowForOpen(row, "取消关联，待重新处理")),
      },
    });
    return [];
  });

  if (reopenedGroups.length === 0) {
    return data;
  }

  return rebuildWorkbenchSummary({
    ...data,
    paired: {
      groups: nextPairedGroups,
    },
    open: {
      groups: [...reopenedGroups, ...data.open.groups],
    },
  });
}

function updateWorkbenchAfterWithdrawLink(
  data: WorkbenchData,
  rowIds: string[],
  afterGroups: WorkbenchCandidateGroup[],
) {
  if (afterGroups.length === 0) {
    return updateWorkbenchAfterCancelLink(data, rowIds);
  }

  const targetRowIds = new Set(rowIds);
  const restoredOpenGroups = afterGroups.flatMap((group, index) => {
    const restoredGroup: WorkbenchCandidateGroup = {
      ...group,
      id: `local-open-withdraw-${group.id}-${index}`,
      reason: group.reason || "撤回关联后恢复关系",
      rows: {
        oa: group.rows.oa.map((row) => updateWorkbenchRowForWithdrawPreview(row, group)),
        bank: group.rows.bank.map((row) => updateWorkbenchRowForWithdrawPreview(row, group)),
        invoice: group.rows.invoice.map((row) => updateWorkbenchRowForWithdrawPreview(row, group)),
      },
    };
    return flattenGroups([restoredGroup]).length > 0 ? [restoredGroup] : [];
  });

  return rebuildWorkbenchSummary({
    ...data,
    paired: {
      groups: removeRowsFromWorkbenchGroups(data.paired.groups, targetRowIds),
    },
    open: {
      groups: [
        ...restoredOpenGroups,
        ...removeRowsFromWorkbenchGroups(data.open.groups, targetRowIds),
      ],
    },
  });
}

function removeRowsFromWorkbenchGroups(groups: WorkbenchCandidateGroup[], rowIds: Set<string>) {
  return groups.flatMap((group) => {
    const nextGroup = {
      ...group,
      rows: {
        oa: group.rows.oa.filter((row) => !rowIds.has(row.id)),
        bank: group.rows.bank.filter((row) => !rowIds.has(row.id)),
        invoice: group.rows.invoice.filter((row) => !rowIds.has(row.id)),
      },
    };
    return flattenGroups([nextGroup]).length > 0 ? [nextGroup] : [];
  });
}

function updateWorkbenchAfterHandledException(data: WorkbenchData, rowIds: string[], exceptionCode: string, label: string) {
  const targetRowIds = new Set(rowIds);
  const nextOpenGroups = data.open.groups.map((group) => ({
    ...group,
    rows: {
      oa: group.rows.oa.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForException(row, exceptionCode, label) : row),
      bank: group.rows.bank.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForException(row, exceptionCode, label) : row),
      invoice: group.rows.invoice.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForException(row, exceptionCode, label) : row),
    },
  }));

  return rebuildWorkbenchSummary({
    ...data,
    open: {
      groups: nextOpenGroups,
    },
  });
}

function updateWorkbenchAfterCancelException(data: WorkbenchData, rowIds: string[]) {
  const targetRowIds = new Set(rowIds);
  const nextOpenGroups = data.open.groups.map((group) => ({
    ...group,
    rows: {
      oa: group.rows.oa.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForOpen(row, pendingLabelForRow(row)) : row),
      bank: group.rows.bank.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForOpen(row, pendingLabelForRow(row)) : row),
      invoice: group.rows.invoice.map((row) => targetRowIds.has(row.id) ? updateWorkbenchRowForOpen(row, pendingLabelForRow(row)) : row),
    },
  }));

  return rebuildWorkbenchSummary({
    ...data,
    open: {
      groups: nextOpenGroups,
    },
  });
}

function updateWorkbenchAfterIgnoreRow(data: WorkbenchData, rowId: string) {
  const nextOpenGroups = data.open.groups.flatMap((group) => {
    const nextGroup: WorkbenchCandidateGroup = {
      ...group,
      rows: {
        oa: group.rows.oa,
        bank: group.rows.bank,
        invoice: group.rows.invoice.filter((row) => row.id !== rowId),
      },
    };

    return flattenGroups([nextGroup]).length > 0 ? [nextGroup] : [];
  });

  return rebuildWorkbenchSummary({
    ...data,
    open: {
      groups: nextOpenGroups,
    },
  });
}

function updateWorkbenchAfterUnignoreRow(data: WorkbenchData, row: WorkbenchRecord) {
  const reopenedRow = updateWorkbenchRowForOpen(row, "待重新处理");
  return rebuildWorkbenchSummary({
    ...data,
    open: {
      groups: [
        {
          id: `local-open-unignored-${row.id}`,
          groupType: "candidate",
          matchConfidence: "medium",
          reason: "撤回忽略后待重新处理",
          rows: {
            oa: reopenedRow.recordType === "oa" ? [reopenedRow] : [],
            bank: reopenedRow.recordType === "bank" ? [reopenedRow] : [],
            invoice: reopenedRow.recordType === "invoice" ? [reopenedRow] : [],
          },
        },
        ...data.open.groups,
      ],
    },
  });
}

function updateIgnoredDataAfterIgnore(data: IgnoredWorkbenchData, row: WorkbenchRecord): IgnoredWorkbenchData {
  if (data.rows.some((candidate) => candidate.id === row.id)) {
    return data;
  }

  return {
    ...data,
    rows: [row, ...data.rows],
  };
}

function updateIgnoredDataAfterUnignore(data: IgnoredWorkbenchData, rowId: string): IgnoredWorkbenchData {
  return {
    ...data,
    rows: data.rows.filter((row) => row.id !== rowId),
  };
}

function rebuildWorkbenchSummary(data: WorkbenchData): WorkbenchData {
  const pairedRows = flattenGroups(data.paired.groups);
  const openRows = flattenGroups(data.open.groups);
  const visibleOpenRows = flattenGroups(removeProcessedExceptionRows(data.open.groups));
  const exceptionRows = flattenGroups(collectProcessedExceptionGroups(data.open.groups));
  const allRows = [...pairedRows, ...openRows];

  return {
    ...data,
    summary: {
      oaCount: allRows.filter((row) => row.recordType === "oa").length,
      bankCount: allRows.filter((row) => row.recordType === "bank").length,
      invoiceCount: allRows.filter((row) => row.recordType === "invoice").length,
      pairedCount: pairedRows.length,
      openCount: visibleOpenRows.length,
      exceptionCount: exceptionRows.length,
      totalCount: allRows.length,
    },
  };
}

function updateWorkbenchRowForLinked(row: WorkbenchRecord, caseId: string): WorkbenchRecord {
  return {
    ...row,
    caseId,
    status: "完全关联",
    statusCode: "fully_linked",
    statusTone: "success",
    exceptionHandled: false,
    availableActions: ["detail"],
    actionVariant: "detail-only",
    tableValues: {
      ...row.tableValues,
      reconciliationStatus: row.recordType === "oa" ? "完全关联" : row.tableValues.reconciliationStatus,
      invoiceRelationStatus: row.recordType === "bank" ? "完全关联" : row.tableValues.invoiceRelationStatus,
    },
  };
}

function updateWorkbenchRowForException(row: WorkbenchRecord, code: string, label: string): WorkbenchRecord {
  const availableActions = row.recordType === "bank"
    ? ["detail", "view_relation", "cancel_link", "handle_exception"]
    : row.recordType === "invoice"
      ? ["detail", "confirm_link", "mark_exception", "ignore"]
      : ["detail", "confirm_link", "mark_exception"];

  return {
    ...row,
    caseId: undefined,
    status: label,
    statusCode: code,
    statusTone: "danger",
    exceptionHandled: true,
    availableActions,
    actionVariant: row.recordType === "bank" ? "bank-review" : "confirm-exception",
    tableValues: {
      ...row.tableValues,
      reconciliationStatus: row.recordType === "oa" ? label : row.tableValues.reconciliationStatus,
      invoiceRelationStatus: row.recordType === "bank" ? label : row.tableValues.invoiceRelationStatus,
    },
  };
}

function pendingLabelForRow(row: WorkbenchRecord) {
  if (row.recordType === "oa") {
    return "待找流水与发票";
  }
  if (row.recordType === "bank") {
    return "待关联发票";
  }
  return "待匹配流水";
}

function updateWorkbenchRowForOpen(row: WorkbenchRecord, label: string): WorkbenchRecord {
  const pendingCode = row.recordType === "oa"
    ? "pending_match"
    : row.recordType === "bank"
      ? "pending_invoice_match"
      : "pending_collection";
  const availableActions = row.recordType === "bank"
    ? ["detail", "view_relation", "cancel_link", "handle_exception"]
    : row.recordType === "invoice"
      ? ["detail", "confirm_link", "mark_exception", "ignore"]
      : ["detail", "confirm_link", "mark_exception"];

  return {
    ...row,
    caseId: undefined,
    status: label,
    statusCode: pendingCode,
    statusTone: "warn",
    exceptionHandled: false,
    availableActions,
    actionVariant: row.recordType === "bank" ? "bank-review" : "confirm-exception",
    tableValues: {
      ...row.tableValues,
      reconciliationStatus: row.recordType === "oa" ? label : row.tableValues.reconciliationStatus,
      invoiceRelationStatus: row.recordType === "bank" ? label : row.tableValues.invoiceRelationStatus,
    },
  };
}

function updateWorkbenchRowForWithdrawPreview(row: WorkbenchRecord, group: WorkbenchCandidateGroup): WorkbenchRecord {
  const caseId = group.id.startsWith("case:") ? group.id.slice("case:".length) : undefined;
  const openRow = updateWorkbenchRowForOpen(row, withdrawPreviewOpenLabel(row, group));
  return {
    ...openRow,
    caseId,
    tags: row.tags,
  };
}

function withdrawPreviewOpenLabel(row: WorkbenchRecord, group: WorkbenchCandidateGroup) {
  const hasOa = group.rows.oa.length > 0;
  const hasBank = group.rows.bank.length > 0;
  const hasInvoice = group.rows.invoice.length > 0;
  const rowCount = group.rows.oa.length + group.rows.bank.length + group.rows.invoice.length;
  if (rowCount <= 1) {
    return "待重新处理";
  }
  if (hasOa && hasInvoice && !hasBank) {
    return "待找流水";
  }
  if (hasOa && hasBank && !hasInvoice) {
    return "待找发票";
  }
  if (hasBank && hasInvoice && !hasOa) {
    return "待找OA";
  }
  return pendingLabelForRow(row);
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
