import { useCallback, useEffect, useMemo, useRef, useState, type FocusEvent, type MouseEvent } from "react";
import { Button, Chip, Input } from "@heroui/react";
import { AlertTriangle, ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react";

import BatchAccountingTagRulesDrawer from "../components/batchAccounting/BatchAccountingTagRulesDrawer";
import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import StatePanel from "../components/common/StatePanel";
import QuerySearch from "../components/common/QuerySearch";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { formatDateTimeText } from "../features/dateTime";
import { formatMoney } from "../features/money";
import {
  fetchBatchAccounting,
  fetchBatchAccountingTagRules,
  saveBatchAccountingTagRules,
  submitBatchAccounting,
  withdrawBatchAccounting,
} from "../features/batchAccounting/api";
import type {
  BatchAccountingBankRow,
  BatchAccountingBucket,
  BatchAccountingAmountCheck,
  BatchAccountingOaRow,
  BatchAccountingResponse,
  BatchAccountingTagRules,
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
  tagSelectionVersion: 1,
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

function formatCents(cents: number) {
  return formatMoney((cents / 100).toFixed(2));
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
  const [oaSearchDraft, setOaSearchDraft] = useState("");
  const [oaSearchQuery, setOaSearchQuery] = useState("");
  const [differenceNote, setDifferenceNote] = useState("");
  const [feedback, setFeedback] = useState<{ severity: "success" | "error"; message: string } | null>(null);
  const [tagRulesOpen, setTagRulesOpen] = useState(false);
  const [tagRules, setTagRules] = useState<BatchAccountingTagRules | null>(null);
  const [selectedTagCodes, setSelectedTagCodes] = useState<Set<string>>(() => new Set());
  const [tagRulesLoading, setTagRulesLoading] = useState(false);
  const [tagRulesSaving, setTagRulesSaving] = useState(false);
  const [tagRulesError, setTagRulesError] = useState<string | null>(null);
  const submitIntentRef = useRef<{ fingerprint: string; idempotencyKey: string } | null>(null);
  const withdrawIntentRef = useRef<{ fingerprint: string; idempotencyKey: string } | null>(null);
  const loadRequestIdRef = useRef(0);
  const tagRulesRequestIdRef = useRef(0);

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
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
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
      .then((nextPayload) => {
        if (requestId === loadRequestIdRef.current) {
          applyBatchAccountingPayload(nextPayload);
        }
      })
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught) || requestId !== loadRequestIdRef.current) {
          return;
        }
        setPayload(EMPTY_PAYLOAD);
        setError(caught instanceof Error ? caught.message : "批量账务数据加载失败");
      })
      .finally(() => {
        if (requestId === loadRequestIdRef.current) {
          setLoading(false);
        }
      });
  }, [applyBatchAccountingPayload, bankPage, bankYear, bucket, oaPage, oaSearchQuery]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadData(controller.signal);
    return () => {
      controller.abort();
      loadRequestIdRef.current += 1;
    };
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
    const submitFingerprint = JSON.stringify({
      bankYear,
      bankRowId: selectedBankRow.id,
      oaRowIds: selectedOaRows.map((row) => row.id).sort(),
      expectedVersion: selectedBankRow.version,
      expectedTagSelectionVersion: payload.tagSelectionVersion,
      note: isAmountMismatch ? differenceNote.trim() : "",
    });
    if (submitIntentRef.current?.fingerprint !== submitFingerprint) {
      submitIntentRef.current = { fingerprint: submitFingerprint, idempotencyKey: crypto.randomUUID() };
    }
    const idempotencyKey = submitIntentRef.current.idempotencyKey;
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
            expectedTagSelectionVersion: payload.tagSelectionVersion,
            note: isAmountMismatch ? differenceNote : "",
            idempotencyKey,
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
      submitIntentRef.current = null;
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
    const withdrawFingerprint = JSON.stringify({ relationId, expectedVersion, reason });
    if (withdrawIntentRef.current?.fingerprint !== withdrawFingerprint) {
      withdrawIntentRef.current = { fingerprint: withdrawFingerprint, idempotencyKey: crypto.randomUUID() };
    }
    const idempotencyKey = withdrawIntentRef.current.idempotencyKey;
    const result = await runOperation({
      loadingMessage: "正在撤回批量账务关联...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const withdrawResult = await withdrawBatchAccounting({
            relationId,
            expectedVersion,
            reason,
            idempotencyKey,
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
      withdrawIntentRef.current = null;
      handleMutationComplete("已撤回批量账务关联。", result.value);
    } else {
      setFeedback({ severity: "error", message: mutationErrorMessage(result.error, "撤回关联失败") });
    }
  };

  const handleOpenTagRules = async () => {
    setTagRulesOpen(true);
    setTagRulesLoading(true);
    setTagRulesError(null);
    const requestId = tagRulesRequestIdRef.current + 1;
    tagRulesRequestIdRef.current = requestId;
    try {
      const nextRules = await fetchBatchAccountingTagRules();
      if (requestId !== tagRulesRequestIdRef.current) {
        return;
      }
      setTagRules(nextRules);
      setSelectedTagCodes(new Set(nextRules.selectedTagCodes));
    } catch (caught) {
      if (requestId === tagRulesRequestIdRef.current) {
        setTagRulesError(mutationErrorMessage(caught, "批量账务标签规则加载失败"));
      }
    } finally {
      if (requestId === tagRulesRequestIdRef.current) {
        setTagRulesLoading(false);
      }
    }
  };

  const handleSaveTagRules = async () => {
    if (!tagRules || !tagRules.canSave || tagRulesSaving) {
      return;
    }
    setTagRulesSaving(true);
    setTagRulesError(null);
    try {
      const nextRules = await saveBatchAccountingTagRules({
        expectedVersion: tagRules.version,
        selectedTagCodes: Array.from(selectedTagCodes),
      });
      setTagRules(nextRules);
      setSelectedTagCodes(new Set(nextRules.selectedTagCodes));
      setTagRulesOpen(false);
      setBankPage(1);
      setSelectedBankRowId(null);
      setSelectedOaRowIds(new Set());
      try {
        const nextPayload = await fetchBatchAccounting({
          bankYear,
          bucket,
          bankPage: 1,
          bankPageSize: BATCH_ACCOUNTING_PAGE_SIZE,
          oaPage: bucket === "unsubmitted" ? oaPage : undefined,
          oaPageSize: bucket === "unsubmitted" ? BATCH_ACCOUNTING_PAGE_SIZE : undefined,
          oaSearch: bucket === "unsubmitted" ? oaSearchQuery : undefined,
        });
        applyBatchAccountingPayload(nextPayload);
        setFeedback({ severity: "success", message: "批量账务标签规则已更新。" });
      } catch {
        setFeedback({
          severity: "success",
          message: mutationReloadFailedMessage(undefined, "批量账务标签规则已更新。"),
        });
      }
    } catch (caught) {
      setTagRulesError(mutationErrorMessage(caught, "批量账务标签规则保存失败"));
    } finally {
      setTagRulesSaving(false);
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
        <div className="batch-accounting-page-actions">
          <Button className="batch-accounting-page-action" onPress={handleOpenTagRules} size="sm" variant="outline">
            批量账务标签规则
          </Button>
          <Button
            className="batch-accounting-page-action"
            isDisabled={loading}
            onPress={() => loadData()}
            size="sm"
            variant="outline"
          >
            <RefreshCw aria-hidden="true" size={16} strokeWidth={2.2} />
            刷新
          </Button>
        </div>
      )}
    >
      <div aria-label="批量账务筛选" className="batch-accounting-filter" role="region">
        <div aria-label="批量账务状态" className="batch-accounting-segment" role="group">
          <Button
            aria-pressed={bucket === "unsubmitted"}
            className={cx("batch-accounting-segment__button", bucket === "unsubmitted" && "batch-accounting-segment__button--active")}
            onPress={() => handleBucketChange("unsubmitted")}
            size="sm"
            variant={bucket === "unsubmitted" ? "primary" : "secondary"}
          >
            未提交 {payload.summary.unsubmittedCount}
          </Button>
          <Button
            aria-pressed={bucket === "submitted"}
            className={cx("batch-accounting-segment__button", bucket === "submitted" && "batch-accounting-segment__button--active")}
            onPress={() => handleBucketChange("submitted")}
            size="sm"
            variant={bucket === "submitted" ? "primary" : "secondary"}
          >
            已提交 {payload.summary.submittedCount}
          </Button>
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
            <div className="batch-accounting-field batch-accounting-field--year">
              <Input
                aria-label="流水年份"
                max={2100}
                min={2000}
                onChange={(event) => handleBankYearChange(event.target.value)}
                type="number"
                value={bankYear}
              />
            </div>
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
              const tradeTimeLabel = formatDateTimeText(row.tradeTime);
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
                    <span className="batch-accounting-bank-row__identity">
                      <span className="batch-accounting-bank-row__title">批量账务集中处理</span>
                      {row.tagLabel ? (
                        <Chip color="accent" size="sm" variant="soft">
                          <Chip.Label>{row.tagLabel}</Chip.Label>
                        </Chip>
                      ) : null}
                    </span>
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
              <QuerySearch
                ariaLabel="搜索OA内容"
                className="batch-accounting-query-search"
                onChange={setOaSearchDraft}
                onClear={() => {
                  setOaSearchDraft("");
                  setOaSearchQuery("");
                  setOaPage(1);
                }}
                onSubmit={() => {
                  setOaSearchQuery(oaSearchDraft.trim());
                  setOaPage(1);
                }}
                placeholder="申请人、项目、金额、事由"
                value={oaSearchDraft}
              />
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

      <BatchAccountingTagRulesDrawer
        error={tagRulesError}
        loading={tagRulesLoading}
        onClose={() => {
          tagRulesRequestIdRef.current += 1;
          setTagRulesOpen(false);
        }}
        onSave={handleSaveTagRules}
        onToggle={(code, selected) => {
          setSelectedTagCodes((current) => {
            const next = new Set(current);
            if (selected) {
              next.add(code);
            } else {
              next.delete(code);
            }
            return next;
          });
        }}
        open={tagRulesOpen}
        rules={tagRules}
        saving={tagRulesSaving}
        selectedCodes={selectedTagCodes}
      />

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
