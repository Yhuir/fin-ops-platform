import { PopoverContent, PopoverDialog, PopoverRoot, PopoverTrigger } from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { formatMoney } from "../../features/turnoverLedger/presentation";
import type { TurnoverLedgerGroupedResponse } from "../../features/turnoverLedger/types";

const metrics = [
  ["pendingRepaymentAmount", "我方待还", "pending-repayment"],
  ["pendingCollectionAmount", "我方待收", "pending-collection"],
  ["repaidAmount", "累计已还", "repaid"],
  ["collectedAmount", "累计已收", "collected"],
] as const;

export default function TurnoverLedgerSummary({ ledger }: { ledger: TurnoverLedgerGroupedResponse | null }) {
  return <div className="turnover-overview">
    {metrics.map(([key, label, id], index) => <div className={`turnover-overview-metric${index > 1 ? " turnover-overview-metric--secondary" : ""}`} data-testid={`turnover-summary-${id}`} key={key}>
      <span>{label}</span><strong>{ledger ? formatMoney(ledger.summary[key]) : "—"}</strong>
    </div>)}
    <PopoverRoot><PopoverTrigger className="turnover-breakdown-trigger" aria-label="查看分类明细">分类明细<ChevronDown size={14} /></PopoverTrigger>
      <PopoverContent placement="bottom end" className="turnover-breakdown-popover"><PopoverDialog aria-label="往来款分类明细">
        <table><thead><tr><th>类别</th>{metrics.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{ledger?.familySummaries.map((family) => <tr key={family.family}><th>{family.label}</th>{metrics.map(([key]) => <td key={key}>{formatMoney(family[key])}</td>)}</tr>)}</tbody>
        </table>
      </PopoverDialog></PopoverContent>
    </PopoverRoot>
  </div>;
}
