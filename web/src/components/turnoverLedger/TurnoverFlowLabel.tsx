import { Chip } from "@heroui/react";
import type { TurnoverLedgerGroupedRow } from "../../features/turnoverLedger/types";
import { formatNullable } from "../../features/turnoverLedger/presentation";
import { TruncatedCellText } from "../common/FinanceTable";

function actionColor(action: string | null) {
  switch (action) {
    case "pending_collection": return "accent";
    case "pending_repayment": return "warning";
    case "collected":
    case "repaid": return "success";
    default: return "default";
  }
}

export default function TurnoverFlowLabel({ row }: { row: Pick<TurnoverLedgerGroupedRow, "categoryLabelPath" | "turnoverActionType" | "turnoverActionLabel"> }) {
  return <div className="turnover-flow-label">
    <TruncatedCellText value={formatNullable(row.categoryLabelPath.join(" / "))} />
    <Chip className="turnover-flow-chip" color={actionColor(row.turnoverActionType)} size="sm" variant="soft">
      <Chip.Label>{row.turnoverActionLabel}</Chip.Label>
    </Chip>
  </div>;
}
