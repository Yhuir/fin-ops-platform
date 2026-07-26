import { useCallback, useEffect, useMemo, useState, type FocusEvent, type MouseEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, RefreshCw, Search, X } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import {
  fetchBatchAccounting,
  submitBatchAccounting,
  withdrawBatchAccounting,
} from "../features/batchAccounting/api";
import type {
  BatchAccountingBankRow,
  BatchAccountingBucket,
  BatchAccountingAmountCheck,
  BatchAccountingOaRow,
  BatchAccountingResponse,
} from "../features/batchAccounting/types";

const EMPTY_PAYLOAD: BatchAccountingResponse = {
  summary: {
    unsubmittedCount: 0,
    submittedCount: 0,
  },
  bankRows: [],
  oaRows: [],
  relationsByBankRowId: {},
  pagination: {},
};

const BATCH_ACCOUNTING_PAGE_SIZE = 200;

function currentYear() {
  return String(new Date().getFullYear());
}

function isValidYear(value: string) {
  return /^20\d{2}$/.test(value);
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
}

function parseMoneyCents(value: string | number | null | undefined) {
  const numeric = Number(String(value ?? "0").replace(/,/g, "").trim());
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.round(numeric * 100);
}

function formatMoney(value: string | number | null | undefined) {
  const numeric = Number(String(value ?? "0").replace(/,/g, "").trim());
  if (!Number.isFinite(numeric)) {
    return String(value ?? "0.00");
  }
  return numeric.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatCents(cents: number) {
  return (cents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatTradeTime(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  const isoMatch = text.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/);
  if (!isoMatch) {
    return text;
  }
  const time = isoMatch[2].length === 5 ? `${isoMatch[2]}:00` : isoMatch[2];
  return `${isoMatch[1]} ${time}`;
}

function accountLabel(row: BatchAccountingBankRow) {
  const bankName = row.bankName || "多账户";
  return row.accountLast4 ? `${bankName} ${row.accountLast4}` : bankName;
}

function pageRange(page: number, pageSize: number, total: number) {
  if (total <= 0) {
    return "0-0 / 0";
  }
  const start = (page - 1) * pageSize + 1;
  if (start > total) {
    return `0-0 / ${total}`;
  }
  const end = Math.min(total, page * pageSize);
  return `${start}-${end} / ${total}`;
}

function PageControls({
  disabled,
  label,
  onNext,
  onPrevious,
  page,
  pageSize,
  total,
}: {
  disabled?: boolean;
  label: string;
  onNext: () => void;
  onPrevious: () => void;
  page: number;
  pageSize: number;
  total: number;
}) {
  const pageCount = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  return (
    <div aria-label={label} className="batch-accounting-pagination" role="group">
      <span className="batch-accounting-pagination__summary">{pageRange(page, pageSize, total)}</span>
      <button
        aria-label={`${label}上一页`}
        className="batch-accounting-pagination__button"
        disabled={disabled || page <= 1}
        onClick={onPrevious}
        title={`${label}上一页`}
        type="button"
      >
        <ChevronLeft aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
      <button
        aria-label={`${label}下一页`}
        className="batch-accounting-pagination__button"
        disabled={disabled || page >= pageCount}
        onClick={onNext}
        title={`${label}下一页`}
        type="button"
      >
        <ChevronRight aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
    </div>
  );
}

function mutationErrorMessage(caught: unknown, fallback: string) {
  return caught instanceof Error ? caught.message : fallback;
}

function mutationReloadFailedMessage(message: string | undefined, fallback: string) {
  return `${message || fallback} 最新列表加载失败，请手动刷新。`;
}

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function ExpandableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const shouldOfferToggle = text.length > 18;
  return (
    <span className="batch-accounting-expandable">
      <span
        className={cx("batch-accounting-expandable__text", !expanded && "batch-accounting-expandable__text--clamped")}
        title={text}
      >
        {text || "-"}
      </span>
      {shouldOfferToggle ? (
        <button className="batch-accounting-expandable__toggle" onClick={() => setExpanded((current) => !current)} type="button">
          {expanded ? "收起" : "展开"}
        </button>
      ) : null}
    </span>
  );
}

function AmountMismatchWarning({
  amountCheck,
  note,
}: {
  amountCheck: BatchAccountingAmountCheck;
  note: string;
}) {
  const [open, setOpen] = useState(false);
  const showMismatchDetails = () => setOpen(true);
  const hideMismatchDetails = (event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>) => {
    if (event.type === "mouseleave" || event.type === "blur") {
      setOpen(false);
    }
  };

  return (
    <span className="batch-accounting-mismatch-warning">
      <button
        aria-label="查看金额不一致差额说明"
        aria-describedby={open ? "batch-accounting-mismatch-tooltip" : undefined}
        className="batch-accounting-mismatch-warning__trigger"
        onBlur={hideMismatchDetails}
        onClick={showMismatchDetails}
        onFocus={showMismatchDetails}
        onMouseEnter={showMismatchDetails}
        onMouseLeave={hideMismatchDetails}
        onTouchStart={showMismatchDetails}
        type="button"
      >
        <AlertTriangle aria-hidden="true" size={16} strokeWidth={2.3} />
      </button>
      {open ? (
        <span className="batch-accounting-mismatch-warning__tooltip" id="batch-accounting-mismatch-tooltip" role="tooltip">
          <span>{`银行流水金额：${formatMoney(amountCheck.bankAmount)}`}</span>
          <span>{`OA合计：${formatMoney(amountCheck.oaAmount)}`}</span>
          <span>{`差额：${formatMoney(amountCheck.amountDelta)}`}</span>
          <span>{`差额说明：${note || "-"}`}</span>
        </span>
      ) : null}
    </span>
  );
}

export default function BatchAccountingPage() {
  const { active, activationGeneration } = useOptionalPageActivation("batch-accounting");
  const { runOperation } = useGlobalOperationOverlay();
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const [bankYear, setBankYear] = useState(currentYear);
  const [bucket, setBucket] = useState<BatchAccountingBucket>("unsubmitted");
  const [payload, setPayload] = useState<BatchAccountingResponse>(EMPTY_PAYLOAD);
  const [selectedBankRowId, setSelectedBankRowId] = useState<string | null>(null);
  const [selectedOaRowIds, setSelectedOaRowIds] = useState<Set<string>>(() => new Set());
  const [bankRowsById, setBankRowsById] = useState<Record<string, BatchAccountingBankRow>>({});
  const [oaRowsById, setOaRowsById] = useState<Record<string, BatchAccountingOaRow>>({});
  const [bankPage, setBankPage] = useState(1);
  const [oaPage, setOaPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [oaSearchQuery, setOaSearchQuery] = useState("");
  const [differenceNote, setDifferenceNote] = useState("");
  const [feedback, setFeedback] = useState<{ severity: "success" | "error"; message: string } | null>(null);

  const selectedBankRow = useMemo(
    () => (
      payload.bankRows.find((row) => row.id === selectedBankRowId)
      ?? (selectedBankRowId ? bankRowsById[selectedBankRowId] : undefined)
      ?? null
    ),
    [bankRowsById, payload.bankRows, selectedBankRowId],
  );

  const selectedRelationBucket = selectedBankRow
    ? payload.relationsByBankRowId[selectedBankRow.id]
    : undefined;
  const selectedRelation = selectedRelationBucket?.relation;
  const selectedRelationAmountCheck = selectedRelation?.amountCheck;

  const sourceOaRows = useMemo(() => {
    if (bucket === "unsubmitted") {
      return payload.oaRows;
    }
    if (!selectedBankRow) {
      return [];
    }
    return payload.relationsByBankRowId[selectedBankRow.id]?.oaRows ?? payload.oaRows;
  }, [bucket, payload.oaRows, payload.relationsByBankRowId, selectedBankRow]);

  const visibleOaRows = sourceOaRows;

  const selectedOaRows = useMemo(() => {
    if (bucket === "submitted") {
      return selectedRelationBucket?.oaRows ?? [];
    }
    return Array.from(selectedOaRowIds)
      .map((rowId) => sourceOaRows.find((row) => row.id === rowId) ?? oaRowsById[rowId])
      .filter((row): row is BatchAccountingOaRow => Boolean(row));
  }, [bucket, oaRowsById, selectedOaRowIds, selectedRelationBucket, sourceOaRows]);

  const bankAmountCents = selectedBankRow ? parseMoneyCents(selectedBankRow.amount) : 0;
  const selectedOaTotalCents = selectedOaRows.reduce((total, row) => total + parseMoneyCents(row.amount), 0);
  const differenceCents = bankAmountCents - selectedOaTotalCents;
  const isAmountMismatch = bucket === "unsubmitted"
    && Boolean(selectedBankRow)
    && selectedOaRows.length > 0
    && differenceCents !== 0;
  const submittedAmountMismatch = bucket === "submitted" && selectedRelationAmountCheck?.status === "mismatch";
  const canSubmit = Boolean(selectedBankRow)
    && canMutateData
    && selectedOaRows.length > 0
    && isValidYear(bankYear)
    && !mutating
    && (differenceCents === 0 || differenceNote.trim().length > 0);
  const canWithdraw = Boolean(selectedBankRow?.relationId) && canMutateData && !mutating;
  const bankPagination = payload.pagination.bankRows ?? {
    page: bankPage,
    pageSize: BATCH_ACCOUNTING_PAGE_SIZE,
    total: payload.bankRows.length,
  };
  const oaPagination = payload.pagination.oaRows ?? {
    page: oaPage,
    pageSize: BATCH_ACCOUNTING_PAGE_SIZE,
    total: bucket === "unsubmitted" ? payload.oaRows.length : sourceOaRows.length,
  };

  const applyBatchAccountingPayload = useCallback((nextPayload: BatchAccountingResponse) => {
    setPayload(nextPayload);
    setBankRowsById((current) => ({
      ...current,
      ...Object.fromEntries(nextPayload.bankRows.map((row) => [row.id, row])),
    }));
    const relationOaRows = Object.values(nextPayload.relationsByBankRowId).flatMap((relation) => relation.oaRows);
    setOaRowsById((current) => ({
      ...current,
      ...Object.fromEntries([...nextPayload.oaRows, ...relationOaRows].map((row) => [row.id, row])),
    }));
    setSelectedBankRowId((current) => (
      current
        ? current
        : nextPayload.bankRows[0]?.id ?? null
    ));
  }, []);

  const reloadDataAfterMutation = useCallback(async () => {
    if (!isValidYear(bankYear)) {
      return null;
    }
    const nextPayload = await fetchBatchAccounting({
      bankYear,
      bucket,
      bankPage,
      bankPageSize: BATCH_ACCOUNTING_PAGE_SIZE,
      oaPage: bucket === "unsubmitted" ? oaPage : undefined,
      oaPageSize: bucket === "unsubmitted" ? BATCH_ACCOUNTING_PAGE_SIZE : undefined,
      oaSearch: bucket === "unsubmitted" ? oaSearchQuery : undefined,
    });
    applyBatchAccountingPayload(nextPayload);
    return nextPayload;
  }, [applyBatchAccountingPayload, bankPage, bankYear, bucket, oaPage, oaSearchQuery]);

  const loadData = useCallback((signal?: AbortSignal) => {
    if (!isValidYear(bankYear)) {
      return;
    }
    setLoading(true);
    setError(null);
    fetchBatchAccounting({
      bankYear,
      bucket,
      bankPage,
      bankPageSize: BATCH_ACCOUNTING_PAGE_SIZE,
      oaPage: bucket === "unsubmitted" ? oaPage : undefined,
      oaPageSize: bucket === "unsubmitted" ? BATCH_ACCOUNTING_PAGE_SIZE : undefined,
      oaSearch: bucket === "unsubmitted" ? oaSearchQuery : undefined,
      signal,
    })
      .then(applyBatchAccountingPayload)
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setPayload(EMPTY_PAYLOAD);
        setError(caught instanceof Error ? caught.message : "批量账务数据加载失败");
      })
      .finally(() => setLoading(false));
  }, [applyBatchAccountingPayload, bankPage, bankYear, bucket, oaPage, oaSearchQuery]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadData]);

  useEffect(() => {
    setSelectedBankRowId((current) => {
      if (current && payload.bankRows.some((row) => row.id === current)) {
        return current;
      }
      const nextBankRowId = payload.bankRows[0]?.id ?? null;
      if (current !== nextBankRowId) {
        setSelectedOaRowIds(new Set());
        setDifferenceNote("");
      }
      return nextBankRowId;
    });
  }, [payload.bankRows]);

  useEffect(() => {
    if (!feedback) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  const handleBucketChange = (nextBucket: BatchAccountingBucket) => {
    if (nextBucket === bucket) {
      return;
    }
    setBucket(nextBucket);
    setBankPage(1);
    setOaPage(1);
    setSelectedBankRowId(null);
    setSelectedOaRowIds(new Set());
    setDifferenceNote("");
  };

  const handleBankYearChange = (nextYear: string) => {
    setBankYear(nextYear);
    setBankPage(1);
    setSelectedBankRowId(null);
    setSelectedOaRowIds(new Set());
    setDifferenceNote("");
  };

  const handleSelectBankRow = (row: BatchAccountingBankRow) => {
    setBankRowsById((current) => ({ ...current, [row.id]: row }));
    setSelectedBankRowId(row.id);
    setSelectedOaRowIds(new Set());
    setDifferenceNote("");
  };

  const handleOaToggle = (row: BatchAccountingOaRow, checked: boolean) => {
    setOaRowsById((current) => ({ ...current, [row.id]: row }));
    setDifferenceNote("");
    setSelectedOaRowIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(row.id);
      } else {
        next.delete(row.id);
      }
      return next;
    });
  };

  const handleBankPageChange = (nextPage: number) => {
    setBankPage(Math.max(1, nextPage));
    setSelectedBankRowId(null);
    setSelectedOaRowIds(new Set());
    setDifferenceNote("");
  };

  const handleOaPageChange = (nextPage: number) => {
    setOaPage(Math.max(1, nextPage));
  };

  const handleMutationComplete = (fallbackMessage: string, result: { affectedMonths?: string[]; message?: string }) => {
    setFeedback({ severity: "success", message: result.message || fallbackMessage });
  };

  const handleSubmit = async () => {
    if (!selectedBankRow || !canSubmit) {
      return;
    }
    const result = await runOperation({
      loadingMessage: "正在保存批量账务关联...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBatchAccounting({
            bankYear,
            bankRowId: selectedBankRow.id,
            oaRowIds: selectedOaRows.map((row) => row.id),
            expectedVersion: selectedBankRow.version,
            note: isAmountMismatch ? differenceNote : "",
          });
          setMessage("正在加载批量账务最新数据...");
          try {
            await reloadDataAfterMutation();
          } catch {
            return {
              ...submitResult,
              message: mutationReloadFailedMessage(submitResult.message, "已关联批量账务流水与 OA。"),
            };
          }
          return submitResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "关联OA项与流水失败"),
    });
    if (result.status === "success") {
      handleMutationComplete("已关联批量账务流水与 OA。", result.value);
    } else {
      setFeedback({ severity: "error", message: mutationErrorMessage(result.error, "关联OA项与流水失败") });
    }
  };

  const handleConfirmWithdraw = async () => {
    if (!selectedBankRow?.relationId || !withdrawReason.trim() || mutating) {
      return;
    }
    const relationId = selectedBankRow.relationId;
    const expectedVersion = selectedBankRow.version;
    const reason = withdrawReason.trim();
    const result = await runOperation({
      loadingMessage: "正在撤回批量账务关联...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const withdrawResult = await withdrawBatchAccounting({
            relationId,
            expectedVersion,
            reason,
          });
          setWithdrawOpen(false);
          setWithdrawReason("");
          setMessage("正在加载批量账务最新数据...");
          try {
            await reloadDataAfterMutation();
          } catch {
            return {
              ...withdrawResult,
              message: mutationReloadFailedMessage(withdrawResult.message, "已撤回批量账务关联。"),
            };
          }
          return withdrawResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "撤回关联失败"),
    });
    if (result.status === "success") {
      handleMutationComplete("已撤回批量账务关联。", result.value);
    } else {
      setFeedback({ severity: "error", message: mutationErrorMessage(result.error, "撤回关联失败") });
    }
  };

  const titleAccessory = canAdminAccess ? (
    <PageBusinessAuditIcon
      ariaLabel="Audit 日常报销批量账务管理"
      pageKey="batch-accounting"
      label="日常报销批量账务管理"
    />
  ) : null;

  return (
    <PageScaffold
      title="日常报销批量账务管理"
      titleAccessory={titleAccessory}
      actions={(
        <button
          className="batch-accounting-button batch-accounting-button--secondary"
          disabled={loading}
          onClick={() => loadData()}
          type="button"
        >
          <RefreshCw aria-hidden="true" size={16} strokeWidth={2.2} />
          刷新
        </button>
      )}
    >
      <div aria-label="批量账务筛选" className="batch-accounting-filter" role="region">
        <div aria-label="批量账务状态" className="batch-accounting-segment" role="group">
          <button
            aria-pressed={bucket === "unsubmitted"}
            className={cx("batch-accounting-segment__button", bucket === "unsubmitted" && "batch-accounting-segment__button--active")}
            onClick={() => handleBucketChange("unsubmitted")}
            type="button"
          >
            未提交 {payload.summary.unsubmittedCount}
          </button>
          <button
            aria-pressed={bucket === "submitted"}
            className={cx("batch-accounting-segment__button", bucket === "submitted" && "batch-accounting-segment__button--active")}
            onClick={() => handleBucketChange("submitted")}
            type="button"
          >
            已提交 {payload.summary.submittedCount}
          </button>
        </div>
      </div>

      {error ? <StatePanel tone="error" title={error} /> : null}
      {!canMutateData ? (
        <StatePanel compact tone="warning">
          当前账号仅支持查看和导出，不能提交或撤回批量账务关联。
        </StatePanel>
      ) : null}

      <div className="batch-accounting-layout">
        <section aria-label="批量账务流水" className="batch-accounting-bank-panel" role="region">
          <header className="batch-accounting-bank-panel__header">
            <div>
              <h2 className="batch-accounting-bank-panel__title">批量账务流水</h2>
              <p className="batch-accounting-bank-panel__subtitle">对方户名精确匹配批量账务集中处理</p>
            </div>
            <label className="batch-accounting-field batch-accounting-field--year" htmlFor="batch-accounting-bank-year">
              <span>流水年份</span>
              <input
                id="batch-accounting-bank-year"
                max={2100}
                min={2000}
                onChange={(event) => handleBankYearChange(event.target.value)}
                type="number"
                value={bankYear}
              />
            </label>
            <PageControls
              disabled={loading}
              label="批量账务流水分页"
              onNext={() => handleBankPageChange(bankPagination.page + 1)}
              onPrevious={() => handleBankPageChange(bankPagination.page - 1)}
              page={bankPagination.page}
              pageSize={bankPagination.pageSize}
              total={bankPagination.total}
            />
          </header>
          {loading ? (
            <div className="batch-accounting-bank-panel__state">
              <StatePanel compact tone="loading" title="正在加载流水" />
            </div>
          ) : null}
          {!loading && !error && payload.bankRows.length === 0 ? (
            <div className="batch-accounting-bank-panel__state">
              <StatePanel compact tone="empty" title="当前年份暂无批量账务流水" />
            </div>
          ) : null}
          <div className="batch-accounting-bank-list">
            {payload.bankRows.map((row) => {
              const selected = row.id === selectedBankRowId;
              const tradeTimeLabel = formatTradeTime(row.tradeTime);
              return (
                <button
                  aria-label={`批量账务集中处理 ${formatMoney(row.amount)} ${tradeTimeLabel} ${row.directionLabel || "支出"} ${accountLabel(row)}`}
                  aria-pressed={selected}
                  className={cx("batch-accounting-bank-row", selected && "batch-accounting-bank-row--selected")}
                  key={row.id}
                  onClick={() => handleSelectBankRow(row)}
                  type="button"
                >
                  <span className="batch-accounting-bank-row__main">
                    <span className="batch-accounting-bank-row__title">批量账务集中处理</span>
                    <span className="batch-accounting-bank-row__amount">{formatMoney(row.amount)}</span>
                  </span>
                  <span className="batch-accounting-bank-row__tags">
                    <span className="batch-accounting-tag batch-accounting-tag--meta">{tradeTimeLabel}</span>
                    <span className="batch-accounting-tag batch-accounting-tag--direction">{row.directionLabel || "支出"}</span>
                    <span className="batch-accounting-tag batch-accounting-tag--meta">{accountLabel(row)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section aria-label={bucket === "unsubmitted" ? "可关联OA项" : "已关联OA项"} className="batch-accounting-oa-panel">
          <div className="batch-accounting-oa-panel__toolbar">
            <div className="batch-accounting-oa-panel__controls">
              <div className="batch-accounting-summary">
                <span className="batch-accounting-summary-tag">{`银行流水金额 ${formatCents(bankAmountCents)}`}</span>
                <span className="batch-accounting-summary__warning-slot">
                  {submittedAmountMismatch && selectedRelationAmountCheck ? (
                    <AmountMismatchWarning
                      amountCheck={selectedRelationAmountCheck}
                      note={selectedRelation?.note ?? ""}
                    />
                  ) : null}
                </span>
                <span className="batch-accounting-summary-tag">{`已选 OA ${selectedOaRows.length} 项`}</span>
                <span className="batch-accounting-summary-tag">{`已选 OA 金额 ${formatCents(selectedOaTotalCents)}`}</span>
                <span className={cx("batch-accounting-summary-tag", differenceCents === 0 ? "batch-accounting-summary-tag--success" : "batch-accounting-summary-tag--warning")}>
                  {`差额 ${formatCents(differenceCents)}`}
                </span>
                {submittedAmountMismatch ? (
                  <span className="batch-accounting-summary-tag batch-accounting-summary-tag--warning">金额不一致</span>
                ) : null}
              </div>
              {isAmountMismatch ? (
                <div className="batch-accounting-field batch-accounting-field--note">
                  <label htmlFor="batch-accounting-difference-note">差额说明</label>
                  <input
                    aria-describedby="batch-accounting-difference-note-help"
                    aria-required="true"
                    id="batch-accounting-difference-note"
                    onChange={(event) => setDifferenceNote(event.target.value)}
                    value={differenceNote}
                  />
                  <small id="batch-accounting-difference-note-help">金额不一致时必须填写，提交后视为人工差额闭环。</small>
                </div>
              ) : null}
              <div className="batch-accounting-field batch-accounting-field--search">
                <label htmlFor="batch-accounting-oa-search">搜索OA内容</label>
                <div className="batch-accounting-search">
                  <Search aria-hidden="true" size={15} strokeWidth={2.2} />
                  <input
                    id="batch-accounting-oa-search"
                    onChange={(event) => {
                      setOaSearchQuery(event.target.value);
                      setOaPage(1);
                    }}
                    placeholder="申请人、项目、金额、事由"
                    type="search"
                    value={oaSearchQuery}
                  />
                  {oaSearchQuery ? (
                    <button
                      aria-label="清空搜索"
                      className="batch-accounting-search__clear"
                      onClick={() => {
                        setOaSearchQuery("");
                        setOaPage(1);
                      }}
                      type="button"
                    >
                      <X aria-hidden="true" size={14} strokeWidth={2.4} />
                    </button>
                  ) : null}
                </div>
              </div>
              {bucket === "unsubmitted" ? (
                <PageControls
                  disabled={loading}
                  label="可关联OA项分页"
                  onNext={() => handleOaPageChange(oaPagination.page + 1)}
                  onPrevious={() => handleOaPageChange(oaPagination.page - 1)}
                  page={oaPagination.page}
                  pageSize={oaPagination.pageSize}
                  total={oaPagination.total}
                />
              ) : null}
            </div>
            {bucket === "unsubmitted" ? (
              <button
                className="batch-accounting-button batch-accounting-button--primary"
                disabled={!canSubmit}
                onClick={handleSubmit}
                type="button"
              >
                关联OA项与流水
              </button>
            ) : (
              <button
                className="batch-accounting-button batch-accounting-button--primary"
                disabled={!canWithdraw}
                onClick={() => setWithdrawOpen(true)}
                type="button"
              >
                撤回关联
              </button>
            )}
          </div>
          <div className="batch-accounting-oa-panel__divider" />
          <div className="batch-accounting-oa-table-wrap">
            <table className="batch-accounting-oa-table" aria-label={bucket === "unsubmitted" ? "可关联OA项" : "已关联OA项"}>
              <thead>
                <tr>
                  {bucket === "unsubmitted" ? <th className="batch-accounting-oa-table__check" scope="col">选择</th> : null}
                  <th scope="col">申请人</th>
                  <th scope="col">项目名称</th>
                  <th className="batch-accounting-oa-table__amount" scope="col">金额</th>
                  <th scope="col">申请事由</th>
                </tr>
              </thead>
              <tbody>
                {visibleOaRows.map((row) => (
                  <tr className={cx(selectedOaRowIds.has(row.id) && "batch-accounting-oa-table__row--selected")} key={row.id}>
                    {bucket === "unsubmitted" ? (
                      <td className="batch-accounting-oa-table__check">
                        <input
                          aria-label={`选择 ${row.applicant} ${row.applyTime}`}
                          className="batch-accounting-checkbox"
                          checked={selectedOaRowIds.has(row.id)}
                          onChange={(event) => handleOaToggle(row, event.target.checked)}
                          type="checkbox"
                        />
                      </td>
                    ) : null}
                    <td className="batch-accounting-oa-table__identity">
                      <span className="batch-accounting-oa-table__applicant">{row.applicant || "-"}</span>
                      <span className="batch-accounting-tag batch-accounting-tag--meta">{row.applyTime || "-"}</span>
                    </td>
                    <td className="batch-accounting-oa-table__description">
                      <ExpandableText text={row.projectName} />
                    </td>
                    <td className="batch-accounting-oa-table__amount">
                      {formatMoney(row.amount)}
                    </td>
                    <td className="batch-accounting-oa-table__description">
                      <ExpandableText text={row.reason} />
                    </td>
                  </tr>
                ))}
                {visibleOaRows.length === 0 ? (
                  <tr>
                    <td className="batch-accounting-oa-table__empty" colSpan={bucket === "unsubmitted" ? 5 : 4}>
                      <StatePanel compact tone="empty" title={bucket === "unsubmitted" ? "暂无可关联 OA" : "暂无已关联 OA"} />
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <AppDialog
        actions={(
          <>
            <button className="batch-accounting-button" onClick={() => setWithdrawOpen(false)} type="button">
              取消
            </button>
            <button
              className="batch-accounting-button batch-accounting-button--primary"
              disabled={!withdrawReason.trim() || mutating}
              onClick={handleConfirmWithdraw}
              type="button"
            >
              确认撤回
            </button>
          </>
        )}
        maxWidth="sm"
        onClose={() => setWithdrawOpen(false)}
        open={withdrawOpen}
        title="撤回关联"
      >
        <label className="batch-accounting-field batch-accounting-field--withdraw" htmlFor="batch-accounting-withdraw-reason">
          <span>撤回原因</span>
          <textarea
            autoFocus
            id="batch-accounting-withdraw-reason"
            rows={3}
            onChange={(event) => setWithdrawReason(event.target.value)}
            value={withdrawReason}
          />
        </label>
      </AppDialog>

      {feedback ? (
        <div
          className={cx("batch-accounting-feedback", `batch-accounting-feedback--${feedback.severity}`)}
          role="alert"
        >
          <span>{feedback.message}</span>
          <button
            aria-label="关闭消息"
            className="batch-accounting-feedback__close"
            onClick={() => setFeedback(null)}
            type="button"
          >
            <X aria-hidden="true" size={14} strokeWidth={2.4} />
          </button>
        </div>
      ) : null}
    </PageScaffold>
  );
}
