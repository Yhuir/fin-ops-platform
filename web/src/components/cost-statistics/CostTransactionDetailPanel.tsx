import type { CostTransactionDetail } from "../../features/cost-statistics/types";
import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";

type CostTransactionDetailPanelProps = {
  detail: CostTransactionDetail["transaction"];
};

function renderFieldRows(fields: Record<string, string>) {
  const entries = Object.entries(fields).filter(([label, value]) => label !== "资金方向" && value);
  if (entries.length === 0) {
    return <div className="state-panel">当前流水没有更多字段。</div>;
  }

  return (
    <dl className="cost-detail-grid">
      {entries.map(([label, value]) => (
        <div key={label} className="cost-detail-item">
          <dt>{label}</dt>
          <dd>{label === "支付账户" || label === "收款账户" ? <BankAccountValue value={value} variant="tag" /> : value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function CostTransactionDetailPanel({ detail }: CostTransactionDetailPanelProps) {
  return (
    <div className="cost-detail-stack">
      <div className="cost-detail-summary">
        <div className="cost-detail-summary-item">
          <span>项目名称</span>
          <strong>{detail.projectName}</strong>
        </div>
        <div className="cost-detail-summary-item">
          <span>费用类型</span>
          <strong>{detail.expenseType}</strong>
        </div>
        <div className="cost-detail-summary-item">
          <span>金额</span>
          <strong className="money-cell-stack money-detail-stack">
            <span className="money-detail-value">
              <span>{detail.amount}</span>
            </span>
            <span className="money-cell-meta-row">
              <DirectionTag direction={detail.direction} />
              <span className="money-cell-account">
                <BankAccountValue value={detail.paymentAccountLabel} variant="tag" />
              </span>
            </span>
          </strong>
        </div>
        <div className="cost-detail-summary-item">
          <span>交易时间</span>
          <strong>{detail.tradeTime}</strong>
        </div>
      </div>

      <section className="cost-detail-section">
        <header className="cost-detail-section-header">
          <h2>成本归属</h2>
          <p>展示这条支出流水对应的 OA 成本字段，便于核对项目归属和费用分类。</p>
        </header>
        <dl className="cost-detail-grid compact">
          <div className="cost-detail-item">
            <dt>OA提交人</dt>
            <dd>{detail.oaApplicant}</dd>
          </div>
          <div className="cost-detail-item">
            <dt>费用内容</dt>
            <dd>{detail.expenseContent}</dd>
          </div>
          <div className="cost-detail-item">
            <dt>对方户名</dt>
            <dd>{detail.counterpartyName}</dd>
          </div>
          <div className="cost-detail-item">
            <dt>备注</dt>
            <dd>{detail.remark || "—"}</dd>
          </div>
        </dl>
      </section>

      <section className="cost-detail-section">
        <header className="cost-detail-section-header">
          <h2>流水摘要字段</h2>
          <p>用于快速核对当前流水在工作台主表中的关键信息。</p>
        </header>
        {renderFieldRows(detail.summaryFields)}
      </section>

      <section className="cost-detail-section">
        <header className="cost-detail-section-header">
          <h2>流水详细字段</h2>
          <p>保留原始银行流水详情字段，方便继续向下核查。</p>
        </header>
        {renderFieldRows(detail.detailFields)}
      </section>
    </div>
  );
}
