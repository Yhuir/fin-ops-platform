import { useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from "react";

import AppDialog from "../common/AppDialog";
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

  const updateField = (key: keyof FormState) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
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
    <AppDialog
      actions={(
        <>
          <button className="pending-invoices-button" disabled={busy} onClick={handleClose} type="button">取消</button>
          <button className="pending-invoices-button" disabled={!canPreview || busy} onClick={handlePreview} type="button">预览</button>
          <button
            className="pending-invoices-button pending-invoices-button--primary"
            disabled={!preview?.canConfirm || busy}
            onClick={handleConfirm}
            type="button"
          >
            确认写入
          </button>
        </>
      )}
      maxWidth="md"
      onClose={handleClose}
      open={open}
      title="手工补录发票"
    >
      <div className="pending-invoice-manual-dialog">
        <p className="pending-invoice-panel__description">
          {row ? `${row.bankTransaction.counterpartyName} · ${targetLabel}` : targetLabel}
        </p>
        {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
        <div className="pending-invoice-manual-grid pending-invoice-manual-grid--three">
          <Field label="发票号码" value={form.invoiceNo} onChange={updateField("invoiceNo")} />
          <Field label="数电发票号码" value={form.digitalInvoiceNo} onChange={updateField("digitalInvoiceNo")} />
          <Field label="发票代码" value={form.invoiceCode} onChange={updateField("invoiceCode")} />
        </div>
        <div className="pending-invoice-manual-grid pending-invoice-manual-grid--four">
          <Field label="开票日期" value={form.issueDate} onChange={updateField("issueDate")} />
          <Field label="价税合计" value={form.totalWithTax} onChange={updateField("totalWithTax")} />
          <Field label="税额" value={form.taxAmount} onChange={updateField("taxAmount")} />
          <Field label="税率" value={form.taxRate} onChange={updateField("taxRate")} />
        </div>
        <div className="pending-invoice-manual-grid pending-invoice-manual-grid--two">
          <Field label="销方名称" value={form.sellerName} onChange={updateField("sellerName")} />
          <Field label="销方税号" value={form.sellerTaxNo} onChange={updateField("sellerTaxNo")} />
        </div>
        <div className="pending-invoice-manual-grid pending-invoice-manual-grid--two">
          <Field label="购方名称" value={form.buyerName} onChange={updateField("buyerName")} />
          <Field label="购方税号" value={form.buyerTaxNo} onChange={updateField("buyerTaxNo")} />
        </div>
        <Field label="备注" multiline value={form.remark} onChange={updateField("remark")} />
        {preview ? (
          <StatusMessage tone={preview.canConfirm ? "info" : "warning"}>
            <span>预览键：{preview.requestKey}</span>
            <span>重复检查：{preview.duplicateCheck.message || preview.duplicateCheck.status}</span>
            <span>影响月份：{preview.affectedMonths.join("、") || "—"}</span>
          </StatusMessage>
        ) : null}
      </div>
    </AppDialog>
  );
}

function Field({
  label,
  multiline = false,
  value,
  onChange,
}: {
  label: string;
  multiline?: boolean;
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}) {
  return (
    <label className="pending-invoice-form-field">
      <span>{label}</span>
      {multiline ? (
        <textarea rows={2} value={value} onChange={onChange} />
      ) : (
        <input value={value} onChange={onChange} />
      )}
    </label>
  );
}

function StatusMessage({ children, tone }: { children: ReactNode; tone: "danger" | "success" | "info" | "warning" }) {
  return (
    <div className={`pending-invoice-status-message pending-invoice-status-message--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </div>
  );
}
