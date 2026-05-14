import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import KeyboardArrowDownOutlinedIcon from "@mui/icons-material/KeyboardArrowDownOutlined";
import KeyboardArrowRightOutlinedIcon from "@mui/icons-material/KeyboardArrowRightOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select, { type SelectChangeEvent } from "@mui/material/Select";
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

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import {
  fetchNoOaBankBatchDetail,
  fetchNoOaBankBatches,
  submitNoOaBankBatch,
  submitNoOaBankBatches,
  withdrawNoOaBankBatch,
} from "../features/noOaBankBatches/api";
import type {
  NoOaBankBatch,
  NoOaBankBatchDetail,
  NoOaBankBatchesResponse,
  NoOaBankBatchStatus,
  NoOaBankBatchStatusFilter,
  NoOaBankBatchTypeFilter,
} from "../features/noOaBankBatches/types";

const BATCH_TYPES: Array<{ value: NoOaBankBatchTypeFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "fee", label: "手续费" },
  { value: "salary", label: "工资" },
  { value: "holiday_bonus", label: "过节费" },
  { value: "bonus", label: "奖金" },
  { value: "internal_transfer", label: "内部往来款" },
];

const BATCH_STATUSES: Array<{ value: NoOaBankBatchStatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "draft", label: "待提交" },
  { value: "submitted", label: "已提交" },
  { value: "withdrawn", label: "已撤回" },
  { value: "conflict", label: "冲突" },
  { value: "stale", label: "需刷新确认" },
];

const EMPTY_BATCHES: NoOaBankBatchesResponse = {
  summary: {
    draftCount: 0,
    submittedCount: 0,
    withdrawnCount: 0,
    conflictCount: 0,
    totalAmount: "0.00",
  },
  batches: [],
};

const STATUS_META: Record<NoOaBankBatchStatus, { label: string; color: "default" | "primary" | "success" | "warning" | "error" }> = {
  draft: { label: "待提交", color: "warning" },
  submitted: { label: "已提交", color: "success" },
  withdrawn: { label: "已撤回", color: "default" },
  conflict: { label: "冲突", color: "error" },
  stale: { label: "需刷新确认", color: "primary" },
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
  const suffix = batch.accountLast4 ? batch.accountLast4 : "";
  return `${batch.bankName || "多账户"}${suffix}`;
}

function groupKey(batch: NoOaBankBatch) {
  return `${batch.bankName || "多账户"} / ${batch.scopeMonth || "-"}`;
}

function statusLabel(status: string) {
  return STATUS_META[status as NoOaBankBatchStatus]?.label ?? status;
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
  return batch.status === "draft";
}

function SummaryCard({ label, value, helper }: { label: string; value: string | number; helper?: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1, minHeight: 88 }}>
      <Typography color="text.secondary" fontWeight={800} variant="body2">
        {label}
      </Typography>
      <Typography fontWeight={900} sx={{ mt: 0.75 }} variant="h6">
        {value}
      </Typography>
      {helper ? (
        <Typography color="text.secondary" variant="caption">
          {helper}
        </Typography>
      ) : null}
    </Paper>
  );
}

function BatchStatusChip({ status }: { status: string }) {
  const meta = STATUS_META[status as NoOaBankBatchStatus] ?? { label: status, color: "default" as const };
  return <Chip color={meta.color} label={meta.label} size="small" />;
}

