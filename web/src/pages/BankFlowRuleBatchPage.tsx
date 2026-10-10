import { CountedLabel } from "../components/common/CountLabel";
import { Segment, SegmentGroup } from "../components/common/SegmentedControl";
import BankTransactionDrawer from "../features/bankSplits/BankTransactionDrawer";
import { Button, Checkbox } from "@heroui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Eye } from "lucide-react";
import BatchExpansion from "../features/bankFlowRuleBatches/BatchExpansion";
import { useBatchExpansion } from "../features/bankFlowRuleBatches/useBatchExpansion";

import AppDialog from "../components/common/AppDialog";
import AppDrawer from "../components/common/AppDrawer";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import PageScaffold from "../components/common/PageScaffold";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../components/common/FinanceTable";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { ApiClientError } from "../features/apiClient";
import {
  fetchBankFlowRuleBatchTagSelection,
  fetchBankFlowRuleBatches,
  saveBankFlowRuleBatchTagSelection,
  submitBankFlowRuleBatch,
  submitBankFlowRuleBatchSelection,
  withdrawBankFlowRuleBatch,
} from "../features/bankFlowRuleBatches/api";
import {
  canSelectBatchRows,
  canSubmitInternalTransferBatch,
  canWithdrawBatch,
  batchMatchesSelectionScope,
} from "../features/bankFlowRuleBatches/policy";
import { BatchStatusTag, PageControls } from "../features/bankFlowRuleBatches/components";
import type { BatchSelectionScope } from "../features/bankFlowRuleBatches/policy";
import {
  accountLabel,
  buildTagDrawerRows,
  categoryCountForBucket,
  currentMonth,
  cx,
  directionTagLabel,
  formatMoney,
  isAbortLikeError,
  relationContextLabels,
  requirementFor,
  requirementsFromSelection,
  tagPrimaryLabel,
  tagSubLabel,
} from "../features/bankFlowRuleBatches/viewModel";
import type {
  BankFlowRuleDraftRequirements,
} from "../features/bankFlowRuleBatches/viewModel";
import type {
  BankFlowRuleBatch,
  BankFlowRuleBatchesResponse,
  BankFlowRuleBatchStatusBucket,
  BankFlowRuleBatchDetailRow,
  BankFlowRuleBatchTagRule,
  BankFlowRuleBatchTagSelection,
} from "../features/bankFlowRuleBatches/types";
import { fetchBackgroundJob } from "../features/backgroundJobs/api";
import { formatDateTimeText } from "../features/dateTime";

const EMPTY_BATCHES: BankFlowRuleBatchesResponse = {
  summary: {
    labelCounts: [],
    draftCount: 0,
    submittedCount: 0,
    withdrawnCount: 0,
    conflictCount: 0,
    staleCount: 0,
    totalRowCount: 0,
    draftRowCount: 0,
    submittedRowCount: 0,
    withdrawnRowCount: 0,
    totalAmount: "0.00",
    categories: [],
  },
  batches: [],
  pagination: { page: 1, pageSize: 50, total: 0 },
};

const EMPTY_TAG_SELECTION: BankFlowRuleBatchTagSelection = {
  version: 1,
  bankAutoTagRulesVersion: 1,
  activeTags: [],
  rules: [],
  requirementsByTagCode: {},
  eligibilityChanged: false,
  eligibilityChangedTagCodes: [],
  requirementChangedTagCodes: [],
  recalculationJobId: "",
  affectedMonths: [],
  affectedScopeKeys: [],
};

const SELF_SUB_LABEL = "主标签本身";
const BANK_FLOW_RULE_BATCH_PAGE_SIZE = 50;
const CANDIDATE_CONFLICT_CODE = "bank_flow_rule_batch_candidate_conflict";
const CANDIDATE_CONFLICT_MESSAGE = "候选已更新，请重新选择。";
const RECALCULATION_POLL_INTERVAL_MS = 250;
const RECALCULATION_POLL_LIMIT = 120;

function waitForPollInterval() {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, RECALCULATION_POLL_INTERVAL_MS);
  });
}

async function waitForRequirementRecalculation(jobId: string) {
  for (let attempt = 0; attempt < RECALCULATION_POLL_LIMIT; attempt += 1) {
    const job = await fetchBackgroundJob(jobId);
    if (job.status === "succeeded") {
      return;
    }
    if (job.status !== "queued" && job.status !== "running") {
      throw new Error(job.error || job.message || `流水关联要求重算失败（${job.status}）。`);
    }
    await waitForPollInterval();
  }
  throw new Error("流水规则已保存，但关联重算在 30 秒内未完成，请稍后刷新。");
}

function isCandidateConflict(caught: unknown) {
  return caught instanceof ApiClientError && caught.code === CANDIDATE_CONFLICT_CODE;
}

function mutationErrorMessage(caught: unknown, fallback: string) {
  if (isCandidateConflict(caught)) {
    return CANDIDATE_CONFLICT_MESSAGE;
  }
  const message = caught instanceof Error ? caught.message : fallback;
  if (!(caught instanceof ApiClientError) || caught.status < 500 || !caught.payload || typeof caught.payload !== "object") {
    return message;
  }
  const requestId = "requestId" in caught.payload && typeof caught.payload.requestId === "string"
    ? caught.payload.requestId.trim()
    : "";
  return requestId ? `${message}（请求编号：${requestId}）` : message;
}

