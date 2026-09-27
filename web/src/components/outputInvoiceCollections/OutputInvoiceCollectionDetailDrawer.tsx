import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import { preparePublicDetailSections } from "../common/EntityDetailContent";
import type {
  OutputInvoiceCollectionDetailResponse,
  OutputInvoiceCollectionDetailTarget,
} from "../../features/outputInvoiceCollections/types";

type OutputInvoiceCollectionDetailDrawerProps = {
  open: boolean;
  target: OutputInvoiceCollectionDetailTarget | null;
  loadDetail: (target: OutputInvoiceCollectionDetailTarget) => Promise<OutputInvoiceCollectionDetailResponse>;
  onClose: () => void;
  onBankSplitSaved?: () => void | Promise<void>;
};

export default function OutputInvoiceCollectionDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
  onBankSplitSaved,
}: OutputInvoiceCollectionDetailDrawerProps) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const [detail, setDetail] = useState<OutputInvoiceCollectionDetailResponse | null>(null);
  const [requestTarget, setRequestTarget] = useState<OutputInvoiceCollectionDetailTarget | null>(null);
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

  const title = (currentRequest ? detail?.title : undefined) ?? drawerTitle(target);
  const sections = currentRequest && detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭详情抽屉"
      onClose={close}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      <div className="output-invoice-collection-drawer__body">
        <BankTransactionDetailContent onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved} bankTransactionId={target?.kind === "bank" ? target.id : undefined}
          detailAvailable={currentRequest ? detail?.detailAvailable : undefined}
          error={currentRequest ? error : null}
          loading={loading || Boolean(open && target && !currentRequest)}
          sections={sections}
          unavailableReason={currentRequest ? detail?.unavailableReason : undefined}
        />
      </div>
    </AppDrawer>
  );
}

function drawerTitle(target: OutputInvoiceCollectionDetailTarget | null) {
  if (target?.kind === "bank" || target?.relationKind === "bank") {
    return "流水详情";
  }
  return "销项发票详情";
}
