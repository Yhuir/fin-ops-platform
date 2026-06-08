import { Download } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import InputInvoiceUsageExportDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageExportDrawer";
import InputInvoiceUsageTable from "../components/inputInvoiceUsage/InputInvoiceUsageTable";
import OaReverseWorkspaceDrawer, { type OaReversePreviewRequest } from "../components/inputInvoiceUsage/OaReverseWorkspaceDrawer";
import PaymentStatusRulesDrawer from "../components/inputInvoiceUsage/PaymentStatusRulesDrawer";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import {
  downloadInputInvoiceUsageExport,
  fetchInputInvoiceUsageBankTransactionDetail,
  fetchInputInvoiceUsageExportPreview,
  fetchInputInvoiceUsageFilterOptions,
  fetchInputInvoiceUsageInvoiceDetail,
  fetchInputInvoiceUsageOaDetail,
  fetchInputInvoiceUsagePaymentStatusRules,
  fetchInputInvoiceUsageRows,
  fetchInputInvoiceUsageRowRelationDetail,
  createInputInvoiceUsageOaReverseBatch,
  createInputInvoiceUsageOaReverseDraft,
  manualInputInvoiceUsageOaReverseStatus,
  previewInputInvoiceUsageOaReverse,
  refreshInputInvoiceUsageOaReverseStatus,
  revokeInputInvoiceUsageOaReverseDraft,
  saveInputInvoiceUsagePaymentStatusRules,
  nextSortDirection,
} from "../features/inputInvoiceUsage/api";
import type {
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageFilterFieldConfig,
  InputInvoiceUsageFilterOption,
  InputInvoiceUsageQuery,
  InputInvoiceUsageRow,
  InputInvoiceUsageSortDirection,
} from "../features/inputInvoiceUsage/types";

