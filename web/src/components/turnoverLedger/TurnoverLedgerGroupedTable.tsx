import { useState } from "react";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import type {
  TurnoverLedgerDirection,
  TurnoverLedgerGroup,
  TurnoverLedgerGroupedRow,
  TurnoverRowTone,
} from "../../features/turnoverLedger/types";

const ROW_TONE_BACKGROUND: Record<TurnoverRowTone, string> = {
  success: "rgba(46, 125, 50, 0.07)",
  warning: "rgba(237, 108, 2, 0.10)",
  info: "rgba(2, 136, 209, 0.07)",
  danger: "rgba(211, 47, 47, 0.08)",
  error: "rgba(211, 47, 47, 0.08)",
  muted: "rgba(97, 97, 97, 0.07)",
};

const AMOUNT_BACKGROUND: Record<"income" | "expense" | "neutral", string> = {
  income: "rgba(46, 125, 50, 0.14)",
  expense: "rgba(239, 108, 0, 0.15)",
  neutral: "rgba(117, 117, 117, 0.10)",
};

const LEFT_COLUMN_WIDTH = 240;
const LEFT_HEADER_BACKGROUND = "#f5f7fa";
const LEFT_CELL_BACKGROUND: Record<TurnoverRowTone, string> = {
  success: "#eef7ee",
  warning: "#fff4e5",
  info: "#edf6fb",
  danger: "#fdecec",
  error: "#fdecec",
  muted: "#f5f5f5",
};
const FLOW_ROW_BACKGROUND: Record<"income" | "expense" | "neutral", string> = {
  income: "#eef8f0",
  expense: "#fff5eb",
  neutral: "#f3f5fb",
};
const FLOW_ROW_HOVER_BACKGROUND: Record<"income" | "expense" | "neutral", string> = {
  income: "#e4f3e7",
  expense: "#ffeddd",
  neutral: "#eceff8",
};

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

function normalizedTone(tone: TurnoverRowTone | string | null | undefined): TurnoverRowTone {
  if (tone === "success" || tone === "warning" || tone === "info" || tone === "danger" || tone === "error" || tone === "muted") {
    return tone;
  }
  return "muted";
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
  color,
}: {
  label: string;
  amount: string;
  color: string;
}) {
  return (
    <Typography variant="body2" fontWeight={800} sx={{ color }}>
      {label}：{formatMoney(amount)}
    </Typography>
  );
}

function BalanceLines({ group }: { group: TurnoverLedgerGroup }) {
  const compatibleGroup = runtimeGroup(group);
  const repaymentAmount = compatibleGroup.pendingRepaymentAmount;
  const collectionAmount = compatibleGroup.pendingCollectionAmount;
  const closedAmount = compatibleGroup.closedAmount;

  if (group.pendingDirection === "mixed") {
    if (isFilledAmount(repaymentAmount) || isFilledAmount(collectionAmount)) {
      return (
        <>
          {isFilledAmount(repaymentAmount) ? (
            <BalanceLine label="待还款合计" amount={repaymentAmount} color="warning.dark" />
          ) : null}
          {isFilledAmount(collectionAmount) ? (
            <BalanceLine label="待收款合计" amount={collectionAmount} color="success.dark" />
          ) : null}
        </>
      );
    }
    return <BalanceLine label="混合余额合计" amount={group.pendingAmount} color="warning.dark" />;
  }

  if (group.pendingDirection === "collection") {
    return <BalanceLine label="待收款合计" amount={collectionAmount ?? group.pendingAmount} color="success.dark" />;
  }
  if (group.pendingDirection === "repayment") {
    return <BalanceLine label="待还款合计" amount={repaymentAmount ?? group.pendingAmount} color="warning.dark" />;
  }
  return <BalanceLine label="已闭合合计" amount={closedAmount ?? group.pendingAmount} color="text.secondary" />;
}

function AmountBlock({
  amount,
  date,
  direction,
  testId,
}: {
  amount: string;
  date: string | null;
  direction: TurnoverLedgerDirection;
  testId: string;
}) {
  const tone = directionKey(direction);
  return (
    <Stack spacing={0.5} alignItems="flex-start">
      <Box
        data-testid={testId}
        className={`turnover-amount-${tone}`}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "flex-end",
          minWidth: 88,
          px: 0.75,
          py: 0.35,
          borderRadius: 0.75,
          fontWeight: 800,
          backgroundColor: AMOUNT_BACKGROUND[tone],
          color: tone === "income" ? "success.dark" : tone === "expense" ? "warning.dark" : "text.primary",
        }}
      >
        {formatMoney(amount)}
      </Box>
      <Chip size="small" variant="outlined" label={formatNullable(date)} />
    </Stack>
  );
}

