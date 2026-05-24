import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { PendingInvoiceRelationDetail } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRelationDrawerProps = {
  open: boolean;
  transactionId: string | null;
  loadDetail: (transactionId: string) => Promise<PendingInvoiceRelationDetail>;
  onOpenInvoicePicker: (transactionId: string) => void;
  onClose: () => void;
};

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value || "-";
}

export default function PendingInvoiceRelationDrawer({
  open,
  transactionId,
  loadDetail,
  onOpenInvoicePicker,
  onClose,
}: PendingInvoiceRelationDrawerProps) {
  const [detail, setDetail] = useState<PendingInvoiceRelationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !transactionId) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    loadDetail(transactionId)
      .then((payload) => {
        if (active) {
          setDetail(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "关系明细加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadDetail, open, transactionId]);

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title="关系与支付明细"
      subtitle={detail?.transactionSummary.counterpartyName ?? transactionId ?? undefined}
      closeLabel="关闭关系明细抽屉"
      onClose={onClose}
      footer={transactionId ? (
        <Button variant="contained" onClick={() => onOpenInvoicePicker(transactionId)}>
          选择已有发票
        </Button>
      ) : null}
    >
      {loading ? (
        <Stack direction="row" spacing={1.25} alignItems="center">
          <CircularProgress aria-label="正在加载关系明细" size={22} />
          <Typography variant="body2" color="text.secondary">正在加载关系明细</Typography>
        </Stack>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {detail ? (
        <>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(4, minmax(0, 1fr))" }, gap: 1.5 }}>
            <Metric label="已付合计" value={formatMoney(detail.paidTotal)} />
            <Metric label="发票合计" value={formatMoney(detail.invoiceTotal)} />
            <Metric label="待付金额" value={formatMoney(detail.remainingAmount)} />
            <Metric label="支付差额" value={formatMoney(detail.differenceAmount)} />
          </Box>
          <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
            <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>已关联发票</Typography>
            <Stack spacing={1}>
              {detail.relatedInvoices.length === 0 ? <Typography color="text.secondary">暂无关联发票。</Typography> : null}
              {detail.relatedInvoices.map((invoice) => (
                <Box key={invoice.id || invoice.digitalInvoiceNo}>
                  <Typography variant="body2" fontWeight={800}>{invoice.digitalInvoiceNo || invoice.invoiceNo || "-"}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {invoice.sellerName || "-"} · {formatMoney(invoice.totalWithTax)}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Paper>
          <Paper variant="outlined" sx={{ borderRadius: 1 }}>
            <Table size="small" aria-label="历史支付流水">
              <TableHead>
                <TableRow>
                  <TableCell>支付日期</TableCell>
                  <TableCell>对方</TableCell>
                  <TableCell align="right">金额</TableCell>
                  <TableCell>关系</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {detail.paymentRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4}>暂无历史支付。</TableCell>
                  </TableRow>
                ) : detail.paymentRows.map((row) => (
                  <TableRow key={row.id || row.relationCaseId}>
                    <TableCell>{row.tradeTime || "-"}</TableCell>
                    <TableCell>{row.counterpartyName || "-"}</TableCell>
                    <TableCell align="right">{formatMoney(row.debitAmount)}</TableCell>
                    <TableCell>{row.relationCaseId || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ borderRadius: 1, p: 1.25 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={800}>{label}</Typography>
      <Typography variant="body1" fontWeight={900} sx={{ fontVariantNumeric: "tabular-nums" }}>{value}</Typography>
    </Paper>
  );
}
