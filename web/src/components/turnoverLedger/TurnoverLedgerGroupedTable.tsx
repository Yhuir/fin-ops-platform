import { useState, type MutableRefObject } from "react";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
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
} from "../../features/turnoverLedger/types";

const SUMMARY_ROW_BACKGROUND = "#d8e8f8";

const AMOUNT_BACKGROUND: Record<"income" | "expense" | "neutral", string> = {
  income: "rgba(46, 125, 50, 0.14)",
  expense: "rgba(239, 108, 0, 0.15)",
  neutral: "rgba(117, 117, 117, 0.10)",
};

const LEFT_COLUMN_WIDTH = 176;
const LEFT_HEADER_BACKGROUND = "#f5f7fa";
const FLOW_ROW_BACKGROUND: Record<"income" | "expense" | "neutral", string> = {
  income: "#eef8f0",
  expense: "#fff5eb",
  neutral: "#f3f5fb",
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
    <Stack spacing={0.15} sx={{ color }}>
      <Typography variant="caption" fontWeight={800} sx={{ lineHeight: 1.2 }}>
        {label}：
      </Typography>
      <Typography variant="body2" fontWeight={900} sx={{ lineHeight: 1.25 }}>
        {formatMoney(amount)}
      </Typography>
    </Stack>
  );
}

