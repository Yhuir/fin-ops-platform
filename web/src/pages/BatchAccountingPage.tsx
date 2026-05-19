import { useCallback, useEffect, useMemo, useState, type FocusEvent, type MouseEvent } from "react";
import ClearOutlinedIcon from "@mui/icons-material/ClearOutlined";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
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
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
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
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
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

function ExpandableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const shouldOfferToggle = text.length > 18;
  return (
    <Stack spacing={0.5}>
      <Typography
        color="text.primary"
        noWrap={!expanded}
        sx={{ maxWidth: 320 }}
        title={text}
        variant="body2"
      >
        {text || "-"}
      </Typography>
      {shouldOfferToggle ? (
        <Button onClick={() => setExpanded((current) => !current)} size="small" sx={{ alignSelf: "flex-start", minWidth: 0, px: 0.5 }}>
          {expanded ? "收起" : "展开"}
        </Button>
      ) : null}
    </Stack>
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
  const showTooltip = () => setOpen(true);
  const hideTooltip = (event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>) => {
    if (event.type === "mouseleave" || event.type === "blur") {
      setOpen(false);
    }
  };

  return (
    <Tooltip
      arrow
      describeChild
      disableFocusListener
      disableHoverListener
      disableTouchListener
      onClose={() => setOpen(false)}
      open={open}
      placement="top"
      title={(
        <Stack spacing={0.5}>
          <span>{`银行流水金额：${formatMoney(amountCheck.bankAmount)}`}</span>
          <span>{`OA合计：${formatMoney(amountCheck.oaAmount)}`}</span>
          <span>{`差额：${formatMoney(amountCheck.amountDelta)}`}</span>
          <span>{`差额说明：${note || "-"}`}</span>
        </Stack>
      )}
    >
      <IconButton
        aria-label="查看金额不一致差额说明"
        color="warning"
        onBlur={hideTooltip}
        onClick={showTooltip}
        onFocus={showTooltip}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onTouchStart={showTooltip}
        size="small"
        sx={{ height: 28, ml: -0.5, width: 28 }}
      >
        <WarningAmberRoundedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
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
  const [snackbar, setSnackbar] = useState<{ severity: "success" | "error"; message: string } | null>(null);

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

  const handleBucketChange = (_event: MouseEvent<HTMLElement>, nextBucket: BatchAccountingBucket | null) => {
    if (!nextBucket) {
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
    window.dispatchEvent(new CustomEvent("workbenchRelationUpdated", { detail: mutationEventDetail(result) }));
    setSnackbar({ severity: "success", message: result.message || fallbackMessage });
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
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "关联OA项与流水失败" });
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
      setSnackbar({ severity: "error", message: caught instanceof Error ? caught.message : "撤回关联失败" });
    } finally {
      setMutating(false);
    }
  };

  return (
    <PageScaffold
      title="日常报销批量账务管理"
      actions={(
        <Button
          disabled={loading}
          onClick={() => loadData()}
          startIcon={<RefreshOutlinedIcon />}
          variant="outlined"
        >
          刷新
        </Button>
      )}
    >
      <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
        <Stack alignItems={{ xs: "stretch", md: "center" }} direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <ToggleButtonGroup
            aria-label="批量账务状态"
            color="primary"
            exclusive
            onChange={handleBucketChange}
            size="small"
            value={bucket}
          >
            <ToggleButton value="unsubmitted">未提交 {payload.summary.unsubmittedCount}</ToggleButton>
            <ToggleButton value="submitted">已提交 {payload.summary.submittedCount}</ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      </Paper>

      {error ? <StatePanel tone="error" title={error} /> : null}

      <Box
        sx={{
          display: "grid",
          gap: 1.5,
          gridTemplateColumns: { xs: "1fr", lg: "30% minmax(0, 1fr)" },
          alignItems: "start",
        }}
      >
        <Paper aria-label="批量账务流水" role="region" variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack alignItems={{ xs: "stretch", sm: "center" }} direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.25} sx={{ px: 2, py: 1.5 }}>
            <Box>
              <Typography fontWeight={900}>批量账务流水</Typography>
              <Typography color="text.secondary" variant="caption">对方户名精确匹配批量账务集中处理</Typography>
            </Box>
            <TextField
              InputLabelProps={{ shrink: true }}
              inputProps={{ min: 2000, max: 2100 }}
              label="流水年份"
              onChange={(event) => setBankYear(event.target.value)}
              size="small"
              sx={{ width: { xs: "100%", sm: 128 } }}
              type="number"
              value={bankYear}
            />
          </Stack>
          <Divider />
          {loading ? (
            <Box sx={{ p: 2 }}>
              <StatePanel compact tone="loading" title="正在加载流水" />
            </Box>
          ) : null}
          {!loading && payload.bankRows.length === 0 ? (
            <Box sx={{ p: 2 }}>
              <StatePanel compact tone="empty" title="当前年份暂无批量账务流水" />
            </Box>
          ) : null}
          <Stack divider={<Divider flexItem />}>
            {payload.bankRows.map((row) => {
              const selected = row.id === selectedBankRowId;
              return (
                <Box
                  aria-label={`批量账务集中处理 ${formatMoney(row.amount)} ${row.tradeTime} ${row.directionLabel || "支出"} ${accountLabel(row)}`}
                  aria-pressed={selected}
                  key={row.id}
                  onClick={() => handleSelectBankRow(row)}
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
                  <Stack spacing={1}>
                    <Stack alignItems="baseline" direction="row" justifyContent="space-between" spacing={1}>
                      <Typography fontWeight={900}>批量账务集中处理</Typography>
                      <Typography fontWeight={900} sx={{ whiteSpace: "nowrap" }}>{formatMoney(row.amount)}</Typography>
                    </Stack>
                    <Stack direction="row" flexWrap="wrap" spacing={0.75} useFlexGap>
                      <Chip label={row.tradeTime || "-"} size="small" variant="outlined" />
                      <Chip color="warning" label={row.directionLabel || "支出"} size="small" />
                      <Chip label={accountLabel(row)} size="small" variant="outlined" />
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
          <Stack alignItems={{ xs: "stretch", xl: "center" }} direction={{ xs: "column", xl: "row" }} justifyContent="space-between" spacing={1.5} sx={{ px: 2, py: 1.5 }}>
            <Stack direction={{ xs: "column", lg: "row" }} spacing={1.25} sx={{ minWidth: 0 }}>
              <Stack direction="row" flexWrap="wrap" spacing={1} useFlexGap>
                <Stack alignItems="center" direction="row" spacing={0.5}>
                  <Chip label={`银行流水金额 ${formatCents(bankAmountCents)}`} />
                  {submittedAmountMismatch && selectedRelationAmountCheck ? (
                    <AmountMismatchWarning
                      amountCheck={selectedRelationAmountCheck}
                      note={selectedRelation?.note ?? ""}
                    />
                  ) : null}
                </Stack>
                <Chip label={`已选 OA ${selectedOaRows.length} 项`} />
                <Chip label={`已选 OA 金额 ${formatCents(selectedOaTotalCents)}`} />
                <Chip color={differenceCents === 0 ? "success" : "warning"} label={`差额 ${formatCents(differenceCents)}`} />
                {submittedAmountMismatch ? (
                  <Chip color="warning" label="金额不一致" />
                ) : null}
              </Stack>
              {isAmountMismatch ? (
                <TextField
                  helperText="金额不一致时必须填写，提交后视为人工差额闭环。"
                  inputProps={{ "aria-required": true }}
                  label="差额说明"
                  onChange={(event) => setDifferenceNote(event.target.value)}
                  size="small"
                  sx={{ minWidth: { xs: "100%", lg: 260 } }}
                  value={differenceNote}
                />
              ) : null}
              <TextField
                InputLabelProps={{ shrink: true }}
                inputProps={{ min: 2000, max: 2100 }}
                label="OA年份"
                onChange={(event) => setOaYear(event.target.value)}
                size="small"
                sx={{ width: { xs: "100%", lg: 128 } }}
                type="number"
                value={oaYear}
              />
              <TextField
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchOutlinedIcon fontSize="small" />
                    </InputAdornment>
                  ),
                  endAdornment: oaSearchQuery ? (
                    <InputAdornment position="end">
                      <IconButton aria-label="清空搜索" edge="end" onClick={() => setOaSearchQuery("")} size="small">
                        <ClearOutlinedIcon fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ) : undefined,
                }}
                label="搜索OA内容"
                onChange={(event) => setOaSearchQuery(event.target.value)}
                placeholder="申请人、项目、金额、事由"
                size="small"
                sx={{ minWidth: { xs: "100%", lg: 280 } }}
                value={oaSearchQuery}
              />
            </Stack>
            {bucket === "unsubmitted" ? (
              <Button disabled={!canSubmit} onClick={handleSubmit} variant="contained">
                关联OA项与流水
              </Button>
            ) : (
              <Button disabled={!canWithdraw} onClick={() => setWithdrawOpen(true)} variant="contained">
                撤回关联
              </Button>
            )}
          </Stack>
          <Divider />
          <TableContainer>
            <Table aria-label={bucket === "unsubmitted" ? "可关联OA项" : "已关联OA项"} size="small">
              <TableHead>
                <TableRow>
                  {bucket === "unsubmitted" ? <TableCell padding="checkbox">选择</TableCell> : null}
                  <TableCell>申请人</TableCell>
                  <TableCell>项目名称</TableCell>
                  <TableCell align="right">金额</TableCell>
                  <TableCell>申请事由</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibleOaRows.map((row) => (
                  <TableRow hover key={row.id} selected={selectedOaRowIds.has(row.id)}>
                    {bucket === "unsubmitted" ? (
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={selectedOaRowIds.has(row.id)}
                          inputProps={{ "aria-label": `选择 ${row.applicant} ${row.applyTime}` }}
                          onChange={(event) => handleOaToggle(row, event.target.checked)}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell sx={{ minWidth: 140 }}>
                      <Stack spacing={0.5}>
                        <Typography fontWeight={800}>{row.applicant || "-"}</Typography>
                        <Chip label={row.applyTime || "-"} size="small" variant="outlined" />
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 340 }}>
                      <ExpandableText text={row.projectName} />
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      {formatMoney(row.amount)}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 360 }}>
                      <ExpandableText text={row.reason} />
                    </TableCell>
                  </TableRow>
                ))}
                {visibleOaRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={bucket === "unsubmitted" ? 5 : 4}>
                      <StatePanel compact tone="empty" title={bucket === "unsubmitted" ? "暂无可关联 OA" : "暂无已关联 OA"} />
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Box>

      <Dialog fullWidth maxWidth="sm" onClose={() => setWithdrawOpen(false)} open={withdrawOpen}>
        <DialogTitle>撤回关联</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label="撤回原因"
            minRows={3}
            multiline
            onChange={(event) => setWithdrawReason(event.target.value)}
            sx={{ mt: 1 }}
            value={withdrawReason}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWithdrawOpen(false)}>取消</Button>
          <Button disabled={!withdrawReason.trim() || mutating} onClick={handleConfirmWithdraw} variant="contained">
            确认撤回
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        autoHideDuration={4000}
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
