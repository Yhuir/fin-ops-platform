import type { CostEntryDetail } from "../../features/cost-statistics/types";
import { formatCostAmount } from "../../features/cost-statistics/format";
import EntityDetailContent, {
  preparePublicDetailSections,
  type EntityDetailSection,
} from "../common/EntityDetailContent";

export default function CostEntryDetailPanel({ detail }: { detail: CostEntryDetail }) {
  return <EntityDetailContent sections={costDetailSections(detail)} />;
}

function costDetailSections(detail: CostEntryDetail) {
  if (detail.kind === "bank_transaction") {
    const transaction = detail.bankTransaction;
    return preparePublicDetailSections([{
      title: "交易信息",
      fields: [
        { label: "交易时间", value: transaction.tradeTime },
        { label: "收支方向", value: transaction.direction },
        { label: transaction.direction === "收入" ? "收入金额" : "支出金额", value: formatCostAmount(transaction.amount) },
        { label: "对方户名", value: transaction.counterpartyName },
        { label: "银行账户", value: transaction.paymentAccountLabel },
        { label: "摘要", value: transaction.expenseContent },
        { label: "备注", value: transaction.remark },
      ],
    }]);
  }

  const allocation = detail.allocation;
  const sections: EntityDetailSection[] = [{
    title: "基本信息",
    fields: [
      { label: "金额", value: formatCostAmount(allocation.amount) },
      { label: "审批完成时间", value: allocation.oaCompletedAt },
      { label: "项目名称", value: allocation.projectName },
      { label: "费用类型", value: allocation.expenseType },
      { label: "费用内容", value: allocation.expenseContent },
      { label: "OA类型", value: allocation.oaApplyType },
      { label: "申请人", value: allocation.oaApplicant },
      { label: "对方户名", value: allocation.counterpartyName },
      { label: "银行账户", value: allocation.paymentAccountLabel },
    ],
  }, {
    title: "金额核对",
    fields: [
      { label: "OA归集合计", value: formatCostAmount(detail.reconciliation.oaAllocationTotal) },
      { label: "关联付款流水合计", value: formatCostAmount(detail.reconciliation.bankOutflowTotal) },
      { label: "差异", value: formatCostAmount(detail.reconciliation.difference) },
      { label: "状态", value: detail.reconciliation.status === "balanced" ? "金额一致" : "金额不一致" },
    ],
  }];
  detail.paymentEvidence.forEach((evidence, index) => {
    sections.push({
      title: detail.paymentEvidence.length > 1 ? `银行流水 ${index + 1}` : "关联付款流水",
      fields: [
        { label: "交易时间", value: evidence.tradeTime },
        { label: "对方户名", value: evidence.counterpartyName },
        { label: "支出金额", value: formatCostAmount(evidence.amount) },
        { label: "银行账户", value: evidence.paymentAccountLabel },
        { label: "备注", value: evidence.remark },
      ],
    });
  });
  return preparePublicDetailSections(sections);
}
