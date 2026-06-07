import { RefreshCw, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
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
    <div className="oa-pending-payments-actions">
      <button
        aria-label="支出流水无需开票规则设置"
        onClick={() => setRulesOpen(true)}
        className="oa-pending-payments-button"
        type="button"
      >
        <SlidersHorizontal aria-hidden="true" size={16} />
        支出流水无需开票规则设置
      </button>
      <button
        className="oa-pending-payments-button oa-pending-payments-button--primary"
        disabled={refreshing}
        onClick={() => loadRows("refresh")}
        type="button"
      >
        <RefreshCw aria-hidden="true" size={16} />
        刷新
      </button>
    </div>
  ), [loadRows, refreshing]);
  const isEmpty = !loading && !error && rows.length === 0;

  return (
    <>
      <div className="oa-pending-payments-page" data-testid="oa-pending-payments-page">
        <PageScaffold title="OA 待付款核对" actions={actions}>
          <div className="oa-pending-payments-content">
            <PageToolbar
              className="oa-pending-payments-query"
              left={(
                <div className="oa-pending-payments-query__grid">
                  <label className="oa-pending-payments-field oa-pending-payments-field--search">
                    <span>全页面检索</span>
                    <input
                      aria-label="全页面检索"
                      value={keywordDraft}
                      onChange={(event) => setKeywordDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          handleKeywordSubmit();
                        }
                      }}
                    />
                  </label>
                  <button className="oa-pending-payments-button" onClick={handleKeywordSubmit} type="button">查询</button>
                  <label className="oa-pending-payments-field">
                    <span>月份</span>
                    <input
                      type="month"
                      value={query.month}
                      onChange={(event) => setQuery((current) => ({ ...current, page: 1, month: event.target.value }))}
                    />
                  </label>
                  <label className="oa-pending-payments-field">
                    <span>交易开始</span>
                    <input
                      type="date"
                      value={query.tradeDateFrom}
                      onChange={(event) => setQuery((current) => ({ ...current, page: 1, tradeDateFrom: event.target.value }))}
                    />
                  </label>
                  <label className="oa-pending-payments-field">
                    <span>交易结束</span>
                    <input
                      type="date"
                      value={query.tradeDateTo}
                      onChange={(event) => setQuery((current) => ({ ...current, page: 1, tradeDateTo: event.target.value }))}
                    />
                  </label>
                  <label className="oa-pending-payments-field">
                    <span>支付状态</span>
                    <select
                      value={query.filters.find((filter) => filter.field === "payment_status")?.values?.[0] ?? ""}
                      onChange={(event) => applyPaymentStatusFilter(event.target.value)}
                    >
                      <option value="">全部</option>
                      <option value="unpaid">未支付</option>
                      <option value="paid">已支付</option>
                      <option value="merged_paid">合并支付</option>
                      <option value="partially_paid">支付少了</option>
                      <option value="overpaid">支付多了</option>
                      <option value="pending_review">待核对</option>
                    </select>
                  </label>
                </div>
              )}
            />
            {error ? (
              <div className="oa-pending-payments-alert" role="alert">
                {error}
              </div>
            ) : null}
            {loading ? (
              <div className="oa-pending-payments-loading" aria-label="OA待付款核对加载中">
                <span className="oa-pending-payments-loading__bar" />
                <span className="oa-pending-payments-loading__panel" />
                <span className="oa-pending-payments-loading__panel" />
              </div>
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
          </div>
        </PageScaffold>
      </div>
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
