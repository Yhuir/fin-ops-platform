import { Button, Checkbox } from "@heroui/react";
import { useState, type MutableRefObject } from "react";

import type {
  TurnoverLedgerDirection,
  TurnoverLedgerGroup,
  TurnoverLedgerGroupedRow,
} from "../../features/turnoverLedger/types";
import { formatMoney } from "../../features/money";
import {
  EmptyValue,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";

export { formatMoney };

type RuntimeGroupedRow = TurnoverLedgerGroupedRow & {
  rowKind?: "summary" | "lot" | string;
  lotId?: string;
  balanceAmount?: string;
  flowAmount?: string;
};

type RuntimeGroup = TurnoverLedgerGroup & {
  summaryRow?: TurnoverLedgerGroupedRow;
  flowRows?: TurnoverLedgerGroupedRow[];
  lotRows?: TurnoverLedgerGroupedRow[];
  pendingRepaymentAmount?: string;
  pendingCollectionAmount?: string;
  closedAmount?: string;
};

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
  if (isFlow && row.cashPairLinked && !row.cashClosureLinked) {
    chips.push({ label: "已配对未结清", tone: "outline" });
  }
  if (isFlow && row.cashClosureLinked) {
    chips.push({ label: "收支闭环", tone: "closure" });
  }
  return chips;
}

function workbenchRelationGroupLabel(group: TurnoverLedgerGroup) {
  if (group.cashClosureLinked) {
    return "收支闭环";
  }
  return group.pairedUnsettled ? "已配对未结清" : "";
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

function flowAccessibleName(row: TurnoverLedgerGroupedRow) {
  const direction = flowDirectionKey(row);
  const date = row.borrowDate || row.repaymentDate || "时间未知";
  const amount = runtimeRow(row).flowAmount || (direction === "income" ? row.borrowAmount : row.repaymentAmount);
  return `${row.counterpartyName || "未知对方"} ${date} ${direction === "income" ? "收入" : direction === "expense" ? "支出" : "流水"} ${formatMoney(amount)}`;
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
  return group.cashClosureLinked
    ? <BalanceLine label="已闭合合计" amount="0.00" tone="closed" />
    : null;
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
      <FinanceTableCell columnRole="amount">
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
      </FinanceTableCell>
      <FinanceTableCell columnRole="amount">
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
      </FinanceTableCell>
      <FinanceTableCell columnRole="description">
        <span className="turnover-ledger-cell-stack">
          <span>{formatNullable(isFlow ? row.repaymentRemark : "")}</span>
          {relationChips.map((chip) => (
            <span
              className={`turnover-ledger-chip turnover-ledger-chip--compact ${chip.tone === "closure" ? "turnover-ledger-chip--closure" : "turnover-ledger-chip--outline"}`}
              key={chip.label}
            >
              {chip.label}
            </span>
          ))}
        </span>
      </FinanceTableCell>
      <FinanceTableCell columnRole="amount">
        <span className="turnover-ledger-interest-cell">
          <span className="turnover-ledger-interest-cell__amount">
            {formatMoney(row.interestPaidAmount)}
          </span>
          <span className="turnover-ledger-interest-cell__rate">
            {rateText(row)}
          </span>
        </span>
      </FinanceTableCell>
      <FinanceTableCell columnRole="quantity">{formatNullable(row.loanDays)}</FinanceTableCell>
      <FinanceTableCell columnRole="amount">{row.accruedInterest ? formatMoney(row.accruedInterest) : "-"}</FinanceTableCell>
      <FinanceTableCell columnRole="date">
        <span className="turnover-ledger-cell-stack">
          <span>{formatNullable(row.interestPaidDate)}</span>
          <span className="turnover-ledger-chip turnover-ledger-chip--outline">
            {formatNullable(row.interestPaymentMethod)}
          </span>
        </span>
      </FinanceTableCell>
      <FinanceTableCell columnRole="description">{formatNullable(row.note)}</FinanceTableCell>
      <FinanceTableCell columnRole="action">
        {isFlow ? (
          <Button
            className="turnover-ledger-table-button"
            isDisabled={actionsDisabled}
            onPress={() => onEdit(row)}
            aria-label={`编辑流水 ${flowAccessibleName(row)}`}
            size="sm"
            variant="tertiary"
          >
            编辑
          </Button>
        ) : null}
      </FinanceTableCell>
    </>
  );
}

