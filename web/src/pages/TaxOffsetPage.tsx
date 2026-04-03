import { useCallback, useEffect, useState } from "react";

import CertifiedInvoiceImportModal from "../components/tax/CertifiedInvoiceImportModal";
import CertifiedResultsDrawer from "../components/tax/CertifiedResultsDrawer";
import MonthPicker from "../components/MonthPicker";
import TaxResultPanel from "../components/tax/TaxResultPanel";
import TaxSummaryCards from "../components/tax/TaxSummaryCards";
import TaxTable from "../components/tax/TaxTable";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { calculateTaxOffset, fetchTaxOffsetMonth } from "../features/tax/api";
import type { TaxMonthData, TaxSummary } from "../features/tax/types";

function toggleSelection(currentIds: string[], id: string) {
  return currentIds.includes(id) ? currentIds.filter((currentId) => currentId !== id) : [...currentIds, id];
}

export default function TaxOffsetPage() {
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

  const isEmpty = !isLoading && !loadError && monthData
    ? monthData.outputInvoices.length === 0
      && monthData.inputPlanInvoices.length === 0
      && monthData.certifiedMatchedInvoices.length === 0
      && monthData.certifiedOutsidePlanInvoices.length === 0
    : false;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>税金抵扣计划与试算</h1>
          <p>围绕进项票认证计划与已认证结果，做本月税金抵扣试算与展示，不承担真实税务业务动作。</p>
        </div>
        <div className="page-header-actions">
          <button className="secondary-button" type="button" onClick={() => setIsCertifiedImportModalOpen(true)}>
            已认证发票导入
          </button>
          <MonthPicker value={currentMonth} onChange={setCurrentMonth} />
        </div>
      </header>

      {loadError ? <div className="state-panel error">{loadError}</div> : null}
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
          <div className="tax-layout">
            <TaxTable
              selectable={false}
              title="销项票开票情况"
              rows={monthData.outputInvoices}
              selectedIds={[]}
            />
            <TaxTable
              highlightedRowId={highlightedPlanInputId}
              title="进项票认证计划"
              rows={monthData.inputPlanInvoices}
              selectedIds={selectedInputIds}
              onToggleRow={(id) => setSelectedInputIds((currentIds) => toggleSelection(currentIds, id))}
            />
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
        <CertifiedInvoiceImportModal onClose={() => setIsCertifiedImportModalOpen(false)} />
      ) : null}
    </div>
  );
}
