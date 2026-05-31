import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type {
  OutputInvoiceCollectionRow,
  OutputInvoiceReceiptPreviewRequest,
  OutputInvoiceReceiptPreviewResponse,
} from "../../features/outputInvoiceCollections/types";

type ReceiptPreviewDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  loadPreview: (request: OutputInvoiceReceiptPreviewRequest) => Promise<OutputInvoiceReceiptPreviewResponse>;
  createReceipt?: (rowId: string, bankTransactionId: string) => Promise<void>;
  onChanged?: () => void;
  onClose: () => void;
};

export default function ReceiptPreviewDrawer({
  open,
  row,
  loadPreview,
  createReceipt,
  onChanged,
  onClose,
}: ReceiptPreviewDrawerProps) {
  const [payload, setPayload] = useState<OutputInvoiceReceiptPreviewResponse | null>(null);
  const [selectedBankTransactionId, setSelectedBankTransactionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rowId = row?.id ?? "";

  useEffect(() => {
    if (!open || !rowId) {
      setPayload(null);
      setSelectedBankTransactionId("");
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadPreview({ rowId, selectedBankTransactionId: selectedBankTransactionId || undefined })
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收据预览加载失败");
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
  }, [loadPreview, open, rowId, selectedBankTransactionId]);

  const candidates = useMemo(() => payload?.candidates ?? [], [payload]);
  const handleCreate = async () => {
    const bankTransactionId = payload?.receipt?.bankTransactionId || selectedBankTransactionId;
    if (!rowId || !bankTransactionId || !createReceipt) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createReceipt(rowId, bankTransactionId);
      onChanged?.();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "正式收据创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "待出收据预览" : undefined,
        sx: { width: { xs: "100%", sm: 720 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>待出收据</Typography>
            {row ? <Typography variant="caption" color="text.secondary">{row.invoice.displayNo || row.invoice.invoiceNo}</Typography> : null}
          </Box>
          <IconButton aria-label="关闭待出收据预览" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载待出收据预览" size={22} />
              <Typography variant="body2" color="text.secondary">正在生成预览</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {payload && !payload.canPreview ? (
            <Alert severity={payload.reasonCode === "bank_selection_required" ? "warning" : "info"}>
              {payload.reason || "当前记录不能生成收据预览。"}
              {payload.pendingAmount ? ` 待收款金额：${payload.pendingAmount}` : ""}
            </Alert>
          ) : null}
          {payload?.reasonCode === "bank_selection_required" && candidates.length > 0 ? (
            <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
              <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>
                选择本次收据对应收入流水
              </Typography>
              <FormControl>
                <RadioGroup
                  value={selectedBankTransactionId}
                  onChange={(event) => setSelectedBankTransactionId(event.target.value)}
                >
                  {candidates.map((candidate) => (
                    <FormControlLabel
                      key={candidate.bankTransactionId}
                      value={candidate.bankTransactionId}
                      control={<Radio />}
                      label={`${candidate.tradeTime || "日期为空"} / ${candidate.amount} / ${candidate.bankName || "银行为空"} / ${candidate.summary || candidate.counterpartyName}`}
                    />
                  ))}
                </RadioGroup>
              </FormControl>
            </Paper>
          ) : null}
          {payload?.canPreview && payload.receipt ? (
            <Paper variant="outlined" sx={{ borderRadius: 1, p: 2.5 }}>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" fontWeight={900}>{payload.receipt.companyName}</Typography>
                  <Chip label={payload.receipt.templateVersion} size="small" variant="outlined" />
                </Stack>
                <Typography align="center" component="h3" variant="h5" fontWeight={900} letterSpacing={0}>
                  {payload.receipt.title}
                </Typography>
                <Typography align="right" variant="body2">
                  {payload.receipt.dateParts.year} 年 {payload.receipt.dateParts.month} 月 {payload.receipt.dateParts.day} 日
                </Typography>
                <Typography variant="body1">
                  兹收到 {payload.receipt.payerName || "付款方为空"} 交来下列款项
                </Typography>
                <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, overflow: "hidden" }}>
                  <Box sx={{ display: "grid", gridTemplateColumns: "1fr 140px 1fr", bgcolor: "grey.50" }}>
                    <Cell strong>摘要</Cell>
                    <Cell strong>金额</Cell>
                    <Cell strong>备注</Cell>
                  </Box>
                  <Box sx={{ display: "grid", gridTemplateColumns: "1fr 140px 1fr" }}>
                    <Cell>{payload.receipt.summary}</Cell>
                    <Cell>{payload.receipt.amount}</Cell>
                    <Cell>{payload.receipt.remark}</Cell>
                  </Box>
                </Box>
                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                  <Typography variant="body2" fontWeight={900}>合计人民币大写：{payload.receipt.amountUppercase}</Typography>
                  <Typography variant="body2" fontWeight={900}>小写：{payload.receipt.amount}</Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  正式创建后会分配收据编号并写入收据历史。
                </Typography>
                <Stack direction="row" justifyContent="flex-end">
                  <Button
                    variant="contained"
                    disabled={submitting || !createReceipt || !payload.receipt.bankTransactionId}
                    onClick={handleCreate}
                  >
                    创建正式收据
                  </Button>
                </Stack>
              </Stack>
            </Paper>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}

function Cell({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return (
    <Box sx={{ p: 1, minHeight: 40, borderRight: "1px solid", borderColor: "divider", wordBreak: "break-word" }}>
      <Typography variant="body2" fontWeight={strong ? 900 : 500}>{children}</Typography>
    </Box>
  );
}
