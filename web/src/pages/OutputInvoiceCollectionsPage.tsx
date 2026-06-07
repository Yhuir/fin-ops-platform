import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import CollectionStatusReminderDrawer from "../components/outputInvoiceCollections/CollectionStatusReminderDrawer";
import CollectionStatusRulesDrawer from "../components/outputInvoiceCollections/CollectionStatusRulesDrawer";
import OutputInvoiceCollectionDetailDrawer from "../components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer";
import OutputInvoiceCollectionsTable from "../components/outputInvoiceCollections/OutputInvoiceCollectionsTable";
import RedInvoiceRelationDrawer from "../components/outputInvoiceCollections/RedInvoiceRelationDrawer";
import ReceiptHistoryDrawer from "../components/outputInvoiceCollections/ReceiptHistoryDrawer";
import ReceiptPreviewDrawer from "../components/outputInvoiceCollections/ReceiptPreviewDrawer";
import ReceiptSettingsDrawer from "../components/outputInvoiceCollections/ReceiptSettingsDrawer";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  cancelOutputInvoiceCollectionReminder,
  fetchOutputInvoiceCollectionBankTransactionDetail,
  fetchOutputInvoiceCollectionFilterOptions,
  fetchOutputInvoiceCollectionInvoiceDetail,
  fetchOutputInvoiceCollectionRows,
  fetchOutputInvoiceCollectionRowRelationDetail,
  fetchOutputInvoiceCollectionStatusRules,
  fetchOutputInvoiceReceiptHistory,
  fetchOutputInvoiceReceiptSettings,
  createOutputInvoiceReceipt,
  confirmOutputInvoiceRedRelation,
  nextSortDirection,
  previewOutputInvoiceReceipt,
  reissueOutputInvoiceReceipt,
  revokeOutputInvoiceRedRelation,
  updateOutputInvoiceCollectionReminder,
  updateOutputInvoiceCollectionStatus,
  updateOutputInvoiceReceiptSettings,
  voidOutputInvoiceReceipt,
} from "../features/outputInvoiceCollections/api";
import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionQuery,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionStatusRulesResponse,
  OutputInvoiceCollectionWorkflow,
} from "../features/outputInvoiceCollections/types";

const initialQuery: OutputInvoiceCollectionQuery = {
  page: 1,
  pageSize: 20,
  keyword: "",
  invoiceDateFrom: "",
  invoiceDateTo: "",
  month: "",
  filters: [],
  sortField: "",
  sortDirection: "",
  activeWorkflow: null,
  detailTarget: null,
};
const READ_MODEL_REFRESH_RETRY_MS = 10000;

function isFilterArray(value: unknown): value is OutputInvoiceCollectionFilter[] {
  return Array.isArray(value) && value.every((item) => (
    item
    && typeof item === "object"
    && typeof (item as OutputInvoiceCollectionFilter).field === "string"
    && typeof (item as OutputInvoiceCollectionFilter).operator === "string"
  ));
}

function isDetailTarget(value: unknown): value is OutputInvoiceCollectionDetailTarget | null {
  if (value === null) {
    return true;
  }
  if (!value || typeof value !== "object") {
    return false;
  }
  const target = value as OutputInvoiceCollectionDetailTarget;
  return typeof target.id === "string"
    && ["invoice", "bank", "relationList"].includes(target.kind);
}

function isWorkflow(value: unknown): value is OutputInvoiceCollectionWorkflow {
  if (value === null) {
    return true;
  }
  if (!value || typeof value !== "object") {
    return false;
  }
  const workflow = value as NonNullable<OutputInvoiceCollectionWorkflow>;
  if (workflow.kind === "statusRules") {
    return true;
  }
  if (workflow.kind === "receiptSettings") {
    return true;
  }
  if (workflow.kind === "collectionStatus" || workflow.kind === "redRelation" || workflow.kind === "receiptPreview") {
    return typeof workflow.rowId === "string";
  }
  if (workflow.kind === "receiptHistory") {
    return typeof workflow.invoiceId === "string" && typeof workflow.rowId === "string";
  }
  return false;
}

