import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AttachExistingInvoicePreview,
  AttachExistingInvoiceResult,
  FetchPendingInvoiceCandidatesRequest,
  PendingInvoiceCandidate,
  PendingInvoiceCandidatesResponse,
} from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceInvoicePickerDrawerProps = {
  open: boolean;
  transactionId: string | null;
  loadCandidates: (request: FetchPendingInvoiceCandidatesRequest) => Promise<PendingInvoiceCandidatesResponse>;
  previewAttach: (transactionId: string, invoiceId: string, requestId: string) => Promise<AttachExistingInvoicePreview>;
  confirmAttach: (transactionId: string, invoiceId: string, previewId: string, requestId: string) => Promise<AttachExistingInvoiceResult>;
  onConfirmed: (result: AttachExistingInvoiceResult) => void;
  onClose: () => void;
};

function createRequestId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value || "-";
}

function invoiceNumber(candidate: PendingInvoiceCandidate) {
  return candidate.digitalInvoiceNo || candidate.invoiceNo || candidate.invoiceId || "-";
}

function candidateStatusLabel(status: PendingInvoiceCandidate["candidateStatus"]) {
  const labels: Record<string, string> = {
    available: "可关联",
    already_related: "已关联本流水",
    conflict: "存在冲突",
  };
  return labels[status] ?? status;
}

