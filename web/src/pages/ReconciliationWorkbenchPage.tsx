import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import ActionStatusModal from "../components/workbench/ActionStatusModal";
import CancelProcessedExceptionModal from "../components/workbench/CancelProcessedExceptionModal";
import DetailDrawer from "../components/workbench/DetailDrawer";
import IgnoredItemsModal from "../components/workbench/IgnoredItemsModal";
import OaBankExceptionModal from "../components/workbench/OaBankExceptionModal";
import ProcessedExceptionsModal from "../components/workbench/ProcessedExceptionsModal";
import WorkbenchImportModal, { type WorkbenchImportMode } from "../components/workbench/WorkbenchImportModal";
import WorkbenchSearchBox from "../components/workbench/WorkbenchSearchBox";
import WorkbenchSearchModal from "../components/workbench/WorkbenchSearchModal";
import WorkbenchSettingsModal from "../components/workbench/WorkbenchSettingsModal";
import WorkbenchZone from "../components/workbench/WorkbenchZone";
import type { WorkbenchPane } from "../components/workbench/ResizableTriPane";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  cancelWorkbenchLink,
  cancelWorkbenchException,
  confirmWorkbenchLink,
  fetchIgnoredWorkbenchRows,
  fetchWorkbenchRowDetail,
  fetchWorkbenchSettings,
  fetchWorkbenchWithProgress,
  ignoreWorkbenchRow,
  markWorkbenchException,
  resetWorkbenchSettingsData,
  saveWorkbenchSettings,
  submitOaBankException,
  unignoreWorkbenchRow,
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
  WorkbenchRecord,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetResult,
} from "../features/workbench/types";
import { createEmptySearchResponse, fetchWorkbenchSearch } from "../features/search/api";
import type {
  WorkbenchSearchJumpTarget,
  WorkbenchSearchResponse,
  WorkbenchSearchResult,
  WorkbenchSearchScope,
  WorkbenchSearchStatus,
} from "../features/search/types";
import { useMonth } from "../contexts/MonthContext";
import useWorkbenchSelection from "../hooks/useWorkbenchSelection";
import type { WorkbenchInlineAction } from "../components/workbench/RowActions";
import type { ImportSessionPayload } from "../features/imports/types";

type ActionDialogState = {
  phase: "loading" | "result";
  title: string;
  message: string;
};

type OaBankExceptionDialogState = {
  rows: WorkbenchRecord[];
};

type CancelProcessedExceptionDialogState = {
  group: WorkbenchCandidateGroup;
};

type SubmittedSearchState = {
  query: string;
  scope: WorkbenchSearchScope;
  month: string;
  projectName: string;
  status: WorkbenchSearchStatus;
};

type WorkbenchLoadProgressState = {
  label: string;
  loadedBytes: number;
  totalBytes: number;
  percent: number | null;
  indeterminate: boolean;
};

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

function normalizeSearchKeyword(value: string) {
  return value.replace(/\s+/g, "").trim();
}

const READONLY_ACTION_MESSAGE = "当前账号仅支持查看和导出，不能执行写操作。";
const WORKBENCH_VIEW_MONTH = "all";

