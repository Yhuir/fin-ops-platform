import TableClassificationHeader, { type ClassificationGroup } from "../components/common/TableClassificationHeader";
import { acquisitionOptions, type AcquisitionStatusCode, type AcquisitionSummary } from "../features/pendingInvoices/statusOptions";
import { Button } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import PageToolbar from "../components/common/PageToolbar";
import QuerySearch from "../components/common/QuerySearch";
import PendingInvoiceDetailDrawer from "../components/pendingInvoices/PendingInvoiceDetailDrawer";
import PendingInvoiceExportDrawer from "../components/pendingInvoices/PendingInvoiceExportDrawer";
import PendingInvoiceInvoicePickerDrawer from "../components/pendingInvoices/PendingInvoiceInvoicePickerDrawer";
import PendingInvoiceRelationDrawer from "../components/pendingInvoices/PendingInvoiceRelationDrawer";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import PendingInvoicesTable from "../components/pendingInvoices/PendingInvoicesTable";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { formatMoney } from "../features/money";
import {
  confirmAttachExistingInvoices,
  fetchPendingInvoiceCandidatesBatch,
  fetchPendingInvoiceFilterOptions,
  fetchPendingInvoiceObjectDetail,
  fetchPendingInvoiceRelationDetail,
  fetchPendingInvoiceRows,
  fetchPendingInvoiceRules,
  previewAttachExistingInvoices,
  savePendingInvoiceRules,
  savePendingInvoiceIncomeStatuses,
} from "../features/pendingInvoices/api";
import type {
  AttachExistingInvoiceResult,
  AttachExistingInvoicesResult,
  FetchPendingInvoiceRowsRequest,
  PendingInvoiceDirection,
  PendingInvoiceColumnFilter,
  PendingInvoiceFilterField,
  PendingInvoiceIncomeStatusCode,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceRelationDetailKind,
  PendingInvoiceRow,
  PendingInvoiceRowsResponse,
  PendingInvoiceSortDirection,
  PendingInvoiceSortField,
  PendingInvoiceSourceSummary,
  PendingInvoiceStatistics,
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

type ActiveDrawer = "rules" | "relation" | "invoicePicker" | "detail" | "export" | null;
type RelationTarget = { transactionId: string; kind: PendingInvoiceRelationDetailKind } | null;
type RulesDirection = Exclude<PendingInvoiceDirection, "all">;
function transactionIdForRow(row: PendingInvoiceRow) {
  return row.bankTransaction.id || row.id;
}

function numericMoney(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function setsEqual(left: Set<string>, right: Set<string>) {
  if (left.size !== right.size) {
    return false;
  }
  for (const value of left) {
    if (!right.has(value)) {
      return false;
    }
  }
  return true;
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

function persistTagVersion(version: number | null | undefined) {
  if (typeof version !== "number" || !Number.isFinite(version)) {
    return;
  }
  try {
    window.localStorage.setItem(TAG_VERSION_STORAGE_KEY, String(version));
  } catch {
    // localStorage can be unavailable in embedded contexts.
  }
}

function readPersistedTagVersion() {
  try {
    const value = Number(window.localStorage.getItem(TAG_VERSION_STORAGE_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export default function PendingInvoicesPage() {
  const { active, activationGeneration } = useOptionalPageActivation("pending-invoices");
  const { runOperation } = useGlobalOperationOverlay();
  const { canOperateData } = useSessionPermissions();
  const [direction, setDirection] = useState<PendingInvoiceDirection>("all");
  const [statusFilters, setStatusFilters] = useState<AcquisitionStatusCode[]>([]);
  const [rows, setRows] = useState<PendingInvoiceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [sourceSummary, setSourceSummary] = useState<PendingInvoiceSourceSummary | null>(null);
  const [acquisitionSummary, setAcquisitionSummary] = useState<AcquisitionSummary | null>(null);
  const [statistics, setStatistics] = useState<PendingInvoiceStatistics | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [columnFilters, setColumnFilters] = useState<PendingInvoiceColumnFilter[]>([]);
  const [columnFilterFields, setColumnFilterFields] = useState<PendingInvoiceFilterField[]>([]);
  const [sortField, setSortField] = useState<PendingInvoiceSortField>("trade_date");
  const [sortDirection, setSortDirection] = useState<PendingInvoiceSortDirection>("desc");
  const [activeDrawer, setActiveDrawer] = useState<ActiveDrawer>(null);
  const [rulesDirection, setRulesDirection] = useState<RulesDirection>("expense");
  const [detailTarget, setDetailTarget] = useState<PendingInvoiceObjectDetailTarget | null>(null);
  const [relationTarget, setRelationTarget] = useState<RelationTarget>(null);
  const [invoicePickerTransactionIds, setInvoicePickerTransactionIds] = useState<string[]>([]);
  const [selectedTransactionIds, setSelectedTransactionIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [rulesTagRefreshToken, setRulesTagRefreshToken] = useState(0);
  const [pendingIncomeStatusRows, setPendingIncomeStatusRows] = useState<Set<string>>(() => new Set());
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());
  const statisticsRef = useRef<PendingInvoiceStatistics | null>(null);

  const filterOpen = filterMenuOpen;

  const queryFilters = useMemo<PendingInvoiceColumnFilter[]>(() => {
    const baseFilters = columnFilters.filter((item) => item.field !== "status_code");
    return statusFilters.length > 0
      ? [...baseFilters, { field: "status_code", operator: "in" as const, values: statusFilters }]
      : baseFilters;
  }, [columnFilters, statusFilters]);

  const query = useMemo<FetchPendingInvoiceRowsRequest>(() => ({
    direction,
    filter: "all",
    keyword,
    page,
    pageSize,
    filters: queryFilters,
    sortField,
    sortDirection,
    includeStatistics: false,
  }), [direction, keyword, page, pageSize, queryFilters, sortDirection, sortField, statusFilters]);

  const applyRowsPayload = useCallback((payload: PendingInvoiceRowsResponse) => {
    setRows(payload.rows);
    setAcquisitionSummary(payload.acquisitionSummary);
    setTotal(payload.pagination.total);
    setSourceSummary(payload.summary.sourceSummary ?? null);
    if (payload.statistics) {
      statisticsRef.current = payload.statistics;
      setStatistics(payload.statistics);
    }
    setColumnFilterFields(payload.filterFields);
    const version = payload.tagDictionary?.version;
    if (typeof version === "number" && version > 0) {
      const previousVersion = tagVersionRef.current;
      tagVersionRef.current = version;
      persistTagVersion(version);
      if (previousVersion !== null && previousVersion !== version) {
        setRulesTagRefreshToken((current) => current + 1);
      }
    }
  }, []);

  const loadStatistics = useCallback((signal?: AbortSignal) => {
    return fetchPendingInvoiceRows({
      direction: "all",
      filter: "all",
      page: 1,
      pageSize: 1,
      includeStatistics: true,
      signal,
    }).then((payload) => {
      if (!signal?.aborted && payload.statistics) {
        statisticsRef.current = payload.statistics;
        setStatistics(payload.statistics);
      }
    });
  }, []);

  const loadRows = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchPendingInvoiceRows({ ...query, signal })
      .then((payload) => {
        if (signal?.aborted) return;
        applyRowsPayload(payload);
        if (statisticsRef.current === null) {
          void loadStatistics(signal).catch(() => undefined);
        }
        void fetchPendingInvoiceFilterOptions({ ...query, signal })
          .then((options) => {
            if (!signal?.aborted) {
              setColumnFilterFields(options.fields);
            }
          })
          .catch(() => undefined);
      })
      .catch((caught) => {
        if (!signal?.aborted && !isAbortLikeError(caught)) {
          statisticsRef.current = null;
          setStatistics(null);
          setError(caught instanceof Error ? caught.message : "待找发票加载失败。");
        }
      })
      .finally(() => {
        if (!signal?.aborted) {
          setLoading(false);
        }
      });
  }, [applyRowsPayload, loadStatistics, query]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadRows(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadRows, refreshToken]);

  const filterOptions = useMemo(() => acquisitionOptions(direction), [direction]);

  const tableConfig = useMemo(() => ({
    sortField,
    sortDirection,
  }), [sortDirection, sortField]);
  const exportDisabled = Boolean(error) || loading;
  const isTransactionSelectable = useCallback((row: PendingInvoiceRow) => {
    if (direction === "expense") {
      return row.availableActions.includes("attach_existing_invoice");
    }
    if (direction === "income") {
      return row.availableActions.includes("mark_income_status");
    }
    return false;
  }, [direction]);
  const selectedRows = useMemo(() => (
    rows.filter((row) => selectedTransactionIds.has(transactionIdForRow(row)) && isTransactionSelectable(row))
  ), [isTransactionSelectable, rows, selectedTransactionIds]);
  const selectedBankTotal = useMemo(() => (
    selectedRows.reduce((totalAmount, row) => totalAmount + numericMoney(row.bankTransaction.amount || row.bankTransaction.debitAmount || row.bankTransaction.creditAmount), 0)
  ), [selectedRows]);
  const clearSelectedTransactions = useCallback(() => {
    setSelectedTransactionIds(new Set());
  }, []);

  useEffect(() => {
    const selectableIds = new Set(rows.filter(isTransactionSelectable).map(transactionIdForRow));
    setSelectedTransactionIds((current) => {
      const next = new Set([...current].filter((id) => selectableIds.has(id)));
      return setsEqual(current, next) ? current : next;
    });
  }, [isTransactionSelectable, rows]);

  const handleSortChange = useCallback((field: PendingInvoiceSortField, nextDirection?: PendingInvoiceSortDirection) => {
    clearSelectedTransactions();
    setPage(1);
    if (nextDirection) {
      setSortField(field);
      setSortDirection(nextDirection);
      return;
    }
    if (field === sortField) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("asc");
  }, [clearSelectedTransactions, sortField]);

  const handleOpenRelation = useCallback((row: PendingInvoiceRow, kind: PendingInvoiceRelationDetailKind = "all") => {
    setRelationTarget({ transactionId: row.bankTransaction.id || row.id, kind });
    setActiveDrawer("relation");
  }, []);

  const handleToggleTransactionSelection = useCallback((row: PendingInvoiceRow) => {
    if (!isTransactionSelectable(row)) {
      return;
    }
    const transactionId = transactionIdForRow(row);
    setSelectedTransactionIds((current) => {
      const next = new Set(current);
      if (next.has(transactionId)) {
        next.delete(transactionId);
      } else {
        next.add(transactionId);
      }
      return next;
    });
  }, [isTransactionSelectable]);

  const handleOpenSelectedInvoicePicker = useCallback(() => {
    if (!canOperateData) {
      setError("当前页面暂不可选择发票或建立关系。");
      return;
    }
    const transactionIds = selectedRows.map(transactionIdForRow);
    if (transactionIds.length === 0) {
      return;
    }
    setInvoicePickerTransactionIds(transactionIds);
    setActiveDrawer("invoicePicker");
  }, [canOperateData, selectedRows]);

  const handleOpenDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => {
    setDetailTarget(target);
    setActiveDrawer("detail");
  }, []);

  function closeDrawer() {
    setActiveDrawer(null);
    setDetailTarget(null);
    setRelationTarget(null);
    setInvoicePickerTransactionIds([]);
  }

  async function handleAttachConfirmed(result: AttachExistingInvoiceResult | AttachExistingInvoicesResult) {
    const operationResult = await runOperation({
      loadingMessage: "正在等待关联关系同步...",
      blockOnError: false,
      action: async ({ setMessage }) => {
        if (result.row) {
          setRows((current) => current.map((row) => (row.id === result.row?.id ? result.row : row)));
        }
        setMessage("正在刷新当前待找发票页面...");
        const rowsPayload = await fetchPendingInvoiceRows(query);
        applyRowsPayload(rowsPayload);
        void loadStatistics().catch(() => undefined);
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "关联关系同步失败。",
    });
    if (operationResult.status !== "success") {
      throw operationResult.error;
    }
    clearSelectedTransactions();
  }

  const loadRelation = useCallback(
    (transactionId: string, signal?: AbortSignal) => fetchPendingInvoiceRelationDetail(transactionId, direction, relationTarget?.kind ?? "all", signal),
    [direction, relationTarget?.kind],
  );
  const loadObjectDetail = useCallback((target: PendingInvoiceObjectDetailTarget, signal?: AbortSignal) => fetchPendingInvoiceObjectDetail(target, signal), []);
  const loadRules = useCallback(() => fetchPendingInvoiceRules(rulesDirection), [rulesDirection]);
  const saveRules = useCallback(async (payload: Parameters<typeof savePendingInvoiceRules>[0]) => {
    const result = await runOperation({
      loadingMessage: "正在保存待找发票规则...",
      blockOnError: false,
      action: async ({ setMessage }) => {
        const savedPayload = await savePendingInvoiceRules(payload, rulesDirection);
        setMessage("正在刷新当前待找发票页面...");
        const rowsPayload = await fetchPendingInvoiceRows(query);
        applyRowsPayload(rowsPayload);
        void loadStatistics().catch(() => undefined);
        return savedPayload;
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "待找发票规则保存失败。",
    });
    if (result.status === "success") {
      return result.value;
    }
    throw result.error;
  }, [applyRowsPayload, direction, loadStatistics, query, rulesDirection, runOperation, statusFilters]);
  const loadCandidates = useCallback(fetchPendingInvoiceCandidatesBatch, []);

  const handleDirectionChange = useCallback((nextDirection: PendingInvoiceDirection) => {
    setDirection(nextDirection);
    setStatusFilters([]);
    setColumnFilters(current => current.filter(filter => filter.field !== "direction"));
    clearSelectedTransactions();
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleToggleStatusFilter = useCallback((codes: AcquisitionStatusCode[]) => {
    clearSelectedTransactions();
    setStatusFilters(current => codes.every(code => current.includes(code))
      ? current.filter(code => !codes.includes(code)) : [...new Set([...current, ...codes])]);
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleSelectAllStatusFilters = useCallback(() => {
    clearSelectedTransactions();
    setStatusFilters(filterOptions.flatMap(option => option.codes));
    setPage(1);
  }, [clearSelectedTransactions, filterOptions]);

  const handleClearStatusFilters = useCallback(() => {
    clearSelectedTransactions();
    setStatusFilters([]);
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleApplyColumnFilters = useCallback((nextFilters: PendingInvoiceColumnFilter[]) => {
    clearSelectedTransactions();
    setColumnFilters((current) => {
      const fields = new Set(nextFilters.map((item) => item.field));
      return [
        ...current.filter((item) => !fields.has(item.field)),
        ...nextFilters,
      ];
    });
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleClearColumnFilters = useCallback((fields: string[]) => {
    clearSelectedTransactions();
    const fieldSet = new Set(fields);
    setColumnFilters((current) => current.filter((item) => !fieldSet.has(item.field)));
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleOpenRules = useCallback((nextRulesDirection: RulesDirection) => {
    setRulesDirection(nextRulesDirection);
    setActiveDrawer("rules");
  }, []);

  const handleMarkSelectedIncomeStatus = useCallback((statusCode: PendingInvoiceIncomeStatusCode) => {
    if (!canOperateData) {
      setError("当前页面暂不可修改收入流水状态。");
      return;
    }
    const transactionIds = selectedRows.map(transactionIdForRow);
    if (transactionIds.length === 0) {
      return;
    }
    setPendingIncomeStatusRows((current) => {
      const next = new Set(current);
      for (const transactionId of transactionIds) {
        next.add(transactionId);
      }
      return next;
    });
    savePendingInvoiceIncomeStatuses(transactionIds, statusCode)
      .then(async (result) => {
        const operationResult = await runOperation({
          loadingMessage: "正在等待待找发票同步...",
          blockOnError: false,
          action: async ({ setMessage }) => {
            if (result.rows.length > 0) {
              const updatedRows = new Map(result.rows.map((row) => [row.id, row]));
              setRows((current) => current.map((item) => updatedRows.get(item.id) ?? item));
            }
            setMessage("正在刷新当前待找发票页面...");
            const rowsPayload = await fetchPendingInvoiceRows(query);
            applyRowsPayload(rowsPayload);
            void loadStatistics().catch(() => undefined);
            return result;
          },
          errorMessage: (caught) => caught instanceof Error ? caught.message : "收入流水状态同步失败。",
        });
        if (operationResult.status !== "success") {
          throw operationResult.error;
        }
        clearSelectedTransactions();
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "收入流水状态保存失败。");
      })
      .finally(() => {
        setPendingIncomeStatusRows((current) => {
          const next = new Set(current);
          for (const transactionId of transactionIds) {
            next.delete(transactionId);
          }
          return next;
        });
      });
  }, [applyRowsPayload, canOperateData, clearSelectedTransactions, loadStatistics, query, runOperation, selectedRows, statusFilters]);

  const summaryCounts = {
    all: sourceSummary?.bankTransactionRows,
    expense: sourceSummary?.expenseRows,
    income: sourceSummary?.incomeRows,
  };
  const selectedStatus = statusFilters.length === 0 || setsEqual(new Set(statusFilters), new Set(filterOptions.flatMap(option => option.codes))) ? "all" : filterOptions.find(option =>
    setsEqual(new Set(option.codes), new Set(statusFilters)))?.key ?? "multiple";
  const statusFilterSummary = selectedStatus === "all" ? "全部" : selectedStatus === "multiple" ? "多状态筛选" : filterOptions.find(option => option.key === selectedStatus)!.label;
  const directionFilter = columnFilters.find(filter => filter.field === "direction");
  const visibleDirections = (["expense", "income"] as const).filter(scope =>
    (direction === "all" || direction === scope)
    && (!directionFilter || !("values" in directionFilter) || directionFilter.values.includes(scope)));
  const classificationGroups: ClassificationGroup[] = (["expense", "income"] as const).map(scope => ({
    id: scope, label: scope === "expense" ? "支出流水" : "收入流水",
    tone: scope === "expense" ? "blue" : "green", count: summaryCounts[scope],
    selected: visibleDirections.length === 1 && visibleDirections[0] === scope && statusFilters.length === 0,
    onSelect: () => handleDirectionChange(scope),
    children: acquisitionOptions(scope).map(option => {
      const selectedCount = option.codes.filter(code => statusFilters.includes(code)).length;
      const matchesDirection = visibleDirections.includes(scope);
      const labels: Record<string, string> = scope === "expense"
        ? { pending: "待取得发票", linked: "有票·付款已覆盖", review: "有票·金额待核对" }
        : { pending: "待开票", linked: "已关联发票" };
      return { id: `${scope}:${option.key}`, label: labels[option.key] ?? option.label,
        count: acquisitionSummary ? option.codes.reduce((sum, code) => sum + acquisitionSummary.scopeStatusCounts[code], 0) : undefined,
        selected: matchesDirection && selectedCount > 0 ? selectedCount === option.codes.length ? true : "mixed" : false,
        onSelect: () => { handleDirectionChange(scope); setStatusFilters(option.codes); },
      };
    }),
  }));

  const statusFilterControl = (
    <div
      className="pending-invoice-status-filter"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setFilterMenuOpen(false);
        }
      }}
    >
      <button
        aria-expanded={filterOpen ? "true" : undefined}
        aria-haspopup="menu"
        aria-label={`筛选发票获取状态：${statusFilterSummary}`}
        className="pending-invoice-status-filter-button"
        onClick={() => setFilterMenuOpen((current) => !current)}
        type="button"
      >
        <span>{statusFilterSummary}</span>
        <ChevronDown aria-hidden="true" size={12} strokeWidth={2.4} />
      </button>
      {filterOpen ? (
        <div className="pending-invoice-status-filter-menu" role="menu">
          <div className="pending-invoice-status-filter-menu-actions">
            <button
              className="pending-invoice-status-filter-menu-item pending-invoice-status-filter-menu-action"
              onClick={handleSelectAllStatusFilters}
              role="menuitem"
              type="button"
            >
              全选
            </button>
            <button
              className="pending-invoice-status-filter-menu-item pending-invoice-status-filter-menu-action"
              onClick={handleClearStatusFilters}
              role="menuitem"
              type="button"
            >
              清空
            </button>
          </div>
          {filterOptions.map((option) => (
            <button
              aria-checked={option.codes.every(code => statusFilters.includes(code))}
              className="pending-invoice-status-filter-menu-item"
              key={option.key}
              onClick={() => handleToggleStatusFilter(option.codes)}
              role="menuitemcheckbox"
              type="button"
            >
              <span className="pending-invoice-status-filter-menu-check" aria-hidden="true">
                {option.codes.every(code => statusFilters.includes(code)) ? "✓" : ""}
              </span>
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );

  const titleAccessory = (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="待找发票数据统计"
        loading={loading && statistics === null}
        coreItems={[
          { label: "流水", value: statistics?.bankTransactionCount, unit: "笔" },
          { label: "OA", value: statistics?.oaCount, unit: "条" },
          { label: "进项发票", value: statistics?.inputInvoiceCount, unit: "张" },
          { label: "销项发票", value: statistics?.outputInvoiceCount, unit: "张" },
        ]}
        detailItems={[
          { label: "支出", value: statistics?.expenseTransactionCount, unit: "笔", tone: "expense" },
          { label: "收入", value: statistics?.incomeTransactionCount, unit: "笔", tone: "income" },
        ]}
      />
    </div>
  );

  return (
    <div className="pending-invoices-page" data-testid="pending-invoices-page">
      <PageScaffold
        actions={(
          <div className="pending-invoices-toolbar-actions pending-invoices-toolbar-actions--primary">
            <Button onPress={() => setRefreshToken((current) => current + 1)} isDisabled={loading} size="sm" variant="secondary">
              刷新
            </Button>
            <Button onPress={() => handleOpenRules("expense")} size="sm" variant="secondary">
              支出待找发票规则设置
            </Button>
            <Button onPress={() => handleOpenRules("income")} size="sm" variant="secondary">
              收入待找发票规则设置
            </Button>
            <Button isDisabled={exportDisabled} onPress={() => setActiveDrawer("export")} size="sm" variant="primary">
              筛选内容导出
            </Button>
          </div>
        )}
        className="invoice-count-page-scaffold"
        title="待找发票"
        titleAccessory={titleAccessory}
      >
        <div className="pending-invoices-content">
        <TableClassificationHeader label="待找发票分类" unit="笔" pending={loading} invalid={Boolean(error)}
          root={{ id: "all", label: "全部流水", count: summaryCounts.all,
            selected: visibleDirections.length === 2 && statusFilters.length === 0, onSelect: () => handleDirectionChange("all") }}
          groups={classificationGroups} />
        <PageToolbar
          className="pending-invoices-toolbar"
          left={error ? <div className="pending-invoices-status-text pending-invoices-status-text--error" role="alert">{error}</div> : null}
          right={(
            <div className="pending-invoices-toolbar-actions">
              {selectedRows.length > 0 ? (
                <div className="pending-invoices-selection-toolbar" role="status">
                  <span>已选 {selectedRows.length} 条流水</span>
                  <span>流水合计 {formatMoney(selectedBankTotal)}</span>
                  {direction === "income" ? (
                    <>
                      <Button
                        isDisabled={!canOperateData || pendingIncomeStatusRows.size > 0}
                        onPress={() => handleMarkSelectedIncomeStatus("income_no_invoice_required")}
                        size="sm"
                        variant="primary"
                      >
                        标记无需开票
                      </Button>
                      <Button
                        isDisabled={!canOperateData || pendingIncomeStatusRows.size > 0}
                        onPress={() => handleMarkSelectedIncomeStatus("cash_income")}
                        size="sm"
                        variant="primary"
                      >
                        标记现金收入
                      </Button>
                    </>
                  ) : (
                    <Button isDisabled={!canOperateData} onPress={handleOpenSelectedInvoicePicker} size="sm" variant="primary">
                      选择发票
                    </Button>
                  )}
                  <Button onPress={clearSelectedTransactions} size="sm" variant="secondary">
                    清除选择
                  </Button>
                </div>
              ) : null}
              <QuerySearch
                ariaLabel="搜索流水"
                className="pending-invoices-search"
                onChange={setKeywordDraft}
                onClear={() => {
                  setKeywordDraft("");
                  setKeyword("");
                  clearSelectedTransactions();
                  setPage(1);
                }}
                onSubmit={() => {
                  setKeyword(keywordDraft.trim());
                  clearSelectedTransactions();
                  setPage(1);
                }}
                placeholder="搜索流水"
                value={keywordDraft}
              />
            </div>
          )}
        />
        <div className="pending-invoices-loading-slot">
          {loading ? <div aria-label="待找发票加载中" className="pending-invoices-loading-bar" role="progressbar" /> : null}
        </div>
        {!canOperateData ? (
          <div className="pending-invoices-status-text pending-invoices-status-text--warning" role="status">
            当前页面暂不可选择发票、修改收入状态或保存规则。
          </div>
        ) : null}
        <PendingInvoicesTable
          rows={rows}
          config={tableConfig}
          onSortChange={handleSortChange}
          filterFields={columnFilterFields}
          columnFilters={columnFilters}
          onApplyColumnFilters={handleApplyColumnFilters}
          onClearColumnFilters={handleClearColumnFilters}
          onOpenRelation={handleOpenRelation}
          onOpenObjectDetail={handleOpenDetail}
          direction={direction}
          statusFilterControl={statusFilterControl}
          selectedTransactionIds={selectedTransactionIds}
          onToggleTransactionSelection={handleToggleTransactionSelection}
          isTransactionSelectable={isTransactionSelectable}
          emptyStateMessage={error ? "待找发票加载失败，请点击刷新重试。" : undefined}
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={(nextPage) => {
            clearSelectedTransactions();
            setPage(nextPage);
          }}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            clearSelectedTransactions();
            setPage(1);
          }}
        />
        </div>
      </PageScaffold>
      <PendingInvoiceRulesDrawer
        open={activeDrawer === "rules"}
        loadRules={loadRules}
        saveRules={saveRules}
        title={rulesDirection === "income" ? "收入待找发票规则设置" : "支出待找发票规则设置"}
        refreshToken={rulesTagRefreshToken}
        onSaved={() => undefined}
        onClose={closeDrawer}
      />
      <PendingInvoiceRelationDrawer onBankSplitSaved={() => setRefreshToken(value => value + 1)}
        open={activeDrawer === "relation"}
        transactionId={relationTarget?.transactionId ?? null}
        detailKind={relationTarget?.kind ?? "all"}
        loadDetail={loadRelation}
        onClose={closeDrawer}
      />
      <PendingInvoiceInvoicePickerDrawer
        open={activeDrawer === "invoicePicker"}
        transactionIds={invoicePickerTransactionIds}
        loadCandidates={loadCandidates}
        previewAttach={(transactionIds, invoiceIds, requestId) => previewAttachExistingInvoices({ transactionIds, invoiceIds, requestId })}
        confirmAttach={(transactionIds, invoiceIds, previewId, requestId) => confirmAttachExistingInvoices({ transactionIds, invoiceIds, previewId, requestId })}
        onConfirmed={handleAttachConfirmed}
        onClose={closeDrawer}
      />
      <PendingInvoiceDetailDrawer onBankSplitSaved={() => setRefreshToken(value => value + 1)}
        open={activeDrawer === "detail"}
        target={detailTarget}
        loadDetail={loadObjectDetail}
        onClose={closeDrawer}
      />
      <PendingInvoiceExportDrawer
        query={query}
        open={activeDrawer === "export"}
        onClose={closeDrawer}
      />
    </div>
  );
}
