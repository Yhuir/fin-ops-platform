import { ChevronLeft, ChevronRight, PanelRightOpen, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import PageScaffold from "../components/common/PageScaffold";
import PageToolbar from "../components/common/PageToolbar";
import StatePanel from "../components/common/StatePanel";
import InputInvoiceUsageDetailDrawer from "../components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer";
import OaPendingPaymentAuditIcon from "../components/oaPendingPayments/OaPendingPaymentAuditIcon";
import OaPendingPaymentsTable from "../components/oaPendingPayments/OaPendingPaymentsTable";
import PendingInvoiceRulesDrawer from "../components/pendingInvoices/PendingInvoiceRulesDrawer";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  fetchOaPendingPaymentBankCandidates,
  fetchOaPendingPaymentDetail,
  fetchOaPendingPaymentRows,
  linkOaPendingPaymentBankTransactions,
  nextOaPendingPaymentSortDirection,
  writebackOaPendingPaymentPaid,
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
  OaPendingPaymentViewMode,
  LinkOaPendingPaymentBankTransactionsResponse,
  WritebackOaPendingPaymentPaidResponse,
} from "../features/oaPendingPayments/types";
import { operationBarrierTargets, waitForOperationFreshness } from "../features/operationBarrier/api";
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
const CONDITIONAL_REFRESH_INTERVAL_MS = 500;

const readModelStatusPriority = ["unavailable", "schema_mismatch", "missing", "failed", "stale", "refreshing", "fresh"];

type ReadModelStatusPayload = {
  readModelStatus?: string | null;
  read_model_status?: string | null;
};

function readModelStatusFromPayloads(...payloads: ReadModelStatusPayload[]): string {
  const statuses = payloads
    .map((payload) => (payload.readModelStatus ?? payload.read_model_status ?? "").trim().toLowerCase())
    .filter(Boolean);
  if (statuses.length === 0) {
    return "refreshing";
  }
  const knownStatuses = statuses.filter((status) => readModelStatusPriority.includes(status));
  if (knownStatuses.length > 0) {
    return knownStatuses.sort((left, right) => (
      readModelStatusPriority.indexOf(left) - readModelStatusPriority.indexOf(right)
    ))[0];
  }
  return statuses.find((status) => status !== "fresh") ?? "refreshing";
}

function isReadModelFresh(status: string) {
  return status === "fresh";
}

type OaPendingPaymentReadModelRefresh = {
  scopeKeys?: string[];
};

function normalizedRefreshScopeKeys(refresh: OaPendingPaymentReadModelRefresh | undefined) {
  return Array.from(new Set(
    (refresh?.scopeKeys ?? [])
      .map((scopeKey) => String(scopeKey).trim())
      .filter(Boolean),
  ));
}

function oaPendingPaymentBarrierTargets(refresh: OaPendingPaymentReadModelRefresh | undefined, currentScopeKey: string) {
  const visibleScopeKey = currentScopeKey.trim() || "all";
  const refreshScopeKeys = normalizedRefreshScopeKeys(refresh);
  const concreteRefreshScopeKeys = refreshScopeKeys.filter((scopeKey) => scopeKey !== "all");
  if (visibleScopeKey === "all" && concreteRefreshScopeKeys.length > 0) {
    return operationBarrierTargets("oa_pending_payment", concreteRefreshScopeKeys);
  }
  if (refreshScopeKeys.includes(visibleScopeKey)) {
    return operationBarrierTargets("oa_pending_payment", [visibleScopeKey]);
  }
  if (visibleScopeKey === "all" && refreshScopeKeys.length > 0) {
    return operationBarrierTargets("oa_pending_payment", refreshScopeKeys);
  }
  return operationBarrierTargets("oa_pending_payment", [visibleScopeKey]);
}

async function waitForOaPendingPaymentBarrier(
  refresh: OaPendingPaymentReadModelRefresh | undefined,
  currentScopeKey: string,
) {
  try {
    await waitForOperationFreshness(oaPendingPaymentBarrierTargets(refresh, currentScopeKey));
    return true;
  } catch {
    return false;
  }
}

function readModelStatusTitle(status: string) {
  if (status === "stale") {
    return "OA 待付款核对数据不是最新";
  }
  if (status === "failed" || status === "unavailable") {
    return "OA 待付款核对数据暂不可用";
  }
  return "OA 待付款核对数据正在刷新";
}

