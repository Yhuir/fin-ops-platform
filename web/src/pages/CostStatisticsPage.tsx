import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";

import MonthPicker, { formatMonthLabel } from "../components/MonthPicker";
import CostExplorerList from "../components/cost-statistics/CostExplorerList";
import ExportCenterModal, {
  type ExportCenterMode,
  type ExportRangeMode,
} from "../components/cost-statistics/ExportCenterModal";
import CostStatisticsSummaryCards from "../components/cost-statistics/CostStatisticsSummaryCards";
import CostStatisticsTable, {
  type CostStatisticsTableColumn,
} from "../components/cost-statistics/CostStatisticsTable";
import CostTransactionDetailModal from "../components/cost-statistics/CostTransactionDetailModal";
import { useAppChrome } from "../contexts/AppChromeContext";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  exportCostStatisticsView,
  fetchCostStatisticsExplorer,
  fetchCostStatisticsExportPreview,
  fetchCostTransactionDetail,
  getCachedCostStatisticsExplorer,
  type CostExportParams,
  type PreviewCostExportParams,
} from "../features/cost-statistics/api";
import { importWorkflowPath } from "../features/imports/importRoutes";
import type {
  CostExpenseTypeExplorerRow,
  CostProjectScope,
  CostProjectExplorerRow,
  CostStatisticsExplorer,
  CostStatisticsExportPreview,
  CostTimeRow,
  CostTransactionDetail,
} from "../features/cost-statistics/types";

type CostViewMode = "time" | "project" | "bank" | "expenseType";
type RangeScopeMode = "all" | "year" | "month";
type ExplorerScopeMode = RangeScopeMode | "custom";
type ScopePickerPanel = Exclude<ExplorerScopeMode, "all">;

type CostStatisticsPageSession = {
  viewMode: CostViewMode;
  costProjectScope: CostProjectScope;
  timeScopeMode: ExplorerScopeMode;
  timeScopeYear: string;
  timeScopeMonth: string;
  timeScopeStartDate: string;
  timeScopeEndDate: string;
  projectScopeMode: ExplorerScopeMode;
  projectScopeYear: string;
  projectScopeMonth: string;
  projectScopeStartDate: string;
  projectScopeEndDate: string;
  bankScopeMode: ExplorerScopeMode;
  bankScopeYear: string;
  bankScopeMonth: string;
  bankScopeStartDate: string;
  bankScopeEndDate: string;
  expenseTypeScopeMode: ExplorerScopeMode;
  expenseTypeScopeYear: string;
  expenseTypeScopeMonth: string;
  expenseTypeScopeStartDate: string;
  expenseTypeScopeEndDate: string;
};

type ProjectExpenseTypeRow = {
  expenseType: string;
  totalAmount: string;
  transactionCount: number;
  percentageLabel: string;
};

type ExpenseTypeExplorerDisplayRow = CostExpenseTypeExplorerRow & {
  percentageLabel: string;
};

type CostBankExplorerRow = {
  paymentAccountLabel: string;
  totalAmount: string;
  transactionCount: number;
  projectCount: number;
  percentageLabel: string;
};

