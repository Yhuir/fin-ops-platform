import { useState, type MutableRefObject } from "react";

import type {
  TurnoverLedgerDirection,
  TurnoverLedgerGroup,
  TurnoverLedgerGroupedRow,
} from "../../features/turnoverLedger/types";

type RuntimeGroupedRow = TurnoverLedgerGroupedRow & {
  rowKind?: "summary" | "lot" | string;
  lotId?: string;
  balanceAmount?: string;
};

type RuntimeGroup = TurnoverLedgerGroup & {
  summaryRow?: TurnoverLedgerGroupedRow;
  flowRows?: TurnoverLedgerGroupedRow[];
  lotRows?: TurnoverLedgerGroupedRow[];
  pendingRepaymentAmount?: string;
  pendingCollectionAmount?: string;
  closedAmount?: string;
};

export function formatMoney(value: string | null | undefined) {
  if (!value || !value.trim()) {
    return "0.00";
  }
  const parsed = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatNullable(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function categoryPathText(row: TurnoverLedgerGroupedRow) {
  const path = row.categoryLabelPath.filter(Boolean);
  if (path.length > 0) {
    return path.join(" / ");
  }
  const labelPath = [row.categoryPrimaryLabel, row.categorySubLabel, row.categoryThirdLabel].filter(Boolean);
  if (labelPath.length > 0) {
    return labelPath.join(" / ");
  }
  return formatNullable(row.categoryLabel);
}

function categoryChipLabels(row: TurnoverLedgerGroupedRow) {
  const path = row.categoryLabelPath.filter(Boolean);
  if (path.length > 0) {
    return path;
  }
  const labelPath = [row.categoryPrimaryLabel, row.categorySubLabel, row.categoryThirdLabel].filter(Boolean);
  if (labelPath.length > 0) {
    return labelPath;
  }
  const fallback = categoryPathText(row);
  return fallback === "-" ? [] : [fallback];
}

type RelationChip = {
  label: string;
  tone: "outline" | "closure";
};

function workbenchRelationChips(row: TurnoverLedgerGroupedRow, isFlow: boolean) {
  const chips: RelationChip[] = [];
  if (row.linkedOa) {
    chips.push({ label: "已关联 OA", tone: "outline" });
  }
  if (row.linkedInvoice) {
    chips.push({ label: "已关联 发票", tone: "outline" });
  }
  if (isFlow && row.cashClosureLinked) {
    chips.push({ label: "收支闭环", tone: "closure" });
  }
  return chips;
}

function workbenchRelationGroupLabel(group: TurnoverLedgerGroup) {
  const rows = runtimeGroup(group).flowRows ?? [];
  if (rows.length === 0) {
    const summaryRow = runtimeGroup(group).summaryRow;
    return summaryRow?.cashClosureLinked ? "收支闭环" : "";
  }
  return rows.some((row) => row.cashClosureLinked) ? "收支闭环" : "";
}

function directionKey(direction: TurnoverLedgerDirection | null | undefined): "income" | "expense" | "neutral" {
  if (direction === "income") {
    return "income";
  }
  if (direction === "expense") {
    return "expense";
  }
  return "neutral";
}

function amountNumber(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function flowDirectionKey(row: TurnoverLedgerGroupedRow): "income" | "expense" | "neutral" {
  const explicitDirection = directionKey(runtimeRow(row).flowDirection);
  if (explicitDirection !== "neutral") {
    return explicitDirection;
  }
  if (amountNumber(row.borrowAmount) > 0 && amountNumber(row.repaymentAmount) <= 0) {
    return "income";
  }
  if (amountNumber(row.repaymentAmount) > 0 && amountNumber(row.borrowAmount) <= 0) {
    return "expense";
  }
  return "neutral";
}

function rateText(row: TurnoverLedgerGroupedRow) {
  if (row.interestRateType === "none") {
    return "不计息";
  }
  const parsed = Number(row.interestRateValue);
  const percentage = Number.isFinite(parsed)
    ? `${(parsed * 100).toLocaleString("en-US", { maximumFractionDigits: 4 })}%`
    : row.interestRateValue || "-";
  if (row.interestRateType === "annual") {
    return `年息 ${percentage}`;
  }
  if (row.interestRateType === "monthly") {
    return `月息 ${percentage}`;
  }
  return percentage;
}

function runtimeGroup(group: TurnoverLedgerGroup) {
  return group as RuntimeGroup;
}

function runtimeRow(row: TurnoverLedgerGroupedRow) {
  return row as RuntimeGroupedRow;
}

function flowDisplayId(row: TurnoverLedgerGroupedRow) {
  return runtimeRow(row).sourceBankRowId || runtimeRow(row).flowId || row.bankRowIds[0] || row.relationId || "未知流水";
}

function resolveRows(group: TurnoverLedgerGroup) {
  const compatibleGroup = runtimeGroup(group);
  const rows = Array.isArray(group.rows) ? group.rows : [];
  const summaryRow = compatibleGroup.summaryRow
    ?? rows.find((row) => runtimeRow(row).rowKind === "summary")
    ?? rows[0]
    ?? null;
  const explicitFlowRows = Array.isArray(compatibleGroup.flowRows) && compatibleGroup.flowRows.length > 0
    ? compatibleGroup.flowRows
    : null;
  const flowRows = explicitFlowRows
    ?? rows.filter((row) => row !== summaryRow && runtimeRow(row).rowKind === "flow");

  return { summaryRow, flowRows };
}

function isFilledAmount(value: string | null | undefined) {
  return typeof value === "string" && value.trim() !== "";
}

function BalanceLine({
  label,
  amount,
  tone,
}: {
  label: string;
  amount: string;
  tone: "repayment" | "collection" | "closed";
}) {
  return (
    <span className={`turnover-ledger-balance-line turnover-ledger-balance-line--${tone}`}>
      <span className="turnover-ledger-balance-line__label">
        {label}：
      </span>
      <span className="turnover-ledger-balance-line__amount">
        {formatMoney(amount)}
      </span>
    </span>
  );
}

function BalanceLines({ group }: { group: TurnoverLedgerGroup }) {
  const compatibleGroup = runtimeGroup(group);
  const repaymentAmount = compatibleGroup.pendingRepaymentAmount;
  const collectionAmount = compatibleGroup.pendingCollectionAmount;
  const closedAmount = compatibleGroup.closedAmount;
  const lines: Array<{ label: string; amount: string; tone: "repayment" | "collection" | "closed" }> = [];

  if (group.pendingDirection === "mixed") {
    if (isFilledAmount(repaymentAmount) || isFilledAmount(collectionAmount)) {
      if (isFilledAmount(repaymentAmount)) {
        lines.push({ label: "待还款合计", amount: repaymentAmount, tone: "repayment" });
      }
      if (isFilledAmount(collectionAmount)) {
        lines.push({ label: "待收款合计", amount: collectionAmount, tone: "collection" });
      }
      return <BalanceLineStack lines={lines} />;
    }
    return <BalanceLine label="混合余额合计" amount={group.pendingAmount} tone="repayment" />;
  }

  if (group.pendingDirection === "collection") {
    return <BalanceLine label="待收款合计" amount={collectionAmount ?? group.pendingAmount} tone="collection" />;
  }
  if (group.pendingDirection === "repayment") {
    return <BalanceLine label="待还款合计" amount={repaymentAmount ?? group.pendingAmount} tone="repayment" />;
  }
  return <BalanceLine label="已闭合合计" amount={closedAmount ?? group.pendingAmount} tone="closed" />;
}

function BalanceLineStack({ lines }: { lines: Array<{ label: string; amount: string; tone: "repayment" | "collection" | "closed" }> }) {
  return (
    <span className="turnover-ledger-balance-stack">
      {lines.map((line) => (
        <BalanceLine key={line.label} label={line.label} amount={line.amount} tone={line.tone} />
      ))}
    </span>
  );
}

function AmountBlock({
  amount,
  date,
  direction,
  testId,
  showDate = true,
  categoryLabels = [],
  bankAccountLabels = [],
}: {
  amount: string;
  date: string | null;
  direction: TurnoverLedgerDirection;
  testId: string;
  showDate?: boolean;
  categoryLabels?: string[];
  bankAccountLabels?: string[];
}) {
  const tone = directionKey(direction);
  const directionTag = tone === "income" ? "收" : tone === "expense" ? "支" : "";
  return (
    <span className="turnover-ledger-amount-stack">
      <span
        data-testid={testId}
        className={`turnover-amount-${tone}`}
        aria-label={directionTag ? `${directionTag} ${formatMoney(amount)}` : formatMoney(amount)}
      >
        {directionTag ? (
          <span className={`turnover-ledger-direction-tag turnover-ledger-direction-tag--${tone}`}>
            {directionTag}
          </span>
        ) : null}
        <span>{formatMoney(amount)}</span>
      </span>
      {showDate ? <span className="turnover-ledger-chip turnover-ledger-chip--outline">{formatNullable(date)}</span> : null}
      {categoryLabels.length > 0 ? (
        <span className="turnover-ledger-chip-row">
          {categoryLabels.map((label) => (
            <span className="turnover-ledger-chip turnover-ledger-chip--outline turnover-ledger-chip--compact" key={label}>
              {label}
            </span>
          ))}
        </span>
      ) : null}
      {bankAccountLabels.length > 0 ? (
        <span className="turnover-ledger-chip-row">
          {bankAccountLabels.map((label) => (
            <span className="turnover-ledger-chip turnover-ledger-chip--filled turnover-ledger-chip--compact" key={label}>
              {label}
            </span>
          ))}
        </span>
      ) : null}
    </span>
  );
}

function EmptyAmountBlock({ testId }: { testId: string }) {
  return (
    <span className="turnover-ledger-amount-stack">
      <span
        data-testid={testId}
        className="turnover-amount-empty"
      >
        -
      </span>
      <span className="turnover-ledger-chip turnover-ledger-chip--outline">-</span>
    </span>
  );
}

function BalanceBlock({
  group,
  expanded,
  canExpand,
  onToggle,
}: {
  group: TurnoverLedgerGroup;
  expanded: boolean;
  canExpand: boolean;
  onToggle: () => void;
}) {
  const labelName = group.counterpartyName || "未命名对方";
  const relationLabel = workbenchRelationGroupLabel(group);
  return (
    <span className="turnover-ledger-balance-block">
      <span className="turnover-ledger-balance-block__row">
        {canExpand ? (
          <button
            className="turnover-ledger-expand-button"
            onClick={onToggle}
            aria-label={`${expanded ? "收起" : "展开"} ${labelName} 流水明细`}
            type="button"
          >
            <span aria-hidden="true">{expanded ? "v" : ">"}</span>
          </button>
        ) : (
          <span className="turnover-ledger-expand-button-placeholder" />
        )}
        <span className="turnover-ledger-balance-block__content">
          <span className="turnover-ledger-balance-block__name">
            {group.counterpartyName || "-"}
          </span>
          <span className="turnover-ledger-chip turnover-ledger-chip--filled turnover-ledger-chip--family">
            {group.familyLabel || group.family || "-"}
          </span>
          {relationLabel ? (
            <span className="turnover-ledger-chip turnover-ledger-chip--outline turnover-ledger-chip--compact">
              {relationLabel}
            </span>
          ) : null}
          <BalanceLines group={group} />
        </span>
      </span>
    </span>
  );
}

function RowCells({
  row,
  rowKind,
  onEdit,
  actionsDisabled,
}: {
  row: TurnoverLedgerGroupedRow;
  rowKind: "summary" | "flow";
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
  actionsDisabled: boolean;
}) {
  const isFlow = rowKind === "flow";
  const hasBorrowAmount = amountNumber(row.borrowAmount) > 0;
  const hasRepaymentAmount = amountNumber(row.repaymentAmount) > 0;
  const metadata = isFlow
    ? {
        categoryLabels: categoryChipLabels(row),
        bankAccountLabels: row.bankAccountLabels,
      }
    : {
        categoryLabels: [],
        bankAccountLabels: [],
      };
  const relationChips = workbenchRelationChips(row, isFlow);
  return (
    <>
      <td>
        <span className="turnover-ledger-cell-stack">
          {isFlow && !hasBorrowAmount ? (
            <EmptyAmountBlock testId={`amount-empty-${row.relationId}-borrow`} />
          ) : (
            <AmountBlock
              amount={row.borrowAmount}
              date={row.borrowDate}
              direction={row.borrowDirection || "income"}
              testId={`amount-${directionKey(row.borrowDirection || "income")}-${row.relationId}-borrow`}
              showDate={isFlow}
              {...(hasBorrowAmount ? metadata : {})}
            />
          )}
        </span>
      </td>
      <td>
        {isFlow && !hasRepaymentAmount ? (
          <EmptyAmountBlock testId={`amount-empty-${row.relationId}-repayment`} />
        ) : (
          <AmountBlock
            amount={row.repaymentAmount}
            date={row.repaymentDate}
            direction={row.repaymentDirection || "expense"}
            testId={`amount-${directionKey(row.repaymentDirection || "expense")}-${row.relationId}-repayment`}
            showDate={isFlow}
            {...(hasRepaymentAmount ? metadata : {})}
          />
        )}
      </td>
      <td>
        <span className="turnover-ledger-cell-stack">
          <span>{formatNullable(isFlow ? row.repaymentRemark : "")}</span>
          {relationChips.map((chip) => (
            <span
              className={`turnover-ledger-chip turnover-ledger-chip--compact ${chip.tone === "closure" ? "turnover-ledger-chip--closure" : "turnover-ledger-chip--outline"}`}
              key={chip.label}
              title={[row.cashClosureCaseId, ...row.workbenchRelationCaseIds].filter(Boolean).join("、")}
            >
              {chip.label}
            </span>
          ))}
        </span>
      </td>
      <td>
        <span className="turnover-ledger-interest-cell">
          <span className="turnover-ledger-interest-cell__amount">
            {formatMoney(row.interestPaidAmount)}
          </span>
          <span className="turnover-ledger-interest-cell__rate">
            {rateText(row)}
          </span>
        </span>
      </td>
      <td>{formatNullable(row.loanDays)}</td>
      <td>{row.accruedInterest ? formatMoney(row.accruedInterest) : "-"}</td>
      <td>
        <span className="turnover-ledger-cell-stack">
          <span>{formatNullable(row.interestPaidDate)}</span>
          <span className="turnover-ledger-chip turnover-ledger-chip--outline">
            {formatNullable(row.interestPaymentMethod)}
          </span>
        </span>
      </td>
      <td>{formatNullable(row.note)}</td>
      <td>
        {isFlow ? (
          <button
            className="turnover-ledger-table-button"
            disabled={actionsDisabled}
            onClick={() => onEdit(row)}
            aria-label={`编辑流水 ${flowDisplayId(row)}`}
            type="button"
          >
            编辑
          </button>
        ) : null}
      </td>
    </>
  );
}

export default function TurnoverLedgerGroupedTable({
  groups,
  loading,
  onEdit,
  selectedFlowRowIds = new Set<string>(),
  onToggleFlowSelection,
  tableWrapRef,
  actionsDisabled = false,
}: {
  groups: TurnoverLedgerGroup[];
  loading: boolean;
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
  selectedFlowRowIds?: Set<string>;
  onToggleFlowSelection?: (group: TurnoverLedgerGroup, row: TurnoverLedgerGroupedRow) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  actionsDisabled?: boolean;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const hasRows = groups.some((group) => resolveRows(group).summaryRow !== null);
  return (
    <div className="turnover-ledger-table-wrap" ref={tableWrapRef}>
      <table className="turnover-ledger-table" aria-label="往来款左右双栏台账">
        <thead>
          <tr>
            <th className="turnover-sticky-left-header" scope="col">
              对方户名
            </th>
            <th className="turnover-ledger-table__check" scope="col">选择</th>
            <th className="turnover-ledger-table__occurred" scope="col">往来发生</th>
            <th className="turnover-ledger-table__settled" scope="col">结清发生</th>
            <th className="turnover-ledger-table__remark" scope="col">还款备注</th>
            <th className="turnover-ledger-table__interest" scope="col">利息额 / 年息或月息</th>
            <th className="turnover-ledger-table__days" scope="col">借款天数</th>
            <th className="turnover-ledger-table__interest-due" scope="col">应还利息</th>
            <th className="turnover-ledger-table__paid" scope="col">还利息日期 / 方式</th>
            <th className="turnover-ledger-table__note" scope="col">备注</th>
            <th className="turnover-ledger-table__action" scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className="turnover-ledger-table__empty" colSpan={11}>
                正在加载往来款台账
              </td>
            </tr>
          ) : null}
          {!loading && !hasRows ? (
            <tr>
              <td className="turnover-ledger-table__empty" colSpan={11}>
                暂无往来款台账
              </td>
            </tr>
          ) : null}
          {!loading
            ? groups.flatMap((group, groupIndex) => {
                const { summaryRow, flowRows } = resolveRows(group);
                if (!summaryRow) {
                  return [];
                }
                const expanded = Boolean(expandedGroups[group.groupId]);
                const visibleFlowRows = expanded ? flowRows : [];
                const rowSpan = 1 + visibleFlowRows.length;
                const toggleGroup = () => {
                  setExpandedGroups((current) => ({
                    ...current,
                    [group.groupId]: !current[group.groupId],
                  }));
                };
                const summary = (
                  <tr
                    key={`${group.groupId}:summary:${summaryRow.relationId}`}
                    data-testid={`turnover-row-${summaryRow.relationId}`}
                    className="turnover-summary-row turnover-group-start-row"
                  >
                    <td
                      data-testid={`turnover-group-cell-${group.groupId}`}
                      rowSpan={rowSpan}
                      className="turnover-sticky-left-cell"
                    >
                      <BalanceBlock
                        group={group}
                        expanded={expanded}
                        canExpand={flowRows.length > 0}
                        onToggle={toggleGroup}
                      />
                    </td>
                    <td className="turnover-ledger-table__check" />
                    <RowCells
                      row={{ ...summaryRow, counterpartyName: group.counterpartyName, familyLabel: group.familyLabel }}
                      rowKind="summary"
                      onEdit={onEdit}
                      actionsDisabled={actionsDisabled}
                    />
                  </tr>
                );
                const flows = visibleFlowRows.map((row, index) => {
                  const rowTone = flowDirectionKey(row);
                  const rowId = runtimeRow(row).sourceBankRowId || runtimeRow(row).flowId || String(index);
                  const checked = selectedFlowRowIds.has(rowId);
                  return (
                    <tr
                      key={`${group.groupId}:flow:${rowId}`}
                      data-testid={`turnover-flow-row-${row.relationId}-${index}`}
                      className={`turnover-row-${rowTone} turnover-flow-row`}
                    >
                      <td className="turnover-ledger-table__check">
                        <input
                          className="turnover-ledger-checkbox"
                          checked={checked}
                          disabled={actionsDisabled}
                          onChange={() => onToggleFlowSelection?.(group, row)}
                          aria-label={`选择流水 ${rowId}`}
                          type="checkbox"
                        />
                      </td>
                      <RowCells
                        row={{ ...row, counterpartyName: group.counterpartyName, familyLabel: group.familyLabel }}
                        rowKind="flow"
                        onEdit={onEdit}
                        actionsDisabled={actionsDisabled}
                      />
                    </tr>
                  );
                });
                return [summary, ...flows];
              })
            : null}
        </tbody>
      </table>
    </div>
  );
}
