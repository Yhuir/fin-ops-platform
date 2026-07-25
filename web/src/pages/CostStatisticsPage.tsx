import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";

import { formatMonthLabel } from "../components/MonthPicker";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import CostExplorerList from "../components/cost-statistics/CostExplorerList";
import CostStatisticsTagRulesDrawer from "../components/cost-statistics/CostStatisticsTagRulesDrawer";
import ExportCenterModal, {
  type ExportCenterMode,
  type ExportRangeMode,
} from "../components/cost-statistics/ExportCenterModal";
import CostStatisticsTable, {
  type CostStatisticsTableColumn,
} from "../components/cost-statistics/CostStatisticsTable";
import CostTransactionDetailModal from "../components/cost-statistics/CostTransactionDetailModal";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppStatusOverview } from "../contexts/AppHealthStatusContext";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  exportCostStatisticsView,
  fetchCostStatisticsExplorerPage,
  fetchCostStatisticsTagRules,
  fetchCostStatisticsExportPreview,
  fetchCostTransactionDetail,
  saveCostStatisticsTagRules,
  type CostExportParams,
  type PreviewCostExportParams,
} from "../features/cost-statistics/api";
import { ApiClientError } from "../features/apiClient";
import { formatCostAmount } from "../features/cost-statistics/format";
import { importWorkflowPath } from "../features/imports/importRoutes";
import type {
  CostBankExplorerRow,
  CostBankTagPrimaryExplorerRow,
  CostBankTagSubExplorerRow,
  CostExpenseTypeExplorerRow,
  CostProjectScope,
  CostProjectExplorerRow,
  CostStatisticsExplorerPage,
  CostStatisticsExplorerPageRequest,
  CostStatisticsExportPreview,
  CostStatisticsTagRules,
  CostTimeRow,
  CostTransactionDetail,
} from "../features/cost-statistics/types";

type CostViewMode = "time" | "project" | "bank" | "expenseType" | "bankTag";
type RangeScopeMode = "all" | "year" | "month";
type ExplorerScopeMode = RangeScopeMode;
type ScopePickerPanel = "scope";
type EffectiveCostPageState = "fresh" | "loading" | "refreshing" | "stale" | "unavailable" | "error";

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

function waitForCostRefreshRetry(signal: AbortSignal, delayMs = 150) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("The operation was aborted.", "AbortError"));
      return;
    }
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, delayMs);
    const abort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("The operation was aborted.", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
  });
}

// ponytail: one user load gets a bounded 30-second retry window; a manual reload starts a new attempt.
const COST_REFRESH_MAX_RETRIES = 200;

type LoadedCostStatisticsExplorer = {
  requestKey: string;
  payload: CostStatisticsExplorerPage;
};

type CostStatisticsExportReferenceData = {
  projects: CostProjectExplorerRow[];
  expenseTypes: CostExpenseTypeExplorerRow[];
};

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

function formatCostTradeTime(value: string) {
  const raw = String(value || "").trim();
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::(\d{2}))?/);
  if (!match) {
    return raw;
  }
  return `${match[1]} ${match[2]}${match[3] ? `:${match[3]}` : ""}`;
}

function DirectionAmount({
  amount,
  label,
  tone,
}: {
  amount: string;
  label: string;
  tone: "expense" | "income";
}) {
  const formattedAmount = formatCostAmount(amount);
  return (
    <span
      aria-label={`${label} ${formattedAmount}`}
      className={`cost-direction-amount cost-direction-amount--aligned cost-direction-amount--${tone}`}
    >
      <span className="cost-direction-amount-label">{label}</span>
      <span className="cost-direction-amount-value">{formattedAmount}</span>
    </span>
  );
}

