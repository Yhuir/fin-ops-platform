import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { RefreshCw } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import AppDrawer from "../components/common/AppDrawer";
import PageScaffold from "../components/common/PageScaffold";
import PageBusinessAuditIcon from "../components/common/PageBusinessAuditIcon";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { ApiClientError } from "../features/apiClient";
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
  accountLabel,
  bankDetailTagLabels,
  bankTagLabel,
  batchBlockingReason,
  buildTagDrawerRows,
  categoryCountForBucket,
  categoryRowCountForBucket,
  currentMonth,
  cx,
  directionTagLabel,
  formatMoney,
  isAbortLikeError,
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
  BankFlowRuleBatchStatus,
  BankFlowRuleBatchStatusBucket,
  BankFlowRuleBatchDetailRow,
  BankFlowRuleBatchTagRule,
  BankFlowRuleBatchTagSelection,
} from "../features/bankFlowRuleBatches/types";
import { formatDateTimeText } from "../features/dateTime";

const EMPTY_BATCHES: BankFlowRuleBatchesResponse = {
  summary: {
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
};

const EMPTY_TAG_SELECTION: BankFlowRuleBatchTagSelection = {
  version: 1,
  bankAutoTagRulesVersion: 1,
  activeTags: [],
  rules: [],
  requirementsByTagCode: {},
  eligibilityChanged: false,
  eligibilityChangedTagCodes: [],
  affectedMonths: [],
  affectedScopeKeys: [],
};

const SELF_SUB_LABEL = "主标签本身";
const BANK_FLOW_RULE_BATCH_PAGE_SIZE = 50;
const CANDIDATE_CONFLICT_CODE = "bank_flow_rule_batch_candidate_conflict";
const CANDIDATE_CONFLICT_MESSAGE = "候选已更新，请重新选择。";

function isCandidateConflict(caught: unknown) {
  return caught instanceof ApiClientError && caught.code === CANDIDATE_CONFLICT_CODE;
}

export default function BankFlowRuleBatchPage() {
  const { runOperation } = useGlobalOperationOverlay();
  const { active, activationGeneration } = useOptionalPageActivation("bank-flow-rule-batches");
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
  const [tagLoading, setTagLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<BankFlowRuleBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [feedback, setFeedback] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const tagRequestSeqRef = useRef(0);
  const batchRequestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);
  const batchQueryKeyRef = useRef("");
  const manualLabelSelectionRef = useRef(false);
  const suppressNextAutoSelectRef = useRef(false);

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
    setSelectedAccountForSubmit(null);
  }, []);

  const applyBatchesPayload = useCallback((nextPayload: BankFlowRuleBatchesResponse) => {
    setPayload(nextPayload);
    clearSelection();
  }, [clearSelection]);

  const reloadBatchesAfterMutation = useCallback(async (query?: {
    bucket?: BankFlowRuleBatchStatusBucket;
    page?: number;
  }) => {
    const requestId = batchRequestSeqRef.current + 1;
    batchRequestSeqRef.current = requestId;
    const nextPayload = await fetchBankFlowRuleBatches({
      month,
      bucket: query?.bucket ?? bucket,
      page: query?.page ?? batchPage,
      pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE,
    });
    if (requestId !== batchRequestSeqRef.current) {
      return null;
    }
    applyBatchesPayload(nextPayload);
    setLoading(false);
    return nextPayload;
  }, [applyBatchesPayload, batchPage, bucket, month]);

  const loadBatches = useCallback((signal?: AbortSignal) => {
    const requestId = batchRequestSeqRef.current + 1;
    batchRequestSeqRef.current = requestId;
    setLoading(true);
    setError(null);
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
        if (!isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "流水规则批次加载失败");
        }
      })
      .finally(() => {
        if (!signal?.aborted && requestId === batchRequestSeqRef.current) {
          setLoading(false);
        }
      });
  }, [applyBatchesPayload, batchPage, bucket, month]);

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
    const batchQueryKey = JSON.stringify({ bucket, month, page: batchPage });
    if (batchQueryKeyRef.current !== batchQueryKey) {
      batchQueryKeyRef.current = batchQueryKey;
      setDetails({});
      setDetailErrors({});
      setSelectedBatchId("");
    }
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [active, activationGeneration, batchPage, bucket, loadBatches, month, refreshToken]);

  const tagNodesByCode = useMemo(() => {
    const nodes = new Map<string, BankFlowRuleTagNode>();
    payload.summary.categories.forEach((category) => {
      if (categoryCountForBucket(category, bucket) <= 0) {
        return;
      }
      nodes.set(category.code, {
        code: category.code,
        label: category.label || category.code,
        primaryLabel: tagPrimaryLabel(category) || category.label || category.code,
        subLabel: tagSubLabel(category),
      });
    });
    return nodes;
  }, [bucket, payload.summary.categories]);

  const visibleBucketBatches = useMemo(
    () => payload.batches.filter((batch) => statusBucketFor(batch) === bucket),
    [bucket, payload.batches],
  );

  const primaryGroups = useMemo(() => {
    const groups = new Map<string, { primaryLabel: string; codes: string[]; batchCount: number; rowCount: number }>();
    const categoriesByCode = new Map(payload.summary.categories.map((category) => [category.code, category]));
    tagNodesByCode.forEach((node) => {
      if (!groups.has(node.primaryLabel)) {
        groups.set(node.primaryLabel, { primaryLabel: node.primaryLabel, codes: [], batchCount: 0, rowCount: 0 });
      }
      const group = groups.get(node.primaryLabel);
      if (group) {
        const category = categoriesByCode.get(node.code);
        group.codes.push(node.code);
        group.batchCount += category ? categoryCountForBucket(category, bucket) : 0;
        group.rowCount += category ? categoryRowCountForBucket(category, bucket) : 0;
      }
    });
    return Array.from(groups.values());
  }, [bucket, payload.summary.categories, tagNodesByCode]);

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
    const categoriesByCode = new Map(payload.summary.categories.map((category) => [category.code, category]));
    tagNodesByCode.forEach((node) => {
      if (node.primaryLabel !== selectedPrimaryLabel) {
        return;
      }
      const key = node.subLabel || SELF_SUB_LABEL;
      if (!groups.has(key)) {
        groups.set(key, { key, label: key, codes: [], batchCount: 0, rowCount: 0 });
      }
      const group = groups.get(key);
      if (group) {
        const category = categoriesByCode.get(node.code);
        group.codes.push(node.code);
        group.batchCount += category ? categoryCountForBucket(category, bucket) : 0;
        group.rowCount += category ? categoryRowCountForBucket(category, bucket) : 0;
      }
    });
    return Array.from(groups.values());
  }, [bucket, payload.summary.categories, selectedPrimaryLabel, tagNodesByCode]);

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
  const selectedBatch = visibleBatches.find((batch) => batch.batchId === selectedBatchId) ?? null;
  const listPagination = payload.pagination ?? {
    page: batchPage,
    pageSize: BANK_FLOW_RULE_BATCH_PAGE_SIZE,
    total: payload.batches.length,
  };

  useEffect(() => {
    if (visibleBatches.length === 0) {
      setSelectedBatchId("");
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
    if (!selectedBatch || details[selectedBatch.batchId] || detailErrors[selectedBatch.batchId]) {
      return undefined;
    }
    const batchId = selectedBatch.batchId;
    const controller = new AbortController();
    const requestId = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestId;
    let cancelled = false;
    fetchBankFlowRuleBatchDetail(batchId, selectedBatch.scopeMonth, controller.signal)
      .then((detail) => {
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetails((current) => ({ ...current, [batchId]: detail }));
        }
      })
      .catch((caught) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetailErrors((current) => ({
            ...current,
            [batchId]: caught instanceof Error ? caught.message : "批次明细加载失败",
          }));
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [detailErrors, details, selectedBatch]);

  useEffect(() => {
    if (!feedback) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  const handleMutationComplete = useCallback((message: string) => {
    suppressNextAutoSelectRef.current = true;
    setSelectedBatchId("");
    clearSelection();
    setDetails({});
    setDetailErrors({});
    setFeedback({ severity: "success", message });
  }, [clearSelection]);

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
    if (!selectedBatch?.scopeMonth) {
      setFeedback({ severity: "error", message: "流水规则候选月份缺失，请刷新列表后重试" });
      return;
    }
    const transactionIds = Array.from(selectedTransactionIds);
    const scopeMonth = selectedBatch.scopeMonth;
    const result = await runOperation({
      loadingMessage: "正在提交选中流水规则...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitBankFlowRuleBatchSelection({
            transactionIds,
            scopeMonth,
            note: "",
          });
          setMessage("正在加载流水规则批次最新数据...");
          await reloadBatchesAfterMutation();
          return submitResult;
        } catch (caught) {
          if (isCandidateConflict(caught)) {
            suppressNextAutoSelectRef.current = true;
            setSelectedBatchId("");
            clearSelection();
            setDetails({});
            setDetailErrors({});
            setMessage("候选已变化，正在刷新流水规则批次...");
            await reloadBatchesAfterMutation();
          }
          throw caught;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => isCandidateConflict(caught)
        ? CANDIDATE_CONFLICT_MESSAGE
        : caught instanceof Error ? caught.message : "提交选中流水失败",
    });
    if (result.status === "success") {
      handleMutationComplete("选中流水已提交");
    } else {
      setFeedback({
        severity: "error",
        message: isCandidateConflict(result.error)
          ? CANDIDATE_CONFLICT_MESSAGE
          : result.error instanceof Error ? result.error.message : "提交选中流水失败",
      });
    }
  };

  const handleSubmitBatch = async (batch: BankFlowRuleBatch) => {
    if (!canMutateData || !canSubmitInternalTransferBatch(batch, bucket) || mutating) {
      return;
    }
    const scopeMonth = batch.scopeMonth;
    if (!scopeMonth) {
      setFeedback({ severity: "error", message: "流水规则候选月份缺失，请刷新列表后重试" });
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
            scopeMonth,
            note: "",
          });
          setMessage("正在加载流水规则批次最新数据...");
          await reloadBatchesAfterMutation();
          return submitResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "提交内部往来批次失败",
    });
    if (result.status === "success") {
      handleMutationComplete("内部往来批次已提交");
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
          setMessage("正在加载流水规则批次最新数据...");
          await reloadBatchesAfterMutation();
          return withdrawResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "撤回批次失败",
    });
    if (result.status === "success") {
      handleMutationComplete("批次已撤回");
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
          setBucket("unsubmitted");
          setBatchPage(1);
          setMessage("正在加载未提交批次最新数据...");
          await reloadBatchesAfterMutation({ bucket: "unsubmitted", page: 1 });
          return resetResult;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "重置已提交批次失败",
    });
    if (result.status === "success") {
      handleMutationComplete(`已重置 ${result.value.results.length} 个已提交批次`);
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "重置已提交批次失败" });
    }
  };

  const saveTagSelection = async () => {
    if (!canMutateData || tagLoading || mutating) {
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
          clearSelection();
          setSelectedBatchId("");
          setDetails({});
          setDetailErrors({});
          setMessage("流水规则已保存，正在加载当前页面最新数据...");
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
      auditContextKey={`${month}:${bucket}:${batchPage}:${refreshToken}`}
      ariaLabel="Audit 流水规则批量处理"
      pageKey="bank-flow-rule-batches"
      label="流水规则批量处理"
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
                                  <td>{formatDateTimeText(row.tradeTime)}</td>
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

      <AppDrawer
        ariaBusy={tagLoading || mutating}
        className="bank-flow-rule-batches-drawer"
        closeDisabled={tagLoading || mutating}
        closeLabel="关闭流水规则标签管理"
        footer={(
          <div className="bank-flow-rule-batches-drawer__actions">
            <button
              className="bank-flow-rule-batches-button bank-flow-rule-batches-button--compact bank-flow-rule-batches-button--primary"
              disabled={!canMutateData || tagLoading || mutating}
              onClick={saveTagSelection}
              type="button"
            >
              保存
            </button>
          </div>
        )}
        onClose={() => setTagDrawerOpen(false)}
        open={tagDrawerOpen}
        title="流水规则标签管理"
        width="min(960px, 92vw)"
      >
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
      </AppDrawer>

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