function DetailRows({ detail, loading, error }: { detail: NoOaBankBatchDetail | null; loading: boolean; error: string | null }) {
  if (loading) {
    return (
      <TableRow>
        <TableCell colSpan={9}>
          <StatePanel compact tone="loading" title="明细加载中" />
        </TableCell>
      </TableRow>
    );
  }
  if (error) {
    return (
      <TableRow>
        <TableCell colSpan={9}>
          <StatePanel compact tone="error" title={error} />
        </TableCell>
      </TableRow>
    );
  }
  if (!detail || detail.rows.length === 0) {
    return (
      <TableRow>
        <TableCell colSpan={9}>
          <StatePanel compact tone="empty" title="暂无批次明细" />
        </TableCell>
      </TableRow>
    );
  }
  return (
    <TableRow>
      <TableCell colSpan={9} sx={{ bgcolor: "action.hover", p: 1.5 }}>
        <Table size="small" aria-label="批次明细">
          <TableHead>
            <TableRow>
              <TableCell>交易时间</TableCell>
              <TableCell>对方户名</TableCell>
              <TableCell>收/支</TableCell>
              <TableCell align="right">金额</TableCell>
              <TableCell>摘要/用途/备注</TableCell>
              <TableCell>分类来源</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detail.rows.map((row) => (
              <TableRow key={row.transactionId || `${row.tradeTime}-${row.amount}`}>
                <TableCell>{row.tradeTime || "-"}</TableCell>
                <TableCell>{row.counterpartyName || "-"}</TableCell>
                <TableCell>{row.directionLabel || (row.direction === "income" ? "收" : row.direction === "expense" ? "支" : "-")}</TableCell>
                <TableCell align="right">{formatMoney(row.amount)}</TableCell>
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
      </TableCell>
    </TableRow>
  );
}

export default function NoOaBankBatchPage() {
  const [month, setMonth] = useState(currentMonth);
  const [type, setType] = useState<NoOaBankBatchTypeFilter>("all");
  const [status, setStatus] = useState<NoOaBankBatchStatusFilter>("all");
  const [accountKey, setAccountKey] = useState("");
  const [payload, setPayload] = useState<NoOaBankBatchesResponse>(EMPTY_BATCHES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, NoOaBankBatchDetail>>({});
  const [detailLoadingBatchId, setDetailLoadingBatchId] = useState<string | null>(null);
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [selectedBatchIds, setSelectedBatchIds] = useState<Set<string>>(() => new Set());
  const [mutating, setMutating] = useState(false);
  const [withdrawTarget, setWithdrawTarget] = useState<NoOaBankBatch | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "warning" | "error"; message: string } | null>(null);

  const groupedBatches = useMemo(() => {
    const groups = new Map<string, NoOaBankBatch[]>();
    for (const batch of payload.batches) {
      const key = groupKey(batch);
      groups.set(key, [...(groups.get(key) ?? []), batch]);
    }
    return Array.from(groups.entries()).map(([key, batches]) => ({ key, batches }));
  }, [payload.batches]);

  const selectedDraftBatches = useMemo(
    () => payload.batches.filter((batch) => selectedBatchIds.has(batch.batchId) && canSubmit(batch)),
    [payload.batches, selectedBatchIds],
  );

  const loadBatches = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    fetchNoOaBankBatches({
      month,
      type,
      status,
      accountKey: accountKey.trim(),
      signal,
    })
      .then((nextPayload) => {
        setPayload(nextPayload);
        setSelectedBatchIds((current) => {
          const available = new Set(nextPayload.batches.map((batch) => batch.batchId));
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
  }, [accountKey, month, status, type]);

  useEffect(() => {
    const controller = new AbortController();
    loadBatches(controller.signal);
    return () => controller.abort();
  }, [loadBatches]);

  const loadDetail = useCallback((batchId: string) => {
    if (details[batchId]) {
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

  const handleToggleExpand = (batch: NoOaBankBatch) => {
    const nextBatchId = expandedBatchId === batch.batchId ? null : batch.batchId;
    setExpandedBatchId(nextBatchId);
    if (nextBatchId) {
      loadDetail(nextBatchId);
    }
  };

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

  const handleMutationComplete = (message: string) => {
    window.dispatchEvent(new CustomEvent("workbenchRelationUpdated"));
    setSnackbar({ severity: "success", message });
    loadBatches();
  };

  const handleSubmitBatch = async (batch: NoOaBankBatch) => {
    if (!canSubmit(batch) || mutating) {
      return;
    }
    setMutating(true);
    try {
      await submitNoOaBankBatch({
        batchId: batch.batchId,
        expectedVersion: batch.version,
        note: "",
      });
      handleMutationComplete("批次已提交");
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
        window.dispatchEvent(new CustomEvent("workbenchRelationUpdated"));
      }
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
      await withdrawNoOaBankBatch({
        batchId: withdrawTarget.batchId,
        expectedVersion: withdrawTarget.version,
        reason: withdrawReason.trim(),
      });
      setWithdrawTarget(null);
      setWithdrawReason("");
      handleMutationComplete("批次已撤回");
    } catch (caught) {
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "撤回批次失败" });
    } finally {
      setMutating(false);
    }
  };

  const handleTypeChange = (event: SelectChangeEvent) => setType(event.target.value as NoOaBankBatchTypeFilter);
  const handleStatusChange = (event: SelectChangeEvent) => setStatus(event.target.value as NoOaBankBatchStatusFilter);

  return (
    <PageScaffold
      title="免OA流水批量处理"
      description="按银行账户、月份和类型确认免 OA 银行流水批次。"
      actions={(
        <Button
          disabled={loading}
          onClick={() => loadBatches()}
          startIcon={<RefreshOutlinedIcon />}
          variant="outlined"
        >
          刷新
        </Button>
      )}
    >
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <TextField
            InputLabelProps={{ shrink: true }}
            label="月份"
            onChange={(event) => setMonth(event.target.value)}
            size="small"
            type="month"
            value={month}
          />
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="no-oa-type-label">类型</InputLabel>
            <Select label="类型" labelId="no-oa-type-label" onChange={handleTypeChange} value={type}>
              {BATCH_TYPES.map((item) => (
                <MenuItem key={item.value} value={item.value}>
                  {item.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="no-oa-status-label">状态</InputLabel>
            <Select label="状态" labelId="no-oa-status-label" onChange={handleStatusChange} value={status}>
              {BATCH_STATUSES.map((item) => (
                <MenuItem key={item.value} value={item.value}>
                  {item.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="银行账户"
            onChange={(event) => setAccountKey(event.target.value)}
            placeholder="银行或账户尾号"
            size="small"
            value={accountKey}
          />
        </Stack>
      </Paper>

      <Box
        sx={{
          display: "grid",
          gap: 1.5,
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(5, minmax(0, 1fr))" },
        }}
      >
        <SummaryCard label="待提交批次" value={payload.summary.draftCount} />
        <SummaryCard label="已提交批次" value={payload.summary.submittedCount} />
        <SummaryCard label="已撤回批次" value={payload.summary.withdrawnCount} />
        <SummaryCard label="冲突批次" value={payload.summary.conflictCount} />
        <SummaryCard helper="当前筛选范围" label="金额合计" value={formatMoney(payload.summary.totalAmount)} />
      </Box>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5} sx={{ px: 2, py: 1.5 }}>
          <Typography fontWeight={900}>批次列表</Typography>
          <Button disabled={selectedDraftBatches.length === 0 || mutating} onClick={handleBulkSubmit} variant="contained">
            批量提交选中
          </Button>
        </Stack>
        <TableContainer>
          <Table size="small" aria-label="免OA流水批量处理表格">
            <TableHead>
              <TableRow>
                <TableCell width={88}>选择</TableCell>
                <TableCell>批次类型</TableCell>
                <TableCell>银行账户</TableCell>
                <TableCell>月份</TableCell>
                <TableCell align="right">流水数</TableCell>
                <TableCell align="right">金额</TableCell>
                <TableCell>状态</TableCell>
                <TableCell>提交信息</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9}>
                    <StatePanel compact tone="loading" title="批次加载中" />
                  </TableCell>
                </TableRow>
              ) : null}
              {!loading && payload.batches.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9}>
                    <StatePanel compact tone="empty" title="暂无免OA流水批次" />
                  </TableCell>
                </TableRow>
              ) : null}
              {groupedBatches.map((group) => (
                <Fragment key={group.key}>
                  <TableRow sx={{ bgcolor: "background.default" }}>
                    <TableCell colSpan={9}>
                      <Typography fontWeight={900}>{group.key}</Typography>
                    </TableCell>
                  </TableRow>
                  {group.batches.map((batch) => {
                    const expanded = expandedBatchId === batch.batchId;
                    return (
                      <Fragment key={batch.batchId}>
                        <TableRow hover>
                          <TableCell>
                            <Stack alignItems="center" direction="row" spacing={0.5}>
                              <IconButton
                                aria-label={`${expanded ? "收起" : "展开"} ${batch.batchLabel} ${accountLabel(batch)} ${batch.scopeMonth} 明细`}
                                onClick={() => handleToggleExpand(batch)}
                                size="small"
                              >
                                {expanded ? <KeyboardArrowDownOutlinedIcon fontSize="small" /> : <KeyboardArrowRightOutlinedIcon fontSize="small" />}
                              </IconButton>
                              <Checkbox
                                checked={selectedBatchIds.has(batch.batchId)}
                                disabled={!canSubmit(batch)}
                                inputProps={{
                                  "aria-label": `选择 ${batch.batchLabel} ${accountLabel(batch)} ${batch.scopeMonth}`,
                                }}
                                onChange={(event) => handleSelectBatch(batch, event.target.checked)}
                                size="small"
                              />
                            </Stack>
                          </TableCell>
                          <TableCell>{batch.batchLabel || batch.batchType}</TableCell>
                          <TableCell>{accountLabel(batch)}</TableCell>
                          <TableCell>{batch.scopeMonth}</TableCell>
                          <TableCell align="right">{batch.rowCount}</TableCell>
                          <TableCell align="right">{formatMoney(batch.totalAmount)}</TableCell>
                          <TableCell>
                            <Stack alignItems="flex-start" spacing={0.5}>
                              <BatchStatusChip status={batch.status} />
                              {batch.conflictReason ? (
                                <Typography color="error" variant="caption">
                                  {batch.conflictReason}
                                </Typography>
                              ) : null}
                            </Stack>
                          </TableCell>
                          <TableCell>
                            {batch.status === "submitted" ? (
                              <Stack spacing={0.25}>
                                <Typography variant="body2">{batch.submittedBy || "-"}</Typography>
                                <Typography color="text.secondary" variant="caption">
                                  {formatDateTime(batch.submittedAt)}
                                </Typography>
                              </Stack>
                            ) : batch.status === "withdrawn" ? (
                              <Stack spacing={0.25}>
                                <Typography variant="body2">{batch.withdrawnBy || "-"}</Typography>
                                <Typography color="text.secondary" variant="caption">
                                  {formatDateTime(batch.withdrawnAt)}
                                </Typography>
                              </Stack>
                            ) : (
                              <Typography color="text.secondary" variant="body2">
                                -
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">
                            <Stack direction="row" justifyContent="flex-end" spacing={1}>
                              <Button
                                onClick={() => {
                                  setExpandedBatchId(batch.batchId);
                                  loadDetail(batch.batchId);
                                }}
                                size="small"
                                startIcon={<VisibilityOutlinedIcon />}
                              >
                                查看详情
                              </Button>
                              {batch.status === "submitted" ? (
                                <Button disabled={mutating} onClick={() => setWithdrawTarget(batch)} size="small" variant="outlined">
                                  撤回批次
                                </Button>
                              ) : (
                                <Button disabled={!canSubmit(batch) || mutating} onClick={() => handleSubmitBatch(batch)} size="small" variant="contained">
                                  提交批次
                                </Button>
                              )}
                            </Stack>
                          </TableCell>
                        </TableRow>
                        {expanded ? (
                          <DetailRows
                            detail={details[batch.batchId] ?? null}
                            error={detailErrors[batch.batchId] || null}
                            loading={detailLoadingBatchId === batch.batchId}
                          />
                        ) : null}
                      </Fragment>
                    );
                  })}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

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
