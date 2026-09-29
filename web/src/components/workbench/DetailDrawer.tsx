import type { ComponentProps } from "react";
import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import AppDrawer from "../common/AppDrawer";
import {
  preparePublicDetailSections,
} from "../common/EntityDetailContent";
import type { WorkbenchRecord } from "../../features/workbench/types";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onBankSplitSaved?: ComponentProps<typeof BankTransactionDetailContent>["onBankSplitSaved"];
};

const drawerTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "OA详情",
  bank: "银行流水详情",
  invoice: "发票详情",
};

export default function DetailDrawer({ row, loading, error, onClose, onBankSplitSaved }: DetailDrawerProps) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const open = Boolean(row);
  const title = row ? drawerTitles[row.recordType] : "详情";
  const sections = row && !loading && !error
    ? preparePublicDetailSections(row.sourceSections ?? [])
    : [];

  return (
    <AppDrawer
      className="workbench-detail-drawer source-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      title={title}
      width="min(800px, 100vw)"
      onClose={close}
    >
      <div className="workbench-detail-drawer__body">
        <BankTransactionDetailContent onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved} bankTransactionId={row?.recordType === "bank" ? row.id : undefined} error={error} loading={loading} sections={sections} />
      </div>
    </AppDrawer>
  );
}
