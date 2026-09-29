import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import { useSourceDetail } from "../../features/useSourceDetail";

import AppDrawer from "../common/AppDrawer";
import { preparePublicDetailSections } from "../common/EntityDetailContent";
import type {
  OutputInvoiceCollectionDetailResponse,
  OutputInvoiceCollectionDetailTarget,
} from "../../features/outputInvoiceCollections/types";

type OutputInvoiceCollectionDetailDrawerProps = {
  open: boolean;
  target: OutputInvoiceCollectionDetailTarget | null;
  loadDetail: (target: OutputInvoiceCollectionDetailTarget, signal?: AbortSignal) => Promise<OutputInvoiceCollectionDetailResponse>;
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
  const { detail, error, loading } = useSourceDetail(open, target, loadDetail);

  const title = detail?.title ?? drawerTitle(target);
  const sections = detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <AppDrawer
      className="output-invoice-collection-drawer source-detail-drawer"
      closeLabel="关闭详情抽屉"
      onClose={close}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      <div className="output-invoice-collection-drawer__body">
        <BankTransactionDetailContent onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved} bankTransactionId={target?.kind === "bank" ? target.id : undefined}
          detailAvailable={detail?.detailAvailable}
          error={error}
          loading={loading}
          sections={sections}
          unavailableReason={detail?.unavailableReason}
        />
      </div>
    </AppDrawer>
  );
}

function drawerTitle(target: OutputInvoiceCollectionDetailTarget | null) {
  if (target?.kind === "bank" || target?.relationKind === "bank") {
    return "银行流水详情";
  }
  return "发票详情";
}
