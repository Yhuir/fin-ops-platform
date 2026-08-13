import { Chip, Separator } from "@heroui/react";

import type { CostEntryDetail } from "../../features/cost-statistics/types";
import { formatCostAmount } from "../../features/cost-statistics/format";
import BankAccountValue from "../BankAccountValue";

export default function CostEntryDetailPanel({ detail }: { detail: CostEntryDetail }) {
  if (detail.kind === "bank_transaction") {
    const transaction = detail.bankTransaction;
    const direction = transaction.direction === "收入" ? "收入" : "支出";
    return (
      <div className="cost-detail-stack">
        <section className="cost-detail-section" aria-labelledby="cost-detail-bank-title">
          <h3 id="cost-detail-bank-title">银行流水概览</h3>
          <dl className="cost-detail-overview">
            <div><dt>流水金额</dt><dd className="cost-detail-amount">{formatCostAmount(transaction.amount)}</dd></div>
            <div>
              <dt>方向与账户</dt>
              <dd className="cost-detail-chips">
                <Chip color={direction === "收入" ? "success" : "danger"} size="sm" variant="soft"><Chip.Label>{direction}</Chip.Label></Chip>
                <Chip color="default" size="sm" variant="soft"><Chip.Label><BankAccountValue value={transaction.paymentAccountLabel} /></Chip.Label></Chip>
              </dd>
            </div>
            <div><dt>交易时间</dt><dd>{transaction.tradeTime}</dd></div>
            <div><dt>对方户名</dt><dd>{transaction.counterpartyName || "—"}</dd></div>
            <div><dt>流水摘要</dt><dd>{transaction.expenseContent || "—"}</dd></div>
            <div><dt>备注</dt><dd>{transaction.remark || "—"}</dd></div>
          </dl>
        </section>
      </div>
    );
  }

  const allocation = detail.allocation;
  const reconciliation = detail.reconciliation;
  return (
    <div className="cost-detail-stack">
      <section className="cost-detail-section" aria-labelledby="cost-detail-allocation-title">
        <h3 id="cost-detail-allocation-title">OA 成本归集</h3>
        <dl className="cost-detail-overview">
          <div><dt>归集金额</dt><dd className="cost-detail-amount">{formatCostAmount(allocation.amount)}</dd></div>
          <div><dt>OA 完成时间</dt><dd>{allocation.oaCompletedAt || "—"}</dd></div>
          <div><dt>项目名称</dt><dd>{allocation.projectName || "—"}</dd></div>
          <div><dt>OA 费用类型</dt><dd>{allocation.expenseType || "—"}</dd></div>
          <div><dt>费用内容</dt><dd>{allocation.expenseContent || "—"}</dd></div>
          <div><dt>OA 类型</dt><dd>{allocation.oaApplyType || "—"}</dd></div>
          <div><dt>OA 单号</dt><dd>{allocation.oaId || "—"}</dd></div>
          {allocation.expenseItemId ? <div><dt>子付款项 ID</dt><dd>{allocation.expenseItemId}</dd></div> : null}
          <div><dt>申请人</dt><dd>{allocation.oaApplicant || "—"}</dd></div>
          <div><dt>支付账户归属</dt><dd><BankAccountValue value={allocation.paymentAccountLabel || "—"} variant="tag" /></dd></div>
        </dl>
      </section>

      <Separator className="cost-detail-separator" />

      <section className="cost-detail-section" aria-labelledby="cost-detail-reconciliation-title">
        <h3 id="cost-detail-reconciliation-title">关联关系校验</h3>
        <dl className="cost-detail-field-list">
          <div className="cost-detail-field-row"><dt>关系组</dt><dd>{reconciliation.relationCaseId || "—"}</dd></div>
          <div className="cost-detail-field-row"><dt>OA 归集合计</dt><dd>{formatCostAmount(reconciliation.oaAllocationTotal)}</dd></div>
          <div className="cost-detail-field-row"><dt>关联付款流水合计</dt><dd>{formatCostAmount(reconciliation.bankOutflowTotal)}</dd></div>
          <div className="cost-detail-field-row"><dt>差异</dt><dd>{formatCostAmount(reconciliation.difference)}</dd></div>
          <div className="cost-detail-field-row">
            <dt>状态</dt>
            <dd><Chip color={reconciliation.status === "balanced" ? "success" : "warning"} size="sm" variant="soft"><Chip.Label>{reconciliation.status === "balanced" ? "金额一致" : "金额不一致"}</Chip.Label></Chip></dd>
          </div>
        </dl>
      </section>

      <Separator className="cost-detail-separator" />

      <section className="cost-detail-section" aria-labelledby="cost-detail-evidence-title">
        <h3 id="cost-detail-evidence-title">关联付款流水</h3>
        <ol className="cost-detail-allocation-list">
          {detail.paymentEvidence.map((evidence) => (
            <li key={evidence.transactionId}>
              <span className="cost-detail-allocation-main">
                <strong>{evidence.counterpartyName || "未知对方"}</strong>
                <span>{evidence.tradeTime || "—"} · {evidence.paymentAccountLabel || "未识别账户"}</span>
              </span>
              <strong className="cost-detail-allocation-amount">{formatCostAmount(evidence.amount)}</strong>
              {evidence.remark ? <span className="cost-detail-allocation-content">{evidence.remark}</span> : null}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
