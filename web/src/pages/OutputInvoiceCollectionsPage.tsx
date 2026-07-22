import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import MonthPicker from "../components/MonthPicker";
import CollectionStatusReminderDrawer from "../components/outputInvoiceCollections/CollectionStatusReminderDrawer";
import CollectionStatusRulesDrawer from "../components/outputInvoiceCollections/CollectionStatusRulesDrawer";
import OutputInvoiceCollectionDetailDrawer from "../components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer";
import OutputInvoiceCollectionExportDrawer from "../components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer";
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
  downloadOutputInvoiceCollectionExport,
  fetchOutputInvoiceCollectionBankTransactionDetail,
  fetchOutputInvoiceCollectionExportPreview,
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
  OutputInvoiceCollectionMutationResponse,
  OutputInvoiceCollectionQuery,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionStatusRulesResponse,
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
const READ_MODEL_REFRESH_RETRY_MS = 250;
const READ_MODEL_REFRESHING_STATUSES = new Set(["refreshing", "stale", "missing", "schema_mismatch"]);
const READ_MODEL_NON_FRESH_STATUSES = new Set([...READ_MODEL_REFRESHING_STATUSES, "failed", "unavailable"]);

function normalizeReadModelStatus(value: string | undefined) {
  return (value ?? "").trim().toLowerCase();
}

