import { Button, Input, TextArea } from "@heroui/react";
import { useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../components/common/AppDrawer";
import AppDialog from "../components/common/AppDialog";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import ActionStatusModal from "../components/workbench/ActionStatusModal";
import DetailDrawer from "../components/workbench/DetailDrawer";
import RelationPreviewTriPane from "../components/workbench/RelationPreviewTriPane";
import WorkbenchExceptionDrawer from "../components/workbench/WorkbenchExceptionDrawer";
import WorkbenchInvoiceAssignmentDrawer from "../components/workbench/WorkbenchInvoiceAssignmentDrawer";
import WorkbenchInvoiceEntryDrawer from "../components/workbench/WorkbenchInvoiceEntryDrawer";
import WorkbenchReceiptDrawer from "../components/workbench/WorkbenchReceiptDrawer";
import WorkbenchZone from "../components/workbench/WorkbenchZone";
import type { WorkbenchPane } from "../components/workbench/ResizableTriPane";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus } from "../contexts/AppHealthStatusContext";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  cancelWorkbenchCashSpecial,
  confirmWorkbenchCashPassThrough,
  confirmWorkbenchCashTicketPurchase,
  confirmWorkbenchLink,
  fetchWorkbenchExceptionGroups,
  fetchWorkbenchGroupDetail,
  fetchWorkbenchGroupsPage,
  fetchWorkbenchFilterOptions,
  fetchWorkbenchInitialPage,
  fetchWorkbenchOaSyncStatus,
  fetchWorkbenchRowDetail,
  fetchWorkbenchSettings,
  previewWorkbenchConfirmLink,
  previewWorkbenchWithdrawLink,
  resolveWorkbenchActionErrorMessage,
  saveWorkbenchSettings,
  reviewWorkbenchAnomaly,
  withdrawWorkbenchLink,
  WorkbenchApiError,
  WORKBENCH_GROUP_PAGE_SIZE,
  type WorkbenchActionResult,
} from "../features/workbench/api";
import { fetchBankFlowRuleBatchDetail, withdrawBankFlowRuleBatch } from "../features/bankFlowRuleBatches/api";
import {
  buildWorkbenchServerPageQuery,
  buildWorkbenchDisplayGroups,
  buildWorkbenchInvoiceExpenseItemCandidates,
  buildWorkbenchPaneRows,
  createEmptyWorkbenchZoneDisplayState,
  hasWorkbenchServerPageCriteria,
  mergeWorkbenchGroupsById,
  replaceWorkbenchSupportingDocuments,
  resolveWorkbenchActivePane,
  type WorkbenchPaneTimeFilter,
  type WorkbenchZoneDisplayState,
} from "../features/workbench/groupDisplayModel";
import { reorderWorkbenchColumnLayout, type WorkbenchColumnDropPosition } from "../features/workbench/columnLayout";
import {
  buildWorkbenchSelectionContext,
  workbenchRowIdentityKey,
} from "../features/workbench/selectionModel";
import { resolveWorkbenchWriteGate } from "../features/workbench/writeGate";
import type {
  WorkbenchAmountAnomalyCode,
  WorkbenchRelationGroup,
  WorkbenchData,
  WorkbenchExceptionCounts,
  WorkbenchExceptionView,
  WorkbenchGroupsPageQuery,
  WorkbenchInitialPageResult,
  WorkbenchInvoiceExpenseItemAssignmentTarget,
  WorkbenchOaSyncStatus,
  WorkbenchOaInvoiceSupplementTarget,
  WorkbenchOaSupportingDocument,
  WorkbenchRecord,
  WorkbenchRecordIdentity,
  WorkbenchRecordType,
  WorkbenchRelationPreview,
  WorkbenchSettings,
  WorkbenchStatistics,
  WorkbenchZoneCounts,
  WorkbenchZonePageInfo,
} from "../features/workbench/types";
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
  rowTypes: WorkbenchRecordType[];
  canonicalEpoch: number;
  caseId?: string;
  idempotencyKey: string;
};

type RelationPreviewRequestKind = "confirm" | "withdraw";

type WorkbenchActionProgressPhase = "submitting" | "rereading" | "loading";

type WorkbenchActionProgress = {
  phase: WorkbenchActionProgressPhase;
  message: string;
  committed: boolean;
};

type WorkbenchActionProgressHandler = (progress: WorkbenchActionProgress) => void;

type CashTicketPurchaseDialogState = {
  rows: Array<Pick<WorkbenchRecord, "id" | "recordType">>;
  cashAmount: string;
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
    rowCounts: { oa: 0, bank: 0, invoice: 0, canonicalInvoice: 0, rows: 0 },
    hasMore: false,
    cursor: null,
    nextCursor: null,
  };
}

function createInitialZonePages(): Record<"paired" | "unpaired", WorkbenchZonePageInfo> {
  return {
    paired: createInitialZonePageInfo("paired"),
    unpaired: createInitialZonePageInfo("unpaired"),
  };
}

function resolveZoneItemCount(pageInfo: WorkbenchZonePageInfo, zoneCounts?: WorkbenchZoneCounts) {
  if (pageInfo.page > 0) {
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
    return resolveWorkbenchActionErrorMessage(error, "操作失败，请稍后重试。");
  }
  return "操作失败，请稍后重试。";
}

function workbenchReadErrorMessage(error: unknown, fallback: string) {
  return error instanceof WorkbenchApiError && error.message ? error.message : fallback;
}

function createWorkbenchAbortError() {
  return new DOMException("Workbench request superseded.", "AbortError");
}

function isWorkbenchAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
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

function actionResultMessage(result: string | WorkbenchActionResult) {
  return typeof result === "string" ? result : result.message;
}

