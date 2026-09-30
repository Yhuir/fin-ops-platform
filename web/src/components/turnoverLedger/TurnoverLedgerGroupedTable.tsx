import { Button, Checkbox } from "@heroui/react";
import { formatMoney as formatAccessibleMoney } from "../../features/money";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState, type MutableRefObject } from "react";

import type { TurnoverLedgerGroup, TurnoverLedgerGroupedRow } from "../../features/turnoverLedger/types";
import { formatMoney, formatNullable } from "../../features/turnoverLedger/presentation";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../common/FinanceTable";

import TurnoverFlowLabel from "./TurnoverFlowLabel";

export default function TurnoverLedgerGroupedTable({
  groups, loading, showEmptyState = true, onEdit, onDetails,
  selectedFlowRowIds = new Set<string>(), onToggleFlowSelection, tableWrapRef, actionsDisabled = false,
}: {
  groups: TurnoverLedgerGroup[];
  loading: boolean;
  showEmptyState?: boolean;
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
  onDetails: (group: TurnoverLedgerGroup) => void;
  selectedFlowRowIds?: Set<string>;
  onToggleFlowSelection?: (group: TurnoverLedgerGroup, row: TurnoverLedgerGroupedRow) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  actionsDisabled?: boolean;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set());
  return (
    <div className="turnover-register-scroll" ref={tableWrapRef}>
      {/* Native row spans keep the six-column register and eight-column detail grids independent. */}
      <table className="turnover-register" aria-label="外部往来款台账" aria-busy={loading}>
        <thead><tr>
          <th scope="col">往来对象</th><th scope="col">类别</th>
          <th scope="col" className="turnover-number">我方待还</th><th scope="col" className="turnover-number">我方待收</th>
          <th scope="col">结算状态</th><th scope="col">操作</th>
        </tr></thead>
        <tbody>
          {loading ? <tr><td colSpan={6} className="turnover-register-empty">正在加载往来款台账</td></tr> : null}
          {!loading && showEmptyState && !groups.length ? <tr><td colSpan={6} className="turnover-register-empty">暂无符合条件的往来款</td></tr> : null}
          {!loading ? groups.map((group) => {
            const expanded = expandedGroups.has(group.groupId);
            return <Fragment key={group.groupId}>
              <tr className={expanded ? "turnover-register-expanded" : undefined} data-testid={`turnover-row-${group.summaryRow?.relationId}`}>
                <th scope="row" data-testid={`turnover-group-cell-${group.groupId}`}>
                  <Button variant="ghost" size="sm" className="turnover-object-toggle" aria-label={`${expanded ? "收起" : "展开"} ${group.counterpartyName} 流水明细`} aria-expanded={expanded} aria-controls={`turnover-details-${group.groupId}`} onPress={() => setExpandedGroups((current) => { const next = new Set(current); if (next.has(group.groupId)) next.delete(group.groupId); else next.add(group.groupId); return next; })}>
                    {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span>{group.counterpartyName}</span><span className="turnover-muted">· {group.flowRows.length} 笔</span>
                  </Button>
                </th>
                <td className="turnover-muted">{group.familyLabel}</td>
                <td className="turnover-number">{formatMoney(group.pendingRepaymentAmount)}</td>
                <td className="turnover-number">{formatMoney(group.pendingCollectionAmount)}</td>
                <td><span className={group.cashClosureLinked ? "turnover-settled" : "turnover-muted"}>{group.cashClosureLinked ? "已结清" : "未结清"}</span></td>
                <td><Button variant="ghost" size="sm" className="turnover-text-action" onPress={() => onDetails(group)} aria-label={`查看${group.counterpartyName}详情`}>详情</Button></td>
              </tr>
              {expanded ? <tr id={`turnover-details-${group.groupId}`}><td colSpan={6} className="turnover-flow-container">
                <FinanceTable ariaLabel={`${group.counterpartyName}的银行流水`} className="turnover-flows" minWidth={870} scrollMode="contained">
                  <FinanceTableHeader>
                    <FinanceTableColumn columnRole="selection">选择</FinanceTableColumn><FinanceTableColumn columnRole="date" isRowHeader>日期</FinanceTableColumn>
                    <FinanceTableColumn columnRole="description">流水标签</FinanceTableColumn><FinanceTableColumn columnRole="amount">收入金额</FinanceTableColumn>
                    <FinanceTableColumn columnRole="amount">支出金额</FinanceTableColumn><FinanceTableColumn columnRole="account">银行账户</FinanceTableColumn>
                    <FinanceTableColumn columnRole="status">关联状态</FinanceTableColumn><FinanceTableColumn columnRole="action">操作</FinanceTableColumn>
                  </FinanceTableHeader>
                  <FinanceTableBody>{group.flowRows.map((row, index) => {
                    const accessibleName = `${group.counterpartyName} ${row.transactionAt || row.borrowDate || row.repaymentDate || "日期未提供"} ${row.flowDirection === "income" ? "收入" : "支出"} ${formatAccessibleMoney(row.flowAmount)}`;
                    return <FinanceTableRow key={row.sourceBankRowId} id={row.sourceBankRowId} dataTestId={`turnover-flow-row-${row.relationId}-${index}`}>
                      <FinanceTableCell columnRole="selection"><Checkbox aria-label={`选择流水 ${accessibleName}`} isDisabled={actionsDisabled} isSelected={selectedFlowRowIds.has(row.sourceBankRowId)} onChange={() => onToggleFlowSelection?.(group, row)}><Checkbox.Control className="turnover-ledger-checkbox"><Checkbox.Indicator /></Checkbox.Control></Checkbox></FinanceTableCell>
                      <FinanceTableCell columnRole="date">{formatNullable((row.transactionAt || row.borrowDate || row.repaymentDate)?.slice(0, 10))}</FinanceTableCell>
                      <FinanceTableCell columnRole="description"><TurnoverFlowLabel row={row} /></FinanceTableCell>
                      <FinanceTableCell columnRole="amount">{row.flowDirection === "income" ? formatMoney(row.flowAmount) : "—"}</FinanceTableCell>
                      <FinanceTableCell columnRole="amount">{row.flowDirection === "expense" ? formatMoney(row.flowAmount) : "—"}</FinanceTableCell>
                      <FinanceTableCell columnRole="account">{formatNullable(row.bankAccountLabels.join("、"))}</FinanceTableCell>
                      <FinanceTableCell columnRole="status"><span className="turnover-flow-relations">{[row.cashClosureLinked ? "已结清" : row.cashPairLinked ? "已配对" : "", row.linkedOa ? "已关联 OA" : "", row.linkedInvoice ? "已关联发票" : ""].filter(Boolean).join(" · ") || "—"}</span></FinanceTableCell>
                      <FinanceTableCell columnRole="action"><Button className="turnover-text-action" variant="ghost" size="sm" aria-label={`${actionsDisabled ? "查看" : "编辑"}流水 ${accessibleName}`} onPress={() => onEdit({ ...row, counterpartyName: group.counterpartyName, familyLabel: group.familyLabel })}>{actionsDisabled ? "查看" : "编辑"}</Button></FinanceTableCell>
                    </FinanceTableRow>;
                  })}</FinanceTableBody>
                </FinanceTable>
              </td></tr> : null}
            </Fragment>;
          }) : null}
        </tbody>
      </table>
    </div>
  );
}
