import { SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import OaPendingPaymentsTable from "../components/oaPendingPayments/OaPendingPaymentsTable";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import {
  confirmOaPendingPaymentPaid,
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
  OaPendingPaymentViewMode,
} from "../features/oaPendingPayments/types";
import { fetchPendingInvoiceRules, savePendingInvoiceRules } from "../features/pendingInvoices/api";

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
  viewMode: "completed",
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
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<OaPendingPaymentSummary>({ rowCount: 0 });
  const [filterConfigs, setFilterConfigs] = useState<OaPendingPaymentFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OaPendingPaymentFilterOption[]>>({});
  const [keywordDraft, setKeywordDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [confirmingRowIds, setConfirmingRowIds] = useState<Set<string>>(() => new Set());
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
        viewMode: query.viewMode,
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

  const handleViewModeChange = useCallback((viewMode: OaPendingPaymentViewMode) => {
    setQuery((current) => ({ ...current, page: 1, viewMode }));
  }, []);

  const handleConfirmPaid = useCallback((row: OaPendingPaymentRow) => {
    const oaRowId = row.oa.primaryOaId || row.oa.id;
    const bankTransactionId = confirmBankTransactionId(row);
    if (!oaRowId) {
      setError("OA 行缺少可确认的 OA ID。");
      return;
    }
    setConfirmingRowIds((current) => new Set(current).add(row.id));
    setFeedback(null);
    setError(null);
    confirmOaPendingPaymentPaid({
      oaRowId,
      bankTransactionId: bankTransactionId || undefined,
      idempotencyKey: `oa-pending-paid-${oaRowId}-${bankTransactionId || "active"}-${Date.now()}`,
    })
      .then((payload) => {
        setFeedback(payload.oaPaymentWriteback?.label === "已写回" ? "已确认支付并写回 OA。" : "已确认支付，等待 OA 写回状态刷新。");
        loadRows("refresh");
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "确认已支付失败。");
      })
      .finally(() => {
        setConfirmingRowIds((current) => {
          const next = new Set(current);
          next.delete(row.id);
          return next;
        });
      });
  }, [loadRows]);

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
    </div>
  ), []);
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
                  <div className="oa-pending-payments-view-toggle" aria-label="OA流程状态视图">
                    <button
                      className={query.viewMode === "completed" ? "oa-pending-payments-view-toggle__button oa-pending-payments-view-toggle__button--active" : "oa-pending-payments-view-toggle__button"}
                      onClick={() => handleViewModeChange("completed")}
                      type="button"
                    >
                      已完成 OA
                    </button>
                    <button
                      className={query.viewMode === "in_progress" ? "oa-pending-payments-view-toggle__button oa-pending-payments-view-toggle__button--active" : "oa-pending-payments-view-toggle__button"}
                      onClick={() => handleViewModeChange("in_progress")}
                      type="button"
                    >
                      进行中 OA
                    </button>
                  </div>
                  <label className="oa-pending-payments-field">
                    <span>月份</span>
                    <input
                      type="month"
                      value={query.month}
                      onChange={(event) => setQuery((current) => ({ ...current, page: 1, month: event.target.value }))}
                    />
                  </label>
                </div>
              )}
            />
            {error ? (
              <div className="oa-pending-payments-alert" role="alert">
                {error}
              </div>
            ) : null}
            {feedback ? (
              <div className="oa-pending-payments-alert oa-pending-payments-alert--success" role="status">
                {feedback}
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
                  keywordDraft={keywordDraft}
                  filterConfigs={filterConfigs}
                  filterOptions={filterOptions}
                  filters={query.filters}
                  onKeywordDraftChange={setKeywordDraft}
                  onKeywordSubmit={handleKeywordSubmit}
                  onFilterApply={handleFilterApply}
                  onFilterClear={handleFilterClear}
                  onSortChange={handleSortChange}
                  onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
                  onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
                  onOpenDetail={setDetailTarget}
                  onConfirmPaid={handleConfirmPaid}
                  confirmingRowIds={confirmingRowIds}
                  viewMode={query.viewMode}
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
        title="支出流水无需开票规则设置"
        onSaved={() => loadRows("refresh")}
        onClose={() => setRulesOpen(false)}
      />
    </>
  );
}

function confirmBankTransactionId(row: OaPendingPaymentRow): string {
  if (row.bankTransaction.primaryBankTransactionId) {
    return row.bankTransaction.primaryBankTransactionId;
  }
  const firstSummary = row.bankTransaction.summaries?.find((summary) => summary.bankTransactionId);
  return firstSummary?.bankTransactionId ?? "";
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
