import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import OaPendingPaymentsTable from "../components/oaPendingPayments/OaPendingPaymentsTable";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import {
  fetchOaPendingPaymentDetail,
  fetchOaPendingPaymentFilterOptions,
  fetchOaPendingPaymentRows,
  nextOaPendingPaymentSortDirection,
} from "../features/oaPendingPayments/api";
import type {
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFieldConfig,
  OaPendingPaymentFilter,
  OaPendingPaymentFilterOption,
  OaPendingPaymentQuery,
  OaPendingPaymentRow,
  OaPendingPaymentSortDirection,
  OaPendingPaymentSummary,
} from "../features/oaPendingPayments/types";
import { fetchPendingInvoiceRules, savePendingInvoiceRules } from "../features/pendingInvoices/api";
import { usePageScrollSession } from "../hooks/usePageScrollSession";

const initialQuery: OaPendingPaymentQuery = {
  page: 1,
  pageSize: 20,
  keyword: "",
  month: "",
  tradeDateFrom: "",
  tradeDateTo: "",
  filters: [],
  sortField: "",
  sortDirection: "",
};

function filterOptionsByField(fields: Array<OaPendingPaymentFieldConfig & { options?: OaPendingPaymentFilterOption[] }>) {
  return fields.reduce<Record<string, OaPendingPaymentFilterOption[]>>((accumulator, field) => {
    accumulator[field.field] = field.options ?? [];
    return accumulator;
  }, {});
}

function filterConfigsFromOptions(fields: Array<OaPendingPaymentFieldConfig & { options?: OaPendingPaymentFilterOption[] }>) {
  return fields.map(({ options: _options, ...field }) => field);
}

