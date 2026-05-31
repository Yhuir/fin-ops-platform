import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import InputInvoiceUsageTable from "../components/inputInvoiceUsage/InputInvoiceUsageTable";
import OaReverseWorkspaceDrawer, { type OaReversePreviewRequest } from "../components/inputInvoiceUsage/OaReverseWorkspaceDrawer";
import PaymentStatusRulesDrawer from "../components/inputInvoiceUsage/PaymentStatusRulesDrawer";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import {
  fetchInputInvoiceUsageBankTransactionDetail,
  fetchInputInvoiceUsageFilterOptions,
  fetchInputInvoiceUsageInvoiceDetail,
  fetchInputInvoiceUsageOaDetail,
  fetchInputInvoiceUsagePaymentStatusRules,
  fetchInputInvoiceUsageRows,
  fetchInputInvoiceUsageRowRelationDetail,
  createInputInvoiceUsageOaReverseBatch,
  createInputInvoiceUsageOaReverseDraft,
  manualInputInvoiceUsageOaReverseStatus,
  nextSortDirection,
  previewInputInvoiceUsageOaReverse,
  refreshInputInvoiceUsageOaReverseStatus,
  revokeInputInvoiceUsageOaReverseDraft,
  saveInputInvoiceUsagePaymentStatusRules,
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
  return value === null || value === "oaReverse" || value === "paymentRules";
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
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
}): InputInvoiceUsageFilter | null {
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

export default function InputInvoiceUsagePage() {
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
  const [filterConfigs, setFilterConfigs] = useState<InputInvoiceUsageFilterFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, InputInvoiceUsageFilterOption[]>>({});
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
        setFilterConfigs(payload.filterConfig.length > 0 ? payload.filterConfig : filterConfigsFromOptions(optionsPayload.fields));
        setFilterOptions(filterOptionsByField(optionsPayload.fields));
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
        setFilterConfigs([]);
        setFilterOptions({});
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
    loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [loadRows]);

  useEffect(() => {
    if (readModelStatus !== "refreshing" || loading || refreshing) {
      return undefined;
    }
    const retryId = window.setTimeout(() => loadRows("refresh"), READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [loadRows, loading, readModelStatus, refreshing]);

  const handleKeywordSubmit = useCallback(() => {
    setQuery((current) => ({
      ...current,
      page: 1,
      keyword: keywordDraft.trim(),
    }));
  }, [keywordDraft, setQuery]);

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
    })
  ), []);

  const actions = useMemo(() => (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Button
        variant="outlined"
        onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "oaReverse" }))}
      >
        以发票反提 OA
      </Button>
      <Button
        variant="outlined"
        onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "paymentRules" }))}
      >
        发票与支付状态规则设置
      </Button>
      <Button
        startIcon={<RefreshOutlinedIcon />}
        variant="contained"
        disabled={refreshing}
        onClick={() => loadRows("refresh")}
      >
        刷新
      </Button>
    </Stack>
  ), [loadRows, refreshing, setQuery]);

  return (
    <>
    <Box data-testid="input-invoice-usage-page" sx={{ minWidth: 0, overflowX: "hidden" }}>
      <PageScaffold
        title="进项发票使用情况"
        description="以进项发票为主对象反查支付状态、OA 和银行流水。"
        actions={actions}
      >
        <Stack spacing={2} sx={{ minWidth: 0, overflowX: "hidden" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
            <TextField
              label="关键字"
              size="small"
              value={keywordDraft}
              onChange={(event) => setKeywordDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  handleKeywordSubmit();
                }
              }}
              sx={{ width: { xs: "100%", md: 320 } }}
            />
            <Button variant="outlined" onClick={handleKeywordSubmit}>
              查询
            </Button>
          </Stack>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {readModelStatus === "refreshing" ? (
            <Alert severity="info">进项发票使用情况读模型正在刷新，完成后页面会自动重新加载。</Alert>
          ) : null}
          {loading ? (
            <Stack spacing={1.25} aria-label="进项发票使用情况加载中">
              <Skeleton variant="rounded" height={44} />
              <Skeleton variant="rounded" height={96} />
              <Skeleton variant="rounded" height={96} />
            </Stack>
          ) : (
            <InputInvoiceUsageTable
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
              onFilterApply={handleFilterApply}
              onFilterClear={handleFilterClear}
              onSortChange={handleSortChange}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
            />
          )}
        </Stack>
      </PageScaffold>
    </Box>
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
    </>
  );
}
