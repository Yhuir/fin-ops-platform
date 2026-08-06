import { Chip, Separator } from "@heroui/react";

import type { CostTransactionDetail } from "../../features/cost-statistics/types";
import BankAccountValue from "../BankAccountValue";
import { formatCostAmount } from "../../features/cost-statistics/format";

type CostTransactionDetailPanelProps = {
  detail: CostTransactionDetail["transaction"];
};

function fieldEntries(fields: Record<string, string>) {
  return Object.entries(fields).filter(([label, value]) => label !== "资金方向" && value);
}

function renderFieldRows(entries: Array<[string, string]>) {
  return (
    <dl className="cost-detail-field-list">
      {entries.map(([label, value]) => (
        <div key={label} className="cost-detail-field-row">
          <dt>{label}</dt>
          <dd>
            {label === "支付账户" || label === "收款账户"
              ? <BankAccountValue value={value} variant="tag" />
              : /金额|价税合计|税额|余额|差异/.test(label)
                ? formatCostAmount(value)
                : value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function CostTransactionDetailPanel({ detail }: CostTransactionDetailPanelProps) {
  const summaryEntries = fieldEntries(detail.summaryFields);
  const detailEntries = fieldEntries(detail.detailFields);
  const direction = detail.direction === "收入" ? "收入" : "支出";

  return (
    <div className="cost-detail-stack">
      <section className="cost-detail-section" aria-labelledby="cost-detail-overview-title">
        <h3 id="cost-detail-overview-title">流水概览</h3>
        <dl className="cost-detail-overview">
          <div>
            <dt>金额</dt>
            <dd className="cost-detail-amount">{formatCostAmount(detail.amount)}</dd>
          </div>
          <div>
            <dt>方向与账户</dt>
            <dd className="cost-detail-chips">
              <Chip color={direction === "收入" ? "success" : "danger"} size="sm" variant="soft">
                <Chip.Label>{direction}</Chip.Label>
              </Chip>
              <Chip color="default" size="sm" variant="soft">
                <Chip.Label><BankAccountValue value={detail.paymentAccountLabel} /></Chip.Label>
              </Chip>
            </dd>
          </div>
          <div>
            <dt>交易时间</dt>
            <dd>{detail.tradeTime}</dd>
          </div>
          <div>
            <dt>对方户名</dt>
            <dd>{detail.counterpartyName || "—"}</dd>
          </div>
        </dl>
      </section>

      <Separator className="cost-detail-separator" />

      <section className="cost-detail-section" aria-labelledby="cost-detail-attribution-title">
        <h3 id="cost-detail-attribution-title">成本归属</h3>
        <dl className="cost-detail-field-list">
          <div className="cost-detail-field-row">
            <dt>项目名称</dt>
            <dd>{detail.projectName || "—"}</dd>
          </div>
          <div className="cost-detail-field-row">
            <dt>OA费用类型</dt>
            <dd>{detail.expenseType || "—"}</dd>
          </div>
          <div className="cost-detail-field-row">
            <dt>OA提交人</dt>
            <dd>{detail.oaApplicant || "—"}</dd>
          </div>
          <div className="cost-detail-field-row">
            <dt>费用内容</dt>
            <dd>{detail.expenseContent || "—"}</dd>
          </div>
          <div className="cost-detail-field-row">
            <dt>备注</dt>
            <dd>{detail.remark || "—"}</dd>
          </div>
        </dl>
      </section>

      {detail.costAllocations.length > 1 ? (
        <>
          <Separator className="cost-detail-separator" />
          <section className="cost-detail-section" aria-labelledby="cost-detail-allocation-title">
            <h3 id="cost-detail-allocation-title">OA 成本拆分</h3>
            <ol className="cost-detail-allocation-list">
              {detail.costAllocations.map((allocation) => (
                <li key={allocation.rowKey}>
                  <span className="cost-detail-allocation-main">
                    <strong>{allocation.projectName}</strong>
                    <span>{allocation.expenseType}</span>
                  </span>
                  <strong className="cost-detail-allocation-amount">{formatCostAmount(allocation.amount)}</strong>
                  {allocation.expenseContent ? (
                    <span className="cost-detail-allocation-content">{allocation.expenseContent}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : null}

      {summaryEntries.length > 0 ? (
        <>
          <Separator className="cost-detail-separator" />
          <section className="cost-detail-section" aria-labelledby="cost-detail-summary-title">
            <h3 id="cost-detail-summary-title">流水摘要字段</h3>
            {renderFieldRows(summaryEntries)}
          </section>
        </>
      ) : null}

      {detailEntries.length > 0 ? (
        <>
          <Separator className="cost-detail-separator" />
          <section className="cost-detail-section" aria-labelledby="cost-detail-fields-title">
            <h3 id="cost-detail-fields-title">流水详细字段</h3>
            {renderFieldRows(detailEntries)}
          </section>
        </>
      ) : null}
    </div>
  );
}
