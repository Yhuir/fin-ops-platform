import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import InputInvoiceUsageExportDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageExportDrawer";
import InputInvoiceUsageTable from "../components/inputInvoiceUsage/InputInvoiceUsageTable";
import OaReverseWorkspaceDrawer, { type OaReversePreviewRequest } from "../components/inputInvoiceUsage/OaReverseWorkspaceDrawer";
import PaymentStatusRulesDrawer from "../components/inputInvoiceUsage/PaymentStatusRulesDrawer";
import { usePageSessionState } from "../contexts/PageSessionStateContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { usePageScrollSession } from "../hooks/usePageScrollSession";
import {
  downloadInputInvoiceUsageExport,
  fetchInputInvoiceUsageBankTransactionDetail,
  fetchInputInvoiceUsageExportPreview,
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
} from "../features/inputInvoiceUsage/api";
import type {
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageQuery,
  InputInvoiceUsageRow,
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
    filters: [],
    sortField: "",
    sortDirection: "",
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
  const [error, setError] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(() => new Set());
  const tableWrapRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "input-invoice-usage",
    scrollKey: "usage-table",
  });
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
    fetchInputInvoiceUsageRows(request)
      .then((payload) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRows(payload.rows);
        setTotal(payload.pagination.total);
        setReadModelStatus(payload.readModelStatus || "");
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
        startIcon={<FileDownloadOutlinedIcon />}
        variant="outlined"
        onClick={() => setQuery((current) => ({ ...current, activeWorkflow: "export" }))}
      >
        筛选内容导出
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
  const isEmpty = !loading && !error && rows.length === 0;

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
            {loading ? (
              <Stack spacing={1.25} aria-label="进项发票使用情况加载中">
                <Skeleton variant="rounded" height={44} />
                <Skeleton variant="rounded" height={96} />
                <Skeleton variant="rounded" height={96} />
              </Stack>
            ) : (
              <>
                {isEmpty ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
                <InputInvoiceUsageTable
                  rows={rows}
                  page={query.page}
                  pageSize={query.pageSize}
                  total={total}
                  expandedCells={expandedCells}
                  onToggleCellExpand={handleToggleCellExpand}
                  onOpenDetail={handleOpenDetail}
                  onPageChange={handlePageChange}
                  onPageSizeChange={handlePageSizeChange}
                  tableWrapRef={tableWrapRef}
                />
              </>
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
      <InputInvoiceUsageExportDrawer
        open={query.activeWorkflow === "export"}
        loadPreview={loadExportPreview}
        downloadExport={downloadExport}
        onClose={handleCloseWorkflow}
      />
    </>
  );
}
