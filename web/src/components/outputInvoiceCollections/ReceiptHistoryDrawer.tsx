import { useEffect, useState } from "react";

import type { OutputInvoiceReceiptHistoryResponse } from "../../features/outputInvoiceCollections/types";
import AppDialog from "../common/AppDialog";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

type ReceiptHistoryDrawerProps = {
  open: boolean;
  invoiceId: string | null;
  canMutateData: boolean;
  loadHistory: (invoiceId: string) => Promise<OutputInvoiceReceiptHistoryResponse>;
  onVoidReceipt: (receiptId: string, reason: string) => Promise<void>;
  onReissueReceipt: (receiptId: string, reason: string) => Promise<void>;
  onChanged?: () => Promise<void> | void;
  onClose: () => void;
};

export default function ReceiptHistoryDrawer({
  open,
  invoiceId,
  canMutateData,
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
  const [pendingAction, setPendingAction] = useState<{
    kind: "void" | "reissue";
    receiptId: string;
    receiptNo: string;
  } | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!open || !invoiceId) {
      setPayload(null);
      setLoading(false);
      setError(null);
      setPendingAction(null);
      setReason("");
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
      .catch((loadReason: unknown) => {
        if (active) {
          setError(loadReason instanceof Error ? loadReason.message : "收据历史加载失败");
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

  const handleVoid = async (receiptId: string, actionReason: string) => {
    setSubmittingId(receiptId);
    setError(null);
    try {
      await onVoidReceipt(receiptId, actionReason);
      await reload();
      await onChanged?.();
      return true;
    } catch (voidReason) {
      setError(voidReason instanceof Error ? voidReason.message : "作废收据失败");
      return false;
    } finally {
      setSubmittingId("");
    }
  };

  const handleReissue = async (receiptId: string, actionReason: string) => {
    setSubmittingId(receiptId);
    setError(null);
    try {
      await onReissueReceipt(receiptId, actionReason);
      await reload();
      await onChanged?.();
      return true;
    } catch (reissueReason) {
      setError(reissueReason instanceof Error ? reissueReason.message : "重开收据失败");
      return false;
    } finally {
      setSubmittingId("");
    }
  };

  const openActionDialog = (kind: "void" | "reissue", receiptId: string, receiptNo: string) => {
    setPendingAction({ kind, receiptId, receiptNo });
    setReason("");
    setError(null);
  };

  const closeActionDialog = () => {
    if (submittingId) {
      return;
    }
    setPendingAction(null);
    setReason("");
  };

  const handleConfirmAction = async () => {
    if (!pendingAction) {
      return;
    }
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setError("请填写收据处理原因");
      return;
    }
    const succeeded = pendingAction.kind === "void"
      ? await handleVoid(pendingAction.receiptId, trimmedReason)
      : await handleReissue(pendingAction.receiptId, trimmedReason);
    if (!succeeded) {
      return;
    }
    setPendingAction(null);
    setReason("");
  };

  const dialogTitle = pendingAction?.kind === "void" ? "作废收据原因" : "重开收据原因";
  const reasonLabel = pendingAction?.kind === "void" ? "作废原因" : "重开原因";

  return (
    <>
      <AppDrawer
        className="output-invoice-collection-drawer"
        closeLabel="关闭已出收据历史"
        open={open}
        subtitle={invoiceId || undefined}
        title="已出收据历史"
        width={640}
        onClose={onClose}
      >
        <div className="output-invoice-collection-drawer__body">
          {loading ? (
            <div aria-label="正在加载已出收据历史">
              <StatePanel compact tone="loading" title="正在读取历史" />
            </div>
          ) : null}
          {error ? (
            <StatePanel compact tone="error">
              {error}
            </StatePanel>
          ) : null}
          {payload && !payload.sourceAvailable ? (
            <StatePanel compact tone="info">
              {payload.message || "暂无系统内历史收据事实。"}
            </StatePanel>
          ) : null}
          {payload?.sourceAvailable && payload.receipts.length === 0 ? (
            <StatePanel compact tone="info">
              暂无已出收据。
            </StatePanel>
          ) : null}
          <div className="output-invoice-collection-receipt-history-list">
            {payload?.receipts.map((receipt) => {
              const receiptIdentity = receipt.receiptNo || receipt.id || "";
              return (
                <article className="output-invoice-collection-receipt-history-card" key={receipt.id || receipt.receiptNo}>
                  <div className="output-invoice-collection-receipt-history-card__main">
                    <h3>{receiptIdentity}</h3>
                    <p>
                      {receipt.createdAt || "日期为空"} / {receipt.amount || "金额为空"} / {receipt.status || "状态为空"}
                    </p>
                    {receipt.voidedAt || receipt.voidReason ? (
                      <p className="output-invoice-collection-receipt-history-card__voided">
                        作废：{receipt.voidedAt || "时间为空"} {receipt.voidReason || ""}
                      </p>
                    ) : null}
                  </div>
                  <div className="output-invoice-collection-receipt-history-card__actions">
                    {canMutateData && receipt.status === "issued" && receipt.id ? (
                      <button
                        className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--warning"
                        disabled={submittingId === receipt.id}
                        type="button"
                        onClick={() => openActionDialog("void", receipt.id || "", receiptIdentity)}
                      >
                        作废收据 {receiptIdentity}
                      </button>
                    ) : null}
                    {canMutateData && receipt.status === "voided" && receipt.id ? (
                      <button
                        className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--primary"
                        disabled={submittingId === receipt.id}
                        type="button"
                        onClick={() => openActionDialog("reissue", receipt.id || "", receiptIdentity)}
                      >
                        重开收据 {receiptIdentity}
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </AppDrawer>

      <AppDialog
        description={pendingAction?.receiptNo || undefined}
        maxWidth="sm"
        open={Boolean(pendingAction)}
        title={dialogTitle}
        onClose={closeActionDialog}
        actions={
          <>
            <button
              className="output-invoice-collection-drawer__button"
              disabled={Boolean(submittingId)}
              type="button"
              onClick={closeActionDialog}
            >
              取消
            </button>
            <button
              className={`output-invoice-collection-drawer__button ${
                pendingAction?.kind === "void"
                  ? "output-invoice-collection-drawer__button--warning"
                  : "output-invoice-collection-drawer__button--primary"
              }`}
              disabled={Boolean(submittingId) || !reason.trim()}
              type="button"
              onClick={handleConfirmAction}
            >
              {pendingAction?.kind === "void" ? "确认作废" : "确认重开"}
            </button>
          </>
        }
      >
        <label className="output-invoice-collection-drawer__field">
          <span>{reasonLabel}</span>
          <input autoFocus type="text" value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      </AppDialog>
    </>
  );
}
