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
        { label: "归属项目", value: transaction.projectName },
        { label: "费用类型", value: transaction.expenseType },
      ],
    }]);
  }

  const allocation = detail.allocation;
  const sections: EntityDetailSection[] = [{
    title: "基本信息",
    fields: [
      { label: "本项净成本", value: formatCostAmount(allocation.amount) },
      { label: "OA 原始金额", value: formatCostAmount(allocation.oaOriginalAmount) },
      { label: "OA 金额占比", value: allocation.oaAllocationWeight },
      { label: "本笔支出流水原额", value: formatCostAmount(allocation.bankEventAmount) },
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
      { label: "OA 原始金额合计", value: formatCostAmount(detail.reconciliation.oaTotal) },
      { label: "支出流水原额", value: formatCostAmount(detail.reconciliation.grossOutflowTotal) },
      { label: "付错退款", value: formatCostReduction(detail.reconciliation.wrongPaymentRefundTotal) },
      { label: "关系净支出", value: formatCostAmount(detail.reconciliation.netOutflowTotal) },
      { label: "净支出与 OA 差额", value: formatCostAmount(detail.reconciliation.difference) },
      { label: "净支出 / OA", value: detail.reconciliation.cashPaymentRatio },
      { label: "状态", value: detail.reconciliation.status === "balanced" ? "金额一致" : "金额不一致" },
    ],
  }];
  detail.paymentEvidence.forEach((evidence, index) => {
    sections.push({
      title: detail.paymentEvidence.length > 1 ? `关系内银行流水 ${index + 1}` : "关系内银行流水",
      fields: [
        { label: "交易时间", value: evidence.tradeTime },
        { label: "收支方向", value: evidence.direction },
        { label: "对方户名", value: evidence.counterpartyName },
        {
          label: evidence.direction === "收入" ? "付错退款金额" : "支出金额",
          value: evidence.direction === "收入"
            ? formatCostReduction(evidence.amount)
            : formatCostAmount(evidence.amount),
        },
        { label: "流水标签", value: evidence.bankTagLabel },
        { label: "银行账户", value: evidence.paymentAccountLabel },
        { label: "备注", value: evidence.remark },
      ],
    });
  });
  return preparePublicDetailSections(sections);
}

function formatCostReduction(value: string): string {
  const normalized = value.trim().replace(/,/g, "");
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(normalized)) {
    return formatCostAmount(value);
  }
  const unsigned = normalized.replace(/^[+-]/, "");
  return formatCostAmount(/^0+(?:\.0+)?$/.test(unsigned) ? "0" : `-${unsigned}`);
}
