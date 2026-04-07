import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import MonthPicker from "../components/MonthPicker";
import ActionStatusModal from "../components/workbench/ActionStatusModal";
import CancelProcessedExceptionModal from "../components/workbench/CancelProcessedExceptionModal";
import DetailDrawer from "../components/workbench/DetailDrawer";
import IgnoredItemsModal from "../components/workbench/IgnoredItemsModal";
import OaBankExceptionModal from "../components/workbench/OaBankExceptionModal";
import ProcessedExceptionsModal from "../components/workbench/ProcessedExceptionsModal";
import WorkbenchSearchBox from "../components/workbench/WorkbenchSearchBox";
import WorkbenchSearchModal from "../components/workbench/WorkbenchSearchModal";
import WorkbenchSettingsModal from "../components/workbench/WorkbenchSettingsModal";
import WorkbenchZone from "../components/workbench/WorkbenchZone";
import type { WorkbenchPane } from "../components/workbench/ResizableTriPane";
import { useAppChrome } from "../contexts/AppChromeContext";
import {
  cancelWorkbenchLink,
  cancelWorkbenchException,
  confirmWorkbenchLink,
  fetchIgnoredWorkbenchRows,
  fetchWorkbench,
  fetchWorkbenchSettings,
  fetchWorkbenchRowDetail,
  ignoreWorkbenchRow,
  markWorkbenchException,
  saveWorkbenchSettings,
  submitOaBankException,
  unignoreWorkbenchRow,
} from "../features/workbench/api";
import { buildOaBankExceptionOptions } from "../features/workbench/oaBankExceptionOptions";
import type { IgnoredWorkbenchData, WorkbenchCandidateGroup, WorkbenchData, WorkbenchRecord, WorkbenchSettings } from "../features/workbench/types";
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