function validateQuery(value: unknown): value is OutputInvoiceCollectionQuery {
  if (!value || typeof value !== "object") {
    return false;
  }
  const query = value as OutputInvoiceCollectionQuery;
  return Number.isInteger(query.page)
    && Number.isInteger(query.pageSize)
    && typeof query.keyword === "string"
    && typeof query.invoiceDateFrom === "string"
    && typeof query.invoiceDateTo === "string"
    && typeof query.month === "string"
    && isFilterArray(query.filters)
    && typeof query.sortField === "string"
    && (query.sortDirection === "" || query.sortDirection === "asc" || query.sortDirection === "desc")
    && isWorkflow(query.activeWorkflow)
    && isDetailTarget(query.detailTarget);
}

function restoreQuery(raw: unknown): OutputInvoiceCollectionQuery {
  if (!validateQuery(raw)) {
    return initialQuery;
  }
  return {
    ...initialQuery,
    ...raw,
    page: Math.max(1, raw.page),
    pageSize: [20, 50, 100].includes(raw.pageSize) ? raw.pageSize : initialQuery.pageSize,
  };
}

function filterOptionsByField(fields: Array<OutputInvoiceCollectionFilterFieldConfig & { options?: OutputInvoiceCollectionFilterOption[] }>) {
  return fields.reduce<Record<string, OutputInvoiceCollectionFilterOption[]>>((accumulator, field) => {
    accumulator[field.field] = field.options ?? [];
    return accumulator;
  }, {});
}

function filterConfigsFromOptions(fields: Array<OutputInvoiceCollectionFilterFieldConfig & { options?: OutputInvoiceCollectionFilterOption[] }>) {
  return fields.map(({ options: _options, ...field }) => field);
}

function normalizeFilterValue(filter: {
  field: string;
  operator: string;
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
}): OutputInvoiceCollectionFilter | null {
  if (filter.operator === "in") {
    const values = Array.isArray(filter.values) ? filter.values.filter(Boolean) : [];
    return values.length > 0 ? { field: filter.field, operator: "in", values } : null;
  }
  if (filter.operator === "equals") {
    const value = typeof filter.value === "string" ? filter.value : "";
    return value ? { field: filter.field, operator: "equals", value } : null;
  }
  if (filter.operator === "contains") {
    const value = typeof filter.value === "string" ? filter.value : "";
    return value ? { field: filter.field, operator: "contains", value } : null;
  }
  if (filter.operator === "between") {
    return { field: filter.field, operator: "between", value: filter.value ?? null };
  }
  return null;
}

