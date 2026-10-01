import { Button, PopoverContent, PopoverDialog, PopoverRoot } from "@heroui/react";
import { useRef } from "react";
import { ChevronDown } from "lucide-react";
import { formatMoney } from "../../features/turnoverLedger/presentation";
import type { TurnoverLedgerFamily, TurnoverLedgerGroupedResponse } from "../../features/turnoverLedger/types";

const metrics = [
  ["pendingRepaymentAmount", "我方待还", "pending-repayment"],
  ["pendingCollectionAmount", "我方待收", "pending-collection"],
  ["repaidAmount", "累计已还", "repaid"],
  ["collectedAmount", "累计已收", "collected"],
] as const;

export default function TurnoverLedgerSummary({ ledger, family }: { ledger: TurnoverLedgerGroupedResponse | null; family: TurnoverLedgerFamily }) {
  const families = ["personal", "company", "bank", "business"];
  const breakdown = ledger?.familySummaries.filter(item => families.includes(item.family))
    .sort((a, b) => families.indexOf(a.family) - families.indexOf(b.family)) ?? [];
  const triggerRef = useRef<HTMLButtonElement>(null);
  return <div className="turnover-overview">
    {metrics.map(([key, label, id], index) => <div className={`turnover-overview-metric${index > 1 ? " turnover-overview-metric--secondary" : ""}`} data-testid={`turnover-summary-${id}`} key={key}>
      <span>{label}</span><strong>{ledger ? formatMoney(ledger.summary[key]) : "—"}</strong>
    </div>)}
    <PopoverRoot key={ledger ? "available" : "unavailable"}><Button ref={triggerRef} isDisabled={!ledger} variant="ghost" size="sm" className="turnover-breakdown-trigger" aria-label="查看分类明细">分类明细<ChevronDown size={14} /></Button>
      <PopoverContent isNonModal shouldCloseOnInteractOutside={(element) => !triggerRef.current?.contains(element)} placement="bottom start" className="turnover-breakdown-popover"><PopoverDialog aria-label="往来款分类明细">
        <p className="turnover-breakdown-scope">当前搜索及结算条件下的四类往来统计</p>
        {ledger ? <div className="turnover-breakdown-scroll"><table><thead><tr><th scope="col">类别</th>{metrics.map(([, label]) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{breakdown.map((item) => <tr key={item.family} className={item.family === family ? "turnover-breakdown-current" : undefined}><th scope="row">{item.label}{item.family === family ? <span className="turnover-breakdown-current-label">当前</span> : null}</th>{metrics.map(([key]) => <td key={key}>{formatMoney(item[key])}</td>)}</tr>)}</tbody>
        </table>{!breakdown.length ? <p>暂无分类统计</p> : null}</div> : <p>统计暂不可用</p>}
      </PopoverDialog></PopoverContent>
    </PopoverRoot>
  </div>;
}
