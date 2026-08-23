import { startTransition, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import {
  Button,
  Chip,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import { useNavigate } from "react-router-dom";

import BusinessPeriodPicker from "../components/common/BusinessPeriodPicker";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import QuerySearch from "../components/common/QuerySearch";
import CostExplorerList from "../components/cost-statistics/CostExplorerList";
import CostStatisticsNoOaRulesDrawer from "../components/cost-statistics/CostStatisticsNoOaRulesDrawer";
import CostStatisticsTimeTagRulesDrawer from "../components/cost-statistics/CostStatisticsTimeTagRulesDrawer";
import ExportCenterModal, {
  type ExportCenterMode,
  type ExportRangeMode,
} from "../components/cost-statistics/ExportCenterModal";
import CostStatisticsTable, {
  type CostStatisticsTableColumn,
} from "../components/cost-statistics/CostStatisticsTable";
import CostEntryDetailDrawer from "../components/cost-statistics/CostEntryDetailDrawer";
import { useAppChrome } from "../contexts/AppChromeContext";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  exportCostStatisticsView,
  fetchCostStatisticsExplorerPage,
  fetchCostStatisticsNoOaRules,
  fetchCostStatisticsTimeTagRules,
  fetchCostStatisticsExportPreview,
  fetchCostEntryDetail,
  saveCostStatisticsNoOaRules,
  saveCostStatisticsTimeTagRules,
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
  CostProjectExplorerRow,
  CostStatisticsNoOaProject,
  CostStatisticsNoOaRules,
  CostStatisticsExplorerPage,
  CostStatisticsExplorerPageRequest,
  CostStatisticsExportPreview,
  CostStatisticsTimeTagRules,
  CostExplorerEntryRow,
  CostEntryDetail,
} from "../features/cost-statistics/types";

type CostViewMode = "time" | "project" | "bank" | "expenseType" | "bankTag";
type CostEntryDetailSource = CostViewMode;
type RangeScopeMode = "all" | "year" | "month";
type ExplorerScopeMode = RangeScopeMode;
type ExplorerScopeSelection = {
  mode: ExplorerScopeMode;
  year: string;
  month: string;
};
type EffectiveCostPageState = "fresh" | "loading" | "error";
type ExplorerTransitionScope = "surface" | "children" | "rows" | null;

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

type LoadedCostStatisticsExplorer = {
  requestKey: string;
  payload: CostStatisticsExplorerPage;
};

function getExplorerTransitionScope(
  previousRequestKey: string | undefined,
  nextRequestKey: string,
  loading: boolean,
): ExplorerTransitionScope {
  if (!previousRequestKey) {
    return "surface";
  }
  if (previousRequestKey === nextRequestKey) {
    return loading ? "surface" : null;
  }

  const previous = JSON.parse(previousRequestKey) as CostStatisticsExplorerPageRequest;
  const next = JSON.parse(nextRequestKey) as CostStatisticsExplorerPageRequest;
  if (previous.scope !== next.scope || previous.view !== next.view) {
    return "surface";
  }
  if (previous.query !== next.query) {
    return "surface";
  }
  if (
    (next.view === "project" && previous.projectName !== next.projectName)
    || (next.view === "bank" && previous.paymentAccountLabel !== next.paymentAccountLabel)
    || (next.view === "bank_tag" && previous.bankTagPrimaryLabel !== next.bankTagPrimaryLabel)
  ) {
    return "children";
  }
  return "rows";
}

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

function getCostEntryRowRenderKey(row: CostExplorerEntryRow, index: number) {
  return [
    row.entryId || "entry",
    row.occurredAt,
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
  hideWhenZero = false,
  label,
  tone,
}: {
  amount: string;
  hideWhenZero?: boolean;
  label: string;
  tone: "expense" | "income";
}) {
  const numericAmount = Number(amount.replace(/,/g, ""));
  if (hideWhenZero && Number.isFinite(numericAmount) && numericAmount === 0) {
    return null;
  }
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

function CostPercentageChip({ label }: { label: string }) {
  return (
    <Chip className="cost-explorer-percentage-badge" color="accent" size="sm" variant="soft">
      <Chip.Label>{label}</Chip.Label>
    </Chip>
  );
}

function CostLaneCount({ value }: { value: number }) {
  return (
    <Chip className="cost-explorer-lane-count" color="default" size="sm" variant="soft">
      <Chip.Label>{value}</Chip.Label>
    </Chip>
  );
}

function CostSurfaceSkeleton({ loading }: { loading: boolean }) {
  return (
    <div
      aria-busy={loading}
      aria-label="正在加载成本统计内容"
      className="cost-surface-skeleton"
    >
      <span />
      <span />
      <span />
    </div>
  );
}

function EntryIdentity({
  label,
  occurredAt,
  secondaryLabel,
}: {
  label: string;
  occurredAt: string;
  secondaryLabel?: string;
}) {
  const formattedTradeTime = formatCostTradeTime(occurredAt);
  return (
    <span className="cost-transaction-identity grid min-w-0 justify-items-start gap-1.5">
      {label ? (
        <span className="max-w-full text-left font-extrabold leading-5 text-[var(--fp-text)] [overflow-wrap:anywhere]">
          {label}
        </span>
      ) : null}
      {secondaryLabel ? (
        <span className="max-w-full text-left text-xs font-semibold leading-4 text-[var(--fp-text-muted)] [overflow-wrap:anywhere]">
          {secondaryLabel}
        </span>
      ) : null}
      <time
        className="cost-transaction-time-chip inline-flex min-h-5 items-center whitespace-nowrap rounded-sm border border-[var(--fp-border)] bg-[var(--fp-surface-muted)] px-1.5 text-xs font-semibold leading-none text-[var(--fp-text-muted)] tabular-nums"
        dateTime={occurredAt}
      >
        {formattedTradeTime || "--"}
      </time>
    </span>
  );
}

function costEntryActionLabel(row: CostExplorerEntryRow) {
  const target = row.rowKind === "oa_allocation" ? row.projectName || "未命名项目" : row.counterpartyName || "未知对方";
  return `查看${row.rowKind === "oa_allocation" ? "OA 成本归集" : "银行流水"} ${target} ${formatCostTradeTime(row.occurredAt) || "时间未知"} ${formatCostAmount(row.amount)}`;
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
  const { canMutateData } = useSessionPermissions();
  const defaultMonthBounds = buildMonthDateBounds(DEFAULT_MONTH);
  const costPageSession = usePageSessionState<CostStatisticsPageSession>({
    pageKey: "cost-statistics",
    stateKey: "explorerState",
    version: 3,
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
  const timeScopeMode = costSession.timeScopeMode;
  const timeScopeYear = costSession.timeScopeYear;
  const timeScopeMonth = costSession.timeScopeMonth;

  const [loadedExplorer, setLoadedExplorer] = useState<LoadedCostStatisticsExplorer | null>(null);
  const [pageStatistics, setPageStatistics] = useState<CostStatisticsExplorerPage["statistics"]>(undefined);
  const [exportReferenceData, setExportReferenceData] = useState<CostStatisticsExportReferenceData | null>(null);
  const [entryDetail, setEntryDetail] = useState<CostEntryDetail | null>(null);
  const [isExplorerLoading, setIsExplorerLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [isExportReferenceLoading, setIsExportReferenceLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [exportFeedback, setExportFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [isExportCenterOpen, setIsExportCenterOpen] = useState(false);
  const [exportPreview, setExportPreview] = useState<CostStatisticsExportPreview | null>(null);
  const [exportCenterMode, setExportCenterMode] = useState<ExportCenterMode>("time");
  const [domainRefreshNonce, setDomainRefreshNonce] = useState(0);
  const [isTimeTagRulesOpen, setIsTimeTagRulesOpen] = useState(false);
  const [timeTagRules, setTimeTagRules] = useState<CostStatisticsTimeTagRules | null>(null);
  const [timeTagDraftMode, setTimeTagDraftMode] = useState<"all" | "custom">("all");
  const [timeTagDraftCodes, setTimeTagDraftCodes] = useState<string[]>([]);
  const [isTimeTagRulesLoading, setIsTimeTagRulesLoading] = useState(false);
  const [isTimeTagRulesSaving, setIsTimeTagRulesSaving] = useState(false);
  const [timeTagRulesError, setTimeTagRulesError] = useState<string | null>(null);
  const [isNoOaRulesOpen, setIsNoOaRulesOpen] = useState(false);
  const [noOaRules, setNoOaRules] = useState<CostStatisticsNoOaRules | null>(null);
  const [noOaDraftProjects, setNoOaDraftProjects] = useState<CostStatisticsNoOaProject[]>([]);
  const [isNoOaRulesLoading, setIsNoOaRulesLoading] = useState(false);
  const [isNoOaRulesSaving, setIsNoOaRulesSaving] = useState(false);
  const [noOaRulesError, setNoOaRulesError] = useState<string | null>(null);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchComposing, setIsSearchComposing] = useState(false);

  const [timeRangeMode, setTimeRangeMode] = useState<ExportRangeMode>("month");
  const [timeMonth, setTimeMonth] = useState(DEFAULT_MONTH);
  const [timeStartDate, setTimeStartDate] = useState(defaultMonthBounds.startDate);
  const [timeEndDate, setTimeEndDate] = useState(defaultMonthBounds.endDate);

  const [projectExportNames, setProjectExportNames] = useState<string[]>([]);
  const [projectAggregateBy, setProjectAggregateBy] = useState<"month" | "year">("month");
  const [projectExpenseTypes, setProjectExpenseTypes] = useState<string[]>([]);
  const projectScopeMode = costSession.projectScopeMode;
  const projectScopeYear = costSession.projectScopeYear;
  const projectScopeMonth = costSession.projectScopeMonth;
  const bankScopeMode = costSession.bankScopeMode;
  const bankScopeYear = costSession.bankScopeYear;
  const bankScopeMonth = costSession.bankScopeMonth;

  const expenseTypeScopeMode = costSession.expenseTypeScopeMode;
  const expenseTypeScopeYear = costSession.expenseTypeScopeYear;
  const expenseTypeScopeMonth = costSession.expenseTypeScopeMonth;
  const [expenseTypeRangeMode, setExpenseTypeRangeMode] = useState<ExportRangeMode>("month");
  const [expenseTypeMonth, setExpenseTypeMonth] = useState(DEFAULT_MONTH);
  const [expenseTypeStartDate, setExpenseTypeStartDate] = useState(defaultMonthBounds.startDate);
  const [expenseTypeEndDate, setExpenseTypeEndDate] = useState(defaultMonthBounds.endDate);
  const [expenseTypeSelections, setExpenseTypeSelections] = useState<string[]>([]);
  const bankTagScopeMode = costSession.bankTagScopeMode;
  const bankTagScopeYear = costSession.bankTagScopeYear;
  const bankTagScopeMonth = costSession.bankTagScopeMonth;

  const [selectedTimeEntryId, setSelectedTimeEntryId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [selectedProjectExpenseType, setSelectedProjectExpenseType] = useState<string | null>(null);
  const [selectedProjectEntryId, setSelectedProjectEntryId] = useState<string | null>(null);
  const [selectedBankAccountLabel, setSelectedBankAccountLabel] = useState<string | null>(null);
  const [selectedBankProjectName, setSelectedBankProjectName] = useState<string | null>(null);
  const [selectedBankEntryId, setSelectedBankEntryId] = useState<string | null>(null);
  const [selectedExpenseType, setSelectedExpenseType] = useState<string | null>(null);
  const [selectedExpenseEntryId, setSelectedExpenseEntryId] = useState<string | null>(null);
  const [selectedBankTagPrimaryLabel, setSelectedBankTagPrimaryLabel] = useState<string | null>(null);
  const [selectedBankTagSubLabel, setSelectedBankTagSubLabel] = useState<string | null>(null);
  const [selectedBankTagEntryId, setSelectedBankTagEntryId] = useState<string | null>(null);
  const pageTitleRef = useRef<HTMLHeadingElement | null>(null);
  const headerControlsRef = useRef<HTMLDivElement | null>(null);
  const headerActionsRef = useRef<HTMLDivElement | null>(null);
  const contentShellRef = useRef<HTMLElement | null>(null);
  const lockStatusRef = useRef<HTMLDivElement | null>(null);
  const lastLockedFocusRef = useRef<HTMLElement | null>(null);
  const shouldRestoreFocusRef = useRef(false);
  const explorerRequestRef = useRef<AbortController | null>(null);
  const statisticsRequestRef = useRef<AbortController | null>(null);
  const exportReferenceRequestRef = useRef<AbortController | null>(null);
  const exportRequestRef = useRef<AbortController | null>(null);
  const exportPreviewRequestRef = useRef<AbortController | null>(null);
  const loadMoreRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);
  const loadedStatisticsRefreshKeyRef = useRef<string | undefined>(undefined);

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
    ...(searchQuery ? { query: searchQuery } : {}),
  };
  const explorerRequestKey = JSON.stringify(explorerRequest);
  const statisticsRefreshKey = `${activationGeneration}:${domainRefreshNonce}`;
  const explorerData = loadedExplorer?.payload ?? null;
  const explorerTransitionScope = getExplorerTransitionScope(
    loadedExplorer?.requestKey,
    explorerRequestKey,
    isExplorerLoading,
  );

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
    setEntryDetail(null);
    setSelectedTimeEntryId(null);
    setSelectedProjectEntryId(null);
    setSelectedBankEntryId(null);
    setSelectedExpenseEntryId(null);
    setSelectedBankTagEntryId(null);
    setIsDetailLoading(false);
    setDetailError(null);
  }, []);

  const resetExplorerSelection = useCallback((targetView: CostViewMode) => {
    resetDetailSelection();
    if (targetView === "project") {
      setSelectedProjectName(null);
      setSelectedProjectExpenseType(null);
    } else if (targetView === "bank") {
      setSelectedBankAccountLabel(null);
      setSelectedBankProjectName(null);
    } else if (targetView === "expenseType") {
      setSelectedExpenseType(null);
    } else if (targetView === "bankTag") {
      setSelectedBankTagPrimaryLabel(null);
      setSelectedBankTagSubLabel(null);
    }
  }, [resetDetailSelection]);

  useEffect(() => {
    if (!active || isSearchComposing) {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      const normalizedQuery = searchDraft.trim().replace(/\s+/g, " ");
      if (normalizedQuery === searchQuery) {
        return;
      }
      loadMoreRequestRef.current?.abort();
      loadMoreRequestRef.current = null;
      setIsLoadingMore(false);
      setLoadMoreError(null);
      resetExplorerSelection(viewMode);
      setSearchQuery(normalizedQuery);
    }, 200);
    return () => window.clearTimeout(timeoutId);
  }, [
    active,
    isSearchComposing,
    resetExplorerSelection,
    searchDraft,
    searchQuery,
    viewMode,
  ]);

  const updateScopeSelection = useCallback((
    targetView: CostViewMode,
    selection: ExplorerScopeSelection,
  ) => {
    resetExplorerSelection(targetView);
    costPageSession.setValue((current) => {
      if (targetView === "time") {
        return {
          ...current,
          timeScopeMode: selection.mode,
          timeScopeYear: selection.year,
          timeScopeMonth: selection.month,
        };
      }
      if (targetView === "project") {
        return {
          ...current,
          projectScopeMode: selection.mode,
          projectScopeYear: selection.year,
          projectScopeMonth: selection.month,
        };
      }
      if (targetView === "bank") {
        return {
          ...current,
          bankScopeMode: selection.mode,
          bankScopeYear: selection.year,
          bankScopeMonth: selection.month,
        };
      }
      if (targetView === "expenseType") {
        return {
          ...current,
          expenseTypeScopeMode: selection.mode,
          expenseTypeScopeYear: selection.year,
          expenseTypeScopeMonth: selection.month,
        };
      }
      return {
        ...current,
        bankTagScopeMode: selection.mode,
        bankTagScopeYear: selection.year,
        bankTagScopeMonth: selection.month,
      };
    });
  }, [costPageSession, resetExplorerSelection]);

  const handleManualRefresh = useCallback(() => {
    invalidateExportReferenceData();
    setDomainRefreshNonce((current) => current + 1);
  }, [invalidateExportReferenceData]);

  const closeTimeTagRules = useCallback(() => {
    if (!isTimeTagRulesSaving) {
      setIsTimeTagRulesOpen(false);
      setTimeTagRulesError(null);
    }
  }, [isTimeTagRulesSaving]);
  const closeNoOaRules = useCallback(() => {
    if (!isNoOaRulesSaving) {
      setIsNoOaRulesOpen(false);
      setNoOaRulesError(null);
    }
  }, [isNoOaRulesSaving]);

  useEffect(() => {
    if (!active || !isTimeTagRulesOpen) {
      return undefined;
    }
    const controller = new AbortController();
    async function loadRules() {
      setIsTimeTagRulesLoading(true);
      setTimeTagRulesError(null);
      try {
        const payload = await fetchCostStatisticsTimeTagRules(controller.signal);
        if (!controller.signal.aborted) {
          setTimeTagRules(payload);
          setTimeTagDraftMode(payload.mode);
          setTimeTagDraftCodes(payload.selectedTagCodes);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setTimeTagRulesError(getCostStatisticsLoadErrorMessage(caught));
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsTimeTagRulesLoading(false);
        }
      }
    }
    void loadRules();
    return () => controller.abort();
  }, [active, activationGeneration, isTimeTagRulesOpen]);

  useEffect(() => {
    if (!active || !isNoOaRulesOpen) return undefined;
    const controller = new AbortController();
    async function loadRules() {
      setIsNoOaRulesLoading(true);
      setNoOaRulesError(null);
      try {
        const payload = await fetchCostStatisticsNoOaRules(controller.signal);
        if (!controller.signal.aborted) {
          setNoOaRules(payload);
          setNoOaDraftProjects(payload.projects);
        }
      } catch (caught) {
        if (!controller.signal.aborted) setNoOaRulesError(getCostStatisticsLoadErrorMessage(caught));
      } finally {
        if (!controller.signal.aborted) setIsNoOaRulesLoading(false);
      }
    }
    void loadRules();
    return () => controller.abort();
  }, [active, activationGeneration, isNoOaRulesOpen]);

  const saveTimeTagRules = useCallback(async () => {
    if (!timeTagRules || isTimeTagRulesSaving) return;
    setIsTimeTagRulesSaving(true);
    setTimeTagRulesError(null);
    try {
      const result = await saveCostStatisticsTimeTagRules({
        expectedVersion: timeTagRules.version,
        mode: timeTagDraftMode,
        selectedTagCodes: timeTagDraftMode === "all" ? [] : timeTagDraftCodes,
      });
      setTimeTagRules(result);
      setTimeTagDraftMode(result.mode);
      setTimeTagDraftCodes(result.selectedTagCodes);
      if (viewMode === "time" || viewMode === "bankTag") setDomainRefreshNonce((current) => current + 1);
      setIsTimeTagRulesOpen(false);
    } catch (caught) {
      setTimeTagRulesError(getCostStatisticsActionErrorMessage(caught));
    } finally {
      setIsTimeTagRulesSaving(false);
    }
  }, [
    isTimeTagRulesSaving,
    timeTagDraftCodes,
    timeTagDraftMode,
    timeTagRules,
    viewMode,
  ]);

  const saveNoOaRules = useCallback(async () => {
    if (!noOaRules || isNoOaRulesSaving) return;
    setIsNoOaRulesSaving(true);
    setNoOaRulesError(null);
    invalidateExportReferenceData();
    try {
      const result = await saveCostStatisticsNoOaRules({
        expectedVersion: noOaRules.version,
        projects: noOaDraftProjects.map((project) => ({ ...project, displayName: project.displayName.trim() })),
      });
      setNoOaRules(result);
      setNoOaDraftProjects(result.projects);
      if (viewMode === "project" || viewMode === "bank" || viewMode === "expenseType") setDomainRefreshNonce((current) => current + 1);
      setIsNoOaRulesOpen(false);
    } catch (caught) {
      setNoOaRulesError(getCostStatisticsActionErrorMessage(caught));
    } finally {
      setIsNoOaRulesSaving(false);
    }
  }, [invalidateExportReferenceData, isNoOaRulesSaving, noOaDraftProjects, noOaRules, viewMode]);

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
      setLoadMoreError(null);
      setLoadError(null);
      setExportFeedback(null);
      resetDetailSelection();
      setIsExplorerLoading(true);

      try {
        const request = JSON.parse(explorerRequestKey) as CostStatisticsExplorerPageRequest;
        const payload = await fetchCostStatisticsExplorerPage({
          ...request,
          includeStatistics: false,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setLoadedExplorer({ requestKey: explorerRequestKey, payload });
          setIsExplorerLoading(false);
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
    return () => {
      controller.abort();
      if (explorerRequestRef.current === controller) {
        explorerRequestRef.current = null;
      }
    };
  }, [
    active,
    activationGeneration,
    domainRefreshNonce,
    explorerRequestKey,
    resetDetailSelection,
  ]);

  useEffect(() => {
    if (!active || loadedStatisticsRefreshKeyRef.current === statisticsRefreshKey) {
      return undefined;
    }
    statisticsRequestRef.current?.abort();
    const controller = new AbortController();
    statisticsRequestRef.current = controller;
    const request = JSON.parse(explorerRequestKey) as CostStatisticsExplorerPageRequest;
    void fetchCostStatisticsExplorerPage({
      ...request,
      pageSize: 1,
      includeStatistics: true,
      signal: controller.signal,
    }).then((payload) => {
      if (!controller.signal.aborted && payload.statistics) {
        loadedStatisticsRefreshKeyRef.current = statisticsRefreshKey;
        setPageStatistics(payload.statistics);
      }
    }).catch(() => undefined);
    return () => {
      controller.abort();
      if (statisticsRequestRef.current === controller) {
        statisticsRequestRef.current = null;
      }
    };
  }, [active, statisticsRefreshKey]);

  async function loadMoreExplorerRows() {
    if (
      !explorerData?.nextCursor
      || loadedExplorer?.requestKey !== explorerRequestKey
      || isLoadingMore
    ) {
      return;
    }
    loadMoreRequestRef.current?.abort();
    const controller = new AbortController();
    loadMoreRequestRef.current = controller;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    try {
      const request = JSON.parse(explorerRequestKey) as CostStatisticsExplorerPageRequest;
      const nextPage = await fetchCostStatisticsExplorerPage({
        ...request,
        cursor: explorerData.nextCursor,
        includeStatistics: false,
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
        setLoadMoreError(getCostStatisticsLoadErrorMessage(caught));
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

  const isChildrenTransition = explorerTransitionScope === "children";
  const isRowsTransition = isChildrenTransition || explorerTransitionScope === "rows";
  const pageRows = isRowsTransition ? [] : explorerData?.rows ?? [];
  const availableScopeYears = explorerData?.availableYears ?? [];
  const filteredTimeRows = pageRows;
  const projectRows = explorerData?.facets.projects ?? [];
  const projectExpenseTypeRows = isChildrenTransition ? [] : explorerData?.facets.expenseTypes ?? [];
  const bankRows = explorerData?.facets.bankAccounts ?? [];
  const bankProjectRows = isChildrenTransition ? [] : explorerData?.facets.projects ?? [];
  const expenseTypeRows = explorerData?.facets.expenseTypes ?? [];
  const bankTagPrimaryRows = explorerData?.facets.bankTagPrimary ?? [];
  const bankTagSubRows = isChildrenTransition ? [] : explorerData?.facets.bankTagSub ?? [];
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
      updateScopeSelection("time", {
        mode: timeScopeMode,
        year: availableScopeYears[0],
        month: timeScopeMonth,
      });
    }
  }, [availableScopeYears, timeScopeMode, timeScopeMonth, timeScopeYear, updateScopeSelection]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(projectScopeYear)) {
      updateScopeSelection("project", {
        mode: projectScopeMode,
        year: availableScopeYears[0],
        month: projectScopeMonth,
      });
    }
  }, [availableScopeYears, projectScopeMode, projectScopeMonth, projectScopeYear, updateScopeSelection]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(bankScopeYear)) {
      updateScopeSelection("bank", {
        mode: bankScopeMode,
        year: availableScopeYears[0],
        month: bankScopeMonth,
      });
    }
  }, [availableScopeYears, bankScopeMode, bankScopeMonth, bankScopeYear, updateScopeSelection]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(expenseTypeScopeYear)) {
      updateScopeSelection("expenseType", {
        mode: expenseTypeScopeMode,
        year: availableScopeYears[0],
        month: expenseTypeScopeMonth,
      });
    }
  }, [
    availableScopeYears,
    expenseTypeScopeMode,
    expenseTypeScopeMonth,
    expenseTypeScopeYear,
    updateScopeSelection,
  ]);

  useEffect(() => {
    if (availableScopeYears.length === 0) {
      return;
    }
    if (!availableScopeYears.includes(bankTagScopeYear)) {
      updateScopeSelection("bankTag", {
        mode: bankTagScopeMode,
        year: availableScopeYears[0],
        month: bankTagScopeMonth,
      });
    }
  }, [availableScopeYears, bankTagScopeMode, bankTagScopeMonth, bankTagScopeYear, updateScopeSelection]);

  const exportProjectOptions = useMemo(
    () => (exportReferenceData?.projects ?? []).map((row) => row.projectName),
    [exportReferenceData],
  );
  const allExpenseTypeOptions = useMemo(
    () => (exportReferenceData?.expenseTypes ?? []).map((row) => row.expenseType),
    [exportReferenceData],
  );

  const projectExpenseTypeOptions = projectExportNames.length > 0 ? allExpenseTypeOptions : [];

  const hasExplorerLoadError = Boolean(loadError) && !loadedExplorer;
  const effectiveCostPageState: EffectiveCostPageState = hasExplorerLoadError
    ? "error"
    : !loadedExplorer
      ? "loading"
      : "fresh";
  const interactionLocked = effectiveCostPageState !== "fresh";
  const lockStatusCopy = effectiveCostPageState === "error"
    ? {
        title: "无法确认成本数据状态",
        detail: loadError || "网络恢复前页面保持锁定。",
      }
    : {
        title: "正在加载成本统计",
        detail: "正在从统一事实源读取数据，完成后将自动开放操作。",
      };
  const lockStatusCanRetry = effectiveCostPageState === "error";

  useEffect(() => {
    if (interactionLocked) {
      const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const lockedRegions = [headerControlsRef.current, headerActionsRef.current, contentShellRef.current];
      const ownsActiveFocus = Boolean(activeElement && (
        lockedRegions.some((region) => region?.contains(activeElement))
        || activeElement.closest(".cost-transaction-detail-drawer, .export-center-modal, .cost-tag-rules-drawer")
      ));
      if (activeElement && ownsActiveFocus) {
        lastLockedFocusRef.current = activeElement;
        shouldRestoreFocusRef.current = true;
        queueMicrotask(() => lockStatusRef.current?.focus());
      }
      setIsExportCenterOpen(false);
      setExportPreview(null);
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

  async function loadEntryDetail(entryId: string, rowKind: CostExplorerEntryRow["rowKind"], source: CostEntryDetailSource) {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    setEntryDetail(null);
    setDetailError(null);
    setIsDetailLoading(true);
    try {
      const detailView =
        source === "bankTag"
          ? "bank_tag"
          : source === "expenseType"
            ? "expense_type"
            : source;
      const payload = await fetchCostEntryDetail(
        { entryId, rowKind },
        detailView,
        explorerScope,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setEntryDetail(payload);
      }
    } catch (caught) {
      if (!controller.signal.aborted && !isAbortLikeError(caught)) {
        setDetailError(`${rowKind === "oa_allocation" ? "OA 成本归集明细" : "银行流水详情"}加载失败，请稍后重试。`);
      }
    } finally {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
        setIsDetailLoading(false);
      }
    }
  }

  async function openEntryDetail(row: CostExplorerEntryRow, source: CostEntryDetailSource) {
    if (source === "time") {
      setSelectedTimeEntryId(row.entryId);
    }
    if (source === "project") {
      setSelectedProjectEntryId(row.entryId);
    }
    if (source === "bank") {
      setSelectedBankEntryId(row.entryId);
    }
    if (source === "expenseType") {
      setSelectedExpenseEntryId(row.entryId);
    }
    if (source === "bankTag") {
      setSelectedBankTagEntryId(row.entryId);
    }
    await loadEntryDetail(row.entryId, row.rowKind, source);
  }

  function handleViewModeChange(nextViewMode: CostViewMode) {
    if (nextViewMode === viewMode) {
      return;
    }
    exportReferenceRequestRef.current?.abort();
    exportReferenceRequestRef.current = null;
    setIsExportReferenceLoading(false);
    setLoadError(null);
    setLoadMoreError(null);
    setExportFeedback(null);
    setSearchDraft("");
    setSearchQuery("");
    setIsSearchComposing(false);
    resetExplorerSelection(nextViewMode);
    startTransition(() => {
      setViewMode(nextViewMode);
    });
  }

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
          pageSize: 1,
          includeStatistics: false,
          signal: controller.signal,
        }),
        fetchCostStatisticsExplorerPage({
          scope: "all",
          view: "expense_type",
          pageSize: 1,
          includeStatistics: false,
          signal: controller.signal,
        }),
      ]);
      if (controller.signal.aborted) {
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
        };
      }
      return {
        month: "all",
        view: exportCenterMode,
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
    if (params.view === "month") {
      return null;
    }
    return params;
  }

  async function runExport(params: CostExportParams) {
    exportRequestRef.current?.abort();
    const controller = new AbortController();
    exportRequestRef.current = controller;
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

  const timeColumns = useMemo<CostStatisticsTableColumn<CostExplorerEntryRow>[]>(
    () => [
      { key: "occurredAt", header: "时间", width: 170, render: (row) => formatCostTradeTime(row.occurredAt) },
      { key: "counterpartyName", header: "对方户名", flex: 1.1, render: (row) => row.counterpartyName || "--" },
      {
        key: "bankTag",
        header: "流水标签",
        flex: 0.8,
        getTextValue: (row) => row.bankTagLabelPath.join(" / "),
        render: (row) => row.bankTagLabelPath.join(" / ") || "未标记",
      },
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
      { key: "expenseContent", header: "流水摘要", flex: 1.25, render: (row) => row.expenseContent || row.remark || "--" },
    ],
    [],
  );

  const entryColumns = useMemo<CostStatisticsTableColumn<CostExplorerEntryRow>[]>(
    () => {
      const isBankFactView = viewMode === "time" || viewMode === "bankTag";
      const identityColumn: CostStatisticsTableColumn<CostExplorerEntryRow> = viewMode === "expenseType"
        ? {
            key: "projectName",
            header: "项目名 / 申请/报销人",
            flex: 1.15,
            getTextValue: (row) => `${row.projectName} ${row.oaApplicant} ${formatCostTradeTime(row.occurredAt)}`,
            render: (row) => (
              <EntryIdentity
                label={row.projectName}
                secondaryLabel={row.oaApplicant}
                occurredAt={row.occurredAt}
              />
            ),
          }
        : isBankFactView
          ? {
              key: "counterpartyName",
              header: "对方户名",
              flex: 1.15,
              getTextValue: (row) => `${row.counterpartyName} ${formatCostTradeTime(row.occurredAt)}`,
              render: (row) => <EntryIdentity label={row.counterpartyName} occurredAt={row.occurredAt} />,
            }
          : {
              key: "oaApplicant",
              header: "申请/报销人",
              flex: 1.15,
              getTextValue: (row) => `${row.oaApplicant} ${formatCostTradeTime(row.occurredAt)}`,
              render: (row) => <EntryIdentity label={row.oaApplicant} occurredAt={row.occurredAt} />,
            };
      return [
        identityColumn,
        {
          key: "amount",
          header: "成本金额",
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
      ];
    },
    [viewMode],
  );

  const activeEntryId =
    selectedTimeEntryId
    ?? selectedProjectEntryId
    ?? selectedBankEntryId
    ?? selectedExpenseEntryId
    ?? selectedBankTagEntryId;
  const activeRowKind: CostExplorerEntryRow["rowKind"] | null = activeEntryId
    ? explorerData?.rows.find((row) => row.entryId === activeEntryId)?.rowKind
      ?? entryDetail?.kind
      ?? null
    : null;
  const costViewSearch = (
    <QuerySearch
      ariaLabel="搜索当前成本统计表格"
      className="cost-view-search-form"
      maxLength={200}
      onChange={setSearchDraft}
      onClear={() => setSearchDraft("")}
      onCompositionChange={setIsSearchComposing}
      onSubmit={() => {
        const normalizedQuery = searchDraft.trim().replace(/\s+/g, " ");
        resetExplorerSelection(viewMode);
        setSearchQuery(normalizedQuery);
      }}
      pending={!isSearchComposing && (isExplorerLoading || searchDraft.trim().replace(/\s+/g, " ") !== searchQuery)}
      placeholder="搜索当前表格"
      value={searchDraft}
    />
  );
  const autoLoadTableProps = {
    fitContainer: true,
    hasNextPage: Boolean(explorerData?.nextCursor),
    loadingMore: isLoadingMore,
    loadMoreError,
    onRequestNextPage: () => void loadMoreExplorerRows(),
  };
  const isExportActionBusy = isExportReferenceLoading || isExporting || isPreviewLoading;
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
          { label: "成本明细", value: visibleStatistics?.costTransactionCount, unit: "条" },
        ]}
      />
    </div>
  );

  return (
    <div className="page-stack cost-page gap-3 bg-[var(--fp-page)]">
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
            <ToggleButtonGroup
              aria-label="成本统计视图切换"
              className="cost-view-switcher cost-view-tabs"
              disallowEmptySelection
              onSelectionChange={(keys) => {
                const [key] = Array.from(keys);
                if (key === "project" || key === "bank" || key === "expenseType" || key === "bankTag" || key === "time") handleViewModeChange(key);
              }}
              selectedKeys={new Set([viewMode])}
              selectionMode="single"
              size="sm"
            >
              <ToggleButton className="cost-view-tab" id="project">按项目</ToggleButton>
              <ToggleButton className="cost-view-tab" id="bank">按银行</ToggleButton>
              <ToggleButton className="cost-view-tab" id="expenseType">按费用类型</ToggleButton>
              <ToggleButton className="cost-view-tab" id="bankTag"><ToggleButtonGroup.Separator />按标签</ToggleButton>
              <ToggleButton className="cost-view-tab" id="time"><ToggleButtonGroup.Separator />按时间</ToggleButton>
            </ToggleButtonGroup>
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
          <Button
            aria-label="刷新成本统计"
            className="cost-page-action cost-refresh-button"
            isDisabled={isExplorerLoading}
            onPress={handleManualRefresh}
            size="sm"
            variant="secondary"
          >
            刷新
          </Button>
          <Button
            className="cost-page-action"
            isDisabled={isTimeTagRulesSaving}
            onPress={() => { setTimeTagRulesError(null); setIsTimeTagRulesOpen(true); }}
            size="sm"
            variant="secondary"
          >
            按标签/按时间标签规则
          </Button>
          <Button
            className="cost-page-action"
            isDisabled={isNoOaRulesSaving}
            onPress={() => { setNoOaRulesError(null); setIsNoOaRulesOpen(true); }}
            size="sm"
            variant="secondary"
          >
            无 OA 成本范围
          </Button>
          <Button
            className="cost-page-action"
            isDisabled={isExplorerLoading || isExportReferenceLoading || hasExplorerLoadError}
            onPress={() => void openExportCenter()}
            size="sm"
            variant="primary"
          >
            {isExportReferenceLoading ? "正在准备导出..." : "导出中心"}
          </Button>
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
            {exportFeedback && !isExportCenterOpen ? (
              <div className={`action-feedback ${exportFeedback.tone}`}>{exportFeedback.message}</div>
            ) : null}
        {explorerData ? (
          <>
            {viewMode === "time" ? (
              <div className="cost-analysis-layout time-layout cost-time-workspace">
                <aside className="cost-time-filter-rail">
                  <h2>时间范围</h2>
                  <BusinessPeriodPicker
                    ariaLabel="时间统计时间范围"
                    inline
                    onChange={(selection) => updateScopeSelection("time", selection)}
                    selection={{ mode: timeScopeMode, year: timeScopeYear, month: timeScopeMonth }}
                    years={availableScopeYears}
                  />
                </aside>
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
                      {costViewSearch}
                    </div>
                  </div>
                  {explorerTransitionScope === "surface" ? (
                    <CostSurfaceSkeleton loading={isExplorerLoading} />
                  ) : (
                    <CostStatisticsTable
                      ariaLabel="按时间统计表"
                      columns={timeColumns}
                      rows={filteredTimeRows}
                      getRowKey={getCostEntryRowRenderKey}
                      emptyLabel="当前时间范围没有收入或支出流水。"
                      onRowClick={(row) => void openEntryDetail(row, "time")}
                      getRowActionLabel={costEntryActionLabel}
                      {...autoLoadTableProps}
                    />
                  )}
                </section>
              </div>
            ) : null}

            {viewMode === "project" ? (
              <div className="cost-analysis-layout explorer-layout grid min-h-0 grid-cols-1 gap-3">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按项目统计</h2>
                    <DirectionAmount amount={projectTotalAmount} label="支出金额" tone="expense" />
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <BusinessPeriodPicker
                      ariaLabel="项目统计时间范围"
                      onChange={(selection) => updateScopeSelection("project", selection)}
                      selection={{ mode: projectScopeMode, year: projectScopeYear, month: projectScopeMonth }}
                      years={availableScopeYears}
                    />
                    {costViewSearch}
                  </div>
                </div>
                {explorerTransitionScope === "surface" ? (
                  <CostSurfaceSkeleton loading={isExplorerLoading} />
                ) : (
                <div className="cost-explorer-grid project grid min-h-[520px] grid-cols-1 gap-3 lg:grid-cols-[minmax(220px,0.92fr)_minmax(220px,0.92fr)_minmax(0,2.16fr)]">
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
                      setSelectedProjectEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.projectName}
                    renderSecondary={(row) => `${row.transactionCount} 条归集 / ${row.expenseTypeCount} 类费用`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        {row.percentageLabel ? (
                          <CostPercentageChip label={row.percentageLabel} />
                        ) : null}
                      </div>
                    )}
                  />
                  <CostExplorerList<CostExpenseTypeExplorerRow>
                    title="费用类型"
                    count={projectExpenseTypeRows.length}
                    items={projectExpenseTypeRows}
                    loading={isChildrenTransition}
                    emptyLabel={selectedProjectName ? "该项目下暂无费用类型。" : "请先在左侧选择项目。"}
                    getKey={(row) => row.expenseType}
                    isActive={(row) => row.expenseType === selectedProjectExpenseType}
                    onSelect={(row) => {
                      setSelectedProjectExpenseType(row.expenseType);
                      setSelectedProjectEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.expenseType}
                    renderSecondary={(row) => `${row.transactionCount} 条归集`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        {row.percentageLabel ? <CostPercentageChip label={row.percentageLabel} /> : null}
                      </div>
                    )}
                  />
                  <section
                    aria-busy={isExplorerLoading && isRowsTransition}
                    className="cost-explorer-lane cost-explorer-lane-table"
                  >
                    <header className="cost-explorer-lane-header">
                      <h2>成本明细</h2>
                      <CostLaneCount value={isRowsTransition ? 0 : explorerData?.rowCount ?? selectedProjectTransactionRows.length} />
                    </header>
                    {isRowsTransition ? (
                      <div className="cost-explorer-empty" />
                    ) : selectedProjectName && selectedProjectExpenseType ? (
                      <CostStatisticsTable
                        ariaLabel="项目成本明细表"
                        columns={entryColumns}
                        rows={selectedProjectTransactionRows}
                        getRowKey={getCostEntryRowRenderKey}
                        onRowClick={(row) => void openEntryDetail(row, "project")}
                        getRowActionLabel={costEntryActionLabel}
                        emptyLabel="该费用类型下暂无成本明细。"
                        {...autoLoadTableProps}
                      />
                    ) : <div className="cost-explorer-empty">依次选择项目和费用类型</div>}
                  </section>
                </div>
                )}
              </div>
            ) : null}

            {viewMode === "bank" ? (
              <div className="cost-analysis-layout explorer-layout grid min-h-0 grid-cols-1 gap-3">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按银行统计</h2>
                    <DirectionAmount amount={bankTotalAmount} label="支出金额" tone="expense" />
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <BusinessPeriodPicker
                      ariaLabel="银行统计时间范围"
                      onChange={(selection) => updateScopeSelection("bank", selection)}
                      selection={{ mode: bankScopeMode, year: bankScopeYear, month: bankScopeMonth }}
                      years={availableScopeYears}
                    />
                    {costViewSearch}
                  </div>
                </div>
                {explorerTransitionScope === "surface" ? (
                  <CostSurfaceSkeleton loading={isExplorerLoading} />
                ) : (
                <div className="cost-explorer-grid project grid min-h-[520px] grid-cols-1 gap-3 lg:grid-cols-[minmax(220px,0.92fr)_minmax(220px,0.92fr)_minmax(0,2.16fr)]">
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
                      setSelectedBankEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.paymentAccountLabel}
                    renderSecondary={(row) => `${row.transactionCount} 条归集 / ${row.projectCount} 个项目`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        {row.percentageLabel ? <CostPercentageChip label={row.percentageLabel} /> : null}
                      </div>
                    )}
                  />
                  <CostExplorerList<CostProjectExplorerRow>
                    title="项目名"
                    count={bankProjectRows.length}
                    items={bankProjectRows}
                    loading={isChildrenTransition}
                    emptyLabel={selectedBankAccountLabel ? "该账户下暂无项目归集。" : "请先在左侧选择银行账户。"}
                    getKey={(row) => row.projectName}
                    isActive={(row) => row.projectName === selectedBankProjectName}
                    onSelect={(row) => {
                      setSelectedBankProjectName(row.projectName);
                      setSelectedBankEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.projectName}
                    renderSecondary={(row) => `${row.transactionCount} 条归集 / ${row.expenseTypeCount} 类费用`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        {row.percentageLabel ? <CostPercentageChip label={row.percentageLabel} /> : null}
                      </div>
                    )}
                  />
                  <section
                    aria-busy={isExplorerLoading && isRowsTransition}
                    className="cost-explorer-lane cost-explorer-lane-table"
                  >
                    <header className="cost-explorer-lane-header">
                      <h2>成本明细</h2>
                      <CostLaneCount value={isRowsTransition ? 0 : explorerData?.rowCount ?? selectedBankProjectRows.length} />
                    </header>
                    {isRowsTransition ? (
                      <div className="cost-explorer-empty" />
                    ) : selectedBankAccountLabel && selectedBankProjectName ? (
                      <CostStatisticsTable
                        ariaLabel="银行成本明细表"
                        columns={entryColumns}
                        rows={selectedBankProjectRows}
                        getRowKey={getCostEntryRowRenderKey}
                        onRowClick={(row) => void openEntryDetail(row, "bank")}
                        getRowActionLabel={costEntryActionLabel}
                        emptyLabel="该项目下暂无成本明细。"
                        {...autoLoadTableProps}
                      />
                    ) : <div className="cost-explorer-empty">依次选择银行账户和项目</div>}
                  </section>
                </div>
                )}
              </div>
            ) : null}

            {viewMode === "expenseType" ? (
              <div className="cost-analysis-layout explorer-layout expense-layout grid min-h-0 grid-cols-1 gap-3">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按费用类型统计</h2>
                    <DirectionAmount amount={expenseTypeTotalAmount} label="支出金额" tone="expense" />
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <BusinessPeriodPicker
                      ariaLabel="费用类型统计时间范围"
                      onChange={(selection) => updateScopeSelection("expenseType", selection)}
                      selection={{ mode: expenseTypeScopeMode, year: expenseTypeScopeYear, month: expenseTypeScopeMonth }}
                      years={availableScopeYears}
                    />
                    {costViewSearch}
                  </div>
                </div>
                {explorerTransitionScope === "surface" ? (
                  <CostSurfaceSkeleton loading={isExplorerLoading} />
                ) : (
                <div className="cost-explorer-grid expense grid min-h-[520px] grid-cols-1 gap-3 lg:grid-cols-[minmax(280px,0.85fr)_minmax(0,2.15fr)]">
                  <CostExplorerList<CostExpenseTypeExplorerRow>
                    title="费用类型"
                    count={expenseTypeRows.length}
                    items={expenseTypeRows}
                    emptyLabel="当前时间范围没有费用类型数据。"
                    getKey={(row) => row.expenseType}
                    isActive={(row) => row.expenseType === selectedExpenseType}
                    onSelect={(row) => {
                      setSelectedExpenseType(row.expenseType);
                      setSelectedExpenseEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.expenseType}
                    renderSecondary={(row) => `${row.transactionCount} 条归集 / ${row.projectCount} 个项目`}
                    renderMeta={(row) => (
                      <div className="cost-explorer-item-meta-stack">
                        <DirectionAmount amount={row.totalAmount} label="支出" tone="expense" />
                        <CostPercentageChip label={row.percentageLabel} />
                      </div>
                    )}
                  />
                  <section
                    aria-busy={isExplorerLoading && isRowsTransition}
                    className="cost-explorer-lane cost-explorer-lane-table"
                  >
                    <header className="cost-explorer-lane-header">
                      <h2>成本明细</h2>
                      <CostLaneCount value={isRowsTransition ? 0 : explorerData?.rowCount ?? selectedExpenseTypeRows.length} />
                    </header>
                    {isRowsTransition ? (
                      <div className="cost-explorer-empty" />
                    ) : selectedExpenseType ? (
                      <CostStatisticsTable
                        ariaLabel="按费用类型成本明细表"
                        columns={entryColumns}
                        rows={selectedExpenseTypeRows}
                        getRowKey={getCostEntryRowRenderKey}
                        onRowClick={(row) => void openEntryDetail(row, "expenseType")}
                        getRowActionLabel={costEntryActionLabel}
                        emptyLabel="该费用类型下暂无成本明细。"
                        {...autoLoadTableProps}
                      />
                    ) : <div className="cost-explorer-empty">选择费用类型查看成本明细</div>}
                  </section>
                </div>
                )}
              </div>
            ) : null}

            {viewMode === "bankTag" ? (
              <div className="cost-analysis-layout explorer-layout grid min-h-0 grid-cols-1 gap-3">
                <div className="cost-section-heading cost-view-scope-heading">
                  <div className="cost-section-heading-copy">
                    <h2>按标签统计</h2>
                    <div className="cost-direction-summary" aria-label="标签统计方向金额">
                      <DirectionAmount amount={bankTagDirectionSummary.expenseAmount} label="支出金额" tone="expense" />
                      <DirectionAmount amount={bankTagDirectionSummary.incomeAmount} label="收入金额" tone="income" />
                    </div>
                  </div>
                  <div className="cost-section-heading-actions cost-project-scope-actions">
                    <BusinessPeriodPicker
                      ariaLabel="流水标签统计时间范围"
                      onChange={(selection) => updateScopeSelection("bankTag", selection)}
                      selection={{ mode: bankTagScopeMode, year: bankTagScopeYear, month: bankTagScopeMonth }}
                      years={availableScopeYears}
                    />
                    {costViewSearch}
                  </div>
                </div>
                {explorerTransitionScope === "surface" ? (
                  <CostSurfaceSkeleton loading={isExplorerLoading} />
                ) : (
                <div className="cost-explorer-grid bank-tag grid min-h-[520px] grid-cols-1 gap-3 lg:grid-cols-[minmax(210px,0.82fr)_minmax(210px,0.82fr)_minmax(0,2.36fr)]">
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
                      setSelectedBankTagEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.primaryLabel}
                    renderSecondary={(row) => (
                      <span className="cost-tag-counts">
                        <span>支出 <strong className="cost-tag-count cost-tag-count--expense">{row.expenseTransactionCount}</strong> 笔</span>
                        <span>收入 <strong className="cost-tag-count cost-tag-count--income">{row.incomeTransactionCount}</strong> 笔</span>
                        <span>{row.subTagCount} 个子标签</span>
                      </span>
                    )}
                    renderMeta={(row) => (
                      <div className="cost-direction-meta">
                        <DirectionAmount amount={row.expenseAmount} hideWhenZero label="支出" tone="expense" />
                        <DirectionAmount amount={row.incomeAmount} hideWhenZero label="收入" tone="income" />
                      </div>
                    )}
                  />
                  <CostExplorerList<CostBankTagSubExplorerRow>
                    title="子标签"
                    count={bankTagSubRows.length}
                    items={bankTagSubRows}
                    loading={isChildrenTransition}
                    emptyLabel={selectedBankTagPrimaryLabel ? "该主标签下暂无子标签。" : "请先在左侧选择主标签。"}
                    getKey={(row) => `${row.primaryLabel}:${row.subLabel}`}
                    isActive={(row) => row.subLabel === selectedBankTagSubLabel}
                    onSelect={(row) => {
                      setSelectedBankTagSubLabel(row.subLabel);
                      setSelectedBankTagEntryId(null);
                      setEntryDetail(null);
                    }}
                    getPrimaryText={(row) => row.subLabel}
                    renderSecondary={(row) => (
                      <span className="cost-tag-counts">
                        <span>支出 <strong className="cost-tag-count cost-tag-count--expense">{row.expenseTransactionCount}</strong> 笔</span>
                        <span>收入 <strong className="cost-tag-count cost-tag-count--income">{row.incomeTransactionCount}</strong> 笔</span>
                      </span>
                    )}
                    renderMeta={(row) => (
                      <div className="cost-direction-meta">
                        <DirectionAmount amount={row.expenseAmount} hideWhenZero label="支出" tone="expense" />
                        <DirectionAmount amount={row.incomeAmount} hideWhenZero label="收入" tone="income" />
                      </div>
                    )}
                  />
                  <section
                    aria-busy={isExplorerLoading && isRowsTransition}
                    className="cost-explorer-lane cost-explorer-lane-table"
                  >
                    <header className="cost-explorer-lane-header">
                      <h2>对应流水</h2>
                      <CostLaneCount value={isRowsTransition ? 0 : explorerData?.rowCount ?? selectedBankTagSubRows.length} />
                    </header>
                    {isRowsTransition ? (
                      <div className="cost-explorer-empty" />
                    ) : selectedBankTagPrimaryLabel && selectedBankTagSubLabel ? (
                      <CostStatisticsTable
                        ariaLabel="流水标签对应流水表"
                        columns={entryColumns}
                        rows={selectedBankTagSubRows}
                        getRowKey={getCostEntryRowRenderKey}
                        onRowClick={(row) => void openEntryDetail(row, "bankTag")}
                        getRowActionLabel={costEntryActionLabel}
                        emptyLabel="该流水标签下暂无流水。"
                        {...autoLoadTableProps}
                      />
                    ) : <div className="cost-explorer-empty">依次选择主标签和子标签</div>}
                  </section>
                </div>
                )}
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

      <CostEntryDetailDrawer
        detail={entryDetail}
        error={detailError}
        loading={isDetailLoading}
        onClose={resetDetailSelection}
        onRetry={() => {
          if (activeEntryId && activeRowKind) {
            void loadEntryDetail(activeEntryId, activeRowKind, viewMode);
          }
        }}
        open={Boolean(activeEntryId)}
        rowKind={activeRowKind}
      />

      <CostStatisticsTimeTagRulesDrawer
        canSave={canMutateData && !interactionLocked && (timeTagRules?.canSave ?? true)}
        error={timeTagRulesError}
        interactionLocked={interactionLocked}
        loading={isTimeTagRulesLoading}
        mode={timeTagDraftMode}
        onChange={(mode, codes) => { setTimeTagDraftMode(mode); setTimeTagDraftCodes(codes); }}
        onClose={closeTimeTagRules}
        onSave={() => void saveTimeTagRules()}
        open={isTimeTagRulesOpen}
        rules={timeTagRules}
        saving={isTimeTagRulesSaving}
        selectedCodes={timeTagDraftCodes}
      />

      <CostStatisticsNoOaRulesDrawer
        canSave={canMutateData && !interactionLocked && (noOaRules?.canSave ?? true)}
        error={noOaRulesError}
        interactionLocked={interactionLocked}
        loading={isNoOaRulesLoading}
        onClose={closeNoOaRules}
        onProjectsChange={setNoOaDraftProjects}
        onSave={() => void saveNoOaRules()}
        open={isNoOaRulesOpen}
        projects={noOaDraftProjects}
        rules={noOaRules}
        saving={isNoOaRulesSaving}
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
