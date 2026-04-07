import { startTransition, useEffect, useMemo, useState } from "react";

import MonthPicker, { formatMonthLabel } from "../components/MonthPicker";
import CostExplorerList from "../components/cost-statistics/CostExplorerList";
import ExportCenterModal, {
  type ExportCenterMode,
  type ExportRangeMode,
} from "../components/cost-statistics/ExportCenterModal";
import CostStatisticsSummaryCards from "../components/cost-statistics/CostStatisticsSummaryCards";
import CostStatisticsTable from "../components/cost-statistics/CostStatisticsTable";
import CostTransactionDetailModal from "../components/cost-statistics/CostTransactionDetailModal";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import {
  exportCostStatisticsView,
  fetchCostStatisticsExplorer,
  fetchCostStatisticsExportPreview,
  fetchCostTransactionDetail,
  type CostExportParams,
  type PreviewCostExportParams,
} from "../features/cost-statistics/api";
import type {
  CostExpenseTypeExplorerRow,
  CostProjectExplorerRow,
  CostStatisticsExplorer,
  CostStatisticsExportPreview,
  CostTimeRow,
  CostTransactionDetail,
} from "../features/cost-statistics/types";

type CostViewMode = "time" | "project" | "expenseType";

type ProjectExpenseTypeRow = {
  expenseType: string;
  totalAmount: string;
  transactionCount: number;
  percentageLabel: string;
};