export default function OutputInvoiceCollectionsPage() {
  const { active } = useOptionalPageActivation("output-invoice-collections");
  const { canAdminAccess } = useSessionPermissions();
  const querySession = usePageSessionState({
    pageKey: "output-invoice-collections",
    stateKey: "query",
    version: 1,
    initialValue: initialQuery,
    ttlMs: 24 * 60 * 60 * 1000,
    storage: "session",
    restore: restoreQuery,
    validate: validateQuery,
    debounceMs: 100,
  });
  const query = querySession.value;
  const setQuery = querySession.setValue;
  const [rows, setRows] = useState<OutputInvoiceCollectionRow[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState({
    invoiceCount: 0,
    totalWithTax: "0.00",
    collectedAmount: "0.00",
    pendingAmount: "0.00",
    pendingCollectionCount: 0,
    partialCollectionCount: 0,
    receiptPendingCount: 0,
  });
  const [filterConfigs, setFilterConfigs] = useState<OutputInvoiceCollectionFilterFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OutputInvoiceCollectionFilterOption[]>>({});
  const [statusRulesPayload, setStatusRulesPayload] = useState<OutputInvoiceCollectionStatusRulesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [readModelStatus, setReadModelStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(() => new Set());
  const [keywordDraft, setKeywordDraft] = useState(query.keyword);
  const requestIdRef = useRef(0);

  useEffect(() => {
    setKeywordDraft(query.keyword);
  }, [query.keyword]);

  const loadRows = useCallback((mode: "reset" | "refresh", signal?: AbortSignal) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === "reset") {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    const request = {
      page: query.page,
      pageSize: query.pageSize,
      keyword: query.keyword,
      invoiceDateFrom: query.invoiceDateFrom,
      invoiceDateTo: query.invoiceDateTo,
      month: query.month,
      filters: query.filters,
      sortField: query.sortField,
      sortDirection: query.sortDirection,
      signal,
    };
    Promise.all([
      fetchOutputInvoiceCollectionRows(request),
      fetchOutputInvoiceCollectionFilterOptions({
        keyword: query.keyword,
        invoiceDateFrom: query.invoiceDateFrom,
        invoiceDateTo: query.invoiceDateTo,
        month: query.month,
        filters: query.filters,
        signal,
      }),
      fetchOutputInvoiceCollectionStatusRules(signal).catch(() => null),
    ])
      .then(([payload, optionsPayload, rulesPayload]) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setSummary(payload.summary ?? {
          invoiceCount: payload.pagination.total,
          totalWithTax: "0.00",
          collectedAmount: "0.00",
          pendingAmount: "0.00",
          pendingCollectionCount: 0,
          partialCollectionCount: 0,
          receiptPendingCount: 0,
        });
        setFilterConfigs(payload.filterConfig.length > 0 ? payload.filterConfig : filterConfigsFromOptions(optionsPayload.fields));
        setFilterOptions(filterOptionsByField(optionsPayload.fields));
        if (rulesPayload) {
          setStatusRulesPayload(rulesPayload);
        }
        setReadModelStatus(
          payload.readModelStatus === "refreshing" || optionsPayload.readModelStatus === "refreshing"
            ? "refreshing"
            : payload.readModelStatus || optionsPayload.readModelStatus || "",
        );
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== requestIdRef.current) {
          return;
        }
        setRows([]);
        setTotal(0);
        setSummary({
          invoiceCount: 0,
          totalWithTax: "0.00",
          collectedAmount: "0.00",
          pendingAmount: "0.00",
          pendingCollectionCount: 0,
          partialCollectionCount: 0,
          receiptPendingCount: 0,
        });
        setFilterConfigs([]);
        setFilterOptions({});
        setReadModelStatus("");
        setError(caught instanceof Error ? caught.message : "销项发票收款情况加载失败，请稍后重试。");
      })
      .finally(() => {
        if (requestId === requestIdRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      });
  }, [
    query.filters,
    query.invoiceDateFrom,
    query.invoiceDateTo,
    query.keyword,
    query.month,
    query.page,
    query.pageSize,
    query.sortDirection,
    query.sortField,
  ]);

  useEffect(() => {
    const controller = new AbortController();
    loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [loadRows]);

  useEffect(() => {
    if (!active || readModelStatus !== "refreshing" || loading || refreshing) {
      return undefined;
    }
    const retryId = window.setTimeout(() => loadRows("refresh"), READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [active, loadRows, loading, readModelStatus, refreshing]);

  const handleKeywordSubmit = useCallback(() => {
    setQuery((current) => ({
      ...current,
      page: 1,
      keyword: keywordDraft.trim(),
    }));
  }, [keywordDraft, setQuery]);

  const handleSortChange = useCallback((field: string, direction?: OutputInvoiceCollectionSortDirection) => {
    setQuery((current) => ({
      ...current,
      page: 1,
      sortField: field,
      sortDirection: direction ?? nextSortDirection(current.sortField, current.sortDirection, field),
    }));
  }, [setQuery]);

  const handleFilterApply = useCallback((filter: {
    field: string;
    operator: string;
    value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
    values?: string[];
  }) => {
    const normalized = normalizeFilterValue(filter);
    setQuery((current) => {
      const filters = current.filters.filter((item) => item.field !== filter.field);
      return {
        ...current,
        page: 1,
        filters: normalized ? [...filters, normalized] : filters,
      };
    });
  }, [setQuery]);

  const handleFilterClear = useCallback((field: string) => {
    setQuery((current) => ({
      ...current,
      page: 1,
      filters: current.filters.filter((filter) => filter.field !== field),
    }));
  }, [setQuery]);

  const handlePageChange = useCallback((page: number) => {
    setQuery((current) => ({ ...current, page }));
  }, [setQuery]);

  const handlePageSizeChange = useCallback((pageSize: number) => {
    setQuery((current) => ({ ...current, page: 1, pageSize }));
  }, [setQuery]);

  const handleToggleCellExpand = useCallback((rowId: string, cellId: string) => {
    const key = `${rowId}:${cellId}`;
    setExpandedCells((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleOpenDetail = useCallback((target: OutputInvoiceCollectionDetailTarget) => {
    setQuery((current) => ({ ...current, detailTarget: target }));
  }, [setQuery]);

  const handleCloseDetail = useCallback(() => {
    setQuery((current) => ({ ...current, detailTarget: null }));
  }, [setQuery]);

  const handleOpenWorkflow = useCallback((target: NonNullable<OutputInvoiceCollectionWorkflow>) => {
    setQuery((current) => ({ ...current, activeWorkflow: target }));
  }, [setQuery]);

  const handleCloseWorkflow = useCallback(() => {
    setQuery((current) => ({ ...current, activeWorkflow: null }));
  }, [setQuery]);

  const loadDetail = useCallback((target: OutputInvoiceCollectionDetailTarget) => {
    if (target.kind === "invoice") {
      return fetchOutputInvoiceCollectionInvoiceDetail(target.id);
    }
    if (target.kind === "bank") {
      return fetchOutputInvoiceCollectionBankTransactionDetail(target.id);
    }
    return fetchOutputInvoiceCollectionRowRelationDetail(target);
  }, []);

  const activeWorkflow = query.activeWorkflow;
  const receiptHistoryInvoiceId = activeWorkflow?.kind === "receiptHistory" ? activeWorkflow.invoiceId : null;
  const receiptPreviewRow = activeWorkflow?.kind === "receiptPreview"
    ? rows.find((row) => row.id === activeWorkflow.rowId) ?? null
    : null;
  const collectionStatusRow = activeWorkflow?.kind === "collectionStatus"
    ? rows.find((row) => row.id === activeWorkflow.rowId) ?? null
    : null;
  const redRelationRow = activeWorkflow?.kind === "redRelation"
    ? rows.find((row) => row.id === activeWorkflow.rowId) ?? null
    : null;
  const manualStatusOptions = useMemo(() => {
    const options = statusRulesPayload?.manualStatusOptions;
    if (Array.isArray(options) && options.length > 0) {
      return options.map((option) => ({ code: option.code, label: option.label }));
    }
    return (statusRulesPayload?.rules ?? [])
      .filter((rule) => rule.id || rule.code)
      .map((rule) => ({ code: rule.id || rule.code || "", label: rule.label }))
      .filter((option) => option.code);
  }, [statusRulesPayload]);
  const quickCollectionStatusOptions = useMemo(() => {
    const options = filterOptions.collection_status ?? [];
    if (options.length > 0) {
      return options.map((option) => ({ code: option.value, label: option.label }));
    }
    return (statusRulesPayload?.rules ?? [])
      .filter((rule) => rule.id || rule.code)
      .map((rule) => ({ code: rule.id || rule.code || "", label: rule.label }))
      .filter((option) => option.code);
  }, [filterOptions.collection_status, statusRulesPayload]);

  const applyQuickStatusFilter = useCallback((statusCode: string) => {
    setQuery((current) => {
      const filters = current.filters.filter((filter) => filter.field !== "collection_status");
      return {
        ...current,
        page: 1,
        filters: statusCode ? [...filters, { field: "collection_status", operator: "in", values: [statusCode] }] : filters,
      };
    });
  }, [setQuery]);

  const handleLifecycleChanged = useCallback(() => {
    loadRows("refresh");
  }, [loadRows]);

  const actions = useMemo(() => (
    <div className="output-invoice-collections-actions">
      <button
        className="output-invoice-collections-button"
        onClick={() => handleOpenWorkflow({ kind: "statusRules" })}
        type="button"
      >
        收款状态规则
      </button>
      {canAdminAccess ? (
        <button
          className="output-invoice-collections-button"
          onClick={() => handleOpenWorkflow({ kind: "receiptSettings" })}
          type="button"
        >
          收据编号设置
        </button>
      ) : null}
      <button
        className="output-invoice-collections-button output-invoice-collections-button--primary"
        disabled={refreshing}
        onClick={() => loadRows("refresh")}
        type="button"
      >
        <RefreshCw aria-hidden="true" size={16} strokeWidth={2.3} />
        刷新
      </button>
    </div>
  ), [canAdminAccess, handleOpenWorkflow, loadRows, refreshing]);
  const isEmpty = !loading && !error && rows.length === 0;

  return (
    <>
    <div className="output-invoice-collections-page" data-testid="output-invoice-collections-page">
      <PageScaffold
        title="销项发票收款情况"
        description="以销项发票为主对象查看收款状态、收入流水和收据预览。"
        actions={actions}
      >
        <div className="output-invoice-collections-content">
          <PageToolbar className="output-invoice-collections-query">
            <div className="output-invoice-collections-query__grid">
              <label className="output-invoice-collections-field output-invoice-collections-field--keyword">
                <span>关键字</span>
                <input
                  value={keywordDraft}
                  onChange={(event) => setKeywordDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      handleKeywordSubmit();
                    }
                  }}
                />
              </label>
              <button
                className="output-invoice-collections-button"
                onClick={handleKeywordSubmit}
                type="button"
              >
                查询
              </button>
              <label className="output-invoice-collections-field">
                <span>月份</span>
                <input
                  type="month"
                  value={query.month}
                  onChange={(event) => setQuery((current) => ({ ...current, page: 1, month: event.target.value }))}
                />
              </label>
              <label className="output-invoice-collections-field">
                <span>收款状态</span>
                <select
                  value={query.filters.find((filter) => filter.field === "collection_status")?.values?.[0] ?? ""}
                  onChange={(event) => applyQuickStatusFilter(event.target.value)}
                >
                  <option value="">全部</option>
                  {quickCollectionStatusOptions.map((option) => (
                    <option key={option.code} value={option.code}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </PageToolbar>
          <div className="output-invoice-collections-summary">
            <SummaryTile label="销项发票数" value={String(summary.invoiceCount)} />
            <SummaryTile label="待收款金额" value={formatMoney(summary.pendingAmount)} />
            <SummaryTile label="已收金额" value={formatMoney(summary.collectedAmount)} />
            <SummaryTile label="待出收据数" value={String(summary.receiptPendingCount)} />
          </div>
          {error ? <div className="output-invoice-collections-alert" role="alert">{error}</div> : null}
          {loading ? (
            <div className="output-invoice-collections-loading" aria-label="销项发票收款情况加载中">
              <span className="output-invoice-collections-loading__bar" />
              <span className="output-invoice-collections-loading__panel" />
              <span className="output-invoice-collections-loading__panel" />
            </div>
          ) : (
            <>
              {isEmpty ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
              <OutputInvoiceCollectionsTable
                rows={rows}
                page={query.page}
                pageSize={query.pageSize}
                total={total}
                sortField={query.sortField}
                sortDirection={query.sortDirection}
                filters={query.filters}
                filterConfigs={filterConfigs}
                filterOptions={filterOptions}
                expandedCells={expandedCells}
                onToggleCellExpand={handleToggleCellExpand}
                onOpenDetail={handleOpenDetail}
                onOpenWorkflow={handleOpenWorkflow}
                onFilterApply={handleFilterApply}
                onFilterClear={handleFilterClear}
                onSortChange={handleSortChange}
                onPageChange={handlePageChange}
                onPageSizeChange={handlePageSizeChange}
              />
            </>
          )}
        </div>
      </PageScaffold>
    </div>
    <OutputInvoiceCollectionDetailDrawer
      open={Boolean(query.detailTarget)}
      target={query.detailTarget}
      loadDetail={loadDetail}
      onClose={handleCloseDetail}
    />
    <CollectionStatusRulesDrawer
      open={query.activeWorkflow?.kind === "statusRules"}
      loadRules={fetchOutputInvoiceCollectionStatusRules}
      onClose={handleCloseWorkflow}
    />
    <ReceiptHistoryDrawer
      open={query.activeWorkflow?.kind === "receiptHistory"}
      invoiceId={receiptHistoryInvoiceId}
      loadHistory={fetchOutputInvoiceReceiptHistory}
      onVoidReceipt={(receiptId, reason) => voidOutputInvoiceReceipt(receiptId, reason).then(() => undefined)}
      onReissueReceipt={(receiptId, reason) => reissueOutputInvoiceReceipt(receiptId, reason).then(() => undefined)}
      onChanged={handleLifecycleChanged}
      onClose={handleCloseWorkflow}
    />
    <ReceiptPreviewDrawer
      open={query.activeWorkflow?.kind === "receiptPreview"}
      row={receiptPreviewRow}
      loadPreview={previewOutputInvoiceReceipt}
      createReceipt={(rowId, bankTransactionId) => createOutputInvoiceReceipt(rowId, {
        bankTransactionId,
        idempotencyKey: `receipt:${rowId}:${bankTransactionId}`,
      }).then(() => undefined)}
      onChanged={handleLifecycleChanged}
      onClose={handleCloseWorkflow}
    />
    <CollectionStatusReminderDrawer
      open={query.activeWorkflow?.kind === "collectionStatus"}
      row={collectionStatusRow}
      statusOptions={manualStatusOptions}
      onSaveStatus={(rowId, payload) => updateOutputInvoiceCollectionStatus(rowId, payload).then(() => handleLifecycleChanged())}
      onSaveReminder={(rowId, payload) => updateOutputInvoiceCollectionReminder(rowId, payload).then(() => handleLifecycleChanged())}
      onClearStatus={(rowId, expectedVersion) => updateOutputInvoiceCollectionStatus(rowId, {
        statusCode: "",
        expectedVersion,
      }).then(() => handleLifecycleChanged())}
      onCancelReminder={(rowId, reminderId) => cancelOutputInvoiceCollectionReminder(rowId, reminderId).then(() => handleLifecycleChanged())}
      onClose={handleCloseWorkflow}
    />
    <RedInvoiceRelationDrawer
      open={query.activeWorkflow?.kind === "redRelation"}
      row={redRelationRow}
      candidateRows={rows}
      onConfirm={(rowId, payload) => confirmOutputInvoiceRedRelation(rowId, payload).then(() => handleLifecycleChanged())}
      onRevoke={(relationId) => revokeOutputInvoiceRedRelation(relationId).then(() => handleLifecycleChanged())}
      onClose={handleCloseWorkflow}
    />
    <ReceiptSettingsDrawer
      open={query.activeWorkflow?.kind === "receiptSettings"}
      loadSettings={() => fetchOutputInvoiceReceiptSettings()}
      onSave={(payload) => updateOutputInvoiceReceiptSettings(payload).then(() => undefined)}
      onClose={handleCloseWorkflow}
    />
    </>
  );
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "0.00";
  }
  return parsed.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="output-invoice-collections-summary-tile">
      <span className="output-invoice-collections-summary-tile__label">{label}</span>
      <strong className="output-invoice-collections-summary-tile__value">{value}</strong>
    </div>
  );
}
