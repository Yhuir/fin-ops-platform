import { Button } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import PageToolbar from "../components/common/PageToolbar";
import QuerySearch from "../components/common/QuerySearch";
import OutputInvoiceCollectionDetailDrawer from "../components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer";
import OutputInvoiceCollectionExportDrawer from "../components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer";
import OutputInvoiceCollectionsTable from "../components/outputInvoiceCollections/OutputInvoiceCollectionsTable";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  downloadOutputInvoiceCollectionExport,
  fetchOutputInvoiceCollectionBankTransactionDetail,
  fetchOutputInvoiceCollectionExportPreview,
  fetchOutputInvoiceCollectionInvoiceDetail,
  fetchOutputInvoiceCollectionRowRelationDetail,
  fetchOutputInvoiceCollectionRows,
  nextSortDirection,
} from "../features/outputInvoiceCollections/api";
import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionQuery,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionStatistics,
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

function isFilterArray(value: unknown): value is OutputInvoiceCollectionFilter[] {
  return Array.isArray(value) && value.every((item) => (
    item
    && typeof item === "object"
    && typeof (item as OutputInvoiceCollectionFilter).field === "string"
    && typeof (item as OutputInvoiceCollectionFilter).operator === "string"
  ));
}

function isDetailTarget(value: unknown): value is OutputInvoiceCollectionDetailTarget | null {
  if (value === null) return true;
  if (!value || typeof value !== "object") return false;
  const target = value as OutputInvoiceCollectionDetailTarget;
  return typeof target.id === "string" && ["invoice", "bank", "relationList"].includes(target.kind);
}

function isWorkflow(value: unknown): value is OutputInvoiceCollectionWorkflow {
  return value === null || (
    Boolean(value)
    && typeof value === "object"
    && (value as NonNullable<OutputInvoiceCollectionWorkflow>).kind === "export"
  );
}

function validateQuery(value: unknown): value is OutputInvoiceCollectionQuery {
  if (!value || typeof value !== "object") return false;
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
  if (!validateQuery(raw)) return initialQuery;
  return {
    ...initialQuery,
    ...raw,
    page: Math.max(1, raw.page),
    pageSize: [20, 50, 100].includes(raw.pageSize) ? raw.pageSize : initialQuery.pageSize,
  };
}

function optionsByField(fields: Array<OutputInvoiceCollectionFilterFieldConfig & { options?: OutputInvoiceCollectionFilterOption[] }>) {
  return fields.reduce<Record<string, OutputInvoiceCollectionFilterOption[]>>((result, field) => {
    result[field.field] = field.options ?? [];
    return result;
  }, {});
}

function configsFromOptions(fields: Array<OutputInvoiceCollectionFilterFieldConfig & { options?: OutputInvoiceCollectionFilterOption[] }>) {
  return fields.map(({ options: _options, ...field }) => field);
}

function normalizeFilter(filter: {
  field: string;
  operator: string;
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
}): OutputInvoiceCollectionFilter | null {
  if (filter.operator === "in") {
    const values = Array.isArray(filter.values) ? filter.values.filter(Boolean) : [];
    return values.length ? { field: filter.field, operator: "in", values } : null;
  }
  if (filter.operator === "equals" || filter.operator === "contains") {
    const value = typeof filter.value === "string" ? filter.value : "";
    return value ? { field: filter.field, operator: filter.operator, value } : null;
  }
  if (filter.operator === "between") {
    return { field: filter.field, operator: "between", value: filter.value ?? null };
  }
  return null;
}

