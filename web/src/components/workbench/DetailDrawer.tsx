import type { ComponentProps } from "react";
import { useBankSplitClose } from "../../features/bankSplits/useBankSplitClose";
import BankTransactionDetailContent from "../../features/bankSplits/BankTransactionDetailContent";
import AppDrawer from "../common/AppDrawer";
import {
  preparePublicDetailSections,
  type EntityDetailField,
} from "../common/EntityDetailContent";
import type { WorkbenchRecord } from "../../features/workbench/types";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onBankSplitSaved?: ComponentProps<typeof BankTransactionDetailContent>["onBankSplitSaved"];
  renderPartAction?: ComponentProps<typeof BankTransactionDetailContent>["renderPartAction"];
};

const drawerTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "OA详情",
  bank: "银行流水详情",
  invoice: "发票详情",
};

const sectionTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "基本信息",
  bank: "交易信息",
  invoice: "基本信息",
};

export default function DetailDrawer({ row, loading, error, onClose, onBankSplitSaved, renderPartAction }: DetailDrawerProps) {
  const { close, setDirty } = useBankSplitClose(onClose);
  const open = Boolean(row);
  const title = row ? drawerTitles[row.recordType] : "详情";
  const sections = row
    ? preparePublicDetailSections([{
        title: sectionTitles[row.recordType],
        fields: row.detailFields.map((field): EntityDetailField => ({
          label: field.label,
          value: sanitizeAttachmentValue(field.value),
        })),
      }, ...(row.expenseItems ?? []).map((item, index) => ({
        title: `费用明细 ${index + 1}`,
        fields: [
          { label: "项目名称", value: item.projectName },
          { label: "报销金额", value: item.amount },
          { label: "费用类型", value: item.expenseType ?? "—" },
          { label: "费用内容", value: item.expenseContent ?? "—" },
          { label: "费用说明", value: item.feeDescription ?? "—" },
          { label: "报销日期", value: item.reimbursementDate ?? "—" },
          { label: "支付方式", value: item.paymentMethod ?? "—" },
          { label: "发票种类", value: item.invoiceKind ?? "—" },
          { label: "票据张数", value: item.ticketCount ?? "—" },
          { label: "附件文件数", value: String(item.attachmentFileCount ?? "—") },
        ],
      }))])
    : [];

  return (
    <AppDrawer
      className="workbench-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      title={title}
      width="min(800px, 100vw)"
      onClose={close}
    >
      <div className="workbench-detail-drawer__body">
        <BankTransactionDetailContent renderPartAction={renderPartAction} onSplitDirtyChange={setDirty} onBankSplitSaved={onBankSplitSaved} bankTransactionId={row?.recordType === "bank" ? row.id : undefined} error={error} loading={loading} sections={sections} />
      </div>
    </AppDrawer>
  );
}

function sanitizeAttachmentValue(value: string) {
  return value.replace(/\s*[（(][0-9a-f]{16,}\.(?:png|jpg|jpeg|pdf)[）)]/gi, "");
}