export default function TurnoverLedgerGroupedTable({
  groups,
  loading,
  showEmptyState = true,
  onEdit,
  selectedFlowRowIds = new Set<string>(),
  onToggleFlowSelection,
  tableWrapRef,
  actionsDisabled = false,
}: {
  groups: TurnoverLedgerGroup[];
  loading: boolean;
  showEmptyState?: boolean;
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
  selectedFlowRowIds?: Set<string>;
  onToggleFlowSelection?: (group: TurnoverLedgerGroup, row: TurnoverLedgerGroupedRow) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  actionsDisabled?: boolean;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const hasRows = groups.some((group) => resolveRows(group).summaryRow !== null);
  return (
    <FinanceTable ariaLabel="往来款左右双栏台账" className="turnover-ledger-table turnover-ledger-table-wrap" minWidth={1320} scrollMode="contained" scrollRef={tableWrapRef}>
        <FinanceTableHeader>
            <FinanceTableColumn className="turnover-sticky-left-header" columnRole="identity" isRowHeader>对方户名</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__check" columnRole="selection">选择</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__occurred" columnRole="amount">往来发生</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__settled" columnRole="amount">结清发生</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__remark" columnRole="description">还款备注</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__interest" columnRole="amount">利息额 / 年息或月息</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__days" columnRole="quantity">借款天数</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__interest-due" columnRole="amount">应还利息</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__paid" columnRole="date">还利息日期 / 方式</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__note" columnRole="description">备注</FinanceTableColumn>
            <FinanceTableColumn className="turnover-ledger-table__action" columnRole="action">操作</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          {loading ? (
            <FinanceTableRow id="turnover-loading">
              <FinanceTableCell className="turnover-ledger-table__empty" columnRole="identity">正在加载往来款台账</FinanceTableCell>
              {Array.from({ length: 10 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
            </FinanceTableRow>
          ) : null}
          {!loading && showEmptyState && !hasRows ? (
            <FinanceTableRow id="turnover-empty">
              <FinanceTableCell className="turnover-ledger-table__empty" columnRole="identity">暂无往来款台账</FinanceTableCell>
              {Array.from({ length: 10 }, (_, index) => <FinanceTableCell columnRole="description" key={index}><EmptyValue /></FinanceTableCell>)}
            </FinanceTableRow>
          ) : null}
          {!loading
            ? groups.flatMap((group, groupIndex) => {
                const { summaryRow, flowRows } = resolveRows(group);
                if (!summaryRow) {
                  return [];
                }
                const expanded = Boolean(expandedGroups[group.groupId]);
                const visibleFlowRows = expanded ? flowRows : [];
                const toggleGroup = () => {
                  setExpandedGroups((current) => ({
                    ...current,
                    [group.groupId]: !current[group.groupId],
                  }));
                };
                const summary = (
                  <FinanceTableRow
                    key={`${group.groupId}:summary:${summaryRow.relationId}`}
                    className="turnover-summary-row turnover-group-start-row"
                    dataTestId={`turnover-row-${summaryRow.relationId}`}
                    id={`turnover-group-${group.groupId}`}
                  >
                    <FinanceTableCell className="turnover-sticky-left-cell" columnRole="identity" dataTestId={`turnover-group-cell-${group.groupId}`}>
                      <BalanceBlock
                        group={group}
                        expanded={expanded}
                        canExpand={flowRows.length > 0}
                        onToggle={toggleGroup}
                      />
                    </FinanceTableCell>
                    <FinanceTableCell className="turnover-ledger-table__check" columnRole="selection"><EmptyValue /></FinanceTableCell>
                    <RowCells
                      row={{ ...summaryRow, counterpartyName: group.counterpartyName, familyLabel: group.familyLabel }}
                      rowKind="summary"
                      onEdit={onEdit}
                      actionsDisabled={actionsDisabled}
                    />
                  </FinanceTableRow>
                );
                const flows = visibleFlowRows.map((row, index) => {
                  const rowTone = flowDirectionKey(row);
                  const rowId = runtimeRow(row).sourceBankRowId || runtimeRow(row).flowId || String(index);
                  const checked = selectedFlowRowIds.has(rowId);
                  return (
                    <FinanceTableRow
                      key={`${group.groupId}:flow:${rowId}`}
                      className={`turnover-row-${rowTone} turnover-flow-row`}
                      dataTestId={`turnover-flow-row-${row.relationId}-${index}`}
                      id={`turnover-flow-row-${group.groupId}-${rowId}`}
                    >
                      <FinanceTableCell className="turnover-sticky-left-cell turnover-sticky-left-cell--flow" columnRole="identity">{group.counterpartyName || <EmptyValue />}</FinanceTableCell>
                      <FinanceTableCell className="turnover-ledger-table__check" columnRole="selection">
                        <Checkbox
                          aria-label={`选择流水 ${flowAccessibleName({ ...row, counterpartyName: group.counterpartyName })}`}
                          isDisabled={actionsDisabled}
                          isSelected={checked}
                          onChange={() => onToggleFlowSelection?.(group, row)}
                        >
                          <Checkbox.Control className="turnover-ledger-checkbox">
                            <Checkbox.Indicator />
                          </Checkbox.Control>
                        </Checkbox>
                      </FinanceTableCell>
                      <RowCells
                        row={{ ...row, counterpartyName: group.counterpartyName, familyLabel: group.familyLabel }}
                        rowKind="flow"
                        onEdit={onEdit}
                        actionsDisabled={actionsDisabled}
                      />
                    </FinanceTableRow>
                  );
                });
                return [summary, ...flows];
              })
            : null}
        </FinanceTableBody>
    </FinanceTable>
  );
}
