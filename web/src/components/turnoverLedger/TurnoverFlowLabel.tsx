import type { TurnoverLedgerGroupedRow } from "../../features/turnoverLedger/types";
import { formatNullable } from "../../features/turnoverLedger/presentation";

export default function TurnoverFlowLabel({ row }: { row: TurnoverLedgerGroupedRow }) {
  return <div className="turnover-flow-label">
    <span>{formatNullable(row.categoryLabelPath.join(" / "))}</span>
    <span className="turnover-flow-label__action">往来标记：{row.turnoverActionLabel}</span>
  </div>;
}