function finiteCount(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeSummary(summary: OaPendingPaymentSummary | undefined, fallbackRowCount: number): OaPendingPaymentSummary {
  return {
    ...(summary ?? {}),
    rowCount: finiteCount(summary?.rowCount, fallbackRowCount),
  };
}

export default function OaPendingPaymentsPage() {
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const [query, setQuery] = useState<OaPendingPaymentQuery>(initialQuery);
  const [rows, setRows] = useState<OaPendingPaymentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<OaPendingPaymentSummary>({ rowCount: 0 });
  const [filterConfigs, setFilterConfigs] = useState<OaPendingPaymentFieldConfig[]>([]);
  const [filterOptions, setFilterOptions] = useState<Record<string, OaPendingPaymentFilterOption[]>>({});
  const [readModelStatus, setReadModelStatus] = useState("refreshing");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [selectedOaRowIds, setSelectedOaRowIds] = useState<Set<string>>(() => new Set());
  const [detailTarget, setDetailTarget] = useState<OaPendingPaymentDetailTarget | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [bankLinkDrawerOpen, setBankLinkDrawerOpen] = useState(false);
  const [writingBackOaRowIds, setWritingBackOaRowIds] = useState<Set<string>>(() => new Set());
  const [conditionalPollingEnabled, setConditionalPollingEnabled] = useState(false);
  const requestIdRef = useRef(0);
  const etagRef = useRef<string | null>(null);
  const selectedOaRowIdList = useMemo(() => [...selectedOaRowIds], [selectedOaRowIds]);

  const clearVisibleReadModel = useCallback(() => {
    setRows([]);
    setTotal(0);
    setSummary({ rowCount: 0 });
    setFilterConfigs([]);
    setFilterOptions({});
  }, []);

  const applyRowsPayload = useCallback((payload: OaPendingPaymentRowsResponse) => {
    const payloadTotal = finiteCount(payload.pagination?.total);
    setRows(payload.rows ?? []);
    setTotal(payloadTotal);
    setSummary(normalizeSummary(payload.summary, payloadTotal));
    setFilterConfigs(payload.filterConfig ?? []);
    setFilterOptions(payload.filterOptions ?? {});
    setReadModelStatus(readModelStatusFromPayloads(payload));
  }, []);

  const loadRows = useCallback(async (
    mode: "reset" | "refresh" | "conditional",
    signal?: AbortSignal,
  ) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === "reset") {
      setLoading(true);
    } else if (mode === "refresh") {
      setRefreshing(true);
    }
    if (mode !== "conditional") {
      setConditionalPollingEnabled(false);
      setError(null);
    }
    try {
      let result = await fetchOaPendingPaymentRows({
        ...query,
        etag: mode === "conditional" ? etagRef.current ?? undefined : undefined,
        signal,
      });
      if (signal?.aborted || requestId !== requestIdRef.current || result.status === "not_modified") {
        return;
      }
      etagRef.current = result.etag;
      const responseStatus = readModelStatusFromPayloads(result.payload);
      if (result.status === "refreshing" || !isReadModelFresh(responseStatus)) {
        clearVisibleReadModel();
        setReadModelStatus(responseStatus === "fresh" ? "refreshing" : responseStatus);
        const targets = result.payload.operationBarrierTargets ?? [];
        if (targets.length === 0) {
          setConditionalPollingEnabled(false);
          return;
        }
        try {
          await waitForOperationFreshness(targets, { signal });
        } catch {
          if (!signal?.aborted && requestId === requestIdRef.current) {
            setReadModelStatus("refreshing");
            setConditionalPollingEnabled(false);
          }
          return;
        }
        if (signal?.aborted || requestId !== requestIdRef.current) {
          return;
        }
        result = await fetchOaPendingPaymentRows({ ...query, signal });
        if (
          signal?.aborted
          || requestId !== requestIdRef.current
          || result.status === "not_modified"
          || result.status === "refreshing"
          || !isReadModelFresh(readModelStatusFromPayloads(result.payload))
        ) {
          clearVisibleReadModel();
          setReadModelStatus("refreshing");
          setConditionalPollingEnabled(false);
          return;
        }
        etagRef.current = result.etag;
      }
      applyRowsPayload(result.payload);
      setConditionalPollingEnabled(Boolean(result.etag));
    } catch (caught: unknown) {
      if (signal?.aborted || requestId !== requestIdRef.current) {
        return;
      }
      clearVisibleReadModel();
      setReadModelStatus("unavailable");
      setConditionalPollingEnabled(false);
      setError(caught instanceof Error ? caught.message : "OA 待付款核对加载失败。");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [applyRowsPayload, clearVisibleReadModel, query]);

  useEffect(() => {
    const controller = new AbortController();
    etagRef.current = null;
    setConditionalPollingEnabled(false);
    void loadRows("reset", controller.signal);
    return () => controller.abort();
  }, [loadRows]);

  useEffect(() => {
    if (!conditionalPollingEnabled) {
      return undefined;
    }
    let controller: AbortController | null = null;
    let inFlight = false;
    let disposed = false;

    const checkForFreshRows = async () => {
      if (disposed || inFlight || document.visibilityState !== "visible") {
        return;
      }
      inFlight = true;
      controller = new AbortController();
      try {
        await loadRows("conditional", controller.signal);
      } finally {
        inFlight = false;
        controller = null;
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") {
        controller?.abort();
        return;
      }
      void checkForFreshRows();
    };
    const intervalId = window.setInterval(() => {
      void checkForFreshRows();
    }, CONDITIONAL_REFRESH_INTERVAL_MS);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      disposed = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      controller?.abort();
    };
  }, [conditionalPollingEnabled, loadRows]);

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
    const synced = await waitForOaPendingPaymentBarrier(result.readModelRefresh, query.month || "all");
    setFeedback(synced ? message : "已关联支出流水，后台同步尚未完成，请稍后刷新。");
    setSelectedOaRowIds(new Set());
    setBankLinkDrawerOpen(false);
    if (synced) {
      loadRows("refresh");
    }
  }, [loadRows, query.month]);

  const handleWritebackPaid = useCallback(async (row: OaPendingPaymentRow) => {
    if (!canMutateData) {
      return;
    }
    const oaRowIds = rowOaIdsForWriteback(row);
    if (oaRowIds.length === 0) {
      return;
    }
    setActionError(null);
    setWritingBackOaRowIds((current) => new Set([...current, ...oaRowIds]));
    try {
      const result = await writebackOaPendingPaymentPaid({ oaRowIds });
      const synced = await waitForOaPendingPaymentBarrier(result.readModelRefresh, query.month || "all");
      if (synced) {
        setFeedback(writebackPaidFeedback(result));
        loadRows("refresh");
      } else {
        setFeedback("写回已提交，后台同步尚未完成，请稍后刷新。");
      }
    } catch (caught: unknown) {
      setActionError(caught instanceof Error ? caught.message : "写回失败。");
    } finally {
      setWritingBackOaRowIds((current) => {
        const next = new Set(current);
        oaRowIds.forEach((oaRowId) => next.delete(oaRowId));
        return next;
      });
    }
  }, [canMutateData, loadRows, query.month]);

  const loadExpensePendingInvoiceRules = useCallback(() => fetchPendingInvoiceRules("expense"), []);

  const saveExpensePendingInvoiceRules = useCallback(
    (payload: Parameters<typeof savePendingInvoiceRules>[0]) => savePendingInvoiceRules(payload, "expense"),
    [],
  );

  const handleRulesSaved = useCallback(() => {
    setFeedback("规则已保存。");
  }, []);

  const actions = useMemo(() => (
    <div className="oa-pending-payments-actions">
      <button
        aria-label="刷新 OA 待付款核对"
        className="oa-pending-payments-button"
        disabled={loading || refreshing}
        onClick={() => loadRows("refresh")}
        type="button"
      >
        刷新
      </button>
      {query.viewMode === "in_progress" ? (
        <button
          aria-label="关联支出流水"
          onClick={() => setBankLinkDrawerOpen(true)}
          className="oa-pending-payments-button oa-pending-payments-button--primary"
          disabled={!canMutateData || selectedOaRowIds.size === 0}
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
  ), [canMutateData, loadRows, loading, query.viewMode, refreshing, selectedOaRowIds.size]);
  const visibleError = error ?? actionError;
  const isEmpty = !loading && !refreshing && !visibleError && rows.length === 0;
  const showReadModelState = isEmpty && !isReadModelFresh(readModelStatus);
  const completedCountLabel = formatViewCount(summary.viewCounts?.completed);
  const inProgressCountLabel = formatViewCount(summary.viewCounts?.in_progress);
  const titleAccessory = canAdminAccess ? (
    <OaPendingPaymentAuditIcon
      readModelStatus={readModelStatus}
      scopeKey={query.month || "all"}
    />
  ) : null;

  return (
    <>
      <div className="oa-pending-payments-page" data-testid="oa-pending-payments-page">
        <PageScaffold title="OA 待付款核对" titleAccessory={titleAccessory} actions={actions}>
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
                  <div className="oa-pending-payments-field">
                    <span id="oa-pending-payments-month-label">月份</span>
                    <span
                      aria-labelledby="oa-pending-payments-month-label"
                      className="oa-pending-payments-month-picker"
                      role="group"
                    >
                      <button
                        aria-pressed={query.month === ""}
                        className={query.month === "" ? "oa-pending-payments-month-picker__all oa-pending-payments-month-picker__all--active" : "oa-pending-payments-month-picker__all"}
                        onClick={() => setQuery((current) => ({ ...current, page: 1, month: "" }))}
                        type="button"
                      >
                        全部
                      </button>
                      <input
                        aria-label="选择月份"
                        type="month"
                        value={query.month}
                        onChange={(event) => setQuery((current) => ({ ...current, page: 1, month: event.target.value }))}
                      />
                    </span>
                  </div>
                </div>
              )}
            />
            {visibleError ? (
              <div className="oa-pending-payments-alert" role="alert">
                {visibleError}
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
                {!canMutateData ? (
                  <StatePanel compact tone="warning">
                    当前账号仅支持查看和导出，不能自动写回 OA 或关联支出流水。
                  </StatePanel>
                ) : null}
                {showReadModelState ? (
                  <StatePanel tone={readModelStatus === "refreshing" ? "loading" : "warning"} title={readModelStatusTitle(readModelStatus)} compact>
                    当前数据仍在刷新或等待后台任务完成，请稍后重试。
                  </StatePanel>
                ) : null}
                {isEmpty && !showReadModelState ? <StatePanel tone="empty" compact>当前条件下暂无记录。</StatePanel> : null}
                <OaPendingPaymentsTable
                  rows={rows}
                  page={query.page}
                  pageSize={query.pageSize}
                  total={total}
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
                  selectedOaRowIds={selectedOaRowIds}
                  onToggleOaSelection={canMutateData && query.viewMode === "in_progress" ? handleToggleOaSelection : undefined}
                  onWritebackPaid={canMutateData ? (row) => void handleWritebackPaid(row) : undefined}
                  writingBackOaRowIds={writingBackOaRowIds}
                  emptyStateMessage={
                    error
                      ? "OA 待付款核对加载失败，请点击刷新重试。"
                      : refreshing
                        ? "OA 待付款核对数据正在刷新，请稍候。"
                        : undefined
                  }
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
        layout="table"
        variant="persistent"
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
        open={canMutateData && bankLinkDrawerOpen}
        selectedOaRowIds={selectedOaRowIdList}
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

function writebackPaidFeedback(result: WritebackOaPendingPaymentPaidResponse): string {
  const written = Number(result.writebackCount ?? 0);
  if (written > 0) {
    return `已写回 ${written} 条 OA。`;
  }
  return "OA 已经写回。";
}

function linkBankSuccessMessage(result: LinkOaPendingPaymentBankTransactionsResponse): string {
  if (
    result.autoWriteback?.code === "written"
    || result.oaPaymentWriteback?.code === "written"
    || (result.oaPaymentWritebacks ?? []).some((item) => item.code === "written")
  ) {
    return "已关联支出流水并写回 OA，等待核对表刷新。";
  }
  return "已关联支出流水，等待核对表刷新。";
}

function selectableOaRowIds(row: OaPendingPaymentRow): string[] {
  return rowOaIdsForWriteback(row);
}

function rowOaIdsForWriteback(row: OaPendingPaymentRow): string[] {
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
  onLinked: (message: string, result: LinkOaPendingPaymentBankTransactionsResponse) => Promise<void> | void;
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const [relationStatus, setRelationStatus] = useState<OaPendingPaymentBankCandidateRelationStatus>("all");
  const [keyword, setKeyword] = useState("");
  const [rows, setRows] = useState<OaPendingPaymentBankCandidate[]>([]);
  const [selectedBankIds, setSelectedBankIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageCount = Math.max(1, Math.ceil(total / BANK_CANDIDATE_PAGE_SIZE));

  const loadCandidates = useCallback((signal?: AbortSignal) => {
    if (!open) {
      return;
    }
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
  }, [keyword, onError, open, page, relationStatus, selectedOaRowIds]);

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

  const searchCandidates = () => {
    if (page === 1) {
      loadCandidates();
    } else {
      setPage(1);
    }
  };

  const submit = () => {
    if (selectedOaRowIds.length === 0 || selectedBankIds.size === 0) {
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
        await onLinked(linkBankSuccessMessage(result), result);
      } catch (caught: unknown) {
        onError(caught instanceof Error ? caught.message : "关联支出流水失败。");
      } finally {
        setSubmitting(false);
      }
    })();
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
              onClick={() => {
                setRelationStatus(status);
                setPage(1);
              }}
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
            onChange={(event) => {
              setKeyword(event.target.value);
              setPage(1);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                searchCandidates();
              }
            }}
          />
          <button onClick={searchCandidates} type="button">查询</button>
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
        <div className="oa-pending-payments-bank-drawer__pagination">
          <span>第 {page} / {pageCount} 页</span>
          <div className="oa-pending-payments-bank-drawer__pagination-actions">
            <button
              aria-label="上一页"
              disabled={loading || page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              <ChevronLeft aria-hidden="true" size={18} />
            </button>
            <button
              aria-label="下一页"
              disabled={loading || page >= pageCount}
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
              type="button"
            >
              <ChevronRight aria-hidden="true" size={18} />
            </button>
          </div>
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
