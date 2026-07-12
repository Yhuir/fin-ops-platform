import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { RefreshCw } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
} from "../features/domainEvents";
import { useActivePageEvent, useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { useSessionPermissions } from "../contexts/SessionContext";
import { operationBarrierTargets, waitForOperationFreshness } from "../features/operationBarrier/api";
import {
  fetchBankFlowRuleBatchDetail,
  fetchBankFlowRuleBatchTagSelection,
  fetchBankFlowRuleBatches,
  resetSubmittedBankFlowRuleBatches,
  saveBankFlowRuleBatchTagSelection,
  submitBankFlowRuleBatch,
  submitBankFlowRuleBatchSelection,
  withdrawBankFlowRuleBatch,
} from "../features/bankFlowRuleBatches/api";
import {
  canSelectBatchRows,
  canSubmitInternalTransferBatch,
  canWithdrawBatch,
  statusBucketFor,
} from "../features/bankFlowRuleBatches/policy";
import { BatchStatusTag, LabelRail, PageControls } from "../features/bankFlowRuleBatches/components";
import type { LabelRailGroup } from "../features/bankFlowRuleBatches/components";
import {
  BANK_FLOW_RULE_BATCH_READ_MODEL_KEY,
  accountLabel,
  bankDetailTagLabels,
  bankTagLabel,
  batchBlockingReason,
  buildTagDrawerRows,
  currentMonth,
  cx,
  directionTagLabel,
  formatMoney,
  isAbortLikeError,
  mutationBarrierTargets,
  mutationEventDetail,
  relationContextLabels,
  requirementFor,
  requirementsFromSelection,
  tagDrawerGroupColor,
  tagPrimaryLabel,
  tagSubLabel,
} from "../features/bankFlowRuleBatches/viewModel";
import type {
  BankFlowRuleDraftRequirements,
  BankFlowRuleTagNode,
} from "../features/bankFlowRuleBatches/viewModel";
import type {
  BankFlowRuleBatch,
  BankFlowRuleBatchDetail,
  BankFlowRuleBatchesResponse,
  BankFlowRuleBatchReadModelStatus,
  BankFlowRuleBatchStatus,
  BankFlowRuleBatchStatusBucket,
  BankFlowRuleBatchDetailRow,
  BankFlowRuleBatchTagRule,
  BankFlowRuleBatchTagSelection,
} from "../features/bankFlowRuleBatches/types";

const EMPTY_BATCHES: BankFlowRuleBatchesResponse = {
  summary: {
    draftCount: 0,
    submittedCount: 0,
    withdrawnCount: 0,
    conflictCount: 0,
    staleCount: 0,
    totalAmount: "0.00",
    categories: [],
  },
  batches: [],
  readModelStatus: "refreshing",
  readModelStaleReasons: [],
};

const EMPTY_TAG_SELECTION: BankFlowRuleBatchTagSelection = {
  version: 1,
  bankAutoTagRulesVersion: 1,
  activeTags: [],
  rules: [],
  requirementsByTagCode: {},
};

const SELF_SUB_LABEL = "主标签本身";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const BANK_FLOW_RULE_READ_MODEL_REFRESH_RETRY_MS = 1000;
const BANK_FLOW_RULE_BATCH_PAGE_SIZE = 200;

export default function BankFlowRuleBatchPage() {
  const { runOperation } = useGlobalOperationOverlay();
  const { active } = useOptionalPageActivation("bank-flow-rule-batches");
  const { canAdminAccess, canMutateData } = useSessionPermissions();
  const [month, setMonth] = useState(currentMonth);
  const [bucket, setBucket] = useState<BankFlowRuleBatchStatusBucket>("unsubmitted");
  const [payload, setPayload] = useState<BankFlowRuleBatchesResponse>(EMPTY_BATCHES);
  const [tagSelection, setTagSelection] = useState<BankFlowRuleBatchTagSelection>(EMPTY_TAG_SELECTION);
  const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
  const [draftTagRequirements, setDraftTagRequirements] = useState<BankFlowRuleDraftRequirements>(() => ({}));
  const [selectedPrimaryLabel, setSelectedPrimaryLabel] = useState("");
  const [selectedSubKey, setSelectedSubKey] = useState("");
  const [details, setDetails] = useState<Record<string, BankFlowRuleBatchDetail>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [selectedTransactionIds, setSelectedTransactionIds] = useState<Set<string>>(() => new Set());
  const [selectedAccountForSubmit, setSelectedAccountForSubmit] = useState<string | null>(null);
  const [batchPage, setBatchPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [backgroundRefreshing, setBackgroundRefreshing] = useState(false);
  const [tagLoading, setTagLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<BankFlowRuleBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [feedback, setFeedback] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const batchRequestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);
  const batchQueryKeyRef = useRef("");
  const manualLabelSelectionRef = useRef(false);
  const suppressNextAutoSelectRef = useRef(false);
  const readModelStatus = payload.readModelStatus;
  const readModelNeedsRefresh = readModelStatus !== "fresh";

  const loadTagSelection = useCallback((signal?: AbortSignal) => {
    setTagLoading(true);
    fetchBankFlowRuleBatchTagSelection(signal)
      .then((nextSelection) => {
        setTagSelection(nextSelection);
        setDraftTagRequirements(requirementsFromSelection(nextSelection));
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setFeedback({ severity: "error", message: caught instanceof Error ? caught.message : "流水标签配置加载失败" });
        }
      })
      .finally(() => setTagLoading(false));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedTransactionIds(new Set());
    setSelectedAccountForSubmit(null);
  }, []);

  const applyBatchesPayload = useCallback((nextPayload: BankFlowRuleBatchesResponse) => {
    setPayload(nextPayload);
    clearSelection();
  }, [clearSelection]);

  const reloadBatchesAfterMutation = useCallback(async () => {
    const requestId = batchRequestSeqRef.current + 1;
    batchRequestSeqRef.current = requestId;
    const nextPayload = await fetchBankFlowRuleBatches({
      month,
      bucket,
      page: batchPage,
      pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE,
    });
    if (requestId !== batchRequestSeqRef.current) {
      return null;
    }
    applyBatchesPayload(nextPayload);
    setLoading(false);
    setBackgroundRefreshing(false);
    return nextPayload;
  }, [applyBatchesPayload, batchPage, bucket, month]);

  const loadBatches = useCallback((signal?: AbortSignal, options: { background?: boolean } = {}) => {
    const background = options.background === true;
    const requestId = batchRequestSeqRef.current + 1;
    batchRequestSeqRef.current = requestId;
    if (background) {
      setBackgroundRefreshing(true);
    } else {
      setLoading(true);
      setError(null);
    }
    fetchBankFlowRuleBatches({
      month,
      bucket,
      page: batchPage,
      pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE,
      signal,
    })
      .then((nextPayload) => {
        if (signal?.aborted || requestId !== batchRequestSeqRef.current) {
          return;
        }
        applyBatchesPayload(nextPayload);
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== batchRequestSeqRef.current) {
          return;
        }
        if (!background && !isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "流水规则批次加载失败");
        }
      })
      .finally(() => {
        if (background && requestId !== batchRequestSeqRef.current) {
          setBackgroundRefreshing(false);
          return;
        }
        if (!signal?.aborted && requestId === batchRequestSeqRef.current) {
          if (background) {
            setBackgroundRefreshing(false);
          } else {
            setLoading(false);
          }
        }
      });
  }, [applyBatchesPayload, batchPage, bucket, month]);

  useEffect(() => {
    const controller = new AbortController();
    loadTagSelection(controller.signal);
    return () => controller.abort();
  }, [loadTagSelection]);

  useEffect(() => {
    const controller = new AbortController();
    const batchQueryKey = JSON.stringify({ bucket, month, page: batchPage });
    if (batchQueryKeyRef.current !== batchQueryKey) {
      batchQueryKeyRef.current = batchQueryKey;
      setDetails({});
      setDetailErrors({});
      setSelectedBatchId("");
    }
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [batchPage, bucket, loadBatches, month, refreshToken]);

  useEffect(() => {
    if (!active || !readModelNeedsRefresh || loading || backgroundRefreshing) {
      return undefined;
    }
    const retryId = window.setTimeout(() => {
      loadBatches(undefined, { background: true });
    }, BANK_FLOW_RULE_READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [active, backgroundRefreshing, loadBatches, loading, readModelNeedsRefresh]);

  const tagNodesByCode = useMemo(() => {
    const nodes = new Map<string, BankFlowRuleTagNode>();
    tagSelection.activeTags.forEach((tag) => {
      nodes.set(tag.code, {
        code: tag.code,
        label: tag.label || tag.code,
        primaryLabel: tagPrimaryLabel(tag) || tag.label || tag.code,
        subLabel: tagSubLabel(tag),
      });
    });
    payload.summary.categories.forEach((category) => {
      if (!nodes.has(category.code)) {
        nodes.set(category.code, {
          code: category.code,
          label: category.label || category.code,
          primaryLabel: tagPrimaryLabel(category) || category.label || category.code,
          subLabel: tagSubLabel(category),
        });
      }
    });
    payload.batches.forEach((batch) => {
      if (!nodes.has(batch.batchType)) {
        nodes.set(batch.batchType, {
          code: batch.batchType,
          label: batch.batchLabel || batch.batchType,
          primaryLabel: tagPrimaryLabel(batch) || batch.batchLabel || batch.batchType,
          subLabel: tagSubLabel(batch),
        });
      }
    });
    return nodes;
  }, [payload.batches, payload.summary.categories, tagSelection.activeTags]);

  const visibleBucketBatches = useMemo(
    () => payload.batches.filter((batch) => statusBucketFor(batch) === bucket),
    [bucket, payload.batches],
  );

  const primaryGroups = useMemo(() => {
    const groups = new Map<string, { primaryLabel: string; codes: string[]; batchCount: number; rowCount: number }>();
    tagNodesByCode.forEach((node) => {
      if (!groups.has(node.primaryLabel)) {
        groups.set(node.primaryLabel, { primaryLabel: node.primaryLabel, codes: [], batchCount: 0, rowCount: 0 });
      }
      groups.get(node.primaryLabel)?.codes.push(node.code);
    });
    visibleBucketBatches.forEach((batch) => {
      const node = tagNodesByCode.get(batch.batchType);
      if (!node) {
        return;
      }
      const group = groups.get(node.primaryLabel);
      if (group) {
        group.batchCount += 1;
        group.rowCount += batch.rowCount;
      }
    });
    return Array.from(groups.values());
  }, [tagNodesByCode, visibleBucketBatches]);

  useEffect(() => {
    if (primaryGroups.length === 0) {
      setSelectedPrimaryLabel("");
      setSelectedSubKey("");
      return;
    }
    const selectedGroup = primaryGroups.find((group) => group.primaryLabel === selectedPrimaryLabel);
    const preferredGroup = primaryGroups.find((group) => group.batchCount > 0);
    if (!selectedGroup) {
      const nextGroup = preferredGroup ?? (!loading ? primaryGroups[0] : null);
      if (nextGroup) {
        setSelectedPrimaryLabel(nextGroup.primaryLabel);
      }
      return;
    }
    if (!manualLabelSelectionRef.current && preferredGroup && selectedGroup.batchCount === 0) {
      setSelectedPrimaryLabel(preferredGroup.primaryLabel);
    }
  }, [loading, primaryGroups, selectedPrimaryLabel]);

  const subGroups = useMemo(() => {
    const groups = new Map<string, { key: string; label: string; codes: string[]; batchCount: number; rowCount: number }>();
    tagNodesByCode.forEach((node) => {
      if (node.primaryLabel !== selectedPrimaryLabel) {
        return;
      }
      const key = node.subLabel || SELF_SUB_LABEL;
      if (!groups.has(key)) {
        groups.set(key, { key, label: key, codes: [], batchCount: 0, rowCount: 0 });
      }
      groups.get(key)?.codes.push(node.code);
    });
    visibleBucketBatches.forEach((batch) => {
      const node = tagNodesByCode.get(batch.batchType);
      if (!node || node.primaryLabel !== selectedPrimaryLabel) {
        return;
      }
      const key = node.subLabel || SELF_SUB_LABEL;
      const group = groups.get(key);
      if (group) {
        group.batchCount += 1;
        group.rowCount += batch.rowCount;
      }
    });
    return Array.from(groups.values());
  }, [selectedPrimaryLabel, tagNodesByCode, visibleBucketBatches]);

  useEffect(() => {
    if (subGroups.length === 0) {
      setSelectedSubKey("");
      return;
    }
    const selectedGroup = subGroups.find((group) => group.key === selectedSubKey);
    const preferredGroup = subGroups.find((group) => group.batchCount > 0);
    if (!selectedGroup) {
      const nextGroup = preferredGroup ?? (!loading ? subGroups[0] : null);
      if (nextGroup) {
        setSelectedSubKey(nextGroup.key);
      }
      return;
    }
    if (!manualLabelSelectionRef.current && preferredGroup && selectedGroup.batchCount === 0) {
      setSelectedSubKey(preferredGroup.key);
    }
  }, [loading, selectedSubKey, subGroups]);

  const selectedSubGroup = subGroups.find((group) => group.key === selectedSubKey) ?? null;
  const visibleBatches = useMemo(() => {
    const codes = new Set(selectedSubGroup?.codes ?? []);
    return visibleBucketBatches.filter((batch) => codes.has(batch.batchType));
  }, [selectedSubGroup, visibleBucketBatches]);
  const listPagination = payload.pagination ?? {
    page: batchPage,
    pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE,
    total: payload.batches.length,
  };

  useEffect(() => {
    if (visibleBatches.length === 0) {
      setSelectedBatchId("");
      suppressNextAutoSelectRef.current = false;
      return;
    }
    if (!selectedBatchId && suppressNextAutoSelectRef.current) {
      return;
    }
    if (!visibleBatches.some((batch) => batch.batchId === selectedBatchId)) {
      setSelectedBatchId(visibleBatches[0].batchId);
    }
  }, [selectedBatchId, visibleBatches]);

  useEffect(() => {
    if (!selectedBatchId || details[selectedBatchId] || detailErrors[selectedBatchId]) {
      return undefined;
    }
    const controller = new AbortController();
    const requestId = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestId;
    let cancelled = false;
    fetchBankFlowRuleBatchDetail(selectedBatchId, controller.signal)
      .then((detail) => {
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetails((current) => ({ ...current, [selectedBatchId]: detail }));
        }
      })
      .catch((caught) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetailErrors((current) => ({
            ...current,
            [selectedBatchId]: caught instanceof Error ? caught.message : "批次明细加载失败",
          }));
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [detailErrors, details, selectedBatchId]);

  const handleCategoryUpdated = useCallback(() => {
    setDetails({});
    loadTagSelection();
    loadBatches();
  }, [loadBatches, loadTagSelection]);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleCategoryUpdated);
  useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankAutoTagRulesUpdated, handleCategoryUpdated);
  useActivePageEvent(TAG_SYNC_EVENT, handleCategoryUpdated);

  useEffect(() => {
    if (!feedback) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  useEffect(() => {
    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.onmessage = () => {
        window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT));
      };
    }

    return () => {
      channel?.close();
    };
  }, []);

  const handleMutationComplete = useCallback((message: string, result: { affectedMonths?: string[] }) => {
    suppressNextAutoSelectRef.current = true;
    setSelectedBatchId("");
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      ...mutationEventDetail(result),
    });
    clearSelection();
    setDetails({});
    setDetailErrors({});
    setFeedback({ severity: "success", message });
  }, [clearSelection]);

  const applySubmittedBatchLocally = useCallback((batch: BankFlowRuleBatch, submittedBatch: BankFlowRuleBatch | null) => {
    suppressNextAutoSelectRef.current = true;
    setSelectedBatchId("");
    setPayload((current) => {
      const existingBatch = current.batches.find((item) => item.batchId === batch.batchId);
      if (!existingBatch) {
        return current;
      }
      const nextBatches = current.batches.filter((item) => item.batchId !== batch.batchId);
      return {
        ...current,
        summary: {
          ...current.summary,
          draftCount: Math.max(0, current.summary.draftCount - 1),
          submittedCount: current.summary.submittedCount + 1,
          categories: current.summary.categories.map((category) => (
            category.code === batch.batchType
              ? {
                ...category,
                draft: Math.max(0, category.draft - 1),
                submitted: category.submitted + 1,
              }
              : category
          )),
        },
        batches: submittedBatch && bucket === "submitted"
          ? [...nextBatches, submittedBatch]
          : nextBatches,
        pagination: current.pagination
          ? { ...current.pagination, total: Math.max(0, current.pagination.total - 1) }
          : current.pagination,
      };
    });
    setDetails((current) => {
      const next = { ...current };
      delete next[batch.batchId];
      return next;
    });
    setDetailErrors((current) => {
      const next = { ...current };
      delete next[batch.batchId];
      return next;
    });
  }, [bucket]);

  const reconcileMutationInBackground = useCallback((result: {
    affectedMonths?: string[];
    freshnessTargets?: Parameters<typeof mutationBarrierTargets>[0]["freshnessTargets"];
    operationBarrierTargets?: Parameters<typeof mutationBarrierTargets>[0]["operationBarrierTargets"];
  }, fallbackScopeKey: string) => {
    void (async () => {
      try {
        await waitForOperationFreshness(
          mutationBarrierTargets(result, fallbackScopeKey),
        );
        await reloadBatchesAfterMutation();
      } catch (caught) {
        setFeedback({
          severity: "warning",
          message: caught instanceof Error ? caught.message : "流水规则批次已提交，后台同步状态检查失败，请稍后刷新。",
        });
      }
    })();
  }, [reloadBatchesAfterMutation]);

  const toggleTransaction = (row: BankFlowRuleBatchDetailRow, checked: boolean) => {
    setSelectedTransactionIds((current) => {
      const next = new Set(current);
      if (!checked) {
        next.delete(row.transactionId);
        if (next.size === 0) {
          setSelectedAccountForSubmit(null);
        }
        return next;
      }
      if (selectedAccountForSubmit && selectedAccountForSubmit !== row.accountKey) {
        setFeedback({ severity: "warning", message: "请先清空当前选择，再选择其他流水。" });
        return current;
      }
      setSelectedAccountForSubmit(row.accountKey);
      next.add(row.transactionId);
      return next;
    });
  };

  const setRegionSelection = (rows: BankFlowRuleBatchDetailRow[], checked: boolean) => {
    if (!checked) {
      setSelectedTransactionIds((current) => {
        const next = new Set(current);
        rows.forEach((row) => next.delete(row.transactionId));
        if (next.size === 0) {
          setSelectedAccountForSubmit(null);
        }
        return next;
      });
      return;
    }
    const account = rows[0]?.accountKey;
    if (!account) {
      return;
    }
    if (selectedAccountForSubmit && selectedAccountForSubmit !== account) {
      setFeedback({ severity: "warning", message: "请先清空当前选择，再选择其他流水。" });
      return;
    }
    setSelectedAccountForSubmit(account);
    setSelectedTransactionIds((current) => new Set([...current, ...rows.map((row) => row.transactionId)]));
  };

  const handleSubmitSelected = async () => {
    if (!canMutateData || selectedTransactionIds.size === 0 || mutating) {
      return;
    }
    const transactionIds = Array.from(selectedTransactionIds);
    const result = await runOperation({
      loadingMessage: "正在提交选中流水规则...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBankFlowRuleBatchSelection({
            transactionIds,
            note: "",
          });
          setMessage("正在更新流水规则批次...");
          reconcileMutationInBackground(submitResult, month);
          return submitResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "提交选中流水失败",
    });
    if (result.status === "success") {
      handleMutationComplete("选中流水已提交", result.value);
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "提交选中流水失败" });
    }
  };

  const handleSubmitBatch = async (batch: BankFlowRuleBatch) => {
    if (!canMutateData || !canSubmitInternalTransferBatch(batch, bucket) || mutating) {
      return;
    }
    const result = await runOperation({
      loadingMessage: "正在提交内部往来流水规则批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBankFlowRuleBatch({
            batchId: batch.batchId,
            expectedVersion: batch.version,
            note: "",
          });
          applySubmittedBatchLocally(batch, submitResult.batch);
          setMessage("正在更新流水规则批次...");
          reconcileMutationInBackground(submitResult, batch.scopeMonth || month);
          return submitResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "提交内部往来批次失败",
    });
    if (result.status === "success") {
      handleMutationComplete("内部往来批次已提交", result.value);
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "提交内部往来批次失败" });
    }
  };

  const handleConfirmWithdraw = async () => {
    if (!canMutateData || !withdrawTarget || !withdrawReason.trim() || mutating) {
      return;
    }
    const target = withdrawTarget;
    const reason = withdrawReason.trim();
    const result = await runOperation({
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
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(
            mutationBarrierTargets(withdrawResult, target.scopeMonth || month),
          );
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
          return withdrawResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "撤回批次失败",
    });
    if (result.status === "success") {
      handleMutationComplete("批次已撤回", result.value);
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "撤回批次失败" });
    }
  };

  const handleResetSubmitted = async () => {
    if (!canMutateData || mutating) {
      return;
    }
    const result = await runOperation({
      loadingMessage: "正在重置已提交流水规则批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const resetResult = await resetSubmittedBankFlowRuleBatches({
            reason: "流水规则批量处理：全部已提交批次重新过规则",
          });
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(
            mutationBarrierTargets(resetResult, month),
          );
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
          return resetResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "重置已提交批次失败",
    });
    if (result.status === "success") {
      setBucket("unsubmitted");
      setBatchPage(1);
      handleMutationComplete(`已重置 ${result.value.results.length} 个已提交批次`, result.value);
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "重置已提交批次失败" });
    }
  };

  const saveTagSelection = async () => {
    if (!canMutateData || mutating) {
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
    const result = await runOperation({
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
          setTagDrawerOpen(false);
          setDetails({});
          setDetailErrors({});
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(operationBarrierTargets(BANK_FLOW_RULE_BATCH_READ_MODEL_KEY, ["all"]));
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
          return saved;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "保存流水规则失败",
    });
    if (result.status === "success") {
      setFeedback({ severity: "success", message: "流水规则已保存" });
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "保存流水规则失败" });
    }
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

  const unsubmittedCount = payload.summary.draftCount;
  const resetListScope = useCallback(() => {
    clearSelection();
    suppressNextAutoSelectRef.current = false;
    manualLabelSelectionRef.current = false;
    setSelectedPrimaryLabel("");
    setSelectedSubKey("");
    setSelectedBatchId("");
    setDetails({});
    setDetailErrors({});
  }, [clearSelection]);

  const selectBucket = (nextBucket: BankFlowRuleBatchStatusBucket) => {
    if (nextBucket === bucket) {
      return;
    }
    resetListScope();
    setBatchPage(1);
    setBucket(nextBucket);
  };

  const handleMonthChange = (nextMonth: string) => {
    resetListScope();
    setBatchPage(1);
    setMonth(nextMonth);
  };

  const handlePageChange = (nextPage: number) => {
    resetListScope();
    setBatchPage(Math.max(1, nextPage));
  };

  const titleAccessory = canAdminAccess ? (
    <PageBusinessAuditIcon
      ariaLabel="Audit 流水规则批量处理"
      pageKey="bank-flow-rule-batches"
      label="流水规则批量处理"
      readModelStatus={readModelStatus}
    />
  ) : null;

  return (
    <PageScaffold
      title="流水规则批量处理"
      titleAccessory={titleAccessory}
      actions={(
        <div className="bank-flow-rule-batches-actions">
          <button
            className="bank-flow-rule-batches-button"
            disabled={tagLoading}
            type="button"
            onClick={() => {
              loadTagSelection();
              setTagDrawerOpen(true);
            }}
          >
            流水规则标签管理
          </button>
          <button
            className="bank-flow-rule-batches-button"
            disabled={loading}
            type="button"
            onClick={() => {
              setDetails({});
              loadTagSelection();
              setRefreshToken((current) => current + 1);
            }}
          >
            <RefreshCw aria-hidden="true" size={16} strokeWidth={2.2} />
            刷新
          </button>
        </div>
      )}
    >
      {!canMutateData ? (
        <StatePanel compact tone="warning">当前账号仅支持查看和导出，不能提交、撤回或保存流水规则批次。</StatePanel>
      ) : null}
      <div aria-label="批次筛选" className="bank-flow-rule-batches-filter" role="region">
        <div aria-label="批次状态" className="bank-flow-rule-batches-segment" role="group">
          <button
            aria-pressed={bucket === "unsubmitted"}
            className={cx("bank-flow-rule-batches-segment__button", bucket === "unsubmitted" && "bank-flow-rule-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("unsubmitted")}
          >
            未提交 {unsubmittedCount}
          </button>
          <button
            aria-pressed={bucket === "submitted"}
            className={cx("bank-flow-rule-batches-segment__button", bucket === "submitted" && "bank-flow-rule-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("submitted")}
          >
            已提交 {payload.summary.submittedCount}
          </button>
          <button
            aria-pressed={bucket === "withdrawn"}
            className={cx("bank-flow-rule-batches-segment__button", bucket === "withdrawn" && "bank-flow-rule-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("withdrawn")}
          >
            历史 {payload.summary.withdrawnCount}
          </button>
        </div>
        <label className="bank-flow-rule-batches-field">
          <span>月份</span>
          <input onChange={(event) => handleMonthChange(event.target.value)} type="month" value={month} />
        </label>
        <PageControls
          disabled={loading}
          label="流水规则批次分页"
          onNext={() => handlePageChange(listPagination.page + 1)}
          onPrevious={() => handlePageChange(listPagination.page - 1)}
          page={listPagination.page}
          pageSize={listPagination.pageSize}
          total={listPagination.total}
        />
        {bucket === "unsubmitted" && canMutateData ? (
          <button
            className="bank-flow-rule-batches-button bank-flow-rule-batches-button--primary"
            disabled={selectedTransactionIds.size === 0 || mutating}
            type="button"
            onClick={handleSubmitSelected}
          >
            提交批次
          </button>
        ) : null}
        {canMutateData && payload.summary.submittedCount > 0 ? (
          <button
            className="bank-flow-rule-batches-button"
            disabled={mutating}
            type="button"
            onClick={handleResetSubmitted}
          >
            重置全部已提交
          </button>
        ) : null}
          {selectedTransactionIds.size > 0 ? (
            <span className="bank-flow-rule-batches-selected-count">
              已选 {selectedTransactionIds.size} 条
            </span>
          ) : null}
      </div>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <div className="bank-flow-rule-batches-layout">
        <LabelRail
          ariaLabel="主标签"
          emptyTitle="请先在标签管理中选择流水标签"
          groups={primaryGroups.map((group) => ({
            key: group.primaryLabel,
            label: group.primaryLabel,
            batchCount: group.batchCount,
            rowCount: group.rowCount,
          }))}
          onSelect={(primaryLabel) => {
            clearSelection();
            manualLabelSelectionRef.current = true;
            setSelectedPrimaryLabel(primaryLabel);
          }}
          selectedKey={selectedPrimaryLabel}
          title="主标签"
        />

        <LabelRail
          ariaLabel="子标签"
          emptyTitle="暂无子标签"
          groups={subGroups.map((group) => ({
            key: group.key,
            label: group.label,
            batchCount: group.batchCount,
            rowCount: group.rowCount,
          }))}
          onSelect={(subKey) => {
            clearSelection();
            manualLabelSelectionRef.current = true;
            setSelectedSubKey(subKey);
          }}
          selectedKey={selectedSubKey}
          title="子标签"
        />

        <section aria-label="流水" className="bank-flow-rule-batches-transactions" role="region">
          <header className="bank-flow-rule-batches-transactions__header">
            <div className="bank-flow-rule-batches-transactions__heading">
              <h2 className="bank-flow-rule-batches-transactions__title">
                {selectedPrimaryLabel && selectedSubKey ? `${selectedPrimaryLabel} / ${selectedSubKey}` : "流水"}
              </h2>
            </div>
          </header>
          <div className="bank-flow-rule-batches-transactions__list">
            {loading ? <StatePanel compact tone="loading" title="流水加载中" /> : null}
            {!loading && !error && visibleBatches.length === 0 ? <StatePanel compact tone="empty" title="当前标签下暂无流水" /> : null}
            {!loading ? visibleBatches.map((batch) => {
              const detail = details[batch.batchId];
              const rows = detail?.rows ?? [];
              const selected = selectedBatchId === batch.batchId;
              const rowSelectionEnabled = canSelectBatchRows(batch, bucket);
              const internalTransferSubmitEnabled = canSubmitInternalTransferBatch(batch, bucket);
              const regionChecked = rowSelectionEnabled && rows.length > 0 && rows.every((row) => selectedTransactionIds.has(row.transactionId));
              const blockingReason = batchBlockingReason(batch);
              return (
                <section
                  className={cx(
                    "bank-flow-rule-batches-batch",
                    selected && "bank-flow-rule-batches-batch--selected",
                  )}
                  key={batch.batchId}
                >
                  <div className="bank-flow-rule-batches-batch__body">
                    <div className="bank-flow-rule-batches-batch__header">
                      <div className="bank-flow-rule-batches-batch__summary">
                        <div className="bank-flow-rule-batches-batch__title-row">
                          <h3 className="bank-flow-rule-batches-batch__title">{accountLabel(batch)}</h3>
                          <BatchStatusTag status={batch.status} />
                        </div>
                        <p className="bank-flow-rule-batches-batch__meta">
                          {batch.rowCount} 条 · 合计 {formatMoney(batch.totalAmount)}
                        </p>
                      </div>
                      <div className="bank-flow-rule-batches-batch__actions">
                        {!selected ? (
                          <button
                            aria-label={`查看${accountLabel(batch)}流水`}
                            className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact"
                            onClick={() => setSelectedBatchId(batch.batchId)}
                            type="button"
                          >
                            查看流水
                          </button>
                        ) : null}
                        {selected && rowSelectionEnabled ? (
                          <>
                            <button
                              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact"
                              disabled={!canMutateData || rows.length === 0 || mutating}
                              onClick={() => setRegionSelection(rows, true)}
                              type="button"
                            >
                              全选
                            </button>
                            <button
                              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact"
                              disabled={!canMutateData || rows.length === 0 || mutating}
                              onClick={() => setRegionSelection(rows, false)}
                              type="button"
                            >
                              清空
                            </button>
                          </>
                        ) : null}
                        {internalTransferSubmitEnabled && canMutateData ? (
                          <button
                            className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact bank-flow-rule-batches-button--primary"
                            disabled={mutating}
                            onClick={() => handleSubmitBatch(batch)}
                            type="button"
                          >
                            提交内部往来批次
                          </button>
                        ) : null}
                        {bucket === "submitted" && canMutateData && canWithdrawBatch(batch) ? (
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
                    {blockingReason ? (
                      <div
                        className={cx(
                          "bank-flow-rule-batches-notice",
                          "bank-flow-rule-batches-notice--warning",
                        )}
                        role="alert"
                      >
                        {blockingReason}
                      </div>
                    ) : null}
                    {selected && detailErrors[batch.batchId] ? (
                      <div className="bank-flow-rule-batches-notice bank-flow-rule-batches-notice--error" role="alert">
                        {detailErrors[batch.batchId]}
                      </div>
                    ) : null}
                    {selected && !detail && !detailErrors[batch.batchId] ? <StatePanel compact tone="loading" title="正在加载流水明细" /> : null}
                    {selected && detail && rows.length === 0 ? <StatePanel compact tone="empty" title="暂无流水明细" /> : null}
                    {selected && rows.length > 0 ? (
                      <div className="bank-flow-rule-batches-table-wrap">
                        <table className="bank-flow-rule-batches-table" aria-label={`${accountLabel(batch)}流水`}>
                          <thead>
                            <tr>
                              {rowSelectionEnabled ? (
                                <th className="bank-flow-rule-batches-table__check" scope="col">
                                  <input
                                    aria-label={`${accountLabel(batch)}全选`}
                                    checked={regionChecked}
                                    className="bank-flow-rule-batches-checkbox"
                                    disabled={!canMutateData}
                                    onChange={(event) => setRegionSelection(rows, event.target.checked)}
                                    type="checkbox"
                                  />
                                </th>
                              ) : null}
                              <th scope="col">交易时间</th>
                              <th scope="col">对方户名</th>
                              <th className="bank-flow-rule-batches-table__amount" scope="col">金额</th>
                              <th scope="col">摘要/用途/备注</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((row) => {
                              const rowTagLabels = bankDetailTagLabels(row);
                              const relationLabels = relationContextLabels(row);
                              return (
                                <tr key={row.transactionId}>
                                  {rowSelectionEnabled ? (
                                    <td className="bank-flow-rule-batches-table__check">
                                      <input
                                        aria-label={`选择流水 ${row.transactionId}`}
                                        checked={selectedTransactionIds.has(row.transactionId)}
                                        className="bank-flow-rule-batches-checkbox"
                                        disabled={!canMutateData}
                                        onChange={(event) => toggleTransaction(row, event.target.checked)}
                                        type="checkbox"
                                      />
                                    </td>
                                  ) : null}
                                  <td>{row.tradeTime || "-"}</td>
                                  <td>{row.counterpartyName || "-"}</td>
                                  <td className="bank-flow-rule-batches-table__amount">
                                    <div className="bank-flow-rule-batches-amount-cell">
                                      <div className="bank-flow-rule-batches-amount-cell__main">
                                        <span className="bank-flow-rule-batches-tag bank-flow-rule-batches-tag--direction">
                                          {directionTagLabel(row)}
                                        </span>
                                        <span className="bank-flow-rule-batches-amount">{formatMoney(row.amount)}</span>
                                      </div>
                                      <span className="bank-flow-rule-batches-tag bank-flow-rule-batches-tag--bank">
                                        {bankTagLabel(row)}
                                      </span>
                                    </div>
                                  </td>
                                  <td>
                                    <div className="bank-flow-rule-batches-summary-cell">
                                      <span className="bank-flow-rule-batches-summary-cell__summary">{row.summary || "-"}</span>
                                      <span className="bank-flow-rule-batches-summary-cell__memo">{[row.purpose, row.remark].filter(Boolean).join(" / ") || "-"}</span>
                                      {rowTagLabels.length > 0 ? (
                                        <div aria-label={`银行明细标签 ${row.transactionId}`} className="bank-flow-rule-batches-bank-tags">
                                          {rowTagLabels.map((label) => (
                                            <span className="bank-flow-rule-batches-tag bank-flow-rule-batches-tag--bank-detail" key={label}>{label}</span>
                                          ))}
                                        </div>
                                      ) : null}
                                      {relationLabels.length > 0 ? (
                                        <div className="bank-flow-rule-batches-relation-cell">
                                          {relationLabels.map((label) => (
                                            <span className="bank-flow-rule-batches-tag" key={label}>{label}</span>
                                          ))}
                                        </div>
                                      ) : null}
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                  </div>
                </section>
              );
            }) : null}
          </div>
        </section>
      </div>

      {tagDrawerOpen ? (
        <div className="bank-flow-rule-batches-drawer-shell">
          <button
            aria-label="关闭流水规则标签管理"
            className="bank-flow-rule-batches-drawer-shell__backdrop"
            onClick={() => setTagDrawerOpen(false)}
            type="button"
          />
          <aside aria-label="流水规则标签管理" className="bank-flow-rule-batches-drawer" role="dialog">
            <header className="bank-flow-rule-batches-drawer__header">
              <div>
                <h2 className="bank-flow-rule-batches-drawer__title">流水规则标签管理</h2>
              </div>
              <button
                aria-label="关闭流水规则标签管理"
                className="bank-flow-rule-batches-drawer__close"
                onClick={() => setTagDrawerOpen(false)}
                type="button"
              >
                ×
              </button>
            </header>
            <div className="bank-flow-rule-batches-drawer__body">
              <div className="bank-flow-rule-batches-drawer__grid-wrap">
                <table className="bank-flow-rule-batches-drawer__grid">
                  <colgroup>
                    <col className="bank-flow-rule-batches-drawer__direction-col" />
                    <col />
                    <col />
                    <col className="bank-flow-rule-batches-drawer__check-col" />
                    <col className="bank-flow-rule-batches-drawer__check-col" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">收支类型</th>
                      <th scope="col">流水主标签</th>
                      <th scope="col">流水子标签</th>
                      <th className="bank-flow-rule-batches-drawer__check-col" scope="col">OA</th>
                      <th className="bank-flow-rule-batches-drawer__check-col" scope="col">发票</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drawerRows.map(({
                      tag,
                      direction,
                      directionKey,
                      directionRowSpan,
                      isDirectionStart,
                      primaryLabel,
                      primaryRowSpan,
                      primaryGroupIndex,
                      isPrimaryStart,
                      subLabel,
                    }) => {
                      const rule = requirementFor(draftTagRequirements, tag.code);
                      const rowLabel = subLabel === SELF_SUB_LABEL ? primaryLabel : `${primaryLabel} / ${subLabel}`;
                      return (
                        <tr
                          className="bank-flow-rule-batches-drawer__grid-row"
                          data-primary-label={primaryLabel}
                          data-tag-code={tag.code}
                          key={tag.code}
                          style={{
                            "--bank-flow-rule-batches-drawer-group-bg": tagDrawerGroupColor(primaryGroupIndex),
                          } as CSSProperties}
                        >
                          {isDirectionStart ? (
                            <td
                              className={cx(
                                "bank-flow-rule-batches-drawer__direction-cell",
                                `bank-flow-rule-batches-drawer__direction-cell--${directionKey}`,
                              )}
                              rowSpan={directionRowSpan}
                            >
                              {direction}
                            </td>
                          ) : null}
                          {isPrimaryStart ? (
                            <td className="bank-flow-rule-batches-drawer__primary-cell" rowSpan={primaryRowSpan}>
                              {primaryLabel}
                            </td>
                          ) : null}
                          <td>{subLabel}</td>
                          <td className="bank-flow-rule-batches-drawer__check-col">
                            <input
                              aria-label={`${rowLabel} 需要OA`}
                              checked={rule.requiresOa}
                              className="bank-flow-rule-batches-checkbox"
                              disabled={!canMutateData || tagLoading}
                              onChange={(event) => updateDraftRequirement(tag.code, "requiresOa", event.target.checked)}
                              type="checkbox"
                            />
                          </td>
                          <td className="bank-flow-rule-batches-drawer__check-col">
                            <input
                              aria-label={`${rowLabel} 需要发票`}
                              checked={rule.requiresInvoice}
                              className="bank-flow-rule-batches-checkbox"
                              disabled={!canMutateData || tagLoading}
                              onChange={(event) => updateDraftRequirement(tag.code, "requiresInvoice", event.target.checked)}
                              type="checkbox"
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <footer className="bank-flow-rule-batches-drawer__footer">
              <div className="bank-flow-rule-batches-drawer__actions">
                <button
                  className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact bank-flow-rule-batches-button--primary"
                  disabled={!canMutateData || mutating}
                  onClick={saveTagSelection}
                  type="button"
                >
                  保存
                </button>
              </div>
            </footer>
          </aside>
        </div>
      ) : null}

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
    </PageScaffold>
  );
}
