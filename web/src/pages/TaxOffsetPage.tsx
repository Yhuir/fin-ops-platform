import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button } from "@heroui/react";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import CertifiedInvoiceImportModal from "../components/tax/CertifiedInvoiceImportModal";
import CertifiedResultsDrawer from "../components/tax/CertifiedResultsDrawer";
import MonthPicker from "../components/MonthPicker";
import TaxResultPanel from "../components/tax/TaxResultPanel";
import TaxSummaryCards from "../components/tax/TaxSummaryCards";
import TaxTable from "../components/tax/TaxTable";
import { useAppChrome } from "../contexts/AppChromeContext";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { ApiClientError } from "../features/apiClient";
import { calculateTaxOffset, fetchTaxOffsetMonth, saveTaxOffsetPlan } from "../features/tax/api";
import { FINANCE_DOMAIN_EVENTS } from "../features/domainEvents";
import { importWorkflowPath } from "../features/imports/importRoutes";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import type {
  TaxCertifiedImportConfirmedResult,
  TaxMonthData,
  TaxSummary,
} from "../features/tax/types";

function toggleSelection(currentIds: string[], id: string) {
  return currentIds.includes(id) ? currentIds.filter((currentId) => currentId !== id) : [...currentIds, id];
}

function getSelectableInputIds(data: TaxMonthData | null) {
  if (!data) {
    return [];
  }
  return data.inputPlanInvoices.filter((row) => row.isSelectable !== false && !row.isLocked).map((row) => row.id);
}

