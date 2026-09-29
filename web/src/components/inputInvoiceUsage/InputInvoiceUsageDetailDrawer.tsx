import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import { useSourceDetail } from "../../features/useSourceDetail";

import AppDrawer from "../common/AppDrawer";
import {
  preparePublicDetailSections,
  type EntityDetailField,
  type EntityDetailSection,
} from "../common/EntityDetailContent";

export type InputInvoiceUsageDetailTarget = {
  kind: "invoice" | "bank" | "oa" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: string;
};

export type InputInvoiceUsageDetailField = EntityDetailField;

export type InputInvoiceUsageDetailSection = EntityDetailSection;

export type InputInvoiceUsageDetailPayload = {
  title?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: InputInvoiceUsageDetailSection[];
};

type InputInvoiceUsageDetailDrawerProps<TTarget extends InputInvoiceUsageDetailTarget> = {
  open: boolean;
  target: TTarget | null;
  loadDetail: (target: TTarget, signal?: AbortSignal) => Promise<InputInvoiceUsageDetailPayload>;
  onClose: () => void;
  onBankSplitSaved?: () => void | Promise<void>;
};

const fallbackTitles: Record<InputInvoiceUsageDetailTarget["kind"], string> = {
  invoice: "发票详情",
  bank: "银行流水详情",
  oa: "OA详情",
  relationList: "关联明细",
};

export default function InputInvoiceUsageDetailDrawer<TTarget extends InputInvoiceUsageDetailTarget>({
  open,
  target,
  loadDetail,
  onClose,
  onBankSplitSaved,
}: InputInvoiceUsageDetailDrawerProps<TTarget>) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const { detail, error, loading } = useSourceDetail(open, target, loadDetail);

  const title = detail?.title ?? (target ? fallbackTitles[target.kind] : "详情");
  const sections = detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <AppDrawer
      className="input-invoice-usage-detail-drawer source-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      title={title}
      width="min(800px, 100vw)"
      onClose={close}
    >
      <div className="input-invoice-usage-drawer-body">
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