const initialQuery: InputInvoiceUsageQuery = {
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

function isFilterArray(value: unknown): value is InputInvoiceUsageFilter[] {
  return Array.isArray(value) && value.every((item) => (
    item
    && typeof item === "object"
    && typeof (item as InputInvoiceUsageFilter).field === "string"
    && typeof (item as InputInvoiceUsageFilter).operator === "string"
  ));
}

function isDetailTarget(value: unknown): value is InputInvoiceUsageDetailTarget | null {
  if (value === null) {
    return true;
  }
  if (!value || typeof value !== "object") {
    return false;
  }
  const target = value as InputInvoiceUsageDetailTarget;
  return typeof target.id === "string"
    && ["invoice", "bank", "oa", "relationList"].includes(target.kind);
}

function isWorkflow(value: unknown): value is InputInvoiceUsageQuery["activeWorkflow"] {
  return value === null || value === "oaReverse" || value === "paymentRules" || value === "export";
}

function validateQuery(value: unknown): value is InputInvoiceUsageQuery {
  if (!value || typeof value !== "object") {
    return false;
  }
  const query = value as InputInvoiceUsageQuery;
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

function restoreQuery(raw: unknown): InputInvoiceUsageQuery {
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

function filterOptionsByField(fields: Array<InputInvoiceUsageFilterFieldConfig & { options?: InputInvoiceUsageFilterOption[] }>) {
  return fields.reduce<Record<string, InputInvoiceUsageFilterOption[]>>((accumulator, field) => {
    accumulator[field.field] = field.options ?? [];
    return accumulator;
  }, {});
}

function filterConfigsFromOptions(fields: Array<InputInvoiceUsageFilterFieldConfig & { options?: InputInvoiceUsageFilterOption[] }>) {
  return fields.map(({ options: _options, ...field }) => field);
}

function normalizeFilterValue(filter: {
  field: string;
  operator: string;
  value?: string | null;
  values?: string[];
}): InputInvoiceUsageFilter | null {
  if (filter.operator === "in") {
    const values = Array.from(new Set((filter.values ?? []).map((value) => String(value).trim()).filter(Boolean)));
    return values.length > 0 ? { field: filter.field, operator: "in", values } : null;
  }
  if (filter.operator === "equals") {
    const value = String(filter.value ?? "").trim();
    return value ? { field: filter.field, operator: "equals", value } : null;
  }
  return {
    field: filter.field,
    operator: filter.operator as InputInvoiceUsageFilter["operator"],
    value: filter.value ?? null,
    values: filter.values,
  };
}

export default function InputInvoiceUsagePage() {
  const { active } = useOptionalPageActivation("input-invoice-usage");
  const querySession = usePageSessionState({
    pageKey: "input-invoice-usage",
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
  const [rows, setRows] = useState<InputInvoiceUsageRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [readModelStatus, setReadModelStatus] = useState("");
  const [filterConfigs, setFilterConfigs] = useState<InputInvoiceUsageFilterFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, InputInvoiceUsageFilterOption[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(() => new Set());
  const [keywordDraft, setKeywordDraft] = useState(query.keyword);
  const requestIdRef = useRef(0);
  const hasLoadedRef = useRef(false);

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
      fetchInputInvoiceUsageRows(request),
      fetchInputInvoiceUsageFilterOptions({
        keyword: query.keyword,
        invoiceDateFrom: query.invoiceDateFrom,
        invoiceDateTo: query.invoiceDateTo,
        month: query.month,
        filters: query.filters,
        signal,
      }),
    ])
      .then(([payload, optionsPayload]) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setFilterConfigs((payload.filterConfig?.length ?? 0) > 0 ? payload.filterConfig : filterConfigsFromOptions(optionsPayload.fields ?? []));
        setFilterOptions(filterOptionsByField(optionsPayload.fields ?? []));
        setReadModelStatus(payload.readModelStatus || optionsPayload.readModelStatus || "");
        hasLoadedRef.current = true;
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== requestIdRef.current) {
          return;
        }
        setRows([]);
        setTotal(0);
        setReadModelStatus("");
        setError(caught instanceof Error ? caught.message : "进项发票使用情况加载失败，请稍后重试。");
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
    loadRows(hasLoadedRef.current ? "refresh" : "reset", controller.signal);
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

  const handlePageChange = useCallback((page: number) => {
    setQuery((current) => ({ ...current, page }));
  }, [setQuery]);

  const handlePageSizeChange = useCallback((pageSize: number) => {
    setQuery((current) => ({ ...current, page: 1, pageSize }));
  }, [setQuery]);

  const handleSortChange = useCallback((field: string, direction?: InputInvoiceUsageSortDirection) => {
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
    value?: string | null;
    values?: string[];
  }) => {
    const normalized = normalizeFilterValue(filter);
    setQuery((current) => {
      const filters = current.filters.filter((item) => item.field !== filter.field);
      return { ...current, page: 1, filters: normalized ? [...filters, normalized] : filters };
    });
  }, [setQuery]);

  const handleFilterClear = useCallback((field: string) => {
    setQuery((current) => ({ ...current, page: 1, filters: current.filters.filter((filter) => filter.field !== field) }));
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

  const handleOpenDetail = useCallback((target: InputInvoiceUsageDetailTarget) => {
    setQuery((current) => ({ ...current, detailTarget: target }));
  }, [setQuery]);

  const handleCloseDetail = useCallback(() => {
    setQuery((current) => ({ ...current, detailTarget: null }));
  }, [setQuery]);

  const handleCloseWorkflow = useCallback(() => {
    setQuery((current) => ({ ...current, activeWorkflow: null }));
  }, [setQuery]);

  const loadDetail = useCallback((target: InputInvoiceUsageDetailTarget) => {
    if (target.kind === "invoice") {
      return fetchInputInvoiceUsageInvoiceDetail(target.id);
    }
    if (target.kind === "bank") {
      return fetchInputInvoiceUsageBankTransactionDetail(target.id);
    }
    if (target.kind === "oa") {
      return fetchInputInvoiceUsageOaDetail(target.id);
    }
    return fetchInputInvoiceUsageRowRelationDetail(target);
  }, []);

  const loadOaReversePreview = useCallback((request: OaReversePreviewRequest) => (
    previewInputInvoiceUsageOaReverse({
      source: request.selectedInvoiceIds.length > 0 ? "explicitSelection" : "currentFilters",
      filters: isFilterArray(request.sourceFilters) ? request.sourceFilters : [],
      selectedInvoiceIds: request.selectedInvoiceIds,
      targetApplicantCode: request.targetApplicantCode || undefined,
    })
  ), []);

  const exportRequest = useMemo(() => ({
    page: query.page,
    pageSize: query.pageSize,
    keyword: query.keyword,
    invoiceDateFrom: query.invoiceDateFrom,
    invoiceDateTo: query.invoiceDateTo,
    month: query.month,
    filters: query.filters,
    sortField: query.sortField,
    sortDirection: query.sortDirection,
  }), [
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

  const loadExportPreview = useCallback(() => fetchInputInvoiceUsageExportPreview(exportRequest), [exportRequest]);
  const downloadExport = useCallback(() => downloadInputInvoiceUsageExport(exportRequest), [exportRequest]);

  const actions = useMemo(() => (
    <PageToolbar className="input-invoice-usage-actions">
      <button
        className="input-invoice-usage-button"
        onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "paymentRules" }))}
        type="button"
      >
        发票与支付状态规则设置
      </button>
      <button
        className="input-invoice-usage-button"
        onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "export" }))}
        type="button"
      >
        <Download aria-hidden="true" size={16} />
        筛选内容导出
      </button>
    </PageToolbar>
  ), [setQuery]);
  const isEmpty = !loading && !error && rows.length === 0;

  return (
    <>
      <div className="input-invoice-usage-page" data-testid="input-invoice-usage-page">
        <PageScaffold
          title="进项发票使用情况"
          actions={actions}
        >
          <div className="input-invoice-usage-content">
            <PageToolbar
              className="input-invoice-usage-query-toolbar"
              right={(
                <div className="input-invoice-usage-query-actions">
                  <button
                    className="input-invoice-usage-button input-invoice-usage-button--accent"
                    onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "oaReverse" }))}
                    type="button"
                  >
                    以发票反提 OA
                  </button>
                  <label className="input-invoice-usage-search">
                    <input
                      aria-label="进项发票使用情况搜索"
                      placeholder="搜索发票、销方、OA、流水"
                      value={keywordDraft}
                      onChange={(event) => setKeywordDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          handleKeywordSubmit();
                        }
                      }}
                      type="text"
                    />
                  </label>
                  <button className="input-invoice-usage-button" onClick={handleKeywordSubmit} type="button">
                    查询
                  </button>
                </div>
              )}
            />
            {error ? <StatePanel tone="error" compact>{error}</StatePanel> : null}
            {loading ? (
              <div aria-label="进项发票使用情况加载中" className="input-invoice-usage-loading" role="status">
                <span className="input-invoice-usage-loading__bar input-invoice-usage-loading__bar--sm" />
                <span className="input-invoice-usage-loading__bar" />
                <span className="input-invoice-usage-loading__bar" />
              </div>
            ) : (
              <>
                {isEmpty ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
                <InputInvoiceUsageTable
                  rows={rows}
                  page={query.page}
                  pageSize={query.pageSize}
                  total={total}
                  filterConfigs={filterConfigs}
                  filterOptions={filterOptions}
                  filters={query.filters}
                  sortField={query.sortField}
                  sortDirection={query.sortDirection}
                  expandedCells={expandedCells}
                  onToggleCellExpand={handleToggleCellExpand}
                  onOpenDetail={handleOpenDetail}
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
      <InputInvoiceUsageDetailDrawer
        open={Boolean(query.detailTarget)}
        target={query.detailTarget}
        loadDetail={loadDetail}
        onClose={handleCloseDetail}
      />
      <OaReverseWorkspaceDrawer
        open={query.activeWorkflow === "oaReverse"}
        sourceFilters={query.filters}
        selectedInvoiceIds={[]}
        loadPreview={loadOaReversePreview}
        createBatch={createInputInvoiceUsageOaReverseBatch}
        createDraft={createInputInvoiceUsageOaReverseDraft}
        refreshStatus={refreshInputInvoiceUsageOaReverseStatus}
        revokeDraft={revokeInputInvoiceUsageOaReverseDraft}
        manualStatus={manualInputInvoiceUsageOaReverseStatus}
        onClose={handleCloseWorkflow}
      />
      <PaymentStatusRulesDrawer
        open={query.activeWorkflow === "paymentRules"}
        loadRules={fetchInputInvoiceUsagePaymentStatusRules}
        saveRules={saveInputInvoiceUsagePaymentStatusRules}
        onClose={handleCloseWorkflow}
      />
      <InputInvoiceUsageExportDrawer
        open={query.activeWorkflow === "export"}
        loadPreview={loadExportPreview}
        downloadExport={downloadExport}
        onClose={handleCloseWorkflow}
      />
    </>
  );
}