function hasSameIds(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((id, index) => id === right[index]);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function PageNote({ message, tone }: { message: string; tone: "info" | "success" }) {
  return (
    <Alert className={`page-note page-note-${tone}`} role="status" status={tone === "success" ? "success" : "accent"}>
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Description>{message}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

export default function TaxOffsetPage() {
  const navigate = useNavigate();
  const { setWorkbenchHeaderActions } = useAppChrome();
  const { canMutateData } = useSessionPermissions();
  const currentMonthSession = usePageSessionState({
    pageKey: "tax-offset",
    stateKey: "currentMonth",
    version: 1,
    initialValue: DEFAULT_MONTH,
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is string => typeof value === "string" && /^\d{4}-\d{2}$/.test(value),
  });
  const selectedInputIdsSession = usePageSessionState({
    pageKey: "tax-offset",
    stateKey: "selectedInputIds",
    version: 1,
    initialValue: [] as string[],
    ttlMs: 30 * 60 * 1000,
    storage: "session",
    validate: isStringArray,
  });
  const certifiedDrawerSession = usePageSessionState({
    pageKey: "tax-offset",
    stateKey: "certifiedDrawerCollapsed",
    version: 1,
    initialValue: false,
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: (value): value is boolean => typeof value === "boolean",
  });
  const currentMonth = currentMonthSession.value;
  const setCurrentMonth = currentMonthSession.setValue;
  const [monthData, setMonthData] = useState<TaxMonthData | null>(null);
  const [summary, setSummary] = useState<TaxSummary | null>(null);
  const selectedInputIds = selectedInputIdsSession.value;
  const setSelectedInputIds = selectedInputIdsSession.setValue;
  const isCertifiedDrawerCollapsed = certifiedDrawerSession.value;
  const setIsCertifiedDrawerCollapsed = certifiedDrawerSession.setValue;
  const [isCertifiedImportModalOpen, setIsCertifiedImportModalOpen] = useState(false);
  const [highlightedPlanInputId, setHighlightedPlanInputId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [isSavingPlan, setIsSavingPlan] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [importFeedback, setImportFeedback] = useState<string | null>(null);
  const [planFeedback, setPlanFeedback] = useState<string | null>(null);
  const outputTableWrapRef = useRef<HTMLDivElement | null>(null);
  const inputTableWrapRef = useRef<HTMLDivElement | null>(null);
  const taxLayoutScrollbarRef = useRef<HTMLDivElement | null>(null);
  const taxLayoutScrollbarInnerRef = useRef<HTMLDivElement | null>(null);
  const isSyncingTaxLayoutScrollRef = useRef(false);
  const isMountedRef = useRef(false);
  const resetLoadRequestIdRef = useRef(0);
  const refreshLoadRequestIdRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useLayoutEffect(() => {
    setWorkbenchHeaderActions({
      canMutateData,
      onOpenImport: (mode) => navigate(importWorkflowPath(mode)),
      onOpenSettings: () => navigate("/settings"),
    });
    return () => {
      setWorkbenchHeaderActions(null);
    };
  }, [canMutateData, navigate, setWorkbenchHeaderActions]);

  const loadMonthData = useCallback(
    async (mode: "reset" | "refresh", signal?: AbortSignal) => {
      const requestId = mode === "reset"
        ? resetLoadRequestIdRef.current + 1
        : refreshLoadRequestIdRef.current + 1;
      if (mode === "reset") {
        resetLoadRequestIdRef.current = requestId;
      } else {
        refreshLoadRequestIdRef.current = requestId;
      }
      const isCurrentRequest = () => (
        mode === "reset"
          ? requestId === resetLoadRequestIdRef.current
          : requestId === refreshLoadRequestIdRef.current
      );
      if (mode === "reset") {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setLoadError(null);
      try {
        const payload = await fetchTaxOffsetMonth(currentMonth, signal);
        if (!isMountedRef.current || !isCurrentRequest()) {
          return;
        }
        setMonthData(payload);
        setSummary(payload.summary);
        setHighlightedPlanInputId((currentId) =>
          currentId && payload.inputPlanInvoices.some((row) => row.id === currentId) ? currentId : null,
        );
        setSelectedInputIds((currentIds) => {
          const selectableIds = new Set(
            payload.inputPlanInvoices
              .filter((row) => row.isSelectable !== false && !row.isLocked)
              .map((row) => row.id),
          );
          const filteredIds = currentIds.filter((id) => selectableIds.has(id));
          return mode === "refresh" || filteredIds.length > 0 ? filteredIds : payload.defaultSelectedInputIds;
        });
      } catch {
        if (!signal?.aborted && isMountedRef.current && isCurrentRequest()) {
          setMonthData(null);
          setSummary(null);
          setLoadError("税金抵扣数据加载失败，请稍后重试。");
        }
      } finally {
        if (isMountedRef.current && isCurrentRequest()) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    },
    [currentMonth],
  );

  useEffect(() => {
    const controller = new AbortController();
    setImportFeedback(null);
    setPlanFeedback(null);
    void loadMonthData("reset", controller.signal);
    return () => controller.abort();
  }, [loadMonthData]);

  const handleRefreshTrigger = useCallback(() => {
    if (document.visibilityState === "hidden") {
      return;
    }
    void loadMonthData("refresh");
  }, [loadMonthData]);

  useEffect(() => {
    window.addEventListener("focus", handleRefreshTrigger);
    document.addEventListener("visibilitychange", handleRefreshTrigger);
    return () => {
      window.removeEventListener("focus", handleRefreshTrigger);
      document.removeEventListener("visibilitychange", handleRefreshTrigger);
    };
  }, [handleRefreshTrigger]);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, handleRefreshTrigger);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.etcBusinessBatchUpdated, handleRefreshTrigger);

  useEffect(() => {
    if (!monthData) {
      return;
    }

    if (hasSameIds(selectedInputIds, monthData.defaultSelectedInputIds)) {
      setSummary(monthData.summary);
      setIsCalculating(false);
      return;
    }

    let cancelled = false;
    const monthSnapshot = monthData;

    async function recalculate() {
      setIsCalculating(true);
      try {
        const nextSummary = await calculateTaxOffset({
          month: currentMonth,
          selectedOutputIds: monthSnapshot.defaultSelectedOutputIds,
          selectedInputIds,
        });
        if (!cancelled) {
          setSummary(nextSummary);
        }
      } catch {
        if (!cancelled) {
          setLoadError("税金抵扣试算失败，请稍后重试。");
        }
      } finally {
        if (!cancelled) {
          setIsCalculating(false);
        }
      }
    }

    void recalculate();
    return () => {
      cancelled = true;
    };
  }, [currentMonth, monthData, selectedInputIds]);

  useEffect(() => {
    const tableWraps = [outputTableWrapRef.current, inputTableWrapRef.current].filter(
      (node): node is HTMLDivElement => Boolean(node),
    );
    const scrollbar = taxLayoutScrollbarRef.current;
    const scrollbarInner = taxLayoutScrollbarInnerRef.current;
    if (tableWraps.length === 0 || !scrollbar || !scrollbarInner) {
      return undefined;
    }

    const getMaxScrollLeft = (node: HTMLDivElement) => Math.max(0, node.scrollWidth - node.clientWidth);

    const syncDimensions = () => {
      const maxScrollWidth = Math.max(...tableWraps.map((node) => node.scrollWidth), 0);
      scrollbarInner.style.width = `${maxScrollWidth}px`;
      scrollbar.scrollLeft = Math.max(...tableWraps.map((node) => node.scrollLeft), 0);
    };

    const syncFromTable = (source: HTMLDivElement) => {
      if (isSyncingTaxLayoutScrollRef.current) {
        return;
      }
      isSyncingTaxLayoutScrollRef.current = true;
      const nextScrollLeft = source.scrollLeft;
      scrollbar.scrollLeft = nextScrollLeft;
      tableWraps.forEach((node) => {
        if (node === source) {
          return;
        }
        node.scrollLeft = Math.min(nextScrollLeft, getMaxScrollLeft(node));
      });
      requestAnimationFrame(() => {
        isSyncingTaxLayoutScrollRef.current = false;
      });
    };

    const syncFromScrollbar = () => {
      if (isSyncingTaxLayoutScrollRef.current) {
        return;
      }
      isSyncingTaxLayoutScrollRef.current = true;
      tableWraps.forEach((node) => {
        node.scrollLeft = Math.min(scrollbar.scrollLeft, getMaxScrollLeft(node));
      });
      requestAnimationFrame(() => {
        isSyncingTaxLayoutScrollRef.current = false;
      });
    };

    const cleanupTableListeners = tableWraps.map((node) => {
      const handleScroll = () => syncFromTable(node);
      node.addEventListener("scroll", handleScroll);
      return () => node.removeEventListener("scroll", handleScroll);
    });

    syncDimensions();
    scrollbar.addEventListener("scroll", syncFromScrollbar);
    window.addEventListener("resize", syncDimensions);

    return () => {
      cleanupTableListeners.forEach((cleanup) => cleanup());
      scrollbar.removeEventListener("scroll", syncFromScrollbar);
      window.removeEventListener("resize", syncDimensions);
    };
  }, [monthData]);

  const isEmpty = !isLoading && !loadError && monthData
    ? monthData.outputInvoices.length === 0
      && monthData.inputPlanInvoices.length === 0
      && monthData.certifiedMatchedInvoices.length === 0
      && monthData.certifiedOutsidePlanInvoices.length === 0
    : false;
  const selectableInputIds = getSelectableInputIds(monthData);
  const hasVisibleMonthData = Boolean(monthData);
  const headerStatusMessage = importFeedback
    ?? planFeedback
    ?? null;

  const handleCertifiedImportComplete = useCallback(
    async (result: TaxCertifiedImportConfirmedResult) => {
      setIsCertifiedImportModalOpen(false);
      await loadMonthData("refresh");
      setImportFeedback(`已导入 ${result.persistedRecordCount} 条已认证记录，并已刷新当前税金抵扣页面。`);
      setPlanFeedback(null);
    },
    [loadMonthData],
  );

  const handleSavePlan = useCallback(async () => {
    if (!monthData || !summary || isSavingPlan) {
      return;
    }
    setIsSavingPlan(true);
    setLoadError(null);
    setImportFeedback(null);
    setPlanFeedback(null);
    try {
      await saveTaxOffsetPlan({
        month: currentMonth,
        selectedOutputIds: monthData.defaultSelectedOutputIds,
        selectedInputIds,
        expectedSourceVersions: monthData.sourceVersions,
        idempotencyKey: `tax-offset-plan:${currentMonth}:${selectedInputIds.join(",")}`,
      });
      setPlanFeedback("已保存本月税金抵扣计划。");
      await loadMonthData("refresh");
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409) {
        setLoadError(error.message || "税金抵扣数据已变化，请刷新后重新保存。");
      } else {
        setLoadError("税金抵扣计划保存失败，请稍后重试。");
      }
    } finally {
      if (isMountedRef.current) {
        setIsSavingPlan(false);
      }
    }
  }, [currentMonth, isSavingPlan, loadMonthData, monthData, selectedInputIds, summary]);

  return (
    <PageScaffold
      title="税金抵扣计划与试算"
      description="围绕进项票认证计划与已认证结果，做本月税金抵扣试算、导入核对与计划保存。"
      actions={(
        <div className="tax-page-actions">
          {headerStatusMessage ? (
            <PageNote message={headerStatusMessage} tone={importFeedback || planFeedback ? "success" : "info"} />
          ) : null}
          {canMutateData ? (
            <Button type="button" variant="outline" onPress={() => setIsCertifiedImportModalOpen(true)}>
              已认证发票导入
            </Button>
          ) : null}
          <MonthPicker value={currentMonth} onChange={setCurrentMonth} />
        </div>
      )}
    >
      {loadError ? <StatePanel tone="error">{loadError}</StatePanel> : null}
      {!hasVisibleMonthData && isLoading ? (
        <StatePanel tone="loading">正在加载 {currentMonth} 的税金抵扣计划与已认证结果...</StatePanel>
      ) : null}
      {isEmpty ? <StatePanel tone="empty">当前月份没有可用于计划与试算的发票数据。</StatePanel> : null}

      {summary ? <TaxSummaryCards summary={summary} /> : null}

      {summary ? (
        <TaxResultPanel
          outputCount={monthData?.outputInvoices.length ?? 0}
          certifiedCount={(monthData?.certifiedMatchedInvoices.length ?? 0) + (monthData?.certifiedOutsidePlanInvoices.length ?? 0)}
          selectedPlanInputCount={selectedInputIds.length}
          resultAmount={summary.resultAmount}
          resultLabel={summary.resultLabel}
          canSave={canMutateData}
          isSaving={isSavingPlan}
          saveDisabled={isCalculating || isLoading || isRefreshing}
          onSave={handleSavePlan}
        />
      ) : null}
      {!loadError && monthData ? (
        <div className="tax-offset-workspace">
          <div className="tax-left-workspace">
            <div className="tax-layout">
              <TaxTable
                selectable={false}
                showBottomScrollbar={false}
                tableWrapRef={outputTableWrapRef}
                title="销项票开票情况"
                rows={monthData.outputInvoices}
                selectedIds={[]}
              />
              <TaxTable
                highlightedRowId={highlightedPlanInputId}
                showBottomScrollbar={false}
                tableWrapRef={inputTableWrapRef}
                title="进项票认证计划"
                rows={monthData.inputPlanInvoices}
                selectedIds={selectedInputIds}
                headerActions={(
                  <>
                    <Button
                      className="secondary-button compact"
                      type="button"
                      isDisabled={selectableInputIds.length === 0 || selectedInputIds.length === selectableInputIds.length}
                      size="sm"
                      variant="outline"
                      onPress={() => setSelectedInputIds(selectableInputIds)}
                    >
                      全选
                    </Button>
                    <Button
                      className="secondary-button compact"
                      type="button"
                      isDisabled={selectedInputIds.length === 0}
                      size="sm"
                      variant="outline"
                      onPress={() => setSelectedInputIds([])}
                    >
                      清空
                    </Button>
                  </>
                )}
                onToggleRow={(id) => setSelectedInputIds((currentIds) => toggleSelection(currentIds, id))}
              />
            </div>
            <div
              ref={taxLayoutScrollbarRef}
              className="tax-layout-scrollbar"
              aria-label="税金抵扣表格横向滚动"
            >
              <div ref={taxLayoutScrollbarInnerRef} className="tax-layout-scrollbar-inner" />
            </div>
          </div>
          <CertifiedResultsDrawer
            isCollapsed={isCertifiedDrawerCollapsed}
            matchedRows={monthData.certifiedMatchedInvoices}
            outsidePlanRows={monthData.certifiedOutsidePlanInvoices}
            onSelectMatchedRow={(row) => setHighlightedPlanInputId(row.matchedInputId)}
            onToggleCollapse={() => setIsCertifiedDrawerCollapsed((current) => !current)}
          />
        </div>
      ) : null}

      {isCertifiedImportModalOpen ? (
        <CertifiedInvoiceImportModal
          currentMonth={currentMonth}
          onClose={() => setIsCertifiedImportModalOpen(false)}
          onImported={handleCertifiedImportComplete}
        />
      ) : null}
    </PageScaffold>
  );
}
