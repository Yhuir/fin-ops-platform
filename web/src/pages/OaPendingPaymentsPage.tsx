import TableClassificationHeader from "../components/common/TableClassificationHeader";
import SegmentedControl from "../components/common/SegmentedControl";
import { Button, Checkbox, Input } from "@heroui/react";
import { ChevronLeft, ChevronRight, Download, PanelRightOpen, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AppDrawer from "../components/common/AppDrawer";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import QuerySearch from "../components/common/QuerySearch";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import OaPendingPaymentExportDrawer from "../components/oaPendingPayments/OaPendingPaymentExportDrawer";
import OaPendingPaymentsTable from "../components/oaPendingPayments/OaPendingPaymentsTable";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { formatDateTimeText } from "../features/dateTime";
import {
  fetchOaPendingPaymentBankCandidates,
  fetchOaPendingPaymentDetail,
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
  OaPendingPaymentRowsResponse,
  OaPendingPaymentSortDirection,
  OaPendingPaymentSummary,
  OaPendingPaymentStatistics,
  LinkOaPendingPaymentBankTransactionsResponse,
} from "../features/oaPendingPayments/types";
import { formatMoney } from "../features/money";
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

const BANK_CANDIDATE_PAGE_SIZE = 100;

function finiteCount(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export default function OaPendingPaymentsPage() {
  const { canOperateData } = useSessionPermissions();
  const { active, activationGeneration } = useOptionalPageActivation("oa-pending-payments");
  const [query, setQuery] = useState<OaPendingPaymentQuery>(initialQuery);
  const [rows, setRows] = useState<OaPendingPaymentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<OaPendingPaymentSummary | null>(null);
  const [statistics, setStatistics] = useState<OaPendingPaymentStatistics | null>(null);
  const [filterConfigs, setFilterConfigs] = useState<OaPendingPaymentFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OaPendingPaymentFilterOption[]>>({});
  const [keywordDraft, setKeywordDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [selectedOaRowIds, setSelectedOaRowIds] = useState<Set<string>>(() => new Set());
  const [detailTarget, setDetailTarget] = useState<OaPendingPaymentDetailTarget | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [exportScope, setExportScope] = useState<OaPendingPaymentQuery | null>(null);
  const [bankLinkDrawerOpen, setBankLinkDrawerOpen] = useState(false);
  const requestIdRef = useRef(0);
  const tableWrapRef = useRef<HTMLDivElement | null>(null);
  const selectedOaRowIdList = useMemo(() => [...selectedOaRowIds], [selectedOaRowIds]);

  const clearVisibleRows = useCallback(() => {
    setRows([]);
    setTotal(0);
    setSummary(null);
    setStatistics(null);
    setFilterConfigs([]);
    setFilterOptions({});
  }, []);

  const applyRowsPayload = useCallback((payload: OaPendingPaymentRowsResponse) => {
    const payloadTotal = payload.pagination.total;
    setRows(payload.rows ?? []);
    setTotal(payloadTotal);
    setSummary(payload.summary);
    setStatistics(payload.statistics ?? null);
    setFilterConfigs(payload.filterConfig ?? []);
    setFilterOptions(payload.filterOptions ?? {});
  }, []);

  const loadRows = useCallback(async (
    mode: "reset" | "refresh",
    signal?: AbortSignal,
  ) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === "reset") {
      setLoading(true);
      setRows([]);
      setSelectedOaRowIds(new Set());
      if (tableWrapRef.current) tableWrapRef.current.scrollTop = 0;
    } else if (mode === "refresh") {
      setRefreshing(true);
    }
    setError(null);
    if (mode === "reset") setFeedback(null);
    try {
      const payload = await fetchOaPendingPaymentRows({ ...query, signal });
      if (signal?.aborted || requestId !== requestIdRef.current) {
        return;
      }
      const lastPage = Math.max(1, Math.ceil(payload.pagination.total / query.pageSize));
      if (query.page > lastPage) {
        setQuery(current => ({ ...current, page: lastPage }));
        return;
      }
      applyRowsPayload(payload);
    } catch (caught: unknown) {
      if (signal?.aborted || requestId !== requestIdRef.current) {
        return;
      }
      clearVisibleRows();
      setError(caught instanceof Error ? caught.message : "OA 待付款核对加载失败。");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [applyRowsPayload, clearVisibleRows, query]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    void loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadRows]);

  useEffect(() => {
    setSelectedOaRowIds(new Set());
    setDetailTarget(null);
  }, [query.keyword, query.filters, query.viewMode, query.tradeDateFrom, query.tradeDateTo, query.month]);

  const handleKeywordSubmit = useCallback(() => {
    setQuery((current) => ({ ...current, page: 1, keyword: keywordDraft.trim() }));
  }, [keywordDraft]);

  const handleKeywordClear = useCallback(() => {
    setKeywordDraft("");
    setQuery((current) => ({ ...current, page: 1, keyword: "" }));
  }, []);

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

  const handleBankLinkSuccess = useCallback(async (
    message: string,
    result: LinkOaPendingPaymentBankTransactionsResponse,
  ) => {
    setFeedback(message);
    setSelectedOaRowIds(new Set());
    loadRows("refresh");
  }, [loadRows]);

  const loadExpensePendingInvoiceRules = useCallback(() => fetchPendingInvoiceRules("expense"), []);

  const saveExpensePendingInvoiceRules = useCallback(
    (payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, "expense"),
    [],
  );

  const handleRulesSaved = useCallback(() => {
    setFeedback("规则已保存。");
  }, []);

  const secondaryActions = <>
    <button
      aria-label="支出流水无需开票规则设置"
      onClick={() => setRulesOpen(true)}
      className="oa-pending-payments-button"
      type="button"
    >
      <SlidersHorizontal aria-hidden="true" size={16} />
      支出流水无需开票规则设置
    </button>
  </>;
  const actions = useMemo(() => (
    <div className="oa-pending-payments-actions">
      <BusinessPeriodPicker
        allowedModes={["month"]}
        ariaLabel="OA月份筛选"
        onChange={(selection) => setQuery((current) => ({
          ...current,
          page: 1,
          month: selection.mode === "all" ? "" : selection.month,
        }))}
        selection={{
          mode: query.month ? "month" : "all",
          year: (query.month || DEFAULT_MONTH).slice(0, 4),
          month: query.month || DEFAULT_MONTH,
        }}
        years={nearbyBusinessYears(query.month || DEFAULT_MONTH)}
      />

      {query.viewMode === "in_progress" ? (
        <button
          aria-label="关联支出流水"
          onClick={() => setBankLinkDrawerOpen(true)}
          className="oa-pending-payments-button oa-pending-payments-button--primary"
          disabled={!canOperateData || loading || refreshing || selectedOaRowIds.size === 0}
          type="button"
        >
          <PanelRightOpen aria-hidden="true" size={16} />
          关联支出流水
          {selectedOaRowIds.size > 0 ? <span>{selectedOaRowIds.size}</span> : null}
        </button>
      ) : null}

      <button
        aria-label="导出 OA"
        className="oa-pending-payments-button"
        disabled={loading || refreshing || Boolean(error)}
        onClick={() => setExportScope(structuredClone(query))}
        type="button"
      >
        <Download aria-hidden="true" size={16} />
        导出 OA
      </button>
    </div>
  ), [canOperateData, loading, query, refreshing, selectedOaRowIds.size, error]);
  const paymentValues = query.filters.find(filter => filter.field === "payment_status")?.values ?? [];
  const titleAccessory = (
    <div className="page-title-accessory-group">
      <PageStatisticsPopover
        ariaLabel="OA 待付款核对数据统计"
        loading={loading && !statistics}
        coreItems={[
          { label: "已完成 OA", value: statistics?.completed_oa_count, unit: "条", tone: "success" },
          { label: "进行中 OA", value: statistics?.in_progress_oa_count, unit: "条" },
          { label: "进项发票", value: statistics?.input_invoice_count, unit: "张" },
        ]}
        detailItems={[]}
      />
    </div>
  );

  return (
    <>
      <div className="oa-pending-payments-page" data-testid="oa-pending-payments-page">
        <PageScaffold secondaryActions={secondaryActions} query={(<QuerySearch
          ariaLabel="搜索OA待付款核对"
          onChange={setKeywordDraft}
          onClear={handleKeywordClear}
          onSubmit={handleKeywordSubmit}
          placeholder="搜索 OA / 流水 / 发票"
          value={keywordDraft}
        />)} fillViewport title="OA付款情况" titleAccessory={titleAccessory} actions={actions}>
          <div className="oa-pending-payments-content finance-table-layout">
            <TableClassificationHeader label="OA 核对分类" unit="条" pending={loading || refreshing} invalid={Boolean(error)}
              root={{ id: "all", label: "OA 核对范围", count: summary ? summary.viewCounts.completed + summary.viewCounts.in_progress : undefined }}
              groups={(["completed", "in_progress"] as const).map(view => {
                const select = (values: string[]) => setQuery(current => ({
                  ...current, page: 1, viewMode: view,
                  filters: [...current.filters.filter(filter => filter.field !== "payment_status"),
                  ...(values.length ? [{ field: "payment_status", operator: "in" as const, values }] : [])]
                }));
                return {
                  id: view, label: view === "completed" ? "已完成 OA" : "进行中 OA",
                  count: summary?.viewCounts[view], tone: view === "completed" ? "green" : "purple",
                  selected: query.viewMode === view && (paymentValues.length === 0 || (paymentValues.length === 2 && paymentValues.includes("paid") && paymentValues.includes("unpaid"))), onSelect: () => select([]),
                  children: (["paid", "unpaid"] as const).map(status => ({
                    id: `${view}:${status}`, label: status === "paid" ? "已关联流水" : "未关联流水",
                    count: summary?.classificationCounts[view][status],
                    selected: query.viewMode === view && paymentValues.length === 1 && paymentValues[0] === status, onSelect: () => select([status]),
                  })),
                };
              })} />
            {(error || feedback || !canOperateData) && <div className="page-feedback-floating">
              {error ? <div role="alert">{error}<button className="oa-pending-payments-button" type="button" onClick={() => void loadRows("refresh")}>重试</button></div>
                : <div role="status">{feedback || "当前页面暂不可关联支出流水。"}</div>}
            </div>}
            <OaPendingPaymentsTable
              rows={rows}
              loading={loading || refreshing}
              tableWrapRef={tableWrapRef}
              page={query.page}
              pageSize={query.pageSize}
              total={total}
              oaCount={summary?.oaCount}
              filterConfigs={filterConfigs}
              filterOptions={filterOptions}
              filters={query.filters}
              onFilterApply={handleFilterApply}
              onFilterClear={handleFilterClear}
              onSortChange={handleSortChange}
              onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
              onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
              onOpenDetail={setDetailTarget}
              selectedOaRowIds={selectedOaRowIds}
              onToggleOaSelection={canOperateData && query.viewMode === "in_progress" ? handleToggleOaSelection : undefined}
              emptyStateMessage={
                error
                  ? "OA 待付款核对加载失败，请使用错误提示中的重试按钮。"
                  : loading || refreshing
                    ? "OA 待付款核对数据正在刷新，请稍候。"
                    : "当前条件下暂无记录。"
              }
            />
          </div>
        </PageScaffold>
      </div>
      <InputInvoiceUsageDetailDrawer onBankSplitSaved={() => loadRows("refresh")}
        open={detailTarget !== null}
        target={detailTarget}
        loadDetail={fetchOaPendingPaymentDetail}
        onClose={() => setDetailTarget(null)}
      />
      <PendingInvoiceRulesDrawer
        open={rulesOpen}
        loadRules={loadExpensePendingInvoiceRules}
        saveRules={saveExpensePendingInvoiceRules}
        title="支出流水无需开票规则设置"
        onSaved={handleRulesSaved}
        onClose={() => setRulesOpen(false)}
      />
      <OaBankLinkDrawer
        open={canOperateData && bankLinkDrawerOpen}
        selectedOaRowIds={selectedOaRowIdList}
        onLinked={handleBankLinkSuccess}
        onError={setError}
        onClose={() => setBankLinkDrawerOpen(false)}
      />
      {exportScope ? <OaPendingPaymentExportDrawer
        query={exportScope}
        onClose={() => setExportScope(null)}
      /> : null}
    </>
  );
}

function linkBankSuccessMessage(result: LinkOaPendingPaymentBankTransactionsResponse): string {
  if (result.paymentStatusSync?.code === "queued") {
    return "已关联支出流水，OA 支付状态正在自动同步。";
  }
  return "已关联支出流水，正在重新加载当前核对表。";
}

function selectableOaRowIds(row: OaPendingPaymentRow): string[] {
  return rowOaIds(row);
}

function rowOaIds(row: OaPendingPaymentRow): string[] {
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
  onLinked: (message: string, result: LinkOaPendingPaymentBankTransactionsResponse) => Promise<void> | void;
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const [completion, setCompletion] = useState<string | undefined>();
  useEffect(() => { if (!open) setCompletion(undefined); }, [open]);
  const [relationStatus, setRelationStatus] = useState<OaPendingPaymentBankCandidateRelationStatus>("all");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [keyword, setKeyword] = useState("");
  const [rows, setRows] = useState<OaPendingPaymentBankCandidate[]>([]);
  const [selectedBankIds, setSelectedBankIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [searchGeneration, setSearchGeneration] = useState(0);
  const candidateRequestSeqRef = useRef(0);
  const pageCount = Math.max(1, Math.ceil(total / BANK_CANDIDATE_PAGE_SIZE));
  const closeBlocked = (!completion && loading) || submitting;

  const loadCandidates = useCallback((signal?: AbortSignal) => {
    if (!open || completion) {
      return;
    }
    const requestId = candidateRequestSeqRef.current + 1;
    candidateRequestSeqRef.current = requestId;
    setCandidateError(null);
    setLoading(true);
    fetchOaPendingPaymentBankCandidates({
      relationStatus,
      keyword,
      oaRowIds: selectedOaRowIds,
      page,
      pageSize: BANK_CANDIDATE_PAGE_SIZE,
      signal,
    })
      .then((payload) => {
        if (signal?.aborted || requestId !== candidateRequestSeqRef.current) {
          return;
        }
        setCandidateError(null);
        setRows(payload.rows ?? []);
        setTotal(payload.pagination?.total ?? payload.rows?.length ?? 0);
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== candidateRequestSeqRef.current) {
          return;
        }
        setCandidateError(caught instanceof Error ? caught.message : "支出流水加载失败。");
        setRows([]);
        setTotal(0);
      })
      .finally(() => {
        if (!signal?.aborted && requestId === candidateRequestSeqRef.current) {
          setLoading(false);
        }
      });
  }, [completion, keyword, open, page, relationStatus, selectedOaRowIds]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const controller = new AbortController();
    setSelectedBankIds(new Set());
    loadCandidates(controller.signal);
    return () => controller.abort();
  }, [loadCandidates, open, searchGeneration]);

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

  const searchCandidates = () => {
    setPage(1);
    setKeyword(keywordDraft.trim());
    setSearchGeneration((current) => current + 1);
  };

  const submit = () => {
    if (loading || submitting || selectedOaRowIds.length === 0 || selectedBankIds.size === 0) {
      return;
    }
    setSubmitting(true);
    void (async () => {
      try {
        const result = await linkOaPendingPaymentBankTransactions({
          oaRowIds: selectedOaRowIds,
          bankTransactionIds: [...selectedBankIds],
          idempotencyKey: `oa-pending-link-${selectedOaRowIds.join("-")}-${[...selectedBankIds].join("-")}-${Date.now()}`,
        });
        setCompletion("支出流水关联已保存");
        await onLinked(linkBankSuccessMessage(result), result);
      } catch (caught: unknown) {
        onError(caught instanceof Error ? caught.message : "关联支出流水失败。");
      } finally {
        setSubmitting(false);
      }
    })();
  };

  return (
    <AppDrawer
      ariaBusy={closeBlocked}
      completion={completion}
      ariaLabel="关联支出流水抽屉"
      className="oa-pending-payments-bank-drawer"
      closeDisabled={closeBlocked}
      closeLabel="关闭关联支出流水抽屉"
      footer={(
        <div className="oa-pending-payments-bank-drawer__footer">

          <Button
            className="oa-pending-payments-button oa-pending-payments-button--primary"
            isDisabled={loading || submitting || selectedOaRowIds.length === 0 || selectedBankIds.size === 0}
            isPending={submitting}
            onPress={submit}
            size="sm"
            variant="primary"
          >
            确认关联 {selectedBankIds.size} 条流水
          </Button>
        </div>
      )}
      onClose={onClose}
      open={open}
      title="关联支出流水"
      width="min(560px, 100vw)"
    >
        <div className="oa-pending-payments-bank-drawer__meta">已选 OA {selectedOaRowIds.length} 条</div>
        <SegmentedControl label="支出流水关联状态" value={relationStatus}
          onChange={status => { setRelationStatus(status); setPage(1); }}
          options={(["all", "unmatched", "matched", "linked_in_progress"] as OaPendingPaymentBankCandidateRelationStatus[]).map(status => ({ key: status, label: bankCandidateFilterLabel(status) }))} />
        <label className="oa-pending-payments-bank-drawer__search">
          <span>搜索</span>
          <Input
            placeholder="对方户名 / 摘要 / 金额"
            value={keywordDraft}
            onChange={(event) => setKeywordDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                searchCandidates();
              }
            }}
          />
          <Button isDisabled={submitting} onPress={searchCandidates} size="sm" variant="secondary">查询</Button>
        </label>
        <div className="oa-pending-payments-bank-drawer__meta">
          {loading ? "加载中" : `显示 ${rows.length} / ${total} 条`}
        </div>
        {candidateError ? (
          <div className="oa-pending-payments-alert" role="alert">
            {candidateError}
          </div>
        ) : null}
        <div className="oa-pending-payments-bank-drawer__list">
          {rows.length === 0 && !loading ? <div className="oa-pending-payments-bank-drawer__empty">暂无支出流水</div> : null}
          {rows.map((row) => (
            <Checkbox
              className="oa-pending-payments-bank-drawer__row"
              isDisabled={row.relationStatus !== "unmatched"}
              isSelected={selectedBankIds.has(row.id)}
              key={row.id}
              onChange={() => toggleBank(row.id)}
            >
              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
              <span className="oa-pending-payments-bank-drawer__row-main">
                <span className="oa-pending-payments-bank-drawer__counterparty">{row.counterpartyName || "-"}</span>
                <span className="oa-pending-payments-bank-drawer__tags">
                  {row.tradeTime ? <span>{formatDateTimeText(row.tradeTime)}</span> : null}
                  {row.bankAccount ? <span>{row.bankAccount}</span> : null}
                  <span>{row.relationStatusLabel}</span>
                </span>
                <span className="oa-pending-payments-bank-drawer__summary">{[row.summary, row.remark].filter(Boolean).join(" / ") || "-"}</span>
              </span>
              <span className="oa-pending-payments-bank-drawer__amount">{formatMoney(row.amount, "-")}</span>
            </Checkbox>
          ))}
        </div>
        <div className="oa-pending-payments-bank-drawer__pagination">
          <span>第 {page} / {pageCount} 页</span>
          <div className="oa-pending-payments-bank-drawer__pagination-actions">
            <Button
              aria-label="上一页"
              isDisabled={loading || page <= 1}
              isIconOnly
              onPress={() => setPage((current) => Math.max(1, current - 1))}
              size="sm"
              variant="tertiary"
            >
              <ChevronLeft aria-hidden="true" size={18} />
            </Button>
            <Button
              aria-label="下一页"
              isDisabled={loading || page >= pageCount}
              isIconOnly
              onPress={() => setPage((current) => Math.min(pageCount, current + 1))}
              size="sm"
              variant="tertiary"
            >
              <ChevronRight aria-hidden="true" size={18} />
            </Button>
          </div>
        </div>
    </AppDrawer>
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
