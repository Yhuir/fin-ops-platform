import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import { useSourceDetail } from "../../features/useSourceDetail";

import type { PendingInvoiceRelationDetail, PendingInvoiceRelationDetailKind } from "../../features/pendingInvoices/types";
import { preparePublicDetailSections } from "../common/EntityDetailContent";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRelationDrawerProps = {
  open: boolean;
  transactionId: string | null;
  detailKind?: PendingInvoiceRelationDetailKind;
  loadDetail: (transactionId: string, signal?: AbortSignal) => Promise<PendingInvoiceRelationDetail>;
  onClose: () => void;
  onBankSplitSaved?: () => void | Promise<void>;
};

const drawerTitles: Record<PendingInvoiceRelationDetailKind, string> = {
  all: "详情",
  bank: "银行流水详情",
  invoice: "发票详情",
  oa: "OA详情",
};

export default function PendingInvoiceRelationDrawer({
  open,
  transactionId,
  detailKind = "all",
  loadDetail,
  onClose,
  onBankSplitSaved,
}: PendingInvoiceRelationDrawerProps) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const { detail, error, loading } = useSourceDetail(open, transactionId, loadDetail);

  const sections = detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <PendingInvoiceDrawerFrame sourceDetail
      closeLabel="关闭详情抽屉"
      onClose={close}
      open={open}
      title={drawerTitles[detailKind]}
      width="min(800px, 100vw)"
    >
      <BankTransactionDetailContent onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved}
        emptyMessage="暂无可展示的详情。"
        error={error}
        loading={loading}
        loadingLabel="正在加载详情"
        sections={sections}
      />
    </PendingInvoiceDrawerFrame>
  );
}
