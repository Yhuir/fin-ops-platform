import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { OutputInvoiceReceiptHistoryResponse } from "../../features/outputInvoiceCollections/types";

type ReceiptHistoryDrawerProps = {
  open: boolean;
  invoiceId: string | null;
  loadHistory: (invoiceId: string) => Promise<OutputInvoiceReceiptHistoryResponse>;
  onVoidReceipt: (receiptId: string) => Promise<void>;
  onReissueReceipt: (receiptId: string) => Promise<void>;
  onChanged?: () => void;
  onClose: () => void;
};

export default function ReceiptHistoryDrawer({
  open,
  invoiceId,
  loadHistory,
  onVoidReceipt,
  onReissueReceipt,
  onChanged,
  onClose,
}: ReceiptHistoryDrawerProps) {
  const [payload, setPayload] = useState<OutputInvoiceReceiptHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState("");

  useEffect(() => {
    if (!open || !invoiceId) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadHistory(invoiceId)
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收据历史加载失败");
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
  }, [invoiceId, loadHistory, open]);

  const reload = async () => {
    if (!invoiceId) {
      return;
    }
    setPayload(await loadHistory(invoiceId));
  };

  const handleVoid = async (receiptId: string) => {
    setSubmittingId(receiptId);
    setError(null);
    try {
      await onVoidReceipt(receiptId);
      await reload();
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "作废收据失败");
    } finally {
      setSubmittingId("");
    }
  };

  const handleReissue = async (receiptId: string) => {
    setSubmittingId(receiptId);
    setError(null);
    try {
      await onReissueReceipt(receiptId);
      await reload();
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重开收据失败");
    } finally {
      setSubmittingId("");
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "已出收据历史" : undefined,
        sx: { width: { xs: "100%", sm: 640 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>已出收据历史</Typography>
            {invoiceId ? <Typography variant="caption" color="text.secondary">{invoiceId}</Typography> : null}
          </Box>
          <IconButton aria-label="关闭已出收据历史" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载已出收据历史" size={22} />
              <Typography variant="body2" color="text.secondary">正在读取历史</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {payload && !payload.sourceAvailable ? (
            <Alert severity="info">{payload.message || "暂无系统内历史收据事实。"}</Alert>
          ) : null}
          {payload?.sourceAvailable && payload.receipts.length === 0 ? (
            <Alert severity="info">暂无已出收据。</Alert>
          ) : null}
          {payload?.receipts.map((receipt) => (
            <Paper key={receipt.id || receipt.receiptNo} variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
              <Typography variant="subtitle2" fontWeight={900}>{receipt.receiptNo || receipt.id}</Typography>
              <Typography variant="body2" color="text.secondary">
                {receipt.createdAt || "日期为空"} / {receipt.amount || "金额为空"} / {receipt.status || "状态为空"}
              </Typography>
              {receipt.voidedAt || receipt.voidReason ? (
                <Typography variant="caption" color="text.secondary">
                  作废：{receipt.voidedAt || "时间为空"} {receipt.voidReason || ""}
                </Typography>
              ) : null}
              <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1 }}>
                {receipt.status === "issued" && receipt.id ? (
                  <Button
                    size="small"
                    variant="outlined"
                    color="warning"
                    disabled={submittingId === receipt.id}
                    onClick={() => handleVoid(receipt.id || "")}
                  >
                    作废收据 {receipt.receiptNo || receipt.id}
                  </Button>
                ) : null}
                {receipt.status === "voided" && receipt.id ? (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={submittingId === receipt.id}
                    onClick={() => handleReissue(receipt.id || "")}
                  >
                    重开收据 {receipt.receiptNo || receipt.id}
                  </Button>
                ) : null}
              </Stack>
            </Paper>
          ))}
        </Stack>
      </Stack>
    </Drawer>
  );
}
