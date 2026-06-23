import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import PendingInvoiceDetailDrawer from "../components/pendingInvoices/PendingInvoiceDetailDrawer";
import PendingInvoiceExportDrawer from "../components/pendingInvoices/PendingInvoiceExportDrawer";
import PendingInvoiceInvoicePickerDrawer from "../components/pendingInvoices/PendingInvoiceInvoicePickerDrawer";
import PendingInvoiceRelationDrawer from "../components/pendingInvoices/PendingInvoiceRelationDrawer";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import PendingInvoicesTable from "../components/pendingInvoices/PendingInvoicesTable";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
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
  savePendingInvoiceIncomeStatuses,
} from "../features/pendingInvoices/api";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import { OperationBarrierTimeoutError, operationBarrierTargets, operationBarrierTargetsFromMonths, waitForOperationFreshness } from "../features/operationBarrier/api";
import type {
  AttachExistingInvoiceResult,
  AttachExistingInvoicesResult,
  FetchPendingInvoiceRowsRequest,
  PendingInvoiceDirection,
  PendingInvoiceFilter,
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
} from "../features/pendingInvoices/types";

const DEFAULT_PAGE_SIZE = 50;
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

type ActiveDrawer = "rules" | "relation" | "invoicePicker" | "detail" | "export" | null;
type RelationTarget = { transactionId: string; kind: PendingInvoiceRelationDetailKind } | null;
type RulesDirection = Exclude<PendingInvoiceDirection, "all">;
type StatusFilterSelection =
  | "paid_pending_invoice"
  | "paid_invoiced"
  | "bank_statement_as_invoice"
  | "no_invoice_required"
  | "income_pending_invoice"
  | "income_no_invoice_required"
  | "cash_income";

type StatusFilterOption = {
  value: StatusFilterSelection;
  label: string;
  backendFilter: PendingInvoiceFilter;
};

const EXPENSE_STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  { value: "paid_pending_invoice", label: "已支付待开票", backendFilter: "requires_invoice" },
  { value: "paid_invoiced", label: "已支付已开票", backendFilter: "requires_invoice" },
  { value: "bank_statement_as_invoice", label: "流水代替发票", backendFilter: "bank_statement_as_invoice" },
  { value: "no_invoice_required", label: "无需开票", backendFilter: "no_invoice_required" },
];

const INCOME_STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  { value: "income_pending_invoice", label: "待开发票", backendFilter: "requires_invoice" },
  { value: "income_no_invoice_required", label: "无需开票", backendFilter: "no_invoice_required" },
  { value: "cash_income", label: "现金收入", backendFilter: "cash_income" },
];

const DEFAULT_STATUS_FILTERS: StatusFilterSelection[] = ["paid_pending_invoice", "paid_invoiced"];

function statusFilterOptionsForDirection(direction: PendingInvoiceDirection) {
  if (direction === "expense") {
    return EXPENSE_STATUS_FILTER_OPTIONS;
  }
  if (direction === "income") {
    return INCOME_STATUS_FILTER_OPTIONS;
  }
  return [];
}

function statusFilterLabel(direction: PendingInvoiceDirection, selectedFilters: StatusFilterSelection[]) {
  const options = statusFilterOptionsForDirection(direction);
  if (selectedFilters.length === 0 || options.length === 0) {
    return "全部";
  }
  if (selectedFilters.length === 1) {
    return options.find((option) => option.value === selectedFilters[0])?.label ?? "全部";
  }
  return `已选 ${selectedFilters.length} 项`;
}

function effectiveBackendFilter(direction: PendingInvoiceDirection, selectedFilters: StatusFilterSelection[]): PendingInvoiceFilter {
  const selected = new Set(selectedFilters);
  const backendFilters = new Set(
    statusFilterOptionsForDirection(direction)
      .filter((option) => selected.has(option.value))
      .map((option) => option.backendFilter),
  );
  return backendFilters.size === 1 ? [...backendFilters][0] : "all";
}

function pendingInvoiceRuleRefreshScopes(
  rulesDirection: RulesDirection,
  currentDirection: PendingInvoiceDirection,
  currentFilters: StatusFilterSelection[],
) {
  const refreshFilter = currentDirection === rulesDirection ? effectiveBackendFilter(currentDirection, currentFilters) : "all";
  return [`${rulesDirection}:${refreshFilter}`];
}