export default function ReconciliationWorkbenchPage() {
  const navigate = useNavigate();
  const { currentMonth, setCurrentMonth } = useMonth();
  const { setWorkbenchFocusMode } = useAppChrome();
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);
  const [expandedZoneId, setExpandedZoneId] = useState<"paired" | "open" | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionDialogState | null>(null);
  const [ignoredData, setIgnoredData] = useState<IgnoredWorkbenchData>({ month: currentMonth, rows: [] });
  const [workbenchSettings, setWorkbenchSettings] = useState<WorkbenchSettings | null>(null);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
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

  async function loadWorkbenchData(month: string, signal?: AbortSignal) {
    setIsLoading(true);
    setLoadError(null);

    try {
      const [payload, ignoredPayload, settingsPayload] = await Promise.all([
        fetchWorkbench(month, signal),
        fetchIgnoredWorkbenchRows(month, signal),
        fetchWorkbenchSettings(signal),
      ]);
      setWorkbenchData(payload);
      setIgnoredData(ignoredPayload);
      setWorkbenchSettings(settingsPayload);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setWorkbenchData(null);
      setIgnoredData({ month, rows: [] });
      setLoadError("工作台数据加载失败，请稍后重试。");
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    clearSelection();
    setLastActionMessage(null);
    setDetailError(null);
    void loadWorkbenchData(currentMonth, controller.signal);
    return () => controller.abort();
  }, [currentMonth]);

  useEffect(() => {
    setWorkbenchFocusMode(expandedZoneId !== null);
    return () => setWorkbenchFocusMode(false);
  }, [expandedZoneId, setWorkbenchFocusMode]);

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

    if (currentMonth !== pendingSearchJump.month || isLoading) {
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
    currentMonth,
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
      ...flattenGroups(workbenchData.paired.groups),
      ...flattenGroups(visibleOpenGroups),
    ];
  }, [visibleOpenGroups, workbenchData]);

  const allGroups = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchCandidateGroup[];
    }
    return [...workbenchData.paired.groups, ...visibleOpenGroups];
  }, [visibleOpenGroups, workbenchData]);

  const openRows = useMemo(() => {
    return flattenGroups(visibleOpenGroups);
  }, [visibleOpenGroups]);

  const pairedRows = useMemo(() => {
    if (!workbenchData) {
      return [] as WorkbenchRecord[];
    }
    return flattenGroups(workbenchData.paired.groups);
  }, [workbenchData]);

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

  const collectCaseRowIds = (row: WorkbenchRecord) => {
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
  };

  const handleOpenDetail = async (row: WorkbenchRecord) => {
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
  };

  const handleCloseDetail = () => {
    setDetailError(null);
    setIsDetailLoading(false);
    closeDetail();
  };

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
    if (currentMonth !== jumpTarget.month) {
      setCurrentMonth(jumpTarget.month);
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
  }) => {
    setIsSettingsSaving(true);
    try {
      const saved = await saveWorkbenchSettings(payload);
      setWorkbenchSettings(saved);
      setSettingsModalOpen(false);
      await loadWorkbenchData(currentMonth);
      setLastActionMessage("已保存关联台设置。");
    } catch {
      openActionResultDialog("保存设置失败，请稍后重试。");
    } finally {
      setIsSettingsSaving(false);
    }
  };

  const openCancelProcessedExceptionDialog = (row: WorkbenchRecord) => {
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
  };

  const handleCloseCancelProcessedExceptionDialog = () => {
    setCancelProcessedExceptionDialog(null);
  };

  const openOaBankExceptionDialog = (rows: WorkbenchRecord[]) => {
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
  };

  const handleCloseOaBankExceptionDialog = () => {
    setOaBankExceptionDialog(null);
  };

  const openActionResultDialog = (message: string, title = "操作提示") => {
    setActionDialog({
      phase: "result",
      title,
      message,
    });
  };

  const runBlockingAction = async ({
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
  };

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
    setOaBankExceptionDialog(null);
    await runBlockingAction({
      loadingMessage: "正在执行异常处理...",
      action: async () => {
        const result = await submitOaBankException({
          month: currentMonth,
          rowIds: rows.map((row) => row.id),
          exceptionCode,
          exceptionLabel,
          comment,
        });
        clearOpenSelection();
        await loadWorkbenchData(currentMonth);
        return result.message;
      },
    });
  };

  const handleConfirmFromOaBankException = async (rows: WorkbenchRecord[]) => {
    setOaBankExceptionDialog(null);
    await runBlockingAction({
      loadingMessage: "正在确认关联...",
      action: async () => {
        const result = await confirmWorkbenchLink({
          month: currentMonth,
          rowIds: rows.map((row) => row.id),
          caseId: resolveSelectedCaseId(rows),
        });
        clearOpenSelection();
        await loadWorkbenchData(currentMonth);
        return result.message;
      },
    });
  };

  const handleRowAction = async (row: WorkbenchRecord, action: WorkbenchInlineAction) => {
    if (action === "relation-status") {
      openActionResultDialog(`当前关联情况：${row.status}`, "关联情况");
      return;
    }

    if (action === "confirm-match") {
      await runBlockingAction({
        loadingMessage: "正在确认关联...",
        action: async () => {
          const result = await confirmWorkbenchLink({
            month: currentMonth,
            rowIds: collectCaseRowIds(row),
            caseId: row.caseId,
          });
          await loadWorkbenchData(currentMonth);
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
            month: currentMonth,
            rowId: row.id,
            exceptionCode: row.recordType === "invoice" ? "pending_collection" : "manual_review",
            comment: `由关联台标记异常：${row.id}`,
          });
          await loadWorkbenchData(currentMonth);
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
            month: currentMonth,
            rowId: row.id,
            comment: `由关联台忽略发票：${row.id}`,
          });
          await loadWorkbenchData(currentMonth);
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
            month: currentMonth,
            rowId: row.id,
            comment: "由关联台取消关联",
          });
          await loadWorkbenchData(currentMonth);
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
  };

  const handleSelectRow = (row: WorkbenchRecord, zoneId: "paired" | "open") => {
    if (zoneId === "open") {
      toggleOpenRowSelection(row);
      return;
    }
    togglePairedRowSelection(row);
  };

  const resolveSelectedCaseId = (rows: WorkbenchRecord[]) => {
    const caseIds = Array.from(new Set(rows.map((row) => row.caseId).filter((caseId): caseId is string => Boolean(caseId))));
    return caseIds.length === 1 ? caseIds[0] : undefined;
  };

  const handleConfirmOpenSelection = async () => {
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
          month: currentMonth,
          rowIds: selectedOpenRows.map((row) => row.id),
          caseId: resolveSelectedCaseId(selectedOpenRows),
        });
        clearOpenSelection();
        await loadWorkbenchData(currentMonth);
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
                month: currentMonth,
                rowId: row.id,
                exceptionCode: "pending_collection",
                comment: `由关联台批量标记异常：${row.id}`,
              })),
          );
          clearOpenSelection();
          await loadWorkbenchData(currentMonth);
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
              month: currentMonth,
              rowId: representativeRow.id,
              comment: "由关联台批量取消配对",
            });
          }),
        );
        clearPairedSelection();
        await loadWorkbenchData(currentMonth);
        return `已取消 ${selectedGroups.length} 组配对。`;
      },
    });
  };

  const handleUnignoreRow = async (row: WorkbenchRecord) => {
    setIgnoredModalOpen(false);
    await runBlockingAction({
      loadingMessage: "正在撤回忽略...",
      action: async () => {
        const result = await unignoreWorkbenchRow({
          month: currentMonth,
          rowId: row.id,
        });
        await loadWorkbenchData(currentMonth);
        return result.message;
      },
    });
  };

  const handleConfirmCancelProcessedException = async () => {
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
          month: currentMonth,
          rowIds: rows.map((row) => row.id),
          comment: "由已处理异常弹窗撤回异常处理",
        });
        await loadWorkbenchData(currentMonth);
        return result.message;
      },
    });
  };

  const pairedPanes: WorkbenchPane[] = [
    { id: "oa", title: "OA", rows: workbenchData?.paired.groups.flatMap((group) => group.rows.oa) ?? [] },
    { id: "bank", title: "银行流水", rows: workbenchData?.paired.groups.flatMap((group) => group.rows.bank) ?? [] },
    { id: "invoice", title: "进销项发票", rows: workbenchData?.paired.groups.flatMap((group) => group.rows.invoice) ?? [] },
  ];

  const openPanes: WorkbenchPane[] = [
    { id: "oa", title: "OA", rows: visibleOpenGroups.flatMap((group) => group.rows.oa) },
    { id: "bank", title: "银行流水", rows: visibleOpenGroups.flatMap((group) => group.rows.bank) },
    { id: "invoice", title: "进销项发票", rows: visibleOpenGroups.flatMap((group) => group.rows.invoice) },
  ];

  const isEmpty = (workbenchData?.summary.totalCount ?? 0) === 0;
  const shouldRenderPairedZone = expandedZoneId === null || expandedZoneId === "paired";
  const shouldRenderOpenZone = expandedZoneId === null || expandedZoneId === "open";

  return (
    <div className="workbench-shell">
      <div className={`page-stack${expandedZoneId ? " zone-expanded-layout" : ""}`}>
        <div className="workbench-page-toolbar">
          <div className="workbench-page-toolbar-actions">
            <button className="secondary-button" type="button" onClick={handleOpenSettingsModal}>
              设置
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/imports?intent=bank_transaction")}>
              银行流水导入
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/imports?intent=output_invoice")}>
              销项发票导入
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/imports?intent=input_invoice")}>
              进项发票导入
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/imports?intent=etc_invoice")}>
              ETC发票导入
            </button>
          </div>
          <WorkbenchSearchBox onOpen={handleOpenSearchModal} />
          <MonthPicker value={currentMonth} onChange={setCurrentMonth} />
        </div>
        {lastActionMessage ? <div className="action-feedback">{lastActionMessage}</div> : null}
        {isLoading ? <div className="state-panel">正在加载 {currentMonth} 的工作台数据...</div> : null}
        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {!isLoading && !loadError && isEmpty ? (
          <div className="state-panel">当前月份没有可展示的 OA / 银行流水 / 发票记录。</div>
        ) : null}

        {expandedZoneId === null ? (
          <div className="stats-row">
            <div className="stat-card">
              <span>已配对</span>
              <strong>{workbenchData?.summary.pairedCount ?? 0} 条</strong>
            </div>
            <div className="stat-card warn">
              <span>未配对</span>
              <strong>{workbenchData?.summary.openCount ?? 0} 条</strong>
            </div>
            <div className="stat-card">
              <span>异常待处理</span>
              <strong>{workbenchData?.summary.exceptionCount ?? 0} 条</strong>
            </div>
          </div>
        ) : null}

        {!loadError ? (
          <>
            {shouldRenderPairedZone ? (
              <WorkbenchZone
                getRowState={getRowState}
                isExpanded={expandedZoneId === "paired"}
                meta="自动闭环与人工确认后的记录"
                onClearSelection={handleClearPairedSelection}
                onOpenDetail={handleOpenDetail}
                onPrimarySelectionAction={handleCancelPairedSelection}
                primarySelectionActionDisabled={isPairedCancelSelectionDisabled}
                onRowAction={handleRowAction}
                onSelectRow={handleSelectRow}
                onToggleExpand={() => setExpandedZoneId((current) => (current === "paired" ? null : "paired"))}
                groups={workbenchData?.paired.groups ?? []}
                highlightedRowId={highlightedRowId}
                panes={pairedPanes}
                primarySelectionActionLabel="取消配对"
                selectionSummary={pairedSelectionSummary}
                title="已配对"
                tone="success"
                zoneId="paired"
              />
            ) : null}

            {shouldRenderOpenZone ? (
              <WorkbenchZone
                auxiliaryHeaderActions={[
                  {
                    label: `已处理异常${processedExceptionRows.length}项`,
                    onClick: handleOpenProcessedExceptionsModal,
                    tone: "danger",
                  },
                  {
                    label: `已忽略${ignoredData.rows.length}项`,
                    onClick: handleOpenIgnoredModal,
                    tone: "warning",
                  },
                ]}
                getRowState={getRowState}
                isExpanded={expandedZoneId === "open"}
                meta="等待人工处理、台账跟进或后续单据补齐"
                onClearSelection={handleClearOpenSelection}
                onOpenDetail={handleOpenDetail}
                onPrimarySelectionAction={handleConfirmOpenSelection}
                primarySelectionActionDisabled={isOpenConfirmSelectionDisabled}
                onRowAction={handleRowAction}
                onSelectRow={handleSelectRow}
                onSecondarySelectionAction={handleOpenSelectionException}
                secondarySelectionActionDisabled={isOpenExceptionSelectionDisabled}
                onToggleExpand={() => setExpandedZoneId((current) => (current === "open" ? null : "open"))}
                groups={visibleOpenGroups}
                highlightedRowId={highlightedRowId}
                panes={openPanes}
                primarySelectionActionLabel="确认关联"
                secondarySelectionActionLabel="异常处理"
                selectionSummary={openSelectionSummary}
                title="未配对"
                tone="warning"
                zoneId="open"
              />
            ) : null}
          </>
        ) : null}
      </div>

      {settingsModalOpen && workbenchSettings ? (
        <WorkbenchSettingsModal
          isSaving={isSettingsSaving}
          settings={workbenchSettings}
          onClose={handleCloseSettingsModal}
          onSave={handleSaveSettings}
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
          highlightedRowId={highlightedRowId}
          rows={ignoredData.rows}
          onClose={handleCloseIgnoredModal}
          onUnignore={handleUnignoreRow}
        />
      ) : null}
      {processedExceptionsModalOpen ? (
        <ProcessedExceptionsModal
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
