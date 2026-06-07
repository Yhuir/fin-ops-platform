import { useEffect, useMemo, useState, type ReactNode } from "react";

import type {
  OutputInvoiceCollectionRow,
  OutputInvoiceReceiptPreviewRequest,
  OutputInvoiceReceiptPreviewResponse,
} from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

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
      .catch((loadReason: unknown) => {
        if (active) {
          setError(loadReason instanceof Error ? loadReason.message : "收据预览加载失败");
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
    } catch (createReason) {
      setError(createReason instanceof Error ? createReason.message : "正式收据创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭待出收据预览"
      open={open}
      subtitle={row ? row.invoice.displayNo || row.invoice.invoiceNo : undefined}
      title="待出收据预览"
      width={720}
      onClose={onClose}
    >
      <div className="output-invoice-collection-drawer__body">
        {loading ? (
          <div aria-label="正在加载待出收据预览">
            <StatePanel compact tone="loading" title="正在生成预览" />
          </div>
        ) : null}
        {error ? (
          <StatePanel compact tone="error">
            {error}
          </StatePanel>
        ) : null}
        {payload && !payload.canPreview ? (
          <StatePanel compact tone={payload.reasonCode === "bank_selection_required" ? "warning" : "info"}>
            {payload.reason || "当前记录不能生成收据预览。"}
            {payload.pendingAmount ? ` 待收款金额：${payload.pendingAmount}` : ""}
          </StatePanel>
        ) : null}
        {payload?.reasonCode === "bank_selection_required" && candidates.length > 0 ? (
          <fieldset className="output-invoice-collection-candidate-list">
            <legend>选择本次收据对应收入流水</legend>
            <div className="output-invoice-collection-candidate-list__scroll">
              {candidates.map((candidate) => {
                const candidateLabel = `${candidate.tradeTime || "日期为空"} / ${candidate.amount} / ${
                  candidate.bankName || "银行为空"
                } / ${candidate.summary || candidate.counterpartyName}`;
                return (
                  <label className="output-invoice-collection-candidate-list__option" key={candidate.bankTransactionId}>
                    <input
                      checked={selectedBankTransactionId === candidate.bankTransactionId}
                      name="receipt-bank-transaction"
                      type="radio"
                      value={candidate.bankTransactionId}
                      onChange={(event) => setSelectedBankTransactionId(event.target.value)}
                    />
                    <span>{candidateLabel}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ) : null}
        {payload?.canPreview && payload.receipt ? (
          <article className="output-invoice-collection-receipt-card">
            <header className="output-invoice-collection-receipt-card__header">
              <strong>{payload.receipt.companyName}</strong>
              <span className="output-invoice-collections-table-tag">{payload.receipt.templateVersion}</span>
            </header>
            <h3 className="output-invoice-collection-receipt-card__title">{payload.receipt.title}</h3>
            <p className="output-invoice-collection-receipt-card__date">
              {payload.receipt.dateParts.year} 年 {payload.receipt.dateParts.month} 月 {payload.receipt.dateParts.day} 日
            </p>
            <p className="output-invoice-collection-receipt-card__payer">
              兹收到 {payload.receipt.payerName || "付款方为空"} 交来下列款项
            </p>
            <div className="output-invoice-collection-receipt-grid">
              <Cell strong>摘要</Cell>
              <Cell strong>金额</Cell>
              <Cell strong>备注</Cell>
              <Cell>{payload.receipt.summary}</Cell>
              <Cell>{payload.receipt.amount}</Cell>
              <Cell>{payload.receipt.remark}</Cell>
            </div>
            <div className="output-invoice-collection-receipt-card__totals">
              <strong>合计人民币大写：{payload.receipt.amountUppercase}</strong>
              <strong>小写：{payload.receipt.amount}</strong>
            </div>
            <p className="output-invoice-collection-receipt-card__note">正式创建后会分配收据编号并写入收据历史。</p>
            <div className="output-invoice-collection-drawer__footer-actions">
              <button
                className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--primary"
                disabled={submitting || !createReceipt || !payload.receipt.bankTransactionId}
                type="button"
                onClick={handleCreate}
              >
                创建正式收据
              </button>
            </div>
          </article>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function Cell({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return (
    <div
      className={`output-invoice-collection-receipt-grid__cell${
        strong ? " output-invoice-collection-receipt-grid__cell--strong" : ""
      }`}
    >
      {children}
    </div>
  );
}