function pendingInvoiceAttachRefreshScopes(
  currentDirection: PendingInvoiceDirection,
  currentFilters: StatusFilterSelection[],
  affectedMonths: string[],
) {
  const refreshDirection: RulesDirection = currentDirection === "income" ? "income" : "expense";
  const refreshFilter = effectiveBackendFilter(refreshDirection, currentFilters);
  const baseScope = `${refreshDirection}:${refreshFilter}`;
  const months = Array.from(new Set(affectedMonths.map((month) => month.trim()).filter(Boolean)));
  return months.length > 0 ? months.map((month) => `${baseScope}:${month}`) : [baseScope];
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
  const { runOperation } = useGlobalOperationOverlay();
  const { canMutateData } = useSessionPermissions();
  const pageActiveRef = useRef(active);
  const pendingTagRefreshRef = useRef(false);
  const [direction, setDirection] = useState<PendingInvoiceDirection>("expense");
  const [statusFilters, setStatusFilters] = useState<StatusFilterSelection[]>(DEFAULT_STATUS_FILTERS);
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
  const [pendingIncomeStatusRows, setPendingIncomeStatusRows] = useState<Set<string>>(() => new Set());
  const tagVersionRef = useRef<number | null>(readPersistedTagVersion());

  const filterOpen = filterMenuOpen;

  const queryFilters = useMemo<PendingInvoiceColumnFilter[]>(() => {
    const baseFilters = columnFilters.filter((item) => item.field !== "status_code");
    return statusFilters.length > 0
      ? [...baseFilters, { field: "status_code", operator: "in" as const, values: statusFilters }]
      : baseFilters;
  }, [columnFilters, statusFilters]);

  const query = useMemo<FetchPendingInvoiceRowsRequest>(() => ({
    direction,
    filter: effectiveBackendFilter(direction, statusFilters),
    keyword,
    page,
    pageSize,
    filters: queryFilters,
    sortField,
    sortDirection,
  }), [direction, keyword, page, pageSize, queryFilters, sortDirection, sortField, statusFilters]);

  const applyRowsPayload = useCallback((payload: PendingInvoiceRowsResponse) => {
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
  }, []);

  const loadRows = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchPendingInvoiceRows({ ...query, signal })
      .then(applyRowsPayload)
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
  }, [applyRowsPayload, query]);

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

  const filterOptions = useMemo(() => statusFilterOptionsForDirection(direction), [direction]);

  const tableConfig = useMemo(() => ({
    sortField,
    sortDirection,
  }), [sortDirection, sortField]);
  const exportDisabled = Boolean(error) || Boolean(readModelStatus && readModelStatus !== "fresh");
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
    if (!canMutateData) {
      setError("当前账号仅支持查看和导出，不能选择发票或建立关系。");
      return;
    }
    const transactionIds = selectedRows.map(transactionIdForRow);
    if (transactionIds.length === 0) {
      return;
    }
    setInvoicePickerTransactionIds(transactionIds);
    setActiveDrawer("invoicePicker");
  }, [canMutateData, selectedRows]);

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
    const operationResult = await runOperation({
      loadingMessage: "正在等待关联关系同步...",
      blockOnError: false,
      action: async ({ setMessage }) => {
        if (result.row) {
          setRows((current) => current.map((row) => (row.id === result.row?.id ? result.row : row)));
        }
        try {
          await waitForOperationFreshness([
            ...operationBarrierTargetsFromMonths("workbench_relation", result.affectedMonths),
            ...operationBarrierTargets("pending_invoice", pendingInvoiceAttachRefreshScopes(direction, statusFilters, result.affectedMonths)),
          ]);
        } catch (caught) {
          if (!(caught instanceof OperationBarrierTimeoutError)) {
            throw caught;
          }
        }
        setMessage("正在刷新待找发票...");
        const rowsPayload = await fetchPendingInvoiceRows(query);
        applyRowsPayload(rowsPayload);
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "关联关系同步失败。",
    });
    if (operationResult.status !== "success") {
      throw operationResult.error;
    }
    clearSelectedTransactions();
    closeDrawer();
  }

  const loadRelation = useCallback(
    (transactionId: string) => fetchPendingInvoiceRelationDetail(transactionId, direction, relationTarget?.kind ?? "all"),
    [direction, relationTarget?.kind],
  );
  const loadObjectDetail = useCallback((target: PendingInvoiceObjectDetailTarget) => fetchPendingInvoiceObjectDetail(target), []);
  const loadRules = useCallback(() => fetchPendingInvoiceRules(rulesDirection), [rulesDirection]);
  const saveRules = useCallback(async (payload: Parameters<typeof savePendingInvoiceRules>[0]) => {
    const result = await runOperation({
      loadingMessage: "正在保存待找发票规则...",
      blockOnError: false,
      action: async ({ setMessage }) => {
        const savedPayload = await savePendingInvoiceRules(payload, rulesDirection);
        setMessage("正在等待待找发票读模型同步...");
        try {
          await waitForOperationFreshness(
            operationBarrierTargets("pending_invoice", pendingInvoiceRuleRefreshScopes(rulesDirection, direction, statusFilters)),
          );
        } catch (caught) {
          if (!(caught instanceof OperationBarrierTimeoutError)) {
            throw caught;
          }
        }
        setMessage("正在刷新待找发票...");
        const rowsPayload = await fetchPendingInvoiceRows(query);
        applyRowsPayload(rowsPayload);
        return savedPayload;
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "待找发票规则保存失败。",
    });
    if (result.status === "success") {
      return result.value;
    }
    throw result.error;
  }, [applyRowsPayload, direction, query, rulesDirection, runOperation, statusFilters]);
  const loadCandidates = useCallback(fetchPendingInvoiceCandidatesBatch, []);
  const loadExportPreview = useCallback(() => fetchPendingInvoiceExportPreview(query), [query]);
  const handleDownloadExport = useCallback(() => downloadPendingInvoiceExport(query), [query]);

  const handleDirectionChange = useCallback((nextDirection: PendingInvoiceDirection) => {
    setDirection(nextDirection);
    setStatusFilters([]);
    setColumnFilters([]);
    clearSelectedTransactions();
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleToggleStatusFilter = useCallback((value: StatusFilterSelection) => {
    clearSelectedTransactions();
    setStatusFilters((current) => (
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value]
    ));
    setPage(1);
  }, [clearSelectedTransactions]);

  const handleSelectAllStatusFilters = useCallback(() => {
    clearSelectedTransactions();
    setStatusFilters(filterOptions.map((option) => option.value));
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
    if (!canMutateData) {
      setError("当前账号仅支持查看和导出，不能修改收入流水状态。");
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
            try {
              await waitForOperationFreshness(
                operationBarrierTargets("pending_invoice", pendingInvoiceAttachRefreshScopes("income", statusFilters, result.affectedMonths)),
              );
            } catch (caught) {
              if (!(caught instanceof OperationBarrierTimeoutError)) {
                throw caught;
              }
            }
            setMessage("正在刷新待找发票...");
            const rowsPayload = await fetchPendingInvoiceRows(query);
            applyRowsPayload(rowsPayload);
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
  }, [applyRowsPayload, canMutateData, clearSelectedTransactions, query, runOperation, selectedRows, statusFilters]);

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
  const statusFilterSummary = statusFilterLabel(direction, statusFilters);

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
              aria-checked={statusFilters.includes(option.value)}
              className="pending-invoice-status-filter-menu-item"
              key={option.value}
              onClick={() => handleToggleStatusFilter(option.value)}
              role="menuitemcheckbox"
              type="button"
            >
              <span className="pending-invoice-status-filter-menu-check" aria-hidden="true">
                {statusFilters.includes(option.value) ? "✓" : ""}
              </span>
              <span>{option.label}</span>
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
        {!canMutateData ? (
          <div className="pending-invoices-status-text pending-invoices-status-text--warning" role="status">
            当前账号仅支持查看和导出，不能选择发票、修改收入状态或保存规则。
          </div>
        ) : null}
        {selectedRows.length > 0 ? (
          <div className="pending-invoices-selection-toolbar" role="status">
            <span>已选 {selectedRows.length} 条流水</span>
            <span>流水合计 {formatMoney(selectedBankTotal)}</span>
            {direction === "income" ? (
              <>
                <button
                  className="pending-invoices-button pending-invoices-button--primary"
                  disabled={!canMutateData || pendingIncomeStatusRows.size > 0}
                  onClick={() => handleMarkSelectedIncomeStatus("income_no_invoice_required")}
                  type="button"
                >
                  标记无需开票
                </button>
                <button
                  className="pending-invoices-button pending-invoices-button--primary"
                  disabled={!canMutateData || pendingIncomeStatusRows.size > 0}
                  onClick={() => handleMarkSelectedIncomeStatus("cash_income")}
                  type="button"
                >
                  标记现金收入
                </button>
              </>
            ) : (
              <button className="pending-invoices-button pending-invoices-button--primary" disabled={!canMutateData} onClick={handleOpenSelectedInvoicePicker} type="button">
                选择发票
              </button>
            )}
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
          onOpenObjectDetail={handleOpenDetail}
          direction={direction}
          statusFilterControl={statusFilterControl}
          selectedTransactionIds={selectedTransactionIds}
          onToggleTransactionSelection={handleToggleTransactionSelection}
          isTransactionSelectable={isTransactionSelectable}
          emptyStateMessage={error ? "待找发票加载失败，请点击刷新重试。" : undefined}
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
        onSaved={() => undefined}
        onClose={closeDrawer}
      />
      <PendingInvoiceRelationDrawer
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
    </div>
  );
}