function EmptyAmountBlock({ testId }: { testId: string }) {
  return (
    <Stack spacing={0.5} alignItems="flex-start">
      <Box
        data-testid={testId}
        className="turnover-amount-empty"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          minWidth: 88,
          px: 0.75,
          py: 0.35,
          borderRadius: 0.75,
          fontWeight: 800,
          backgroundColor: AMOUNT_BACKGROUND.neutral,
          color: "text.secondary",
        }}
      >
        -
      </Box>
      <Chip size="small" variant="outlined" label="-" />
    </Stack>
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
  return (
    <Stack spacing={0.75} alignItems="flex-start">
      <Stack direction="row" spacing={0.75} alignItems="flex-start" sx={{ width: "100%" }}>
        {canExpand ? (
          <IconButton
            size="small"
            onClick={onToggle}
            aria-label={`${expanded ? "收起" : "展开"} ${labelName} 流水明细`}
            sx={{ mt: -0.25, flex: "0 0 auto" }}
          >
            {expanded ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
          </IconButton>
        ) : (
          <Box sx={{ width: 32, flex: "0 0 auto" }} />
        )}
        <Stack spacing={0.75} sx={{ minWidth: 0 }}>
          <Typography variant="body2" fontWeight={900} sx={{ wordBreak: "break-word" }}>
            {group.counterpartyName || "-"}
          </Typography>
          <Chip size="small" label={group.familyLabel || group.family || "-"} sx={{ alignSelf: "flex-start" }} />
          <BalanceLines group={group} />
        </Stack>
      </Stack>
    </Stack>
  );
}

