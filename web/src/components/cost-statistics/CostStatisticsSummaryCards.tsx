type CostStatisticsSummaryCardsProps = {
  rowLabel: string;
  rowCount: number;
  transactionCount: number;
  totalAmount: string;
};

export default function CostStatisticsSummaryCards({
  rowLabel,
  rowCount,
  transactionCount,
  totalAmount,
}: CostStatisticsSummaryCardsProps) {
  return (
    <div className="stats-row">
      <div className="stat-card">
        <span>{rowLabel}</span>
        <strong>{rowCount}</strong>
      </div>
      <div className="stat-card">
        <span>支出流水</span>
        <strong>{transactionCount}</strong>
      </div>
      <div className="stat-card">
        <span>支出总额</span>
        <strong>{totalAmount}</strong>
      </div>
    </div>
  );
}