export default function PendingInvoiceInvoicePickerDrawer({
  open,
  transactionId,
  loadCandidates,
  previewAttach,
  confirmAttach,
  onConfirmed,
  onClose,
}: PendingInvoiceInvoicePickerDrawerProps) {
  const [payload, setPayload] = useState<PendingInvoiceCandidatesResponse | null>(null);
  const [selected, setSelected] = useState<PendingInvoiceCandidate | null>(null);
  const [preview, setPreview] = useState<AttachExistingInvoicePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [issueDateFrom, setIssueDateFrom] = useState("");
  const [issueDateTo, setIssueDateTo] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const confirmRequestId = useMemo(() => createRequestId("attach-confirm"), [preview?.previewId]);

  const reloadCandidates = useCallback((guard: { active: boolean } = { active: true }) => {
    if (!transactionId) {
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    setPreview(null);
    loadCandidates({
      transactionId,
      keyword,
      sellerName,
      issueDateFrom,
      issueDateTo,
      amountMin,
      amountMax,
      sortField: "amount_difference_abs",
      sortDirection: "asc",
      page,
      pageSize,
    })
      .then((nextPayload) => {
        if (guard.active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (guard.active) {
          setError(reason instanceof Error ? reason.message : "候选发票加载失败");
        }
      })
      .finally(() => {
        if (guard.active) {
          setLoading(false);
        }
      });
  }, [amountMax, amountMin, issueDateFrom, issueDateTo, keyword, loadCandidates, page, pageSize, sellerName, transactionId]);

  useEffect(() => {
    if (!open || !transactionId) {
      setPayload(null);
      setSelected(null);
      setPreview(null);
      setLoading(false);
      setBusy(false);
      setError(null);
      setPage(1);
      return undefined;
    }
    const guard = { active: true };
    reloadCandidates(guard);
    return () => {
      guard.active = false;
    };
  }, [open, reloadCandidates, transactionId]);

  async function handlePreview(candidate: PendingInvoiceCandidate) {
    if (!transactionId || busy) {
      return;
    }
    setSelected(candidate);
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewAttach(transactionId, candidate.invoiceId, createRequestId("attach-preview")));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联预览失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!transactionId || !selected || !preview || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await confirmAttach(transactionId, selected.invoiceId, preview.previewId, confirmRequestId);
      onConfirmed(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关系确认失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title="选择已有进项发票"
      subtitle={transactionId ?? undefined}
      closeLabel="关闭发票选择抽屉"
      width={820}
      onClose={onClose}
      footer={(
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button onClick={onClose} disabled={busy}>关闭</Button>
          <Button variant="contained" onClick={handleConfirm} disabled={!preview?.canConfirm || busy}>
            确认建立关系
          </Button>
        </Stack>
      )}
    >
      {loading ? (
        <Stack direction="row" spacing={1.25} alignItems="center">
          <CircularProgress aria-label="正在加载发票候选" size={22} />
          <Typography variant="body2" color="text.secondary">正在加载发票候选</Typography>
        </Stack>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {preview ? (
        <Alert severity={preview.canConfirm ? "info" : "warning"}>
          <Stack spacing={0.5}>
            <Typography variant="body2">{preview.requestKey}</Typography>
            <Typography variant="body2">关联后待付 {formatMoney(preview.paymentImpact.remainingAmountAfter)}</Typography>
          </Stack>
        </Alert>
      ) : null}
      <Paper variant="outlined" sx={{ borderRadius: 1, p: 1.5 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} useFlexGap flexWrap="wrap">
          <TextField size="small" label="关键词" value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} />
          <TextField size="small" label="销方" value={sellerName} onChange={(event) => { setSellerName(event.target.value); setPage(1); }} />
          <TextField size="small" label="开票开始" type="date" value={issueDateFrom} onChange={(event) => { setIssueDateFrom(event.target.value); setPage(1); }} InputLabelProps={{ shrink: true }} />
          <TextField size="small" label="开票结束" type="date" value={issueDateTo} onChange={(event) => { setIssueDateTo(event.target.value); setPage(1); }} InputLabelProps={{ shrink: true }} />
          <TextField size="small" label="最小金额" value={amountMin} onChange={(event) => { setAmountMin(event.target.value); setPage(1); }} inputProps={{ inputMode: "decimal" }} />
          <TextField size="small" label="最大金额" value={amountMax} onChange={(event) => { setAmountMax(event.target.value); setPage(1); }} inputProps={{ inputMode: "decimal" }} />
          <Button variant="outlined" onClick={() => reloadCandidates()} disabled={loading || busy}>搜索</Button>
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ borderRadius: 1 }}>
        <Table size="small" aria-label="发票候选">
          <TableHead>
            <TableRow>
              <TableCell>发票号码</TableCell>
              <TableCell>销方</TableCell>
              <TableCell align="right">价税合计</TableCell>
              <TableCell align="right">待支付</TableCell>
              <TableCell>状态</TableCell>
              <TableCell align="right">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {payload?.rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>暂无候选发票。</TableCell>
              </TableRow>
            ) : null}
            {payload?.rows.map((candidate) => (
              <TableRow key={candidate.invoiceId || candidate.id}>
                <TableCell>
                  <Typography variant="body2" fontWeight={900}>{invoiceNumber(candidate)}</Typography>
                  <Typography variant="caption" color="text.secondary">{candidate.issueDate || "-"}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{candidate.sellerName || "-"}</Typography>
                  <Typography variant="caption" color="text.secondary">{candidate.sellerTaxNo || "-"}</Typography>
                </TableCell>
                <TableCell align="right">{formatMoney(candidate.totalWithTax)}</TableCell>
                <TableCell align="right">{formatMoney(candidate.remainingAmount)}</TableCell>
                <TableCell>
                  <Stack spacing={0.25} alignItems="flex-start">
                    <Chip
                      size="small"
                      label={candidateStatusLabel(candidate.candidateStatus)}
                      color={candidate.candidateStatus === "available" ? "success" : candidate.candidateStatus === "conflict" ? "warning" : "default"}
                      variant="outlined"
                    />
                    {candidate.conflictReason ? <Typography variant="caption" color="text.secondary">{candidate.conflictReason}</Typography> : null}
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={candidate.candidateStatus !== "available" || busy}
                    onClick={() => handlePreview(candidate)}
                    aria-label={`预览关联 ${invoiceNumber(candidate)}`}
                  >
                    预览关联
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={payload?.pagination.total ?? 0}
          page={Math.max(0, (payload?.pagination.page ?? page) - 1)}
          rowsPerPage={payload?.pagination.pageSize ?? pageSize}
          rowsPerPageOptions={[10, 20, 50]}
          labelRowsPerPage="每页发票"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
          onPageChange={(_event, nextPage) => setPage(nextPage + 1)}
          onRowsPerPageChange={(event) => {
            setPageSize(Number(event.target.value));
            setPage(1);
          }}
        />
      </Paper>
    </PendingInvoiceDrawerFrame>
  );
}