function RowCells({
  row,
  rowKind,
  onEdit,
}: {
  row: TurnoverLedgerGroupedRow;
  rowKind: "summary" | "flow";
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
}) {
  const isFlow = rowKind === "flow";
  const flowDirection = isFlow ? flowDirectionKey(row) : "neutral";
  return (
    <>
      <TableCell>
        <Stack spacing={0.75} alignItems="flex-start">
          {isFlow ? <Chip size="small" label="流水" color="info" variant="outlined" /> : null}
          {isFlow && flowDirection !== "income" ? (
            <EmptyAmountBlock testId={`amount-empty-${row.relationId}-borrow`} />
          ) : (
            <AmountBlock
              amount={row.borrowAmount}
              date={row.borrowDate}
              direction={isFlow ? "income" : row.borrowDirection}
              testId={`amount-${directionKey(isFlow ? "income" : row.borrowDirection)}-${row.relationId}-borrow`}
            />
          )}
        </Stack>
      </TableCell>
      <TableCell>
        {isFlow && flowDirection !== "expense" ? (
          <EmptyAmountBlock testId={`amount-empty-${row.relationId}-repayment`} />
        ) : (
          <AmountBlock
            amount={row.repaymentAmount}
            date={row.repaymentDate}
            direction={isFlow ? "expense" : row.repaymentDirection}
            testId={`amount-${directionKey(isFlow ? "expense" : row.repaymentDirection)}-${row.relationId}-repayment`}
          />
        )}
      </TableCell>
      <TableCell>{formatNullable(row.counterpartyBankName)}</TableCell>
      <TableCell>{formatNullable(row.repaymentRemark)}</TableCell>
      <TableCell>
        <Stack spacing={0.5}>
          <Typography variant="body2" fontWeight={800}>
            {formatMoney(row.interestPaidAmount)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {rateText(row)}
          </Typography>
        </Stack>
      </TableCell>
      <TableCell>{formatNullable(row.loanDays)}</TableCell>
      <TableCell>{row.accruedInterest ? formatMoney(row.accruedInterest) : "-"}</TableCell>
      <TableCell>
        <Stack spacing={0.5} alignItems="flex-start">
          <Typography variant="body2">{formatNullable(row.interestPaidDate)}</Typography>
          <Chip size="small" variant="outlined" label={formatNullable(row.interestPaymentMethod)} />
        </Stack>
      </TableCell>
      <TableCell>{formatNullable(row.note)}</TableCell>
      <TableCell>
        <Button
          size="small"
          variant="outlined"
          onClick={() => onEdit(row)}
          aria-label={`${isFlow ? "编辑流水" : "编辑"} ${row.relationId}`}
        >
          编辑
        </Button>
      </TableCell>
    </>
  );
}

export default function TurnoverLedgerGroupedTable({
  groups,
  loading,
  onEdit,
}: {
  groups: TurnoverLedgerGroup[];
  loading: boolean;
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const hasRows = groups.some((group) => resolveRows(group).summaryRow !== null);
  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 640, overflow: "auto", borderRadius: 1 }}>
      <Table stickyHeader size="small" aria-label="往来款左右双栏台账" sx={{ minWidth: 1180, tableLayout: "fixed" }}>
        <TableHead>
          <TableRow>
            <TableCell
              className="turnover-sticky-left-header"
              sx={{
                width: LEFT_COLUMN_WIDTH,
                minWidth: LEFT_COLUMN_WIDTH,
                fontWeight: 900,
                left: 0,
                position: "sticky",
                zIndex: 5,
                backgroundColor: LEFT_HEADER_BACKGROUND,
                borderRight: "1px solid",
                borderRightColor: "divider",
              }}
            >
              对方户名
            </TableCell>
            <TableCell sx={{ width: 132, fontWeight: 900 }}>借款金额 / 借款日</TableCell>
            <TableCell sx={{ width: 132, fontWeight: 900 }}>还款金额 / 还款日</TableCell>
            <TableCell sx={{ width: 130, fontWeight: 900 }}>开户机构</TableCell>
            <TableCell sx={{ width: 138, fontWeight: 900 }}>还款备注</TableCell>
            <TableCell sx={{ width: 132, fontWeight: 900 }}>利息额 / 年息或月息</TableCell>
            <TableCell sx={{ width: 86, fontWeight: 900 }}>借款天数</TableCell>
            <TableCell sx={{ width: 104, fontWeight: 900 }}>应还利息</TableCell>
            <TableCell sx={{ width: 132, fontWeight: 900 }}>还利息日期 / 方式</TableCell>
            <TableCell sx={{ width: 150, fontWeight: 900 }}>备注</TableCell>
            <TableCell sx={{ width: 78, fontWeight: 900 }}>操作</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={11} align="center" sx={{ py: 8 }}>
                正在加载往来款台账
              </TableCell>
            </TableRow>
          ) : null}
          {!loading && !hasRows ? (
            <TableRow>
              <TableCell colSpan={11} align="center" sx={{ py: 8 }}>
                暂无往来款台账
              </TableCell>
            </TableRow>
          ) : null}
          {!loading
            ? groups.flatMap((group) => {
                const { summaryRow, flowRows } = resolveRows(group);
                if (!summaryRow) {
                  return [];
                }
                const expanded = Boolean(expandedGroups[group.groupId]);
                const visibleFlowRows = expanded ? flowRows : [];
                const groupTone = normalizedTone(group.groupTone);
                const summaryTone = normalizedTone(summaryRow.rowTone);
                const rowSpan = 1 + visibleFlowRows.length;
                const toggleGroup = () => {
                  setExpandedGroups((current) => ({
                    ...current,
                    [group.groupId]: !current[group.groupId],
                  }));
                };
                const summary = (
                  <TableRow
                    key={`${group.groupId}:summary:${summaryRow.relationId}`}
                    data-testid={`turnover-row-${summaryRow.relationId}`}
                    className={`turnover-row-${summaryTone}`}
                    hover
                    sx={{
                      backgroundColor: ROW_TONE_BACKGROUND[summaryTone],
                      "&:hover": { backgroundColor: ROW_TONE_BACKGROUND[summaryTone] },
                      "& td": { verticalAlign: "top" },
                    }}
                  >
                    <TableCell
                      data-testid={`turnover-group-cell-${group.groupId}`}
                      rowSpan={rowSpan}
                      className="turnover-sticky-left-cell"
                      sx={{
                        position: "sticky",
                        left: 0,
                        zIndex: 4,
                        width: LEFT_COLUMN_WIDTH,
                        minWidth: LEFT_COLUMN_WIDTH,
                        backgroundColor: LEFT_CELL_BACKGROUND[groupTone],
                        borderRight: "1px solid",
                        borderRightColor: "divider",
                      }}
                    >
                      <BalanceBlock
                        group={group}
                        expanded={expanded}
                        canExpand={flowRows.length > 0}
                        onToggle={toggleGroup}
                      />
                    </TableCell>
                    <RowCells row={summaryRow} rowKind="summary" onEdit={onEdit} />
                  </TableRow>
                );
                const flows = visibleFlowRows.map((row, index) => {
                  const rowTone = flowDirectionKey(row);
                  const rowId = runtimeRow(row).sourceBankRowId || runtimeRow(row).flowId || String(index);
                  return (
                    <TableRow
                      key={`${group.groupId}:flow:${rowId}`}
                      data-testid={`turnover-flow-row-${row.relationId}-${index}`}
                      className={`turnover-row-${rowTone} turnover-flow-row`}
                      hover
                      sx={{
                        backgroundColor: FLOW_ROW_BACKGROUND[rowTone],
                        "&:hover": { backgroundColor: FLOW_ROW_HOVER_BACKGROUND[rowTone] },
                        "& td": { verticalAlign: "top" },
                      }}
                    >
                      <RowCells row={row} rowKind="flow" onEdit={onEdit} />
                    </TableRow>
                  );
                });
                return [summary, ...flows];
              })
            : null}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
