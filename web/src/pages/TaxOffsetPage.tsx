import { useCallback, useEffect, useRef, useState } from "react";

import CertifiedInvoiceImportModal from "../components/tax/CertifiedInvoiceImportModal";
import CertifiedResultsDrawer from "../components/tax/CertifiedResultsDrawer";
import MonthPicker from "../components/MonthPicker";
import TaxResultPanel from "../components/tax/TaxResultPanel";
import TaxSummaryCards from "../components/tax/TaxSummaryCards";
import TaxTable from "../components/tax/TaxTable";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { calculateTaxOffset, fetchTaxOffsetMonth } from "../features/tax/api";
import type {
  TaxCertifiedImportConfirmResult,
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

export default function TaxOffsetPage() {
  const { canMutateData } = useSessionPermissions();
  const [currentMonth, setCurrentMonth] = useState(DEFAULT_MONTH);
  const [monthData, setMonthData] = useState<TaxMonthData | null>(null);
  const [summary, setSummary] = useState<TaxSummary | null>(null);
  const [selectedInputIds, setSelectedInputIds] = useState<string[]>([]);
  const [isCertifiedDrawerCollapsed, setIsCertifiedDrawerCollapsed] = useState(false);
  const [isCertifiedImportModalOpen, setIsCertifiedImportModalOpen] = useState(false);
  const [highlightedPlanInputId, setHighlightedPlanInputId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [importFeedback, setImportFeedback] = useState<string | null>(null);
  const outputTableWrapRef = useRef<HTMLDivElement | null>(null);
  const inputTableWrapRef = useRef<HTMLDivElement | null>(null);
  const taxLayoutScrollbarRef = useRef<HTMLDivElement | null>(null);
  const taxLayoutScrollbarInnerRef = useRef<HTMLDivElement | null>(null);
  const isSyncingTaxLayoutScrollRef = useRef(false);

  const loadMonthData = useCallback(
    async (mode: "reset" | "refresh", signal?: AbortSignal) => {
      if (mode === "reset") {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setLoadError(null);
      try {
        const payload = await fetchTaxOffsetMonth(currentMonth, signal);
        setMonthData(payload);
        setSummary(payload.summary);
        setHighlightedPlanInputId((currentId) =>
          currentId && payload.inputPlanInvoices.some((row) => row.id === currentId) ? currentId : null,
        );
        setSelectedInputIds((currentIds) => {
          if (mode === "refresh") {
            const selectableIds = new Set(
              payload.inputPlanInvoices
                .filter((row) => row.isSelectable !== false)
                .map((row) => row.id),
            );
            return currentIds.filter((id) => selectableIds.has(id));
          }
          return payload.defaultSelectedInputIds;
        });
      } catch {
        if (!signal?.aborted) {
          setMonthData(null);
          setSummary(null);
          setLoadError("税金抵扣数据加载失败，请稍后重试。");
        }
      } finally {
        if (!signal?.aborted) {
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
    void loadMonthData("reset", controller.signal);
    return () => controller.abort();
  }, [loadMonthData]);

  useEffect(() => {
    function handleRefreshTrigger() {
      if (document.visibilityState === "hidden") {
        return;
      }
      void loadMonthData("refresh");
    }

    window.addEventListener("focus", handleRefreshTrigger);
    document.addEventListener("visibilitychange", handleRefreshTrigger);
    return () => {
      window.removeEventListener("focus", handleRefreshTrigger);
      document.removeEventListener("visibilitychange", handleRefreshTrigger);
    };
  }, [loadMonthData]);

  useEffect(() => {
    if (!monthData) {
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

  const handleCertifiedImportComplete = useCallback(
    async (result: TaxCertifiedImportConfirmResult) => {
      setIsCertifiedImportModalOpen(false);
      await loadMonthData("refresh");
      setImportFeedback(`已导入 ${result.persistedRecordCount} 条已认证记录，并已刷新当前税金抵扣页面。`);
    },
    [loadMonthData],
  );

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>税金抵扣计划与试算</h1>
          <p>围绕进项票认证计划与已认证结果，做本月税金抵扣试算与展示，不承担真实税务业务动作。</p>
        </div>
        <div className="page-header-actions">
          {canMutateData ? (
            <button className="secondary-button" type="button" onClick={() => setIsCertifiedImportModalOpen(true)}>
              已认证发票导入
            </button>
          ) : null}
          <MonthPicker value={currentMonth} onChange={setCurrentMonth} />
        </div>
      </header>

      {loadError ? <div className="state-panel error">{loadError}</div> : null}
      {importFeedback ? <div className="state-panel success">{importFeedback}</div> : null}
      {isLoading ? <div className="state-panel">正在加载 {currentMonth} 的税金抵扣计划与已认证结果...</div> : null}
      {isRefreshing ? <div className="state-panel">正在同步最新已认证结果与计划状态...</div> : null}
      {isEmpty ? <div className="state-panel">当前月份没有可用于计划与试算的发票数据。</div> : null}

      {summary ? <TaxSummaryCards summary={summary} /> : null}

      {summary ? (
        <TaxResultPanel
          outputCount={monthData?.outputInvoices.length ?? 0}
          certifiedCount={(monthData?.certifiedMatchedInvoices.length ?? 0) + (monthData?.certifiedOutsidePlanInvoices.length ?? 0)}
          selectedPlanInputCount={selectedInputIds.length}
          resultAmount={summary.resultAmount}
          resultLabel={summary.resultLabel}
        />
      ) : null}

      {isCalculating ? <div className="state-panel">正在根据计划勾选项重新试算税金抵扣结果...</div> : null}

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
                    <button
                      className="secondary-button compact"
                      type="button"
                      disabled={selectableInputIds.length === 0 || selectedInputIds.length === selectableInputIds.length}
                      onClick={() => setSelectedInputIds(selectableInputIds)}
                    >
                      全选
                    </button>
                    <button
                      className="secondary-button compact"
                      type="button"
                      disabled={selectedInputIds.length === 0}
                      onClick={() => setSelectedInputIds([])}
                    >
                      清空
                    </button>
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
    </div>
  );
}
