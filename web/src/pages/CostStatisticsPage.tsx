import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";

import { formatMonthLabel } from "../components/MonthPicker";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import CostExplorerList from "../components/cost-statistics/CostExplorerList";
import ExportCenterModal, {
  type ExportCenterMode,
  type ExportRangeMode,
} from "../components/cost-statistics/ExportCenterModal";
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
  clearCostStatisticsExplorerCache,
  type CostExportParams,
  type PreviewCostExportParams,
} from "../features/cost-statistics/api";
import { ApiClientError } from "../features/apiClient";
import { FINANCE_DOMAIN_EVENTS } from "../features/domainEvents";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { importWorkflowPath } from "../features/imports/importRoutes";
import type {
  CostBankAccount,
  CostExpenseTypeExplorerRow,
  CostProjectScope,
  CostProjectExplorerRow,
  CostStatisticsExplorer,
  CostStatisticsExportPreview,
  CostTimeRow,
  CostTransactionDetail,
} from "../features/cost-statistics/types";

type CostViewMode = "time" | "project" | "bank" | "expenseType" | "bankTag";
type RangeScopeMode = "all" | "year" | "month";
type ExplorerScopeMode = RangeScopeMode;
type ScopePickerPanel = "scope";

type CostStatisticsPageSession = {
  viewMode: CostViewMode;
  timeScopeMode: ExplorerScopeMode;
  timeScopeYear: string;
  timeScopeMonth: string;
  projectScopeMode: ExplorerScopeMode;
  projectScopeYear: string;
  projectScopeMonth: string;
  bankScopeMode: ExplorerScopeMode;
  bankScopeYear: string;
  bankScopeMonth: string;
  expenseTypeScopeMode: ExplorerScopeMode;
  expenseTypeScopeYear: string;
  expenseTypeScopeMonth: string;
  bankTagScopeMode: ExplorerScopeMode;
  bankTagScopeYear: string;
  bankTagScopeMonth: string;
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

type CostBankTagPrimaryRow = {
  primaryLabel: string;
  totalAmount: string;
  transactionCount: number;
  subTagCount: number;
  percentageLabel: string;
};

type CostBankTagSubRow = {
  primaryLabel: string;
  subLabel: string;
  totalAmount: string;
  transactionCount: number;
  projectCount: number;
  percentageLabel: string;
};

type ScopeRangePickerProps = {
  ariaLabel: string;
  label: string;
  mode: ExplorerScopeMode;
  years: string[];
  year: string;
  month: string;
  open: boolean;
  onToggle: () => void;
  onModeChange: (mode: ExplorerScopeMode) => void;
  onYearChange: (year: string) => void;
  onMonthChange: (month: string) => void;
  onClose: () => void;
};

const SCOPE_MONTH_LABELS = [
  "一月",
  "二月",
  "三月",
  "四月",
  "五月",
  "六月",
  "七月",
  "八月",
  "九月",
  "十月",
  "十一月",
  "十二月",
];

function getCostTimeRowRenderKey(row: CostTimeRow, index: number) {
  return [
    row.transactionId || "transaction",
    row.tradeTime,
    row.projectName,
    row.expenseType,
    row.expenseContent,
    row.amount,
    String(index),
  ].join("|");
}

function moneyToNumber(value: string) {
  const parsed = Number(String(value || "0").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function sumCostTimeRows(rows: CostTimeRow[]) {
  return rows.reduce((sum, row) => sum + moneyToNumber(row.amount), 0);
}

function formatCostTradeTime(value: string) {
  const raw = String(value || "").trim();
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::(\d{2}))?/);
  if (!match) {
    return raw;
  }
  return `${match[1]} ${match[2]}${match[3] ? `:${match[3]}` : ""}`;
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

function buildBankRowsFromTimeRowsAndAccounts(rows: CostTimeRow[], accounts: CostBankAccount[]) {
  const grouped = new Map<
    string,
    { totalAmount: number; transactionCount: number; projects: Set<string> }
  >();
  const totalAmount = sumCostTimeRows(rows);

  for (const account of accounts) {
    const label = account.paymentAccountLabel.trim();
    if (!label || grouped.has(label)) {
      continue;
    }
    grouped.set(label, {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    });
  }

  for (const row of rows) {
    const label = row.paymentAccountLabel.trim() || "未识别账户";
    const bucket = grouped.get(label) ?? {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    };
    bucket.totalAmount += moneyToNumber(row.amount);
    bucket.transactionCount += 1;
    bucket.projects.add(row.projectName);
    grouped.set(label, bucket);
  }

  return Array.from(grouped.entries())
    .map<CostBankExplorerRow>(([paymentAccountLabel, bucket]) => ({
      paymentAccountLabel,
      totalAmount: formatMoney(bucket.totalAmount),
      transactionCount: bucket.transactionCount,
      projectCount: bucket.projects.size,
      percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => {
      const amountDelta = moneyToNumber(right.totalAmount) - moneyToNumber(left.totalAmount);
      if (amountDelta !== 0) {
        return amountDelta;
      }
      return left.paymentAccountLabel.localeCompare(right.paymentAccountLabel, "zh-CN");
    });
}

function bankTagPrimaryLabel(row: CostTimeRow) {
  return row.bankTagPrimaryLabel || row.bankTagLabelPath[0] || row.bankTagLabel || "未标记";
}

function bankTagSubLabel(row: CostTimeRow) {
  return row.bankTagSubLabel || row.bankTagLabelPath[1] || row.bankTagLabel || bankTagPrimaryLabel(row);
}

function buildBankTagPrimaryRowsFromTimeRows(rows: CostTimeRow[]) {
  const grouped = new Map<string, { totalAmount: number; transactionCount: number; subTags: Set<string> }>();
  const totalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);

  for (const row of rows) {
    const primaryLabel = bankTagPrimaryLabel(row);
    const bucket = grouped.get(primaryLabel) ?? {
      totalAmount: 0,
      transactionCount: 0,
      subTags: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.subTags.add(bankTagSubLabel(row));
    grouped.set(primaryLabel, bucket);
  }

  return Array.from(grouped.entries())
    .map<CostBankTagPrimaryRow>(([primaryLabel, bucket]) => ({
      primaryLabel,
      totalAmount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transactionCount: bucket.transactionCount,
      subTagCount: bucket.subTags.size,
      percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
    }))
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function buildBankTagSubRowsFromTimeRows(rows: CostTimeRow[]) {
  const grouped = new Map<string, { totalAmount: number; transactionCount: number; projects: Set<string> }>();
  const totalAmount = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);

  for (const row of rows) {
    const primaryLabel = bankTagPrimaryLabel(row);
    const subLabel = bankTagSubLabel(row);
    const groupKey = `${primaryLabel}\u0000${subLabel}`;
    const bucket = grouped.get(groupKey) ?? {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.projects.add(row.projectName);
    grouped.set(groupKey, bucket);
  }

  return Array.from(grouped.entries())
    .map<CostBankTagSubRow>(([groupKey, bucket]) => {
      const [primaryLabel, subLabel] = groupKey.split("\u0000");
      return {
        primaryLabel,
        subLabel,
        totalAmount: bucket.totalAmount.toLocaleString("en-US", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }),
        transactionCount: bucket.transactionCount,
        projectCount: bucket.projects.size,
        percentageLabel: `${((bucket.totalAmount / (totalAmount || 1)) * 100).toFixed(1)}%`,
      };
    })
    .sort((left, right) => Number(right.totalAmount.replace(/,/g, "")) - Number(left.totalAmount.replace(/,/g, "")));
}

function filterScopeTimeRows(
  rows: CostTimeRow[],
  mode: ExplorerScopeMode,
  year: string,
  month: string,
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
  return rows;
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

function getCostStatisticsLoadErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    const message = error.message.trim();
    if (message && error.code === "cost_statistics_explorer_temporarily_unavailable") {
      return message;
    }
    if (message && (error.status === 401 || error.status === 403 || error.code === "invalid_oa_session")) {
      return message;
    }
  }
  return "成本统计数据加载失败，请点击刷新重试。";
}

function ScopeRangePicker({
  ariaLabel,
  label,
  mode,
  years,
  year,
  month,
  open,
  onToggle,
  onModeChange,
  onYearChange,
  onMonthChange,
  onClose,
}: ScopeRangePickerProps) {
  const pickerYears = years.length > 0 ? years : [DEFAULT_MONTH.slice(0, 4)];
  const activeYear = mode === "month" ? month.slice(0, 4) || year : year || DEFAULT_MONTH.slice(0, 4);
  const activeMonth = mode === "month" ? month.slice(5, 7) : "";
  const selectedLabel = mode === "all" ? "全部时间" : mode === "year" ? `${year}年` : formatMonthLabel(month);

  function selectAll() {
    onModeChange("all");
    onClose();
  }

  function selectYear(nextYear: string) {
    onYearChange(nextYear);
    onModeChange("year");
    onClose();
  }

  function selectMonth(monthNumber: number) {
    const nextMonth = `${activeYear}-${String(monthNumber).padStart(2, "0")}`;
    onYearChange(activeYear);
    onMonthChange(nextMonth);
    onModeChange("month");
    onClose();
  }

  return (
    <div className="cost-scope-picker">
      <button
        aria-expanded={open}
        aria-label={`${ariaLabel}：${selectedLabel}`}
        className={open ? "cost-scope-trigger is-open" : "cost-scope-trigger"}
        type="button"
        onClick={onToggle}
      >
        <span className="cost-scope-trigger-label">
          <span>{label}</span>
          <strong>{selectedLabel}</strong>
        </span>
        <span aria-hidden="true" className="cost-scope-trigger-icon">
          ▾
        </span>
      </button>
      {open ? (
        <div className="cost-scope-popover" role="dialog" aria-label={`${ariaLabel}选择器`}>
          <button
            aria-pressed={mode === "all"}
            className={mode === "all" ? "cost-scope-option all active" : "cost-scope-option all"}
            type="button"
            onClick={selectAll}
          >
            全部时间
          </button>
          <div className="cost-scope-panel-section">
            <span>年份</span>
            <div className="cost-scope-option-grid years">
              {pickerYears.map((candidateYear) => (
                <button
                  key={candidateYear}
                  aria-pressed={mode === "year" && candidateYear === year}
                  className={mode === "year" && candidateYear === year ? "cost-scope-option active" : "cost-scope-option"}
                  type="button"
                  onClick={() => selectYear(candidateYear)}
                >
                  {candidateYear}年
                </button>
              ))}
            </div>
          </div>
          <div className="cost-scope-panel-section">
            <span>月份</span>
            <div className="cost-scope-option-grid months">
              {SCOPE_MONTH_LABELS.map((monthLabel, index) => {
                const monthNumber = index + 1;
                const isActive = activeMonth === String(monthNumber).padStart(2, "0");
                return (
                  <button
                    key={monthLabel}
                    aria-pressed={mode === "month" && isActive}
                    className={mode === "month" && isActive ? "cost-scope-option active" : "cost-scope-option"}
                    type="button"
                    onClick={() => selectMonth(monthNumber)}
                  >
                    {monthLabel}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
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
    "timeScopeMode",
    "timeScopeYear",
    "timeScopeMonth",
    "projectScopeMode",
    "projectScopeYear",
    "projectScopeMonth",
    "bankScopeMode",
    "bankScopeYear",
    "bankScopeMonth",
    "expenseTypeScopeMode",
    "expenseTypeScopeYear",
    "expenseTypeScopeMonth",
    "bankTagScopeMode",
    "bankTagScopeYear",
    "bankTagScopeMonth",
  ].every((key) => typeof session[key] === "string");
}

export default function CostStatisticsPage() {
  const navigate = useNavigate();
  const { setWorkbenchHeaderActions } = useAppChrome();
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const defaultMonthBounds = buildMonthDateBounds(DEFAULT_MONTH);
  const costPageSession = usePageSessionState<CostStatisticsPageSession>({
    pageKey: "cost-statistics",
    stateKey: "explorerState",
    version: 2,
    initialValue: {
      viewMode: "time",
      timeScopeMode: "month",
      timeScopeYear: DEFAULT_MONTH.slice(0, 4),
      timeScopeMonth: DEFAULT_MONTH,
      projectScopeMode: "all",
      projectScopeYear: DEFAULT_MONTH.slice(0, 4),
      projectScopeMonth: DEFAULT_MONTH,
      bankScopeMode: "all",
      bankScopeYear: DEFAULT_MONTH.slice(0, 4),
      bankScopeMonth: DEFAULT_MONTH,
      expenseTypeScopeMode: "month",
      expenseTypeScopeYear: DEFAULT_MONTH.slice(0, 4),
      expenseTypeScopeMonth: DEFAULT_MONTH,
      bankTagScopeMode: "month",
      bankTagScopeYear: DEFAULT_MONTH.slice(0, 4),
      bankTagScopeMonth: DEFAULT_MONTH,
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
  const costProjectScope: CostProjectScope = "active";
  const timeScopeMode = costSession.timeScopeMode;
  const setTimeScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("timeScopeMode", value);
  const [timeScopePanel, setTimeScopePanel] = useState<ScopePickerPanel | null>(null);
  const timeScopeYear = costSession.timeScopeYear;
  const setTimeScopeYear = (value: SetStateAction<string>) => setCostSessionField("timeScopeYear", value);
  const timeScopeMonth = costSession.timeScopeMonth;
  const setTimeScopeMonth = (value: SetStateAction<string>) => setCostSessionField("timeScopeMonth", value);

  const [explorerData, setExplorerData] = useState<CostStatisticsExplorer | null>(() =>
    getCachedCostStatisticsExplorer(DEFAULT_MONTH, "active"),
  );
  const [exportReferenceData, setExportReferenceData] = useState<CostStatisticsExplorer | null>(() =>
    getCachedCostStatisticsExplorer("all", "active"),
  );
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
  const [domainRefreshNonce, setDomainRefreshNonce] = useState(0);

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
  const bankScopeMode = costSession.bankScopeMode;
  const setBankScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("bankScopeMode", value);
  const [bankScopePanel, setBankScopePanel] = useState<ScopePickerPanel | null>(null);
  const bankScopeYear = costSession.bankScopeYear;
  const setBankScopeYear = (value: SetStateAction<string>) => setCostSessionField("bankScopeYear", value);
  const bankScopeMonth = costSession.bankScopeMonth;
  const setBankScopeMonth = (value: SetStateAction<string>) => setCostSessionField("bankScopeMonth", value);

  const expenseTypeScopeMode = costSession.expenseTypeScopeMode;
  const setExpenseTypeScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("expenseTypeScopeMode", value);
  const [expenseTypeScopePanel, setExpenseTypeScopePanel] = useState<ScopePickerPanel | null>(null);
  const expenseTypeScopeYear = costSession.expenseTypeScopeYear;
  const setExpenseTypeScopeYear = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeYear", value);
  const expenseTypeScopeMonth = costSession.expenseTypeScopeMonth;
  const setExpenseTypeScopeMonth = (value: SetStateAction<string>) => setCostSessionField("expenseTypeScopeMonth", value);
  const [expenseTypeRangeMode, setExpenseTypeRangeMode] = useState<ExportRangeMode>("month");
  const [expenseTypeMonth, setExpenseTypeMonth] = useState(DEFAULT_MONTH);
  const [expenseTypeStartDate, setExpenseTypeStartDate] = useState(defaultMonthBounds.startDate);
  const [expenseTypeEndDate, setExpenseTypeEndDate] = useState(defaultMonthBounds.endDate);
  const [expenseTypeSelections, setExpenseTypeSelections] = useState<string[]>([]);
  const bankTagScopeMode = costSession.bankTagScopeMode;
  const setBankTagScopeMode = (value: SetStateAction<ExplorerScopeMode>) => setCostSessionField("bankTagScopeMode", value);
  const [bankTagScopePanel, setBankTagScopePanel] = useState<ScopePickerPanel | null>(null);
  const bankTagScopeYear = costSession.bankTagScopeYear;
  const setBankTagScopeYear = (value: SetStateAction<string>) => setCostSessionField("bankTagScopeYear", value);
  const bankTagScopeMonth = costSession.bankTagScopeMonth;
  const setBankTagScopeMonth = (value: SetStateAction<string>) => setCostSessionField("bankTagScopeMonth", value);

  const [selectedTimeTransactionId, setSelectedTimeTransactionId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [selectedProjectExpenseType, setSelectedProjectExpenseType] = useState<string | null>(null);
  const [selectedProjectTransactionId, setSelectedProjectTransactionId] = useState<string | null>(null);
  const [selectedBankAccountLabel, setSelectedBankAccountLabel] = useState<string | null>(null);
  const [selectedBankProjectName, setSelectedBankProjectName] = useState<string | null>(null);
  const [selectedBankTransactionId, setSelectedBankTransactionId] = useState<string | null>(null);
  const [selectedExpenseType, setSelectedExpenseType] = useState<string | null>(null);
  const [selectedExpenseTransactionId, setSelectedExpenseTransactionId] = useState<string | null>(null);
  const [selectedBankTagPrimaryLabel, setSelectedBankTagPrimaryLabel] = useState<string | null>(null);
  const [selectedBankTagSubLabel, setSelectedBankTagSubLabel] = useState<string | null>(null);
  const [selectedBankTagTransactionId, setSelectedBankTagTransactionId] = useState<string | null>(null);
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
        : viewMode === "bankTag"
          ? bankTagScopeMode === "month"
            ? bankTagScopeMonth
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
    setSelectedBankTagTransactionId(null);
  }

  const handleDomainMutation = useCallback(() => {
    clearCostStatisticsExplorerCache();
    setDomainRefreshNonce((current) => current + 1);
  }, []);
  const handleManualRefresh = useCallback(() => {
    clearCostStatisticsExplorerCache();
    setDomainRefreshNonce((current) => current + 1);
  }, []);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, handleDomainMutation);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleDomainMutation);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.turnoverRelationUpdated, handleDomainMutation);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, handleDomainMutation);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.etcBusinessBatchUpdated, handleDomainMutation);

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
      setSelectedBankTagPrimaryLabel(null);
      setSelectedBankTagSubLabel(null);
      resetDetailSelection();

      if (cachedPayload) {
        setExplorerData(cachedPayload);
        setIsExplorerLoading(false);
      } else if (hasVisibleData) {
        setIsExplorerLoading(false);
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
      } catch (caught) {
        if (!controller.signal.aborted) {
          setLoadError(getCostStatisticsLoadErrorMessage(caught));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsExplorerLoading(false);
        }
      }
    }

    void loadExplorer();
    return () => controller.abort();
  }, [costProjectScope, domainRefreshNonce, explorerMonth]);

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
	  }, [viewMode, timeScopeMode, timeScopeYear, timeScopeMonth]);

  useEffect(() => {
    if (viewMode !== "project") {
      return;
    }
    setSelectedProjectName(null);
	    setSelectedProjectExpenseType(null);
	    setSelectedProjectTransactionId(null);
	    setTransactionDetail(null);
	  }, [viewMode, projectScopeMode, projectScopeYear, projectScopeMonth]);

  useEffect(() => {
    if (viewMode !== "bank") {
      return;
    }
    setSelectedBankAccountLabel(null);
	    setSelectedBankProjectName(null);
	    setSelectedBankTransactionId(null);
	    setTransactionDetail(null);
	  }, [viewMode, bankScopeMode, bankScopeYear, bankScopeMonth]);

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
	  ]);

  useEffect(() => {
    if (viewMode !== "bankTag") {
      return;
    }
    setSelectedBankTagPrimaryLabel(null);
	    setSelectedBankTagSubLabel(null);
	    setSelectedBankTagTransactionId(null);
	    setTransactionDetail(null);
	  }, [viewMode, bankTagScopeMode, bankTagScopeYear, bankTagScopeMonth]);

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
	      ),
	    [explorerData, timeScopeMode, timeScopeYear, timeScopeMonth],
	  );
  const timeTotalAmount = useMemo(() => formatMoney(sumCostTimeRows(filteredTimeRows)), [filteredTimeRows]);
  const filteredProjectTimeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
	        projectScopeMode,
	        projectScopeYear,
	        projectScopeMonth,
	      ),
	    [explorerData, projectScopeMode, projectScopeYear, projectScopeMonth],
	  );
  const projectTotalAmount = useMemo(() => formatMoney(sumCostTimeRows(filteredProjectTimeRows)), [filteredProjectTimeRows]);
  const projectRows = useMemo(() => buildProjectRowsFromTimeRows(filteredProjectTimeRows), [filteredProjectTimeRows]);
  const filteredBankTimeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
	        bankScopeMode,
	        bankScopeYear,
	        bankScopeMonth,
	      ),
	    [explorerData, bankScopeMode, bankScopeYear, bankScopeMonth],
	  );
  const bankRows = useMemo(
    () => buildBankRowsFromTimeRowsAndAccounts(filteredBankTimeRows, explorerData?.bankAccounts ?? []),
    [explorerData, filteredBankTimeRows],
  );
  const bankTotalAmount = useMemo(() => formatMoney(sumCostTimeRows(filteredBankTimeRows)), [filteredBankTimeRows]);
  const filteredExpenseTypeRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
	        expenseTypeScopeMode,
	        expenseTypeScopeYear,
	        expenseTypeScopeMonth,
	      ),
	    [
	      explorerData,
	      expenseTypeScopeMode,
	      expenseTypeScopeYear,
	      expenseTypeScopeMonth,
	    ],
	  );
  const expenseTypeTotalAmount = useMemo(() => formatMoney(sumCostTimeRows(filteredExpenseTypeRows)), [filteredExpenseTypeRows]);
  const expenseTypeRows = useMemo(
    () => buildExpenseTypeRowsFromTimeRows(filteredExpenseTypeRows),
    [filteredExpenseTypeRows],
  );
  const filteredBankTagRows = useMemo(
    () =>
      filterScopeTimeRows(
        explorerData?.timeRows ?? [],
	        bankTagScopeMode,
	        bankTagScopeYear,
	        bankTagScopeMonth,
	      ),
	    [explorerData, bankTagScopeMode, bankTagScopeYear, bankTagScopeMonth],
	  );
  const bankTagTotalAmount = useMemo(() => formatMoney(sumCostTimeRows(filteredBankTagRows)), [filteredBankTagRows]);
  const bankTagPrimaryRows = useMemo(
    () => buildBankTagPrimaryRowsFromTimeRows(filteredBankTagRows),
    [filteredBankTagRows],
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
  const selectedBankTagPrimaryRows = useMemo(
    () => filteredBankTagRows.filter((row) => bankTagPrimaryLabel(row) === selectedBankTagPrimaryLabel),
    [filteredBankTagRows, selectedBankTagPrimaryLabel],
  );
  const bankTagSubRows = useMemo(
    () => buildBankTagSubRowsFromTimeRows(selectedBankTagPrimaryRows),
    [selectedBankTagPrimaryRows],
  );
  const selectedBankTagSubRows = useMemo(
    () => selectedBankTagPrimaryRows.filter((row) => bankTagSubLabel(row) === selectedBankTagSubLabel),
    [selectedBankTagPrimaryRows, selectedBankTagSubLabel],
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

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(bankTagScopeYear)) {
      setBankTagScopeYear(availableScopeYears[0]);
    }
  }, [availableScopeYears, bankTagScopeYear]);

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
	    return formatMonthLabel(projectScopeMonth);
	  }, [projectScopeMode, projectScopeYear, projectScopeMonth]);

	  const timeScopeLabel = useMemo(() => {
	    if (timeScopeMode === "all") {
	      return "全部时间";
	    }
	    if (timeScopeMode === "year") {
	      return `${timeScopeYear}年`;
	    }
	    return formatMonthLabel(timeScopeMonth);
	  }, [timeScopeMode, timeScopeYear, timeScopeMonth]);

	  const bankScopeLabel = useMemo(() => {
	    if (bankScopeMode === "all") {
	      return "全部时间";
	    }
	    if (bankScopeMode === "year") {
	      return `${bankScopeYear}年`;
	    }
	    return formatMonthLabel(bankScopeMonth);
	  }, [bankScopeMode, bankScopeYear, bankScopeMonth]);

	  const expenseTypeScopeLabel = useMemo(() => {
	    if (expenseTypeScopeMode === "all") {
	      return "全部时间";
	    }
	    if (expenseTypeScopeMode === "year") {
	      return `${expenseTypeScopeYear}年`;
	    }
	    return formatMonthLabel(expenseTypeScopeMonth);
	  }, [expenseTypeScopeMode, expenseTypeScopeYear, expenseTypeScopeMonth]);

	  const bankTagScopeLabel = useMemo(() => {
	    if (bankTagScopeMode === "all") {
	      return "全部时间";
	    }
	    if (bankTagScopeMode === "year") {
	      return `${bankTagScopeYear}年`;
	    }
	    return formatMonthLabel(bankTagScopeMonth);
	  }, [bankTagScopeMode, bankTagScopeYear, bankTagScopeMonth]);

  const readModelStatus = explorerData?.readModelStatus?.trim().toLowerCase();
  const isReadModelRefreshing = readModelStatus === "refreshing";
  const isReadModelStale = readModelStatus === "stale";
  const isReadModelUnavailable = readModelStatus === "unavailable"
    || readModelStatus === "failed"
    || readModelStatus === "missing"
    || readModelStatus === "schema_mismatch";
  const isReadModelNonFresh = Boolean(readModelStatus && readModelStatus !== "fresh");
  const readModelStatusMessage = isReadModelRefreshing
    ? "成本统计读模型正在刷新，当前结果生成后会自动更新。"
    : isReadModelStale
      ? "成本统计读模型不是最新，当前结果刷新完成后会自动更新。"
      : isReadModelUnavailable
        ? "成本统计数据暂不可用，请等待后台刷新完成后重试。"
        : null;

  const isRootEmpty = !isExplorerLoading && !loadError && explorerData && !isReadModelNonFresh
    ? viewMode === "time"
      ? filteredTimeRows.length === 0
      : viewMode === "project"
        ? filteredProjectTimeRows.length === 0
        : viewMode === "bank"
          ? bankRows.length === 0
          : viewMode === "bankTag"
            ? filteredBankTagRows.length === 0
          : filteredExpenseTypeRows.length === 0
    : false;

  async function openTransactionDetail(row: CostTimeRow, source: "time" | "project" | "bank" | "expenseType" | "bankTag") {
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
    if (source === "bankTag") {
      setSelectedBankTagTransactionId(row.transactionId);
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
    setBankTagScopePanel(null);
    startTransition(() => {
      setViewMode(nextViewMode);
    });
  }

  function toggleScopeSelection(
    currentPanel: ScopePickerPanel | null,
    setPanel: (panel: ScopePickerPanel | null) => void,
  ) {
    setPanel(currentPanel === "scope" ? null : "scope");
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
      setBankTagScopePanel(null);
    }

    const hasOpenPanel =
      (viewMode === "time" && timeScopePanel !== null) ||
      (viewMode === "project" && projectScopePanel !== null) ||
      (viewMode === "bank" && bankScopePanel !== null) ||
      (viewMode === "expenseType" && expenseTypeScopePanel !== null) ||
      (viewMode === "bankTag" && bankTagScopePanel !== null);

    if (!hasOpenPanel) {
      return;
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [viewMode, timeScopePanel, projectScopePanel, bankScopePanel, expenseTypeScopePanel, bankTagScopePanel]);

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
	      );
	      setExpenseTypeRangeMode(rangeMode);
	      setExpenseTypeMonth(expenseTypeScopeMonth);
	      setExpenseTypeStartDate(bounds.startDate);
	      setExpenseTypeEndDate(bounds.endDate);
      setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
	    } else {
	      setExportCenterMode("time");
	      const rangeMode = timeScopeMode === "month" ? "month" : "custom";
	      const bounds = getScopeDateRange(timeRows, timeScopeMode, timeScopeYear, timeScopeMonth);
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
    } catch (caught) {
      setExportFeedback({
        tone: "error",
        message: caught instanceof Error ? caught.message : "成本统计导出失败，请稍后重试。",
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
    } catch (caught) {
      setExportFeedback({
        tone: "error",
        message: caught instanceof Error ? caught.message : "导出预览加载失败，请稍后重试。",
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
      { key: "tradeTime", header: "时间", width: 170, render: (row) => formatCostTradeTime(row.tradeTime) },
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
      { key: "tradeTime", header: "时间", width: 170, render: (row) => formatCostTradeTime(row.tradeTime) },
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

  const hasExplorerLoadError = Boolean(loadError) && !explorerData;
  const activeTransactionId =
    selectedTimeTransactionId
    ?? selectedProjectTransactionId
    ?? selectedBankTransactionId
    ?? selectedExpenseTransactionId
    ?? selectedBankTagTransactionId;
  const isExportActionBusy = isExporting || isPreviewLoading || Boolean(detailLoadingMessage);
  const titleAccessory = canAdminAccess ? (
    <PageBusinessAuditIcon
      ariaLabel="Audit 成本统计"
      domainKey="cost_statistics"
      label="成本统计"
      readModelStatus={readModelStatus}
    />
  ) : null;

  return (
    <div className="page-stack cost-page">
	      <header className="page-header">
	        <div>
	          <div className="page-title-row">
	            <h1 className="page-title">成本统计</h1>
	            {titleAccessory ? <div className="page-title-accessory">{titleAccessory}</div> : null}
	          </div>
	        </div>
        <div className="page-header-actions cost-header-actions">
          <button
            aria-label="刷新成本统计"
            className="cost-export-button cost-refresh-button"
            type="button"
            disabled={isExplorerLoading || Boolean(detailLoadingMessage)}
            onClick={handleManualRefresh}
          >
            刷新
          </button>
          <button
            className="cost-export-button"
            type="button"
            disabled={isExplorerLoading || Boolean(detailLoadingMessage) || hasExplorerLoadError || isReadModelNonFresh}
            onClick={openExportCenter}
          >
            导出中心
	          </button>
	        </div>
	      </header>

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
              className={viewMode === "bankTag" ? "cost-view-tab active" : "cost-view-tab"}
              type="button"
              onClick={() => handleViewModeChange("bankTag")}
	            >
	              按流水标签类型
	            </button>
	          </div>
	        </div>

        {loadError ? <div className="state-panel error">{loadError}</div> : null}
        {isExplorerLoading && !explorerData ? (
          <div className="state-panel">正在加载成本统计数据...</div>
        ) : null}
        {detailLoadingMessage ? <div className="state-panel">{detailLoadingMessage}</div> : null}
        {readModelStatusMessage ? (
          <div className={`state-panel${isReadModelUnavailable ? " error" : ""}`} role="status">
            {readModelStatusMessage}
          </div>
        ) : null}
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
                  : viewMode === "bankTag"
                    ? "当前时间范围没有可用于流水标签统计的支出流水。"
                  : "当前时间范围没有可用于成本统计的支出流水。"}
          </div>
        ) : null}

        {!isExplorerLoading && explorerData && !isReadModelNonFresh ? (
          <>
            {viewMode === "time" ? (
              <div className="cost-analysis-layout time-layout single-column">
                <section className="cost-table-section">
                  <div className="cost-section-heading cost-view-scope-heading">
                    <div className="cost-section-heading-copy">
                      <h2>按时间统计</h2>
                      <span>{timeScopeLabel}</span>
                      <strong className="cost-section-total">总金额 {timeTotalAmount}</strong>
	                    </div>
	                    <div className="cost-section-heading-actions cost-project-scope-actions">
	                      <div ref={scopeControlsRef} className="cost-scope-controls">
	                        <ScopeRangePicker
	                          ariaLabel="时间统计时间范围"
	                          label="时间范围"
	                          mode={timeScopeMode}
	                          years={availableScopeYears}
	                          year={timeScopeYear}
	                          month={timeScopeMonth}
	                          open={timeScopePanel === "scope"}
	                          onToggle={() => toggleScopeSelection(timeScopePanel, setTimeScopePanel)}
	                          onModeChange={setTimeScopeMode}
	                          onYearChange={setTimeScopeYear}
	                          onMonthChange={setTimeScopeMonth}
	                          onClose={() => setTimeScopePanel(null)}
	                        />
	                      </div>
	                    </div>
                  </div>
                  <CostStatisticsTable
                    ariaLabel="按时间统计表"
                    columns={timeColumns}
                    rows={filteredTimeRows}
                    getRowKey={getCostTimeRowRenderKey}
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
                    <strong className="cost-section-total">总金额 {projectTotalAmount}</strong>
	                  </div>
	                  <div className="cost-section-heading-actions cost-project-scope-actions">
	                    <div ref={scopeControlsRef} className="cost-scope-controls">
	                      <ScopeRangePicker
	                        ariaLabel="项目统计时间范围"
	                        label="时间范围"
	                        mode={projectScopeMode}
	                        years={availableScopeYears}
	                        year={projectScopeYear}
	                        month={projectScopeMonth}
	                        open={projectScopePanel === "scope"}
	                        onToggle={() => toggleScopeSelection(projectScopePanel, setProjectScopePanel)}
	                        onModeChange={setProjectScopeMode}
	                        onYearChange={setProjectScopeYear}
	                        onMonthChange={setProjectScopeMonth}
	                        onClose={() => setProjectScopePanel(null)}
	                      />
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
                        getRowKey={getCostTimeRowRenderKey}
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
                    <strong className="cost-section-total">总金额 {bankTotalAmount}</strong>
	                  </div>
	                  <div className="cost-section-heading-actions cost-project-scope-actions">
	                    <div ref={scopeControlsRef} className="cost-scope-controls">
	                      <ScopeRangePicker
	                        ariaLabel="银行统计时间范围"
	                        label="时间范围"
	                        mode={bankScopeMode}
	                        years={availableScopeYears}
	                        year={bankScopeYear}
	                        month={bankScopeMonth}
	                        open={bankScopePanel === "scope"}
	                        onToggle={() => toggleScopeSelection(bankScopePanel, setBankScopePanel)}
	                        onModeChange={setBankScopeMode}
	                        onYearChange={setBankScopeYear}
	                        onMonthChange={setBankScopeMonth}
	                        onClose={() => setBankScopePanel(null)}
	                      />
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
                        getRowKey={getCostTimeRowRenderKey}
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
                    <strong className="cost-section-total">总金额 {expenseTypeTotalAmount}</strong>
	                  </div>
	                  <div className="cost-section-heading-actions cost-project-scope-actions">
	                    <div ref={scopeControlsRef} className="cost-scope-controls">
	                      <ScopeRangePicker
	                        ariaLabel="费用类型统计时间范围"
	                        label="时间范围"
	                        mode={expenseTypeScopeMode}
	                        years={availableScopeYears}
	                        year={expenseTypeScopeYear}
	                        month={expenseTypeScopeMonth}
	                        open={expenseTypeScopePanel === "scope"}
	                        onToggle={() => toggleScopeSelection(expenseTypeScopePanel, setExpenseTypeScopePanel)}
	                        onModeChange={setExpenseTypeScopeMode}
	                        onYearChange={setExpenseTypeScopeYear}
	                        onMonthChange={setExpenseTypeScopeMonth}
	                        onClose={() => setExpenseTypeScopePanel(null)}
	                      />
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
                        getRowKey={getCostTimeRowRenderKey}
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

            {viewMode === "bankTag" ? (
              <div className="cost-analysis-layout explorer-layout">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按流水标签类型统计</h2>
                    <span>{bankTagScopeLabel}</span>
                    <strong className="cost-section-total">总金额 {bankTagTotalAmount}</strong>
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <div ref={scopeControlsRef} className="cost-scope-controls">
                      <ScopeRangePicker
                        ariaLabel="流水标签统计时间范围"
                        label="时间范围"
                        mode={bankTagScopeMode}
                        years={availableScopeYears}
                        year={bankTagScopeYear}
                        month={bankTagScopeMonth}
                        open={bankTagScopePanel === "scope"}
                        onToggle={() => toggleScopeSelection(bankTagScopePanel, setBankTagScopePanel)}
                        onModeChange={setBankTagScopeMode}
                        onYearChange={setBankTagScopeYear}
                        onMonthChange={setBankTagScopeMonth}
                        onClose={() => setBankTagScopePanel(null)}
                      />
                    </div>
                  </div>
                </div>
                <div className="cost-explorer-grid bank-tag">
                  <CostExplorerList<CostBankTagPrimaryRow>
                    title="主标签"
                    count={bankTagPrimaryRows.length}
                    items={bankTagPrimaryRows}
                    emptyLabel="当前时间范围没有流水标签数据。"
                    getKey={(row) => row.primaryLabel}
                    isActive={(row) => row.primaryLabel === selectedBankTagPrimaryLabel}
                    onSelect={(row) => {
                      setSelectedBankTagPrimaryLabel(row.primaryLabel);
                      setSelectedBankTagSubLabel(null);
                      setSelectedBankTagTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.primaryLabel}
                    renderSecondary={(row) => `${row.transactionCount} 条流水 / ${row.subTagCount} 个子标签`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <span>{row.totalAmount}</span>
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <CostExplorerList<CostBankTagSubRow>
                    title="子标签"
                    count={bankTagSubRows.length}
                    items={bankTagSubRows}
                    emptyLabel={selectedBankTagPrimaryLabel ? "该主标签下暂无子标签。" : "请先在左侧选择主标签。"}
                    getKey={(row) => `${row.primaryLabel}:${row.subLabel}`}
                    isActive={(row) => row.subLabel === selectedBankTagSubLabel}
                    onSelect={(row) => {
                      setSelectedBankTagSubLabel(row.subLabel);
                      setSelectedBankTagTransactionId(null);
                      setTransactionDetail(null);
                    }}
                    renderPrimary={(row) => row.subLabel}
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
                      <span>{selectedBankTagSubRows.length}</span>
                    </header>
                    {selectedBankTagPrimaryLabel && selectedBankTagSubLabel ? (
                      <CostStatisticsTable
                        ariaLabel="流水标签对应流水表"
                        columns={transactionColumns}
                        rows={selectedBankTagSubRows}
                        getRowKey={getCostTimeRowRenderKey}
                        onRowClick={(row) => void openTransactionDetail(row, "bankTag")}
                        getRowActionLabel={(row) => `查看流水 ${row.transactionId}`}
                        emptyLabel="该流水标签下暂无流水。"
                      />
                    ) : (
                      <div className="cost-explorer-empty">请先依次选择主标签和子标签。</div>
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
