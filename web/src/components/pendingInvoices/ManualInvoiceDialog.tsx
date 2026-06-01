import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  confirmManualPendingInvoice,
  previewManualPendingInvoice,
} from "../../features/pendingInvoices/api";
import type {
  ManualPendingInvoicePreview,
  ManualPendingInvoiceResult,
  PendingInvoiceDirection,
  PendingInvoiceRow,
} from "../../features/pendingInvoices/types";

type ManualInvoiceDialogProps = {
  open: boolean;
  direction: PendingInvoiceDirection;
  row: PendingInvoiceRow | null;
  onClose: () => void;
  onConfirmed: (result: ManualPendingInvoiceResult) => void;
};

type FormState = {
  invoiceNo: string;
  digitalInvoiceNo: string;
  invoiceCode: string;
  issueDate: string;
  totalWithTax: string;
  taxAmount: string;
  taxRate: string;
  sellerName: string;
  sellerTaxNo: string;
  buyerName: string;
  buyerTaxNo: string;
  remark: string;
};

const emptyForm: FormState = {
  invoiceNo: "",
  digitalInvoiceNo: "",
  invoiceCode: "",
  issueDate: "",
  totalWithTax: "",
  taxAmount: "",
  taxRate: "",
  sellerName: "",
  sellerTaxNo: "",
  buyerName: "",
  buyerTaxNo: "",
  remark: "",
};

function createRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ManualInvoiceDialog({
  open,
  direction,
  row,
  onClose,
  onConfirmed,
}: ManualInvoiceDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [requestId, setRequestId] = useState(createRequestId);
  const [preview, setPreview] = useState<ManualPendingInvoicePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const targetLabel = direction === "expense" ? "进项发票" : "销项发票";

  useEffect(() => {
    if (open) {
      setRequestId(createRequestId());
    }
  }, [open, row?.id]);

  const canPreview = useMemo(() => {
    const hasInvoiceNumber = form.invoiceNo.trim() || form.digitalInvoiceNo.trim();
    const hasParty = direction === "expense" ? form.sellerName.trim() : form.buyerName.trim();
    return Boolean(row && hasInvoiceNumber && form.issueDate.trim() && form.totalWithTax.trim() && hasParty);
  }, [direction, form, row]);

  const updateField = (key: keyof FormState) => (event: ChangeEvent<HTMLInputElement>) => {
    setForm((current) => ({ ...current, [key]: event.target.value }));
    setPreview(null);
  };

  const buildRequest = (previewId?: string) => ({
    previewId,
    requestId,
    bankTransactionId: row?.bankTransaction.id ?? "",
    invoiceNo: form.invoiceNo.trim() || undefined,
    digitalInvoiceNo: form.digitalInvoiceNo.trim() || undefined,
    invoiceCode: form.invoiceCode.trim() || undefined,
    issueDate: form.issueDate.trim(),
    totalWithTax: form.totalWithTax.trim(),
    taxAmount: form.taxAmount.trim() || undefined,
    taxRate: form.taxRate.trim() || undefined,
    sellerName: form.sellerName.trim(),
    sellerTaxNo: form.sellerTaxNo.trim() || undefined,
    buyerName: form.buyerName.trim(),
    buyerTaxNo: form.buyerTaxNo.trim() || undefined,
    remark: form.remark.trim() || undefined,
  });

  async function handlePreview() {
    if (!row || !canPreview || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewManualPendingInvoice(buildRequest()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "预览失败。");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!row || !preview || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await confirmManualPendingInvoice(buildRequest(preview.previewId));
      onConfirmed(result);
      setForm(emptyForm);
      setPreview(null);
      setRequestId(createRequestId());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "写入失败。");
    } finally {
      setBusy(false);
    }
  }

  function handleClose() {
    if (busy) {
      return;
    }
    setForm(emptyForm);
    setPreview(null);
    setError(null);
    setRequestId(createRequestId());
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth aria-labelledby="manual-invoice-dialog-title">
      <DialogTitle id="manual-invoice-dialog-title">手工补录发票</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography color="text.secondary" variant="body2">
            {row ? `${row.bankTransaction.counterpartyName} · ${targetLabel}` : targetLabel}
          </Typography>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField label="发票号码" size="small" value={form.invoiceNo} onChange={updateField("invoiceNo")} fullWidth />
            <TextField label="数电发票号码" size="small" value={form.digitalInvoiceNo} onChange={updateField("digitalInvoiceNo")} fullWidth />
            <TextField label="发票代码" size="small" value={form.invoiceCode} onChange={updateField("invoiceCode")} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField label="开票日期" size="small" value={form.issueDate} onChange={updateField("issueDate")} placeholder="YYYY-MM-DD" fullWidth />
            <TextField label="价税合计" size="small" value={form.totalWithTax} onChange={updateField("totalWithTax")} fullWidth />
            <TextField label="税额" size="small" value={form.taxAmount} onChange={updateField("taxAmount")} fullWidth />
            <TextField label="税率" size="small" value={form.taxRate} onChange={updateField("taxRate")} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField label="销方名称" size="small" value={form.sellerName} onChange={updateField("sellerName")} fullWidth />
            <TextField label="销方税号" size="small" value={form.sellerTaxNo} onChange={updateField("sellerTaxNo")} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField label="购方名称" size="small" value={form.buyerName} onChange={updateField("buyerName")} fullWidth />
            <TextField label="购方税号" size="small" value={form.buyerTaxNo} onChange={updateField("buyerTaxNo")} fullWidth />
          </Stack>
          <TextField label="备注" size="small" value={form.remark} onChange={updateField("remark")} multiline minRows={2} fullWidth />
          {preview ? (
            <Alert severity={preview.canConfirm ? "info" : "warning"}>
              <Stack spacing={0.5}>
                <Typography variant="body2">预览键：{preview.requestKey}</Typography>
                <Typography variant="body2">重复检查：{preview.duplicateCheck.message || preview.duplicateCheck.status}</Typography>
                <Typography variant="body2">影响月份：{preview.affectedMonths.join("、") || "—"}</Typography>
              </Stack>
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy}>取消</Button>
        <Button onClick={handlePreview} disabled={!canPreview || busy} variant="outlined">预览</Button>
        <Button onClick={handleConfirm} disabled={!preview?.canConfirm || busy} variant="contained">确认写入</Button>
      </DialogActions>
    </Dialog>
  );
}