export default function OaPendingPaymentsPage() {
  const [query, setQuery] = useState<OaPendingPaymentQuery>(initialQuery);
  const [rows, setRows] = useState<OaPendingPaymentRow[]>([]);
  const tableWrapRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "oa-pending-payments",
    scrollKey: "payments-table",
  });
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<OaPendingPaymentSummary>({ rowCount: 0 });
  const [filterConfigs, setFilterConfigs] = useState<OaPendingPaymentFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OaPendingPaymentFilterOption[]>>({});
  const [keywordDraft, setKeywordDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailTarget, setDetailTarget] = useState<OaPendingPaymentDetailTarget | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const requestIdRef = useRef(0);

  const loadRows = useCallback((mode: "reset" | "refresh", signal?: AbortSignal) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === "reset") {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    Promise.all([
      fetchOaPendingPaymentRows({ ...query, signal }),
      fetchOaPendingPaymentFilterOptions({
        keyword: query.keyword,
        month: query.month,
        tradeDateFrom: query.tradeDateFrom,
        tradeDateTo: query.tradeDateTo,
        filters: query.filters,
        signal,
      }),
    ])
      .then(([payload, optionsPayload]) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setRows(payload.rows ?? []);
        setTotal(payload.pagination?.total ?? 0);
        setSummary(payload.summary ?? { rowCount: payload.pagination?.total ?? 0 });
        setFilterConfigs((payload.filterConfig?.length ?? 0) > 0 ? payload.filterConfig : filterConfigsFromOptions(optionsPayload.fields ?? []));
        setFilterOptions(filterOptionsByField(optionsPayload.fields ?? []));
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== requestIdRef.current) {
          return;
        }
        setRows([]);
        setTotal(0);
        setSummary({ rowCount: 0 });
        setError(caught instanceof Error ? caught.message : "OA 待付款核对加载失败。");
      })
      .finally(() => {
        if (requestId === requestIdRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      });
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [loadRows]);

  const handleKeywordSubmit = useCallback(() => {
    setQuery((current) => ({ ...current, page: 1, keyword: keywordDraft.trim() }));
  }, [keywordDraft]);

  const handleSortChange = useCallback((field: string, direction?: OaPendingPaymentSortDirection) => {
    setQuery((current) => ({
      ...current,
      page: 1,
      sortField: field,
      sortDirection: direction ?? nextOaPendingPaymentSortDirection(current.sortField, current.sortDirection, field),
    }));
  }, []);

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
  }, []);

  const handleFilterClear = useCallback((field: string) => {
    setQuery((current) => ({ ...current, page: 1, filters: current.filters.filter((filter) => filter.field !== field) }));
  }, []);

  const applyPaymentStatusFilter = useCallback((statusCode: string) => {
    setQuery((current) => {
      const filters = current.filters.filter((filter) => filter.field !== "payment_status");
      return {
        ...current,
        page: 1,
        filters: statusCode ? [...filters, { field: "payment_status", operator: "in", values: [statusCode] }] : filters,
      };
    });
  }, []);

  const loadExpensePendingInvoiceRules = useCallback(() => fetchPendingInvoiceRules("expense"), []);

  const saveExpensePendingInvoiceRules = useCallback(
    (payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, "expense"),
    [],
  );

  const actions = useMemo(() => (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Button
        aria-label="支出流水无需开票规则设置"
        startIcon={<TuneOutlinedIcon />}
        variant="outlined"
        onClick={() => setRulesOpen(true)}
      >
        支出流水无需开票规则设置
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
  ), [loadRows, refreshing]);
  const isEmpty = !loading && !error && rows.length === 0;

  return (
    <>
      <Stack data-testid="oa-pending-payments-page" sx={{ minWidth: 0, overflowX: "hidden" }}>
        <PageScaffold title="OA 待付款核对" actions={actions}>
          <Stack spacing={1.5} sx={{ minWidth: 0 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
              <TextField
                label="全页面检索"
                inputProps={{ "aria-label": "全页面检索" }}
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
              <Button variant="outlined" onClick={handleKeywordSubmit}>查询</Button>
              <TextField
                label="月份"
                size="small"
                type="month"
                value={query.month}
                onChange={(event) => setQuery((current) => ({ ...current, page: 1, month: event.target.value }))}
                InputLabelProps={{ shrink: true }}
                sx={{ width: { xs: "100%", md: 150 } }}
              />
              <TextField
                label="交易开始"
                size="small"
                type="date"
                value={query.tradeDateFrom}
                onChange={(event) => setQuery((current) => ({ ...current, page: 1, tradeDateFrom: event.target.value }))}
                InputLabelProps={{ shrink: true }}
                sx={{ width: { xs: "100%", md: 150 } }}
              />
              <TextField
                label="交易结束"
                size="small"
                type="date"
                value={query.tradeDateTo}
                onChange={(event) => setQuery((current) => ({ ...current, page: 1, tradeDateTo: event.target.value }))}
                InputLabelProps={{ shrink: true }}
                sx={{ width: { xs: "100%", md: 150 } }}
              />
              <TextField
                select
                label="支付状态"
                size="small"
                value={query.filters.find((filter) => filter.field === "payment_status")?.values?.[0] ?? ""}
                onChange={(event) => applyPaymentStatusFilter(event.target.value)}
                sx={{ width: { xs: "100%", md: 170 } }}
              >
                <MenuItem value="">全部</MenuItem>
                <MenuItem value="unpaid">未支付</MenuItem>
                <MenuItem value="paid">已支付</MenuItem>
                <MenuItem value="merged_paid">合并支付</MenuItem>
                <MenuItem value="partially_paid">支付少了</MenuItem>
                <MenuItem value="overpaid">支付多了</MenuItem>
                <MenuItem value="pending_review">待核对</MenuItem>
              </TextField>
            </Stack>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {loading ? (
              <Stack spacing={1.25} aria-label="OA待付款核对加载中">
                <Skeleton variant="rounded" height={44} />
                <Skeleton variant="rounded" height={96} />
                <Skeleton variant="rounded" height={96} />
              </Stack>
            ) : (
              <>
                {isEmpty ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
                <OaPendingPaymentsTable
                  rows={rows}
                  page={query.page}
                  pageSize={query.pageSize}
                  total={total || summary.rowCount}
                  filterConfigs={filterConfigs}
                  filterOptions={filterOptions}
                  filters={query.filters}
                  onFilterApply={handleFilterApply}
                  onFilterClear={handleFilterClear}
                  onSortChange={handleSortChange}
                  onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
                  onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
                  onOpenDetail={setDetailTarget}
                  tableWrapRef={tableWrapRef}
                />
              </>
            )}
          </Stack>
        </PageScaffold>
      </Stack>
      <InputInvoiceUsageDetailDrawer
        open={detailTarget !== null}
        target={detailTarget}
        loadDetail={fetchOaPendingPaymentDetail}
        variant="persistent"
        onClose={() => setDetailTarget(null)}
      />
      <PendingInvoiceRulesDrawer
        open={rulesOpen}
        loadRules={loadExpensePendingInvoiceRules}
        saveRules={saveExpensePendingInvoiceRules}
        onSaved={() => loadRows("refresh")}
        onClose={() => setRulesOpen(false)}
      />
    </>
  );
}

function normalizeFilterValue(filter: {
  field: string;
  operator: string;
  value?: string | null;
  values?: string[];
}): OaPendingPaymentFilter | null {
  if (filter.operator === "in") {
    const values = Array.isArray(filter.values) ? filter.values.filter(Boolean) : [];
    return values.length > 0 ? { field: filter.field, operator: "in", values } : null;
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