export default function OutputInvoiceCollectionsPage() {
  const { active, activationGeneration } = useOptionalPageActivation("output-invoice-collections");
  const { canAdminAccess } = useSessionPermissions();
  const querySession = usePageSessionState({
    pageKey: "output-invoice-collections",
    stateKey: "query",
    version: 2,
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
  const [statistics, setStatistics] = useState<OutputInvoiceCollectionStatistics | null>(null);
  const [filterConfigs, setFilterConfigs] = useState<OutputInvoiceCollectionFilterFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OutputInvoiceCollectionFilterOption[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(() => new Set());
  const [keywordDraft, setKeywordDraft] = useState(query.keyword);
  const requestIdRef = useRef(0);
  const hasLoadedRef = useRef(false);

  useEffect(() => setKeywordDraft(query.keyword), [query.keyword]);

  const rowsRequest = useMemo(() => ({
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
    query.page,
    query.pageSize,
    query.keyword,
    query.invoiceDateFrom,
    query.invoiceDateTo,
    query.month,
    query.filters,
    query.sortField,
    query.sortDirection,
  ]);

  const loadRows = useCallback((mode: "reset" | "refresh", signal?: AbortSignal) => {
    const requestId = ++requestIdRef.current;
    mode === "reset" ? setLoading(true) : setRefreshing(true);
    setError(null);
    fetchOutputInvoiceCollectionRows({ ...rowsRequest, signal })
      .then((payload) => {
        if (requestId !== requestIdRef.current) return;
        hasLoadedRef.current = true;
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setStatistics(payload.statistics ?? null);
        setFilterConfigs(payload.filterConfig.length ? payload.filterConfig : configsFromOptions(payload.filterOptions));
        setFilterOptions(optionsByField(payload.filterOptions));
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== requestIdRef.current) return;
        if (mode === "reset") {
          setRows([]);
          setTotal(0);
          setStatistics(null);
          setFilterConfigs([]);
          setFilterOptions({});
        }
        setError(caught instanceof Error ? caught.message : "销项发票收款情况加载失败，请稍后重试。");
      })
      .finally(() => {
        if (requestId !== requestIdRef.current) return;
        setLoading(false);
        setRefreshing(false);
      });
  }, [rowsRequest]);

  useEffect(() => {
    if (!active) return undefined;
    const controller = new AbortController();
    loadRows(hasLoadedRef.current ? "refresh" : "reset", controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadRows]);

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
    const normalized = normalizeFilter(filter);
    setQuery((current) => ({
      ...current,
      page: 1,
      filters: [
        ...current.filters.filter((item) => item.field !== filter.field),
        ...(normalized ? [normalized] : []),
      ],
    }));
  }, [setQuery]);

  const toggleExpandedCell = useCallback((rowId: string, cellId: string) => {
    const key = `${rowId}:${cellId}`;
    setExpandedCells((current) => {
      const next = new Set(current);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  const loadDetail = useCallback((target: OutputInvoiceCollectionDetailTarget) => {
    if (target.kind === "invoice") return fetchOutputInvoiceCollectionInvoiceDetail(target.id);
    if (target.kind === "bank") return fetchOutputInvoiceCollectionBankTransactionDetail(target.id);
    return fetchOutputInvoiceCollectionRowRelationDetail(target);
  }, []);

  const exportRequest = rowsRequest;

  const titleAccessory = useMemo(() => (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="销项发票收款情况数据统计"
        coreItems={[
          { label: "销项发票", value: statistics?.invoiceCount, unit: "张" },
          { label: "已关联收入流水", value: statistics?.linkedIncomeBankInvoiceCount, unit: "张" },
          { label: "已收款", value: statistics?.collectedInvoiceCount, unit: "张", tone: "success" },
        ]}
        detailItems={[
          { label: "未关联流水", value: statistics?.unlinkedBankInvoiceCount, unit: "张", tone: "warning" },
          { label: "未收款", value: statistics?.uncollectedInvoiceCount, unit: "张", tone: "warning" },
          { label: "红字发票", value: statistics?.redInvoiceCount, unit: "张" },
        ]}
        loading={loading}
      />
      {canAdminAccess ? (
        <PageBusinessAuditIcon ariaLabel="Audit 销项发票收款情况" label="销项发票收款情况" pageKey="output-invoice-collections" />
      ) : null}
    </div>
  ), [canAdminAccess, loading, statistics]);

  const actions = (
    <div className="output-invoice-collections-actions">
      <Button isDisabled={loading || refreshing} onPress={() => loadRows("refresh")} size="sm" variant="secondary">
        {refreshing ? "刷新中" : "刷新"}
      </Button>
      <Button
        isDisabled={Boolean(error)}
        onPress={() => setQuery((current) => ({ ...current, activeWorkflow: { kind: "export" } }))}
        size="sm"
        variant="secondary"
      >
        筛选内容导出
      </Button>
    </div>
  );

  return (
    <>
      <div className="output-invoice-collections-page" data-testid="output-invoice-collections-page">
        <PageScaffold
          actions={actions}
          className="invoice-count-page-scaffold"
          title="销项发票收款情况"
          titleAccessory={titleAccessory}
        >
          <div className="output-invoice-collections-content">
            <PageToolbar className="output-invoice-collections-query">
              <div className="output-invoice-collections-query__grid">
                <BusinessPeriodPicker
                  allowedModes={["month"]}
                  ariaLabel="销项发票月份"
                  onChange={(selection) => setQuery((current) => ({
                    ...current,
                    month: selection.mode === "all" ? "" : selection.month,
                    page: 1,
                  }))}
                  selection={{
                    mode: query.month ? "month" : "all",
                    year: (query.month || DEFAULT_MONTH).slice(0, 4),
                    month: query.month || DEFAULT_MONTH,
                  }}
                  years={nearbyBusinessYears(query.month || DEFAULT_MONTH)}
                />
                <QuerySearch
                  ariaLabel="搜索销项发票收款情况"
                  className="output-invoice-collections-search-cluster"
                  onChange={setKeywordDraft}
                  onClear={() => {
                    setKeywordDraft("");
                    setQuery((current) => ({ ...current, keyword: "", page: 1 }));
                  }}
                  onSubmit={() => setQuery((current) => ({ ...current, keyword: keywordDraft.trim(), page: 1 }))}
                  placeholder="发票号、购方、业务或流水"
                  value={keywordDraft}
                />
              </div>
            </PageToolbar>
            {error ? <div className="output-invoice-collections-alert" role="alert">{error}</div> : null}
            {loading ? (
              <div aria-label="销项发票收款情况加载中" className="output-invoice-collections-loading">
                <span className="output-invoice-collections-loading__bar" />
                <span className="output-invoice-collections-loading__panel" />
                <span className="output-invoice-collections-loading__panel" />
              </div>
            ) : (
              <OutputInvoiceCollectionsTable
                emptyStateMessage={error ? "加载失败，请刷新重试。" : undefined}
                expandedCells={expandedCells}
                filterConfigs={filterConfigs}
                filterOptions={filterOptions}
                filters={query.filters}
                onFilterApply={handleFilterApply}
                onFilterClear={(field) => setQuery((current) => ({
                  ...current,
                  page: 1,
                  filters: current.filters.filter((filter) => filter.field !== field),
                }))}
                onOpenDetail={(target) => setQuery((current) => ({ ...current, detailTarget: target }))}
                onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
                onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
                onSortChange={handleSortChange}
                onToggleCellExpand={toggleExpandedCell}
                page={query.page}
                pageSize={query.pageSize}
                rows={rows}
                refreshing={refreshing}
                sortDirection={query.sortDirection}
                sortField={query.sortField}
                total={total}
              />
            )}
          </div>
        </PageScaffold>
      </div>
      <OutputInvoiceCollectionDetailDrawer
        loadDetail={loadDetail}
        onClose={() => setQuery((current) => ({ ...current, detailTarget: null }))}
        open={Boolean(query.detailTarget)}
        target={query.detailTarget}
      />
      <OutputInvoiceCollectionExportDrawer
        downloadExport={() => downloadOutputInvoiceCollectionExport(exportRequest)}
        loadPreview={() => fetchOutputInvoiceCollectionExportPreview(exportRequest)}
        onClose={() => setQuery((current) => ({ ...current, activeWorkflow: null }))}
        open={query.activeWorkflow?.kind === "export"}
      />
    </>
  );
}