type ScopeYearPickerProps = {
  ariaLabel: string;
  years: string[];
  value: string;
  onChange: (year: string) => void;
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

function normalizeDateRange(startDate: string, endDate: string) {
  return startDate <= endDate ? { startDate, endDate } : { startDate: endDate, endDate: startDate };
}

function formatScopeButtonLabel(baseLabel: string, isActive: boolean, selectedLabel: string | null = null) {
  return isActive && selectedLabel ? `${baseLabel} ${selectedLabel}` : baseLabel;
}

function buildProjectRowsFromTimeRows(rows: CostTimeRow[]) {
  const grouped = new Map<string, { totalAmount: number; transactionCount: number; expenseTypes: Set<string> }>();
  const totalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);

  for (const row of rows) {
    const bucket = grouped.get(row.projectName) ?? {
      totalAmount: 0,
      transactionCount: 0,
      expenseTypes: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.expenseTypes.add(row.expenseType);
    grouped.set(row.projectName, bucket);
  }

  return Array.from(grouped.entries())
    .map<CostProjectExplorerRow>(([projectName, bucket]) => ({
      projectName,
      totalAmount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transactionCount: bucket.transactionCount,
      expenseTypeCount: bucket.expenseTypes.size,
      percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function buildBankRowsFromTimeRows(rows: CostTimeRow[]) {
  const grouped = new Map<
    string,
    { totalAmount: number; transactionCount: number; projects: Set<string> }
  >();
  const totalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);

  for (const row of rows) {
    const bucket = grouped.get(row.paymentAccountLabel) ?? {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.projects.add(row.projectName);
    grouped.set(row.paymentAccountLabel, bucket);
  }

  return Array.from(grouped.entries())
    .map<CostBankExplorerRow>(([paymentAccountLabel, bucket]) => ({
      paymentAccountLabel,
      totalAmount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transactionCount: bucket.transactionCount,
      projectCount: bucket.projects.size,
      percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function filterScopeTimeRows(
  rows: CostTimeRow[],
  mode: ExplorerScopeMode,
  year: string,
  month: string,
  startDate: string,
  endDate: string,
) {
  if (mode === "all") {
    return rows;
  }
  if (mode === "year") {
    return rows.filter((row) => row.tradeTime.startsWith(`${year}-`));
  }
  if (mode === "month") {
    return rows.filter((row) => row.tradeTime.startsWith(month));
  }
  const range = normalizeDateRange(startDate, endDate);
  return rows.filter((row) => {
    const tradeDate = row.tradeTime.slice(0, 10);
    return tradeDate >= range.startDate && tradeDate <= range.endDate;
  });
}

function getExplorerRowsDateRange(rows: CostTimeRow[]) {
  const dates = rows
    .map((row) => row.tradeTime.slice(0, 10))
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value))
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
  if (dates.length === 0) {
    return buildMonthDateBounds(DEFAULT_MONTH);
  }
  return {
    startDate: dates[0],
    endDate: dates[dates.length - 1],
  };
}

function getScopeDateRange(
  rows: CostTimeRow[],
  mode: ExplorerScopeMode,
  year: string,
  month: string,
  startDate: string,
  endDate: string,
) {
  if (mode === "month") {
    return buildMonthDateBounds(month);
  }
  if (mode === "year") {
    return {
      startDate: `${year}-01-01`,
      endDate: `${year}-12-31`,
    };
  }
  if (mode === "custom") {
    return normalizeDateRange(startDate, endDate);
  }
  return getExplorerRowsDateRange(rows);
}

function buildExpenseTypeRowsFromTimeRows(rows: CostTimeRow[]) {
  const grouped = new Map<string, { totalAmount: number; transactionCount: number; projects: Set<string> }>();
  const totalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);

  for (const row of rows) {
    const bucket = grouped.get(row.expenseType) ?? {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.projects.add(row.projectName);
    grouped.set(row.expenseType, bucket);
  }

  return Array.from(grouped.entries())
    .map<ExpenseTypeExplorerDisplayRow>(([expenseType, bucket]) => ({
      expenseType,
      totalAmount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transactionCount: bucket.transactionCount,
      projectCount: bucket.projects.size,
      percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function ScopeYearPicker({ ariaLabel, years, value, onChange }: ScopeYearPickerProps) {
  return (
    <div aria-label={ariaLabel} className="cost-year-picker-panel" role="group">
      <div className="cost-year-picker-title">年份</div>
      <div className="cost-year-picker-grid">
        {years.map((year) => (
          <button
            key={year}
            aria-pressed={year === value}
            className={year === value ? "cost-year-picker-chip active" : "cost-year-picker-chip"}
            type="button"
            onClick={() => onChange(year)}
          >
            {year}年
          </button>
        ))}
      </div>
    </div>
  );
}

function isCostStatisticsPageSession(value: unknown): value is CostStatisticsPageSession {
  if (!value || typeof value !== "object") {
    return false;
  }
  const session = value as Record<string, unknown>;
  return [
    "viewMode",
    "costProjectScope",
    "timeScopeMode",
    "timeScopeYear",
    "timeScopeMonth",
    "timeScopeStartDate",
    "timeScopeEndDate",
    "projectScopeMode",
    "projectScopeYear",
    "projectScopeMonth",
    "projectScopeStartDate",
    "projectScopeEndDate",
    "bankScopeMode",
    "bankScopeYear",
    "bankScopeMonth",
    "bankScopeStartDate",
    "bankScopeEndDate",
    "expenseTypeScopeMode",
    "expenseTypeScopeYear",
    "expenseTypeScopeMonth",
    "expenseTypeScopeStartDate",
    "expenseTypeScopeEndDate",
  ].every((key) => typeof session[key] === "string");
}

export default function CostStatisticsPage() {
  const navigate = useNavigate();
  const { setWorkbenchHeaderActions } = useAppChrome();
  const { canMutateData } = useSessionPermissions();
  const defaultMonthBounds = buildMonthDateBounds(DEFAULT_MONTH);
  const costPageSession = usePageSessionState<CostStatisticsPageSession>({
    pageKey: "cost-statistics",
    stateKey: "explorerState",
    version: 1,
    initialValue: {
      viewMode: "time",
      costProjectScope: "active",
      timeScopeMode: "month",
      timeScopeYear: DEFAULT_MONTH.slice(0, 4),
      timeScopeMonth: DEFAULT_MONTH,
      timeScopeStartDate: defaultMonthBounds.startDate,
      timeScopeEndDate: defaultMonthBounds.endDate,
      projectScopeMode: "all",
      projectScopeYear: DEFAULT_MONTH.slice(0, 4),
      projectScopeMonth: DEFAULT_MONTH,
      projectScopeStartDate: defaultMonthBounds.startDate,
      projectScopeEndDate: defaultMonthBounds.endDate,
      bankScopeMode: "all",
      bankScopeYear: DEFAULT_MONTH.slice(0, 4),
      bankScopeMonth: DEFAULT_MONTH,
      bankScopeStartDate: defaultMonthBounds.startDate,
      bankScopeEndDate: defaultMonthBounds.endDate,
      expenseTypeScopeMode: "month",
      expenseTypeScopeYear: DEFAULT_MONTH.slice(0, 4),
      expenseTypeScopeMonth: DEFAULT_MONTH,
      expenseTypeScopeStartDate: defaultMonthBounds.startDate,
      expenseTypeScopeEndDate: defaultMonthBounds.endDate,
    },
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    validate: isCostStatisticsPageSession,
  });
  const setCostSessionField = useCallback(<Key extends keyof CostStatisticsPageSession>(
    key: Key,
    value: SetStateAction<CostStatisticsPageSession[Key]>,
  ) => {
    costPageSession.setValue((current) => ({
      ...current,
      [key]: typeof value === "function"
        ? (value as (currentValue: CostStatisticsPageSession[Key]) => CostStatisticsPageSession[Key])(current[key])
        : value,
    }));
  }, [costPageSession]);
  const { value: costSession } = costPageSession;
  const viewMode = costSession.viewMode;
  const setViewMode = (value: SetStateAction<CostViewMode>) => setCostSessionField("viewMode", value);
  const costProjectScope = costSession.costProjectScope;
  const setCostProjectScope = (value: SetStateAction<CostProjectScope>) => setCostSessionField("costProjectScope", value);
  const timeScopeMode = costSession.timeScopeMode;
  const setTimeScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("timeScopeMode", value);
  const [timeScopePanel, setTimeScopePanel] = useState<ScopePickerPanel | null>("month");
  const timeScopeYear = costSession.timeScopeYear;
  const setTimeScopeYear = (value: SetStateAction<string>) => setCostSessionField("timeScopeYear", value);
  const timeScopeMonth = costSession.timeScopeMonth;
  const setTimeScopeMonth = (value: SetStateAction<string>) => setCostSessionField("timeScopeMonth", value);
  const timeScopeStartDate = costSession.timeScopeStartDate;
  const setTimeScopeStartDate = (value: SetStateAction<string>) => setCostSessionField("timeScopeStartDate", value);
  const timeScopeEndDate = costSession.timeScopeEndDate;
  const setTimeScopeEndDate = (value: SetStateAction<string>) => setCostSessionField("timeScopeEndDate", value);

  const [explorerData, setExplorerData] = useState<CostStatisticsExplorer | null>(() =>
    getCachedCostStatisticsExplorer(DEFAULT_MONTH, "active"),
  );
  const [exportReferenceData, setExportReferenceData] = useState<CostStatisticsExplorer | null>(() =>
    getCachedCostStatisticsExplorer("all", "active"),
  );
  const [transactionDetail, setTransactionDetail] = useState<CostTransactionDetail | null>(null);
  const [isExplorerLoading, setIsExplorerLoading] = useState(true);
  const [isExplorerRefreshing, setIsExplorerRefreshing] = useState(false);
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
  const [timeStartDate, setTimeStartDate] = useState(defaultMonthBounds.startDate);
  const [timeEndDate, setTimeEndDate] = useState(defaultMonthBounds.endDate);

  const [projectExportNames, setProjectExportNames] = useState<string[]>([]);
  const [projectAggregateBy, setProjectAggregateBy] = useState<"month" | "year">("month");
  const [projectExpenseTypes, setProjectExpenseTypes] = useState<string[]>([]);
  const projectScopeMode = costSession.projectScopeMode;
  const setProjectScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("projectScopeMode", value);
  const [projectScopePanel, setProjectScopePanel] = useState<ScopePickerPanel | null>(null);
  const projectScopeYear = costSession.projectScopeYear;
  const setProjectScopeYear = (value: SetStateAction<string>) => setCostSessionField("projectScopeYear", value);
  const projectScopeMonth = costSession.projectScopeMonth;
  const setProjectScopeMonth = (value: SetStateAction<string>) => setCostSessionField("projectScopeMonth", value);
  const projectScopeStartDate = costSession.projectScopeStartDate;
  const setProjectScopeStartDate = (value: SetStateAction<string>) => setCostSessionField("projectScopeStartDate", value);
  const projectScopeEndDate = costSession.projectScopeEndDate;
  const setProjectScopeEndDate = (value: SetStateAction<string>) => setCostSessionField("projectScopeEndDate", value);
  const bankScopeMode = costSession.bankScopeMode;
  const setBankScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("bankScopeMode", value);
  const [bankScopePanel, setBankScopePanel] = useState<ScopePickerPanel | null>(null);
  const bankScopeYear = costSession.bankScopeYear;
  const setBankScopeYear = (value: SetStateAction<string>) => setCostSessionField("bankScopeYear", value);
  const bankScopeMonth = costSession.bankScopeMonth;
  const setBankScopeMonth = (value: SetStateAction<string>) => setCostSessionField("bankScopeMonth", value);
  const bankScopeStartDate = costSession.bankScopeStartDate;
  const setBankScopeStartDate = (value: SetStateAction<string>) => setCostSessionField("bankScopeStartDate", value);
  const bankScopeEndDate = costSession.bankScopeEndDate;
  const setBankScopeEndDate = (value: SetStateAction<string>) => setCostSessionField("bankScopeEndDate", value);

  const expenseTypeScopeMode = costSession.expenseTypeScopeMode;
  const setExpenseTypeScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("expenseTypeScopeMode", value);
  const [expenseTypeScopePanel, setExpenseTypeScopePanel] = useState<ScopePickerPanel | null>("month");
  const expenseTypeScopeYear = costSession.expenseTypeScopeYear;
  const setExpenseTypeScopeYear = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeYear", value);
  const expenseTypeScopeMonth = costSession.expenseTypeScopeMonth;
  const setExpenseTypeScopeMonth = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeMonth", value);
  const [expenseTypeRangeMode, setExpenseTypeRangeMode] = useState<ExportRangeMode>("month");
  const [expenseTypeMonth, setExpenseTypeMonth] = useState(DEFAULT_MONTH);
  const [expenseTypeStartDate, setExpenseTypeStartDate] = useState(defaultMonthBounds.startDate);
  const [expenseTypeEndDate, setExpenseTypeEndDate] = useState(defaultMonthBounds.endDate);
  const expenseTypeScopeStartDate = costSession.expenseTypeScopeStartDate;
  const setExpenseTypeScopeStartDate = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeStartDate", value);
  const expenseTypeScopeEndDate = costSession.expenseTypeScopeEndDate;
  const setExpenseTypeScopeEndDate = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeEndDate", value);
  const [expenseTypeSelections, setExpenseTypeSelections] = useState<string[]>([]);

  const [selectedTimeTransactionId, setSelectedTimeTransactionId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [selectedProjectExpenseType, setSelectedProjectExpenseType] = useState<string | null>(null);
  const [selectedProjectTransactionId, setSelectedProjectTransactionId] = useState<string | null>(null);
  const [selectedBankAccountLabel, setSelectedBankAccountLabel] = useState<string | null>(null);
  const [selectedBankProjectName, setSelectedBankProjectName] = useState<string | null>(null);
  const [selectedBankTransactionId, setSelectedBankTransactionId] = useState<string | null>(null);
  const [selectedExpenseType, setSelectedExpenseType] = useState<string | null>(null);
  const [selectedExpenseTransactionId, setSelectedExpenseTransactionId] = useState<string | null>(null);
  const scopeControlsRef = useRef<HTMLDivElement | null>(null);

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

  const explorerMonth =
    viewMode === "project" || viewMode === "bank"
      ? "all"
      : viewMode === "time"
        ? timeScopeMode === "month"
          ? timeScopeMonth
          : "all"
        : expenseTypeScopeMode === "month"
          ? expenseTypeScopeMonth
          : "all";
  function resetDetailSelection() {
    setTransactionDetail(null);
    setSelectedTimeTransactionId(null);
    setSelectedProjectTransactionId(null);
    setSelectedBankTransactionId(null);
    setSelectedExpenseTransactionId(null);
  }

  useEffect(() => {
    const controller = new AbortController();

    async function loadExplorer() {
      const cachedPayload = getCachedCostStatisticsExplorer(explorerMonth, costProjectScope);
      const hasVisibleData = Boolean(explorerData || cachedPayload);

      setLoadError(null);
      setExportFeedback(null);
      setSelectedProjectName(null);
      setSelectedProjectExpenseType(null);
      setSelectedBankAccountLabel(null);
      setSelectedBankProjectName(null);
      setSelectedExpenseType(null);
      resetDetailSelection();

      if (cachedPayload) {
        setExplorerData(cachedPayload);
        setIsExplorerLoading(false);
        setIsExplorerRefreshing(true);
      } else if (hasVisibleData) {
        setIsExplorerRefreshing(true);
      } else {
        setIsExplorerLoading(true);
      }

      try {
        const payload = await fetchCostStatisticsExplorer(explorerMonth, controller.signal, costProjectScope);
        if (!controller.signal.aborted) {
          setExplorerData(payload);
          if (explorerMonth === "all") {
            setExportReferenceData(payload);
          }
        }
      } catch {
        if (!controller.signal.aborted) {
          setLoadError("成本统计数据加载失败，请稍后重试。");
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsExplorerLoading(false);
          setIsExplorerRefreshing(false);
        }
      }
    }

    void loadExplorer();
    return () => controller.abort();
  }, [costProjectScope, explorerMonth]);

  useEffect(() => {
    const cachedPayload = getCachedCostStatisticsExplorer("all", costProjectScope);
    if (cachedPayload) {
      setExportReferenceData(cachedPayload);
      return undefined;
    }

    const controller = new AbortController();

    async function loadExportReferenceData() {
      try {
        const payload = await fetchCostStatisticsExplorer("all", controller.signal, costProjectScope);
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
  }, [costProjectScope]);

  useEffect(() => {
    if (viewMode !== "time") {
      return;
    }
    setSelectedTimeTransactionId(null);
    setTransactionDetail(null);
  }, [viewMode, timeScopeMode, timeScopeYear, timeScopeMonth, timeScopeStartDate, timeScopeEndDate]);

  useEffect(() => {
    if (viewMode !== "project") {
      return;
    }
    setSelectedProjectName(null);
    setSelectedProjectExpenseType(null);
    setSelectedProjectTransactionId(null);
    setTransactionDetail(null);
  }, [viewMode, projectScopeMode, projectScopeYear, projectScopeMonth, projectScopeStartDate, projectScopeEndDate]);

  useEffect(() => {
    if (viewMode !== "bank") {
      return;
    }
    setSelectedBankAccountLabel(null);
    setSelectedBankProjectName(null);
    setSelectedBankTransactionId(null);
    setTransactionDetail(null);
  }, [viewMode, bankScopeMode, bankScopeYear, bankScopeMonth, bankScopeStartDate, bankScopeEndDate]);

  useEffect(() => {
    if (viewMode !== "expenseType") {
      return;
    }
    setSelectedExpenseType(null);
    setSelectedExpenseTransactionId(null);
    setTransactionDetail(null);
  }, [
    viewMode,
    expenseTypeScopeMode,
    expenseTypeScopeYear,
    expenseTypeScopeMonth,
    expenseTypeScopeStartDate,
    expenseTypeScopeEndDate,
  ]);

  const timeRows = explorerData?.timeRows ?? [];
  const availableScopeYears = useMemo(
    () =>
      Array.from(new Set((explorerData?.timeRows ?? []).map((row) => row.tradeTime.slice(0, 4)).filter(Boolean))).sort(
        (left, right) => right.localeCompare(left, "zh-CN"),
      ),
    [explorerData],
  );
  const filteredTimeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
        timeScopeMode,
        timeScopeYear,
        timeScopeMonth,
        timeScopeStartDate,
        timeScopeEndDate,
      ),
    [explorerData, timeScopeMode, timeScopeYear, timeScopeMonth, timeScopeStartDate, timeScopeEndDate],
  );
  const filteredProjectTimeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
        projectScopeMode,
        projectScopeYear,
        projectScopeMonth,
        projectScopeStartDate,
        projectScopeEndDate,
      ),
    [explorerData, projectScopeMode, projectScopeYear, projectScopeMonth, projectScopeStartDate, projectScopeEndDate],
  );
  const projectRows = useMemo(() => buildProjectRowsFromTimeRows(filteredProjectTimeRows), [filteredProjectTimeRows]);
  const filteredBankTimeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
        bankScopeMode,
        bankScopeYear,
        bankScopeMonth,
        bankScopeStartDate,
        bankScopeEndDate,
      ),
    [explorerData, bankScopeMode, bankScopeYear, bankScopeMonth, bankScopeStartDate, bankScopeEndDate],
  );
  const bankRows = useMemo(() => buildBankRowsFromTimeRows(filteredBankTimeRows), [filteredBankTimeRows]);
  const filteredExpenseTypeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
        expenseTypeScopeMode,
        expenseTypeScopeYear,
        expenseTypeScopeMonth,
        expenseTypeScopeStartDate,
        expenseTypeScopeEndDate,
      ),
    [
      explorerData,
      expenseTypeScopeMode,
      expenseTypeScopeYear,
      expenseTypeScopeMonth,
      expenseTypeScopeStartDate,
      expenseTypeScopeEndDate,
    ],
  );
  const expenseTypeRows = useMemo(
    () => buildExpenseTypeRowsFromTimeRows(filteredExpenseTypeRows),
    [filteredExpenseTypeRows],
  );

  const selectedProjectRows = useMemo(
    () => filteredProjectTimeRows.filter((row) => row.projectName === selectedProjectName),
    [filteredProjectTimeRows, selectedProjectName],
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
    () => filteredExpenseTypeRows.filter((row) => row.expenseType === selectedExpenseType),
    [filteredExpenseTypeRows, selectedExpenseType],
  );
  const selectedBankRows = useMemo(
    () => filteredBankTimeRows.filter((row) => row.paymentAccountLabel === selectedBankAccountLabel),
    [filteredBankTimeRows, selectedBankAccountLabel],
  );
  const bankProjectRows = useMemo(() => buildProjectRowsFromTimeRows(selectedBankRows), [selectedBankRows]);
  const selectedBankProjectRows = useMemo(
    () => selectedBankRows.filter((row) => row.projectName === selectedBankProjectName),
    [selectedBankRows, selectedBankProjectName],
  );

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(timeScopeYear)) {
      setTimeScopeYear(availableScopeYears[0]);
    }
  }, [availableScopeYears, timeScopeYear]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(projectScopeYear)) {
      setProjectScopeYear(availableScopeYears[0]);
    }
  }, [availableScopeYears, projectScopeYear]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(bankScopeYear)) {
      setBankScopeYear(availableScopeYears[0]);
    }
  }, [availableScopeYears, bankScopeYear]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(expenseTypeScopeYear)) {
      setExpenseTypeScopeYear(availableScopeYears[0]);
    }
  }, [availableScopeYears, expenseTypeScopeYear]);

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

  const projectScopeLabel = useMemo(() => {
    if (projectScopeMode === "all") {
      return "全部时间";
    }
    if (projectScopeMode === "year") {
      return `${projectScopeYear}年`;
    }
    if (projectScopeMode === "month") {
      return formatMonthLabel(projectScopeMonth);
    }
    const range = normalizeDateRange(projectScopeStartDate, projectScopeEndDate);
    return `${range.startDate}至${range.endDate}`;
  }, [projectScopeMode, projectScopeYear, projectScopeMonth, projectScopeStartDate, projectScopeEndDate]);

  const timeScopeLabel = useMemo(() => {
    if (timeScopeMode === "all") {
      return "全部时间";
    }
    if (timeScopeMode === "year") {
      return `${timeScopeYear}年`;
    }
    if (timeScopeMode === "month") {
      return formatMonthLabel(timeScopeMonth);
    }
    const range = normalizeDateRange(timeScopeStartDate, timeScopeEndDate);
    return `${range.startDate}至${range.endDate}`;
  }, [timeScopeMode, timeScopeYear, timeScopeMonth, timeScopeStartDate, timeScopeEndDate]);

  const bankScopeLabel = useMemo(() => {
    if (bankScopeMode === "all") {
      return "全部时间";
    }
    if (bankScopeMode === "year") {
      return `${bankScopeYear}年`;
    }
    if (bankScopeMode === "month") {
      return formatMonthLabel(bankScopeMonth);
    }
    const range = normalizeDateRange(bankScopeStartDate, bankScopeEndDate);
    return `${range.startDate}至${range.endDate}`;
  }, [bankScopeMode, bankScopeYear, bankScopeMonth, bankScopeStartDate, bankScopeEndDate]);

  const expenseTypeScopeLabel = useMemo(() => {
    if (expenseTypeScopeMode === "all") {
      return "全部时间";
    }
    if (expenseTypeScopeMode === "year") {
      return `${expenseTypeScopeYear}年`;
    }
    if (expenseTypeScopeMode === "month") {
      return formatMonthLabel(expenseTypeScopeMonth);
    }
    const range = normalizeDateRange(expenseTypeScopeStartDate, expenseTypeScopeEndDate);
    return `${range.startDate}至${range.endDate}`;
  }, [
    expenseTypeScopeMode,
    expenseTypeScopeYear,
    expenseTypeScopeMonth,
    expenseTypeScopeStartDate,
    expenseTypeScopeEndDate,
  ]);

  const isRootEmpty = !isExplorerLoading && !loadError && explorerData
    ? viewMode === "time"
      ? filteredTimeRows.length === 0
      : viewMode === "project"
        ? filteredProjectTimeRows.length === 0
        : viewMode === "bank"
          ? filteredBankTimeRows.length === 0
          : filteredExpenseTypeRows.length === 0
    : false;

  async function openTransactionDetail(row: CostTimeRow, source: "time" | "project" | "bank" | "expenseType") {
    setLoadError(null);
    setExportFeedback(null);
    setDetailLoadingMessage(`正在加载流水 ${row.transactionId} 的详情...`);
    if (source === "time") {
      setSelectedTimeTransactionId(row.transactionId);
    }
    if (source === "project") {
      setSelectedProjectTransactionId(row.transactionId);
    }
    if (source === "bank") {
      setSelectedBankTransactionId(row.transactionId);
    }
    if (source === "expenseType") {
      setSelectedExpenseTransactionId(row.transactionId);
    }
    try {
      const payload = await fetchCostTransactionDetail(row.transactionId, undefined, costProjectScope);
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
    setTimeScopePanel(null);
    setProjectScopePanel(null);
    setBankScopePanel(null);
    setExpenseTypeScopePanel(null);
    startTransition(() => {
      setViewMode(nextViewMode);
    });
  }

  function toggleScopeSelection(
    currentMode: ExplorerScopeMode,
    currentPanel: ScopePickerPanel | null,
    nextMode: ScopePickerPanel,
    setMode: (mode: ExplorerScopeMode) => void,
    setPanel: (panel: ScopePickerPanel | null) => void,
  ) {
    if (currentMode === nextMode && currentPanel === nextMode) {
      setPanel(null);
      return;
    }
    setMode(nextMode);
    setPanel(nextMode);
  }

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!scopeControlsRef.current) {
        return;
      }
      if (scopeControlsRef.current.contains(event.target as Node)) {
        return;
      }
      setTimeScopePanel(null);
      setProjectScopePanel(null);
      setBankScopePanel(null);
      setExpenseTypeScopePanel(null);
    }

    const hasOpenPanel =
      (viewMode === "time" && timeScopePanel !== null) ||
      (viewMode === "project" && projectScopePanel !== null) ||
      (viewMode === "bank" && bankScopePanel !== null) ||
      (viewMode === "expenseType" && expenseTypeScopePanel !== null);

    if (!hasOpenPanel) {
      return;
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [viewMode, timeScopePanel, projectScopePanel, bankScopePanel, expenseTypeScopePanel]);

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
        transactionCount: filteredProjectTimeRows.length,
        totalAmount: formatCurrencyFromRows(filteredProjectTimeRows),
      };
    }
    if (viewMode === "bank") {
      if (selectedBankAccountLabel && selectedBankProjectName) {
        return {
          rowLabel: "该项目流水",
          rowCount: selectedBankProjectRows.length,
          transactionCount: selectedBankProjectRows.length,
          totalAmount: formatCurrencyFromRows(selectedBankProjectRows),
        };
      }
      if (selectedBankAccountLabel) {
        return {
          rowLabel: "项目数",
          rowCount: bankProjectRows.length,
          transactionCount: selectedBankRows.length,
          totalAmount: formatCurrencyFromRows(selectedBankRows),
        };
      }
      return {
        rowLabel: "银行账户数",
        rowCount: bankRows.length,
        transactionCount: filteredBankTimeRows.length,
        totalAmount: formatCurrencyFromRows(filteredBankTimeRows),
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
        transactionCount: filteredExpenseTypeRows.length,
        totalAmount: formatCurrencyFromRows(filteredExpenseTypeRows),
      };
    }
    return {
      rowLabel: "时间流水",
      rowCount: filteredTimeRows.length,
      transactionCount: filteredTimeRows.length,
      totalAmount: formatCurrencyFromRows(filteredTimeRows),
    };
  }, [
    explorerData,
    expenseTypeRows,
    filteredExpenseTypeRows,
    filteredTimeRows,
    expenseTypeRows.length,
    filteredBankTimeRows,
    filteredProjectTimeRows,
    bankProjectRows.length,
    bankRows.length,
    projectExpenseTypeRows.length,
    projectRows.length,
    selectedBankAccountLabel,
    selectedBankProjectName,
    selectedBankProjectRows,
    selectedBankRows,
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
      const rangeMode = expenseTypeScopeMode === "month" ? "month" : "custom";
      const bounds = getScopeDateRange(
        timeRows,
        expenseTypeScopeMode,
        expenseTypeScopeYear,
        expenseTypeScopeMonth,
        expenseTypeScopeStartDate,
        expenseTypeScopeEndDate,
      );
      setExpenseTypeRangeMode(rangeMode);
      setExpenseTypeMonth(expenseTypeScopeMonth);
      setExpenseTypeStartDate(bounds.startDate);
      setExpenseTypeEndDate(bounds.endDate);
      setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
    } else {
      setExportCenterMode("time");
      const rangeMode = timeScopeMode === "month" ? "month" : "custom";
      const bounds = getScopeDateRange(timeRows, timeScopeMode, timeScopeYear, timeScopeMonth, timeScopeStartDate, timeScopeEndDate);
      setTimeRangeMode(rangeMode);
      setTimeMonth(timeScopeMonth);
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
          projectScope: costProjectScope,
        };
      }
      return {
        month: "all",
        view: "time",
        projectScope: costProjectScope,
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
        projectScope: costProjectScope,
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
        projectScope: costProjectScope,
        expenseTypes: expenseTypeSelections,
      };
    }
    return {
      month: "all",
      view: "expense_type",
      projectScope: costProjectScope,
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

  const timeColumns = useMemo<CostStatisticsTableColumn<CostTimeRow>[]>(
    () => [
      { key: "tradeTime", header: "时间", width: 170, render: (row) => row.tradeTime },
      { key: "projectName", header: "项目名", flex: 1.4, render: (row) => row.projectName },
      { key: "expenseType", header: "费用类型", width: 150, render: (row) => row.expenseType },
      {
        key: "amount",
        header: "金额",
        width: 190,
        cellClassName: "cost-table-cell-money",
        render: (row) => ({
          amount: row.amount,
          direction: row.direction,
          paymentAccountLabel: row.paymentAccountLabel,
        }),
      },
      { key: "expenseContent", header: "费用内容", flex: 1.2, render: (row) => row.expenseContent },
    ],
    [],
  );

  const transactionColumns = useMemo<CostStatisticsTableColumn<CostTimeRow>[]>(
    () => [
      { key: "tradeTime", header: "时间", width: 170, render: (row) => row.tradeTime },
      viewMode === "expenseType"
        ? { key: "projectName", header: "项目名", flex: 1, render: (row) => row.projectName }
        : { key: "counterpartyName", header: "对方户名", flex: 1, render: (row) => row.counterpartyName },
      {
        key: "amount",
        header: "金额",
        width: 180,
        cellClassName: "cost-table-cell-money",
        render: (row) => ({
          amount: row.amount,
          direction: row.direction,
          paymentAccountLabel: row.paymentAccountLabel,
        }),
      },
      { key: "expenseContent", header: "费用内容", flex: 1.1, render: (row) => row.expenseContent },
    ],
    [viewMode],
  );

  const activeTransactionId =
    selectedTimeTransactionId ?? selectedProjectTransactionId ?? selectedBankTransactionId ?? selectedExpenseTransactionId;
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
              className={viewMode === "bank" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("bank")}
            >
              按银行
            </button>
            <button
              className={viewMode === "expenseType" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("expenseType")}
            >
              按费用类型
            </button>
            <button
              aria-label={`项目范围：${costProjectScope === "active" ? "进行中" : "所有项目"}`}
              className={costProjectScope === "active" ? "cost-project-scope-trigger active" : "cost-project-scope-trigger"}
              type="button"
              onClick={() => setCostProjectScope((current) => (current === "active" ? "all" : "active"))}
            >
              {costProjectScope === "active" ? "进行中" : "所有项目"}
            </button>
          </div>
          <div className="cost-toolbar-meta">
            {viewMode === "time" ? <strong>按时间查看 {timeScopeLabel} 的全部支出流水</strong> : null}
            {viewMode === "project" ? <strong>从左到右依次展开：项目名 / 费用类型 / 流水，支持按范围重新统计</strong> : null}
            {viewMode === "bank" ? <strong>从左到右依次展开：银行账户 / 项目名 / 流水，支持按范围重新统计</strong> : null}
            {viewMode === "expenseType" ? <strong>按费用类型查看 {expenseTypeScopeLabel} 的对应流水</strong> : null}
            {isExplorerRefreshing ? <span className="cost-toolbar-refreshing">正在更新统计...</span> : null}
          </div>
        </div>

        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {isExplorerLoading && !explorerData ? (
          <div className="state-panel">正在加载成本统计数据...</div>
        ) : null}
        {detailLoadingMessage ? <div className="state-panel">{detailLoadingMessage}</div> : null}
        {exportFeedback && !isExportCenterOpen ? (
          <div className={`action-feedback ${exportFeedback.tone}`}>{exportFeedback.message}</div>
        ) : null}
        {isRootEmpty ? (
          <div className="state-panel">
            {viewMode === "project"
              ? "当前时间范围没有可用于项目成本统计的支出流水。"
              : viewMode === "bank"
                ? "当前时间范围没有可用于银行成本统计的支出流水。"
                : viewMode === "expenseType"
                  ? "当前时间范围没有可用于费用类型统计的支出流水。"
                  : "当前时间范围没有可用于成本统计的支出流水。"}
          </div>
        ) : null}

        {!isExplorerLoading && explorerData ? (
          <>
            {viewMode === "time" ? (
              <div className="cost-analysis-layout time-layout single-column">
                <section className="cost-table-section">
                  <div className="cost-section-heading cost-view-scope-heading">
                    <div className="cost-section-heading-copy">
                      <h2>按时间统计</h2>
                      <span>{timeScopeLabel}</span>
                    </div>
                    <div className="cost-section-heading-actions cost-project-scope-actions">
                      <div ref={scopeControlsRef} className="cost-scope-controls">
                        <div className="cost-scope-toggle" role="tablist" aria-label="时间统计时间范围">
                          <button
                            className={timeScopeMode === "all" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                            type="button"
                            onClick={() => {
                              setTimeScopeMode("all");
                              setTimeScopePanel(null);
                            }}
                          >
                            全部时间
                          </button>
                          <button
                            className={timeScopeMode === "year" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                            type="button"
                            onClick={() =>
                              toggleScopeSelection(timeScopeMode, timeScopePanel, "year", setTimeScopeMode, setTimeScopePanel)
                            }
                          >
                            {formatScopeButtonLabel("按年统计", timeScopeMode === "year", `${timeScopeYear}年`)}
                          </button>
                          <button
                            className={timeScopeMode === "month" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                            type="button"
                            onClick={() =>
                              toggleScopeSelection(timeScopeMode, timeScopePanel, "month", setTimeScopeMode, setTimeScopePanel)
                            }
                          >
                            {formatScopeButtonLabel("按月统计", timeScopeMode === "month", formatMonthLabel(timeScopeMonth))}
                          </button>
                          <button
                            className={timeScopeMode === "custom" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                            type="button"
                            onClick={() =>
                              toggleScopeSelection(timeScopeMode, timeScopePanel, "custom", setTimeScopeMode, setTimeScopePanel)
                            }
                          >
                            {formatScopeButtonLabel(
                              "自定义时间段",
                              timeScopeMode === "custom",
                              `${normalizeDateRange(timeScopeStartDate, timeScopeEndDate).startDate}至${normalizeDateRange(timeScopeStartDate, timeScopeEndDate).endDate}`,
                            )}
                          </button>
                        </div>
                        {timeScopePanel === "year" ? (
                          <div className="cost-scope-floating-panel">
                            <ScopeYearPicker
                              ariaLabel="时间统计年份"
                              years={availableScopeYears}
                              value={timeScopeYear}
                              onChange={setTimeScopeYear}
                            />
                          </div>
                        ) : null}
                        {timeScopePanel === "month" ? (
                          <div className="cost-scope-floating-panel">
                            <MonthPicker inline value={timeScopeMonth} onChange={setTimeScopeMonth} ariaLabel="时间统计月份" caption={null} />
                          </div>
                        ) : null}
                        {timeScopePanel === "custom" ? (
                          <div className="cost-scope-floating-panel">
                            <div className="cost-scope-date-panel">
                              <div className="cost-date-range-fields">
                                <label className="cost-inline-field">
                                  <span>开始日期</span>
                                  <input
                                    aria-label="时间统计开始日期"
                                    className="cost-date-input"
                                    type="date"
                                    value={timeScopeStartDate}
                                    onChange={(event) => setTimeScopeStartDate(event.target.value)}
                                  />
                                </label>
                                <label className="cost-inline-field">
                                  <span>结束日期</span>
                                  <input
                                    aria-label="时间统计结束日期"
                                    className="cost-date-input"
                                    type="date"
                                    value={timeScopeEndDate}
                                    onChange={(event) => setTimeScopeEndDate(event.target.value)}
                                  />
                                </label>
                              </div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <CostStatisticsTable
                    ariaLabel="按时间统计表"
                    columns={timeColumns}
                    rows={filteredTimeRows}
                    getRowKey={(row) => row.transactionId}
                    emptyLabel="当前时间范围没有可用于成本统计的支出流水。"
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
                    <span>{projectScopeLabel}</span>
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <div ref={scopeControlsRef} className="cost-scope-controls">
                      <div className="cost-scope-toggle" role="tablist" aria-label="项目统计时间范围">
                        <button
                          className={projectScopeMode === "all" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() => {
                            setProjectScopeMode("all");
                            setProjectScopePanel(null);
                          }}
                        >
                          全部时间
                        </button>
                        <button
                          className={projectScopeMode === "year" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              projectScopeMode,
                              projectScopePanel,
                              "year",
                              setProjectScopeMode,
                              setProjectScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel("按年统计", projectScopeMode === "year", `${projectScopeYear}年`)}
                        </button>
                        <button
                          className={projectScopeMode === "month" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              projectScopeMode,
                              projectScopePanel,
                              "month",
                              setProjectScopeMode,
                              setProjectScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel("按月统计", projectScopeMode === "month", formatMonthLabel(projectScopeMonth))}
                        </button>
                        <button
                          className={projectScopeMode === "custom" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              projectScopeMode,
                              projectScopePanel,
                              "custom",
                              setProjectScopeMode,
                              setProjectScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel(
                            "自定义时间段",
                            projectScopeMode === "custom",
                            `${normalizeDateRange(projectScopeStartDate, projectScopeEndDate).startDate}至${normalizeDateRange(projectScopeStartDate, projectScopeEndDate).endDate}`,
                          )}
                        </button>
                      </div>
                      {projectScopePanel === "year" ? (
                        <div className="cost-scope-floating-panel">
                          <ScopeYearPicker
                            ariaLabel="项目统计年份"
                            years={availableScopeYears}
                            value={projectScopeYear}
                            onChange={setProjectScopeYear}
                          />
                        </div>
                      ) : null}
                      {projectScopePanel === "month" ? (
                        <div className="cost-scope-floating-panel">
                          <MonthPicker inline value={projectScopeMonth} onChange={setProjectScopeMonth} ariaLabel="项目统计月份" caption={null} />
                        </div>
                      ) : null}
                      {projectScopePanel === "custom" ? (
                        <div className="cost-scope-floating-panel">
                          <div className="cost-scope-date-panel">
                            <div className="cost-date-range-fields">
                              <label className="cost-inline-field">
                                <span>开始日期</span>
                                <input
                                  aria-label="项目统计开始日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={projectScopeStartDate}
                                  onChange={(event) => setProjectScopeStartDate(event.target.value)}
                                />
                              </label>
                              <label className="cost-inline-field">
                                <span>结束日期</span>
                                <input
                                  aria-label="项目统计结束日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={projectScopeEndDate}
                                  onChange={(event) => setProjectScopeEndDate(event.target.value)}
                                />
                              </label>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className="cost-explorer-grid project">
                  <CostExplorerList<CostProjectExplorerRow>
                    title="项目名"
                    count={projectRows.length}
                    items={projectRows}
                    emptyLabel="当前时间范围没有项目成本。"
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
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <span>{row.totalAmount}</span>
                        {row.percentageLabel ? (
                          <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                        ) : null}
                      </div>
                    )}
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

            {viewMode === "bank" ? (
              <div className="cost-analysis-layout explorer-layout">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按银行统计</h2>
                    <span>{bankScopeLabel}</span>
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <div ref={scopeControlsRef} className="cost-scope-controls">
                      <div className="cost-scope-toggle" role="tablist" aria-label="银行统计时间范围">
                        <button
                          className={bankScopeMode === "all" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() => {
                            setBankScopeMode("all");
                            setBankScopePanel(null);
                          }}
                        >
                          全部时间
                        </button>
                        <button
                          className={bankScopeMode === "year" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(bankScopeMode, bankScopePanel, "year", setBankScopeMode, setBankScopePanel)
                          }
                        >
                          {formatScopeButtonLabel("按年统计", bankScopeMode === "year", `${bankScopeYear}年`)}
                        </button>
                        <button
                          className={bankScopeMode === "month" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(bankScopeMode, bankScopePanel, "month", setBankScopeMode, setBankScopePanel)
                          }
                        >
                          {formatScopeButtonLabel("按月统计", bankScopeMode === "month", formatMonthLabel(bankScopeMonth))}
                        </button>
                        <button
                          className={bankScopeMode === "custom" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(bankScopeMode, bankScopePanel, "custom", setBankScopeMode, setBankScopePanel)
                          }
                        >
                          {formatScopeButtonLabel(
                            "自定义时间段",
                            bankScopeMode === "custom",
                            `${normalizeDateRange(bankScopeStartDate, bankScopeEndDate).startDate}至${normalizeDateRange(bankScopeStartDate, bankScopeEndDate).endDate}`,
                          )}
                        </button>
                      </div>
                      {bankScopePanel === "year" ? (
                        <div className="cost-scope-floating-panel">
                          <ScopeYearPicker
                            ariaLabel="银行统计年份"
                            years={availableScopeYears}
                            value={bankScopeYear}
                            onChange={setBankScopeYear}
                          />
                        </div>
                      ) : null}
                      {bankScopePanel === "month" ? (
                        <div className="cost-scope-floating-panel">
                          <MonthPicker inline value={bankScopeMonth} onChange={setBankScopeMonth} ariaLabel="银行统计月份" caption={null} />
                        </div>
                      ) : null}
                      {bankScopePanel === "custom" ? (
                        <div className="cost-scope-floating-panel">
                          <div className="cost-scope-date-panel">
                            <div className="cost-date-range-fields">
                              <label className="cost-inline-field">
                                <span>开始日期</span>
                                <input
                                  aria-label="银行统计开始日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={bankScopeStartDate}
                                  onChange={(event) => setBankScopeStartDate(event.target.value)}
                                />
                              </label>
                              <label className="cost-inline-field">
                                <span>结束日期</span>
                                <input
                                  aria-label="银行统计结束日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={bankScopeEndDate}
                                  onChange={(event) => setBankScopeEndDate(event.target.value)}
                                />
                              </label>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className="cost-explorer-grid project">
                  <CostExplorerList<CostBankExplorerRow>
                    title="银行账户"
                    count={bankRows.length}
                    items={bankRows}
                    emptyLabel="当前时间范围没有银行支出数据。"
                    getKey={(row) => row.paymentAccountLabel}
                    isActive={(row) => row.paymentAccountLabel === selectedBankAccountLabel}
                    onSelect={(row) => {
                      setSelectedBankAccountLabel(row.paymentAccountLabel);
                      setSelectedBankProjectName(null);
                      setSelectedBankTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.paymentAccountLabel}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.projectCount} 个项目`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <span>{row.totalAmount}</span>
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <CostExplorerList<CostProjectExplorerRow>
                    title="项目名"
                    count={bankProjectRows.length}
                    items={bankProjectRows}
                    emptyLabel={selectedBankAccountLabel ? "该账户下暂无项目流水。" : "请先在左侧选择银行账户。"}
                    getKey={(row) => row.projectName}
                    isActive={(row) => row.projectName === selectedBankProjectName}
                    onSelect={(row) => {
                      setSelectedBankProjectName(row.projectName);
                      setSelectedBankTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.projectName}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.expenseTypeCount} 类费用`}
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
                      <span>{selectedBankProjectRows.length}</span>
                    </header>
                    {selectedBankAccountLabel && selectedBankProjectName ? (
                      <CostStatisticsTable
                        ariaLabel="银行对应流水表"
                        columns={transactionColumns}
                        rows={selectedBankProjectRows}
                        getRowKey={(row) => row.transactionId}
                        onRowClick={(row) => void openTransactionDetail(row, "bank")}
                        getRowActionLabel={(row) => `查看流水 ${row.transactionId}`}
                        emptyLabel="该项目下暂无流水。"
                      />
                    ) : (
                      <div className="cost-explorer-empty">请先依次选择银行账户和项目。</div>
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
                    <span>{expenseTypeScopeLabel}</span>
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <div ref={scopeControlsRef} className="cost-scope-controls">
                      <div className="cost-scope-toggle" role="tablist" aria-label="费用类型统计时间范围">
                        <button
                          className={expenseTypeScopeMode === "all" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() => {
                            setExpenseTypeScopeMode("all");
                            setExpenseTypeScopePanel(null);
                          }}
                        >
                          全部时间
                        </button>
                        <button
                          className={expenseTypeScopeMode === "year" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              expenseTypeScopeMode,
                              expenseTypeScopePanel,
                              "year",
                              setExpenseTypeScopeMode,
                              setExpenseTypeScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel("按年统计", expenseTypeScopeMode === "year", `${expenseTypeScopeYear}年`)}
                        </button>
                        <button
                          className={expenseTypeScopeMode === "month" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              expenseTypeScopeMode,
                              expenseTypeScopePanel,
                              "month",
                              setExpenseTypeScopeMode,
                              setExpenseTypeScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel(
                            "按月统计",
                            expenseTypeScopeMode === "month",
                            formatMonthLabel(expenseTypeScopeMonth),
                          )}
                        </button>
                        <button
                          className={expenseTypeScopeMode === "custom" ? "cost-scope-toggle-btn active" : "cost-scope-toggle-btn"}
                          type="button"
                          onClick={() =>
                            toggleScopeSelection(
                              expenseTypeScopeMode,
                              expenseTypeScopePanel,
                              "custom",
                              setExpenseTypeScopeMode,
                              setExpenseTypeScopePanel,
                            )
                          }
                        >
                          {formatScopeButtonLabel(
                            "自定义时间段",
                            expenseTypeScopeMode === "custom",
                            `${normalizeDateRange(expenseTypeScopeStartDate, expenseTypeScopeEndDate).startDate}至${normalizeDateRange(expenseTypeScopeStartDate, expenseTypeScopeEndDate).endDate}`,
                          )}
                        </button>
                      </div>
                      {expenseTypeScopePanel === "year" ? (
                        <div className="cost-scope-floating-panel">
                          <ScopeYearPicker
                            ariaLabel="费用类型统计年份"
                            years={availableScopeYears}
                            value={expenseTypeScopeYear}
                            onChange={setExpenseTypeScopeYear}
                          />
                        </div>
                      ) : null}
                      {expenseTypeScopePanel === "month" ? (
                        <div className="cost-scope-floating-panel">
                          <MonthPicker
                            inline
                            value={expenseTypeScopeMonth}
                            onChange={setExpenseTypeScopeMonth}
                            ariaLabel="费用类型统计月份"
                            caption={null}
                          />
                        </div>
                      ) : null}
                      {expenseTypeScopePanel === "custom" ? (
                        <div className="cost-scope-floating-panel">
                          <div className="cost-scope-date-panel">
                            <div className="cost-date-range-fields">
                              <label className="cost-inline-field">
                                <span>开始日期</span>
                                <input
                                  aria-label="费用类型统计开始日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={expenseTypeScopeStartDate}
                                  onChange={(event) => setExpenseTypeScopeStartDate(event.target.value)}
                                />
                              </label>
                              <label className="cost-inline-field">
                                <span>结束日期</span>
                                <input
                                  aria-label="费用类型统计结束日期"
                                  className="cost-date-input"
                                  type="date"
                                  value={expenseTypeScopeEndDate}
                                  onChange={(event) => setExpenseTypeScopeEndDate(event.target.value)}
                                />
                              </label>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className="cost-explorer-grid expense">
                  <CostExplorerList<ExpenseTypeExplorerDisplayRow>
                    title="费用类型"
                    count={expenseTypeRows.length}
                    items={expenseTypeRows}
                    emptyLabel="当前时间范围没有费用类型数据。"
                    getKey={(row) => row.expenseType}
                    isActive={(row) => row.expenseType === selectedExpenseType}
                    onSelect={(row) => {
                      setSelectedExpenseType(row.expenseType);
                      setSelectedExpenseTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.expenseType}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.projectCount} 个项目`}
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