export default function ReconciliationWorkbenchPage() {
  const { currentMonth } = useMonth();
  const { setWorkbenchStatusText } = useAppChrome();
  const { canMutateData, canAdminAccess } = useSessionPermissions();
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
  const [ignoredData, setIgnoredData] = useState<IgnoredWorkbenchData>({ month: WORKBENCH_VIEW_MONTH, rows: [] });
  const [workbenchSettings, setWorkbenchSettings] = useState<WorkbenchSettings | null>(null);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [importModalMode, setImportModalMode] = useState<WorkbenchImportMode | null>(null);
  const [isSettingsSaving, setIsSettingsSaving] = useState(false);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchScope, setSearchScope] = useState<WorkbenchSearchScope>("all");
  const [searchMonthFilter, setSearchMonthFilter] = useState<"all" | "month">("all");
  const [searchMonthValue, setSearchMonthValue] = useState(currentMonth);
  const [searchProjectFilter, setSearchProjectFilter] = useState("");
  const [searchStatusFilter, setSearchStatusFilter] = useState<WorkbenchSearchStatus>("all");
  const [submittedSearch, setSubmittedSearch] = useState<SubmittedSearchState | null>(null);
  const [searchResults, setSearchResults] = useState<WorkbenchSearchResponse>(createEmptySearchResponse());
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [pendingSearchJump, setPendingSearchJump] = useState<WorkbenchSearchJumpTarget | null>(null);
  const [highlightedRowId, setHighlightedRowId] = useState<string | null>(null);
  const [ignoredModalOpen, setIgnoredModalOpen] = useState(false);
  const [processedExceptionsModalOpen, setProcessedExceptionsModalOpen] = useState(false);
  const [oaBankExceptionDialog, setOaBankExceptionDialog] = useState<OaBankExceptionDialogState | null>(null);
  const [cancelProcessedExceptionDialog, setCancelProcessedExceptionDialog] = useState<CancelProcessedExceptionDialogState | null>(null);
  const [pairedDisplayState, setPairedDisplayState] = useState(createEmptyWorkbenchZoneDisplayState);
  const [openDisplayState, setOpenDisplayState] = useState(createEmptyWorkbenchZoneDisplayState);
  const columnLayoutSaveRequestIdRef = useRef(0);
  const deferredPairedDisplayState = useDeferredValue(pairedDisplayState);
  const deferredOpenDisplayState = useDeferredValue(openDisplayState);

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

  const applyLocalConfirmLink = useCallback((rowIds: string[], caseId?: string) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterConfirmLink(current, rowIds, caseId) : current));
  }, []);

  const applyLocalCancelLink = useCallback((rowIds: string[]) => {
    setWorkbenchData((current) => (current ? updateWorkbenchAfterCancelLink(current, rowIds) : current));
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
    document.body.classList.toggle("workbench-focus-mode", expandedZoneId !== null);
    return () => {
      document.body.classList.remove("workbench-focus-mode");
    };
  }, [expandedZoneId]);

  useEffect(() => {
    if (isLoading || isRefreshing) {
      setWorkbenchStatusText(
        loadProgress.percent === null
          ? `${loadProgress.label}...`
          : `${loadProgress.label} ${loadProgress.percent}%`,
      );
      return;
    }
    if (workbenchData?.oaStatus?.message) {
      setWorkbenchStatusText(workbenchData.oaStatus.message);
      return;
    }
    setWorkbenchStatusText(null);
  }, [isLoading, isRefreshing, loadProgress.label, loadProgress.percent, setWorkbenchStatusText, workbenchData?.oaStatus?.message]);

  useEffect(() => () => setWorkbenchStatusText(null), [setWorkbenchStatusText]);

  const searchNarrowingHint = useMemo(() => {
    if (!searchModalOpen) {
      return null;
    }
    const normalizedKeyword = normalizeSearchKeyword(searchQuery);
    if (!normalizedKeyword) {
      return null;
    }
    if (searchMonthFilter === "all" && normalizedKeyword.length < 2) {
      return "全时间搜索请至少输入 2 个字，或切换到具体月份。";
    }
    return null;
  }, [searchModalOpen, searchMonthFilter, searchQuery]);

  const currentSearchState = useMemo<SubmittedSearchState>(
    () => ({
      query: searchQuery.trim(),
      scope: searchScope,
      month: searchMonthFilter === "month" ? searchMonthValue : "all",
      projectName: searchProjectFilter,
      status: searchStatusFilter,
    }),
    [searchMonthFilter, searchMonthValue, searchProjectFilter, searchQuery, searchScope, searchStatusFilter],
  );

  const searchNeedsSubmit = useMemo(() => {
    if (!currentSearchState.query) {
      return false;
    }
    if (!submittedSearch) {
      return true;
    }
    return JSON.stringify(currentSearchState) !== JSON.stringify(submittedSearch);
  }, [currentSearchState, submittedSearch]);

  useEffect(() => {
    if (!searchModalOpen) {
      return;
    }

    if (!submittedSearch || searchNarrowingHint) {
      setSearchResults(createEmptySearchResponse());
      setSearchError(null);
      setIsSearchLoading(false);
      return;
    }

    const controller = new AbortController();
    setIsSearchLoading(true);
    setSearchError(null);

    void fetchWorkbenchSearch({
      q: submittedSearch.query,
      scope: submittedSearch.scope,
      month: submittedSearch.month,
      projectName: submittedSearch.projectName || undefined,
      status: submittedSearch.status,
      signal: controller.signal,
    })
      .then((payload) => {
        setSearchResults(payload);
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        setSearchResults(createEmptySearchResponse(submittedSearch.query));
        setSearchError(actionErrorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsSearchLoading(false);
        }
      });

    return () => controller.abort();
  }, [searchModalOpen, searchNarrowingHint, submittedSearch]);

  useEffect(() => {
    if (!highlightedRowId) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setHighlightedRowId(null);
    }, 2400);

    return () => window.clearTimeout(timeoutId);
  }, [highlightedRowId]);

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

  const importBankOptions = useMemo(
    () => Array.from(new Set((workbenchSettings?.bankAccountMappings ?? []).map((item) => item.bankName.trim()).filter(Boolean))).sort(),
    [workbenchSettings?.bankAccountMappings],
  );

  const searchProjectOptions = useMemo(() => {
    const candidates = new Set<string>();

    if (workbenchSettings) {
      [...workbenchSettings.projects.active, ...workbenchSettings.projects.completed].forEach((project) => {
        const normalizedProjectName = project.projectName.trim();
        if (normalizedProjectName) {
          candidates.add(normalizedProjectName);
        }
      });
    }

    [
      ...(workbenchData ? flattenGroups(workbenchData.paired.groups) : []),
      ...(workbenchData ? flattenGroups(workbenchData.open.groups) : []),
      ...ignoredData.rows,
    ].forEach((row) => {
      const projectName = resolveRecordProjectName(row);
      if (projectName) {
        candidates.add(projectName);
      }
    });

    return Array.from(candidates).sort((left, right) => left.localeCompare(right, "zh-CN"));
  }, [ignoredData.rows, workbenchData, workbenchSettings]);

  useEffect(() => {
    if (!pendingSearchJump) {
      return;
    }

    if (isLoading) {
      return;
    }

    if (pendingSearchJump.zoneHint === "ignored") {
      if (!ignoredModalOpen) {
        setIgnoredModalOpen(true);
        return;
      }
    } else if (pendingSearchJump.zoneHint === "processed_exception") {
      if (!processedExceptionsModalOpen) {
        setProcessedExceptionsModalOpen(true);
        return;
      }
    }

    const targetElement = findSearchTargetElement(pendingSearchJump.rowId);
    if (!targetElement) {
      return;
    }

    targetElement.scrollIntoView?.({ behavior: "smooth", block: "center" });
    setHighlightedRowId(pendingSearchJump.rowId);
    setPendingSearchJump(null);
  }, [
    ignoredModalOpen,
    ignoredData.rows,
    isLoading,
    pendingSearchJump,
    processedExceptionGroups,
    processedExceptionsModalOpen,
    workbenchData,
  ]);

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
  const isOpenConfirmSelectionDisabled = openSelectionSummary.total < 2;
  const isOpenExceptionSelectionDisabled = openSelectionSummary.total < 1;
  const isPairedCancelSelectionDisabled = pairedSelectionSummary.total < 2;

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

  const handleOpenSearchModal = () => {
    setSearchMonthValue(currentMonth);
    setSearchModalOpen(true);
  };

  const handleCloseSearchModal = () => {
    setSearchModalOpen(false);
  };

  const handleSubmitSearch = () => {
    if (!currentSearchState.query) {
      setSubmittedSearch(null);
      setSearchResults(createEmptySearchResponse());
      setSearchError(null);
      setIsSearchLoading(false);
      return;
    }

    if (searchNarrowingHint) {
      setSubmittedSearch(null);
      setSearchResults(createEmptySearchResponse(currentSearchState.query));
      setSearchError(null);
      setIsSearchLoading(false);
      return;
    }

    setSubmittedSearch(currentSearchState);
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

  const handleOpenSettingsModal = () => {
    setSettingsModalOpen(true);
  };

  const handleWorkbenchImportComplete = useCallback((payload: ImportSessionPayload) => {
    const confirmedCount = payload.files.filter((file) => file.status === "confirmed").length;
    setImportModalMode(null);
    setLastActionMessage(`已导入 ${confirmedCount} 个文件，正在后台刷新关联台。`);
    refreshWorkbenchDataInBackground(WORKBENCH_VIEW_MONTH);
  }, [refreshWorkbenchDataInBackground]);

  const handleJumpToSearchResult = (jumpTarget: WorkbenchSearchJumpTarget) => {
    handleCloseDetail();
    setSearchModalOpen(false);
    setSearchError(null);
    setHighlightedRowId(null);
    setPendingSearchJump(jumpTarget);
    setExpandedZoneId(jumpTarget.zoneHint === "paired" ? "paired" : "open");
    if (jumpTarget.zoneHint !== "ignored") {
      setIgnoredModalOpen(false);
    }
    if (jumpTarget.zoneHint !== "processed_exception") {
      setProcessedExceptionsModalOpen(false);
    }
  };

  const handleOpenSearchResultDetail = async (result: WorkbenchSearchResult) => {
    setDetailError(null);
    setIsDetailLoading(true);
    openDetail(buildSearchResultDetailPlaceholder(result));
    try {
      const detailedRow = await fetchWorkbenchRowDetail(result.rowId);
      replaceDetailRow(detailedRow);
    } catch {
      setDetailError("详情加载失败，请稍后重试。");
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleCloseSettingsModal = () => {
    if (isSettingsSaving) {
      return;
    }
    setSettingsModalOpen(false);
  };

  const handleSaveSettings = async (payload: {
    completedProjectIds: string[];
    bankAccountMappings: WorkbenchSettings["bankAccountMappings"];
    allowedUsernames: string[];
    readonlyExportUsernames: string[];
    adminUsernames: string[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaInvoiceOffset: WorkbenchSettings["oaInvoiceOffset"];
  }) => {
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
      return;
    }
    setIsSettingsSaving(true);
    try {
      const saved = await saveWorkbenchSettings(payload);
      setWorkbenchSettings(saved);
      setSettingsModalOpen(false);
      await loadWorkbenchData(WORKBENCH_VIEW_MONTH);
      setLastActionMessage("已保存关联台设置。");
    } catch {
      openActionResultDialog("保存设置失败，请稍后重试。");
    } finally {
      setIsSettingsSaving(false);
    }
  };

  const handleSettingsDataReset = async (payload: {
    action: WorkbenchSettingsDataResetAction;
    oaPassword: string;
  }): Promise<WorkbenchSettingsDataResetResult> => {
    if (!canAdminAccess) {
      throw new Error("当前账号没有管理员权限，不能执行数据重置。");
    }
    const result = await resetWorkbenchSettingsData(payload);
    await loadWorkbenchData(WORKBENCH_VIEW_MONTH);
    setLastActionMessage(result.message);
    return result;
  };

  const openActionResultDialog = useCallback((message: string, title = "操作提示") => {
    setActionDialog({
      phase: "result",
      title,
      message,
    });
  }, []);

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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
  }, [canMutateData, handleCloseDetail, openActionResultDialog]);

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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
      return;
    }
    setOaBankExceptionDialog(null);
    await runBlockingAction({
      loadingMessage: "正在确认关联...",
      action: async () => {
        const result = await confirmWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: rows.map((row) => row.id),
          caseId: resolveSelectedCaseId(rows),
        });
        clearOpenSelection();
        applyLocalConfirmLink(
          rows.map((row) => row.id),
          resolveSelectedCaseId(rows),
        );
        return result.message;
      },
    });
  };

  const handleRowAction = useCallback(async (row: WorkbenchRecord, action: WorkbenchInlineAction) => {
    if (action === "relation-status") {
      openActionResultDialog(`当前关联情况：${row.status}`, "关联情况");
      return;
    }

    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
      return;
    }

    if (action === "confirm-match") {
      await runBlockingAction({
        loadingMessage: "正在确认关联...",
        action: async () => {
        const result = await confirmWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: collectCaseRowIds(row),
          caseId: row.caseId,
        });
        applyLocalConfirmLink(collectCaseRowIds(row), row.caseId);
        return result.message;
      },
    });
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
      await runBlockingAction({
        loadingMessage: "正在取消配对...",
        action: async () => {
        const result = await cancelWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowId: row.id,
          comment: "由关联台取消关联",
        });
        applyLocalCancelLink([row.id]);
        return result.message;
      },
    });
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
    canMutateData,
    clearOpenSelection,
    collectCaseRowIds,
    openActionResultDialog,
    openCancelProcessedExceptionDialog,
    openOaBankExceptionDialog,
    applyLocalCancelException,
    applyLocalCancelLink,
    applyLocalConfirmLink,
    applyLocalHandledException,
    applyLocalIgnoreRow,
    refreshWorkbenchDataInBackground,
    runBlockingAction,
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

  const handleConfirmOpenSelection = async () => {
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
    await runBlockingAction({
      loadingMessage: "正在确认关联...",
      action: async () => {
        const result = await confirmWorkbenchLink({
          month: WORKBENCH_VIEW_MONTH,
          rowIds: selectedOpenRows.map((row) => row.id),
          caseId: resolveSelectedCaseId(selectedOpenRows),
        });
        clearOpenSelection();
        applyLocalConfirmLink(
          selectedOpenRows.map((row) => row.id),
          resolveSelectedCaseId(selectedOpenRows),
        );
        return result.message;
      },
    });
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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
    await runBlockingAction({
      loadingMessage: "正在取消配对...",
      action: async () => {
        await Promise.all(
          selectedGroups.map((group) => {
            const representativeRow = [...group.rows.bank, ...group.rows.oa, ...group.rows.invoice][0];
            return cancelWorkbenchLink({
              month: WORKBENCH_VIEW_MONTH,
              rowId: representativeRow.id,
              comment: "由关联台批量取消配对",
            });
          }),
        );
        clearPairedSelection();
        applyLocalCancelLink(
          selectedGroups.flatMap((group) => [...group.rows.oa, ...group.rows.bank, ...group.rows.invoice].map((row) => row.id)),
        );
        return `已取消 ${selectedGroups.length} 组配对。`;
      },
    });
  };

  const handleUnignoreRow = async (row: WorkbenchRecord) => {
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
    if (!canMutateData) {
      openActionResultDialog(READONLY_ACTION_MESSAGE);
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
      canMutateData={canMutateData}
      getRowState={getRowState}
      isExpanded={expandedZoneId === "paired"}
      isVisible={isPairedVisible}
      meta="自动闭环与人工确认后的记录"
      onClearSelection={handleClearPairedSelection}
      onOpenDetail={handleOpenDetail}
      onPrimarySelectionAction={handleCancelPairedSelection}
      primarySelectionActionDisabled={isPairedCancelSelectionDisabled || !canMutateData}
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
      highlightedRowId={highlightedRowId}
      panes={pairedPanes}
      primarySelectionActionLabel="取消配对"
      selectionSummary={pairedSelectionSummary}
      title={`已配对 ${workbenchData?.summary.pairedCount ?? 0} 条`}
      tone="success"
      zoneId="paired"
    />
  );

  const openZoneElement = (
    <WorkbenchZone
      auxiliaryHeaderActions={openAuxiliaryHeaderActions}
      canMutateData={canMutateData}
      getRowState={getRowState}
      isExpanded={expandedZoneId === "open"}
      isVisible={isOpenVisible}
      meta="等待人工处理、台账跟进或后续单据补齐"
      onClearSelection={handleClearOpenSelection}
      onOpenDetail={handleOpenDetail}
      onPrimarySelectionAction={handleConfirmOpenSelection}
      primarySelectionActionDisabled={isOpenConfirmSelectionDisabled || !canMutateData}
      onRowAction={handleRowAction}
      onClearPaneSearch={handleClearPaneSearch}
      onClosePaneSearch={handleClosePaneSearch}
      onSelectRow={handleSelectRow}
      onSecondarySelectionAction={handleOpenSelectionException}
      secondarySelectionActionDisabled={isOpenExceptionSelectionDisabled || !canMutateData}
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
      highlightedRowId={highlightedRowId}
      panes={openPanes}
      primarySelectionActionLabel="确认关联"
      secondarySelectionActionLabel="异常处理"
      selectionSummary={openSelectionSummary}
      title={`未配对 ${workbenchData?.summary.openCount ?? 0} 条`}
      tone="warning"
      zoneId="open"
    />
  );

  return (
    <div className="workbench-shell">
      <div className={`page-stack${expandedZoneId ? " zone-expanded-layout" : ""}`}>
        <div className="workbench-page-toolbar">
          <div className="workbench-page-toolbar-actions">
            <button className="secondary-button" type="button" onClick={handleOpenSettingsModal}>
              设置
            </button>
            {canMutateData ? (
              <>
                <button className="secondary-button" type="button" onClick={() => setImportModalMode("bank_transaction")}>
                  银行流水导入
                </button>
                <button className="secondary-button" type="button" onClick={() => setImportModalMode("invoice")}>
                  发票导入
                </button>
                <button className="secondary-button" type="button" onClick={() => setImportModalMode("etc_invoice")}>
                  ETC发票导入
                </button>
              </>
            ) : null}
          </div>
          <WorkbenchSearchBox onOpen={handleOpenSearchModal} />
        </div>
        {lastActionMessage ? <div className="action-feedback">{lastActionMessage}</div> : null}
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

      {settingsModalOpen && workbenchSettings ? (
        <WorkbenchSettingsModal
          canManageAccessControl={canAdminAccess}
          canSave={canMutateData}
          isSaving={isSettingsSaving}
          settings={workbenchSettings}
          onClose={handleCloseSettingsModal}
          onDataReset={handleSettingsDataReset}
          onSave={handleSaveSettings}
        />
      ) : null}
      {importModalMode ? (
        <WorkbenchImportModal
          mode={importModalMode}
          bankOptions={importBankOptions}
          onClose={() => setImportModalMode(null)}
          onImported={handleWorkbenchImportComplete}
        />
      ) : null}
      <DetailDrawer error={detailError} loading={isDetailLoading} row={detailRow} onClose={handleCloseDetail} />
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
          canMutateData={canMutateData}
          highlightedRowId={highlightedRowId}
          rows={ignoredData.rows}
          onClose={handleCloseIgnoredModal}
          onUnignore={handleUnignoreRow}
        />
      ) : null}
      {processedExceptionsModalOpen ? (
        <ProcessedExceptionsModal
          canMutateData={canMutateData}
          groups={processedExceptionGroups}
          highlightedRowId={highlightedRowId}
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
      {searchModalOpen ? (
        <WorkbenchSearchModal
          error={searchError}
          hint={searchNarrowingHint}
          isLoading={isSearchLoading}
          isStale={searchNeedsSubmit}
          monthValue={searchMonthValue}
          monthMode={searchMonthFilter}
          projectName={searchProjectFilter}
          projectOptions={searchProjectOptions}
          query={searchQuery}
          results={searchResults}
          scope={searchScope}
          status={searchStatusFilter}
          onClose={handleCloseSearchModal}
          onDetail={handleOpenSearchResultDetail}
          onJump={(result) => handleJumpToSearchResult(result.jumpTarget)}
          onMonthModeChange={setSearchMonthFilter}
          onMonthValueChange={setSearchMonthValue}
          onProjectNameChange={setSearchProjectFilter}
          onQueryChange={setSearchQuery}
          onScopeChange={setSearchScope}
          onStatusChange={setSearchStatusFilter}
          onSubmitSearch={handleSubmitSearch}
        />
      ) : null}
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

function resolveRecordProjectName(row: WorkbenchRecord) {
  const summaryProjectName = row.tableValues.projectName?.trim();
  if (summaryProjectName && summaryProjectName !== "--" && summaryProjectName !== "—") {
    return summaryProjectName;
  }

  const detailProjectName = row.detailFields.find((field) => field.label === "项目名称")?.value.trim();
  if (detailProjectName && detailProjectName !== "--" && detailProjectName !== "—") {
    return detailProjectName;
  }

  return null;
}

function buildSearchResultDetailPlaceholder(result: WorkbenchSearchResult): WorkbenchRecord {
  return {
    id: result.rowId,
    recordType: result.recordType,
    label: result.recordType === "oa" ? "OA" : result.recordType === "bank" ? "银行流水" : "发票",
    status: result.statusLabel,
    statusCode: "search_preview",
    statusTone: "neutral",
    exceptionHandled: result.zoneHint === "processed_exception",
    amount: "--",
    counterparty: "--",
    tableValues: {},
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: [],
  };
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

function findSearchTargetElement(rowId: string) {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-row-id]")).find(
    (element) => element.dataset.rowId === rowId,
  ) ?? null;
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