export default function BankFlowRuleBatchPage() {
  const [bankDetailRow, setBankDetailRow] = useState<BankFlowRuleBatchDetailRow | null>(null);
  const { runOperation } = useGlobalOperationOverlay();
  const { active, activationGeneration } = useOptionalPageActivation("bank-flow-rule-batches");
  const { canOperateData } = useSessionPermissions();
  const [month, setMonth] = useState("");
  const [bucket, setBucket] = useState<BankFlowRuleBatchStatusBucket>("unsubmitted");
  const [payload, setPayload] = useState<BankFlowRuleBatchesResponse>(EMPTY_BATCHES);
  const [tagSelection, setTagSelection] = useState<BankFlowRuleBatchTagSelection>(EMPTY_TAG_SELECTION);
  const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
  const [draftTagRequirements, setDraftTagRequirements] = useState<BankFlowRuleDraftRequirements>(() => ({}));
  const [selectedPrimaryLabel, setSelectedPrimaryLabel] = useState("");
  const [selectedSubKey, setSelectedSubKey] = useState("");
  const [categoryCodes, setCategoryCodes] = useState<string[]>([]);
  const [snapshotVersion, setSnapshotVersion] = useState(0);
  const [candidatesInvalid, setCandidatesInvalid] = useState(false);
  const [discardTagChangesOpen, setDiscardTagChangesOpen] = useState(false);
  const [selectedTransactionIds, setSelectedTransactionIds] = useState<Set<string>>(() => new Set());
  const [selectionScope, setSelectionScope] = useState<BatchSelectionScope | null>(null);
  const [batchPage, setBatchPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasCounts, setHasCounts] = useState(false);
  const [tagLoading, setTagLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<BankFlowRuleBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [feedback, setFeedback] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const tagRequestSeqRef = useRef(0);
  const batchRequestSeqRef = useRef(0);
  const queryScopeKey = JSON.stringify({ month, bucket, page: batchPage, types: categoryCodes });
  const expansion = useBatchExpansion({
    batches: payload.batches, bucket, scopeKey: queryScopeKey, snapshotVersion,
    enabled: active && !loading && !error && !candidatesInvalid,
  });
  const { details, errors: detailErrors } = expansion;
  const pendingCorrectedPageRef = useRef<number | null>(null);

  const loadTagSelection = useCallback((signal?: AbortSignal) => {
    const requestId = tagRequestSeqRef.current + 1;
    tagRequestSeqRef.current = requestId;
    setTagLoading(true);
    fetchBankFlowRuleBatchTagSelection(signal)
      .then((nextSelection) => {
        if (signal?.aborted || requestId !== tagRequestSeqRef.current) {
          return;
        }
        setTagSelection(nextSelection);
        setDraftTagRequirements(requirementsFromSelection(nextSelection));
      })
      .catch((caught) => {
        if (!signal?.aborted && requestId === tagRequestSeqRef.current && !isAbortLikeError(caught)) {
          setFeedback({ severity: "error", message: caught instanceof Error ? caught.message : "流水标签配置加载失败" });
        }
      })
      .finally(() => {
        if (!signal?.aborted && requestId === tagRequestSeqRef.current) {
          setTagLoading(false);
        }
      });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedTransactionIds(new Set());
    setSelectionScope(null);
  }, []);

  const applyBatchesPayload = useCallback((nextPayload: BankFlowRuleBatchesResponse) => {
    setPayload(nextPayload);
    setSnapshotVersion((current) => current + 1);
    setCandidatesInvalid(false);
    setHasCounts(true);
    setError(null);
    clearSelection();
  }, [clearSelection]);

  const readBatches = useCallback(async (signal?: AbortSignal) => {
    const requestId = ++batchRequestSeqRef.current;
    let nextPage = batchPage;
    const read = (page: number) => fetchBankFlowRuleBatches({
      month, bucket, type: categoryCodes, page,
      pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE, signal,
    });
    let nextPayload = await read(nextPage);
    if (signal?.aborted || requestId !== batchRequestSeqRef.current) return null;
    const lastPage = Math.max(1, Math.ceil(nextPayload.pagination.total / nextPayload.pagination.pageSize));
    if (nextPage > lastPage) {
      nextPage = lastPage;
      nextPayload = await read(nextPage);
      if (signal?.aborted || requestId !== batchRequestSeqRef.current) return null;
      pendingCorrectedPageRef.current = nextPage;
      setBatchPage(nextPage);
    }
    applyBatchesPayload(nextPayload);
    return nextPayload;
  }, [applyBatchesPayload, batchPage, bucket, categoryCodes, month]);

  const reloadBatchesAfterMutation = useCallback(async () => {
    setLoading(true);
    const pendingRead = readBatches();
    const requestId = batchRequestSeqRef.current;
    try {
      return await pendingRead;
    } catch (caught) {
      if (requestId !== batchRequestSeqRef.current) return null;
      throw caught;
    } finally {
      if (requestId === batchRequestSeqRef.current) setLoading(false);
    }
  }, [readBatches]);

  const loadBatches = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    const pendingRead = readBatches(signal);
    const requestId = batchRequestSeqRef.current;
    pendingRead
      .catch((caught: unknown) => {
        if (!signal?.aborted && requestId === batchRequestSeqRef.current && !isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "流水规则批次加载失败");
        }
      })
      .finally(() => {
        if (!signal?.aborted && requestId === batchRequestSeqRef.current) setLoading(false);
      });
  }, [readBatches]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    loadTagSelection(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, loadTagSelection]);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    if (pendingCorrectedPageRef.current === batchPage) {
      pendingCorrectedPageRef.current = null;
      return;
    }
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, batchPage, loadBatches, refreshToken]);

  const categoryGroups = useMemo(() => {
    const groups = new Map<string, { label: string; codes: string[]; rowCount: number; children: { label: string; key: string; codes: string[]; rowCount: number }[] }>();
    const countFor = (primaryLabel: string, subLabel: string | null) => {
      const counts = payload.summary.labelCounts.find((item) => item.primaryLabel === primaryLabel && item.subLabel === subLabel);
      if (!counts) throw new Error("流水分类统计缺失。");
      return bucket === "unsubmitted" ? counts.draftRowCount : bucket === "submitted" ? counts.submittedRowCount : counts.withdrawnRowCount;
    };
    payload.summary.categories.forEach((category) => {
      if (categoryCountForBucket(category, bucket) <= 0) return;
      const primary = tagPrimaryLabel(category) || category.label || category.code;
      const sub = tagSubLabel(category);
      if (!groups.has(primary)) groups.set(primary, { label: primary, codes: [], rowCount: countFor(primary, null), children: [] });
      const group = groups.get(primary)!;
      group.codes.push(category.code);
      const key = sub || SELF_SUB_LABEL;
      let child = group.children.find((item) => item.key === key);
      if (!child) {
        child = { label: key, key, codes: [], rowCount: countFor(primary, sub) };
        group.children.push(child);
      }
      child.codes.push(category.code);
    });
    return [...groups.values()];
  }, [bucket, payload.summary]);

  const visibleBatches = payload.batches;
  const hasBatchActions = canOperateData && visibleBatches.some((batch) =>
    canSubmitInternalTransferBatch(batch, bucket) || (bucket === "submitted" && canWithdrawBatch(batch)));
  const selectedAccountBatch = selectionScope ? visibleBatches.find((batch) => batch.accountKey === selectionScope.accountKey && batch.scopeMonth === selectionScope.scopeMonth) : undefined;
  const listPagination = payload.pagination;
  const bucketRowCount = bucket === "unsubmitted" ? payload.summary.draftRowCount : bucket === "submitted" ? payload.summary.submittedRowCount : payload.summary.withdrawnRowCount;
  useEffect(() => {
    if (!feedback || feedback.severity !== "success") {
      return undefined;
    }
    const timeout = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  const toggleTransaction = (batch: BankFlowRuleBatch, row: BankFlowRuleBatchDetailRow, checked: boolean) => {
    if (checked && (!batchMatchesSelectionScope(batch, selectionScope) || row.accountKey !== batch.accountKey)) {
      setFeedback({ severity: "warning", message: "只能选择同一账户、同一月份的流水，请先清空当前选择。" });
      return;
    }
    const next = new Set(selectedTransactionIds);
    if (checked) {
      next.add(row.transactionId);
      setSelectionScope({ accountKey: batch.accountKey, scopeMonth: batch.scopeMonth! });
    } else {
      next.delete(row.transactionId);
      if (!next.size) setSelectionScope(null);
    }
    setSelectedTransactionIds(next);
  };

  const setRegionSelection = (batch: BankFlowRuleBatch, rows: BankFlowRuleBatchDetailRow[], checked: boolean) => {
    if (checked && (!batchMatchesSelectionScope(batch, selectionScope) || rows.some((row) => row.accountKey !== batch.accountKey))) {
      setFeedback({ severity: "warning", message: "只能选择同一账户、同一月份的流水，请先清空当前选择。" });
      return;
    }
    const next = new Set(selectedTransactionIds);
    rows.forEach((row) => checked ? next.add(row.transactionId) : next.delete(row.transactionId));
    setSelectedTransactionIds(next);
    setSelectionScope(next.size ? checked ? { accountKey: batch.accountKey, scopeMonth: batch.scopeMonth! } : selectionScope : null);
  };

  const refreshAfterCandidateConflict = async (caught: unknown, setMessage: (message: string) => void) => {
    if (!isCandidateConflict(caught)) return;
    clearSelection();
    expansion.invalidate();
    setCandidatesInvalid(true);
    setMessage("候选已变化，正在刷新流水规则批次...");
    try { await reloadBatchesAfterMutation(); }
    catch (readError) { setError(readError instanceof Error ? readError.message : "列表刷新失败，请重试读取。"); }
  };

  const readAfterSuccessfulWrite = async (message: string, setMessage: (message: string) => void) => {
    clearSelection();
    expansion.invalidate();
    setCandidatesInvalid(true);
    setMessage("正在加载流水规则批次最新数据...");
    try {
      const refreshed = await reloadBatchesAfterMutation();
      if (refreshed) setFeedback({ severity: "success", message });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "列表刷新失败");
      setFeedback({ severity: "warning", message: `${message}，列表刷新失败，请重试读取。` });
    }
  };

  const handleSubmitSelected = async () => {
    if (!canOperateData || selectedTransactionIds.size === 0 || mutating || loading || candidatesInvalid) {
      return;
    }
    if (!selectionScope?.scopeMonth) {
      setFeedback({ severity: "error", message: "流水规则候选月份缺失，请刷新列表后重试" });
      return;
    }
    const transactionIds = Array.from(selectedTransactionIds);
    const scopeMonth = selectionScope.scopeMonth;
    await runOperation({
      loadingMessage: "正在提交选中流水规则...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBankFlowRuleBatchSelection({
            transactionIds,
            scopeMonth,
            note: "",
          });
          await readAfterSuccessfulWrite("选中流水已提交", setMessage);
          return submitResult;
        } catch (caught) {
          await refreshAfterCandidateConflict(caught, setMessage);
          throw caught;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "提交选中流水失败"),
    });
  };

  const handleSubmitBatch = async (batch: BankFlowRuleBatch) => {
    if (!canOperateData || !canSubmitInternalTransferBatch(batch, bucket) || mutating || loading || candidatesInvalid) {
      return;
    }
    const scopeMonth = batch.scopeMonth;
    if (!scopeMonth) {
      setFeedback({ severity: "error", message: "流水规则候选月份缺失，请刷新列表后重试" });
      return;
    }
    await runOperation({
      loadingMessage: "正在提交内部往来流水规则批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBankFlowRuleBatch({
            batchId: batch.batchId,
            expectedVersion: batch.version,
            scopeMonth,
            note: "",
          });
          await readAfterSuccessfulWrite("内部往来批次已提交", setMessage);
          return submitResult;
        } catch (caught) {
          await refreshAfterCandidateConflict(caught, setMessage);
          throw caught;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "提交内部往来批次失败"),
    });
  };

  const handleConfirmWithdraw = async () => {
    if (!canOperateData || !withdrawTarget || !withdrawReason.trim() || mutating) {
      return;
    }
    const target = withdrawTarget;
    const reason = withdrawReason.trim();
    await runOperation({
      loadingMessage: "正在撤回流水规则批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const withdrawResult = await withdrawBankFlowRuleBatch({
            batchId: target.batchId,
            expectedVersion: target.version,
            reason,
          });
          setWithdrawTarget(null);
          setWithdrawReason("");
          await readAfterSuccessfulWrite("批次已撤回", setMessage);
          return withdrawResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "撤回批次失败"),
    });
  };

  const saveTagSelection = async () => {
    if (!canOperateData || tagLoading || mutating) {
      return;
    }
    const rules: BankFlowRuleBatchTagRule[] = tagSelection.activeTags.map((tag) => {
      const requirement = requirementFor(draftTagRequirements, tag.code);
      return {
        tagCode: tag.code,
        requiresOa: requirement.requiresOa,
        requiresInvoice: requirement.requiresInvoice,
      };
    });
    await runOperation({
      loadingMessage: "正在保存流水规则...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const saved = await saveBankFlowRuleBatchTagSelection({
            expectedVersion: tagSelection.version,
            rules,
          });
          setTagSelection(saved);
          setDraftTagRequirements(requirementsFromSelection(saved));
          clearSelection();
          expansion.invalidate();
          setCandidatesInvalid(true);
          if (saved.recalculationJobId) {
            setMessage("流水规则已保存，正在重算受影响关联...");
            try {
              await waitForRequirementRecalculation(saved.recalculationJobId);
            } catch (caught) {
              const message = caught instanceof Error ? caught.message : "关联重算失败";
              const savedMessage = message.startsWith("流水规则已保存") ? message : `流水规则已保存，但${message}`;
              setError(savedMessage);
              throw new Error(savedMessage);
            }
          }
          await readAfterSuccessfulWrite(saved.recalculationJobId ? "流水规则已保存，受影响关联已重算" : "流水规则已保存", setMessage);
          return saved;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => mutationErrorMessage(caught, "保存流水规则失败"),
    });
  };

  const drawerRows = useMemo(() => buildTagDrawerRows(tagSelection.activeTags), [tagSelection.activeTags]);

  const updateDraftRequirement = (
    tagCode: string,
    field: "requiresOa" | "requiresInvoice",
    checked: boolean,
  ) => {
    setDraftTagRequirements((current) => {
      const currentRule = requirementFor(current, tagCode);
      return {
        ...current,
        [tagCode]: {
          ...currentRule,
          [field]: checked,
        },
      };
    });
  };

  const resetListScope = useCallback(() => {
    clearSelection();
    expansion.reset();
  }, [clearSelection, expansion.reset]);

  const selectCategory = (primary: string, sub: string, codes: string[]) => {
    if (primary === selectedPrimaryLabel && sub === selectedSubKey) return;
    resetListScope();
    setSelectedPrimaryLabel(primary);
    setSelectedSubKey(sub);
    setCategoryCodes(codes);
    setBatchPage(1);
  };

  const savedTagRequirements = useMemo(() => requirementsFromSelection(tagSelection), [tagSelection]);
  const tagDraftDirty = tagSelection.activeTags.some((tag) => {
    const current = requirementFor(draftTagRequirements, tag.code);
    const saved = requirementFor(savedTagRequirements, tag.code);
    return current.requiresOa !== saved.requiresOa || current.requiresInvoice !== saved.requiresInvoice;
  });
  const closeTagDrawer = () => {
    if (tagLoading || mutating) return;
    if (tagDraftDirty) setDiscardTagChangesOpen(true);
    else setTagDrawerOpen(false);
  };

  const selectBucket = (nextBucket: BankFlowRuleBatchStatusBucket) => {
    if (nextBucket === bucket) {
      return;
    }
    resetListScope();
    setBatchPage(1);
    setSelectedPrimaryLabel("");
    setSelectedSubKey("");
    setCategoryCodes([]);
    setBucket(nextBucket);
  };

  const handleMonthChange = (nextMonth: string) => {
    resetListScope();
    setBatchPage(1);
    setSelectedPrimaryLabel("");
    setSelectedSubKey("");
    setCategoryCodes([]);
    setMonth(nextMonth);
  };

  const handlePageChange = (nextPage: number) => {
    resetListScope();
    setBatchPage(Math.max(1, nextPage));
  };

  return (
    <PageScaffold
      title="流水规则批量处理"
      actions={(
        <div className="bank-flow-rule-batches-actions">
          <Button
            className="bank-flow-rule-batches-button"
            isDisabled={tagLoading}
            onPress={() => {
              loadTagSelection();
              setTagDrawerOpen(true);
            }}
            size="sm"
            variant="secondary"
          >
            流水规则标签管理
          </Button>
          {(error) && <Button
            className="bank-flow-rule-batches-button"
            isDisabled={loading}
            onPress={() => {
              loadTagSelection();
              setRefreshToken((current) => current + 1);
            }}
            size="sm"
            variant="secondary"
          >
            重试读取
          </Button>}
        </div>
      )}
    >
      {!canOperateData ? (
        <StatePanel compact tone="warning">当前页面暂不可提交、撤回或保存流水规则批次。</StatePanel>
      ) : null}
      <div aria-label="批次筛选" className="bank-flow-rule-batches-filter" role="region">
        <SegmentGroup
          aria-busy={loading && !error}
          aria-label="批次状态"
          className="bank-flow-rule-batches-segment"
          disallowEmptySelection
          onSelectionChange={(keys) => {
            const [next] = Array.from(keys);
            if (next === "unsubmitted" || next === "submitted" || next === "withdrawn") selectBucket(next);
          }}
          selectedKeys={new Set([bucket])}
          selectionMode="single"
          size="sm"
        >
          <Segment id="unsubmitted"><CountedLabel label="未提交" value={!hasCounts || error ? undefined : payload.summary.draftRowCount} unit="笔" spaced /></Segment>
          <Segment id="submitted"><CountedLabel label="已提交" value={!hasCounts || error ? undefined : payload.summary.submittedRowCount} unit="笔" spaced /></Segment>
          <Segment id="withdrawn"><CountedLabel label="已撤回" value={!hasCounts || error ? undefined : payload.summary.withdrawnRowCount} unit="笔" spaced /></Segment>
        </SegmentGroup>
        <BusinessPeriodPicker
          allowedModes={["month"]}
          ariaLabel="批次月份"
          onChange={(selection) => handleMonthChange(selection.mode === "all" ? "" : selection.month)}
          selection={{
            mode: month ? "month" : "all",
            year: (month || currentMonth()).slice(0, 4),
            month: month || currentMonth(),
          }}
          years={nearbyBusinessYears(month || currentMonth())}
        />
        {bucket === "unsubmitted" && canOperateData ? (
          <div className="bank-flow-rule-batches-selection-actions">
            {selectedTransactionIds.size > 0 ? (
              <>
                <span className="bank-flow-rule-batches-selected-count">
                  已选 {selectedTransactionIds.size} 条明细 · {selectedAccountBatch ? accountLabel(selectedAccountBatch) : ""} · {selectionScope?.scopeMonth}
                </span>
                <Button
                  className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact"
                  isDisabled={mutating}
                  onPress={clearSelection}
                  size="sm"
                  variant="secondary"
                >
                  清空选择
                </Button>
              </>
            ) : null}
            <Button
              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--primary"
              isDisabled={selectedTransactionIds.size === 0 || mutating || loading || candidatesInvalid}
              onPress={handleSubmitSelected}
              size="sm"
              variant="primary"
            >
              提交所选
            </Button>
          </div>
        ) : null}
      </div>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <div className="bank-flow-rule-batches-layout">
        <nav aria-label="流水分类" className="bank-flow-rule-batches-rail">
          <h2 className="bank-flow-rule-batches-rail__title">流水分类</h2>
          <button type="button" aria-pressed={!selectedPrimaryLabel}
            aria-label={hasCounts ? `全部分类 ${bucketRowCount}笔` : "全部分类"}
            className={cx("bank-flow-rule-batches-rail__item", !selectedPrimaryLabel && "bank-flow-rule-batches-rail__item--active")}
            onClick={() => selectCategory("", "", [])}>
            <span>全部分类</span><span className="bank-flow-rule-batches-rail__item-count">{hasCounts ? `${bucketRowCount}笔` : "—"}</span>
          </button>
          {categoryGroups.map((group) => <div key={group.label} className="bank-flow-rule-batches-rail__group">
            <button type="button" aria-label={`${group.label} ${group.rowCount}笔`}
              aria-pressed={selectedPrimaryLabel === group.label && !selectedSubKey}
              className={cx("bank-flow-rule-batches-rail__item", selectedPrimaryLabel === group.label && !selectedSubKey && "bank-flow-rule-batches-rail__item--active")}
              onClick={() => selectCategory(group.label, "", group.codes)}>
              <span className="bank-flow-rule-batches-rail__item-label">{group.label}</span>
              <span className="bank-flow-rule-batches-rail__item-count">{group.rowCount}笔</span>
            </button>
            {group.children.map((child) => <button key={child.key} type="button"
              aria-label={`${group.label} / ${child.label} ${child.rowCount}笔`}
              aria-pressed={selectedPrimaryLabel === group.label && selectedSubKey === child.key}
              className={cx("bank-flow-rule-batches-rail__item", "bank-flow-rule-batches-rail__item--child", selectedPrimaryLabel === group.label && selectedSubKey === child.key && "bank-flow-rule-batches-rail__item--active")}
              onClick={() => selectCategory(group.label, child.key, child.codes)}>
              <span className="bank-flow-rule-batches-rail__item-label">{child.label}</span>
              <span className="bank-flow-rule-batches-rail__item-count">{child.rowCount}笔</span>
            </button>)}
          </div>)}
        </nav>

        <section aria-label="流水" className="bank-flow-rule-batches-transactions" role="region">
          <header className="bank-flow-rule-batches-transactions__header">
            <div className="bank-flow-rule-batches-transactions__heading">
              <h2 className="bank-flow-rule-batches-transactions__title">
                {selectedPrimaryLabel ? `${selectedPrimaryLabel}${selectedSubKey && selectedSubKey !== selectedPrimaryLabel ? ` / ${selectedSubKey}` : ""}` : "全部分类"}
              </h2>
              <span className="bank-flow-rule-batches-result-count">{hasCounts && !error ? `${listPagination.total} 批次` : "—"}</span>
            </div>
            {expansion.expandedIds.size >= 2 && <button type="button" className="bank-flow-rule-batches-text-action" onClick={expansion.collapseAll}>收起全部</button>}
          </header>
          <div className="bank-flow-rule-batches-transactions__list">
            {loading ? <StatePanel compact tone="loading" title="流水加载中" /> : null}
            {!loading && !error && visibleBatches.length === 0 ? <StatePanel compact tone="empty" title="当前标签下暂无流水" /> : null}
            {!loading && !error ? visibleBatches.map((batch) => {
              const detail = details[batch.batchId];
              const rows = detail?.rows ?? [];
              const selected = expansion.expandedIds.has(batch.batchId);
              const mounted = expansion.mountedIds.has(batch.batchId);
              const batchIdentity = `${accountLabel(batch)} ${batch.scopeMonth || "月份缺失"}`;
              const scopeCompatible = batchMatchesSelectionScope(batch, selectionScope);
              const rowSelectionEnabled = canSelectBatchRows(batch, bucket);
              const internalTransferSubmitEnabled = canSubmitInternalTransferBatch(batch, bucket);
              const selectedRowCount = rowSelectionEnabled
                ? rows.reduce((count, row) => count + Number(selectedTransactionIds.has(row.transactionId)), 0)
                : 0;
              const regionChecked = rowSelectionEnabled && rows.length > 0 && selectedRowCount === rows.length;
              const regionIndeterminate = selectedRowCount > 0 && selectedRowCount < rows.length;
              return (
                <section
                  className={cx(
                    "bank-flow-rule-batches-batch",
                    selected && "bank-flow-rule-batches-batch--expanded",
                  )}
                  key={batch.batchId}
                >
                  <div className="bank-flow-rule-batches-batch__body">
                    <div className="bank-flow-rule-batches-batch__header">
                      <button type="button" className="bank-flow-rule-batches-expand" aria-label={`${selected ? "收起" : "展开"}批次 ${batchIdentity}`}
                        aria-expanded={selected} aria-controls={`batch-body-${batch.batchId}`} onClick={() => expansion.toggle(batch.batchId)}>
                        {selected ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
                      </button>
                      <div className="bank-flow-rule-batches-batch__summary">
                        <div className="bank-flow-rule-batches-batch__title-row">
                          <h3 className="bank-flow-rule-batches-batch__title">{accountLabel(batch)}</h3>
                          <span className="bank-flow-rule-batches-batch__scope">{batch.scopeMonth || "月份缺失"}</span>
                          <BatchStatusTag status={batch.status} />
                          {!selectedPrimaryLabel && <span className="bank-flow-rule-batches-batch__category">{batch.categoryLabelPath?.length ? batch.categoryLabelPath.filter((label, index, path) => index === 0 || label !== path[index - 1]).join(" / ") : batch.batchLabel}</span>}
                          {selectedRowCount > 0 && <span className="bank-flow-rule-batches-selected-count">已选 {selectedRowCount} 条</span>}
                        </div>
                        {(batch.submittedAt || batch.withdrawnAt) && <p className="bank-flow-rule-batches-batch__audit">
                          {batch.withdrawnAt ? "撤回于" : "提交于"} {formatDateTimeText(batch.withdrawnAt || batch.submittedAt || "")}
                        </p>}
                      </div>
                      <div className={cx("bank-flow-rule-batches-batch__actions", !hasBatchActions && "bank-flow-rule-batches-batch__actions--read")}>
                        <span className="bank-flow-rule-batches-batch__meta">{batch.rowCount} 条明细</span>
                        <span className="bank-flow-rule-batches-batch__total-group"><span className="bank-flow-rule-batches-batch__meta">合计</span><strong className="bank-flow-rule-batches-batch__total">{formatMoney(batch.totalAmount)}</strong></span>
                        {internalTransferSubmitEnabled && canOperateData ? (
                          <button
                            className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact bank-flow-rule-batches-button--primary"
                            disabled={mutating || loading || candidatesInvalid}
                            onClick={() => handleSubmitBatch(batch)}
                            type="button"
                          >
                            提交内部往来批次
                          </button>
                        ) : null}
                        {bucket === "submitted" && canOperateData && canWithdrawBatch(batch) ? (
                          <button
                            className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact"
                            disabled={mutating}
                            onClick={() => setWithdrawTarget(batch)}
                            type="button"
                          >
                            撤回批次
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {mounted && <BatchExpansion id={`batch-body-${batch.batchId}`} label={`批次明细 ${batchIdentity}`}
                      expanded={selected} contentKey={`${rows.length}:${detailErrors[batch.batchId] || ""}:${Boolean(detail)}`}
                      onExited={() => expansion.onExited(batch.batchId)}>
                      {rowSelectionEnabled && !scopeCompatible && <p className="bank-flow-rule-batches-selection-hint">
                        {batch.scopeMonth ? "只能选择同一账户、同一月份的流水；清空当前选择后可切换。" : "该批次月份缺失，暂不可选择提交。"}
                      </p>}
                    {selected && detailErrors[batch.batchId] ? (
                      <div className="bank-flow-rule-batches-notice bank-flow-rule-batches-notice--error" role="alert">
                        {detailErrors[batch.batchId]}
                        <button type="button" className="bank-flow-rule-batches-text-action" aria-label={`重试批次 ${batchIdentity}`} onClick={() => expansion.retry(batch.batchId)}>重试</button>
                      </div>
                    ) : null}
                    {selected && !detail && !detailErrors[batch.batchId] ? <StatePanel compact tone="loading" title="正在加载流水明细" /> : null}
                    {selected && detail && rows.length === 0 ? <StatePanel compact tone="empty" title="暂无流水明细" /> : null}
                    {detail && rows.length > 0 ? (
                      <FinanceTable
                        ariaLabel={`${accountLabel(batch)}流水`}
                        className="bank-flow-rule-batches-table"
                        minWidth={920}
                      >
                          <FinanceTableHeader>
                              {rowSelectionEnabled ? (
                                <FinanceTableColumn className="bank-flow-rule-batches-table__check" columnRole="selection">
                                  <Checkbox
                                    aria-label={`${accountLabel(batch)}全选`}
                                    className="bank-flow-rule-batches-checkbox bank-flow-rule-batches-checkbox--table"
                                    isDisabled={!canOperateData || !scopeCompatible || mutating || candidatesInvalid || loading}
                                    isIndeterminate={regionIndeterminate}
                                    isSelected={regionChecked}
                                    slot="selection"
                                    onChange={(selected) => setRegionSelection(batch, rows, selected)}
                                  >
                                    <Checkbox.Control className="bank-flow-rule-batches-checkbox__control">
                                      <Checkbox.Indicator />
                                    </Checkbox.Control>
                                  </Checkbox>
                                </FinanceTableColumn>
                              ) : null}
                              <FinanceTableColumn className="bank-flow-rule-batches-table__counterparty" columnRole="identity" isRowHeader>对方户名</FinanceTableColumn>
                              <FinanceTableColumn className="bank-flow-rule-batches-table__time" columnRole="date">交易时间</FinanceTableColumn>
                              <FinanceTableColumn className="bank-flow-rule-batches-table__amount" columnRole="amount">金额</FinanceTableColumn>
                              <FinanceTableColumn className="bank-flow-rule-batches-table__relation" columnRole="status">关联</FinanceTableColumn>
                              <FinanceTableColumn className="bank-flow-rule-batches-table__description" columnRole="description">摘要/用途/备注</FinanceTableColumn>
                          </FinanceTableHeader>
                          <FinanceTableBody>
                            {rows.map((row) => {
                              const relationLabels = relationContextLabels(row);
                              const rowSelected = selectedTransactionIds.has(row.transactionId);
                              const memoText = Array.from(new Set(
                                [row.purpose, row.remark]
                                  .map((value) => value.trim())
                                  .filter(Boolean),
                              )).join(" / ");
                              return (
                                <FinanceTableRow
                                  className={cx(rowSelected && "bank-flow-rule-batches-table__row--selected")}
                                  id={row.transactionId}
                                  key={row.transactionId}
                                >
                                  {rowSelectionEnabled ? (
                                    <FinanceTableCell className="bank-flow-rule-batches-table__check" columnRole="selection">
                                      <Checkbox
                                        aria-label={`选择流水 ${row.counterpartyName || "未知对方"} ${formatDateTimeText(row.tradeTime)} ${formatMoney(row.amount)} ${row.bankName || "未知银行"} ${row.accountLast4 || ""}`}
                                        className="bank-flow-rule-batches-checkbox bank-flow-rule-batches-checkbox--table"
                                        isDisabled={!canOperateData || !scopeCompatible || row.accountKey !== batch.accountKey || mutating || candidatesInvalid || loading}
                                        isSelected={rowSelected}
                                        onChange={(selected) => toggleTransaction(batch, row, selected)}
                                      >
                                        <Checkbox.Control className="bank-flow-rule-batches-checkbox__control">
                                          <Checkbox.Indicator />
                                        </Checkbox.Control>
                                      </Checkbox>
                                    </FinanceTableCell>
                                  ) : null}
                                  <FinanceTableCell className="bank-flow-rule-batches-table__counterparty" columnRole="identity">{row.counterpartyName || "—"}<button type="button" aria-label={`查看银行流水 ${row.counterpartyName} 详情`} className="bank-flow-rule-batches-detail" onClick={() => setBankDetailRow(row)}><Eye size={14} aria-hidden="true" /></button></FinanceTableCell>
                                  <FinanceTableCell className="bank-flow-rule-batches-table__time" columnRole="date">{formatDateTimeText(row.tradeTime)}</FinanceTableCell>
                                  <FinanceTableCell className="bank-flow-rule-batches-table__amount" columnRole="amount">
                                    <div className="bank-flow-rule-batches-amount-cell">
                                      <div className="bank-flow-rule-batches-amount-cell__main">
                                        <span className="bank-flow-rule-batches-tag bank-flow-rule-batches-tag--direction">
                                          {directionTagLabel(row)}
                                        </span>
                                        <span className="bank-flow-rule-batches-amount">{formatMoney(row.amount)}</span>
                                      </div>
                                    </div>
                                  </FinanceTableCell>
                                  <FinanceTableCell className="bank-flow-rule-batches-table__relation" columnRole="status">
                                      {relationLabels.length > 0 ? (
                                        <div className="bank-flow-rule-batches-relation-cell">
                                          <span className="bank-flow-rule-batches-tag">{relationLabels[0]}</span>
                                          <span className="bank-flow-rule-batches-relation-cell__counts">
                                            {relationLabels.slice(1).join(" · ")}
                                          </span>
                                        </div>
                                      ) : <span className="bank-flow-rule-batches-empty-value">—</span>}
                                  </FinanceTableCell>
                                  <FinanceTableCell className="bank-flow-rule-batches-table__description" columnRole="description">
                                    <div className="bank-flow-rule-batches-summary-cell">
                                      <span className="bank-flow-rule-batches-summary-cell__summary">{row.summary.trim() || "—"}</span>
                                      {memoText ? <span className="bank-flow-rule-batches-summary-cell__memo">{memoText}</span> : null}
                                    </div>
                                  </FinanceTableCell>
                                </FinanceTableRow>
                              );
                            })}
                          </FinanceTableBody>
                      </FinanceTable>
                    ) : null}
                    </BatchExpansion>}
                  </div>
                </section>
              );
            }) : null}
          </div>
          <footer className="bank-flow-rule-batches-transactions__footer">
            <span>{hasCounts && !error ? `共 ${listPagination.total} 批次` : "—"}</span>
            <PageControls disabled={loading} label="流水规则批次分页"
              onNext={() => handlePageChange(listPagination.page + 1)} onPrevious={() => handlePageChange(listPagination.page - 1)}
              page={listPagination.page} pageSize={listPagination.pageSize} total={listPagination.total} />
          </footer>
        </section>
      </div>

      <AppDrawer
        ariaBusy={tagLoading || mutating}
        className="bank-flow-rule-batches-drawer"
        closeDisabled={tagLoading || mutating}
        closeLabel="关闭流水规则标签管理"
        footer={(
          <div className="bank-flow-rule-batches-drawer__actions">
            <Button
              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact bank-flow-rule-batches-button--primary"
              isDisabled={!canOperateData || tagLoading || mutating || !tagDraftDirty}
              isPending={mutating}
              onPress={saveTagSelection}
              size="sm"
              variant="primary"
            >
              保存
            </Button>
          </div>
        )}
        onClose={closeTagDrawer}
        open={tagDrawerOpen}
        title="流水规则标签管理"
        width="min(960px, 92vw)"
      >
            <div className="bank-flow-rule-batches-drawer__body">
              <FinanceTable ariaLabel="流水规则标签配置" className="bank-flow-rule-batches-drawer__grid bank-flow-rule-batches-drawer__grid-wrap" minWidth={720} scrollMode="contained">
                  <FinanceTableHeader>
                      <FinanceTableColumn className="bank-flow-rule-batches-drawer__direction-col" columnRole="direction">收支类型</FinanceTableColumn>
                      <FinanceTableColumn columnRole="identity" isRowHeader>流水主标签</FinanceTableColumn>
                      <FinanceTableColumn columnRole="description">流水子标签</FinanceTableColumn>
                      <FinanceTableColumn className="bank-flow-rule-batches-drawer__check-col" columnRole="selection">需要 OA</FinanceTableColumn>
                      <FinanceTableColumn className="bank-flow-rule-batches-drawer__check-col" columnRole="selection">需要发票</FinanceTableColumn>
                  </FinanceTableHeader>
                  <FinanceTableBody>
                    {drawerRows.map(({
                      tag,
                      direction,
                      directionKey,
                      primaryLabel,
                      subLabel,
                    }) => {
                      const rule = requirementFor(draftTagRequirements, tag.code);
                      const rowLabel = subLabel === SELF_SUB_LABEL ? primaryLabel : `${primaryLabel} / ${subLabel}`;
                      return (
                        <FinanceTableRow
                          className="bank-flow-rule-batches-drawer__grid-row"
                          id={tag.code}
                          key={tag.code}
                        >
                            <FinanceTableCell
                              className={cx(
                                "bank-flow-rule-batches-drawer__direction-cell",
                                `bank-flow-rule-batches-drawer__direction-cell--${directionKey}`,
                              )}
                              columnRole="direction"
                            >
                              {direction}
                            </FinanceTableCell>
                            <FinanceTableCell className="bank-flow-rule-batches-drawer__primary-cell" columnRole="identity">
                              {primaryLabel}
                            </FinanceTableCell>
                          <FinanceTableCell columnRole="description">{subLabel}</FinanceTableCell>
                          <FinanceTableCell className="bank-flow-rule-batches-drawer__check-col" columnRole="selection">
                            <Checkbox
                              aria-label={`${rowLabel} 需要OA`}
                              className="bank-flow-rule-batches-checkbox"
                              isDisabled={!canOperateData || tagLoading || mutating}
                              isSelected={rule.requiresOa}
                              onChange={(selected) => updateDraftRequirement(tag.code, "requiresOa", selected)}
                            >
                              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                            </Checkbox>
                          </FinanceTableCell>
                          <FinanceTableCell className="bank-flow-rule-batches-drawer__check-col" columnRole="selection">
                            <Checkbox
                              aria-label={`${rowLabel} 需要发票`}
                              className="bank-flow-rule-batches-checkbox"
                              isDisabled={!canOperateData || tagLoading || mutating}
                              isSelected={rule.requiresInvoice}
                              onChange={(selected) => updateDraftRequirement(tag.code, "requiresInvoice", selected)}
                            >
                              <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                            </Checkbox>
                          </FinanceTableCell>
                        </FinanceTableRow>
                      );
                    })}
                  </FinanceTableBody>
              </FinanceTable>
            </div>
      </AppDrawer>

      <AppDialog open={discardTagChangesOpen} title="放弃未保存的修改？" maxWidth="xs"
        onClose={() => setDiscardTagChangesOpen(false)} actions={<>
          <Button variant="secondary" onPress={() => setDiscardTagChangesOpen(false)}>继续编辑</Button>
          <Button variant="danger" onPress={() => { setDiscardTagChangesOpen(false); setTagDrawerOpen(false); setDraftTagRequirements(requirementsFromSelection(tagSelection)); }}>放弃修改</Button>
        </>}>
        流水关联要求尚未保存。
      </AppDialog>

      <AppDialog
        maxWidth="xs"
        onClose={() => setWithdrawTarget(null)}
        open={Boolean(withdrawTarget)}
        title="撤回批次"
        actions={(
          <>
            <button className="bank-flow-rule-batches-button" onClick={() => setWithdrawTarget(null)} type="button">
              取消
            </button>
            <button
              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--primary"
              disabled={!withdrawReason.trim() || mutating}
              onClick={handleConfirmWithdraw}
              type="button"
            >
              确认撤回
            </button>
          </>
        )}
      >
        <div className="bank-flow-rule-batches-dialog">
          <div className="bank-flow-rule-batches-notice bank-flow-rule-batches-notice--warning" role="alert">
            撤回后会取消关联台闭环关系，相关流水回到未配对区域。
          </div>
          <label className="bank-flow-rule-batches-dialog__field">
            <span>撤回原因</span>
            <textarea
              autoFocus
              onChange={(event) => setWithdrawReason(event.target.value)}
              rows={3}
              value={withdrawReason}
            />
          </label>
        </div>
      </AppDialog>

      {feedback ? (
        <div className={cx("bank-flow-rule-batches-toast", `bank-flow-rule-batches-toast--${feedback.severity}`)} role="alert">
          <span>{feedback.message}</span>
          <button aria-label="关闭提示" onClick={() => setFeedback(null)} type="button">×</button>
        </div>
      ) : null}
      <BankTransactionDrawer transactionId={bankDetailRow?.transactionId ?? null} onClose={() => setBankDetailRow(null)}
        onSaved={async () => { await reloadBatchesAfterMutation(); }}
        />
    </PageScaffold>
  );
}
