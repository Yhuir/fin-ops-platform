import { useCallback, useEffect, useMemo, useState, type FocusEvent, type MouseEvent } from "react";
import { AlertTriangle, RefreshCw, Search, X } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
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
};

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

function accountLabel(row: BatchAccountingBankRow) {
  const bankName = row.bankName || "多账户";
  return row.accountLast4 ? `${bankName} ${row.accountLast4}` : bankName;
}

function normalizeSearchText(value: string | number | null | undefined) {
  return String(value ?? "").replace(/\s+/g, "").toLowerCase();
}

function oaSearchText(row: BatchAccountingOaRow) {
  return normalizeSearchText([
    row.id,
    row.applicant,
    row.applyTime,
    row.projectName,
    row.amount,
    formatMoney(row.amount),
    row.reason,
    ...row.linkedInvoiceRowIds,
  ].join(" "));
}

function mutationEventDetail(result: { affectedMonths?: string[] }) {
  return { affectedMonths: result.affectedMonths ?? [] };
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
  const [bankYear, setBankYear] = useState(currentYear);
  const [oaYear, setOaYear] = useState(currentYear);
  const [bucket, setBucket] = useState<BatchAccountingBucket>("unsubmitted");
  const [payload, setPayload] = useState<BatchAccountingResponse>(EMPTY_PAYLOAD);
  const [selectedBankRowId, setSelectedBankRowId] = useState<string | null>(null);
  const [selectedOaRowIds, setSelectedOaRowIds] = useState<Set<string>>(() => new Set());
  const [bankRowsById, setBankRowsById] = useState<Record<string, BatchAccountingBankRow>>({});
  const [oaRowsById, setOaRowsById] = useState<Record<string, BatchAccountingOaRow>>({});
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

  const normalizedOaSearchQuery = normalizeSearchText(oaSearchQuery);
  const visibleOaRows = useMemo(() => {
    if (!normalizedOaSearchQuery) {
      return sourceOaRows;
    }
    return sourceOaRows.filter((row) => oaSearchText(row).includes(normalizedOaSearchQuery));
  }, [normalizedOaSearchQuery, sourceOaRows]);

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
    && selectedOaRows.length > 0
    && isValidYear(bankYear)
    && isValidYear(oaYear)
    && !mutating
    && (differenceCents === 0 || differenceNote.trim().length > 0);
  const canWithdraw = Boolean(selectedBankRow?.relationId) && !mutating;

  const loadData = useCallback((signal?: AbortSignal) => {
    if (!isValidYear(bankYear) || !isValidYear(oaYear)) {
      return;
    }
    setLoading(true);
    setError(null);
    fetchBatchAccounting({ bankYear, oaYear, bucket, signal })
      .then((nextPayload) => {
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
      })
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setPayload(EMPTY_PAYLOAD);
        setError(caught instanceof Error ? caught.message : "批量账务数据加载失败");
      })
      .finally(() => setLoading(false));
  }, [bankYear, bucket, oaYear]);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

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

  const handleMutationComplete = (fallbackMessage: string, result: { affectedMonths?: string[]; message?: string }) => {
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      ...mutationEventDetail(result),
      source: "batch_accounting_mutation",
    });
    setFeedback({ severity: "success", message: result.message || fallbackMessage });
    loadData();
  };

  const handleSubmit = async () => {
    if (!selectedBankRow || !canSubmit) {
      return;
    }
    setMutating(true);
    try {
      const result = await submitBatchAccounting({
        bankYear,
        oaYear,
        bankRowId: selectedBankRow.id,
        oaRowIds: selectedOaRows.map((row) => row.id),
        expectedVersion: selectedBankRow.version,
        note: isAmountMismatch ? differenceNote : "",
      });
      handleMutationComplete("已关联批量账务流水与 OA。", result);
    } catch (caught) {
      setFeedback({ severity: "error", message: caught instanceof Error ? caught.message : "关联OA项与流水失败" });
    } finally {
      setMutating(false);
    }
  };

  const handleConfirmWithdraw = async () => {
    if (!selectedBankRow?.relationId || !withdrawReason.trim() || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await withdrawBatchAccounting({
        relationId: selectedBankRow.relationId,
        expectedVersion: selectedBankRow.version,
        reason: withdrawReason.trim(),
      });
      setWithdrawOpen(false);
      setWithdrawReason("");
      handleMutationComplete("已撤回批量账务关联。", result);
    } catch (caught) {
      setFeedback({ severity: "error", message: caught instanceof Error ? caught.message : "撤回关联失败" });
    } finally {
      setMutating(false);
    }
  };

  return (
    <PageScaffold
      title="日常报销批量账务管理"
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
                onChange={(event) => setBankYear(event.target.value)}
                type="number"
                value={bankYear}
              />
            </label>
          </header>
          {loading ? (
            <div className="batch-accounting-bank-panel__state">
              <StatePanel compact tone="loading" title="正在加载流水" />
            </div>
          ) : null}
          {!loading && payload.bankRows.length === 0 ? (
            <div className="batch-accounting-bank-panel__state">
              <StatePanel compact tone="empty" title="当前年份暂无批量账务流水" />
            </div>
          ) : null}
          <div className="batch-accounting-bank-list">
            {payload.bankRows.map((row) => {
              const selected = row.id === selectedBankRowId;
              return (
                <button
                  aria-label={`批量账务集中处理 ${formatMoney(row.amount)} ${row.tradeTime} ${row.directionLabel || "支出"} ${accountLabel(row)}`}
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
                    <span className="batch-accounting-tag batch-accounting-tag--meta">{row.tradeTime || "-"}</span>
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
              <label className="batch-accounting-field batch-accounting-field--year" htmlFor="batch-accounting-oa-year">
                <span>OA年份</span>
                <input
                  id="batch-accounting-oa-year"
                  max={2100}
                  min={2000}
                  onChange={(event) => setOaYear(event.target.value)}
                  type="number"
                  value={oaYear}
                />
              </label>
              <div className="batch-accounting-field batch-accounting-field--search">
                <label htmlFor="batch-accounting-oa-search">搜索OA内容</label>
                <div className="batch-accounting-search">
                  <Search aria-hidden="true" size={15} strokeWidth={2.2} />
                  <input
                    id="batch-accounting-oa-search"
                    onChange={(event) => setOaSearchQuery(event.target.value)}
                    placeholder="申请人、项目、金额、事由"
                    type="search"
                    value={oaSearchQuery}
                  />
                  {oaSearchQuery ? (
                    <button
                      aria-label="清空搜索"
                      className="batch-accounting-search__clear"
                      onClick={() => setOaSearchQuery("")}
                      type="button"
                    >
                      <X aria-hidden="true" size={14} strokeWidth={2.4} />
                    </button>
                  ) : null}
                </div>
              </div>
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
