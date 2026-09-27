import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import { useEffect, useState } from "react";

import type {
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
} from "../../features/pendingInvoices/types";
import { preparePublicDetailSections } from "../common/EntityDetailContent";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceDetailDrawerProps = {
  open: boolean;
  target: PendingInvoiceObjectDetailTarget | null;
  loadDetail: (target: PendingInvoiceObjectDetailTarget) => Promise<PendingInvoiceObjectDetail>;
  onClose: () => void;
  onBankSplitSaved?: () => void | Promise<void>;
};

const fallbackTitles: Record<PendingInvoiceObjectDetailTarget["kind"], string> = {
  bankTransaction: "流水详情",
  invoice: "发票详情",
  oa: "OA详情",
};

export default function PendingInvoiceDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
  onBankSplitSaved,
}: PendingInvoiceDetailDrawerProps) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const [detail, setDetail] = useState<PendingInvoiceObjectDetail | null>(null);
  const [requestTarget, setRequestTarget] = useState<PendingInvoiceObjectDetailTarget | null>(null);
  const [loading, setLoading] = useState(false);
  const currentRequest = requestTarget === target;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRequestTarget(target);
    if (!open || !target) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    loadDetail(target)
      .then((payload) => {
        if (active) {
          setDetail(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "详情加载失败");
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
  }, [loadDetail, open, target]);

  const title = target ? fallbackTitles[target.kind] : "详情";
  const sections = currentRequest && detail ? preparePublicDetailSections(detail.sections) : [];
  const body = (
    <div className="pending-invoice-detail-body">
      <BankTransactionDetailContent onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved} bankTransactionId={target?.kind === "bankTransaction" ? target.id : undefined}
        detailAvailable={currentRequest ? detail?.detailAvailable : undefined}
        error={currentRequest ? error : null}
        loading={loading || Boolean(open && target && !currentRequest)}
        sections={sections}
        unavailableReason={currentRequest ? detail?.unavailableReason : undefined}
      />
    </div>
  );

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭详情抽屉"
      onClose={close}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      {body}
    </PendingInvoiceDrawerFrame>
  );
}
