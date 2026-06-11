import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import ManualInvoiceDialog from "../components/pendingInvoices/ManualInvoiceDialog";
import PendingInvoiceDetailDrawer from "../components/pendingInvoices/PendingInvoiceDetailDrawer";
import PendingInvoiceExportDrawer from "../components/pendingInvoices/PendingInvoiceExportDrawer";
import PendingInvoiceInvoicePickerDrawer from "../components/pendingInvoices/PendingInvoiceInvoicePickerDrawer";
import PendingInvoiceRelationDrawer from "../components/pendingInvoices/PendingInvoiceRelationDrawer";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import PendingInvoicesTable from "../components/pendingInvoices/PendingInvoicesTable";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import {
  confirmAttachExistingInvoices,
  downloadPendingInvoiceExport,
  fetchPendingInvoiceCandidatesBatch,
  fetchPendingInvoiceExportPreview,
  fetchPendingInvoiceFilterOptions,
  fetchPendingInvoiceObjectDetail,
  fetchPendingInvoiceRelationDetail,
  fetchPendingInvoiceRows,
  fetchPendingInvoiceRules,
  previewAttachExistingInvoices,
  savePendingInvoiceRules,
  savePendingInvoiceIncomeStatus,
} from "../features/pendingInvoices/api";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import type {
  AttachExistingInvoiceResult,
  AttachExistingInvoicesResult,
  FetchPendingInvoiceRowsRequest,
  ManualPendingInvoiceResult,
  PendingInvoiceDirection,
  PendingInvoiceFilter,
  PendingInvoiceColumnFilter,
  PendingInvoiceFilterField,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceRow,
  PendingInvoiceSortDirection,
  PendingInvoiceSortField,
  PendingInvoiceSourceSummary,
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

type ActiveDrawer = "rules" | "relation" | "invoicePicker" | "detail" | "export" | null;
type RelationTarget = { transactionId: string } | null;
type RulesDirection = Exclude<PendingInvoiceDirection, "all">;
type ExpenseStatusShortcut = "paid_pending_invoice" | "paid_invoiced";
type StatusFilterSelection = PendingInvoiceFilter | ExpenseStatusShortcut;

const EXPENSE_FILTER_LABELS: Record<PendingInvoiceFilter, string> = {
  all: "全部",
  requires_invoice: "需要开票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
  cash_income: "现金收入",
};

const INCOME_FILTER_LABELS: Record<PendingInvoiceFilter, string> = {
  all: "全部",
  requires_invoice: "待开发票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
  cash_income: "现金收入",
};

const EXPENSE_STATUS_SHORTCUT_LABELS: Record<ExpenseStatusShortcut, string> = {
  paid_pending_invoice: "已支付待开票",
  paid_invoiced: "已支付已开票",
};

function isExpenseStatusShortcut(filter: StatusFilterSelection): filter is ExpenseStatusShortcut {
  return filter === "paid_pending_invoice" || filter === "paid_invoiced";
}

function effectiveBackendFilter(filter: StatusFilterSelection): PendingInvoiceFilter {
  return isExpenseStatusShortcut(filter) ? "requires_invoice" : filter;
}

function filterLabel(direction: PendingInvoiceDirection, filter: StatusFilterSelection) {
  if (direction === "expense" && isExpenseStatusShortcut(filter)) {
    return EXPENSE_STATUS_SHORTCUT_LABELS[filter];
  }
  return (direction === "income" ? INCOME_FILTER_LABELS : EXPENSE_FILTER_LABELS)[filter as PendingInvoiceFilter];
}

function transactionIdForRow(row: PendingInvoiceRow) {
  return row.bankTransaction.id || row.id;
}

function numericMoney(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: number | string) {
  const parsed = typeof value === "number" ? value : numericMoney(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(value || "-");
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

function eventVersion(event: Event) {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const version = Number((event.detail as { version?: unknown }).version);
  return Number.isFinite(version) ? version : null;
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

function displayedPendingInvoiceRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const from = (currentPage - 1) * pageSize + 1;
  const to = Math.min(currentPage * pageSize, total);
  return `${from}-${to} / ${total}`;
}

export default function PendingInvoicesPage() {
  const { active, activationGeneration } = useOptionalPageActivation("pending-invoices");
  const pageActiveRef = useRef(active);
  const pendingTagRefreshRef = useRef(false);
  const [direction, setDirection] = useState<PendingInvoiceDirection>("expense");
  const [filter, setFilter] = useState<StatusFilterSelection>("all");
  const [rows, setRows] = useState<PendingInvoiceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [sourceSummary, setSourceSummary] = useState<PendingInvoiceSourceSummary | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [keyword, setKeyword] = useState("");
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
  const [readModelStatus, setReadModelStatus] = useState("");
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [rulesTagRefreshToken, setRulesTagRefreshToken] = useState(0);
  const [dialogRow, setDialogRow] = useState<PendingInvoiceRow | null>(null);
  const [pendingIncomeStatusRows, setPendingIncomeStatusRows] = useState<Set<string>>(() => new Set());
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());

  const filterOpen = filterMenuOpen;

  const queryFilters = useMemo<PendingInvoiceColumnFilter[]>(() => {
    const baseFilters = isExpenseStatusShortcut(filter)
      ? columnFilters.filter((item) => item.field !== "status_code")
      : columnFilters;
    return isExpenseStatusShortcut(filter)
      ? [...baseFilters, { field: "status_code", operator: "in" as const, values: [filter] }]
      : baseFilters;
  }, [columnFilters, filter]);

  const query = useMemo<FetchPendingInvoiceRowsRequest>(() => ({
    direction,
    filter: effectiveBackendFilter(filter),
    keyword,
    page,
    pageSize,
    filters: queryFilters,
    sortField,
    sortDirection,
  }), [direction, filter, keyword, page, pageSize, queryFilters, sortDirection, sortField]);

  const loadRows = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchPendingInvoiceRows({ ...query, signal })
      .then((payload) => {
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setSourceSummary(payload.summary.sourceSummary ?? null);
        setReadModelStatus(payload.readModelStatus);
        const version = payload.tagDictionary?.version;
        if (typeof version === "number" && version > 0) {
          const previousVersion = tagVersionRef.current;
          tagVersionRef.current = version;
          persistTagVersion(version);
          if (previousVersion !== null && previousVersion !== version) {
            setRulesTagRefreshToken((current) => current + 1);
          }
        }
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "待找发票加载失败。");
        }
      })
      .finally(() => {
        if (!signal?.aborted) {
          setLoading(false);
        }
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    loadRows(controller.signal);
    return () => controller.abort();
  }, [loadRows, refreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    fetchPendingInvoiceFilterOptions({
      direction,
      filter: query.filter,
      keyword,
      filters: queryFilters,
      sortField,
      sortDirection,
      signal: controller.signal,
    })
      .then((payload) => setColumnFilterFields(payload.fields))
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setColumnFilterFields([]);
        }
    });
    return () => controller.abort();
  }, [direction, keyword, query.filter, queryFilters, sortDirection, sortField, refreshToken]);

  useEffect(() => {
    pageActiveRef.current = active;
    if (!active || !pendingTagRefreshRef.current) {
      return;
    }
    pendingTagRefreshRef.current = false;
    setRulesTagRefreshToken((current) => current + 1);
    setRefreshToken((current) => current + 1);
  }, [active, activationGeneration]);

  useEffect(() => {
    const handleTagUpdate = (event: Event) => {
      const version = eventVersion(event);
      if (version !== null) {
        tagVersionRef.current = version;
        persistTagVersion(version);
      }
      if (!pageActiveRef.current) {
        pendingTagRefreshRef.current = true;
        return;
      }
      setRulesTagRefreshToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener(TAG_SYNC_EVENT, handleTagUpdate);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.onmessage = (message) => {
        const version = Number((message.data as { version?: unknown } | undefined)?.version);
        window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, { detail: { version: Number.isFinite(version) ? version : undefined } }));
      };
    }

    const handleFocus = () => {
      if (!pageActiveRef.current) {
        return;
      }
      const persistedVersion = readPersistedTagVersion();
      if (persistedVersion !== null && persistedVersion !== tagVersionRef.current) {
        tagVersionRef.current = persistedVersion;
        setRulesTagRefreshToken((current) => current + 1);
      }
      setRefreshToken((current) => current + 1);
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener(TAG_SYNC_EVENT, handleTagUpdate);
      window.removeEventListener("focus", handleFocus);
      channel?.close();
    };
  }, []);

  const filterOptions = useMemo<StatusFilterSelection[]>(() => (
    direction === "expense" ? [
    "all",
    "requires_invoice",
    "paid_pending_invoice",
    "paid_invoiced",
    "bank_statement_as_invoice",
    "no_invoice_required",
  ] : direction === "income" ? [
    "all",
    "requires_invoice",
    "no_invoice_required",
    "cash_income",
  ] : ["all"]
  ), [direction]);

  const tableConfig = useMemo(() => ({
    sortField,
    sortDirection,
  }), [sortDirection, sortField]);
  const exportDisabled = Boolean(readModelStatus && readModelStatus !== "fresh");
  const isTransactionSelectable = useCallback((row: PendingInvoiceRow) => (
    direction !== "income" && row.availableActions.includes("attach_existing_invoice")
  ), [direction]);
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

  const handleOpenRelation = useCallback((row: PendingInvoiceRow) => {
    setRelationTarget({ transactionId: row.bankTransaction.id || row.id });
    setActiveDrawer("relation");
  }, []);

  const handleOpenInvoicePicker = useCallback((row: PendingInvoiceRow) => {
    setInvoicePickerTransactionIds([transactionIdForRow(row)]);
    setActiveDrawer("invoicePicker");
  }, []);

  const handleOpenInvoicePickerById = useCallback((transactionId: string) => {
    setInvoicePickerTransactionIds([transactionId]);
    setActiveDrawer("invoicePicker");
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
    const transactionIds = selectedRows.map(transactionIdForRow);
    if (transactionIds.length === 0) {
      return;
    }
    setInvoicePickerTransactionIds(transactionIds);
    setActiveDrawer("invoicePicker");
  }, [selectedRows]);

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

  function handleManualConfirmed(result: ManualPendingInvoiceResult) {
    setDialogRow(null);
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: [...result.affectedTransactionIds, ...result.affectedInvoiceIds],
      source: "pending_invoice_manual_invoice",
    });
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: result.affectedTransactionIds,
      source: "pending_invoice_manual_invoice",
    });
    const updatedRow = result.row;
    if (updatedRow) {
      setRows((current) => current.map((row) => (row.id === updatedRow.id ? updatedRow : row)));
      return;
    }
    setRefreshToken((current) => current + 1);
  }

  function handleAttachConfirmed(result: AttachExistingInvoiceResult | AttachExistingInvoicesResult) {
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.invoiceFactUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: [...result.affectedTransactionIds, ...result.affectedInvoiceIds],
      source: "pending_invoice_attach_existing_invoice",
    });
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      affectedMonths: result.affectedMonths,
      affectedRowIds: result.affectedTransactionIds,
      source: "pending_invoice_attach_existing_invoice",
    });
    if (result.row) {
      setRows((current) => current.map((row) => (row.id === result.row?.id ? result.row : row)));
    } else {
      setRefreshToken((current) => current + 1);
    }
    clearSelectedTransactions();
    closeDrawer();
  }

  const loadRelation = useCallback((transactionId: string) => fetchPendingInvoiceRelationDetail(transactionId, direction), [direction]);
  const loadObjectDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => fetchPendingInvoiceObjectDetail(target), []);
  const loadRules = useCallback(() => fetchPendingInvoiceRules(rulesDirection), [rulesDirection]);
  const saveRules = useCallback((payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, rulesDirection), [rulesDirection]);
  const loadCandidates = useCallback(fetchPendingInvoiceCandidatesBatch, []);
  const loadExportPreview = useCallback(() => fetchPendingInvoiceExportPreview(query), [query]);
  const handleDownloadExport = useCallback(() => downloadPendingInvoiceExport(query), [query]);

  const handleDirectionChange = useCallback((nextDirection: PendingInvoiceDirection) => {
    setDirection(nextDirection);
    setFilter("all");
    setColumnFilters([]);
    clearSelectedTransactions();
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

  const handleMarkIncomeStatus = useCallback((row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => {
    setPendingIncomeStatusRows((current) => new Set(current).add(row.id));
    savePendingInvoiceIncomeStatus(row.id, statusCode)
      .then((result) => {
        if (result.row) {
          setRows((current) => current.map((item) => (item.id === result.row?.id ? result.row : item)));
        }
        setRefreshToken((current) => current + 1);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "收入流水状态保存失败。");
      })
      .finally(() => {
        setPendingIncomeStatusRows((current) => {
          const next = new Set(current);
          next.delete(row.id);
          return next;
        });
      });
  }, []);

  const compactStatusText = error
    ? error
    : readModelStatus === "refreshing"
      ? "数据刷新中"
      : readModelStatus && !["fresh", "refreshing"].includes(readModelStatus)
        ? `读模型 ${readModelStatus}，写入和导出已暂停`
        : "";

  const summaryCounts = {
    all: sourceSummary?.bankTransactionRows ?? 0,
    expense: sourceSummary?.expenseRows ?? 0,
    income: sourceSummary?.incomeRows ?? 0,
  };
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);

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
        aria-label={`筛选发票获取状态：${filterLabel(direction, filter)}`}
        className="pending-invoice-status-filter-button"
        onClick={() => setFilterMenuOpen((current) => !current)}
        type="button"
      >
        <span>{filterLabel(direction, filter)}</span>
        <ChevronDown aria-hidden="true" size={12} strokeWidth={2.4} />
      </button>
      {filterOpen ? (
        <div className="pending-invoice-status-filter-menu" role="menu">
          {filterOptions.map((option) => (
            <button
              aria-current={option === filter ? "true" : undefined}
              className="pending-invoice-status-filter-menu-item"
              key={option}
              onClick={() => {
                setFilter(option);
                clearSelectedTransactions();
                setPage(1);
                setFilterMenuOpen(false);
              }}
              role="menuitem"
              type="button"
            >
              {filterLabel(direction, option)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="pending-invoices-page" data-testid="pending-invoices-page">
      <PageScaffold
        description={(
          <div aria-label="待找发票流水范围" className="pending-invoices-direction-segment" role="group">
            {([
              ["all", `全部 ${summaryCounts.all}`],
              ["expense", `支出 ${summaryCounts.expense}`],
              ["income", `收入 ${summaryCounts.income}`],
            ] as const).map(([value, label]) => (
              <button
                aria-pressed={direction === value}
                className="pending-invoices-direction-button"
                key={value}
                onClick={() => handleDirectionChange(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        )}
        actions={(
          <div className="pending-invoices-toolbar-actions pending-invoices-toolbar-actions--primary">
            <button className="pending-invoices-button" onClick={() => handleOpenRules("expense")} type="button">
              支出待找发票规则设置
            </button>
            <button className="pending-invoices-button" onClick={() => handleOpenRules("income")} type="button">
              收入待找发票规则设置
            </button>
            <button
              className="pending-invoices-button pending-invoices-button--primary"
              disabled={exportDisabled}
              onClick={() => setActiveDrawer("export")}
              type="button"
            >
              筛选内容导出
            </button>
          </div>
        )}
        className="pending-invoices-page__scaffold"
        title="待找发票"
      >
        <PageToolbar
          className="pending-invoices-toolbar"
          left={(
            <div
              className={`pending-invoices-status-text${error ? " pending-invoices-status-text--error" : readModelStatus && !["fresh", "refreshing"].includes(readModelStatus) ? " pending-invoices-status-text--warning" : ""}`}
              role={error ? "alert" : "status"}
            >
              {compactStatusText}
            </div>
          )}
          right={(
            <div className="pending-invoices-toolbar-actions">
              <input
                aria-label="搜索流水"
                className="pending-invoices-search"
                onChange={(event) => {
                  setKeyword(event.target.value);
                  clearSelectedTransactions();
                  setPage(1);
                }}
                placeholder="搜索流水"
                type="search"
                value={keyword}
              />
              <button className="pending-invoices-button" onClick={() => setRefreshToken((current) => current + 1)} type="button">
                刷新
              </button>
            </div>
          )}
        />
        <div className="pending-invoices-loading-slot">
          {loading ? <div aria-label="待找发票加载中" className="pending-invoices-loading-bar" role="progressbar" /> : null}
        </div>
        {selectedRows.length > 0 ? (
          <div className="pending-invoices-selection-toolbar" role="status">
            <span>已选 {selectedRows.length} 条流水</span>
            <span>流水合计 {formatMoney(selectedBankTotal)}</span>
            <button className="pending-invoices-button pending-invoices-button--primary" onClick={handleOpenSelectedInvoicePicker} type="button">
              选择发票
            </button>
            <button className="pending-invoices-button" onClick={clearSelectedTransactions} type="button">
              清除选择
            </button>
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
          onOpenInvoicePicker={handleOpenInvoicePicker}
          onOpenManualInvoice={setDialogRow}
          onOpenObjectDetail={handleOpenDetail}
          onMarkIncomeStatus={handleMarkIncomeStatus}
          direction={direction}
          statusFilterControl={statusFilterControl}
          pendingActionRowIds={pendingIncomeStatusRows}
          selectedTransactionIds={selectedTransactionIds}
          onToggleTransactionSelection={handleToggleTransactionSelection}
          isTransactionSelectable={isTransactionSelectable}
        />
        <div className="pending-invoices-pagination">
          <label className="pending-invoices-pagination-size">
            <span>每页行数</span>
            <select
              aria-label="每页行数"
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                clearSelectedTransactions();
                setPage(1);
              }}
              value={pageSize}
            >
              {[25, 50, 100].map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <span className="pending-invoices-pagination-range">
            {displayedPendingInvoiceRange(currentPage, pageSize, total)}
          </span>
          <div className="pending-invoices-pagination-actions">
            <button
              aria-label="上一页"
              disabled={currentPage <= 1}
              onClick={() => {
                clearSelectedTransactions();
                setPage(currentPage - 1);
              }}
              type="button"
            >
              上一页
            </button>
            <button
              aria-label="下一页"
              disabled={currentPage >= totalPages}
              onClick={() => {
                clearSelectedTransactions();
                setPage(currentPage + 1);
              }}
              type="button"
            >
              下一页
            </button>
          </div>
        </div>
      </PageScaffold>
      <PendingInvoiceRulesDrawer
        open={activeDrawer === "rules"}
        loadRules={loadRules}
        saveRules={saveRules}
        title={rulesDirection === "income" ? "收入待找发票规则设置" : "支出待找发票规则设置"}
        refreshToken={rulesTagRefreshToken}
        onSaved={(savedPayload) => {
          setReadModelStatus(savedPayload.readModelStatus ?? "refreshing");
          setRefreshToken((current) => current + 1);
        }}
        onClose={closeDrawer}
      />
      <PendingInvoiceRelationDrawer
        open={activeDrawer === "relation"}
        transactionId={relationTarget?.transactionId ?? null}
        loadDetail={loadRelation}
        onOpenInvoicePicker={handleOpenInvoicePickerById}
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
      <PendingInvoiceDetailDrawer
        open={activeDrawer === "detail"}
        target={detailTarget}
        loadDetail={loadObjectDetail}
        onClose={closeDrawer}
      />
      <PendingInvoiceExportDrawer
        open={activeDrawer === "export"}
        loadPreview={loadExportPreview}
        downloadExport={handleDownloadExport}
        onClose={closeDrawer}
      />
      <ManualInvoiceDialog
        open={dialogRow !== null}
        row={dialogRow}
        direction={direction}
        onClose={() => setDialogRow(null)}
        onConfirmed={handleManualConfirmed}
      />
    </div>
  );
}