function combineReadModelStatus(...statuses: Array<string | undefined>) {
  const normalized = statuses.map(normalizeReadModelStatus).filter(Boolean);
  if (normalized.some((status) => READ_MODEL_REFRESHING_STATUSES.has(status))) {
    return "refreshing";
  }
  const nonFresh = normalized.find((status) => READ_MODEL_NON_FRESH_STATUSES.has(status));
  return nonFresh ?? normalized[0] ?? "";
}

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
  if (workflow.kind === "export") {
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

function workflowRequiresMutation(workflow: NonNullable<OutputInvoiceCollectionWorkflow>) {
  return workflow.kind === "collectionStatus"
    || workflow.kind === "redRelation"
    || workflow.kind === "receiptPreview";
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
  const { canAdminAccess, canMutateData } = useSessionPermissions();
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
  const [statistics, setStatistics] = useState<OutputInvoiceCollectionStatistics | null>(null);
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
    ])
      .then(([payload, optionsPayload]) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        const nextReadModelStatus = combineReadModelStatus(payload.readModelStatus, optionsPayload.readModelStatus);
        setStatistics(nextReadModelStatus === "fresh" ? payload.statistics ?? null : null);
        setFilterConfigs(payload.filterConfig.length > 0 ? payload.filterConfig : filterConfigsFromOptions(optionsPayload.fields));
        setFilterOptions(filterOptionsByField(optionsPayload.fields));
        setReadModelStatus(nextReadModelStatus);
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== requestIdRef.current) {
          return;
        }
        setRows([]);
        setTotal(0);
        setStatistics(null);
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
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [active, loadRows]);

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

  const ensureStatusRulesLoaded = useCallback(async () => {
    if (statusRulesPayload) {
      return;
    }
    try {
      setStatusRulesPayload(await fetchOutputInvoiceCollectionStatusRules());
    } catch {
      // Status/reminder can still open with the row's current status as a local fallback.
    }
  }, [statusRulesPayload]);

  const handleOpenWorkflow = useCallback(async (target: NonNullable<OutputInvoiceCollectionWorkflow>) => {
    if (target.kind === "receiptSettings" && !canAdminAccess) {
      return;
    }
    if (workflowRequiresMutation(target) && !canMutateData) {
      return;
    }
    if (target.kind === "collectionStatus") {
      await ensureStatusRulesLoaded();
    }
    setQuery((current) => ({ ...current, activeWorkflow: target }));
  }, [canAdminAccess, canMutateData, ensureStatusRulesLoaded, setQuery]);

  const handleCloseWorkflow = useCallback(() => {
    setQuery((current) => ({ ...current, activeWorkflow: null }));
  }, [setQuery]);

  useEffect(() => {
    const workflow = query.activeWorkflow;
    if (!workflow) {
      return;
    }
    if ((workflow.kind === "receiptSettings" && !canAdminAccess) || (workflowRequiresMutation(workflow) && !canMutateData)) {
      setQuery((current) => (
        current.activeWorkflow === workflow ? { ...current, activeWorkflow: null } : current
      ));
    }
  }, [canAdminAccess, canMutateData, query.activeWorkflow, setQuery]);

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
  const collectionStatusOptions = useMemo(() => {
    if (manualStatusOptions.length > 0) {
      return manualStatusOptions;
    }
    const code = collectionStatusRow?.collectionStatus.manualOverride?.statusCode || collectionStatusRow?.collectionStatus.code || "";
    const label = collectionStatusRow?.collectionStatus.label || code;
    return code ? [{ code, label }] : [];
  }, [collectionStatusRow, manualStatusOptions]);

  const handleLifecycleChanged = useCallback(async (_result?: OutputInvoiceCollectionMutationResponse | null) => {
    loadRows("refresh");
  }, [loadRows]);

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
  const isReadModelNonFresh = READ_MODEL_NON_FRESH_STATUSES.has(readModelStatus);
  const isReadModelRefreshing = READ_MODEL_REFRESHING_STATUSES.has(readModelStatus);
  const exportDisabled = Boolean(error) || isReadModelNonFresh;
  const loadExportPreview = useCallback(() => fetchOutputInvoiceCollectionExportPreview(exportRequest), [exportRequest]);
  const downloadExport = useCallback(() => downloadOutputInvoiceCollectionExport(exportRequest), [exportRequest]);

  const actions = useMemo(() => (
    <div className="output-invoice-collections-actions">
      <button
        className="output-invoice-collections-button"
        disabled={loading || refreshing}
        onClick={() => loadRows("refresh")}
        type="button"
      >
        刷新
      </button>
      <button
        className="output-invoice-collections-button"
        disabled={exportDisabled}
        onClick={() => handleOpenWorkflow({ kind: "export" })}
        type="button"
      >
        筛选内容导出
      </button>
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
    </div>
  ), [canAdminAccess, exportDisabled, handleOpenWorkflow, loadRows, loading, refreshing]);
  const visibleStatistics = readModelStatus === "fresh" ? statistics : null;
  const titleAccessory = useMemo(() => (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="销项发票收款情况数据统计"
        loading={loading && !readModelStatus}
        coreItems={[
          { label: "销项发票", value: visibleStatistics?.invoiceCount, unit: "张" },
          { label: "已关联收入流水的销项票", value: visibleStatistics?.linkedIncomeBankInvoiceCount, unit: "张" },
          { label: "已收款销项票", value: visibleStatistics?.collectedInvoiceCount, unit: "张", tone: "success" },
        ]}
        detailItems={[
          { label: "已关联 OA 的销项票", value: visibleStatistics?.linkedOaInvoiceCount, unit: "张" },
          { label: "未关联 OA", value: visibleStatistics?.unlinkedOaInvoiceCount, unit: "张", tone: "warning" },
          { label: "未关联流水", value: visibleStatistics?.unlinkedBankInvoiceCount, unit: "张", tone: "warning" },
          { label: "未收款销项票", value: visibleStatistics?.uncollectedInvoiceCount, unit: "张", tone: "warning" },
          { label: "红字发票", value: visibleStatistics?.redInvoiceCount, unit: "张" },
          { label: "已开收据", value: visibleStatistics?.issuedReceiptCount, unit: "张" },
        ]}
      />
      {canAdminAccess ? (
        <PageBusinessAuditIcon
          ariaLabel="Audit 销项发票收款情况"
          label="销项发票收款情况"
          pageKey="output-invoice-collections"
          readModelStatus={readModelStatus}
        />
      ) : null}
    </div>
  ), [canAdminAccess, loading, readModelStatus, visibleStatistics]);
  const isEmpty = !loading && !error && !isReadModelNonFresh && rows.length === 0;

  return (
    <>
    <div className="output-invoice-collections-page" data-testid="output-invoice-collections-page">
      <PageScaffold
        className="invoice-count-page-scaffold"
        title="销项发票收款情况"
        titleAccessory={titleAccessory}
        actions={actions}
      >
        <div className="output-invoice-collections-content">
          <PageToolbar className="output-invoice-collections-query">
            <div className="output-invoice-collections-query__grid">
              <div className="output-invoice-collections-field">
                <span>月份</span>
                <MonthPicker
                  allOptionLabel="全部发票"
                  ariaLabel="销项发票月份"
                  caption={null}
                  value={query.month}
                  onChange={(month) => setQuery((current) => ({ ...current, page: 1, month }))}
                />
              </div>
              <div className="output-invoice-collections-search-cluster">
                <input
                  aria-label="搜索销项发票收款情况"
                  className="output-invoice-collections-search-input"
                  type="search"
                  value={keywordDraft}
                  onChange={(event) => setKeywordDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      handleKeywordSubmit();
                    }
                  }}
                />
                <button
                  className="output-invoice-collections-button output-invoice-collections-button--primary"
                  onClick={handleKeywordSubmit}
                  type="button"
                >
                  查询
                </button>
              </div>
            </div>
          </PageToolbar>
          {error ? <div className="output-invoice-collections-alert" role="alert">{error}</div> : null}
          {loading ? (
            <div className="output-invoice-collections-loading" aria-label="销项发票收款情况加载中">
              <span className="output-invoice-collections-loading__bar" />
              <span className="output-invoice-collections-loading__panel" />
              <span className="output-invoice-collections-loading__panel" />
            </div>
          ) : (
            <>
              {isReadModelNonFresh ? (
                <StatePanel tone={isReadModelRefreshing ? "loading" : "warning"} compact title="销项发票收款情况数据正在刷新">
                  当前数据仍在刷新或等待后台任务完成，请稍后重试。
                </StatePanel>
              ) : null}
              {isEmpty ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
              {!isReadModelNonFresh ? (
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
                  canMutateData={canMutateData}
                  expandedCells={expandedCells}
                  onToggleCellExpand={handleToggleCellExpand}
                  onOpenDetail={handleOpenDetail}
                  onOpenWorkflow={handleOpenWorkflow}
                  onFilterApply={handleFilterApply}
                  onFilterClear={handleFilterClear}
                  onSortChange={handleSortChange}
                  onPageChange={handlePageChange}
                  onPageSizeChange={handlePageSizeChange}
                  emptyStateMessage={error ? "销项发票收款情况加载失败，请点击刷新重试。" : undefined}
                />
              ) : null}
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
    <OutputInvoiceCollectionExportDrawer
      open={query.activeWorkflow?.kind === "export"}
      loadPreview={loadExportPreview}
      downloadExport={downloadExport}
      onClose={handleCloseWorkflow}
    />
    <ReceiptHistoryDrawer
      open={query.activeWorkflow?.kind === "receiptHistory"}
      invoiceId={receiptHistoryInvoiceId}
      canMutateData={canMutateData}
      loadHistory={fetchOutputInvoiceReceiptHistory}
      onVoidReceipt={(receiptId, reason) => voidOutputInvoiceReceipt(receiptId, reason)}
      onReissueReceipt={(receiptId, reason) => reissueOutputInvoiceReceipt(receiptId, reason)}
      onChanged={handleLifecycleChanged}
      onClose={handleCloseWorkflow}
    />
    <ReceiptPreviewDrawer
      open={query.activeWorkflow?.kind === "receiptPreview"}
      row={receiptPreviewRow}
      loadPreview={previewOutputInvoiceReceipt}
      createReceipt={canMutateData
        ? (rowId, bankTransactionId) => createOutputInvoiceReceipt(rowId, {
          bankTransactionId,
          idempotencyKey: `receipt:${rowId}:${bankTransactionId}`,
        })
        : undefined}
      onChanged={handleLifecycleChanged}
      onClose={handleCloseWorkflow}
    />
    <CollectionStatusReminderDrawer
      open={query.activeWorkflow?.kind === "collectionStatus"}
      row={collectionStatusRow}
      statusOptions={collectionStatusOptions}
      onSaveStatus={(rowId, payload) => updateOutputInvoiceCollectionStatus(rowId, payload)}
      onSaveReminder={(rowId, payload) => updateOutputInvoiceCollectionReminder(rowId, payload)}
      onClearStatus={(rowId, expectedVersion) => updateOutputInvoiceCollectionStatus(rowId, {
        statusCode: "",
        expectedVersion,
      }).then((result) => handleLifecycleChanged(result))}
      onCancelReminder={(rowId, reminderId) => cancelOutputInvoiceCollectionReminder(rowId, reminderId).then((result) => handleLifecycleChanged(result))}
      onChanged={handleLifecycleChanged}
      onClose={handleCloseWorkflow}
    />
    <RedInvoiceRelationDrawer
      open={query.activeWorkflow?.kind === "redRelation"}
      row={redRelationRow}
      candidateRows={rows}
      onConfirm={(rowId, payload) => confirmOutputInvoiceRedRelation(rowId, payload).then((result) => handleLifecycleChanged(result))}
      onRevoke={(relationId) => revokeOutputInvoiceRedRelation(relationId).then((result) => handleLifecycleChanged(result))}
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
