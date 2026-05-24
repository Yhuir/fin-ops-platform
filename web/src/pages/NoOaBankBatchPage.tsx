import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import {
  FINANCE_DOMAIN_EVENTS,
  emitFinanceDomainEvent,
  subscribeFinanceDomainEvent,
} from "../features/domainEvents";
import {
  fetchNoOaBankBatchDetail,
  fetchNoOaBankBatches,
  submitNoOaBankBatch,
  submitNoOaBankBatches,
  withdrawNoOaBankBatch,
} from "../features/noOaBankBatches/api";
import type {
  NoOaBankBatch,
  NoOaBankBatchCountMap,
  NoOaBankBatchDetail,
  NoOaBankBatchesResponse,
  NoOaBankBatchType,
  NoOaBankBatchStatus,
  NoOaBankBatchStatusBucket,
} from "../features/noOaBankBatches/types";

const NO_OA_CATEGORIES: Array<{ value: NoOaBankBatchType; label: string }> = [
  { value: "fee", label: "手续费" },
  { value: "salary", label: "工资" },
  { value: "holiday_bonus", label: "过节费" },
  { value: "bonus", label: "奖金" },
  { value: "tax_payment", label: "税款" },
  { value: "treasury_tax_collection", label: "代理国库税收收缴" },
  { value: "social_security", label: "社保款" },
  { value: "internal_transfer", label: "内部往来款" },
];

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
};

const STATUS_META: Record<NoOaBankBatchStatus, { label: string; color: "default" | "primary" | "success" | "warning" | "error" }> = {
  draft: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
  conflict: { label: "冲突", color: "error" },
  stale: { label: "需复核", color: "primary" },
};