function formatCurrencyFromRows(rows: Array<{ amount: string }>) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  return total.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function groupProjectExpenseTypes(rows: CostTimeRow[]) {
  const grouped = new Map<string, { totalAmount: number; transactionCount: number }>();
  const projectTotalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  for (const row of rows) {
    const bucket = grouped.get(row.expenseType) ?? { totalAmount: 0, transactionCount: 0 };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    grouped.set(row.expenseType, bucket);
  }
  return Array.from(grouped.entries())
    .map<ProjectExpenseTypeRow>(([expenseType, bucket]) => ({
      expenseType,
      totalAmount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transactionCount: bucket.transactionCount,
      percentageLabel: `${((bucket.totalAmount / (projectTotalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function buildMonthDateBounds(month: string) {
  const [yearText, monthText] = month.split("-");
  const year = Number(yearText);
  const monthNumber = Number(monthText);
  const startDate = `${month}-01`;
  const lastDay = new Date(year, monthNumber, 0).getDate();
  const endDate = `${month}-${String(lastDay).padStart(2, "0")}`;
  return { startDate, endDate };
}

export default function CostStatisticsPage() {
  const [viewMode, setViewMode] = useState<CostViewMode>("time");
  const [scopedMonth, setScopedMonth] = useState(DEFAULT_MONTH);
  const explorerMonth = viewMode === "project" ? "all" : scopedMonth;
  const formattedScopedMonth = formatMonthLabel(scopedMonth);

  const [explorerData, setExplorerData] = useState<CostStatisticsExplorer | null>(null);
  const [exportReferenceData, setExportReferenceData] = useState<CostStatisticsExplorer | null>(null);
  const [transactionDetail, setTransactionDetail] = useState<CostTransactionDetail | null>(null);
  const [isExplorerLoading, setIsExplorerLoading] = useState(true);
  const [detailLoadingMessage, setDetailLoadingMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [isExportCenterOpen, setIsExportCenterOpen] = useState(false);
  const [exportPreview, setExportPreview] = useState<CostStatisticsExportPreview | null>(null);
  const [exportCenterMode, setExportCenterMode] = useState<ExportCenterMode>("time");

  const [timeRangeMode, setTimeRangeMode] = useState<ExportRangeMode>("month");
  const [timeMonth, setTimeMonth] = useState(DEFAULT_MONTH);
  const defaultMonthBounds = buildMonthDateBounds(DEFAULT_MONTH);
  const [timeStartDate, setTimeStartDate] = useState(defaultMonthBounds.startDate);
  const [timeEndDate, setTimeEndDate] = useState(defaultMonthBounds.endDate);

  const [projectExportNames, setProjectExportNames] = useState<string[]>([]);
  const [projectAggregateBy, setProjectAggregateBy] = useState<"month" | "year">("month");
  const [projectExpenseTypes, setProjectExpenseTypes] = useState<string[]>([]);

  const [expenseTypeRangeMode, setExpenseTypeRangeMode] = useState<ExportRangeMode>("month");
  const [expenseTypeMonth, setExpenseTypeMonth] = useState(DEFAULT_MONTH);
  const [expenseTypeStartDate, setExpenseTypeStartDate] = useState(defaultMonthBounds.startDate);
  const [expenseTypeEndDate, setExpenseTypeEndDate] = useState(defaultMonthBounds.endDate);
  const [expenseTypeSelections, setExpenseTypeSelections] = useState<string[]>([]);

  const [selectedTimeTransactionId, setSelectedTimeTransactionId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [selectedProjectExpenseType, setSelectedProjectExpenseType] = useState<string | null>(null);
  const [selectedProjectTransactionId, setSelectedProjectTransactionId] = useState<string | null>(null);
  const [selectedExpenseType, setSelectedExpenseType] = useState<string | null>(null);
  const [selectedExpenseTransactionId, setSelectedExpenseTransactionId] = useState<string | null>(null);

  function resetDetailSelection() {
    setTransactionDetail(null);
    setSelectedTimeTransactionId(null);
    setSelectedProjectTransactionId(null);
    setSelectedExpenseTransactionId(null);
  }

  useEffect(() => {
    const controller = new AbortController();

    async function loadExplorer() {
      setIsExplorerLoading(true);
      setLoadError(null);
      setExportFeedback(null);
      setExplorerData(null);
      setSelectedProjectName(null);
      setSelectedProjectExpenseType(null);
      setSelectedExpenseType(null);
      resetDetailSelection();
      try {
        const payload = await fetchCostStatisticsExplorer(explorerMonth, controller.signal);
        if (!controller.signal.aborted) {
          setExplorerData(payload);
        }
      } catch {
        if (!controller.signal.aborted) {
          setLoadError("成本统计数据加载失败，请稍后重试。");
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsExplorerLoading(false);
        }
      }
    }

    void loadExplorer();
    return () => controller.abort();
  }, [explorerMonth]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadExportReferenceData() {
      try {
        const payload = await fetchCostStatisticsExplorer("all", controller.signal);
        if (!controller.signal.aborted) {
          setExportReferenceData(payload);
        }
      } catch {
        if (!controller.signal.aborted) {
          setExportReferenceData(null);
        }
      }
    }

    void loadExportReferenceData();
    return () => controller.abort();
  }, []);

  const timeRows = explorerData?.timeRows ?? [];
  const projectRows = explorerData?.projectRows ?? [];
  const expenseTypeRows = explorerData?.expenseTypeRows ?? [];

  const selectedProjectRows = useMemo(
    () => timeRows.filter((row) => row.projectName === selectedProjectName),
    [selectedProjectName, timeRows],
  );
  const projectExpenseTypeRows = useMemo(() => groupProjectExpenseTypes(selectedProjectRows), [selectedProjectRows]);
  const selectedProjectTransactionRows = useMemo(
    () =>
      selectedProjectExpenseType
        ? selectedProjectRows.filter((row) => row.expenseType === selectedProjectExpenseType)
        : [],
    [selectedProjectExpenseType, selectedProjectRows],
  );
  const selectedExpenseTypeRows = useMemo(
    () => timeRows.filter((row) => row.expenseType === selectedExpenseType),
    [selectedExpenseType, timeRows],
  );

  const exportProjectOptions = useMemo(
    () => (exportReferenceData?.projectRows ?? []).map((row) => row.projectName),
    [exportReferenceData],
  );
  const allExpenseTypeOptions = useMemo(
    () => (exportReferenceData?.expenseTypeRows ?? []).map((row) => row.expenseType),
    [exportReferenceData],
  );

  const projectExpenseTypeOptions = useMemo(() => {
    if (projectExportNames.length === 0) {
      return [];
    }
    const rows = exportReferenceData?.timeRows ?? [];
    return Array.from(
      new Set(rows.filter((row) => projectExportNames.includes(row.projectName)).map((row) => row.expenseType)),
    ).sort((left, right) => left.localeCompare(right, "zh-CN"));
  }, [exportReferenceData, projectExportNames]);

  const isRootEmpty = !isExplorerLoading && !loadError && explorerData ? explorerData.timeRows.length === 0 : false;

  async function openTransactionDetail(row: CostTimeRow, source: "time" | "project" | "expenseType") {
    setLoadError(null);
    setExportFeedback(null);
    setDetailLoadingMessage(`正在加载流水 ${row.transactionId} 的详情...`);
    if (source === "time") {
      setSelectedTimeTransactionId(row.transactionId);
    }
    if (source === "project") {
      setSelectedProjectTransactionId(row.transactionId);
    }
    if (source === "expenseType") {
      setSelectedExpenseTransactionId(row.transactionId);
    }
    try {
      const payload = await fetchCostTransactionDetail(row.transactionId);
      setTransactionDetail(payload);
    } catch {
      setLoadError("流水详情加载失败，请稍后重试。");
    } finally {
      setDetailLoadingMessage(null);
    }
  }

  function handleViewModeChange(nextViewMode: CostViewMode) {
    setLoadError(null);
    setExportFeedback(null);
    resetDetailSelection();
    startTransition(() => {
      setViewMode(nextViewMode);
    });
  }

  const activeSummary = useMemo(() => {
    if (!explorerData) {
      return {
        rowLabel: "条目数",
        rowCount: 0,
        transactionCount: 0,
        totalAmount: "0.00",
      };
    }
    if (viewMode === "project") {
      if (selectedProjectName && selectedProjectExpenseType) {
        return {
          rowLabel: "该类型流水",
          rowCount: selectedProjectTransactionRows.length,
          transactionCount: selectedProjectTransactionRows.length,
          totalAmount: formatCurrencyFromRows(selectedProjectTransactionRows),
        };
      }
      if (selectedProjectName) {
        return {
          rowLabel: "费用类型",
          rowCount: projectExpenseTypeRows.length,
          transactionCount: selectedProjectRows.length,
          totalAmount: formatCurrencyFromRows(selectedProjectRows),
        };
      }
      return {
        rowLabel: "项目数",
        rowCount: projectRows.length,
        transactionCount: explorerData.summary.transactionCount,
        totalAmount: explorerData.summary.totalAmount,
      };
    }
    if (viewMode === "expenseType") {
      if (selectedExpenseType) {
        return {
          rowLabel: "该类型流水",
          rowCount: selectedExpenseTypeRows.length,
          transactionCount: selectedExpenseTypeRows.length,
          totalAmount: formatCurrencyFromRows(selectedExpenseTypeRows),
        };
      }
      return {
        rowLabel: "费用类型数",
        rowCount: expenseTypeRows.length,
        transactionCount: explorerData.summary.transactionCount,
        totalAmount: explorerData.summary.totalAmount,
      };
    }
    return {
      rowLabel: "时间流水",
      rowCount: explorerData.summary.rowCount,
      transactionCount: explorerData.summary.transactionCount,
      totalAmount: explorerData.summary.totalAmount,
    };
  }, [
    explorerData,
    expenseTypeRows.length,
    projectExpenseTypeRows.length,
    projectRows.length,
    selectedExpenseType,
    selectedExpenseTypeRows,
    selectedProjectExpenseType,
    selectedProjectName,
    selectedProjectRows,
    selectedProjectTransactionRows,
    viewMode,
  ]);

  function updateProjectExportSelection(projectNames: string[]) {
    setProjectExportNames(projectNames);
    const nextExpenseTypes = Array.from(
      new Set(
        (exportReferenceData?.timeRows ?? [])
          .filter((row) => projectNames.includes(row.projectName))
          .map((row) => row.expenseType),
      ),
    ).sort((left, right) => left.localeCompare(right, "zh-CN"));
    setProjectExpenseTypes(nextExpenseTypes);
  }

  function openExportCenter() {
    setExportFeedback(null);
    setExportPreview(null);
    if (viewMode === "project") {
      setExportCenterMode("project");
      const nextProjectNames =
        projectExportNames.length > 0
          ? projectExportNames
          : selectedProjectName
            ? [selectedProjectName]
            : exportProjectOptions.slice(0, 1);
      updateProjectExportSelection(nextProjectNames);
    } else if (viewMode === "expenseType") {
      setExportCenterMode("expense_type");
      setExpenseTypeRangeMode("month");
      setExpenseTypeMonth(scopedMonth);
      const bounds = buildMonthDateBounds(scopedMonth);
      setExpenseTypeStartDate(bounds.startDate);
      setExpenseTypeEndDate(bounds.endDate);
      setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
    } else {
      setExportCenterMode("time");
      setTimeRangeMode("month");
      setTimeMonth(scopedMonth);
      const bounds = buildMonthDateBounds(scopedMonth);
      setTimeStartDate(bounds.startDate);
      setTimeEndDate(bounds.endDate);
    }
    setIsExportCenterOpen(true);
  }

  function buildExportParamsFromState(): CostExportParams | null {
    if (exportCenterMode === "time") {
      if (timeRangeMode === "month") {
        return {
          month: timeMonth,
          view: "time",
        };
      }
      return {
        month: "all",
        view: "time",
        startDate: timeStartDate <= timeEndDate ? timeStartDate : timeEndDate,
        endDate: timeStartDate <= timeEndDate ? timeEndDate : timeStartDate,
      };
    }

    if (exportCenterMode === "project") {
      if (projectExportNames.length === 0 || projectExpenseTypes.length === 0) {
        return null;
      }
      return {
        month: "all",
        view: "project",
        projectNames: projectExportNames,
        aggregateBy: projectAggregateBy,
        expenseTypes: projectExpenseTypes,
        includeOaDetails: true,
        includeInvoiceDetails: true,
        includeExceptionRows: true,
        includeIgnoredRows: true,
        includeExpenseContentSummary: true,
        sortBy: "time",
      };
    }

    if (expenseTypeSelections.length === 0) {
      return null;
    }
    if (expenseTypeRangeMode === "month") {
      return {
        month: expenseTypeMonth,
        view: "expense_type",
        expenseTypes: expenseTypeSelections,
      };
    }
    return {
      month: "all",
      view: "expense_type",
      expenseTypes: expenseTypeSelections,
      startDate: expenseTypeStartDate <= expenseTypeEndDate ? expenseTypeStartDate : expenseTypeEndDate,
      endDate: expenseTypeStartDate <= expenseTypeEndDate ? expenseTypeEndDate : expenseTypeStartDate,
    };
  }

  function buildPreviewParamsFromState(): PreviewCostExportParams | null {
    const params = buildExportParamsFromState();
    if (!params) {
      return null;
    }
    if (params.view === "transaction" || params.view === "month") {
      return null;
    }
    return params;
  }

  async function runExport(params: CostExportParams) {
    setDetailLoadingMessage(null);
    setLoadError(null);
    setExportFeedback(null);
    setIsExporting(true);
    try {
      const { blob, fileName } = await exportCostStatisticsView(params);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = fileName;
      document.body.appendChild(link);
      const isJsdom =
        typeof navigator !== "undefined" && typeof navigator.userAgent === "string" && navigator.userAgent.includes("jsdom");
      if (!isJsdom) {
        link.click();
      }
      link.remove();
      if (isJsdom) {
        URL.revokeObjectURL(objectUrl);
      } else {
        window.setTimeout(() => {
          URL.revokeObjectURL(objectUrl);
        }, 1000);
      }
      setExportFeedback({
        tone: "success",
        message: `已导出 ${fileName}`,
      });
    } catch {
      setExportFeedback({
        tone: "error",
        message: "成本统计导出失败，请稍后重试。",
      });
    } finally {
      setIsExporting(false);
    }
  }

  async function handleExportPreview() {
    const params = buildPreviewParamsFromState();
    if (!params) {
      setExportFeedback({
        tone: "error",
        message: "请先补全导出筛选条件。",
      });
      return;
    }
    setExportFeedback(null);
    setIsPreviewLoading(true);
    try {
      const payload = await fetchCostStatisticsExportPreview(params);
      setExportPreview(payload);
    } catch {
      setExportFeedback({
        tone: "error",
        message: "导出预览加载失败，请稍后重试。",
      });
    } finally {
      setIsPreviewLoading(false);
    }
  }

  async function handleExportFromCenter() {
    const params = buildExportParamsFromState();
    if (!params) {
      setExportFeedback({
        tone: "error",
        message: "请先补全导出筛选条件。",
      });
      return;
    }
    await runExport(params);
  }

  const timeColumns = [
    { key: "tradeTime", header: "时间", render: (row: CostTimeRow) => row.tradeTime },
    { key: "projectName", header: "项目名", render: (row: CostTimeRow) => row.projectName },
    { key: "expenseType", header: "费用类型", render: (row: CostTimeRow) => row.expenseType },
    {
      key: "amount",
      header: "金额",
      cellClassName: "cost-table-cell-money",
      render: (row: CostTimeRow) => ({
        amount: row.amount,
        direction: row.direction,
        paymentAccountLabel: row.paymentAccountLabel,
      }),
    },
    { key: "expenseContent", header: "费用内容", render: (row: CostTimeRow) => row.expenseContent },
  ];

  const transactionColumns = [
    { key: "tradeTime", header: "时间", render: (row: CostTimeRow) => row.tradeTime },
    viewMode === "expenseType"
      ? { key: "projectName", header: "项目名", render: (row: CostTimeRow) => row.projectName }
      : { key: "counterpartyName", header: "对方户名", render: (row: CostTimeRow) => row.counterpartyName },
    {
      key: "amount",
      header: "金额",
      cellClassName: "cost-table-cell-money",
      render: (row: CostTimeRow) => ({
        amount: row.amount,
        direction: row.direction,
        paymentAccountLabel: row.paymentAccountLabel,
      }),
    },
    { key: "expenseContent", header: "费用内容", render: (row: CostTimeRow) => row.expenseContent },
  ];

  const activeTransactionId = selectedTimeTransactionId ?? selectedProjectTransactionId ?? selectedExpenseTransactionId;
  const isExportActionBusy = isExporting || isPreviewLoading || Boolean(detailLoadingMessage);

  return (
    <div className="page-stack cost-page">
      <header className="page-header">
        <div>
          <h1>成本统计</h1>
          <p>以已配对的支出流水为基准，按时间、项目和费用类型查看项目成本，并逐条下钻到具体流水。</p>
        </div>
        <div className="page-header-actions cost-header-actions">
          <button
            className="cost-export-button"
            type="button"
            disabled={isExplorerLoading || Boolean(detailLoadingMessage)}
            onClick={openExportCenter}
          >
            导出中心
          </button>
        </div>
      </header>

      <CostStatisticsSummaryCards
        rowLabel={activeSummary.rowLabel}
        rowCount={activeSummary.rowCount}
        transactionCount={activeSummary.transactionCount}
        totalAmount={activeSummary.totalAmount}
      />

      <section className="cost-content-shell">
        <div className="cost-analysis-toolbar">
          <div className="cost-view-switcher" role="tablist" aria-label="成本统计视图切换">
            <button
              className={viewMode === "time" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("time")}
            >
              按时间
            </button>
            <button
              className={viewMode === "project" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("project")}
            >
              按项目
            </button>
            <button
              className={viewMode === "expenseType" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("expenseType")}
            >
              按费用类型
            </button>
          </div>
          <div className="cost-toolbar-meta">
            {viewMode === "time" ? <strong>默认按时间查看 {formattedScopedMonth} 的全部支出流水</strong> : null}
            {viewMode === "project" ? <strong>从左到右依次展开：项目名 / 费用类型 / 流水，且不受年月限制</strong> : null}
            {viewMode === "expenseType" ? <strong>按费用类型查看 {formattedScopedMonth} 的对应流水</strong> : null}
          </div>
        </div>

        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {isExplorerLoading ? (
          <div className="state-panel">
            正在加载{viewMode === "project" ? "全部期间" : ` ${scopedMonth} `}的成本统计数据...
          </div>
        ) : null}
        {detailLoadingMessage ? <div className="state-panel">{detailLoadingMessage}</div> : null}
        {exportFeedback && !isExportCenterOpen ? (
          <div className={`action-feedback ${exportFeedback.tone}`}>{exportFeedback.message}</div>
        ) : null}
        {isRootEmpty ? (
          <div className="state-panel">
            {viewMode === "project" ? "当前没有可用于项目成本统计的支出流水。" : "当前月份没有可用于成本统计的支出流水。"}
          </div>
        ) : null}

        {!isExplorerLoading && !loadError && explorerData && explorerData.timeRows.length > 0 ? (
          <>
            {viewMode === "time" ? (
              <div className="cost-analysis-layout time-layout single-column">
                <section className="cost-table-section">
                  <div className="cost-section-heading">
                    <div className="cost-section-heading-copy">
                      <h2>按时间统计</h2>
                      <span>{timeRows.length} 条</span>
                    </div>
                    <div className="cost-section-heading-actions">
                      <MonthPicker value={scopedMonth} onChange={setScopedMonth} />
                    </div>
                  </div>
                  <CostStatisticsTable
                    ariaLabel="按时间统计表"
                    columns={timeColumns}
                    rows={timeRows}
                    getRowKey={(row) => row.transactionId}
                    onRowClick={(row) => void openTransactionDetail(row, "time")}
                    getRowActionLabel={(row) => `查看流水 ${row.transactionId}`}
                  />
                </section>
              </div>
            ) : null}

            {viewMode === "project" ? (
              <div className="cost-analysis-layout explorer-layout">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按项目统计</h2>
                    <span>全部期间</span>
                  </div>
                </div>
                <div className="cost-explorer-grid project">
                  <CostExplorerList<CostProjectExplorerRow>
                    title="项目名"
                    count={projectRows.length}
                    items={projectRows}
                    emptyLabel="当前月份没有项目成本。"
                    getKey={(row) => row.projectName}
                    isActive={(row) => row.projectName === selectedProjectName}
                    onSelect={(row) => {
                      setSelectedProjectName(row.projectName);
                      setSelectedProjectExpenseType(null);
                      setSelectedProjectTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.projectName}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.expenseTypeCount} 类费用`}
                    renderMeta={(row) => row.totalAmount}
                  />
                  <CostExplorerList<ProjectExpenseTypeRow>
                    title="费用类型"
                    count={projectExpenseTypeRows.length}
                    items={projectExpenseTypeRows}
                    emptyLabel={selectedProjectName ? "该项目下暂无费用类型。" : "请先在左侧选择项目。"}
                    getKey={(row) => row.expenseType}
                    isActive={(row) => row.expenseType === selectedProjectExpenseType}
                    onSelect={(row) => {
                      setSelectedProjectExpenseType(row.expenseType);
                      setSelectedProjectTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.expenseType}
                    renderSecondary={(row) => `${row.transactionCount} 条流水`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <span>{row.totalAmount}</span>
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{selectedProjectTransactionRows.length}</span>
                    </header>
                    {selectedProjectName && selectedProjectExpenseType ? (
                      <CostStatisticsTable
                        ariaLabel="项目对应流水表"
                        columns={transactionColumns}
                        rows={selectedProjectTransactionRows}
                        getRowKey={(row) => row.transactionId}
                        onRowClick={(row) => void openTransactionDetail(row, "project")}
                        getRowActionLabel={(row) => `查看流水 ${row.transactionId}`}
                        emptyLabel="该费用类型下暂无流水。"
                      />
                    ) : (
                      <div className="cost-explorer-empty">请先依次选择项目和费用类型。</div>
                    )}
                  </section>
                </div>
              </div>
            ) : null}

            {viewMode === "expenseType" ? (
              <div className="cost-analysis-layout explorer-layout expense-layout">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按费用类型统计</h2>
                    <span>{expenseTypeRows.length} 类</span>
                  </div>
                  <div className="cost-section-heading-actions">
                    <MonthPicker value={scopedMonth} onChange={setScopedMonth} />
                  </div>
                </div>
                <div className="cost-explorer-grid expense">
                  <CostExplorerList<CostExpenseTypeExplorerRow>
                    title="费用类型"
                    count={expenseTypeRows.length}
                    items={expenseTypeRows}
                    emptyLabel="当前月份没有费用类型数据。"
                    getKey={(row) => row.expenseType}
                    isActive={(row) => row.expenseType === selectedExpenseType}
                    onSelect={(row) => {
                      setSelectedExpenseType(row.expenseType);
                      setSelectedExpenseTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.expenseType}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.projectCount} 个项目`}
                    renderMeta={(row) => row.totalAmount}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{selectedExpenseTypeRows.length}</span>
                    </header>
                    {selectedExpenseType ? (
                      <CostStatisticsTable
                        ariaLabel="按费用类型流水表"
                        columns={transactionColumns}
                        rows={selectedExpenseTypeRows}
                        getRowKey={(row) => row.transactionId}
                        onRowClick={(row) => void openTransactionDetail(row, "expenseType")}
                        getRowActionLabel={(row) => `查看流水 ${row.transactionId}`}
                        emptyLabel="该费用类型下暂无流水。"
                      />
                    ) : (
                      <div className="cost-explorer-empty">请先在左侧选择费用类型。</div>
                    )}
                  </section>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      {transactionDetail && activeTransactionId ? (
        <CostTransactionDetailModal
          detail={transactionDetail.transaction}
          onClose={() => {
            resetDetailSelection();
            setTransactionDetail(null);
          }}
        />
      ) : null}

      {isExportCenterOpen ? (
        <ExportCenterModal
          mode={exportCenterMode}
          projectOptions={exportProjectOptions}
          expenseTypeOptions={exportCenterMode === "project" ? projectExpenseTypeOptions : allExpenseTypeOptions}
          timeRangeMode={timeRangeMode}
          timeMonth={timeMonth}
          timeStartDate={timeStartDate}
          timeEndDate={timeEndDate}
          projectNames={projectExportNames}
          projectAggregateBy={projectAggregateBy}
          projectExpenseTypes={projectExpenseTypes}
          expenseTypeRangeMode={expenseTypeRangeMode}
          expenseTypeMonth={expenseTypeMonth}
          expenseTypeStartDate={expenseTypeStartDate}
          expenseTypeEndDate={expenseTypeEndDate}
          expenseTypeSelections={expenseTypeSelections}
          preview={exportPreview}
          feedback={exportFeedback}
          isPreviewLoading={isPreviewLoading}
          isExporting={isExporting}
          isBusy={isExportActionBusy}
          onClose={() => setIsExportCenterOpen(false)}
          onModeChange={(mode) => {
            setExportCenterMode(mode);
            setExportPreview(null);
            if (mode === "project") {
              const nextProjectNames =
                projectExportNames.length > 0
                  ? projectExportNames
                  : selectedProjectName
                    ? [selectedProjectName]
                    : exportProjectOptions.slice(0, 1);
              updateProjectExportSelection(nextProjectNames);
            }
            if (mode === "expense_type" && expenseTypeSelections.length === 0) {
              setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
            }
          }}
          onTimeRangeModeChange={(mode) => {
            setTimeRangeMode(mode);
            setExportPreview(null);
          }}
          onTimeMonthChange={(month) => {
            setTimeMonth(month);
            setExportPreview(null);
          }}
          onTimeStartDateChange={(date) => {
            setTimeStartDate(date);
            setExportPreview(null);
          }}
          onTimeEndDateChange={(date) => {
            setTimeEndDate(date);
            setExportPreview(null);
          }}
          onProjectNamesChange={(projectNames) => {
            updateProjectExportSelection(projectNames);
            setExportPreview(null);
          }}
          onProjectAggregateByChange={(aggregateBy) => {
            setProjectAggregateBy(aggregateBy);
            setExportPreview(null);
          }}
          onProjectExpenseTypesChange={(expenseTypes) => {
            setProjectExpenseTypes(expenseTypes);
            setExportPreview(null);
          }}
          onExpenseTypeRangeModeChange={(mode) => {
            setExpenseTypeRangeMode(mode);
            setExportPreview(null);
          }}
          onExpenseTypeMonthChange={(month) => {
            setExpenseTypeMonth(month);
            setExportPreview(null);
          }}
          onExpenseTypeStartDateChange={(date) => {
            setExpenseTypeStartDate(date);
            setExportPreview(null);
          }}
          onExpenseTypeEndDateChange={(date) => {
            setExpenseTypeEndDate(date);
            setExportPreview(null);
          }}
          onExpenseTypeSelectionsChange={(expenseTypes) => {
            setExpenseTypeSelections(expenseTypes);
            setExportPreview(null);
          }}
          onPreview={() => void handleExportPreview()}
          onExport={() => void handleExportFromCenter()}
        />
      ) : null}
    </div>
  );
}