function TransactionIdentity({ label, tradeTime }: { label: string; tradeTime: string }) {
  const formattedTradeTime = formatCostTradeTime(tradeTime);
  return (
    <span className="cost-transaction-identity grid min-w-0 justify-items-start gap-1.5">
      <span className="max-w-full text-left font-extrabold leading-5 text-[var(--fp-text)] [overflow-wrap:anywhere]">
        {label || "--"}
      </span>
      <time
        className="cost-transaction-time-chip inline-flex min-h-5 items-center whitespace-nowrap rounded-sm border border-[var(--fp-border)] bg-[var(--fp-surface-muted)] px-1.5 text-[11px] font-bold leading-none text-[var(--fp-text-muted)] tabular-nums"
        dateTime={tradeTime}
      >
        {formattedTradeTime || "--"}
      </time>
    </span>
  );
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

function getScopeDateRange(
  mode: ExplorerScopeMode,
  year: string,
  month: string,
  availableYears: string[],
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
  const years = availableYears.filter((value) => /^\d{4}$/.test(value)).sort();
  if (years.length === 0) {
    return buildMonthDateBounds(DEFAULT_MONTH);
  }
  return { startDate: `${years[0]}-01-01`, endDate: `${years[years.length - 1]}-12-31` };
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

function getCostStatisticsActionErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    const message = error.message.trim();
    if (message) {
      return message;
    }
  }
  return "成本统计规则保存失败，请稍后重试。";
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
  const { active, activationGeneration } = useOptionalPageActivation("cost-statistics");
  const navigate = useNavigate();
  const { setWorkbenchHeaderActions } = useAppChrome();
  const appStatusOverview = useAppStatusOverview();
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

  const [loadedExplorer, setLoadedExplorer] = useState<LoadedCostStatisticsExplorer | null>(null);
  const [pageStatistics, setPageStatistics] = useState<CostStatisticsExplorerPage["statistics"]>(undefined);
  const [exportReferenceData, setExportReferenceData] = useState<CostStatisticsExportReferenceData | null>(null);
  const [transactionDetail, setTransactionDetail] = useState<CostTransactionDetail | null>(null);
  const [isExplorerLoading, setIsExplorerLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isExportReferenceLoading, setIsExportReferenceLoading] = useState(false);
  const [detailLoadingMessage, setDetailLoadingMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [isExportCenterOpen, setIsExportCenterOpen] = useState(false);
  const [exportPreview, setExportPreview] = useState<CostStatisticsExportPreview | null>(null);
  const [exportCenterMode, setExportCenterMode] = useState<ExportCenterMode>("time");
  const [domainRefreshNonce, setDomainRefreshNonce] = useState(0);
  const [isTagRulesDrawerOpen, setIsTagRulesDrawerOpen] = useState(false);
  const [tagRules, setTagRules] = useState<CostStatisticsTagRules | null>(null);
  const [tagRuleDraftCodes, setTagRuleDraftCodes] = useState<string[]>([]);
  const [isTagRulesLoading, setIsTagRulesLoading] = useState(false);
  const [isTagRulesSaving, setIsTagRulesSaving] = useState(false);
  const [tagRulesError, setTagRulesError] = useState<string | null>(null);

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
  const pageTitleRef = useRef<HTMLHeadingElement | null>(null);
  const headerControlsRef = useRef<HTMLDivElement | null>(null);
  const headerActionsRef = useRef<HTMLDivElement | null>(null);
  const contentShellRef = useRef<HTMLElement | null>(null);
  const lockStatusRef = useRef<HTMLDivElement | null>(null);
  const lastLockedFocusRef = useRef<HTMLElement | null>(null);
  const shouldRestoreFocusRef = useRef(false);
  const explorerRequestRef = useRef<AbortController | null>(null);
  const exportReferenceRequestRef = useRef<AbortController | null>(null);
  const exportRequestRef = useRef<AbortController | null>(null);
  const exportPreviewRequestRef = useRef<AbortController | null>(null);
  const loadMoreRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);

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

  const activeScopeMode = viewMode === "time"
    ? timeScopeMode
    : viewMode === "project"
      ? projectScopeMode
      : viewMode === "bank"
        ? bankScopeMode
        : viewMode === "expenseType"
          ? expenseTypeScopeMode
          : bankTagScopeMode;
  const activeScopeYear = viewMode === "time"
    ? timeScopeYear
    : viewMode === "project"
      ? projectScopeYear
      : viewMode === "bank"
        ? bankScopeYear
        : viewMode === "expenseType"
          ? expenseTypeScopeYear
          : bankTagScopeYear;
  const activeScopeMonth = viewMode === "time"
    ? timeScopeMonth
    : viewMode === "project"
      ? projectScopeMonth
      : viewMode === "bank"
        ? bankScopeMonth
        : viewMode === "expenseType"
          ? expenseTypeScopeMonth
          : bankTagScopeMonth;
  const explorerScope = activeScopeMode === "all"
    ? "all"
    : activeScopeMode === "year"
      ? `year:${activeScopeYear}`
      : activeScopeMonth;
  const explorerView = viewMode === "expenseType"
    ? "expense_type"
    : viewMode === "bankTag"
      ? "bank_tag"
      : viewMode;
  const explorerRequest: CostStatisticsExplorerPageRequest = {
    scope: explorerScope,
    view: explorerView,
    projectScope: costProjectScope,
    pageSize: 50,
    ...(viewMode === "project" && selectedProjectName ? { projectName: selectedProjectName } : {}),
    ...(viewMode === "project" && selectedProjectExpenseType ? { expenseType: selectedProjectExpenseType } : {}),
    ...(viewMode === "bank" && selectedBankAccountLabel ? { paymentAccountLabel: selectedBankAccountLabel } : {}),
    ...(viewMode === "bank" && selectedBankProjectName ? { projectName: selectedBankProjectName } : {}),
    ...(viewMode === "expenseType" && selectedExpenseType ? { expenseType: selectedExpenseType } : {}),
    ...(viewMode === "bankTag" && selectedBankTagPrimaryLabel
      ? { bankTagPrimaryLabel: selectedBankTagPrimaryLabel }
      : {}),
    ...(viewMode === "bankTag" && selectedBankTagSubLabel ? { bankTagSubLabel: selectedBankTagSubLabel } : {}),
  };
  const explorerRequestKey = JSON.stringify(explorerRequest);
  const currentCostStatisticsScopeKey = `${costProjectScope}:${activeScopeMode === "month" ? activeScopeMonth : "all"}`;
  const appStatusCostScope = appStatusOverview?.domains
    .flatMap((domain) => domain.readModelScopes)
    .find((scope) => (
      scope.readModelKey === "cost_statistics"
      && scope.scopeKey === currentCostStatisticsScopeKey
    ));
  const appStatusReadModelStatus = appStatusCostScope?.status.trim().toLowerCase() ?? "";
  const explorerData = loadedExplorer?.requestKey === explorerRequestKey
    ? loadedExplorer.payload
    : null;

  const invalidateExportReferenceData = useCallback(() => {
    exportReferenceRequestRef.current?.abort();
    exportReferenceRequestRef.current = null;
    loadMoreRequestRef.current?.abort();
    loadMoreRequestRef.current = null;
    setExportReferenceData(null);
    setIsExportReferenceLoading(false);
  }, []);

  const resetDetailSelection = useCallback(() => {
    detailRequestRef.current?.abort();
    detailRequestRef.current = null;
    setTransactionDetail(null);
    setSelectedTimeTransactionId(null);
    setSelectedProjectTransactionId(null);
    setSelectedBankTransactionId(null);
    setSelectedExpenseTransactionId(null);
    setSelectedBankTagTransactionId(null);
    setDetailLoadingMessage(null);
  }, []);

  const handleManualRefresh = useCallback(() => {
    setLoadedExplorer(null);
    invalidateExportReferenceData();
    setDomainRefreshNonce((current) => current + 1);
  }, [invalidateExportReferenceData]);

  const openTagRulesDrawer = useCallback(() => {
    setTagRulesError(null);
    setIsTagRulesDrawerOpen(true);
  }, []);
  const closeTagRulesDrawer = useCallback(() => {
    if (isTagRulesSaving) {
      return;
    }
    setIsTagRulesDrawerOpen(false);
    setTagRulesError(null);
  }, [isTagRulesSaving]);
  const toggleTagRuleCode = useCallback((code: string) => {
    setTagRuleDraftCodes((current) => (
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code]
    ));
  }, []);
  const toggleTagRuleGroup = useCallback((codes: string[], checked: boolean) => {
    setTagRuleDraftCodes((current) => {
      const next = new Set(current);
      for (const code of codes) {
        if (checked) {
          next.add(code);
        } else {
          next.delete(code);
        }
      }
      return Array.from(next);
    });
  }, []);
  useEffect(() => {
    if (!active || !isTagRulesDrawerOpen) {
      return undefined;
    }
    const controller = new AbortController();
    async function loadTagRules() {
      setIsTagRulesLoading(true);
      setTagRulesError(null);
      try {
        const payload = await fetchCostStatisticsTagRules(controller.signal);
        if (!controller.signal.aborted) {
          setTagRules(payload);
          setTagRuleDraftCodes(payload.effectiveSelectedTagCodes);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setTagRulesError(getCostStatisticsLoadErrorMessage(caught));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsTagRulesLoading(false);
        }
      }
    }
    void loadTagRules();
    return () => controller.abort();
  }, [active, activationGeneration, isTagRulesDrawerOpen]);

  const saveTagRules = useCallback(async () => {
    if (!tagRules || isTagRulesSaving) {
      return;
    }
    setIsTagRulesSaving(true);
    setTagRulesError(null);
    invalidateExportReferenceData();
    try {
      const result = await saveCostStatisticsTagRules({
        expectedVersion: tagRules.version,
        selectedTagCodes: tagRuleDraftCodes,
      });
      setTagRules(result);
      setTagRuleDraftCodes(result.effectiveSelectedTagCodes);
      setLoadedExplorer(null);
      setDomainRefreshNonce((current) => current + 1);
      setIsTagRulesDrawerOpen(false);
    } catch (caught) {
      setTagRulesError(getCostStatisticsActionErrorMessage(caught));
    } finally {
      setIsTagRulesSaving(false);
    }
  }, [
    invalidateExportReferenceData,
    isTagRulesSaving,
    tagRuleDraftCodes,
    tagRules,
  ]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    explorerRequestRef.current?.abort();
    const controller = new AbortController();
    explorerRequestRef.current = controller;

    async function loadExplorer() {
      loadMoreRequestRef.current?.abort();
      loadMoreRequestRef.current = null;
      setIsLoadingMore(false);
      setLoadError(null);
      setExportFeedback(null);
      resetDetailSelection();
      setLoadedExplorer(null);
      setIsExplorerLoading(true);

      try {
        const request = JSON.parse(explorerRequestKey) as CostStatisticsExplorerPageRequest;
        const publishPayload = (payload: CostStatisticsExplorerPage) => {
          if (controller.signal.aborted) {
            return;
          }
          setPageStatistics(
            payload.readModelStatus === "fresh"
              && payload.statisticsStatus === "fresh"
              ? payload.statistics
              : undefined,
          );
          setLoadedExplorer({ requestKey: explorerRequestKey, payload });
          setIsExplorerLoading(false);
        };
        let payload = await fetchCostStatisticsExplorerPage({ ...request, signal: controller.signal });
        publishPayload(payload);
        for (
          let retry = 0;
          retry < COST_REFRESH_MAX_RETRIES
          && (
            payload.readModelStatus?.trim().toLowerCase() !== "fresh"
            || payload.statisticsStatus?.trim().toLowerCase() !== "fresh"
          )
          && !controller.signal.aborted;
          retry += 1
        ) {
          await waitForCostRefreshRetry(controller.signal);
          if (document.visibilityState !== "visible") {
            break;
          }
          payload = await fetchCostStatisticsExplorerPage({ ...request, signal: controller.signal });
          publishPayload(payload);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setPageStatistics(undefined);
          setLoadError(getCostStatisticsLoadErrorMessage(caught));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsExplorerLoading(false);
        }
      }
    }

    void loadExplorer();
    return () => {
      controller.abort();
      if (explorerRequestRef.current === controller) {
        explorerRequestRef.current = null;
      }
    };
  }, [active, activationGeneration, domainRefreshNonce, explorerRequestKey, resetDetailSelection]);

  async function loadMoreExplorerRows() {
    if (!explorerData?.nextCursor || isLoadingMore) {
      return;
    }
    loadMoreRequestRef.current?.abort();
    const controller = new AbortController();
    loadMoreRequestRef.current = controller;
    setIsLoadingMore(true);
    setLoadError(null);
    try {
      const request = JSON.parse(explorerRequestKey) as CostStatisticsExplorerPageRequest;
      const nextPage = await fetchCostStatisticsExplorerPage({
        ...request,
        cursor: explorerData.nextCursor,
        signal: controller.signal,
      });
      if (controller.signal.aborted) {
        return;
      }
      setLoadedExplorer((current) => current?.requestKey === explorerRequestKey
        ? {
            requestKey: explorerRequestKey,
            payload: {
              ...current.payload,
              rows: [...current.payload.rows, ...nextPage.rows],
              nextCursor: nextPage.nextCursor,
              rowCount: nextPage.rowCount,
            },
          }
        : current);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setLoadError(getCostStatisticsLoadErrorMessage(caught));
      }
    } finally {
      if (loadMoreRequestRef.current === controller) {
        loadMoreRequestRef.current = null;
        setIsLoadingMore(false);
      }
    }
  }

  useEffect(() => () => {
    explorerRequestRef.current?.abort();
    exportReferenceRequestRef.current?.abort();
    exportRequestRef.current?.abort();
    exportPreviewRequestRef.current?.abort();
    loadMoreRequestRef.current?.abort();
    detailRequestRef.current?.abort();
  }, []);

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

  const pageRows = explorerData?.rows ?? [];
  const availableScopeYears = explorerData?.availableYears ?? [];
  const filteredTimeRows = pageRows;
  const projectRows = explorerData?.facets.projects ?? [];
  const projectExpenseTypeRows = explorerData?.facets.expenseTypes ?? [];
  const bankRows = explorerData?.facets.bankAccounts ?? [];
  const bankProjectRows = explorerData?.facets.projects ?? [];
  const expenseTypeRows = explorerData?.facets.expenseTypes ?? [];
  const bankTagPrimaryRows = explorerData?.facets.bankTagPrimary ?? [];
  const bankTagSubRows = explorerData?.facets.bankTagSub ?? [];
  const selectedProjectTransactionRows = selectedProjectName && selectedProjectExpenseType ? pageRows : [];
  const selectedBankProjectRows = selectedBankAccountLabel && selectedBankProjectName ? pageRows : [];
  const selectedExpenseTypeRows = selectedExpenseType ? pageRows : [];
  const selectedBankTagSubRows = selectedBankTagPrimaryLabel && selectedBankTagSubLabel ? pageRows : [];
  const timeDirectionSummary = {
    expenseAmount: explorerData?.summary.expenseAmount ?? "0.00",
    incomeAmount: explorerData?.summary.incomeAmount ?? "0.00",
  };
  const bankTagDirectionSummary = timeDirectionSummary;
  const projectTotalAmount = explorerData?.summary.totalAmount ?? "0.00";
  const bankTotalAmount = explorerData?.summary.totalAmount ?? "0.00";
  const expenseTypeTotalAmount = explorerData?.summary.totalAmount ?? "0.00";

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
    () => (exportReferenceData?.projects ?? []).map((row) => row.projectName),
    [exportReferenceData],
  );
  const allExpenseTypeOptions = useMemo(
    () => (exportReferenceData?.expenseTypes ?? []).map((row) => row.expenseType),
    [exportReferenceData],
  );

  const projectExpenseTypeOptions = projectExportNames.length > 0 ? allExpenseTypeOptions : [];

  const readModelStatus = explorerData?.readModelStatus?.trim().toLowerCase() ?? "";
  const isReadModelRefreshing = readModelStatus === "refreshing"
    || readModelStatus === "loading"
    || readModelStatus === "pending"
    || readModelStatus === "processing";
  const isReadModelStale = readModelStatus === "stale"
    || readModelStatus === "schema_mismatch"
    || readModelStatus === "source_mismatch";
  const isReadModelUnavailable = readModelStatus === "unavailable"
    || readModelStatus === "failed"
    || readModelStatus === "missing";
  const isReadModelNonFresh = Boolean(explorerData && readModelStatus !== "fresh");
  const isAppStatusRefreshing = appStatusReadModelStatus === "loading"
    || appStatusReadModelStatus === "pending"
    || appStatusReadModelStatus === "processing"
    || appStatusReadModelStatus === "refreshing";
  const isAppStatusStale = appStatusReadModelStatus === "stale"
    || appStatusReadModelStatus === "schema_mismatch"
    || appStatusReadModelStatus === "source_mismatch";
  const isAppStatusUnavailable = appStatusReadModelStatus === "failed"
    || appStatusReadModelStatus === "unavailable"
    || appStatusReadModelStatus === "missing";
  const hasExplorerLoadError = Boolean(loadError) && !explorerData;
  const effectiveCostPageState: EffectiveCostPageState = hasExplorerLoadError
    ? "error"
    : isReadModelUnavailable || isAppStatusUnavailable
      ? "unavailable"
      : isReadModelStale || isAppStatusStale
        ? "stale"
        : isReadModelRefreshing || isAppStatusRefreshing || isTagRulesSaving
          ? "refreshing"
          : isExplorerLoading || !explorerData
            ? "loading"
            : readModelStatus === "fresh"
              ? "fresh"
              : "stale";
  const interactionLocked = effectiveCostPageState !== "fresh";
  const lockStatusCopy = effectiveCostPageState === "error"
    ? {
        title: "无法确认成本数据状态",
        detail: loadError || "网络恢复前页面保持锁定。",
      }
    : effectiveCostPageState === "unavailable"
      ? {
          title: "成本数据暂未就绪",
          detail: "页面保持锁定，请重新检查或稍后再试。",
        }
      : effectiveCostPageState === "stale"
        ? {
            title: "正在更新至最新数据",
            detail: "检测到事实已变化，旧数据暂不可操作。",
          }
        : effectiveCostPageState === "refreshing"
          ? {
              title: "成本数据正在同步",
              detail: "当前页面已暂时锁定，完成后自动恢复。",
            }
          : {
              title: "正在加载成本统计",
              detail: "数据就绪后将自动开放操作。",
            };
  const lockStatusCanRetry = effectiveCostPageState === "error" || effectiveCostPageState === "unavailable";

  useEffect(() => {
    if (interactionLocked) {
      const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const lockedRegions = [headerControlsRef.current, headerActionsRef.current, contentShellRef.current];
      const ownsActiveFocus = Boolean(activeElement && (
        lockedRegions.some((region) => region?.contains(activeElement))
        || activeElement.closest(".cost-detail-modal, .export-center-modal, .cost-tag-rules-drawer")
      ));
      if (activeElement && ownsActiveFocus) {
        lastLockedFocusRef.current = activeElement;
        shouldRestoreFocusRef.current = true;
        queueMicrotask(() => lockStatusRef.current?.focus());
      }
      setIsExportCenterOpen(false);
      setExportPreview(null);
      setTimeScopePanel(null);
      setProjectScopePanel(null);
      setBankScopePanel(null);
      setExpenseTypeScopePanel(null);
      setBankTagScopePanel(null);
      invalidateExportReferenceData();
      resetDetailSelection();
      return;
    }

    if (!shouldRestoreFocusRef.current) {
      return;
    }
    const currentFocus = document.activeElement;
    if (
      currentFocus instanceof HTMLElement
      && currentFocus !== document.body
      && !lockStatusRef.current?.contains(currentFocus)
    ) {
      shouldRestoreFocusRef.current = false;
      lastLockedFocusRef.current = null;
      return;
    }
    const previousFocus = lastLockedFocusRef.current;
    shouldRestoreFocusRef.current = false;
    lastLockedFocusRef.current = null;
    queueMicrotask(() => {
      if (
        previousFocus?.isConnected
        && !previousFocus.matches(":disabled")
        && !previousFocus.closest("[inert]")
      ) {
        previousFocus.focus();
        return;
      }
      pageTitleRef.current?.focus();
    });
  }, [interactionLocked, invalidateExportReferenceData, resetDetailSelection]);

  const isRootEmpty = !isExplorerLoading && !loadError && explorerData && !isReadModelNonFresh
    ? viewMode === "time"
      ? explorerData.rowCount === 0
      : viewMode === "project"
        ? projectRows.length === 0
        : viewMode === "bank"
          ? bankRows.length === 0
          : viewMode === "bankTag"
            ? bankTagPrimaryRows.length === 0
          : expenseTypeRows.length === 0
    : false;

  async function openTransactionDetail(row: CostTimeRow, source: "time" | "project" | "bank" | "expenseType" | "bankTag") {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
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
      const detailView =
        source === "bankTag"
          ? "bank_tag"
          : source === "expenseType"
            ? "expense_type"
            : source;
      const payload = await fetchCostTransactionDetail(
        row.transactionId,
        detailView,
        explorerScope,
        controller.signal,
        costProjectScope,
      );
      if (!controller.signal.aborted) {
        setTransactionDetail(payload);
      }
    } catch {
      if (!controller.signal.aborted) {
        setLoadError("流水详情加载失败，请稍后重试。");
      }
    } finally {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
        setDetailLoadingMessage(null);
      }
    }
  }

  function handleViewModeChange(nextViewMode: CostViewMode) {
    exportReferenceRequestRef.current?.abort();
    exportReferenceRequestRef.current = null;
    setIsExportReferenceLoading(false);
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

  function updateProjectExportSelection(
    projectNames: string[],
    referenceData: CostStatisticsExportReferenceData | null = exportReferenceData,
  ) {
    setProjectExportNames(projectNames);
    const nextExpenseTypes = projectNames.length > 0
      ? (referenceData?.expenseTypes ?? []).map((row) => row.expenseType)
      : [];
    setProjectExpenseTypes(nextExpenseTypes);
  }

  async function loadExportReferenceData(): Promise<CostStatisticsExportReferenceData | null> {
    if (exportReferenceData) {
      return exportReferenceData;
    }

    exportReferenceRequestRef.current?.abort();
    const controller = new AbortController();
    exportReferenceRequestRef.current = controller;
    setIsExportReferenceLoading(true);
    try {
      const [projectPage, expenseTypePage] = await Promise.all([
        fetchCostStatisticsExplorerPage({
          scope: "all",
          view: "project",
          projectScope: costProjectScope,
          pageSize: 1,
          signal: controller.signal,
        }),
        fetchCostStatisticsExplorerPage({
          scope: "all",
          view: "expense_type",
          projectScope: costProjectScope,
          pageSize: 1,
          signal: controller.signal,
        }),
      ]);
      if (controller.signal.aborted) {
        return null;
      }
      if ([projectPage, expenseTypePage].some((page) => page.readModelStatus?.trim().toLowerCase() !== "fresh")) {
        setExportFeedback({ tone: "error", message: "导出筛选数据正在刷新，请稍后重试。" });
        return null;
      }
      const referenceData = {
        projects: projectPage.facets.projects,
        expenseTypes: expenseTypePage.facets.expenseTypes,
      };
      setExportReferenceData(referenceData);
      return referenceData;
    } catch (caught) {
      if (!controller.signal.aborted) {
        setExportFeedback({
          tone: "error",
          message: `导出筛选数据加载失败：${getCostStatisticsLoadErrorMessage(caught)}`,
        });
      }
      return null;
    } finally {
      if (exportReferenceRequestRef.current === controller) {
        exportReferenceRequestRef.current = null;
        setIsExportReferenceLoading(false);
      }
    }
  }

  async function openExportCenter() {
    setExportFeedback(null);
    setExportPreview(null);
    const referenceData = viewMode === "project" || viewMode === "expenseType"
      ? await loadExportReferenceData()
      : null;
    if ((viewMode === "project" || viewMode === "expenseType") && !referenceData) {
      return;
    }
    if (viewMode === "project") {
      setExportCenterMode("project");
      const projectOptions = (referenceData?.projects ?? []).map((row) => row.projectName);
      const nextProjectNames =
        projectExportNames.length > 0
          ? projectExportNames
          : selectedProjectName
            ? [selectedProjectName]
            : projectOptions.slice(0, 1);
      updateProjectExportSelection(nextProjectNames, referenceData);
	    } else if (viewMode === "expenseType") {
	      setExportCenterMode("expense_type");
	      const rangeMode = expenseTypeScopeMode === "month" ? "month" : "custom";
	      const bounds = getScopeDateRange(
	        expenseTypeScopeMode,
	        expenseTypeScopeYear,
	        expenseTypeScopeMonth,
          availableScopeYears,
	      );
	      setExpenseTypeRangeMode(rangeMode);
	      setExpenseTypeMonth(expenseTypeScopeMonth);
	      setExpenseTypeStartDate(bounds.startDate);
	      setExpenseTypeEndDate(bounds.endDate);
      setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
    } else {
      const isBankTagExport = viewMode === "bankTag";
	      setExportCenterMode(isBankTagExport ? "bank_tag" : "time");
      const activeScopeMode = isBankTagExport ? bankTagScopeMode : timeScopeMode;
      const activeScopeYear = isBankTagExport ? bankTagScopeYear : timeScopeYear;
      const activeScopeMonth = isBankTagExport ? bankTagScopeMonth : timeScopeMonth;
	      const rangeMode = activeScopeMode === "month" ? "month" : "custom";
	      const bounds = getScopeDateRange(activeScopeMode, activeScopeYear, activeScopeMonth, availableScopeYears);
	      setTimeRangeMode(rangeMode);
	      setTimeMonth(activeScopeMonth);
	      setTimeStartDate(bounds.startDate);
      setTimeEndDate(bounds.endDate);
    }
    setIsExportCenterOpen(true);
  }

  async function handleExportCenterModeChange(mode: ExportCenterMode) {
    setExportFeedback(null);
    setExportPreview(null);
    if (mode === "time" || mode === "bank_tag") {
      exportReferenceRequestRef.current?.abort();
      exportReferenceRequestRef.current = null;
      setIsExportReferenceLoading(false);
    }
    const referenceData = mode === "project" || mode === "expense_type"
      ? await loadExportReferenceData()
      : null;
    if ((mode === "project" || mode === "expense_type") && !referenceData) {
      return;
    }
    setExportCenterMode(mode);
    if (mode === "project") {
      const projectOptions = (referenceData?.projects ?? []).map((row) => row.projectName);
      const nextProjectNames =
        projectExportNames.length > 0
          ? projectExportNames
          : selectedProjectName
            ? [selectedProjectName]
            : projectOptions.slice(0, 1);
      updateProjectExportSelection(nextProjectNames, referenceData);
    }
    if (mode === "expense_type" && expenseTypeSelections.length === 0) {
      setExpenseTypeSelections(selectedExpenseType ? [selectedExpenseType] : []);
    }
  }

  function buildExportParamsFromState(): CostExportParams | null {
    if (exportCenterMode === "time" || exportCenterMode === "bank_tag") {
      if (timeRangeMode === "month") {
        return {
          month: timeMonth,
          view: exportCenterMode,
          projectScope: costProjectScope,
        };
      }
      return {
        month: "all",
        view: exportCenterMode,
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
    exportRequestRef.current?.abort();
    const controller = new AbortController();
    exportRequestRef.current = controller;
    setDetailLoadingMessage(null);
    setLoadError(null);
    setExportFeedback(null);
    setIsExporting(true);
    try {
      const { blob, fileName } = await exportCostStatisticsView(params, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
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
      if (controller.signal.aborted || isAbortLikeError(caught)) {
        return;
      }
      setExportFeedback({
        tone: "error",
        message: caught instanceof Error ? caught.message : "成本统计导出失败，请稍后重试。",
      });
    } finally {
      if (exportRequestRef.current === controller) {
        exportRequestRef.current = null;
        setIsExporting(false);
      }
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
    exportPreviewRequestRef.current?.abort();
    const controller = new AbortController();
    exportPreviewRequestRef.current = controller;
    setExportFeedback(null);
    setIsPreviewLoading(true);
    try {
      const payload = await fetchCostStatisticsExportPreview(params, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setExportPreview(payload);
    } catch (caught) {
      if (controller.signal.aborted || isAbortLikeError(caught)) {
        return;
      }
      setExportFeedback({
        tone: "error",
        message: caught instanceof Error ? caught.message : "导出预览加载失败，请稍后重试。",
      });
    } finally {
      if (exportPreviewRequestRef.current === controller) {
        exportPreviewRequestRef.current = null;
        setIsPreviewLoading(false);
      }
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
          amount: formatCostAmount(row.amount),
          direction: row.direction,
          paymentAccountLabel: row.paymentAccountLabel,
          toneByDirection: true,
        }),
      },
      { key: "expenseContent", header: "费用内容", flex: 1.2, render: (row) => row.expenseContent },
    ],
    [],
  );

  const transactionColumns = useMemo<CostStatisticsTableColumn<CostTimeRow>[]>(
    () => [
      viewMode === "expenseType"
        ? {
            key: "projectName",
            header: "项目名",
            flex: 1.15,
            getTextValue: (row) => `${row.projectName} ${formatCostTradeTime(row.tradeTime)}`,
            render: (row) => <TransactionIdentity label={row.projectName} tradeTime={row.tradeTime} />,
          }
        : {
            key: "counterpartyName",
            header: "对方户名",
            flex: 1.15,
            getTextValue: (row) => `${row.counterpartyName} ${formatCostTradeTime(row.tradeTime)}`,
            render: (row) => <TransactionIdentity label={row.counterpartyName} tradeTime={row.tradeTime} />,
          },
      {
        key: "amount",
        header: "金额",
        width: 180,
        cellClassName: "cost-table-cell-money",
        render: (row) => ({
          amount: formatCostAmount(row.amount),
          direction: row.direction,
          paymentAccountLabel: row.paymentAccountLabel,
          toneByDirection: viewMode === "bankTag",
        }),
      },
      { key: "expenseContent", header: "费用内容", flex: 1.1, render: (row) => row.expenseContent },
    ],
    [viewMode],
  );

  const activeTransactionId =
    selectedTimeTransactionId
    ?? selectedProjectTransactionId
    ?? selectedBankTransactionId
    ?? selectedExpenseTransactionId
    ?? selectedBankTagTransactionId;
  const isExportActionBusy = isExportReferenceLoading || isExporting || isPreviewLoading || Boolean(detailLoadingMessage);
  const visibleStatistics = pageStatistics;
  const titleAccessory = (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="成本统计数据统计"
        loading={isExplorerLoading && !pageStatistics}
        coreItems={[
          { label: "流水", value: visibleStatistics?.transactionCount, unit: "笔" },
          { label: "支出", value: visibleStatistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
          { label: "收入", value: visibleStatistics?.incomeTransactionCount, unit: "笔", tone: "income" },
        ]}
        detailItems={[
          { label: "OA 配对成本组", value: visibleStatistics?.costGroupCount, unit: "组" },
          { label: "有成本标签流水", value: visibleStatistics?.taggedTransactionCount, unit: "笔", tone: "success" },
          { label: "未标记流水", value: visibleStatistics?.untaggedTransactionCount, unit: "笔", tone: "warning" },
          { label: "项目", value: visibleStatistics?.projectCount, unit: "个" },
          { label: "费用类型", value: visibleStatistics?.expenseTypeCount, unit: "类" },
          { label: "银行标签", value: visibleStatistics?.bankTagCount, unit: "个" },
          { label: "已进入成本统计流水", value: visibleStatistics?.costTransactionCount, unit: "笔" },
        ]}
      />
      {canAdminAccess ? (
        <PageBusinessAuditIcon
          ariaLabel="Audit 成本统计"
          pageKey="cost-statistics"
          label="成本统计"
          readModelStatus={readModelStatus}
        />
      ) : null}
    </div>
  );

  return (
    <div className="page-stack cost-page">
      <header className="page-header cost-page-header">
        <div className="cost-page-header-main">
          <div className="page-title-row">
            <h1 className="page-title" ref={pageTitleRef} tabIndex={-1}>成本统计</h1>
            {titleAccessory ? <div className="page-title-accessory">{titleAccessory}</div> : null}
          </div>
          <div
            aria-busy={interactionLocked}
            aria-describedby={interactionLocked ? "cost-statistics-lock-status" : undefined}
            className={interactionLocked
              ? "cost-analysis-toolbar cost-lock-target is-locked"
              : "cost-analysis-toolbar cost-lock-target"}
            inert={interactionLocked ? true : undefined}
            ref={headerControlsRef}
          >
            <div className="cost-view-switcher" role="tablist" aria-label="成本统计视图切换">
              <div className="cost-view-group">
                <span className="cost-view-group-label">OA配对流水统计</span>
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
                  按OA费用类型
                </button>
              </div>
              <span className="cost-view-divider" aria-hidden="true" />
              <div className="cost-view-group">
                <span className="cost-view-group-label">流水统计</span>
                <button
                  className={viewMode === "bankTag" ? "cost-view-tab active" : "cost-view-tab"}
                  type="button"
                  onClick={() => handleViewModeChange("bankTag")}
                >
                  按标签
                </button>
                <button
                  className={viewMode === "time" ? "cost-view-tab active" : "cost-view-tab"}
                  type="button"
                  onClick={() => handleViewModeChange("time")}
                >
                  按时间
                </button>
              </div>
            </div>
          </div>
        </div>
        <div
          aria-busy={interactionLocked}
          aria-describedby={interactionLocked ? "cost-statistics-lock-status" : undefined}
          className={interactionLocked
            ? "page-header-actions cost-header-actions cost-lock-target is-locked"
            : "page-header-actions cost-header-actions cost-lock-target"}
          inert={interactionLocked ? true : undefined}
          ref={headerActionsRef}
        >
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
            disabled={isTagRulesSaving}
            onClick={openTagRulesDrawer}
          >
            成本统计标签规则
          </button>
          <button
            className="cost-export-button"
            type="button"
            disabled={isExplorerLoading || isExportReferenceLoading || Boolean(detailLoadingMessage) || hasExplorerLoadError || isReadModelNonFresh}
            onClick={() => void openExportCenter()}
          >
	          {isExportReferenceLoading ? "正在准备导出..." : "导出中心"}
	          </button>
	        </div>
	      </header>

	      <div className="cost-lock-surface" data-lock-state={effectiveCostPageState}>
        {interactionLocked ? (
          <div
            aria-atomic="true"
            aria-live="polite"
            className={`cost-lock-status cost-lock-status--${effectiveCostPageState}`}
            id="cost-statistics-lock-status"
            ref={lockStatusRef}
            role="status"
            tabIndex={-1}
          >
            <span className="cost-lock-status-indicator" aria-hidden="true" />
            <span className="cost-lock-status-copy">
              <strong>{lockStatusCopy.title}</strong>
              <small>{lockStatusCopy.detail}</small>
            </span>
            {lockStatusCanRetry ? (
              <button className="cost-lock-retry" type="button" onClick={handleManualRefresh}>
                重新检查
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="cost-lock-content">
	      <section
          aria-busy={interactionLocked}
          aria-describedby={interactionLocked ? "cost-statistics-lock-status" : undefined}
          className={interactionLocked
            ? "cost-content-shell cost-lock-target is-locked"
            : "cost-content-shell cost-lock-target"}
          inert={interactionLocked ? true : undefined}
          ref={contentShellRef}
        >
        {interactionLocked && !explorerData ? (
          <div className="cost-lock-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {loadError && explorerData ? <div className="state-panel error">{loadError}</div> : null}
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
                  ? "当前时间范围没有可用于 OA 费用类型统计的支出流水。"
                  : viewMode === "bankTag"
                    ? "当前时间范围没有可用于标签统计的收入或支出流水。"
                  : "当前时间范围没有可用于流水统计的收入或支出流水。"}
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
                      <div className="cost-direction-summary" aria-label="时间统计方向金额">
                        <DirectionAmount amount={timeDirectionSummary.expenseAmount} label="支出金额" tone="expense" />
                        <DirectionAmount amount={timeDirectionSummary.incomeAmount} label="收入金额" tone="income" />
                      </div>
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
                    emptyLabel="当前时间范围没有收入或支出流水。"
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
                    <DirectionAmount amount={projectTotalAmount} label="支出金额" tone="expense" />
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
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        {row.percentageLabel ? (
                          <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                        ) : null}
                      </div>
                    )}
                  />
                  <CostExplorerList<CostExpenseTypeExplorerRow>
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
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{explorerData?.rowCount ?? selectedProjectTransactionRows.length}</span>
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
                    <DirectionAmount amount={bankTotalAmount} label="支出金额" tone="expense" />
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
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
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
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{explorerData?.rowCount ?? selectedBankProjectRows.length}</span>
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
                    <h2>按OA费用类型统计</h2>
                    <DirectionAmount amount={expenseTypeTotalAmount} label="支出金额" tone="expense" />
	                  </div>
	                  <div className="cost-section-heading-actions cost-project-scope-actions">
	                    <div ref={scopeControlsRef} className="cost-scope-controls">
	                      <ScopeRangePicker
	                        ariaLabel="OA费用类型统计时间范围"
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
                  <CostExplorerList<CostExpenseTypeExplorerRow>
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
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        <em className="cost-explorer-percentage-badge">{row.percentageLabel}</em>
                      </div>
                    )}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{explorerData?.rowCount ?? selectedExpenseTypeRows.length}</span>
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
                    <h2>按标签统计</h2>
                    <div className="cost-direction-summary" aria-label="标签统计方向金额">
                      <DirectionAmount amount={bankTagDirectionSummary.expenseAmount} label="支出金额" tone="expense" />
                      <DirectionAmount amount={bankTagDirectionSummary.incomeAmount} label="收入金额" tone="income" />
                    </div>
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
                  <CostExplorerList<CostBankTagPrimaryExplorerRow>
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
                    renderSecondary={(row) => (
                      `支出 ${row.expenseTransactionCount} 笔 / 收入 ${row.incomeTransactionCount} 笔 / ${row.subTagCount} 个子标签`
                    )}
                    renderMeta={(row) => (
                      <div className="cost-direction-meta">
                        <DirectionAmount amount={row.expenseAmount} label="支出" tone="expense" />
                        <DirectionAmount amount={row.incomeAmount} label="收入" tone="income" />
                      </div>
                    )}
                  />
                  <CostExplorerList<CostBankTagSubExplorerRow>
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
                    renderSecondary={(row) => `支出 ${row.expenseTransactionCount} 笔 / 收入 ${row.incomeTransactionCount} 笔`}
                    renderMeta={(row) => (
                      <div className="cost-direction-meta">
                        <DirectionAmount amount={row.expenseAmount} label="支出" tone="expense" />
                        <DirectionAmount amount={row.incomeAmount} label="收入" tone="income" />
                      </div>
                    )}
                  />
                  <section className="cost-explorer-lane cost-explorer-lane-table">
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <span>{explorerData?.rowCount ?? selectedBankTagSubRows.length}</span>
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
            {explorerData.nextCursor ? (
              <div className="cost-load-more">
                <button
                  className="cost-export-button"
                  type="button"
                  disabled={isLoadingMore}
                  onClick={() => void loadMoreExplorerRows()}
                >
                  {isLoadingMore ? "正在加载更多..." : `加载更多（已显示 ${explorerData.rows.length} / ${explorerData.rowCount}）`}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>
          {interactionLocked ? (
            <div
              aria-hidden="true"
              className="cost-lock-overlay"
              data-testid="cost-statistics-interaction-overlay"
            />
          ) : null}
        </div>
      </div>

      {transactionDetail && activeTransactionId ? (
        <CostTransactionDetailModal
          detail={transactionDetail.transaction}
          onClose={() => {
            resetDetailSelection();
            setTransactionDetail(null);
          }}
        />
      ) : null}

      <CostStatisticsTagRulesDrawer
        canSave={canMutateData && !interactionLocked && (tagRules?.canSave ?? true)}
        error={tagRulesError}
        interactionLocked={interactionLocked}
        loading={isTagRulesLoading}
        onClose={closeTagRulesDrawer}
        onSave={() => void saveTagRules()}
        onToggleCode={toggleTagRuleCode}
        onToggleGroup={toggleTagRuleGroup}
        open={isTagRulesDrawerOpen}
        rules={tagRules}
        saving={isTagRulesSaving}
        selectedCodes={tagRuleDraftCodes}
      />

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
          onModeChange={(mode) => void handleExportCenterModeChange(mode)}
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