const TAG_LABELS: Record<string, string> = {
  fee: "手续费",
  salary: "工资",
  holiday_bonus: "过节费",
  bonus: "奖金",
  tax_payment: "税款",
  treasury_tax_collection: "代理国库税收收缴",
  social_security: "社保款",
  internal_transfer: "内部往来款",
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

function formatDateTime(value: string | null) {
  if (!value) {
    return "-";
  }
  return value.replace("T", " ").slice(0, 19);
}

function canSubmit(batch: NoOaBankBatch) {
  return batch.canSubmit || batch.status === "draft";
}

function canWithdraw(batch: NoOaBankBatch) {
  return batch.canWithdraw || batch.status === "submitted";
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

function blockedReason(batch: NoOaBankBatch) {
  return batch.blockedReason || batch.conflictReason || (batch.status === "stale" ? "源流水或分类已变化，需要复核后处理" : "");
}

function BatchStatusChip({ status }: { status: string }) {
  const meta = STATUS_META[status as NoOaBankBatchStatus] ?? { label: status, color: "default" as const };
  return <Chip color={meta.color} label={meta.label} size="small" />;
}

function formatCounts(counts: NoOaBankBatchCountMap, fallbackType: string, fallbackCount: number) {
  const entries = Object.entries(counts);
  if (entries.length === 0 && fallbackType) {
    return `${TAG_LABELS[fallbackType] ?? fallbackType} ${fallbackCount}`;
  }
  return entries.map(([code, count]) => `${TAG_LABELS[code] ?? code} ${count}`).join(" · ");
}

function formatDirectionCounts(counts: NoOaBankBatchCountMap) {
  const income = counts.income ?? 0;
  const expense = counts.expense ?? 0;
  if (!income && !expense) {
    return "";
  }
  return `收入 ${income} / 支出 ${expense}`;
}

function categoryRowCount(batch: NoOaBankBatch, category: NoOaBankBatchType) {
  const explicitCount = batch.tagCounts[category];
  if (typeof explicitCount === "number" && Number.isFinite(explicitCount)) {
    return explicitCount;
  }
  if (batch.batchType === category) {
    return batch.rowCount;
  }
  return 0;
}

function mutationEventDetail(result: { affectedMonths?: string[] }) {
  return { affectedMonths: result.affectedMonths ?? [] };
}

export default function NoOaBankBatchPage() {
  const [month, setMonth] = useState(currentMonth);
  const [selectedCategory, setSelectedCategory] = useState<NoOaBankBatchType>("fee");
  const [bucket, setBucket] = useState<NoOaBankBatchStatusBucket>("unsubmitted");
  const [accountKey, setAccountKey] = useState("");
  const [payload, setPayload] = useState<NoOaBankBatchesResponse>(EMPTY_BATCHES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, NoOaBankBatchDetail>>({});
  const [detailLoadingBatchId, setDetailLoadingBatchId] = useState<string | null>(null);
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [selectedBatchIds, setSelectedBatchIds] = useState<Set<string>>(() => new Set());
  const [mutating, setMutating] = useState(false);
  const [withdrawTarget, setWithdrawTarget] = useState<NoOaBankBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);

  const visibleBucketBatches = useMemo(
    () => payload.batches.filter((batch) => statusBucketFor(batch) === bucket),
    [bucket, payload.batches],
  );

  const noOaCategories = useMemo(() => {
    const categories = payload.summary.categories
      .map((category) => ({
        value: category.code as NoOaBankBatchType,
        label: category.label || TAG_LABELS[category.code] || category.code,
      }))
      .filter((category) => category.value && category.label);
    return categories.length > 0 ? categories : NO_OA_CATEGORIES;
  }, [payload.summary.categories]);

  const categoryStats = useMemo(() => {
    const stats = new Map<NoOaBankBatchType, { batchCount: number; rowCount: number }>();
    noOaCategories.forEach((category) => stats.set(category.value, { batchCount: 0, rowCount: 0 }));
    visibleBucketBatches.forEach((batch) => {
      noOaCategories.forEach((category) => {
        const rowCount = categoryRowCount(batch, category.value);
        if (rowCount > 0 || batch.batchType === category.value) {
          const current = stats.get(category.value) ?? { batchCount: 0, rowCount: 0 };
          stats.set(category.value, {
            batchCount: current.batchCount + 1,
            rowCount: current.rowCount + rowCount,
          });
        }
      });
    });
    return stats;
  }, [noOaCategories, visibleBucketBatches]);

  const visibleBatches = useMemo(
    () => visibleBucketBatches.filter((batch) => batch.batchType === selectedCategory || (batch.tagCounts[selectedCategory] ?? 0) > 0),
    [selectedCategory, visibleBucketBatches],
  );

  const selectedCategoryMeta = noOaCategories.find((category) => category.value === selectedCategory) ?? noOaCategories[0];
  const selectedCategoryStats = categoryStats.get(selectedCategory) ?? { batchCount: 0, rowCount: 0 };
  const unsubmittedCount = payload.summary.draftCount + payload.summary.conflictCount + payload.summary.staleCount;

  const selectedBatch = useMemo(
    () => visibleBatches.find((batch) => batch.batchId === selectedBatchId) ?? null,
    [selectedBatchId, visibleBatches],
  );

  const selectedDetail = selectedBatch ? details[selectedBatch.batchId] ?? null : null;

  const selectedDraftBatches = useMemo(
    () => payload.batches.filter((batch) => selectedBatchIds.has(batch.batchId) && canSubmit(batch)),
    [payload.batches, selectedBatchIds],
  );

  const loadBatches = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchNoOaBankBatches({
      month,
      bucket,
      accountKey: accountKey.trim(),
      signal,
    })
      .then((nextPayload) => {
        setPayload(nextPayload);
        const nextVisible = nextPayload.batches.filter((batch) => (
          statusBucketFor(batch) === bucket
          && (batch.batchType === selectedCategory || (batch.tagCounts[selectedCategory] ?? 0) > 0)
        ));
        setSelectedBatchId((current) => (current && nextVisible.some((batch) => batch.batchId === current) ? current : nextVisible[0]?.batchId ?? null));
        setSelectedBatchIds((current) => {
          const available = new Set(nextPayload.batches.filter(canSubmit).map((batch) => batch.batchId));
          return new Set(Array.from(current).filter((batchId) => available.has(batchId)));
        });
      })
      .catch((caught: unknown) => {
        if (isAbortLikeError(caught)) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "免OA流水批次加载失败");
      })
      .finally(() => setLoading(false));
  }, [accountKey, bucket, month, selectedCategory]);

  const loadDetail = useCallback((batchId: string, force = false) => {
    if (!force && details[batchId]) {
      return;
    }
    setDetailLoadingBatchId(batchId);
    setDetailErrors((current) => ({ ...current, [batchId]: "" }));
    fetchNoOaBankBatchDetail(batchId)
      .then((detail) => {
        setDetails((current) => ({ ...current, [batchId]: detail }));
      })
      .catch((caught: unknown) => {
        setDetailErrors((current) => ({
          ...current,
          [batchId]: caught instanceof Error ? caught.message : "批次明细加载失败",
        }));
      })
      .finally(() => setDetailLoadingBatchId(null));
  }, [details]);

  useEffect(() => {
    const controller = new AbortController();
    setSelectedBatchId(null);
    setSelectedBatchIds(new Set());
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [loadBatches]);

  useEffect(() => {
    if (selectedBatchId) {
      loadDetail(selectedBatchId);
    }
  }, [loadDetail, selectedBatchId]);

  useEffect(() => {
    const handleCategoryUpdated = () => {
      setDetails({});
      loadBatches();
    };
    return subscribeFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handleCategoryUpdated);
  }, [loadBatches]);

  const handleSelectBatch = (batch: NoOaBankBatch, checked: boolean) => {
    setSelectedBatchIds((current) => {
      const next = new Set(current);
      if (checked && canSubmit(batch)) {
        next.add(batch.batchId);
      } else {
        next.delete(batch.batchId);
      }
      return next;
    });
  };

  const handleMutationComplete = (message: string, result: { affectedMonths?: string[] }) => {
    emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
      ...mutationEventDetail(result),
    });
    setDetails({});
    setSnackbar({ severity: "success", message });
    loadBatches();
  };

  const handleSubmitBatch = async (batch: NoOaBankBatch) => {
    if (!canSubmit(batch) || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await submitNoOaBankBatch({
        batchId: batch.batchId,
        expectedVersion: batch.version,
        note: "",
      });
      handleMutationComplete("批次已提交", result);
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "提交批次失败" });
    } finally {
      setMutating(false);
    }
  };

  const handleBulkSubmit = async () => {
    if (selectedDraftBatches.length === 0 || mutating) {
      return;
    }
    setMutating(true);
    try {
      const result = await submitNoOaBankBatches({
        batches: selectedDraftBatches.map((batch) => ({
          batchId: batch.batchId,
          expectedVersion: batch.version,
        })),
      });
      const submittedCount = result.results.filter((item) => String(item.status || "") === "submitted").length;
      const failedResults = result.results.filter((item) => String(item.status || "") === "failed");
      const failedBatchIds = new Set(
        failedResults
          .map((item) => String(item.batch_id || item.batchId || ""))
          .filter(Boolean),
      );
      setSelectedBatchIds((previous) => {
        if (failedBatchIds.size === 0) {
          return new Set();
        }
        return new Set([...previous].filter((batchId) => failedBatchIds.has(batchId)));
      });
      if (submittedCount > 0) {
        emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, {
          ...mutationEventDetail(result),
        });
      }
      setDetails({});
      if (failedResults.length === 0) {
        setSnackbar({ severity: "success", message: "选中批次已提交" });
      } else if (submittedCount > 0) {
        setSnackbar({ severity: "warning", message: `已提交 ${submittedCount} 个，失败 ${failedResults.length} 个，请查看失败项后重试` });
      } else {
        setSnackbar({ severity: "error", message: "批量提交失败，请查看失败项后重试" });
      }
      loadBatches();
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "批量提交失败" });
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

  const handleBucketChange = (_event: MouseEvent<HTMLElement>, nextBucket: NoOaBankBatchStatusBucket | null) => {
    if (!nextBucket) {
      return;
    }
    setBucket(nextBucket);
  };

  const handleCategoryChange = (nextCategory: NoOaBankBatchType) => {
    setSelectedCategory(nextCategory);
    const nextVisible = visibleBucketBatches.filter((batch) => batch.batchType === nextCategory || (batch.tagCounts[nextCategory] ?? 0) > 0);
    setSelectedBatchId(nextVisible[0]?.batchId ?? null);
  };

  const selectedTagCounts = selectedDetail?.tagCounts ?? selectedBatch?.tagCounts ?? {};
  const selectedDirectionCounts = selectedDetail?.directionCounts ?? selectedBatch?.directionCounts ?? {};

  return (
    <PageScaffold
      title="免OA流水批量处理"
      description="按银行账户、月份和类型确认免 OA 银行流水批次。"
      actions={(
        <Button
          disabled={loading}
          onClick={() => {
            setDetails({});
            loadBatches();
          }}
          startIcon={<RefreshOutlinedIcon />}
          variant="outlined"
        >
          刷新
        </Button>
      )}
    >
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
        <Stack alignItems={{ xs: "stretch", lg: "center" }} direction={{ xs: "column", lg: "row" }} spacing={1.5}>
          <ToggleButtonGroup
            aria-label="批次状态"
            color="primary"
            exclusive
            onChange={handleBucketChange}
            size="small"
            value={bucket}
          >
            <ToggleButton value="unsubmitted">未提交 {unsubmittedCount}</ToggleButton>
            <ToggleButton value="submitted">已提交 {payload.summary.submittedCount}</ToggleButton>
          </ToggleButtonGroup>
          <TextField
            InputLabelProps={{ shrink: true }}
            label="月份"
            onChange={(event) => setMonth(event.target.value)}
            size="small"
            type="month"
            value={month}
          />
          <TextField
            label="银行账户"
            onChange={(event) => setAccountKey(event.target.value)}
            placeholder="银行或账户尾号"
            size="small"
            value={accountKey}
          />
        </Stack>
      </Paper>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <Box
        sx={{
          display: "grid",
          gap: 1.5,
          gridTemplateColumns: { xs: "1fr", lg: "280px 280px minmax(0, 1fr)" },
          alignItems: "start",
        }}
      >
        <Paper aria-label="免OA分类" role="region" variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack spacing={0.5} sx={{ px: 2, py: 1.5 }}>
            <Typography fontWeight={900}>免OA分类</Typography>
            <Typography color="text.secondary" variant="caption">固定显示全部免OA标签</Typography>
          </Stack>
          <Divider />
          <Stack divider={<Divider flexItem />}>
            {noOaCategories.map((category) => {
              const stats = categoryStats.get(category.value) ?? { batchCount: 0, rowCount: 0 };
              const selected = selectedCategory === category.value;
              return (
                <Box
                  aria-label={`${category.label} ${stats.batchCount} 批 ${stats.rowCount} 条`}
                  aria-pressed={selected}
                  key={category.value}
                  onClick={() => handleCategoryChange(category.value)}
                  role="button"
                  sx={{
                    bgcolor: selected ? "action.selected" : "background.paper",
                    borderLeft: selected ? 4 : 0,
                    borderColor: "primary.main",
                    cursor: "pointer",
                    px: 2,
                    py: 1.5,
                  }}
                  tabIndex={0}
                >
                  <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
                    <Typography fontWeight={900}>{category.label}</Typography>
                    <Chip label={`${stats.batchCount} 批 / ${stats.rowCount} 条`} size="small" variant={selected ? "filled" : "outlined"} />
                  </Stack>
                </Box>
              );
            })}
          </Stack>
        </Paper>

        <Paper aria-label="免OA批次" role="region" variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5} sx={{ px: 2, py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
              <Typography component="h2" variant="h6" fontWeight={900}>
                {selectedCategoryMeta.label} {selectedCategoryStats.batchCount} 批 / {selectedCategoryStats.rowCount} 条
              </Typography>
            </Stack>
            <Button disabled={selectedDraftBatches.length === 0 || mutating} onClick={handleBulkSubmit} size="small" variant="contained">
              批量提交选中
            </Button>
          </Stack>
          <Divider />
          <Stack divider={<Divider flexItem />} sx={{ maxHeight: { lg: "30vh" }, overflow: "auto" }}>
            {loading ? <StatePanel compact tone="loading" title="批次加载中" /> : null}
            {!loading && visibleBatches.length === 0 ? <StatePanel compact tone="empty" title={`当前状态下暂无${selectedCategoryMeta.label}批次`} /> : null}
            {!loading
              ? visibleBatches.map((batch) => {
                const selected = selectedBatchId === batch.batchId;
                const reason = blockedReason(batch);
                const isSubmitReady = canSubmit(batch);
                return (
                  <Box
                    aria-label={`${batch.batchLabel || batch.batchType} ${accountLabel(batch)} ${batch.scopeMonth} ${batch.rowCount} 条 ${reason}`}
                    key={batch.batchId}
                    onClick={() => setSelectedBatchId(batch.batchId)}
                    role="button"
                    sx={{
                      bgcolor: selected ? "action.selected" : "background.paper",
                      borderLeft: selected ? 4 : 0,
                      borderColor: "primary.main",
                      cursor: "pointer",
                      p: 1.5,
                    }}
                    tabIndex={0}
                  >
                    <Stack spacing={1}>
                      <Stack alignItems="flex-start" direction="row" justifyContent="space-between" spacing={1}>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Checkbox
                            checked={selectedBatchIds.has(batch.batchId)}
                            disabled={!isSubmitReady}
                            inputProps={{
                              "aria-label": `选择 ${batch.batchLabel} ${accountLabel(batch)} ${batch.scopeMonth}`,
                            }}
                            onChange={(event) => handleSelectBatch(batch, event.target.checked)}
                            onClick={(event) => event.stopPropagation()}
                            size="small"
                          />
                          <Box>
                            <Typography fontWeight={900}>{batch.batchLabel || batch.batchType}</Typography>
                            <Typography color="text.secondary" variant="caption">
                              {batch.scopeMonth} · {accountLabel(batch)}
                            </Typography>
                          </Box>
                        </Stack>
                        <BatchStatusChip status={batch.status} />
                      </Stack>
                      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        <Chip label={batch.scopeMonth || "-"} size="small" />
                        <Chip label={accountLabel(batch)} size="small" variant="outlined" />
                        <Chip label={`${batch.rowCount} 条`} size="small" variant="outlined" />
                        <Chip label={batch.batchLabel || batch.batchType} size="small" variant="outlined" />
                      </Stack>
                      {reason ? (
                        <Typography color={batch.status === "conflict" ? "error" : "text.secondary"} variant="caption">
                          {reason}
                        </Typography>
                      ) : null}
                      {batch.status === "submitted" ? (
                        <Typography color="text.secondary" variant="caption">
                          {batch.submittedBy || "-"} · {formatDateTime(batch.submittedAt)}
                        </Typography>
                      ) : null}
                      <Stack direction="row" spacing={1}>
                        {isSubmitReady ? (
                          <Button disabled={mutating} onClick={(event) => {
                            event.stopPropagation();
                            handleSubmitBatch(batch);
                          }} size="small" variant="contained">
                            提交批次
                          </Button>
                        ) : null}
                        {canWithdraw(batch) ? (
                          <Button disabled={mutating} onClick={(event) => {
                            event.stopPropagation();
                            setWithdrawTarget(batch);
                          }} size="small" variant="outlined">
                            撤回批次
                          </Button>
                        ) : null}
                      </Stack>
                    </Stack>
                  </Box>
                );
              })
              : null}
          </Stack>
        </Paper>

        <Paper aria-label="批次明细" role="region" variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
            {selectedBatch ? (
              <>
              <Stack spacing={1} sx={{ px: 2, py: 1.5 }}>
                <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
                  <Typography fontWeight={900}>
                    {selectedBatch.batchLabel || selectedBatch.batchType} · {selectedBatch.rowCount} 条 · 合计 {formatMoney(selectedBatch.totalAmount)}
                  </Typography>
                  <BatchStatusChip status={selectedBatch.status} />
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip label={formatCounts(selectedTagCounts, selectedBatch.batchType, selectedBatch.rowCount)} size="small" />
                  {selectedBatch.batchType === "internal_transfer" && formatDirectionCounts(selectedDirectionCounts) ? (
                    <Chip label={formatDirectionCounts(selectedDirectionCounts)} size="small" variant="outlined" />
                  ) : null}
                </Stack>
              </Stack>
              <Divider />
              {detailErrors[selectedBatch.batchId] ? (
                <StatePanel compact tone="error" title={detailErrors[selectedBatch.batchId]} />
              ) : null}
              {detailLoadingBatchId === selectedBatch.batchId && !selectedDetail ? (
                <StatePanel compact tone="loading" title="明细加载中" />
              ) : null}
              {selectedDetail && selectedDetail.rows.length === 0 ? (
                <StatePanel compact tone="empty" title="暂无批次明细" />
              ) : null}
              {selectedDetail && selectedDetail.rows.length > 0 ? (
                <TableContainer sx={{ maxHeight: { lg: "60vh" } }}>
                  <Table stickyHeader size="small" aria-label="批次明细表格">
	                    <TableHead>
	                      <TableRow>
	                        <TableCell>交易时间</TableCell>
	                        <TableCell>对方户名</TableCell>
	                        <TableCell align="right">金额</TableCell>
	                        <TableCell>摘要/用途/备注</TableCell>
	                        <TableCell>分类来源</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {selectedDetail.rows.map((row) => (
	                        <TableRow key={row.transactionId || `${row.tradeTime}-${row.amount}`}>
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
                              <Typography color="text.secondary" variant="caption">
                                {[row.purpose, row.remark].filter(Boolean).join(" / ") || "-"}
                              </Typography>
                            </Stack>
                          </TableCell>
                          <TableCell>{sourceLabel(row.categorySource)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}
              </>
            ) : (
              <StatePanel compact tone="empty" title="请选择批次查看明细" />
            )}
        </Paper>
      </Box>

      <Dialog fullWidth maxWidth="xs" onClose={() => setWithdrawTarget(null)} open={Boolean(withdrawTarget)}>
        <DialogTitle>撤回批次</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Alert severity="warning">撤回后会取消关联台闭环关系，相关流水回到未配对区域。</Alert>
            <TextField
              autoFocus
              label="撤回原因"
              multiline
              minRows={3}
              onChange={(event) => setWithdrawReason(event.target.value)}
              value={withdrawReason}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWithdrawTarget(null)}>取消</Button>
          <Button disabled={!withdrawReason.trim() || mutating} onClick={handleConfirmWithdraw} variant="contained">
            确认撤回
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        autoHideDuration={3000}
        onClose={() => setSnackbar(null)}
        open={Boolean(snackbar)}
      >
        {snackbar ? (
          <Alert onClose={() => setSnackbar(null)} severity={snackbar.severity} variant="filled">
            {snackbar.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </PageScaffold>
  );
}
