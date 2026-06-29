import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";

import AppDialog from "../components/common/AppDialog";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import { useGlobalOperationOverlay } from "../contexts/GlobalOperationOverlayContext";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
} from "../features/domainEvents";
import { useActivePageEvent, useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { useSessionPermissions } from "../contexts/SessionContext";
import { operationBarrierTargets, operationBarrierTargetsFromMonths, waitForOperationFreshness } from "../features/operationBarrier/api";
import type { OperationBarrierTarget } from "../features/operationBarrier/api";
import {
  fetchNoOaBankBatchDetail,
  fetchNoOaBankBatchTagSelection,
  fetchNoOaBankBatches,
  applyNoOaBankBatchRebaseline,
  dryRunNoOaBankBatchRebaseline,
  resetSubmittedNoOaBankBatches,
  saveNoOaBankBatchTagSelection,
  submitNoOaBankBatch,
  submitNoOaBankBatchSelection,
  withdrawNoOaBankBatch,
} from "../features/noOaBankBatches/api";
import {
  canSelectBatchRows,
  canSubmitInternalTransferBatch,
  canWithdrawBatch,
  statusBucketFor,
} from "../features/noOaBankBatches/policy";
import type {
  NoOaBankBatch,
  NoOaBankBatchDetail,
  NoOaBankBatchesResponse,
  NoOaBankBatchReadModelStatus,
  NoOaBankBatchStatus,
  NoOaBankBatchStatusBucket,
  NoOaBankBatchDetailRow,
  NoOaBankBatchSummaryCategory,
  NoOaBankBatchTagDefinition,
  NoOaBankBatchTagRule,
  NoOaBankBatchTagSelection,
  NoOaBankBatchRebaselineManifest,
} from "../features/noOaBankBatches/types";

const EMPTY_BATCHES: NoOaBankBatchesResponse = {
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

const EMPTY_TAG_SELECTION: NoOaBankBatchTagSelection = {
  version: 1,
  bankAutoTagRulesVersion: 1,
  selectedTagCodes: [],
  inactiveSelectedTagCodes: [],
  activeTags: [],
  rules: [],
  requirementsByTagCode: {},
};

const SELF_SUB_LABEL = "主标签本身";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const NO_OA_READ_MODEL_REFRESH_RETRY_MS = 1000;
const NO_OA_BANK_BATCH_PAGE_SIZE = 200;
const BANK_FLOW_RULE_BATCH_READ_MODEL_KEY = "bank_flow_rule_batch";

type BatchStatusMeta = { label: string; color: "default" | "primary" | "success" | "warning" | "error" };

const STATUS_META: Record<NoOaBankBatchStatus | "unsubmitted", BatchStatusMeta> = {
  draft: { label: "待提交", color: "warning" },
  unsubmitted: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
};

function currentMonth() {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

function isAbortLikeError(caught: unknown) {
  if (caught instanceof DOMException && caught.name === "AbortError") {
    return true;
  }
  return caught instanceof Error && (caught.name === "AbortError" || /aborted|abort/i.test(caught.message));
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

function accountLabel(batch: NoOaBankBatch) {
  const account = batch.accountLast4 ? `${batch.bankName || "多账户"}${batch.accountLast4}` : batch.bankName || "多账户";
  return account || "多账户";
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
    <div aria-label={label} className="no-oa-bank-batches-pagination" role="group">
      <span className="no-oa-bank-batches-pagination__summary">{pageRange(page, pageSize, total)}</span>
      <button
        aria-label={`${label}上一页`}
        className="no-oa-bank-batches-pagination__button"
        disabled={disabled || page <= 1}
        onClick={onPrevious}
        title={`${label}上一页`}
        type="button"
      >
        <ChevronLeft aria-hidden="true" size={15} strokeWidth={2.4} />
      </button>
      <button
        aria-label={`${label}下一页`}
        className="no-oa-bank-batches-pagination__button"
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

function bankTagLabel(row: { bankName?: string; accountLast4?: string; accountKey?: string }) {
  if (row.accountLast4) {
    return `${row.bankName || "银行"}${row.accountLast4}`;
  }
  return row.bankName || row.accountKey || "-";
}

function directionTagLabel(row: { direction?: string; directionLabel?: string }) {
  return row.directionLabel || (row.direction === "income" ? "收" : row.direction === "expense" ? "支" : "-");
}

function batchBlockingReason(_batch: NoOaBankBatch) {
  return "";
}

function BatchStatusTag({ status }: { status: string }) {
  const meta = STATUS_META[status as keyof typeof STATUS_META] ?? { label: status, color: "default" as const };
  return (
    <span className={cx("no-oa-bank-batches-status", `no-oa-bank-batches-status--${meta.color}`)}>
      {meta.label}
    </span>
  );
}

function mutationEventDetail(result: {
  affectedMonths?: string[];
  affectedScopeKeys?: string[];
  operationBarrierTargets?: OperationBarrierTarget[];
}) {
  return {
    affectedMonths: result.affectedMonths ?? [],
    affectedScopeKeys: result.affectedScopeKeys ?? [],
    operationBarrierTargets: result.operationBarrierTargets ?? [],
  };
}

function mutationBarrierTargets(
  result: { affectedMonths?: string[]; operationBarrierTargets?: OperationBarrierTarget[] },
  fallbackScopeKey: string,
) {
  return result.operationBarrierTargets && result.operationBarrierTargets.length > 0
    ? result.operationBarrierTargets
    : operationBarrierTargetsFromMonths(BANK_FLOW_RULE_BATCH_READ_MODEL_KEY, result.affectedMonths ?? [], fallbackScopeKey);
}

type NoOaTagNode = {
  code: string;
  label: string;
  primaryLabel: string;
  subLabel: string;
};

type NoOaDraftRequirements = Record<string, { requiresOa: boolean; requiresInvoice: boolean }>;

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function tagPrimaryLabel(tag: NoOaBankBatchTagDefinition | NoOaBankBatchSummaryCategory | NoOaBankBatch) {
  if ("outputPrimaryLabel" in tag) {
    return cleanText(tag.outputPrimaryLabel) || cleanText(tag.label) || cleanText(tag.code);
  }
  if ("primaryLabel" in tag) {
    return cleanText(tag.primaryLabel) || cleanText(tag.label) || cleanText(tag.code);
  }
  if ("batchType" in tag) {
    return cleanText(tag.categoryPrimaryLabel) || cleanText(tag.batchLabel) || cleanText(tag.batchType);
  }
  return cleanText(tag.label) || cleanText(tag.code);
}

function tagSubLabel(tag: NoOaBankBatchTagDefinition | NoOaBankBatchSummaryCategory | NoOaBankBatch) {
  if ("outputSubLabel" in tag) {
    return cleanText(tag.outputSubLabel);
  }
  if ("subLabel" in tag) {
    return cleanText(tag.subLabel);
  }
  return "batchType" in tag ? cleanText(tag.categorySubLabel) : "";
}

function directionLabel(value: string) {
  if (value === "income") {
    return "收入";
  }
  if (value === "expense") {
    return "支出";
  }
  return "全部";
}

function requirementsFromSelection(selection: NoOaBankBatchTagSelection): NoOaDraftRequirements {
  return Object.fromEntries(selection.rules.map((rule) => [
    rule.tagCode,
    { requiresOa: rule.requiresOa, requiresInvoice: rule.requiresInvoice },
  ]));
}

function requirementFor(requirements: NoOaDraftRequirements, tagCode: string) {
  return requirements[tagCode] ?? { requiresOa: true, requiresInvoice: true };
}

function handleButtonKeyDown(event: KeyboardEvent<HTMLElement>, action: () => void) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  action();
}

function cx(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

function formatCountMeta(batchCount: number, rowCount: number) {
  if (batchCount === 0 && rowCount === 0) {
    return "暂无";
  }
  return `${batchCount}批 · ${rowCount}条`;
}

function relationContextLabels(row: NoOaBankBatchDetailRow) {
  if (row.relationStatus !== "linked" && row.relationCaseIds.length === 0) {
    return [];
  }
  const relationLabel = row.relationCaseIds[0] ? `关联 ${row.relationCaseIds[0]}` : "已有未撤回关联";
  return [relationLabel, `OA ${row.linkedOaCount}`, `发票 ${row.linkedInvoiceCount}`];
}

function bankDetailTagLabels(row: NoOaBankBatchDetailRow) {
  const labelPath = row.categoryLabelPath.map((label) => label.trim()).filter(Boolean);
  if (labelPath.length > 0) {
    return Array.from(new Set(labelPath));
  }
  const fallbackLabels = [
    row.categoryPrimaryLabel,
    row.categorySubLabel,
    row.categoryLabel,
    row.categoryCode,
  ].map((label) => label.trim()).filter(Boolean);
  return Array.from(new Set(fallbackLabels));
}

type LabelRailGroup = {
  key: string;
  label: string;
  batchCount: number;
  rowCount: number;
};

type LabelRailProps = {
  title: string;
  subtitle?: string;
  ariaLabel: string;
  emptyTitle: string;
  groups: LabelRailGroup[];
  selectedKey: string;
  onSelect: (key: string) => void;
};

function LabelRail({ title, subtitle, ariaLabel, emptyTitle, groups, selectedKey, onSelect }: LabelRailProps) {
  return (
    <section aria-label={ariaLabel} className="no-oa-bank-batches-rail" role="region">
      <header className="no-oa-bank-batches-rail__header">
        <h2 className="no-oa-bank-batches-rail__title">{title}</h2>
        {subtitle ? <p className="no-oa-bank-batches-rail__subtitle">{subtitle}</p> : null}
      </header>
      {groups.length === 0 ? (
        <div className="no-oa-bank-batches-rail__empty">
          <StatePanel compact tone="empty" title={emptyTitle} />
        </div>
      ) : (
        <div className="no-oa-bank-batches-rail__list">
          {groups.map((group) => {
            const selected = selectedKey === group.key;
            const countMeta = formatCountMeta(group.batchCount, group.rowCount);
            const isEmpty = group.batchCount === 0 && group.rowCount === 0;
            return (
              <button
                aria-label={`${group.label} ${countMeta}`}
                aria-pressed={selected}
                className={cx(
                  "no-oa-bank-batches-rail__item",
                  selected && "no-oa-bank-batches-rail__item--active",
                )}
                key={group.key}
                onClick={() => onSelect(group.key)}
                onKeyDown={(event) => handleButtonKeyDown(event, () => onSelect(group.key))}
                type="button"
              >
                <span className="no-oa-bank-batches-rail__item-label">
                  {group.label}
                </span>
                <span
                  className={cx(
                    "no-oa-bank-batches-rail__item-count",
                    isEmpty && "no-oa-bank-batches-rail__item-count--empty",
                  )}
                >
                  {countMeta}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

export default function NoOaBankBatchPage() {
  const { runOperation } = useGlobalOperationOverlay();
  const { active } = useOptionalPageActivation("bank-flow-rule-batches");
  const { canMutateData } = useSessionPermissions();
  const [month, setMonth] = useState(currentMonth);
  const [bucket, setBucket] = useState<NoOaBankBatchStatusBucket>("unsubmitted");
  const [payload, setPayload] = useState<NoOaBankBatchesResponse>(EMPTY_BATCHES);
  const [tagSelection, setTagSelection] = useState<NoOaBankBatchTagSelection>(EMPTY_TAG_SELECTION);
  const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
  const [draftTagRequirements, setDraftTagRequirements] = useState<NoOaDraftRequirements>(() => ({}));
  const [selectedPrimaryLabel, setSelectedPrimaryLabel] = useState("");
  const [selectedSubKey, setSelectedSubKey] = useState("");
  const [details, setDetails] = useState<Record<string, NoOaBankBatchDetail>>({});
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
  const [withdrawTarget, setWithdrawTarget] = useState<NoOaBankBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [rebaselineManifest, setRebaselineManifest] = useState<NoOaBankBatchRebaselineManifest | null>(null);
  const [rebaselineReason, setRebaselineReason] = useState("历史免OA已提交批次按流水规则重新处理");
  const [feedback, setFeedback] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const batchRequestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);
  const batchQueryKeyRef = useRef("");
  const manualLabelSelectionRef = useRef(false);
  const readModelStatus = payload.readModelStatus;
  const readModelNeedsRefresh = readModelStatus !== "fresh";

  const loadTagSelection = useCallback((signal?: AbortSignal) => {
    setTagLoading(true);
    fetchNoOaBankBatchTagSelection(signal)
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

  const applyBatchesPayload = useCallback((nextPayload: NoOaBankBatchesResponse) => {
    setPayload(nextPayload);
    clearSelection();
  }, [clearSelection]);

  const reloadBatchesAfterMutation = useCallback(async () => {
    const requestId = batchRequestSeqRef.current + 1;
    batchRequestSeqRef.current = requestId;
    const nextPayload = await fetchNoOaBankBatches({
      month,
      bucket,
      page: batchPage,
      pageSize: NO_OA_BANK_BATCH_PAGE_SIZE,
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
    fetchNoOaBankBatches({
      month,
      bucket,
      page: batchPage,
      pageSize: NO_OA_BANK_BATCH_PAGE_SIZE,
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
    }, NO_OA_READ_MODEL_REFRESH_RETRY_MS);
    return () => window.clearTimeout(retryId);
  }, [active, backgroundRefreshing, loadBatches, loading, readModelNeedsRefresh]);

  const tagNodesByCode = useMemo(() => {
    const nodes = new Map<string, NoOaTagNode>();
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
    pageSize: NO_OA_BANK_BATCH_PAGE_SIZE,
    total: payload.batches.length,
  };

  useEffect(() => {
    if (visibleBatches.length === 0) {
      setSelectedBatchId("");
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
    const requestId = detailRequestSeqRef.current + 1;
    detailRequestSeqRef.current = requestId;
    let cancelled = false;
    fetchNoOaBankBatchDetail(selectedBatchId)
      .then((detail) => {
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetails((current) => ({ ...current, [selectedBatchId]: detail }));
        }
      })
      .catch((caught) => {
        if (!cancelled && requestId === detailRequestSeqRef.current) {
          setDetailErrors((current) => ({
            ...current,
            [selectedBatchId]: caught instanceof Error ? caught.message : "批次明细加载失败",
          }));
        }
      });
    return () => {
      cancelled = true;
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
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      ...mutationEventDetail(result),
    });
    clearSelection();
    setDetails({});
    setDetailErrors({});
    setFeedback({ severity: "success", message });
  }, [clearSelection]);

  const toggleTransaction = (row: NoOaBankBatchDetailRow, checked: boolean) => {
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

  const setRegionSelection = (rows: NoOaBankBatchDetailRow[], checked: boolean) => {
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
          const submitResult = await submitNoOaBankBatchSelection({
            transactionIds,
            note: "",
          });
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(
            mutationBarrierTargets(submitResult, month),
          );
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
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

  const handleSubmitBatch = async (batch: NoOaBankBatch) => {
    if (!canMutateData || !canSubmitInternalTransferBatch(batch, bucket) || mutating) {
      return;
    }
    const result = await runOperation({
      loadingMessage: "正在提交内部往来流水规则批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const submitResult = await submitNoOaBankBatch({
            batchId: batch.batchId,
            expectedVersion: batch.version,
            note: "",
          });
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(
            mutationBarrierTargets(submitResult, batch.scopeMonth || month),
          );
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
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
          const withdrawResult = await withdrawNoOaBankBatch({
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
          const resetResult = await resetSubmittedNoOaBankBatches({
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

  const handleRebaselineDryRun = async () => {
    if (!canMutateData || mutating) {
      return;
    }
    const result = await runOperation({
      loadingMessage: "正在扫描历史免OA已提交批次...",
      action: async () => {
        setMutating(true);
        try {
          return await dryRunNoOaBankBatchRebaseline();
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "历史免OA扫描失败",
    });
    if (result.status === "success") {
      setRebaselineManifest(result.value);
      const count = result.value.summary.batchCount;
      setFeedback({
        severity: count > 0 ? "warning" : "success",
        message: count > 0 ? `已生成历史免OA重算清单：${count} 批` : "没有历史免OA已提交批次需要重算",
      });
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "历史免OA扫描失败" });
    }
  };

  const handleApplyRebaseline = async () => {
    if (!canMutateData || mutating || !rebaselineManifest || rebaselineManifest.summary.batchCount === 0) {
      return;
    }
    const manifest = rebaselineManifest;
    const reason = rebaselineReason.trim() || "历史免OA已提交批次按流水规则重新处理";
    const result = await runOperation({
      loadingMessage: "正在撤回历史免OA已提交批次...",
      action: async ({ setMessage }) => {
        setMutating(true);
        try {
          const applied = await applyNoOaBankBatchRebaseline({ manifest, reason });
          setMessage("正在等待流水规则批次读模型同步...");
          await waitForOperationFreshness(
            operationBarrierTargetsFromMonths(
              BANK_FLOW_RULE_BATCH_READ_MODEL_KEY,
              applied.summary.affectedMonths,
              "all",
            ),
          );
          setMessage("正在刷新流水规则批次...");
          await reloadBatchesAfterMutation();
          return applied;
        } finally {
          setMutating(false);
        }
      },
      errorMessage: (caught) => caught instanceof Error ? caught.message : "历史免OA重算应用失败",
    });
    if (result.status === "success") {
      setRebaselineManifest(result.value);
      setFeedback({ severity: "success", message: `历史免OA已撤回 ${result.value.summary.batchCount} 批` });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
        affectedMonths: result.value.summary.affectedMonths,
        affectedScopeKeys: result.value.summary.affectedMonths,
      });
    } else {
      setFeedback({ severity: "error", message: result.error instanceof Error ? result.error.message : "历史免OA重算应用失败" });
    }
  };

  const saveTagSelection = async () => {
    if (!canMutateData || mutating) {
      return;
    }
    const rules: NoOaBankBatchTagRule[] = tagSelection.activeTags.map((tag) => {
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
          const saved = await saveNoOaBankBatchTagSelection({
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

  const drawerRows = useMemo(() => tagSelection.activeTags.map((tag) => ({
    tag,
    direction: directionLabel(tag.direction),
    primaryLabel: tagPrimaryLabel(tag) || tag.label || tag.code,
    subLabel: tagSubLabel(tag) || SELF_SUB_LABEL,
  })), [tagSelection.activeTags]);

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
    manualLabelSelectionRef.current = false;
    setSelectedPrimaryLabel("");
    setSelectedSubKey("");
    setSelectedBatchId("");
    setDetails({});
    setDetailErrors({});
  }, [clearSelection]);

  const selectBucket = (nextBucket: NoOaBankBatchStatusBucket) => {
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

  return (
    <PageScaffold
      title="流水规则批量处理"
      actions={(
        <div className="no-oa-bank-batches-actions">
          <button
            className="no-oa-bank-batches-button"
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
            className="no-oa-bank-batches-button"
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
      <div aria-label="批次筛选" className="no-oa-bank-batches-filter" role="region">
        <div aria-label="批次状态" className="no-oa-bank-batches-segment" role="group">
          <button
            aria-pressed={bucket === "unsubmitted"}
            className={cx("no-oa-bank-batches-segment__button", bucket === "unsubmitted" && "no-oa-bank-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("unsubmitted")}
          >
            未提交 {unsubmittedCount}
          </button>
          <button
            aria-pressed={bucket === "submitted"}
            className={cx("no-oa-bank-batches-segment__button", bucket === "submitted" && "no-oa-bank-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("submitted")}
          >
            已提交 {payload.summary.submittedCount}
          </button>
          <button
            aria-pressed={bucket === "withdrawn"}
            className={cx("no-oa-bank-batches-segment__button", bucket === "withdrawn" && "no-oa-bank-batches-segment__button--active")}
            type="button"
            onClick={() => selectBucket("withdrawn")}
          >
            历史 {payload.summary.withdrawnCount}
          </button>
        </div>
        <label className="no-oa-bank-batches-field">
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
            className="no-oa-bank-batches-button no-oa-bank-batches-button--primary"
            disabled={selectedTransactionIds.size === 0 || mutating}
            type="button"
            onClick={handleSubmitSelected}
          >
            提交批次
          </button>
        ) : null}
        {canMutateData && payload.summary.submittedCount > 0 ? (
          <button
            className="no-oa-bank-batches-button"
            disabled={mutating}
            type="button"
            onClick={handleResetSubmitted}
          >
            重置全部已提交
          </button>
        ) : null}
          {selectedTransactionIds.size > 0 ? (
            <span className="no-oa-bank-batches-selected-count">
              已选 {selectedTransactionIds.size} 条
            </span>
          ) : null}
      </div>

      {canMutateData ? (
        <div aria-label="历史免OA重算" className="no-oa-bank-batches-rebaseline" role="region">
          <button
            className="no-oa-bank-batches-button no-oa-bank-batches-button--compact"
            disabled={mutating}
            onClick={handleRebaselineDryRun}
            type="button"
          >
            扫描历史免OA
          </button>
          {rebaselineManifest ? (
            <>
              <span className="no-oa-bank-batches-rebaseline__summary">
                待撤回 {rebaselineManifest.summary.batchCount} 批 / {rebaselineManifest.summary.rowCount} 条
                {rebaselineManifest.summary.affectedMonths.length > 0
                  ? ` / ${rebaselineManifest.summary.affectedMonths.join("、")}`
                  : ""}
              </span>
              <label className="no-oa-bank-batches-rebaseline__reason">
                <span>原因</span>
                <input
                  value={rebaselineReason}
                  onChange={(event) => setRebaselineReason(event.target.value)}
                />
              </label>
              <button
                className="no-oa-bank-batches-button no-oa-bank-batches-button--compact no-oa-bank-batches-button--primary"
                disabled={mutating || rebaselineManifest.summary.batchCount === 0}
                onClick={handleApplyRebaseline}
                type="button"
              >
                应用重算
              </button>
            </>
          ) : (
            <span className="no-oa-bank-batches-rebaseline__summary">
              先 dry-run，再按清单撤回旧免OA已提交批次
            </span>
          )}
        </div>
      ) : null}

      {error ? <StatePanel tone="error" title={error} /> : null}

      <div className="no-oa-bank-batches-layout">
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

        <section aria-label="流水" className="no-oa-bank-batches-transactions" role="region">
          <header className="no-oa-bank-batches-transactions__header">
            <div className="no-oa-bank-batches-transactions__heading">
              <h2 className="no-oa-bank-batches-transactions__title">
                {selectedPrimaryLabel && selectedSubKey ? `${selectedPrimaryLabel} / ${selectedSubKey}` : "流水"}
              </h2>
            </div>
          </header>
          <div className="no-oa-bank-batches-transactions__list">
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
                    "no-oa-bank-batches-batch",
                    selected && "no-oa-bank-batches-batch--selected",
                  )}
                  key={batch.batchId}
                >
                  <div className="no-oa-bank-batches-batch__body">
                    <div className="no-oa-bank-batches-batch__header">
                      <div className="no-oa-bank-batches-batch__summary">
                        <div className="no-oa-bank-batches-batch__title-row">
                          <h3 className="no-oa-bank-batches-batch__title">{accountLabel(batch)}</h3>
                          <BatchStatusTag status={batch.status} />
                        </div>
                        <p className="no-oa-bank-batches-batch__meta">
                          {batch.rowCount} 条 · 合计 {formatMoney(batch.totalAmount)}
                        </p>
                      </div>
                      <div className="no-oa-bank-batches-batch__actions">
                        {!selected ? (
                          <button
                            aria-label={`查看${accountLabel(batch)}流水`}
                            className="no-oa-bank-batches-button no-oa-bank-batches-button--compact"
                            onClick={() => setSelectedBatchId(batch.batchId)}
                            type="button"
                          >
                            查看流水
                          </button>
                        ) : null}
                        {selected && rowSelectionEnabled ? (
                          <>
                            <button
                              className="no-oa-bank-batches-button no-oa-bank-batches-button--compact"
                              disabled={!canMutateData || rows.length === 0 || mutating}
                              onClick={() => setRegionSelection(rows, true)}
                              type="button"
                            >
                              全选
                            </button>
                            <button
                              className="no-oa-bank-batches-button no-oa-bank-batches-button--compact"
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
                            className="no-oa-bank-batches-button no-oa-bank-batches-button--compact no-oa-bank-batches-button--primary"
                            disabled={mutating}
                            onClick={() => handleSubmitBatch(batch)}
                            type="button"
                          >
                            提交内部往来批次
                          </button>
                        ) : null}
                        {bucket === "submitted" && canMutateData && canWithdrawBatch(batch) ? (
                          <button
                            className="no-oa-bank-batches-button no-oa-bank-batches-button--compact"
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
                          "no-oa-bank-batches-notice",
                          "no-oa-bank-batches-notice--warning",
                        )}
                        role="alert"
                      >
                        {blockingReason}
                      </div>
                    ) : null}
                    {selected && detailErrors[batch.batchId] ? (
                      <div className="no-oa-bank-batches-notice no-oa-bank-batches-notice--error" role="alert">
                        {detailErrors[batch.batchId]}
                      </div>
                    ) : null}
                    {selected && !detail && !detailErrors[batch.batchId] ? <StatePanel compact tone="loading" title="正在加载流水明细" /> : null}
                    {selected && detail && rows.length === 0 ? <StatePanel compact tone="empty" title="暂无流水明细" /> : null}
                    {selected && rows.length > 0 ? (
                      <div className="no-oa-bank-batches-table-wrap">
                        <table className="no-oa-bank-batches-table" aria-label={`${accountLabel(batch)}流水`}>
                          <thead>
                            <tr>
                              {rowSelectionEnabled ? (
                                <th className="no-oa-bank-batches-table__check" scope="col">
                                  <input
                                    aria-label={`${accountLabel(batch)}全选`}
                                    checked={regionChecked}
                                    className="no-oa-bank-batches-checkbox"
                                    disabled={!canMutateData}
                                    onChange={(event) => setRegionSelection(rows, event.target.checked)}
                                    type="checkbox"
                                  />
                                </th>
                              ) : null}
                              <th scope="col">交易时间</th>
                              <th scope="col">对方户名</th>
                              <th className="no-oa-bank-batches-table__amount" scope="col">金额</th>
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
                                    <td className="no-oa-bank-batches-table__check">
                                      <input
                                        aria-label={`选择流水 ${row.transactionId}`}
                                        checked={selectedTransactionIds.has(row.transactionId)}
                                        className="no-oa-bank-batches-checkbox"
                                        disabled={!canMutateData}
                                        onChange={(event) => toggleTransaction(row, event.target.checked)}
                                        type="checkbox"
                                      />
                                    </td>
                                  ) : null}
                                  <td>{row.tradeTime || "-"}</td>
                                  <td>{row.counterpartyName || "-"}</td>
                                  <td className="no-oa-bank-batches-table__amount">
                                    <div className="no-oa-bank-batches-amount-cell">
                                      <div className="no-oa-bank-batches-amount-cell__main">
                                        <span className="no-oa-bank-batches-tag no-oa-bank-batches-tag--direction">
                                          {directionTagLabel(row)}
                                        </span>
                                        <span className="no-oa-bank-batches-amount">{formatMoney(row.amount)}</span>
                                      </div>
                                      <span className="no-oa-bank-batches-tag no-oa-bank-batches-tag--bank">
                                        {bankTagLabel(row)}
                                      </span>
                                    </div>
                                  </td>
                                  <td>
                                    <div className="no-oa-bank-batches-summary-cell">
                                      <span className="no-oa-bank-batches-summary-cell__summary">{row.summary || "-"}</span>
                                      <span className="no-oa-bank-batches-summary-cell__memo">{[row.purpose, row.remark].filter(Boolean).join(" / ") || "-"}</span>
                                      {rowTagLabels.length > 0 ? (
                                        <div aria-label={`银行明细标签 ${row.transactionId}`} className="no-oa-bank-batches-bank-tags">
                                          {rowTagLabels.map((label) => (
                                            <span className="no-oa-bank-batches-tag no-oa-bank-batches-tag--bank-detail" key={label}>{label}</span>
                                          ))}
                                        </div>
                                      ) : null}
                                      {relationLabels.length > 0 ? (
                                        <div className="no-oa-bank-batches-relation-cell">
                                          {relationLabels.map((label) => (
                                            <span className="no-oa-bank-batches-tag" key={label}>{label}</span>
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
        <div className="no-oa-bank-batches-drawer-shell">
          <button
            aria-label="关闭流水规则标签管理"
            className="no-oa-bank-batches-drawer-shell__backdrop"
            onClick={() => setTagDrawerOpen(false)}
            type="button"
          />
          <aside aria-label="流水规则标签管理" className="no-oa-bank-batches-drawer" role="dialog">
            <header className="no-oa-bank-batches-drawer__header">
              <div>
                <h2 className="no-oa-bank-batches-drawer__title">流水规则标签管理</h2>
              </div>
              <button
                aria-label="关闭流水规则标签管理"
                className="no-oa-bank-batches-drawer__close"
                onClick={() => setTagDrawerOpen(false)}
                type="button"
              >
                ×
              </button>
            </header>
            <div className="no-oa-bank-batches-drawer__body">
              {tagSelection.inactiveSelectedTagCodes.length > 0 ? (
                <div className="no-oa-bank-batches-notice no-oa-bank-batches-notice--warning" role="alert">
                  已停用标签不再生效：{tagSelection.inactiveSelectedTagCodes.join("、")}。保存后会清理这些引用。
                </div>
              ) : null}
              <div className="no-oa-bank-batches-drawer__grid-wrap">
                <table className="no-oa-bank-batches-drawer__grid">
                  <thead>
                    <tr>
                      <th scope="col">收支类型</th>
                      <th scope="col">流水主标签</th>
                      <th scope="col">流水子标签</th>
                      <th className="no-oa-bank-batches-drawer__check-col" scope="col">OA</th>
                      <th className="no-oa-bank-batches-drawer__check-col" scope="col">发票</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drawerRows.map(({ tag, direction, primaryLabel, subLabel }) => {
                      const rule = requirementFor(draftTagRequirements, tag.code);
                      const rowLabel = subLabel === SELF_SUB_LABEL ? primaryLabel : `${primaryLabel} / ${subLabel}`;
                      return (
                        <tr key={tag.code}>
                          <td>{direction}</td>
                          <td>{primaryLabel}</td>
                          <td>{subLabel}</td>
                          <td className="no-oa-bank-batches-drawer__check-col">
                            <input
                              aria-label={`${rowLabel} 需要OA`}
                              checked={rule.requiresOa}
                              className="no-oa-bank-batches-checkbox"
                              disabled={!canMutateData || tagLoading}
                              onChange={(event) => updateDraftRequirement(tag.code, "requiresOa", event.target.checked)}
                              type="checkbox"
                            />
                          </td>
                          <td className="no-oa-bank-batches-drawer__check-col">
                            <input
                              aria-label={`${rowLabel} 需要发票`}
                              checked={rule.requiresInvoice}
                              className="no-oa-bank-batches-checkbox"
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
            <footer className="no-oa-bank-batches-drawer__footer">
              <div className="no-oa-bank-batches-drawer__actions">
                <button
                  className="no-oa-bank-batches-button no-oa-bank-batches-button--compact no-oa-bank-batches-button--primary"
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
            <button className="no-oa-bank-batches-button" onClick={() => setWithdrawTarget(null)} type="button">
              取消
            </button>
            <button
              className="no-oa-bank-batches-button no-oa-bank-batches-button--primary"
              disabled={!withdrawReason.trim() || mutating}
              onClick={handleConfirmWithdraw}
              type="button"
            >
              确认撤回
            </button>
          </>
        )}
      >
        <div className="no-oa-bank-batches-dialog">
          <div className="no-oa-bank-batches-notice no-oa-bank-batches-notice--warning" role="alert">
            撤回后会取消关联台闭环关系，相关流水回到未配对区域。
          </div>
          <label className="no-oa-bank-batches-dialog__field">
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
        <div className={cx("no-oa-bank-batches-toast", `no-oa-bank-batches-toast--${feedback.severity}`)} role="alert">
          <span>{feedback.message}</span>
          <button aria-label="关闭提示" onClick={() => setFeedback(null)} type="button">×</button>
        </div>
      ) : null}
    </PageScaffold>
  );
}
