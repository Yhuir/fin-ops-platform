import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { RefreshCw } from "lucide-react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
} from "../features/domainEvents";
import { useActivePageEvent, useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";
import { usePageScrollSession } from "../hooks/usePageScrollSession";
import {
  fetchNoOaBankBatchDetail,
  fetchNoOaBankBatchTagSelection,
  fetchNoOaBankBatches,
  saveNoOaBankBatchTagSelection,
  submitNoOaBankBatch,
  submitNoOaBankBatchSelection,
  withdrawNoOaBankBatch,
} from "../features/noOaBankBatches/api";
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
  NoOaBankBatchTagSelection,
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
  readModelStatus: "fresh",
  readModelStaleReasons: [],
};

const EMPTY_TAG_SELECTION: NoOaBankBatchTagSelection = {
  version: 1,
  bankAutoTagRulesVersion: 1,
  selectedTagCodes: [],
  inactiveSelectedTagCodes: [],
  activeTags: [],
};

const SELF_SUB_LABEL = "主标签本身";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const NO_OA_READ_MODEL_REFRESH_RETRY_MS = 1000;

const STATUS_META: Record<NoOaBankBatchStatus, { label: string; color: "default" | "primary" | "success" | "warning" | "error" }> = {
  draft: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
  conflict: { label: "冲突", color: "error" },
  stale: { label: "需复核", color: "primary" },
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

function bankTagLabel(row: { bankName?: string; accountLast4?: string; accountKey?: string }) {
  if (row.accountLast4) {
    return `${row.bankName || "银行"}${row.accountLast4}`;
  }
  return row.bankName || row.accountKey || "-";
}

function directionTagLabel(row: { direction?: string; directionLabel?: string }) {
  return row.directionLabel || (row.direction === "income" ? "收" : row.direction === "expense" ? "支" : "-");
}

function sourceLabel(source: string) {
  if (source === "auto") {
    return "自动";
  }
  if (source === "manual") {
    return "人工";
  }
  return source || "-";
}

function canWithdraw(batch: NoOaBankBatch) {
  return batch.canWithdraw || batch.status === "submitted";
}

function canSelectBatchRows(batch: NoOaBankBatch, bucket: NoOaBankBatchStatusBucket) {
  return bucket === "unsubmitted"
    && batch.status === "draft"
    && batch.canSubmit
    && batch.batchType !== "internal_transfer";
}

function canSubmitInternalTransferBatch(batch: NoOaBankBatch, bucket: NoOaBankBatchStatusBucket) {
  return bucket === "unsubmitted"
    && batch.status === "draft"
    && batch.canSubmit
    && batch.batchType === "internal_transfer";
}

function statusBucketFor(batch: NoOaBankBatch): NoOaBankBatchStatusBucket {
  if (batch.statusBucket === "submitted" || batch.status === "submitted") {
    return "submitted";
  }
  if (batch.statusBucket === "withdrawn" || batch.status === "withdrawn") {
    return "withdrawn";
  }
  return "unsubmitted";
}

function BatchStatusChip({ status }: { status: string }) {
  const meta = STATUS_META[status as NoOaBankBatchStatus] ?? { label: status, color: "default" as const };
  return <Chip color={meta.color} label={meta.label} size="small" />;
}

function mutationEventDetail(result: { affectedMonths?: string[] }) {
  return { affectedMonths: result.affectedMonths ?? [] };
}

type NoOaTagNode = {
  code: string;
  label: string;
  primaryLabel: string;
  subLabel: string;
};

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

function tagDisplayLabel(node: NoOaTagNode) {
  return node.subLabel ? `${node.primaryLabel} / ${node.subLabel}` : node.primaryLabel;
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

function bucketWorkHint(bucket: NoOaBankBatchStatusBucket) {
  if (bucket === "submitted") {
    return "已提交批次保留撤回入口。";
  }
  if (bucket === "withdrawn") {
    return "已撤回批次只读展示。";
  }
  return "每次只能选择同一银行区域内的流水提交。";
}

type LabelRailGroup = {
  key: string;
  label: string;
  batchCount: number;
  rowCount: number;
};

type LabelRailProps = {
  title: string;
  subtitle: string;
  ariaLabel: string;
  emptyTitle: string;
  groups: LabelRailGroup[];
  selectedKey: string;
  onSelect: (key: string) => void;
};

function LabelRail({ title, subtitle, ariaLabel, emptyTitle, groups, selectedKey, onSelect }: LabelRailProps) {
  return (
    <Paper
      aria-label={ariaLabel}
      role="region"
      variant="outlined"
      sx={{
        borderRadius: 1,
        overflow: "hidden",
        bgcolor: "background.paper",
      }}
    >
      <Stack spacing={0.25} sx={{ px: 1.5, py: 1.25 }}>
        <Typography fontWeight={900}>{title}</Typography>
        <Typography color="text.secondary" variant="caption">{subtitle}</Typography>
      </Stack>
      <Divider />
      {groups.length === 0 ? (
        <Box sx={{ p: 1.25 }}>
          <StatePanel compact tone="empty" title={emptyTitle} />
        </Box>
      ) : (
        <List disablePadding dense>
          {groups.map((group) => {
            const selected = selectedKey === group.key;
            const countMeta = formatCountMeta(group.batchCount, group.rowCount);
            return (
              <ListItemButton
                aria-label={`${group.label} ${countMeta}`}
                aria-pressed={selected}
                component="button"
                divider
                key={group.key}
                onClick={() => onSelect(group.key)}
                onKeyDown={(event) => handleButtonKeyDown(event, () => onSelect(group.key))}
                selected={selected}
                sx={{
                  width: "100%",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 1.25,
                  px: 1.5,
                  py: 1.25,
                  color: "text.primary",
                  textAlign: "left",
                  transition: "background-color 150ms ease, color 150ms ease",
                  "&.Mui-selected": {
                    bgcolor: "rgba(23, 105, 170, 0.1)",
                    color: "primary.dark",
                  },
                  "&.Mui-selected:hover": {
                    bgcolor: "rgba(23, 105, 170, 0.14)",
                  },
                  "&:focus-visible": {
                    outline: "2px solid",
                    outlineColor: "primary.main",
                    outlineOffset: -2,
                  },
                }}
                type="button"
              >
                <Typography
                  component="span"
                  fontWeight={selected ? 900 : 800}
                  sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {group.label}
                </Typography>
                <Typography
                  color={group.batchCount === 0 && group.rowCount === 0 ? "text.disabled" : "text.secondary"}
                  component="span"
                  variant="caption"
                  sx={{ flex: "0 0 auto", fontWeight: selected ? 800 : 700 }}
                >
                  {countMeta}
                </Typography>
              </ListItemButton>
            );
          })}
        </List>
      )}
    </Paper>
  );
}

export default function NoOaBankBatchPage() {
  const { active } = useOptionalPageActivation("no-oa-bank-batches");
  const [month, setMonth] = useState(currentMonth);
  const [bucket, setBucket] = useState<NoOaBankBatchStatusBucket>("unsubmitted");
  const [accountKey, setAccountKey] = useState("");
  const [payload, setPayload] = useState<NoOaBankBatchesResponse>(EMPTY_BATCHES);
  const [tagSelection, setTagSelection] = useState<NoOaBankBatchTagSelection>(EMPTY_TAG_SELECTION);
  const [tagDrawerOpen, setTagDrawerOpen] = useState(false);
  const [draftSelectedTagCodes, setDraftSelectedTagCodes] = useState<Set<string>>(() => new Set());
  const [selectedPrimaryLabel, setSelectedPrimaryLabel] = useState("");
  const [selectedSubKey, setSelectedSubKey] = useState("");
  const [details, setDetails] = useState<Record<string, NoOaBankBatchDetail>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [selectedTransactionIds, setSelectedTransactionIds] = useState<Set<string>>(() => new Set());
  const [selectedAccountForSubmit, setSelectedAccountForSubmit] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backgroundRefreshing, setBackgroundRefreshing] = useState(false);
  const [tagLoading, setTagLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<NoOaBankBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const detailTableWrapRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "no-oa-bank-batch",
    scrollKey: "detail-transactions-table",
  });
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
        setDraftSelectedTagCodes(new Set(nextSelection.selectedTagCodes));
      })
      .catch((caught) => {
        if (!isAbortLikeError(caught)) {
          setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "免OA标签配置加载失败" });
        }
      })
      .finally(() => setTagLoading(false));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedTransactionIds(new Set());
    setSelectedAccountForSubmit(null);
  }, []);

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
      accountKey: accountKey.trim(),
      signal,
    })
      .then((nextPayload) => {
        if (signal?.aborted || requestId !== batchRequestSeqRef.current) {
          return;
        }
        setPayload(nextPayload);
        clearSelection();
      })
      .catch((caught: unknown) => {
        if (signal?.aborted || requestId !== batchRequestSeqRef.current) {
          return;
        }
        if (!background && !isAbortLikeError(caught)) {
          setError(caught instanceof Error ? caught.message : "免OA流水批次加载失败");
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
  }, [accountKey, bucket, clearSelection, month]);

  useEffect(() => {
    const controller = new AbortController();
    loadTagSelection(controller.signal);
    return () => controller.abort();
  }, [loadTagSelection]);

  useEffect(() => {
    const controller = new AbortController();
    const batchQueryKey = JSON.stringify({ accountKey: accountKey.trim(), bucket, month });
    if (batchQueryKeyRef.current !== batchQueryKey) {
      batchQueryKeyRef.current = batchQueryKey;
      setDetails({});
      setDetailErrors({});
      setSelectedBatchId("");
    }
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [accountKey, bucket, loadBatches, month, refreshToken]);

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
      if (!tagSelection.selectedTagCodes.includes(tag.code)) {
        return;
      }
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
  }, [payload.batches, payload.summary.categories, tagSelection.activeTags, tagSelection.selectedTagCodes]);

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

  const handleMutationComplete = (message: string, result: { affectedMonths?: string[] }) => {
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      ...mutationEventDetail(result),
    });
    clearSelection();
    setDetails({});
    setDetailErrors({});
    setSnackbar({ severity: "success", message });
    loadBatches();
  };

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
        setSnackbar({ severity: "warning", message: "请先清空已选银行区域，再选择其他银行流水。" });
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
      setSnackbar({ severity: "warning", message: "请先清空已选银行区域，再选择其他银行流水。" });
      return;
    }
    setSelectedAccountForSubmit(account);
    setSelectedTransactionIds((current) => new Set([...current, ...rows.map((row) => row.transactionId)]));
  };

  const handleSubmitSelected = async () => {
    if (selectedTransactionIds.size === 0 || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await submitNoOaBankBatchSelection({
        transactionIds: Array.from(selectedTransactionIds),
        note: "",
      });
      handleMutationComplete("选中流水已提交", result);
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "提交选中流水失败" });
    } finally {
      setMutating(false);
    }
  };

  const handleSubmitBatch = async (batch: NoOaBankBatch) => {
    if (!canSubmitInternalTransferBatch(batch, bucket) || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await submitNoOaBankBatch({
        batchId: batch.batchId,
        expectedVersion: batch.version,
        note: "",
      });
      handleMutationComplete("内部往来批次已提交", result);
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "提交内部往来批次失败" });
    } finally {
      setMutating(false);
    }
  };

  const handleConfirmWithdraw = async () => {
    if (!withdrawTarget || !withdrawReason.trim() || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await withdrawNoOaBankBatch({
        batchId: withdrawTarget.batchId,
        expectedVersion: withdrawTarget.version,
        reason: withdrawReason.trim(),
      });
      setWithdrawTarget(null);
      setWithdrawReason("");
      handleMutationComplete("批次已撤回", result);
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "撤回批次失败" });
    } finally {
      setMutating(false);
    }
  };

  const saveTagSelection = async () => {
    setMutating(true);
    try {
      const saved = await saveNoOaBankBatchTagSelection({
        expectedVersion: tagSelection.version,
        selectedTagCodes: Array.from(draftSelectedTagCodes),
      });
      setTagSelection(saved);
      setDraftSelectedTagCodes(new Set(saved.selectedTagCodes));
      setTagDrawerOpen(false);
      setDetails({});
      setDetailErrors({});
      setSnackbar({ severity: "success", message: "免OA流水标签范围已保存" });
      loadBatches();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "保存免OA标签范围失败" });
    } finally {
      setMutating(false);
    }
  };

  const drawerGroups = useMemo(() => {
    const groups = new Map<string, NoOaBankBatchTagDefinition[]>();
    tagSelection.activeTags.forEach((tag) => {
      const primary = tagPrimaryLabel(tag) || tag.label || tag.code;
      groups.set(primary, [...(groups.get(primary) ?? []), tag]);
    });
    return Array.from(groups.entries()).map(([primaryLabel, tags]) => ({ primaryLabel, tags }));
  }, [tagSelection.activeTags]);

  const unsubmittedCount = payload.summary.draftCount + payload.summary.conflictCount + payload.summary.staleCount;
  const selectBucket = (nextBucket: NoOaBankBatchStatusBucket) => {
    if (nextBucket === bucket) {
      return;
    }
    clearSelection();
    manualLabelSelectionRef.current = false;
    setSelectedPrimaryLabel("");
    setSelectedSubKey("");
    setSelectedBatchId("");
    setBucket(nextBucket);
  };

  return (
    <PageScaffold
      title="免OA流水批量处理"
      description="按月份、主子标签和银行账户确认免 OA 银行流水批次。"
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
            免OA流水标签管理
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
          <input onChange={(event) => setMonth(event.target.value)} type="month" value={month} />
        </label>
        <label className="no-oa-bank-batches-field no-oa-bank-batches-field--account">
          <span>银行账户</span>
          <input onChange={(event) => setAccountKey(event.target.value)} placeholder="精确账户键，如 建设银行:8106" type="text" value={accountKey} />
        </label>
          {bucket === "unsubmitted" ? (
            <button
              className="no-oa-bank-batches-button no-oa-bank-batches-button--primary"
              disabled={selectedTransactionIds.size === 0 || mutating}
              type="button"
              onClick={handleSubmitSelected}
            >
              提交批次
            </button>
          ) : null}
          {selectedTransactionIds.size > 0 ? (
            <span className="no-oa-bank-batches-selected-count">
              已选 {selectedTransactionIds.size} 条
            </span>
          ) : null}
      </div>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <Box
        sx={{
          display: "grid",
          gap: 1.5,
          gridTemplateColumns: { xs: "1fr", lg: "18% 18% minmax(0, 1fr)" },
          alignItems: "start",
        }}
      >
        <LabelRail
          ariaLabel="主标签"
          emptyTitle="请先在标签管理中选择免OA标签"
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
          subtitle="来自银行明细自动标签"
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
          subtitle={selectedPrimaryLabel || "请选择主标签"}
          title="子标签"
        />

        <Paper aria-label="流水" role="region" variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack
            alignItems={{ xs: "stretch", md: "flex-start" }}
            direction={{ xs: "column", md: "row" }}
            justifyContent="space-between"
            spacing={1}
            sx={{ px: 1.5, py: 1.25 }}
          >
            <Stack spacing={0.25}>
              <Typography fontWeight={900}>
                {selectedPrimaryLabel && selectedSubKey ? `${selectedPrimaryLabel} / ${selectedSubKey}` : "流水"}
              </Typography>
              <Typography color="text.secondary" variant="caption">
                {bucketWorkHint(bucket)}
              </Typography>
            </Stack>
            {selectedAccountForSubmit ? (
              <Typography color="text.secondary" variant="caption" sx={{ fontWeight: 800 }}>
                当前选择账户：{selectedAccountForSubmit}
              </Typography>
            ) : null}
          </Stack>
          <Divider />
          <Stack divider={<Divider flexItem />} sx={{ maxHeight: { lg: "68vh" }, overflow: "auto" }}>
            {loading ? <StatePanel compact tone="loading" title="流水加载中" /> : null}
            {!loading && visibleBatches.length === 0 ? <StatePanel compact tone="empty" title="当前标签下暂无流水" /> : null}
            {!loading ? visibleBatches.map((batch) => {
              const detail = details[batch.batchId];
              const rows = detail?.rows ?? [];
              const selected = selectedBatchId === batch.batchId;
              const rowSelectionEnabled = canSelectBatchRows(batch, bucket);
              const internalTransferSubmitEnabled = canSubmitInternalTransferBatch(batch, bucket);
              const regionChecked = rowSelectionEnabled && rows.length > 0 && rows.every((row) => selectedTransactionIds.has(row.transactionId));
              const blockingReason = batch.blockedReason || batch.conflictReason;
              const auditItems = [
                batch.version !== null && batch.version !== undefined ? `版本：${batch.version}` : "",
                batch.submittedBy ? `提交人：${batch.submittedBy}` : "",
                batch.submittedAt ? `提交时间：${batch.submittedAt}` : "",
                batch.withdrawnBy ? `撤回人：${batch.withdrawnBy}` : "",
                batch.withdrawnAt ? `撤回时间：${batch.withdrawnAt}` : "",
              ].filter(Boolean);
              return (
                <Box
                  component="section"
                  key={batch.batchId}
                  sx={{
                    px: 1.5,
                    py: 1.25,
                    bgcolor: selected ? "rgba(23, 105, 170, 0.04)" : "background.paper",
                  }}
                >
                  <Stack spacing={1}>
                    <Stack
                      alignItems={{ xs: "stretch", md: "center" }}
                      direction={{ xs: "column", md: "row" }}
                      justifyContent="space-between"
                      spacing={1}
                    >
                      <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                        <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                          <Typography fontWeight={900}>{accountLabel(batch)}</Typography>
                          <BatchStatusChip status={batch.status} />
                        </Stack>
                        <Typography color="text.secondary" variant="body2">
                          {batch.rowCount} 条 · 合计 {formatMoney(batch.totalAmount)}
                        </Typography>
                      </Stack>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {!selected ? (
                          <Button
                            aria-label={`查看${accountLabel(batch)}流水`}
                            onClick={() => setSelectedBatchId(batch.batchId)}
                            size="small"
                            variant="outlined"
                          >
                            查看流水
                          </Button>
                        ) : null}
                        {selected && rowSelectionEnabled ? (
                          <>
                            <Button disabled={rows.length === 0 || mutating} onClick={() => setRegionSelection(rows, true)} size="small">全选</Button>
                            <Button disabled={rows.length === 0 || mutating} onClick={() => setRegionSelection(rows, false)} size="small">清空</Button>
                          </>
                        ) : null}
                        {internalTransferSubmitEnabled ? (
                          <Button disabled={mutating} onClick={() => handleSubmitBatch(batch)} size="small" variant="contained">提交内部往来批次</Button>
                        ) : null}
                        {bucket === "submitted" && canWithdraw(batch) ? (
                          <Button disabled={mutating} onClick={() => setWithdrawTarget(batch)} size="small" variant="outlined">撤回批次</Button>
                        ) : null}
                      </Stack>
                    </Stack>
                    {blockingReason ? (
                      <Alert severity={batch.status === "conflict" ? "error" : "warning"} sx={{ py: 0 }}>
                        {blockingReason}
                      </Alert>
                    ) : null}
                    {auditItems.length > 0 ? (
                      <Typography color="text.secondary" variant="caption">
                        {auditItems.join(" · ")}
                      </Typography>
                    ) : null}
                    {selected && detailErrors[batch.batchId] ? <Alert severity="error">{detailErrors[batch.batchId]}</Alert> : null}
                    {selected && !detail && !detailErrors[batch.batchId] ? <StatePanel compact tone="loading" title="正在加载流水明细" /> : null}
                    {selected && detail && rows.length === 0 ? <StatePanel compact tone="empty" title="暂无流水明细" /> : null}
                    {selected && rows.length > 0 ? (
                      <TableContainer ref={detailTableWrapRef}>
                        <Table size="small" aria-label={`${accountLabel(batch)}流水`}>
                          <TableHead>
                            <TableRow>
                              {rowSelectionEnabled ? (
                                <TableCell padding="checkbox">
                                  <Checkbox
                                    checked={regionChecked}
                                    inputProps={{ "aria-label": `${accountLabel(batch)}全选` }}
                                    onChange={(event) => setRegionSelection(rows, event.target.checked)}
                                  />
                                </TableCell>
                              ) : null}
                              <TableCell>交易时间</TableCell>
                              <TableCell>对方户名</TableCell>
                              <TableCell align="right">金额</TableCell>
                              <TableCell>摘要/用途/备注</TableCell>
                              <TableCell>分类来源</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {rows.map((row) => (
                              <TableRow key={row.transactionId}>
                                {rowSelectionEnabled ? (
                                  <TableCell padding="checkbox">
                                    <Checkbox
                                      checked={selectedTransactionIds.has(row.transactionId)}
                                      inputProps={{ "aria-label": `选择流水 ${row.transactionId}` }}
                                      onChange={(event) => toggleTransaction(row, event.target.checked)}
                                    />
                                  </TableCell>
                                ) : null}
                                <TableCell>{row.tradeTime || "-"}</TableCell>
                                <TableCell>{row.counterpartyName || "-"}</TableCell>
                                <TableCell align="right">
                                  <Stack alignItems="flex-end" spacing={0.25}>
                                    <Stack alignItems="center" direction="row" justifyContent="flex-end" spacing={0.75}>
                                      <Chip label={directionTagLabel(row)} size="small" />
                                      <Typography variant="body2">{formatMoney(row.amount)}</Typography>
                                    </Stack>
                                    <Chip label={bankTagLabel(row)} size="small" variant="outlined" />
                                  </Stack>
                                </TableCell>
                                <TableCell>
                                  <Stack spacing={0.25}>
                                    <Typography variant="body2">{row.summary || "-"}</Typography>
                                    <Typography color="text.secondary" variant="caption">{[row.purpose, row.remark].filter(Boolean).join(" / ") || "-"}</Typography>
                                  </Stack>
                                </TableCell>
                                <TableCell>{sourceLabel(row.categorySource)}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : null}
                  </Stack>
                </Box>
              );
            }) : null}
          </Stack>
        </Paper>
      </Box>

      <Drawer
        anchor="right"
        open={tagDrawerOpen}
        onClose={() => setTagDrawerOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: "520px" }, maxWidth: "100vw" }, role: "dialog", "aria-label": "免OA流水标签管理" }}
      >
        <Stack spacing={0} sx={{ height: "100%" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={900}>免OA流水标签管理</Typography>
              <Typography color="text.secondary" variant="caption">版本 {tagSelection.version}</Typography>
            </Box>
            <IconButton aria-label="关闭免OA流水标签管理" onClick={() => setTagDrawerOpen(false)}><CloseIcon /></IconButton>
          </Stack>
          <Divider />
          <Stack direction="row" spacing={1} sx={{ p: 2 }}>
            <Button onClick={() => setDraftSelectedTagCodes(new Set(tagSelection.activeTags.map((tag) => tag.code)))} size="small" variant="outlined">全选</Button>
            <Button onClick={() => setDraftSelectedTagCodes(new Set())} size="small" variant="outlined">清空</Button>
            <Button disabled={mutating} onClick={saveTagSelection} size="small" variant="contained">保存</Button>
          </Stack>
          {tagSelection.inactiveSelectedTagCodes.length > 0 ? (
            <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
              已停用标签不再生效：{tagSelection.inactiveSelectedTagCodes.join("、")}。保存后会清理这些引用。
            </Alert>
          ) : null}
          <Stack divider={<Divider flexItem />} sx={{ overflow: "auto" }}>
            {drawerGroups.map((group) => {
              const codes = group.tags.map((tag) => tag.code);
              const checkedCount = codes.filter((code) => draftSelectedTagCodes.has(code)).length;
              const allChecked = checkedCount === codes.length && codes.length > 0;
              return (
                <Box key={group.primaryLabel} sx={{ p: 2 }}>
                  <FormControlLabel
                    control={(
                      <Checkbox
                        checked={allChecked}
                        indeterminate={checkedCount > 0 && !allChecked}
                        onChange={(event) => {
                          setDraftSelectedTagCodes((current) => {
                            const next = new Set(current);
                            codes.forEach((code) => {
                              if (event.target.checked) {
                                next.add(code);
                              } else {
                                next.delete(code);
                              }
                            });
                            return next;
                          });
                        }}
                      />
                    )}
                    label={<Typography fontWeight={900}>{group.primaryLabel}</Typography>}
                  />
                  <Stack sx={{ pl: 4 }}>
                    {group.tags.map((tag) => {
                      const node = { code: tag.code, label: tag.label, primaryLabel: tagPrimaryLabel(tag), subLabel: tagSubLabel(tag) };
                      return (
                        <FormControlLabel
                          key={tag.code}
                          control={(
                            <Checkbox
                              checked={draftSelectedTagCodes.has(tag.code)}
                              onChange={(event) => {
                                setDraftSelectedTagCodes((current) => {
                                  const next = new Set(current);
                                  if (event.target.checked) {
                                    next.add(tag.code);
                                  } else {
                                    next.delete(tag.code);
                                  }
                                  return next;
                                });
                              }}
                            />
                          )}
                          label={node.subLabel ? tagDisplayLabel(node) : SELF_SUB_LABEL}
                        />
                      );
                    })}
                  </Stack>
                </Box>
              );
            })}
          </Stack>
        </Stack>
      </Drawer>

      <Dialog fullWidth maxWidth="xs" onClose={() => setWithdrawTarget(null)} open={Boolean(withdrawTarget)}>
        <DialogTitle>撤回批次</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Alert severity="warning">撤回后会取消关联台闭环关系，相关流水回到未配对区域。</Alert>
            <TextField autoFocus label="撤回原因" multiline minRows={3} onChange={(event) => setWithdrawReason(event.target.value)} value={withdrawReason} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWithdrawTarget(null)}>取消</Button>
          <Button disabled={!withdrawReason.trim() || mutating} onClick={handleConfirmWithdraw} variant="contained">确认撤回</Button>
        </DialogActions>
      </Dialog>

      <Snackbar autoHideDuration={3000} onClose={() => setSnackbar(null)} open={Boolean(snackbar)}>
        {snackbar ? <Alert onClose={() => setSnackbar(null)} severity={snackbar.severity} variant="filled">{snackbar.message}</Alert> : undefined}
      </Snackbar>
    </PageScaffold>
  );
}