function BalanceLines({ group }: { group: TurnoverLedgerGroup }) {
  const compatibleGroup = runtimeGroup(group);
  const repaymentAmount = compatibleGroup.pendingRepaymentAmount;
  const collectionAmount = compatibleGroup.pendingCollectionAmount;
  const closedAmount = compatibleGroup.closedAmount;
  const lines: Array<{ label: string; amount: string; color: string }> = [];

  if (group.pendingDirection === "mixed") {
    if (isFilledAmount(repaymentAmount) || isFilledAmount(collectionAmount)) {
      if (isFilledAmount(repaymentAmount)) {
        lines.push({ label: "待还款合计", amount: repaymentAmount, color: "warning.dark" });
      }
      if (isFilledAmount(collectionAmount)) {
        lines.push({ label: "待收款合计", amount: collectionAmount, color: "success.dark" });
      }
      return <BalanceLineStack lines={lines} />;
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

function BalanceLineStack({ lines }: { lines: Array<{ label: string; amount: string; color: string }> }) {
  return (
    <Stack spacing={0.6} divider={<Divider flexItem sx={{ borderColor: "rgba(25, 88, 145, 0.22)" }} />}>
      {lines.map((line) => (
        <BalanceLine key={line.label} label={line.label} amount={line.amount} color={line.color} />
      ))}
    </Stack>
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
    <Stack spacing={0.5} alignItems="flex-start">
      <Box
        data-testid={testId}
        className={`turnover-amount-${tone}`}
        aria-label={directionTag ? `${directionTag} ${formatMoney(amount)}` : formatMoney(amount)}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 0.5,
          minWidth: 78,
          px: 0.75,
          py: 0.25,
          borderRadius: 0.75,
          fontWeight: 800,
          backgroundColor: AMOUNT_BACKGROUND[tone],
          color: tone === "income" ? "success.dark" : tone === "expense" ? "warning.dark" : "text.primary",
        }}
      >
        {directionTag ? (
          <Box
            component="span"
            sx={{
              px: 0.5,
              py: 0.1,
              borderRadius: 0.5,
              fontSize: 11,
              lineHeight: 1.2,
              fontWeight: 900,
              backgroundColor: tone === "income" ? "rgba(46, 125, 50, 0.16)" : "rgba(239, 108, 0, 0.18)",
            }}
          >
            {directionTag}
          </Box>
        ) : null}
        <Box component="span">{formatMoney(amount)}</Box>
      </Box>
      {showDate ? <Chip size="small" variant="outlined" label={formatNullable(date)} sx={{ height: 22 }} /> : null}
      {categoryLabels.length > 0 ? (
        <Stack direction="row" spacing={0.35} useFlexGap flexWrap="wrap">
          {categoryLabels.map((label) => (
            <Chip
              key={label}
              size="small"
              variant="outlined"
              label={label}
              sx={{ height: 20, "& .MuiChip-label": { px: 0.6, fontSize: 11 } }}
            />
          ))}
        </Stack>
      ) : null}
      {bankAccountLabels.length > 0 ? (
        <Stack direction="row" spacing={0.35} useFlexGap flexWrap="wrap">
          {bankAccountLabels.map((label) => (
            <Chip
              key={label}
              size="small"
              variant="filled"
              label={label}
              sx={{ height: 20, "& .MuiChip-label": { px: 0.6, fontSize: 11 } }}
            />
          ))}
        </Stack>
      ) : null}
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
          minWidth: 78,
          px: 0.75,
          py: 0.25,
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
  return (
    <>
      <TableCell>
        <Stack spacing={0.75} alignItems="flex-start">
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
        </Stack>
      </TableCell>
      <TableCell>
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
      </TableCell>
      <TableCell>{formatNullable(isFlow ? row.repaymentRemark : "")}</TableCell>
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
  selectedFlowRowIds = new Set<string>(),
  onToggleFlowSelection,
  tableWrapRef,
}: {
  groups: TurnoverLedgerGroup[];
  loading: boolean;
  onEdit: (row: TurnoverLedgerGroupedRow) => void;
  selectedFlowRowIds?: Set<string>;
  onToggleFlowSelection?: (group: TurnoverLedgerGroup, row: TurnoverLedgerGroupedRow) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const hasRows = groups.some((group) => resolveRows(group).summaryRow !== null);
  return (
    <TableContainer ref={tableWrapRef} component={Paper} variant="outlined" sx={{ maxHeight: 640, overflow: "auto", borderRadius: 1 }}>
      <Table stickyHeader size="small" aria-label="往来款左右双栏台账" sx={{ minWidth: 1080, tableLayout: "fixed" }}>
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
            <TableCell sx={{ width: 52, fontWeight: 900 }} padding="checkbox">选择</TableCell>
            <TableCell sx={{ width: 150, fontWeight: 900 }}>往来发生</TableCell>
            <TableCell sx={{ width: 150, fontWeight: 900 }}>结清发生</TableCell>
            <TableCell sx={{ width: 118, fontWeight: 900 }}>还款备注</TableCell>
            <TableCell sx={{ width: 122, fontWeight: 900 }}>利息额 / 年息或月息</TableCell>
            <TableCell sx={{ width: 76, fontWeight: 900 }}>借款天数</TableCell>
            <TableCell sx={{ width: 92, fontWeight: 900 }}>应还利息</TableCell>
            <TableCell sx={{ width: 118, fontWeight: 900 }}>还利息日期 / 方式</TableCell>
            <TableCell sx={{ width: 126, fontWeight: 900 }}>备注</TableCell>
            <TableCell sx={{ width: 68, fontWeight: 900 }}>操作</TableCell>
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
                  <TableRow
                    key={`${group.groupId}:summary:${summaryRow.relationId}`}
                    data-testid={`turnover-row-${summaryRow.relationId}`}
                    className="turnover-summary-row turnover-group-start-row"
                    sx={{
                      backgroundColor: SUMMARY_ROW_BACKGROUND,
                      "& > td": {
                        verticalAlign: "top",
                        borderTop: groupIndex === 0 ? "1px solid" : "3px solid",
                        borderTopColor: groupIndex === 0 ? "divider" : "#9fb3c8",
                      },
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
                        backgroundColor: SUMMARY_ROW_BACKGROUND,
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
                    <TableCell padding="checkbox">
                      <Checkbox disabled aria-label={`${group.counterpartyName || "未命名对方"} 合计行不可选`} />
                    </TableCell>
                    <RowCells
                      row={summaryRow}
                      rowKind="summary"
                      onEdit={onEdit}
                    />
                  </TableRow>
                );
                const flows = visibleFlowRows.map((row, index) => {
                  const rowTone = flowDirectionKey(row);
                  const rowId = runtimeRow(row).sourceBankRowId || runtimeRow(row).flowId || String(index);
                  const checked = selectedFlowRowIds.has(rowId);
                  return (
                    <TableRow
                      key={`${group.groupId}:flow:${rowId}`}
                      data-testid={`turnover-flow-row-${row.relationId}-${index}`}
                      className={`turnover-row-${rowTone} turnover-flow-row`}
                      sx={{
                        backgroundColor: FLOW_ROW_BACKGROUND[rowTone],
                        "& td": { verticalAlign: "top" },
                      }}
                    >
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={checked}
                          onChange={() => onToggleFlowSelection?.(group, row)}
                          inputProps={{ "aria-label": `选择流水 ${rowId}` }}
                        />
                      </TableCell>
                      <RowCells
                        row={row}
                        rowKind="flow"
                        onEdit={onEdit}
                      />
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
