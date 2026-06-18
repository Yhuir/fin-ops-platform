import { PanelRightOpen, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import OaPendingPaymentsTable from "../components/oaPendingPayments/OaPendingPaymentsTable";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import {
  confirmOaPendingPaymentPaid,
  fetchOaPendingPaymentBankCandidates,
  fetchOaPendingPaymentDetail,
  fetchOaPendingPaymentFilterOptions,
  fetchOaPendingPaymentRows,
  linkOaPendingPaymentBankTransactions,
  nextOaPendingPaymentSortDirection,
} from "../features/oaPendingPayments/api";
import type {
  OaPendingPaymentBankCandidate,
  OaPendingPaymentBankCandidateRelationStatus,
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
  const [selectedOaRowIds, setSelectedOaRowIds] = useState<Set<string>>(() => new Set());
  const [detailTarget, setDetailTarget] = useState<OaPendingPaymentDetailTarget | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [bankLinkDrawerOpen, setBankLinkDrawerOpen] = useState(false);
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
    setSelectedOaRowIds(new Set());
  }, []);

  const handleConfirmPaid = useCallback((row: OaPendingPaymentRow) => {
    const oaRowId = row.oa.primaryOaId || row.oa.id;
    const bankTransactionIds = confirmBankTransactionIds(row);
    if (!oaRowId) {
      setError("OA 行缺少可确认的 OA ID。");
      return;
    }
    setConfirmingRowIds((current) => new Set(current).add(row.id));
    setFeedback(null);
    setError(null);
    confirmOaPendingPaymentPaid({
      oaRowId,
      bankTransactionIds: bankTransactionIds.length > 0 ? bankTransactionIds : undefined,
      idempotencyKey: `oa-pending-paid-${oaRowId}-${bankTransactionIds.join("-") || "active"}-${Date.now()}`,
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

  const handleToggleOaSelection = useCallback((row: OaPendingPaymentRow) => {
    const ids = selectableOaRowIds(row);
    if (ids.length === 0) {
      return;
    }
    setSelectedOaRowIds((current) => {
      const next = new Set(current);
      const selected = ids.every((id) => next.has(id));
      ids.forEach((id) => {
        if (selected) {
          next.delete(id);
        } else {
          next.add(id);
        }
      });
      return next;
    });
  }, []);

  const handleBankLinkSuccess = useCallback((message: string) => {
    setFeedback(message);
    setSelectedOaRowIds(new Set());
    setBankLinkDrawerOpen(false);
    loadRows("refresh");
  }, [loadRows]);

  const loadExpensePendingInvoiceRules = useCallback(() => fetchPendingInvoiceRules("expense"), []);

  const saveExpensePendingInvoiceRules = useCallback(
    (payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, "expense"),
    [],
  );

  const actions = useMemo(() => (
    <div className="oa-pending-payments-actions">
      {query.viewMode === "in_progress" ? (
        <button
          aria-label="关联支出流水"
          onClick={() => setBankLinkDrawerOpen(true)}
          className="oa-pending-payments-button oa-pending-payments-button--primary"
          disabled={selectedOaRowIds.size === 0}
          type="button"
        >
          <PanelRightOpen aria-hidden="true" size={16} />
          关联支出流水
          {selectedOaRowIds.size > 0 ? <span>{selectedOaRowIds.size}</span> : null}
        </button>
      ) : null}
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
  ), [query.viewMode, selectedOaRowIds.size]);
  const isEmpty = !loading && !error && rows.length === 0;
  const completedCountLabel = formatViewCount(summary.viewCounts?.completed);
  const inProgressCountLabel = formatViewCount(summary.viewCounts?.in_progress);

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
                      {completedCountLabel ? <span className="oa-pending-payments-view-toggle__count">{completedCountLabel}</span> : null}
                    </button>
                    <button
                      className={query.viewMode === "in_progress" ? "oa-pending-payments-view-toggle__button oa-pending-payments-view-toggle__button--active" : "oa-pending-payments-view-toggle__button"}
                      onClick={() => handleViewModeChange("in_progress")}
                      type="button"
                    >
                      进行中 OA
                      {inProgressCountLabel ? <span className="oa-pending-payments-view-toggle__count">{inProgressCountLabel}</span> : null}
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
                  selectedOaRowIds={selectedOaRowIds}
                  onToggleOaSelection={query.viewMode === "in_progress" ? handleToggleOaSelection : undefined}
                  confirmingRowIds={confirmingRowIds}
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
      <OaBankLinkDrawer
        open={bankLinkDrawerOpen}
        selectedOaRowIds={[...selectedOaRowIds]}
        onLinked={handleBankLinkSuccess}
        onError={setError}
        onClose={() => setBankLinkDrawerOpen(false)}
      />
    </>
  );
}

function formatViewCount(count: number | null | undefined): string {
  return typeof count === "number" && Number.isFinite(count) ? `${count}条` : "";
}

function confirmBankTransactionIds(row: OaPendingPaymentRow): string[] {
  const ids: string[] = [];
  if (row.bankTransaction.primaryBankTransactionId) {
    ids.push(row.bankTransaction.primaryBankTransactionId);
  }
  row.bankTransaction.summaries?.forEach((summary) => {
    if (summary.bankTransactionId && !ids.includes(summary.bankTransactionId)) {
      ids.push(summary.bankTransactionId);
    }
  });
  return ids;
}

function selectableOaRowIds(row: OaPendingPaymentRow): string[] {
  if (row.oaPaymentWriteback?.code === "written") {
    return [];
  }
  const ids: string[] = [];
  const primary = row.oa.primaryOaId || row.oa.id;
  if (primary) {
    ids.push(primary);
  }
  row.oa.summaries?.forEach((summary) => {
    if (summary.oaId && !ids.includes(summary.oaId)) {
      ids.push(summary.oaId);
    }
  });
  return ids;
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

function OaBankLinkDrawer({
  open,
  selectedOaRowIds,
  onLinked,
  onError,
  onClose,
}: {
  open: boolean;
  selectedOaRowIds: string[];
  onLinked: (message: string) => void;
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const [relationStatus, setRelationStatus] = useState<OaPendingPaymentBankCandidateRelationStatus>("all");
  const [keyword, setKeyword] = useState("");
  const [rows, setRows] = useState<OaPendingPaymentBankCandidate[]>([]);
  const [selectedBankIds, setSelectedBankIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [total, setTotal] = useState(0);

  const loadCandidates = useCallback((signal?: AbortSignal) => {
    if (!open) {
      return;
    }
    setLoading(true);
    fetchOaPendingPaymentBankCandidates({
      relationStatus,
      keyword,
      page: 1,
      pageSize: 100,
      signal,
    })
      .then((payload) => {
        setRows(payload.rows ?? []);
        setTotal(payload.pagination?.total ?? payload.rows?.length ?? 0);
      })
      .catch((caught: unknown) => {
        if (signal?.aborted) {
          return;
        }
        setRows([]);
        setTotal(0);
        onError(caught instanceof Error ? caught.message : "支出流水加载失败。");
      })
      .finally(() => {
        if (!signal?.aborted) {
          setLoading(false);
        }
      });
  }, [keyword, onError, open, relationStatus]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const controller = new AbortController();
    setSelectedBankIds(new Set());
    loadCandidates(controller.signal);
    return () => controller.abort();
  }, [loadCandidates, open]);

  const toggleBank = (bankId: string) => {
    setSelectedBankIds((current) => {
      const next = new Set(current);
      if (next.has(bankId)) {
        next.delete(bankId);
      } else {
        next.add(bankId);
      }
      return next;
    });
  };

  const submit = () => {
    if (selectedOaRowIds.length === 0 || selectedBankIds.size === 0) {
      return;
    }
    setSubmitting(true);
    linkOaPendingPaymentBankTransactions({
      oaRowIds: selectedOaRowIds,
      bankTransactionIds: [...selectedBankIds],
      idempotencyKey: `oa-pending-link-${selectedOaRowIds.join("-")}-${[...selectedBankIds].join("-")}-${Date.now()}`,
    })
      .then(() => onLinked("已关联支出流水，等待核对表刷新。"))
      .catch((caught: unknown) => {
        onError(caught instanceof Error ? caught.message : "关联支出流水失败。");
      })
      .finally(() => setSubmitting(false));
  };

  if (!open) {
    return null;
  }

  return (
    <div className="oa-pending-payments-drawer-backdrop" role="presentation">
      <aside aria-label="关联支出流水抽屉" className="oa-pending-payments-bank-drawer">
        <div className="oa-pending-payments-bank-drawer__header">
          <div>
            <h2>关联支出流水</h2>
            <p>已选 OA {selectedOaRowIds.length} 条</p>
          </div>
          <button aria-label="关闭关联支出流水抽屉" onClick={onClose} type="button">×</button>
        </div>
        <div className="oa-pending-payments-bank-drawer__filters">
          {(["all", "unmatched", "matched", "linked_in_progress"] as OaPendingPaymentBankCandidateRelationStatus[]).map((status) => (
            <button
              className={relationStatus === status ? "oa-pending-payments-bank-drawer__filter oa-pending-payments-bank-drawer__filter--active" : "oa-pending-payments-bank-drawer__filter"}
              key={status}
              onClick={() => setRelationStatus(status)}
              type="button"
            >
              {bankCandidateFilterLabel(status)}
            </button>
          ))}
        </div>
        <label className="oa-pending-payments-bank-drawer__search">
          <span>搜索</span>
          <input
            placeholder="对方户名 / 摘要 / 金额"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                loadCandidates();
              }
            }}
          />
          <button onClick={() => loadCandidates()} type="button">查询</button>
        </label>
        <div className="oa-pending-payments-bank-drawer__meta">
          {loading ? "加载中" : `显示 ${rows.length} / ${total} 条`}
        </div>
        <div className="oa-pending-payments-bank-drawer__list">
          {rows.length === 0 && !loading ? <div className="oa-pending-payments-bank-drawer__empty">暂无支出流水</div> : null}
          {rows.map((row) => (
            <label className="oa-pending-payments-bank-drawer__row" key={row.id}>
              <input
                checked={selectedBankIds.has(row.id)}
                disabled={row.relationStatus !== "unmatched"}
                onChange={() => toggleBank(row.id)}
                type="checkbox"
              />
              <span className="oa-pending-payments-bank-drawer__row-main">
                <span className="oa-pending-payments-bank-drawer__counterparty">{row.counterpartyName || "-"}</span>
                <span className="oa-pending-payments-bank-drawer__tags">
                  {row.tradeTime ? <span>{row.tradeTime}</span> : null}
                  {row.bankAccount ? <span>{row.bankAccount}</span> : null}
                  <span>{row.relationStatusLabel}</span>
                </span>
                <span className="oa-pending-payments-bank-drawer__summary">{[row.summary, row.remark].filter(Boolean).join(" / ") || "-"}</span>
              </span>
              <span className="oa-pending-payments-bank-drawer__amount">{row.amount}</span>
            </label>
          ))}
        </div>
        <div className="oa-pending-payments-bank-drawer__footer">
          <button onClick={onClose} type="button">取消</button>
          <button
            className="oa-pending-payments-button oa-pending-payments-button--primary"
            disabled={submitting || selectedOaRowIds.length === 0 || selectedBankIds.size === 0}
            onClick={submit}
            type="button"
          >
            {submitting ? "关联中" : `确认关联 ${selectedBankIds.size} 条流水`}
          </button>
        </div>
      </aside>
    </div>
  );
}

function bankCandidateFilterLabel(status: OaPendingPaymentBankCandidateRelationStatus): string {
  if (status === "unmatched") {
    return "未配对";
  }
  if (status === "matched") {
    return "已配对";
  }
  if (status === "linked_in_progress") {
    return "已关联进行中OA";
  }
  return "全部";
}