export default function ReconciliationWorkbenchPage() {
  const { setWorkbenchStatus } = useAppChrome();
  const healthStatus = useAppHealthStatus();
  const { runOperation } = useGlobalOperationOverlay();
  const { canMutateData } = useSessionPermissions();
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
  const [oaSyncStatusError, setOaSyncStatusError] = useState<string | null>(null);
  const [loadingMoreByZone, setLoadingMoreByZone] = useState<Record<"paired" | "unpaired", boolean>>({
    paired: false,
    unpaired: false,
  });
  const [loadMoreErrorByZone, setLoadMoreErrorByZone] = useState<Record<"paired" | "unpaired", string | null>>({
    paired: null,
    unpaired: null,
  });
  const [zoneQueryLoadingByZone, setZoneQueryLoadingByZone] = useState<Record<"paired" | "unpaired", boolean>>({
    paired: false,
    unpaired: false,
  });
  const [zoneQueryErrorByZone, setZoneQueryErrorByZone] = useState<Record<"paired" | "unpaired", string | null>>({
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
  const directReadAvailable = workbenchData !== null
    && loadError === null
    && backgroundLoadError === null
    && zoneQueryErrorByZone.paired === null
    && zoneQueryErrorByZone.unpaired === null;
  const workbenchWriteGate = resolveWorkbenchWriteGate({
    canMutateData,
    mutationsBlocked: healthStatus.blocksMutations,
    directReadAvailable,
    oaSyncReachable: oaSyncStatus !== null && oaSyncStatusError === null,
    oaSyncStatus: oaSyncStatus?.status ?? null,
    oaDirtyScopes: oaSyncStatus?.dirtyScopes ?? [],
  });
  const canWriteWorkbench = workbenchWriteGate.allowed;
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRequestSeqRef = useRef(0);
  const detailRequestAbortControllerRef = useRef<AbortController | null>(null);
  const loadRequestSeqRef = useRef(0);
  const groupDetailRequestGenerationRef = useRef(0);
  const groupDetailRequestsRef = useRef(new Map<string, {
    canonicalEpoch: number;
    controller: AbortController;
    detailKey: string | undefined;
    generation: number;
    promise: Promise<void>;
  }>());
  const postCommitRereadInFlightRef = useRef(false);
  const oaSyncRefreshPendingRef = useRef(false);
  const zoneQueryRequestSeqRef = useRef<Record<"paired" | "unpaired", number>>({ paired: 0, unpaired: 0 });
  const zoneQueryAbortControllerRef = useRef<Record<"paired" | "unpaired", AbortController | null>>({ paired: null, unpaired: null });
  const zoneQueryInFlightKeyRef = useRef<Record<"paired" | "unpaired", string | null>>({ paired: null, unpaired: null });
  const loadMoreRequestSeqRef = useRef<Record<"paired" | "unpaired", number>>({ paired: 0, unpaired: 0 });
  const loadMoreInFlightRef = useRef<Record<"paired" | "unpaired", boolean>>({ paired: false, unpaired: false });
  const loadMoreAbortControllerRef = useRef<Record<"paired" | "unpaired", AbortController | null>>({ paired: null, unpaired: null });
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialogState | null>(null);
  const [receiptEditorCaseId, setReceiptEditorCaseId] = useState<string | null>(null);
  const [relationPreviewDialog, setRelationPreviewDialog] = useState<RelationPreviewDialogState | null>(null);
  const [relationPreviewRequestKind, setRelationPreviewRequestKind] = useState<RelationPreviewRequestKind | null>(null);
  const relationPreviewRequestKindRef = useRef<RelationPreviewRequestKind | null>(null);
  const relationPreviewAbortControllerRef = useRef<AbortController | null>(null);
  const relationPreviewContextKeyRef = useRef("");
  const canonicalEpochRef = useRef(0);
  const [canonicalEpoch, setCanonicalEpoch] = useState(0);
  const [workbenchSettings, setWorkbenchSettings] = useState<WorkbenchSettings | null>(null);
  const [exceptionDrawerOpen, setExceptionDrawerOpen] = useState(false);
  const [exceptionDrawerBucket, setExceptionDrawerBucket] = useState<"unpaired" | "paired">("unpaired");
  const [exceptionDrawerView, setExceptionDrawerView] = useState<WorkbenchExceptionView>("amount");
  const [exceptionDrawerRequestedCode, setExceptionDrawerRequestedCode] = useState<WorkbenchAmountAnomalyCode | null>(null);
  const [exceptionDrawerSelectedCode, setExceptionDrawerSelectedCode] = useState<WorkbenchAmountAnomalyCode | null>(null);
  const [exceptionDrawerCounts, setExceptionDrawerCounts] = useState<WorkbenchExceptionCounts | null>(null);
  const exceptionDrawerOpenRef = useRef(exceptionDrawerOpen);
  const exceptionDrawerBucketRef = useRef(exceptionDrawerBucket);
  const exceptionDrawerViewRef = useRef(exceptionDrawerView);
  const exceptionDrawerSelectedCodeRef = useRef(exceptionDrawerSelectedCode);
  exceptionDrawerOpenRef.current = exceptionDrawerOpen;
  exceptionDrawerBucketRef.current = exceptionDrawerBucket;
  exceptionDrawerViewRef.current = exceptionDrawerView;
  exceptionDrawerSelectedCodeRef.current = exceptionDrawerSelectedCode;
  const [exceptionDrawerGroups, setExceptionDrawerGroups] = useState<WorkbenchRelationGroup[]>([]);
  const [exceptionDrawerPage, setExceptionDrawerPage] = useState<WorkbenchZonePageInfo>(
    () => createInitialZonePageInfo("unpaired"),
  );
  const [pairedExceptionCount, setPairedExceptionCount] = useState(0);
  const [exceptionDrawerLoading, setExceptionDrawerLoading] = useState(false);
  const [exceptionDrawerLoadingMore, setExceptionDrawerLoadingMore] = useState(false);
  const [exceptionDrawerError, setExceptionDrawerError] = useState<string | null>(null);
  const exceptionDrawerRequestRef = useRef<AbortController | null>(null);
  const exceptionDrawerRequestGenerationRef = useRef(0);
  const exceptionGroupDetailRequestGenerationRef = useRef(0);
  const exceptionGroupDetailRequestsRef = useRef(new Map<string, {
    bucket: "unpaired" | "paired";
    canonicalEpoch: number;
    controller: AbortController;
    detailKey: string | undefined;
    generation: number;
    promise: Promise<WorkbenchRelationGroup>;
  }>());
  const [exceptionDrawerContentGeneration, setExceptionDrawerContentGeneration] = useState(0);
  const [exceptionDrawerReloadGeneration, setExceptionDrawerReloadGeneration] = useState(0);
  const [cashTicketPurchaseDialog, setCashTicketPurchaseDialog] = useState<CashTicketPurchaseDialogState | null>(null);
  const [invoiceEntryTarget, setInvoiceEntryTarget] = useState<WorkbenchOaInvoiceSupplementTarget | null>(null);
  const [invoiceAssignmentTarget, setInvoiceAssignmentTarget] = useState<WorkbenchInvoiceExpenseItemAssignmentTarget | null>(null);
  const hasOaSyncRefreshBlockingInteraction = detailRow !== null
    || isDetailLoading
    || explicitSelectedPairedRows.length > 0
    || explicitSelectedOpenRows.length > 0
    || actionDialog !== null
    || receiptEditorCaseId !== null
    || relationPreviewRequestKind !== null
    || relationPreviewDialog !== null
    || exceptionDrawerOpen
    || cashTicketPurchaseDialog !== null
    || invoiceEntryTarget !== null
    || invoiceAssignmentTarget !== null;
  const hasOaSyncRefreshBlockingInteractionRef = useRef(hasOaSyncRefreshBlockingInteraction);
  useLayoutEffect(() => {
    hasOaSyncRefreshBlockingInteractionRef.current = hasOaSyncRefreshBlockingInteraction;
  }, [hasOaSyncRefreshBlockingInteraction]);
  const pairedDisplaySession = usePageSessionState<WorkbenchZoneDisplayState>({
    pageKey: "reconciliation-workbench",
    stateKey: "pairedDisplayState",
    version: 3,
    initialValue: createEmptyWorkbenchZoneDisplayState(),
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isWorkbenchZoneDisplayState,
    debounceMs: 100,
  });
  const openDisplaySession = usePageSessionState<WorkbenchZoneDisplayState>({
    pageKey: "reconciliation-workbench",
    stateKey: "openDisplayState",
    version: 3,
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
  const oaSyncStatusAbortControllerRef = useRef<AbortController | null>(null);
  const oaSyncStatusRequestSeqRef = useRef(0);
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
  const latestZoneServerPageQueries = useMemo<Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>>(
    () => ({
      paired: buildWorkbenchServerPageQuery(pairedDisplayState),
      unpaired: buildWorkbenchServerPageQuery(openDisplayState),
    }),
    [openDisplayState, pairedDisplayState],
  );
  const latestZoneServerPageQueriesRef = useRef(latestZoneServerPageQueries);
  latestZoneServerPageQueriesRef.current = latestZoneServerPageQueries;
  const [oaSyncShellStatus, setOaSyncShellStatus] = useState<{ level: "ok" | "pending" | "error"; reason: string } | null>(null);

  const invalidateGroupDetailRequests = useCallback(() => {
    groupDetailRequestGenerationRef.current += 1;
    groupDetailRequestsRef.current.forEach(({ controller }) => controller.abort());
    groupDetailRequestsRef.current.clear();
  }, []);

  const invalidateExceptionGroupDetailRequests = useCallback(() => {
    exceptionGroupDetailRequestGenerationRef.current += 1;
    exceptionGroupDetailRequestsRef.current.forEach(({ controller }) => controller.abort());
    exceptionGroupDetailRequestsRef.current.clear();
  }, []);

  const loadFilterOptions = useCallback((
    zone: "paired" | "unpaired",
    request: Parameters<typeof fetchWorkbenchFilterOptions>[2],
    signal?: AbortSignal,
  ) => fetchWorkbenchFilterOptions(
    WORKBENCH_VIEW_MONTH,
    zone,
    request,
    zoneServerPageQueries[zone],
    signal,
  ), [zoneServerPageQueries]);

  const updateZoneDisplayState = useCallback((
    zoneId: "paired" | "unpaired",
    updater: (current: WorkbenchZoneDisplayState) => WorkbenchZoneDisplayState,
  ) => {
    loadMoreRequestSeqRef.current[zoneId] += 1;
    loadMoreInFlightRef.current[zoneId] = false;
    loadMoreAbortControllerRef.current[zoneId]?.abort();
    loadMoreAbortControllerRef.current[zoneId] = null;
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
    if (
      postCommitRereadInFlightRef.current
      || hasOaSyncRefreshBlockingInteractionRef.current
    ) {
      oaSyncRefreshPendingRef.current = true;
      return;
    }
    void loadWorkbenchData(month, undefined, {
      background: true,
      includeAuxiliary: false,
      zoneQueries: latestZoneServerPageQueriesRef.current,
      forceFresh: true,
      deferForActiveInteraction: true,
    });
  }, []);

  const scheduleOaSyncWorkbenchRefresh = useCallback(() => {
    if (postCommitRereadInFlightRef.current) {
      oaSyncRefreshPendingRef.current = true;
      return;
    }
    if (oaSyncRefreshTimeoutRef.current !== null) {
      window.clearTimeout(oaSyncRefreshTimeoutRef.current);
    }
    oaSyncRefreshTimeoutRef.current = window.setTimeout(() => {
      oaSyncRefreshTimeoutRef.current = null;
      refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
    }, OA_SYNC_REFRESH_DEBOUNCE_MS);
  }, [refreshWorkbenchDataInBackground]);

  const applyOaSyncStatus = useCallback((status: WorkbenchOaSyncStatus) => {
    const previousStatus = previousOaSyncStatusRef.current;
    const message = status.message || (status.status === "refreshing" ? "OA 正在同步" : "OA 已同步");

    setOaSyncStatus(status);

    const oaSyncReady = status.status === "synced" && status.dirtyScopes.length === 0;
    if (status.status === "error" || status.status === "unknown") {
      setOaSyncShellStatus({ level: "error", reason: message || "OA 同步失败" });
    } else if (oaSyncReady) {
      setOaSyncShellStatus({ level: "ok", reason: message });
    } else {
      setOaSyncShellStatus({ level: "pending", reason: message });
    }

    if (previousStatus && oaSyncReady) {
      const previousReady = previousStatus.status === "synced" && previousStatus.dirtyScopes.length === 0;
      const becameReady = !previousReady;
      const versionChanged = status.version !== null && status.version !== previousStatus.version;
      const lastSyncedAtChanged = Boolean(
        status.lastSyncedAt && status.lastSyncedAt !== previousStatus.lastSyncedAt,
      );
      if (becameReady || status.changedScopes.length > 0 || versionChanged || lastSyncedAtChanged) {
        scheduleOaSyncWorkbenchRefresh();
      }
    }

    previousOaSyncStatusRef.current = status;
  }, [scheduleOaSyncWorkbenchRefresh]);

  const pollOaSyncStatus = useCallback(async () => {
    oaSyncStatusAbortControllerRef.current?.abort();
    const controller = new AbortController();
    const requestSeq = oaSyncStatusRequestSeqRef.current + 1;
    oaSyncStatusRequestSeqRef.current = requestSeq;
    oaSyncStatusAbortControllerRef.current = controller;
    try {
      const status = await fetchWorkbenchOaSyncStatus(controller.signal);
      if (controller.signal.aborted || oaSyncStatusRequestSeqRef.current !== requestSeq) {
        return;
      }
      setOaSyncStatusError(null);
      applyOaSyncStatus(status);
    } catch {
      if (controller.signal.aborted || oaSyncStatusRequestSeqRef.current !== requestSeq) {
        return;
      }
      const message = "OA 同步状态读取失败，请重试。";
      setOaSyncStatusError(message);
      setOaSyncShellStatus({ level: "error", reason: message });
    } finally {
      if (oaSyncStatusAbortControllerRef.current === controller) {
        oaSyncStatusAbortControllerRef.current = null;
      }
    }
  }, [applyOaSyncStatus]);

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
      throw new Error("流水规则批次状态已变化，请刷新后重试。");
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
      const settings = await fetchWorkbenchSettings(signal);
      if (signal?.aborted) {
        return;
      }
      setWorkbenchSettings(settings);
    } catch {
      if (signal?.aborted) {
        return;
      }
    }
  }

  function applyWorkbenchPageResult(
    workbenchPayload: WorkbenchInitialPageResult,
    resolvedZoneQueries: Record<"paired" | "unpaired", WorkbenchGroupsPageQuery>,
  ) {
    invalidateGroupDetailRequests();
    invalidateExceptionGroupDetailRequests();
    (["paired", "unpaired"] as const).forEach((zone) => {
      zoneQueryRequestSeqRef.current[zone] += 1;
      zoneQueryAbortControllerRef.current[zone]?.abort();
      zoneQueryAbortControllerRef.current[zone] = null;
      zoneQueryInFlightKeyRef.current[zone] = null;
      loadMoreRequestSeqRef.current[zone] += 1;
      loadMoreAbortControllerRef.current[zone]?.abort();
      loadMoreAbortControllerRef.current[zone] = null;
      loadMoreInFlightRef.current[zone] = false;
    });
    setZoneQueryLoadingByZone({ paired: false, unpaired: false });
    setZoneQueryErrorByZone({ paired: null, unpaired: null });
    loadMoreInFlightRef.current = { paired: false, unpaired: false };
    setLoadingMoreByZone({ paired: false, unpaired: false });
    setLoadMoreErrorByZone({ paired: null, unpaired: null });

    canonicalEpochRef.current += 1;
    const nextCanonicalEpoch = canonicalEpochRef.current;
    setCanonicalEpoch(nextCanonicalEpoch);
    relationPreviewContextKeyRef.current = `canonical:${nextCanonicalEpoch}`;

    setWorkbenchData(workbenchPayload.data);
    setPairedExceptionCount(workbenchPayload.data.summary.pairedExceptionCount);
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
      forceFresh?: boolean;
      deferForActiveInteraction?: boolean;
    },
  ): Promise<WorkbenchInitialPageResult | null> {
    const requestSeq = loadRequestSeqRef.current + 1;
    loadRequestSeqRef.current = requestSeq;
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
        { forceFresh: options?.forceFresh ?? false },
      );
      if (signal?.aborted || loadRequestSeqRef.current !== requestSeq) {
        return null;
      }
      if (
        options?.deferForActiveInteraction
        && hasOaSyncRefreshBlockingInteractionRef.current
      ) {
        oaSyncRefreshPendingRef.current = true;
        setIsRefreshing(false);
        return null;
      }
      applyWorkbenchPageResult(workbenchPayload, resolvedZoneQueries);
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
      const normalizedError = new Error(workbenchReadErrorMessage(
        error,
        "关联台读取失败，请稍后重试。",
      ));
      if (!background) {
        setWorkbenchData(null);
        setStatistics(null);
        setLoadedZoneServerPageQueryKeys(null);
        setZonePages(createInitialZonePages());
        setExceptionDrawerGroups([]);
        setExceptionDrawerPage(createInitialZonePageInfo(exceptionDrawerBucketRef.current));
        setExceptionDrawerCounts(null);
        setPairedExceptionCount(0);
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

  async function rereadWorkbenchAfterCommit() {
    if (oaSyncRefreshTimeoutRef.current !== null) {
      window.clearTimeout(oaSyncRefreshTimeoutRef.current);
      oaSyncRefreshTimeoutRef.current = null;
    }
    oaSyncRefreshPendingRef.current = false;
    postCommitRereadInFlightRef.current = true;
    try {
      return await loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
        background: true,
        includeAuxiliary: false,
        zoneQueries: latestZoneServerPageQueriesRef.current,
        propagateError: true,
        forceFresh: true,
      });
    } finally {
      postCommitRereadInFlightRef.current = false;
      if (oaSyncRefreshPendingRef.current) {
        oaSyncRefreshPendingRef.current = false;
        scheduleOaSyncWorkbenchRefresh();
      }
    }
  }

  const handleLoadMoreZone = useCallback(async (zone: "paired" | "unpaired") => {
    const pageInfo = zonePages[zone];
    const displayStatePending = zone === "paired"
      ? pairedDisplayState !== deferredPairedDisplayState
      : openDisplayState !== deferredOpenDisplayState;
    if (
      !workbenchData
      || !pageInfo.hasMore
      || !pageInfo.nextCursor
      || displayStatePending
      || loadedZoneServerPageQueryKeys?.[zone] !== zoneServerPageQueryKeys[zone]
      || loadMoreInFlightRef.current[zone]
    ) {
      return;
    }
    const requestSeq = loadMoreRequestSeqRef.current[zone] + 1;
    loadMoreRequestSeqRef.current[zone] = requestSeq;
    loadMoreInFlightRef.current[zone] = true;
    loadMoreAbortControllerRef.current[zone]?.abort();
    const controller = new AbortController();
    loadMoreAbortControllerRef.current[zone] = controller;
    setLoadingMoreByZone((current) => ({ ...current, [zone]: true }));
    setLoadMoreErrorByZone((current) => current[zone] ? { ...current, [zone]: null } : current);
    try {
      const result = await fetchWorkbenchGroupsPage(
        WORKBENCH_VIEW_MONTH,
        zone,
        pageInfo.nextCursor,
        pageInfo.pageSize,
        controller.signal,
        { ...zoneServerPageQueries[zone], detailLevel: "summary" },
        pageInfo.page + 1,
      );
      if (controller.signal.aborted || loadMoreRequestSeqRef.current[zone] !== requestSeq) {
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
    } catch (error) {
      if (controller.signal.aborted || loadMoreRequestSeqRef.current[zone] !== requestSeq) {
        return;
      }
      setLoadMoreErrorByZone((current) => ({
        ...current,
        [zone]: error instanceof Error ? error.message : "自动加载下一页失败，请重试。",
      }));
    } finally {
      if (loadMoreRequestSeqRef.current[zone] === requestSeq) {
        if (loadMoreAbortControllerRef.current[zone] === controller) {
          loadMoreAbortControllerRef.current[zone] = null;
        }
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
    const detailKey = workbenchData?.[zone].groups.find((candidate) => candidate.id === normalizedGroupId)?.detailKey;
    const requestKey = `${zone}\u001f${normalizedGroupId}`;
    const requestCanonicalEpoch = canonicalEpochRef.current;
    const requestGeneration = groupDetailRequestGenerationRef.current;
    const existingRequest = groupDetailRequestsRef.current.get(requestKey);
    if (
      existingRequest
      && existingRequest.canonicalEpoch === requestCanonicalEpoch
      && existingRequest.detailKey === detailKey
      && existingRequest.generation === requestGeneration
    ) {
      return existingRequest.promise;
    }

    existingRequest?.controller.abort();
    const controller = new AbortController();
    const requestPromise = (async () => {
      try {
        const group = await fetchWorkbenchGroupDetail(
          WORKBENCH_VIEW_MONTH,
          zone,
          normalizedGroupId,
          detailKey,
          controller.signal,
        );
        if (
          controller.signal.aborted
          || canonicalEpochRef.current !== requestCanonicalEpoch
          || groupDetailRequestGenerationRef.current !== requestGeneration
        ) {
          throw createWorkbenchAbortError();
        }
        setWorkbenchData((current) => {
          const currentGroup = current?.[zone].groups.find((candidate) => candidate.id === normalizedGroupId);
          if (!current || !currentGroup || currentGroup.detailKey !== detailKey) {
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
      } catch (error) {
        if (
          controller.signal.aborted
          || canonicalEpochRef.current !== requestCanonicalEpoch
          || groupDetailRequestGenerationRef.current !== requestGeneration
          || isWorkbenchAbortError(error)
        ) {
          throw createWorkbenchAbortError();
        }
        setLastActionMessage("加载完整明细失败，请稍后重试。");
        throw new Error("workbench_group_detail_load_failed");
      } finally {
        if (groupDetailRequestsRef.current.get(requestKey)?.controller === controller) {
          groupDetailRequestsRef.current.delete(requestKey);
        }
      }
    })();
    groupDetailRequestsRef.current.set(requestKey, {
      canonicalEpoch: requestCanonicalEpoch,
      controller,
      detailKey,
      generation: requestGeneration,
      promise: requestPromise,
    });
    return requestPromise;
  }, [workbenchData]);

  const loadZoneFirstPage = useCallback(async (
    zone: "paired" | "unpaired",
    query: WorkbenchGroupsPageQuery,
    queryKey: string,
  ) => {
    invalidateGroupDetailRequests();
    zoneQueryAbortControllerRef.current[zone]?.abort();
    const controller = new AbortController();
    zoneQueryAbortControllerRef.current[zone] = controller;
    zoneQueryInFlightKeyRef.current[zone] = queryKey;
    const requestSeq = zoneQueryRequestSeqRef.current[zone] + 1;
    zoneQueryRequestSeqRef.current[zone] = requestSeq;
    loadMoreAbortControllerRef.current[zone]?.abort();
    loadMoreAbortControllerRef.current[zone] = null;
    loadMoreRequestSeqRef.current[zone] += 1;
    loadMoreInFlightRef.current[zone] = false;
    setLoadingMoreByZone((current) => ({ ...current, [zone]: false }));
    setLoadMoreErrorByZone((current) => ({ ...current, [zone]: null }));
    setZoneQueryLoadingByZone((current) => ({ ...current, [zone]: true }));
    setZoneQueryErrorByZone((current) => ({ ...current, [zone]: null }));
    try {
      const result = await fetchWorkbenchGroupsPage(
        WORKBENCH_VIEW_MONTH,
        zone,
        null,
        WORKBENCH_GROUP_PAGE_SIZE,
        controller.signal,
        { ...query, detailLevel: "summary" },
      );
      if (controller.signal.aborted || zoneQueryRequestSeqRef.current[zone] !== requestSeq) {
        return;
      }
      setWorkbenchData((current) => current ? {
        ...current,
        [zone]: { groups: result.groups },
      } : current);
      setZonePages((current) => ({ ...current, [zone]: result.page }));
      setLoadedZoneServerPageQueryKeys((current) => ({
        paired: current?.paired ?? zoneServerPageQueryKeys.paired,
        unpaired: current?.unpaired ?? zoneServerPageQueryKeys.unpaired,
        [zone]: queryKey,
      }));
    } catch (error) {
      if (!controller.signal.aborted && zoneQueryRequestSeqRef.current[zone] === requestSeq) {
        setZoneQueryErrorByZone((current) => ({
          ...current,
          [zone]: error instanceof WorkbenchApiError ? error.message : "筛选结果加载失败，请重试。",
        }));
      }
    } finally {
      const isCurrentRequest = zoneQueryAbortControllerRef.current[zone] === controller
        && zoneQueryRequestSeqRef.current[zone] === requestSeq;
      if (isCurrentRequest) {
        zoneQueryAbortControllerRef.current[zone] = null;
        zoneQueryInFlightKeyRef.current[zone] = null;
        setZoneQueryLoadingByZone((current) => ({ ...current, [zone]: false }));
      }
    }
  }, [invalidateGroupDetailRequests, zoneServerPageQueryKeys.paired, zoneServerPageQueryKeys.unpaired]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    if (!workbenchData || isLoading) {
      return;
    }
    (["paired", "unpaired"] as const).forEach((zone) => {
      const queryKey = zoneServerPageQueryKeys[zone];
      if (
        loadedZoneServerPageQueryKeys?.[zone] !== queryKey
        && zoneQueryInFlightKeyRef.current[zone] !== queryKey
      ) {
        void loadZoneFirstPage(zone, zoneServerPageQueries[zone], queryKey);
      }
    });
  }, [
    active,
    isLoading,
    loadZoneFirstPage,
    loadedZoneServerPageQueryKeys,
    workbenchData,
    zoneServerPageQueries,
    zoneServerPageQueryKeys,
  ]);

  useEffect(() => () => {
    zoneQueryAbortControllerRef.current.paired?.abort();
    zoneQueryAbortControllerRef.current.unpaired?.abort();
    loadMoreAbortControllerRef.current.paired?.abort();
    loadMoreAbortControllerRef.current.unpaired?.abort();
    relationPreviewAbortControllerRef.current?.abort();
    detailRequestAbortControllerRef.current?.abort();
    exceptionDrawerRequestRef.current?.abort();
    oaSyncStatusAbortControllerRef.current?.abort();
    invalidateGroupDetailRequests();
    invalidateExceptionGroupDetailRequests();
  }, [invalidateExceptionGroupDetailRequests, invalidateGroupDetailRequests]);

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
    void pollOaSyncStatus();
    const intervalId = window.setInterval(() => {
      void pollOaSyncStatus();
    }, OA_SYNC_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
      oaSyncStatusRequestSeqRef.current += 1;
      oaSyncStatusAbortControllerRef.current?.abort();
      oaSyncStatusAbortControllerRef.current = null;
      if (oaSyncRefreshTimeoutRef.current !== null) {
        window.clearTimeout(oaSyncRefreshTimeoutRef.current);
        oaSyncRefreshTimeoutRef.current = null;
      }
      oaSyncRefreshPendingRef.current = false;
    };
  }, [active, pollOaSyncStatus]);

  useEffect(() => {
    if (
      !active
      || hasOaSyncRefreshBlockingInteraction
      || postCommitRereadInFlightRef.current
      || !oaSyncRefreshPendingRef.current
    ) {
      return;
    }
    oaSyncRefreshPendingRef.current = false;
    scheduleOaSyncWorkbenchRefresh();
  }, [active, hasOaSyncRefreshBlockingInteraction, scheduleOaSyncWorkbenchRefresh]);

  useEffect(() => {
    document.body.classList.add("workbench-page-mode");
    return () => {
      document.body.classList.remove("workbench-page-mode");
    };
  }, []);

  useEffect(() => {
    if (loadError) {
      setWorkbenchStatus({ level: "error", reason: loadError });
      return;
    }
    if (backgroundLoadError) {
      setWorkbenchStatus({ level: "error", reason: backgroundLoadError });
      return;
    }
    if (oaSyncStatusError) {
      setWorkbenchStatus({ level: "error", reason: oaSyncStatusError });
      return;
    }
    if (lastActionMessage) {
      setWorkbenchStatus({ level: "pending", reason: lastActionMessage });
      return;
    }
    if (oaSyncShellStatus) {
      setWorkbenchStatus(oaSyncShellStatus);
      return;
    }
    const zoneQueryError = zoneQueryErrorByZone.paired ?? zoneQueryErrorByZone.unpaired;
    if (zoneQueryError) {
      setWorkbenchStatus({ level: "error", reason: zoneQueryError });
      return;
    }
    if (isLoading || isRefreshing || zoneQueryLoadingByZone.paired || zoneQueryLoadingByZone.unpaired) {
      const reason = loadProgress.percent === null
        ? `${loadProgress.label}...`
        : `${loadProgress.label} ${loadProgress.percent}%`;
      setWorkbenchStatus({ level: "pending", reason });
      return;
    }
    setWorkbenchStatus(null);
  }, [
    isLoading,
    isRefreshing,
    backgroundLoadError,
    lastActionMessage,
    loadError,
    loadProgress.label,
    loadProgress.percent,
    oaSyncShellStatus,
    oaSyncStatusError,
    setWorkbenchStatus,
    zoneQueryErrorByZone,
    zoneQueryLoadingByZone,
  ]);

  useEffect(() => () => setWorkbenchStatus(null), [setWorkbenchStatus]);

  const visibleOpenGroups = useMemo(
    () => workbenchData?.unpaired.groups ?? [],
    [workbenchData?.unpaired.groups],
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
  const selectedOpenActionableRows = selectedOpenRows.filter((row) => !row.displayOnly);
  const openSelectionSummary = openSelectionContext.summary;
  const pairedSelectionSummary = pairedSelectionContext.summary;
  const contextualOpenRowIdentityKeys = openSelectionContext.relatedRowIdentityKeySet;
  const contextualPairedRowIdentityKeys = pairedSelectionContext.relatedRowIdentityKeySet;
  relationPreviewContextKeyRef.current = [
    WORKBENCH_VIEW_MONTH,
    canonicalEpoch,
    openSelectionContext.includedRowIdentityKeys.join(","),
    pairedSelectionContext.includedRowIdentityKeys.join(","),
  ].join("|");
  const getWorkbenchRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "unpaired") => {
    const explicitState = getRowState(row, zoneId);
    if (explicitState !== "idle") {
      return explicitState;
    }
    const identityKey = workbenchRowIdentityKey(row);
    return (
      zoneId === "unpaired" ? contextualOpenRowIdentityKeys : contextualPairedRowIdentityKeys
    ).has(identityKey) ? "related" : "idle";
  }, [contextualOpenRowIdentityKeys, contextualPairedRowIdentityKeys, getRowState]);

  const selectedOpenRelationGroupIdSet = new Set(openSelectionContext.selectedRelationGroupIds);
  const selectedOpenWithdrawableRelationGroups = openSelectionSourceGroups.filter((group) => (
    selectedOpenRelationGroupIdSet.has(group.id)
    && group.rawGroupType === "relation"
    && group.canWithdraw
  ));
  const selectedOpenFormalIdentities = selectedOpenWithdrawableRelationGroups[0]?.formalMemberIdentities ?? [];
  const selectedOpenFormalIdentityKeySet = new Set(
    selectedOpenFormalIdentities.map(workbenchRowIdentityKey),
  );
  const isExactOpenRelationSelection = selectedOpenWithdrawableRelationGroups.length === 1
    && selectedOpenRelationGroupIdSet.size === 1
    && selectedOpenFormalIdentities.length >= 2
    && openSelectionContext.includedRowIdentityKeys.length === selectedOpenFormalIdentityKeySet.size
    && openSelectionContext.includedRowIdentityKeys.every((identityKey) => (
      selectedOpenFormalIdentityKeySet.has(identityKey)
    ));
  const canConfirmOpenSelection = selectedOpenActionableRows.length >= 2 && !isExactOpenRelationSelection;
  const canWithdrawOpenSelection = isExactOpenRelationSelection;
  const selectedPairedGroupsForUnifiedAction = useMemo(() => {
    const selectedGroupIdSet = new Set(pairedSelectionContext.selectedRelationGroupIds);
    return pairedSelectionSourceGroups.filter((group) => selectedGroupIdSet.has(group.id));
  }, [pairedSelectionContext.selectedRelationGroupIds, pairedSelectionSourceGroups]);
  const isOpenConfirmSelectionDisabled = !canConfirmOpenSelection;
  const isOpenWithdrawSelectionDisabled = !canWithdrawOpenSelection;
  const isPairedCancelSelectionDisabled = pairedSelectionSummary.total < 1;
  const pairedSelectionActionNotice = pairedSelectionSummary.total > 0 && !workbenchWriteGate.allowed
    ? workbenchWriteGate.message
    : null;
  const openSelectionActionNotice = openSelectionSummary.total < 1
    ? null
    : !workbenchWriteGate.allowed
      ? workbenchWriteGate.message
      : !canConfirmOpenSelection
        && !canWithdrawOpenSelection
        ? "确认关联至少需要选择 2 个不同记录。"
        : null;

  const collectCaseRows = useCallback((row: WorkbenchRecord) => {
    const rowIdentityKey = workbenchRowIdentityKey(row);
    const containingGroup = sourceAllGroups.find((group) =>
      flattenGroups([group]).some((candidate) => workbenchRowIdentityKey(candidate) === rowIdentityKey),
    );
    if (containingGroup) {
      return flattenGroups([containingGroup]);
    }
    if (!row.caseId) {
      return [row];
    }
    const relatedRows = sourceAllRows.filter((candidate) => candidate.caseId === row.caseId);
    return relatedRows.length > 0 ? relatedRows : [row];
  }, [sourceAllGroups, sourceAllRows]);

  const handleOpenDetail = useCallback((row: WorkbenchRecord) => {
    detailRequestAbortControllerRef.current?.abort();
    const requestSeq = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestSeq;
    setDetailError(null);
    setIsDetailLoading(true);
    openDetail(row);
    const controller = new AbortController();
    detailRequestAbortControllerRef.current = controller;
    void fetchWorkbenchRowDetail(row.id, {
      month: WORKBENCH_VIEW_MONTH,
      rowType: row.recordType,
      signal: controller.signal,
    })
      .then((detailedRow) => {
        if (detailRequestSeqRef.current === requestSeq) {
          replaceDetailRow(detailedRow);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && detailRequestSeqRef.current === requestSeq) {
          setDetailError(error instanceof WorkbenchApiError ? error.message : "详情加载失败，请稍后重试。");
        }
      })
      .finally(() => {
        if (detailRequestAbortControllerRef.current === controller) {
          detailRequestAbortControllerRef.current = null;
        }
        if (detailRequestSeqRef.current === requestSeq) {
          setIsDetailLoading(false);
        }
      });
  }, [openDetail, replaceDetailRow]);

  const handleCloseDetail = useCallback(() => {
    detailRequestAbortControllerRef.current?.abort();
    detailRequestAbortControllerRef.current = null;
    detailRequestSeqRef.current += 1;
    setDetailError(null);
    setIsDetailLoading(false);
    closeDetail();
  }, [closeDetail]);

  const handleCloseActionDialog = () => {
    setActionDialog((current) => (current?.phase === "result" ? null : current));
  };

  const loadExceptionDrawer = useCallback(async (
    bucket: "unpaired" | "paired",
    view: WorkbenchExceptionView,
    exceptionCode: WorkbenchAmountAnomalyCode | null,
  ) => {
    invalidateExceptionGroupDetailRequests();
    exceptionDrawerRequestRef.current?.abort();
    const controller = new AbortController();
    const requestGeneration = exceptionDrawerRequestGenerationRef.current + 1;
    exceptionDrawerRequestGenerationRef.current = requestGeneration;
    exceptionDrawerRequestRef.current = controller;
    setExceptionDrawerLoading(true);
    setExceptionDrawerLoadingMore(false);
    setExceptionDrawerError(null);
    try {
      const result = await fetchWorkbenchExceptionGroups(
        WORKBENCH_VIEW_MONTH,
        bucket,
        view,
        view === "amount" ? exceptionCode ?? undefined : undefined,
        controller.signal,
      );
      if (controller.signal.aborted || exceptionDrawerRequestGenerationRef.current !== requestGeneration) {
        return false;
      }
      setExceptionDrawerGroups(result.groups);
      setExceptionDrawerPage(result.page);
      setExceptionDrawerCounts(result.exceptionCounts ?? null);
      setExceptionDrawerSelectedCode(view === "amount"
        ? result.selectedExceptionCode ?? exceptionCode
        : null);
      setExceptionDrawerContentGeneration((current) => current + 1);
      if (result.exceptionCounts) {
        const bucketTotal = result.exceptionCounts.total;
        if (bucket === "paired") {
          setPairedExceptionCount(bucketTotal);
        } else {
          setWorkbenchData((current) => current ? {
            ...current,
            summary: { ...current.summary, unpairedExceptionCount: bucketTotal },
          } : current);
        }
      }
      return true;
    } catch (error) {
      if (!controller.signal.aborted && exceptionDrawerRequestGenerationRef.current === requestGeneration) {
        setExceptionDrawerError(error instanceof Error ? error.message : "异常数据加载失败，请稍后重试。");
      }
      return false;
    } finally {
      if (
        exceptionDrawerRequestRef.current === controller
        && exceptionDrawerRequestGenerationRef.current === requestGeneration
      ) {
        exceptionDrawerRequestRef.current = null;
        setExceptionDrawerLoading(false);
        setExceptionDrawerLoadingMore(false);
      }
    }
  }, [invalidateExceptionGroupDetailRequests]);

  const loadMoreExceptionDrawer = useCallback(async () => {
    if (!exceptionDrawerPage.hasMore || !exceptionDrawerPage.nextCursor || exceptionDrawerLoadingMore) {
      return;
    }
    const requestBucket = exceptionDrawerBucket;
    const requestView = exceptionDrawerView;
    const requestCode = requestView === "amount" ? exceptionDrawerRequestedCode : null;
    exceptionDrawerRequestRef.current?.abort();
    const controller = new AbortController();
    const requestGeneration = exceptionDrawerRequestGenerationRef.current + 1;
    exceptionDrawerRequestGenerationRef.current = requestGeneration;
    exceptionDrawerRequestRef.current = controller;
    setExceptionDrawerLoadingMore(true);
    setExceptionDrawerError(null);
    try {
      const result = await fetchWorkbenchGroupsPage(
        WORKBENCH_VIEW_MONTH,
        requestBucket,
        exceptionDrawerPage.nextCursor,
        WORKBENCH_GROUP_PAGE_SIZE,
        controller.signal,
        {
          detailLevel: "summary",
          exceptionBucket: requestBucket,
          exceptionView: requestView,
          ...(requestCode ? { exceptionCode: requestCode } : {}),
        },
        exceptionDrawerPage.page + 1,
        { forceFresh: true },
      );
      if (controller.signal.aborted || exceptionDrawerRequestGenerationRef.current !== requestGeneration) {
        return;
      }
      setExceptionDrawerGroups((current) => mergeWorkbenchGroupsById(current, result.groups));
      setExceptionDrawerPage(result.page);
      if (result.exceptionCounts) {
        setExceptionDrawerCounts(result.exceptionCounts);
      }
    } catch (error) {
      if (!controller.signal.aborted && exceptionDrawerRequestGenerationRef.current === requestGeneration) {
        setExceptionDrawerError(error instanceof WorkbenchApiError ? error.message : "更多异常加载失败，请重试。");
      }
    } finally {
      if (
        exceptionDrawerRequestRef.current === controller
        && exceptionDrawerRequestGenerationRef.current === requestGeneration
      ) {
        exceptionDrawerRequestRef.current = null;
        setExceptionDrawerLoadingMore(false);
      }
    }
  }, [
    exceptionDrawerBucket,
    exceptionDrawerLoadingMore,
    exceptionDrawerPage,
    exceptionDrawerRequestedCode,
    exceptionDrawerView,
  ]);

  const ensureExceptionGroupDetail = useCallback(async (group: WorkbenchRelationGroup) => {
    const requestBucket = exceptionDrawerBucketRef.current;
    const requestCanonicalEpoch = canonicalEpochRef.current;
    const requestGeneration = exceptionGroupDetailRequestGenerationRef.current;
    const requestKey = `${requestBucket}\u001f${group.groupType}\u001f${group.id}`;
    const existingRequest = exceptionGroupDetailRequestsRef.current.get(requestKey);
    if (
      existingRequest
      && existingRequest.bucket === requestBucket
      && existingRequest.canonicalEpoch === requestCanonicalEpoch
      && existingRequest.detailKey === group.detailKey
      && existingRequest.generation === requestGeneration
    ) {
      return existingRequest.promise;
    }

    existingRequest?.controller.abort();
    const controller = new AbortController();
    const requestPromise = (async () => {
      try {
        const detailGroup = await fetchWorkbenchGroupDetail(
          WORKBENCH_VIEW_MONTH,
          group.groupType,
          group.id,
          group.detailKey,
          controller.signal,
        );
        if (
          controller.signal.aborted
          || canonicalEpochRef.current !== requestCanonicalEpoch
          || exceptionGroupDetailRequestGenerationRef.current !== requestGeneration
          || !exceptionDrawerOpenRef.current
          || exceptionDrawerBucketRef.current !== requestBucket
        ) {
          throw createWorkbenchAbortError();
        }
        setExceptionDrawerGroups((current) => current.map((candidate) => (
          candidate.id === detailGroup.id && candidate.detailKey === group.detailKey
            ? detailGroup
            : candidate
        )));
        return detailGroup;
      } catch (error) {
        if (
          controller.signal.aborted
          || canonicalEpochRef.current !== requestCanonicalEpoch
          || exceptionGroupDetailRequestGenerationRef.current !== requestGeneration
          || isWorkbenchAbortError(error)
        ) {
          throw createWorkbenchAbortError();
        }
        throw error;
      } finally {
        if (exceptionGroupDetailRequestsRef.current.get(requestKey)?.controller === controller) {
          exceptionGroupDetailRequestsRef.current.delete(requestKey);
        }
      }
    })();
    exceptionGroupDetailRequestsRef.current.set(requestKey, {
      bucket: requestBucket,
      canonicalEpoch: requestCanonicalEpoch,
      controller,
      detailKey: group.detailKey,
      generation: requestGeneration,
      promise: requestPromise,
    });
    return requestPromise;
  }, []);

  const resetExceptionDrawerListState = useCallback((
    bucket: "unpaired" | "paired",
    clearCounts: boolean,
  ) => {
    exceptionDrawerRequestRef.current?.abort();
    exceptionDrawerRequestRef.current = null;
    exceptionDrawerRequestGenerationRef.current += 1;
    invalidateExceptionGroupDetailRequests();
    setExceptionDrawerGroups([]);
    setExceptionDrawerPage(createInitialZonePageInfo(bucket));
    if (clearCounts) {
      setExceptionDrawerCounts(null);
    }
    setExceptionDrawerLoading(true);
    setExceptionDrawerLoadingMore(false);
    setExceptionDrawerError(null);
    setExceptionDrawerContentGeneration((current) => current + 1);
  }, [invalidateExceptionGroupDetailRequests]);

  const handleOpenExceptionDrawer = useCallback(() => {
    setExceptionDrawerOpen(true);
    setExceptionDrawerBucket("unpaired");
    setExceptionDrawerView("amount");
    setExceptionDrawerRequestedCode(null);
    setExceptionDrawerSelectedCode(null);
    setExceptionDrawerCounts(null);
  }, []);

  const handleExceptionDrawerBucketChange = useCallback((bucket: "unpaired" | "paired") => {
    if (bucket === exceptionDrawerBucket) {
      return;
    }
    resetExceptionDrawerListState(bucket, true);
    setExceptionDrawerRequestedCode(null);
    setExceptionDrawerSelectedCode(null);
    setExceptionDrawerBucket(bucket);
  }, [exceptionDrawerBucket, resetExceptionDrawerListState]);

  const handleExceptionDrawerViewChange = useCallback((view: WorkbenchExceptionView) => {
    if (view === exceptionDrawerView) {
      return;
    }
    resetExceptionDrawerListState(exceptionDrawerBucket, false);
    setExceptionDrawerRequestedCode(null);
    setExceptionDrawerSelectedCode(null);
    setExceptionDrawerView(view);
  }, [exceptionDrawerBucket, exceptionDrawerView, resetExceptionDrawerListState]);

  const handleExceptionDrawerCodeChange = useCallback((code: WorkbenchAmountAnomalyCode) => {
    if (code === exceptionDrawerSelectedCode) {
      return;
    }
    resetExceptionDrawerListState(exceptionDrawerBucket, false);
    setExceptionDrawerRequestedCode(code);
    setExceptionDrawerSelectedCode(code);
  }, [exceptionDrawerBucket, exceptionDrawerSelectedCode, resetExceptionDrawerListState]);

  const handleCloseExceptionDrawer = useCallback(() => {
    exceptionDrawerRequestRef.current?.abort();
    exceptionDrawerRequestRef.current = null;
    exceptionDrawerRequestGenerationRef.current += 1;
    invalidateExceptionGroupDetailRequests();
    setExceptionDrawerLoading(false);
    setExceptionDrawerLoadingMore(false);
    setExceptionDrawerOpen(false);
  }, [invalidateExceptionGroupDetailRequests]);

  useEffect(() => {
    if (!exceptionDrawerOpen) {
      return;
    }
    void loadExceptionDrawer(
      exceptionDrawerBucket,
      exceptionDrawerView,
      exceptionDrawerRequestedCode,
    );
    return () => exceptionDrawerRequestRef.current?.abort();
  }, [
    exceptionDrawerBucket,
    exceptionDrawerOpen,
    exceptionDrawerRequestedCode,
    exceptionDrawerReloadGeneration,
    exceptionDrawerView,
    loadExceptionDrawer,
  ]);

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

  const handleEditReceipt = useCallback((group: WorkbenchRelationGroup) => {
    const receiptAction = group.receiptAction;
    if (!receiptAction?.eligible) {
      return;
    }
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    setReceiptEditorCaseId(receiptAction.caseId);
  }, [ensureCanWriteWorkbench]);

  const executeWorkbenchActionAndReread = useCallback(async ({
    loadingMessage,
    action,
    onProgress,
  }: {
    loadingMessage: string;
    action: () => Promise<string | WorkbenchActionResult>;
    onProgress?: WorkbenchActionProgressHandler;
  }) => {
    onProgress?.({ phase: "submitting", message: loadingMessage, committed: false });
    const result = await action();
    onProgress?.({ phase: "rereading", message: "关系已写入，正在重新读取关联台...", committed: true });
    clearSelection();
    setSelectionSourceGroups({ paired: [], unpaired: [] });
    loadMoreAbortControllerRef.current.paired?.abort();
    loadMoreAbortControllerRef.current.unpaired?.abort();
    zoneQueryAbortControllerRef.current.paired?.abort();
    zoneQueryAbortControllerRef.current.unpaired?.abort();
    setZonePages(createInitialZonePages());
    const reread = await rereadWorkbenchAfterCommit();
    if (!reread) {
      throw new Error("关系已写入，但页面重新读取失败；请勿重复提交，稍后刷新页面确认。");
    }
    return actionResultMessage(result);
  }, [clearSelection]);

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
        return executeWorkbenchActionAndReread({
          loadingMessage,
          action,
          onProgress: (progress) => setMessage(progress.message),
        });
      },
      errorMessage: actionErrorMessage,
    });
    if (outcome.status === "success") {
      setLastActionMessage(outcome.value);
      return true;
    }
    return false;
  }, [executeWorkbenchActionAndReread, handleCloseDetail, runOperation]);

  const openRelationPreviewErrorDialog = useCallback((error: unknown) => {
    openActionResultDialog(actionErrorMessage(error), "操作失败");
  }, [openActionResultDialog]);

  const handleRowAction = useCallback(async (
    row: WorkbenchRecord,
    action: WorkbenchInlineAction,
    group: WorkbenchRelationGroup,
  ) => {
    if (action === "relation-status") {
      openActionResultDialog(`当前关联情况：${row.status}`, "关联情况");
      return;
    }

    if (!ensureCanWriteWorkbench()) {
      return;
    }

    if (action === "enter-invoice") {
      const expenseItemId = row.sourceExpenseItemIds?.[0] ?? "";
      if (!row.sourceOaId || !expenseItemId) {
        openActionResultDialog("无法确定需要补录发票的 OA 子付款项，请刷新页面后重试。", "无法录入发票");
        return;
      }
      if (exceptionDrawerOpenRef.current) {
        handleCloseExceptionDrawer();
      }
      setInvoiceEntryTarget({
        caseId: row.caseId ?? "",
        oaRowId: row.sourceOaId,
        expenseItemId,
      });
      return;
    }

    if (action === "assign-invoice-expense-items") {
      const anomaly = row.workbenchAnomalies?.find(
        (candidate) => candidate.code === "oa_invoice_attachment_unassigned",
      );
      const candidates = buildWorkbenchInvoiceExpenseItemCandidates(group);
      const caseId = row.caseId
        ?? group.rows.oa.find((candidate) => candidate.caseId)?.caseId
        ?? group.rows.bank.find((candidate) => candidate.caseId)?.caseId
        ?? "";
      if (row.recordType !== "invoice" || !anomaly || !caseId || candidates.length === 0) {
        openActionResultDialog(
          "无法确定这张发票可归属的 OA 付款明细，请刷新页面后重试。",
          "无法选择 OA 明细",
        );
        return;
      }
      if (exceptionDrawerOpenRef.current) {
        handleCloseExceptionDrawer();
      }
      setInvoiceAssignmentTarget({
        caseId,
        invoiceRowId: row.id,
        invoiceNo: row.tableValues.invoiceNo ?? row.label,
        sellerName: row.tableValues.sellerName ?? row.counterparty,
        amount: row.tableValues.grossAmount ?? row.amount,
        anomalyFingerprint: anomaly.fingerprint,
        idempotencyKey: crypto.randomUUID(),
        candidates,
      });
      return;
    }

    if (action === "confirm-cash-pass-through") {
      const rows = collectCaseRows(row);
      await runBlockingAction({
        loadingMessage: "正在确认过账...",
        action: async () => {
          const result = await confirmWorkbenchCashPassThrough({
            month: WORKBENCH_VIEW_MONTH,
            rowIds: rows.map((candidate) => candidate.id),
            rowTypes: rows.map((candidate) => candidate.recordType),
            note: "由关联台确认现金往来过账",
          });
          return result;
        },
      });
      return;
    }

    if (action === "confirm-cash-ticket-purchase") {
      setCashTicketPurchaseDialog({
        rows: collectCaseRows(row).map(({ id, recordType }) => ({ id, recordType })),
        cashAmount: normalizedAmountForInput(row.amount),
      });
      return;
    }

    if (action === "cancel-cash-special") {
      const rows = collectCaseRows(row);
      await runBlockingAction({
        loadingMessage: "正在取消现金处理...",
        action: async () => {
          const result = await cancelWorkbenchCashSpecial({
            month: WORKBENCH_VIEW_MONTH,
            rowIds: rows.map((candidate) => candidate.id),
            rowTypes: rows.map((candidate) => candidate.recordType),
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
      try {
        const relationSelection = buildWorkbenchSelectionContext({
          explicitRows: [row],
          sourceGroups: sourceAllGroups,
          zoneId: "paired",
        });
        if (relationSelection.includedRowIdentities.length === 0) {
          openActionResultDialog("当前关联组的正式成员合同无效，请刷新后重试。");
          return;
        }
        await openWithdrawPreviewIdentities(relationSelection.includedRowIdentities);
      } catch (error) {
        openRelationPreviewErrorDialog(error);
      }
      return;
    }

  }, [
    collectCaseRows,
    ensureCanWriteWorkbench,
    handleCloseExceptionDrawer,
    openActionResultDialog,
    runBlockingAction,
    sourceAllGroups,
    withdrawBankFlowRuleBatchSummaryRow,
    openRelationPreviewErrorDialog,
  ]);

  const handleSupportingDocumentsChanged = useCallback((
    target: WorkbenchOaInvoiceSupplementTarget,
    documents: WorkbenchOaSupportingDocument[],
  ) => {
    setWorkbenchData((current) => current ? {
      ...current,
      paired: {
        groups: replaceWorkbenchSupportingDocuments(current.paired.groups, target, documents),
      },
      unpaired: {
        groups: replaceWorkbenchSupportingDocuments(current.unpaired.groups, target, documents),
      },
    } : current);
    setSelectionSourceGroups((current) => ({
      paired: replaceWorkbenchSupportingDocuments(current.paired, target, documents),
      unpaired: replaceWorkbenchSupportingDocuments(current.unpaired, target, documents),
    }));
    setExceptionDrawerGroups((current) => replaceWorkbenchSupportingDocuments(current, target, documents));
  }, []);

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
    const { rows } = cashTicketPurchaseDialog;
    setCashTicketPurchaseDialog(null);
    await runBlockingAction({
      loadingMessage: "正在确认买票成本...",
      action: async () => {
        const result = await confirmWorkbenchCashTicketPurchase({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: rows.map((row) => row.id),
          rowTypes: rows.map((row) => row.recordType),
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

  const openRelationPreview = async (
    kind: RelationPreviewRequestKind,
    identities: WorkbenchRecordIdentity[],
  ) => {
    if (relationPreviewRequestKindRef.current) {
      return;
    }
    const rowIds = identities.map((identity) => identity.id);
    const rowTypes = identities.map((identity) => identity.recordType);
    const requestContextKey = relationPreviewContextKeyRef.current;
    relationPreviewAbortControllerRef.current?.abort();
    const controller = new AbortController();
    relationPreviewAbortControllerRef.current = controller;
    relationPreviewRequestKindRef.current = kind;
    setRelationPreviewRequestKind(kind);
    try {
      const preview = kind === "confirm"
        ? await previewWorkbenchConfirmLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            rowTypes,
          }, controller.signal)
        : await previewWorkbenchWithdrawLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            rowTypes,
          }, controller.signal);
      if (controller.signal.aborted || relationPreviewContextKeyRef.current !== requestContextKey) {
        return;
      }
      setRelationPreviewDialog({
        preview,
        rowIds,
        rowTypes,
        canonicalEpoch: canonicalEpochRef.current,
        caseId: undefined,
        idempotencyKey: crypto.randomUUID(),
      });
    } catch (error) {
      if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
        return;
      }
      throw error;
    } finally {
      const isCurrentRequest = relationPreviewAbortControllerRef.current === controller;
      if (isCurrentRequest) {
        relationPreviewAbortControllerRef.current = null;
      }
      if (isCurrentRequest && relationPreviewRequestKindRef.current === kind) {
        relationPreviewRequestKindRef.current = null;
        setRelationPreviewRequestKind(null);
      }
    }
  };

  const openConfirmPreview = async (rows: WorkbenchRecord[]) => {
    await openRelationPreview(
      "confirm",
      rows.map((row) => ({ id: row.id, recordType: row.recordType })),
    );
  };

  const openWithdrawPreview = async (rows: WorkbenchRecord[]) => {
    await openRelationPreview(
      "withdraw",
      rows.map((row) => ({ id: row.id, recordType: row.recordType })),
    );
  };

  const openWithdrawPreviewIdentities = async (identities: WorkbenchRecordIdentity[]) => {
    await openRelationPreview("withdraw", identities);
  };

  const handleSubmitRelationPreview = async (note: string, onProgress: WorkbenchActionProgressHandler) => {
    if (!relationPreviewDialog) {
      return;
    }
    if (!ensureCanWriteWorkbench()) {
      throw new Error("当前状态不允许执行写操作。");
    }
    const {
      preview,
      rowIds,
      rowTypes,
      canonicalEpoch: previewCanonicalEpoch,
      caseId,
      idempotencyKey,
    } = relationPreviewDialog;
    if (previewCanonicalEpoch !== canonicalEpochRef.current) {
      throw new Error("关联台数据已更新，请关闭后重新选择记录并重新预览。");
    }
    if (preview.operation === "confirm_link") {
      const message = await executeWorkbenchActionAndReread({
        loadingMessage: "正在确认关联...",
        onProgress,
        action: async () => {
          const result = await confirmWorkbenchLink({
            month: WORKBENCH_VIEW_MONTH,
            rowIds,
            rowTypes,
            caseId,
            note,
            idempotencyKey,
          });
          return result;
        },
      });
      setLastActionMessage(message);
      setRelationPreviewDialog(null);
      return;
    }

    const operationCopy = relationPreviewOperationCopy(preview);
    const message = await executeWorkbenchActionAndReread({
      loadingMessage: operationCopy.submittingMessage,
      onProgress,
      action: async () => {
        const result = await withdrawWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds,
          rowTypes,
          note,
          operationType: "withdraw_relation",
          previewId: preview.previewId,
          expectedVersions: preview.submitExpectedVersions,
          idempotencyKey,
        });
        return result;
      },
    });
    setLastActionMessage(message);
    setRelationPreviewDialog(null);
  };

  const handleConfirmOpenSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (selectedOpenActionableRows.length === 0) {
      openActionResultDialog("请先选择待处理记录。");
      return;
    }
    if (!canConfirmOpenSelection) {
      openActionResultDialog("确认关联至少需要选择 2 个不同记录。");
      return;
    }
    try {
      await openConfirmPreview(selectedOpenActionableRows);
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

  const handleWithdrawOpenSelection = async () => {
    if (!ensureCanWriteWorkbench()) {
      return;
    }
    if (!canWithdrawOpenSelection) {
      openActionResultDialog("请精确选择一个现有正式关系。");
      return;
    }
    try {
      await openWithdrawPreviewIdentities(openSelectionContext.includedRowIdentities);
    } catch (error) {
      openRelationPreviewErrorDialog(error);
    }
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

    if (selectedPairedGroupsForUnifiedAction.length > 1) {
      openActionResultDialog("一次只能处理一个关联组。");
      return;
    }
    const selectedBankFlowRuleBatchRows = uniqueBankFlowRuleBatchRows(
      pairedSelectionContext.explicitRows.filter(isBankFlowRuleBatchSummaryRow),
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
    if (pairedSelectionContext.includedRowIdentities.length === 0) {
      openActionResultDialog("当前关联组的正式成员合同无效，请刷新后重试。");
      return;
    }
    try {
      await openWithdrawPreviewIdentities(pairedSelectionContext.includedRowIdentities);
    } catch (error) {
      openRelationPreviewErrorDialog(error);
    }
  };

  const handleAnomalyReview = useCallback(async (
    group: WorkbenchRelationGroup,
    decision: "accept_paired" | "keep_unpaired",
  ) => {
    if (!ensureCanWriteWorkbench() || !group.workbenchAnomaly) {
      return;
    }
    handleCloseDetail();
    const outcome = await runOperation({
      loadingMessage: decision === "accept_paired" ? "正在确认进入已配对..." : "正在确认留在未配对...",
      action: async ({ setMessage }) => {
        const result = await reviewWorkbenchAnomaly({
          month: WORKBENCH_VIEW_MONTH,
          zone: group.groupType,
          groupId: group.id,
          detailKey: group.detailKey,
          fingerprint: group.workbenchAnomaly!.fingerprint,
          decision,
        });
        setMessage("异常处理已写入，正在重新读取关联台...");
        try {
          await rereadWorkbenchAfterCommit();
        } catch {
          throw new Error("异常处理已写入，但关联台重新读取失败；请勿重复提交，稍后刷新确认。");
        }
        const currentView = exceptionDrawerViewRef.current;
        const currentExceptionCode = exceptionDrawerSelectedCodeRef.current;
        setExceptionDrawerRequestedCode(
          currentView === "amount"
            ? currentExceptionCode
            : null,
        );
        setExceptionDrawerReloadGeneration((current) => current + 1);
        return actionResultMessage(result);
      },
    });
    if (outcome.status === "success") {
      setLastActionMessage(outcome.value);
    }
  }, [
    ensureCanWriteWorkbench,
    handleCloseDetail,
    rereadWorkbenchAfterCommit,
    runOperation,
  ]);

  const pairedPanes = useMemo<WorkbenchPane[]>(
    () => {
      const paneRows = buildWorkbenchPaneRows(displayPairedGroups);
      const totals = zonePages.paired.rowCounts.rows > 0
        ? zonePages.paired.rowCounts
        : workbenchData?.summary.zoneCounts.paired;
      return [
        { id: "oa", title: "OA", rows: paneRows.oa, totalRows: totals?.oa },
        { id: "bank", title: "银行流水", rows: paneRows.bank, totalRows: totals?.bank },
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice, totalRows: totals?.canonicalInvoice },
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
        { id: "invoice", title: "进销项发票", rows: paneRows.invoice, totalRows: totals?.canonicalInvoice },
      ];
    },
    [displayOpenGroups, workbenchData?.summary.zoneCounts.unpaired, zonePages.unpaired.rowCounts],
  );

  const openAuxiliaryHeaderActions = useMemo(
    () => [
      {
        label: `未配对异常 ${workbenchData?.summary.unpairedExceptionCount ?? 0} | 已配对异常 ${pairedExceptionCount}`,
        onClick: handleOpenExceptionDrawer,
        tone: "danger" as const,
      },
    ],
    [handleOpenExceptionDrawer, pairedExceptionCount, workbenchData?.summary.unpairedExceptionCount],
  );

  const isEmpty = (workbenchData?.summary.totalCount ?? 0) === 0;
  const isOaReady = oaSyncStatus?.status === "synced" && oaSyncStatus.dirtyScopes.length === 0;
  const oaStatusPanelMessage = oaSyncStatus && !isOaReady
    ? `${oaSyncStatus.message || "OA 同步状态异常"}，本次结果未包含完整 OA 数据。`
    : null;
  const pairedZoneItemCount = resolveZoneItemCount(zonePages.paired, workbenchData?.summary.zoneCounts.paired);
  const unpairedZoneItemCount = resolveZoneItemCount(zonePages.unpaired, workbenchData?.summary.zoneCounts.unpaired);
  const pairedSearchPending = pairedDisplayState !== deferredPairedDisplayState
    || zoneQueryLoadingByZone.paired;
  const unpairedSearchPending = openDisplayState !== deferredOpenDisplayState
    || zoneQueryLoadingByZone.unpaired;
  const retryZoneSearch = (zone: "paired" | "unpaired") => {
    void loadZoneFirstPage(zone, zoneServerPageQueries[zone], zoneServerPageQueryKeys[zone]);
  };
  const retryWorkbenchDirectRead = () => {
    void loadWorkbenchData(WORKBENCH_VIEW_MONTH, undefined, {
      background: workbenchData !== null,
      includeAuxiliary: workbenchData === null,
      zoneQueries: latestZoneServerPageQueriesRef.current,
      forceFresh: true,
    });
  };
  const pairedZoneElement = (
    <WorkbenchZone
      canMutateData={canWriteWorkbench}
      getRowState={getWorkbenchRowState}
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
      onEditReceipt={handleEditReceipt}
      onSelectRow={handleSelectRow}
      displayState={pairedDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onSearchQueryChange={(query) => handleSearchQueryChange("paired", query)}
      onRetrySearch={() => retryZoneSearch("paired")}
      searchError={zoneQueryErrorByZone.paired}
      searchPending={pairedSearchPending}
      searchQuery={pairedDisplayState.searchQuery}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayPairedGroups}
      sourceGroups={workbenchData?.paired.groups ?? []}
      loadFilterOptions={loadFilterOptions}
      invoiceStatistics={statistics ?? undefined}
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
      onEditReceipt={handleEditReceipt}
      onSelectRow={handleSelectRow}
      onSecondarySelectionAction={handleWithdrawOpenSelection}
      secondarySelectionActionDisabled={
        isOpenWithdrawSelectionDisabled || !canWriteWorkbench || relationPreviewRequestKind !== null
      }
      secondarySelectionActionPending={relationPreviewRequestKind === "withdraw"}
      secondarySelectionActionPendingLabel="正在准备撤回预览"
      selectionActionNotice={openSelectionActionNotice}
      displayState={openDisplayState}
      onColumnFilterChange={handleColumnFilterChange}
      onSearchQueryChange={(query) => handleSearchQueryChange("unpaired", query)}
      onRetrySearch={() => retryZoneSearch("unpaired")}
      searchError={zoneQueryErrorByZone.unpaired}
      searchPending={unpairedSearchPending}
      searchQuery={openDisplayState.searchQuery}
      onTogglePaneSort={handleTogglePaneSort}
      onPaneTimeFilterChange={handlePaneTimeFilterChange}
      onReorderPaneColumns={handleReorderPaneColumns}
      columnLayouts={workbenchSettings?.workbenchColumnLayouts}
      groups={displayOpenGroups}
      sourceGroups={visibleOpenGroups}
      loadFilterOptions={loadFilterOptions}
      invoiceStatistics={statistics ?? undefined}
      loadingMore={loadingMoreByZone.unpaired}
      loadMoreError={loadMoreErrorByZone.unpaired}
      pageInfo={zonePages.unpaired}
      highlightedRowId={null}
      panes={openPanes}
      primarySelectionActionLabel="确认关联"
      secondarySelectionActionLabel="撤回关联"
      selectionSummary={openSelectionSummary}
      title={`未配对 ${unpairedZoneItemCount} 项`}
      tone="warning"
      zoneId="unpaired"
    />
  );

  return (
    <div className="workbench-shell">
      <div className="page-stack">
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
                    { label: "已完成 OA", value: statistics?.completedOaCount, unit: "条", tone: "success" },
                    { label: "进行中 OA", value: statistics?.inProgressOaCount, unit: "条" },
                    { label: "支出流水", value: statistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
                    { label: "收入流水", value: statistics?.incomeTransactionCount, unit: "笔", tone: "income" },
                    { label: "手工导入发票", value: statistics?.manualImportInvoiceCount, unit: "张" },
                    { label: "OA 解析新增发票", value: statistics?.oaParseCreatedInvoiceCount, unit: "张" },
                  ]}
                />
              </div>
            </div>
          </div>
        </header>
        {loadError ? (
          <div className="state-panel error">
            <span>{loadError}</span>
            <Button isDisabled={isLoading} onPress={retryWorkbenchDirectRead} size="sm" variant="secondary">
              重新读取
            </Button>
          </div>
        ) : null}
        {!loadError && backgroundLoadError ? (
          <div className="state-panel error">
            <span>{backgroundLoadError}</span>
            <Button isDisabled={isRefreshing} onPress={retryWorkbenchDirectRead} size="sm" variant="secondary">
              重新读取
            </Button>
          </div>
        ) : null}
        {!loadError && oaSyncStatusError ? (
          <div className="state-panel error">
            <span>{oaSyncStatusError}</span>
            <Button onPress={() => void pollOaSyncStatus()} size="sm" variant="secondary">
              重试 OA 状态
            </Button>
          </div>
        ) : null}
        {!loadError && !oaSyncStatusError && oaStatusPanelMessage ? (
          <div className={`state-panel${oaSyncStatus?.status === "error" ? " error" : ""}`}>{oaStatusPanelMessage}</div>
        ) : null}
        {!isLoading && !loadError && isEmpty && isOaReady ? (
          <div className="state-panel">当前没有可展示的 OA / 银行流水 / 发票记录。</div>
        ) : null}

        {!loadError ? (
          <div className="workbench-zone-stack">
            <div className="workbench-zone-slot workbench-zone-slot-top">
              {pairedZoneElement}
            </div>
            <div className="workbench-zone-slot workbench-zone-slot-bottom">
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
      <WorkbenchExceptionDrawer
        bucket={exceptionDrawerBucket}
        bucketCounts={{
          unpaired: workbenchData?.summary.unpairedExceptionCount ?? 0,
          paired: pairedExceptionCount,
        }}
        canMutateData={canWriteWorkbench}
        contentGeneration={exceptionDrawerContentGeneration}
        error={exceptionDrawerError}
        exceptionCounts={exceptionDrawerCounts}
        groups={exceptionDrawerGroups}
        hasMore={exceptionDrawerPage.hasMore}
        loading={exceptionDrawerLoading}
        loadingMore={exceptionDrawerLoadingMore}
        open={exceptionDrawerOpen}
        onBucketChange={handleExceptionDrawerBucketChange}
        onClose={handleCloseExceptionDrawer}
        onExceptionCodeChange={handleExceptionDrawerCodeChange}
        onReviewAnomaly={handleAnomalyReview}
        onEnsureGroupDetail={ensureExceptionGroupDetail}
        onInvoiceEntry={(row, group) => {
          void handleRowAction(row, "enter-invoice", group);
        }}
        onInvoiceAssignment={(row, group) => {
          void handleRowAction(row, "assign-invoice-expense-items", group);
        }}
        onLoadMore={loadMoreExceptionDrawer}
        onViewChange={handleExceptionDrawerViewChange}
        selectedExceptionCode={exceptionDrawerSelectedCode}
        total={exceptionDrawerPage.total}
        view={exceptionDrawerView}
      />
      {cashTicketPurchaseDialog ? (
        <CashTicketPurchaseModal
          defaultCashAmount={cashTicketPurchaseDialog.cashAmount}
          onClose={handleCloseCashTicketPurchaseDialog}
          onSubmit={handleSubmitCashTicketPurchase}
        />
      ) : null}
      <WorkbenchInvoiceEntryDrawer
        disabled={!canWriteWorkbench}
        open={invoiceEntryTarget !== null}
        target={invoiceEntryTarget}
        onClose={() => setInvoiceEntryTarget(null)}
        onSupportingDocumentsChanged={handleSupportingDocumentsChanged}
        onCompleted={async () => {
          const reread = await rereadWorkbenchAfterCommit();
          if (!reread) {
            throw new Error("数据已保存，但关联台重新读取失败，请稍后刷新页面确认。");
          }
        }}
      />
      <WorkbenchInvoiceAssignmentDrawer
        disabled={!canWriteWorkbench}
        open={invoiceAssignmentTarget !== null}
        target={invoiceAssignmentTarget}
        onClose={() => setInvoiceAssignmentTarget(null)}
        onCompleted={async () => {
          const reread = await rereadWorkbenchAfterCommit();
          if (!reread) {
            throw new Error("归属已保存，但关联台重新读取失败，请稍后刷新页面确认。");
          }
        }}
      />
      <WorkbenchReceiptDrawer
        caseId={receiptEditorCaseId}
        disabled={!canWriteWorkbench}
        onClose={() => setReceiptEditorCaseId(null)}
        open={receiptEditorCaseId !== null}
      />
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
    <AppDialog
      actions={(
        <>
          <Button onPress={onClose} variant="secondary">
            取消
          </Button>
          <Button
            isDisabled={!canSubmit}
            onPress={() =>
              onSubmit({
                cashAmount: normalizedAmountForInput(cashAmount),
                ticketCostAmount: normalizedAmountForInput(ticketCostAmount),
                projectName: projectName.trim(),
                expenseType: expenseType.trim(),
                expenseContent: expenseContent.trim(),
                note: note.trim(),
              })
            }
            variant="primary"
          >
            确认买票
          </Button>
        </>
      )}
      ariaLabel="确认买票成本"
      closeLabel="关闭买票确认"
      maxWidth="md"
      onClose={onClose}
      open
      title="确认买票情况"
    >
        <div className="relation-preview-message">
          此操作只把买票成本计入成本统计，流水全额不会作为成本入账。
        </div>
        <label className="relation-preview-note">
          <span>现金往来金额</span>
          <Input aria-label="现金往来金额" value={cashAmount} onChange={(event) => setCashAmount(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>买票成本（必填）</span>
          <Input aria-label="买票成本（必填）" value={ticketCostAmount} onChange={(event) => setTicketCostAmount(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>项目名称（必填）</span>
          <Input aria-label="项目名称（必填）" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>费用类型</span>
          <Input aria-label="费用类型" value={expenseType} onChange={(event) => setExpenseType(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>费用内容</span>
          <Input aria-label="费用内容" value={expenseContent} onChange={(event) => setExpenseContent(event.target.value)} />
        </label>
        <label className="relation-preview-note">
          <span>备注</span>
          <TextArea aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
    </AppDialog>
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
      title: "撤回关联",
      submitLabel: "确认撤回",
      retryLabel: "重试撤回",
      submittingMessage: "正在撤回关联...",
      statusLabel: "待撤回",
    };
  }
  return {
    title: "确认关联",
    submitLabel: "确认关联",
    retryLabel: "重试确认",
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
          ? `关系已写入，页面重新读取失败：${message} 请勿重复提交。`
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
    <div className="relation-preview-subtitle">
      <span>OA {rowCounts.oa}</span>
      <span>流水 {rowCounts.bank}</span>
      <span>发票 {rowCounts.invoice}</span>
    </div>
  );
  const footer = (
    <div className="relation-preview-actions">
      {isCommittedError || isNonRetryableError ? (
        <Button onPress={closePreview} size="sm" variant="secondary">
          关闭
        </Button>
      ) : (
        <>
          <Button isDisabled={isBusy} onPress={closePreview} size="sm" variant="secondary">
            取消
          </Button>
          <Button
            isDisabled={primaryDisabled}
            isPending={isBusy}
            onPress={handleSubmitClick}
            size="sm"
            variant={preview.operation === "withdraw_link" ? "danger" : "primary"}
          >
            {submitState.phase === "error" ? operationCopy.retryLabel : operationCopy.submitLabel}
          </Button>
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
      open
      title={operationCopy.title}
      width="min(1080px, 100vw)"
      onClose={closePreview}
    >
      <div className="relation-preview-body">
        <div className="relation-preview-toolbar">
          {subtitle}
          {headerAside}
        </div>
        {preview.message ? <div className={`relation-preview-message ${preview.requiresNote ? "warning" : ""}`}>{preview.message}</div> : null}
        <label className="relation-preview-note">
          <span>
            {preview.operation === "withdraw_link"
              ? `撤回说明（${noteRequired ? "必填" : "可选"}）`
              : noteRequired
                ? "差额说明（必填）"
                : "备注（可选）"}
          </span>
          <TextArea
            aria-label={preview.operation === "withdraw_link" ? "撤回说明" : noteRequired ? "差额说明" : "备注"}
            disabled={isBusy || isCommittedError || isNonRetryableError}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
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
      </div>
    </AppDrawer>
  );
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
