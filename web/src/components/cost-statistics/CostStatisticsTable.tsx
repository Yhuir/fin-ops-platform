import { Button, Chip } from "@heroui/react";
import { useEffect, useRef, type ReactNode } from "react";

import BankAccountValue from "../BankAccountValue";
import { formatCostAmount } from "../../features/cost-statistics/format";
import {
  EmptyValue,
  FinanceDirectionTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTablePagination,
  FinanceTableRow,
  type FinanceTableColumnRole,
} from "../common/FinanceTable";
import { hasSelectedTextWithin } from "./textSelection";

export type CostStatisticsAmountCell = {
  amount: string;
  direction: string;
  paymentAccountLabel?: string;
  toneByDirection?: boolean;
};

export type CostStatisticsTableColumn<Row> = {
  key: string;
  header: string;
  headerClassName?: string;
  cellClassName?: string;
  width?: number;
  flex?: number;
  getTextValue?: (row: Row) => string;
  render: (row: Row) => ReactNode | CostStatisticsAmountCell;
};

type CostStatisticsTableProps<Row extends object> = {
  ariaLabel: string;
  columns: CostStatisticsTableColumn<Row>[];
  rows: Row[];
  getRowKey: (row: Row, index: number) => string;
  emptyLabel?: string;
  onRowClick?: (row: Row) => void;
  getRowActionLabel?: (row: Row) => string;
  fitContainer?: boolean;
  page: number;
  pageSize: number;
  total: number;
  isPageLoading?: boolean;
  pageError?: string | null;
  onPageChange: (page: number) => void;
  onRetryPage?: () => void;
};

export default function CostStatisticsTable<Row extends object>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  emptyLabel = "当前视图暂无数据。",
  onRowClick,
  getRowActionLabel,
  fitContainer = false,
  page,
  pageSize,
  total,
  isPageLoading = false,
  pageError,
  onPageChange,
  onRetryPage,
}: CostStatisticsTableProps<Row>) {
  const minWidth = columns.reduce((total, column) => total + (column.width ?? (column.flex ? 180 : 140)), 0);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [page]);

  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));

  return (
    <div className="cost-table-shell cost-finance-table-shell">
      <FinanceTable
        ariaLabel={ariaLabel}
        className={fitContainer ? "cost-finance-table cost-finance-table--fit" : "cost-finance-table"}
        minWidth={fitContainer ? "100%" : Math.max(720, minWidth)}
        selectableText
        scrollMode="contained"
        scrollRef={scrollRef}
      >
        <FinanceTableHeader>
          {columns.map((column, columnIndex) => (
            <FinanceTableColumn
              key={column.key}
              className={column.headerClassName}
              columnRole={getColumnRole(column)}
              id={column.key}
              isRowHeader={columnIndex === 0}
            >
              {column.header}
            </FinanceTableColumn>
          ))}
        </FinanceTableHeader>
        <FinanceTableBody>
          {rows.length === 0 ? (
            <FinanceTableRow id="empty" textValue={emptyLabel}>
              {columns.map((column, columnIndex) => (
                <FinanceTableCell
                  key={column.key}
                  columnRole={columnIndex === 0 ? "description" : getColumnRole(column)}
                  textValue={columnIndex === 0 ? emptyLabel : "--"}
                >
                  <EmptyValue value={columnIndex === 0 ? emptyLabel : "--"} />
                </FinanceTableCell>
              ))}
            </FinanceTableRow>
          ) : rows.map((row, rowIndex) => {
            const rowKey = getRowKey(row, rowIndex);
            return (
              <FinanceTableRow
                key={rowKey}
                className={onRowClick ? "cost-table-row cost-table-row--clickable" : "cost-table-row"}
                id={rowKey}
                onClick={onRowClick ? (event) => {
                  const target = event.target instanceof Element ? event.target : null;
                  if (target?.closest("button, a, input, select, textarea, [role='checkbox']")) {
                    return;
                  }
                  if (hasSelectedTextWithin(event.currentTarget)) {
                    return;
                  }
                  onRowClick(row);
                } : undefined}
                textValue={rowKey}
              >
                {columns.map((column, columnIndex) => {
                  const content = column.render(row);
                  const renderedContent = renderTableCellContent(content);
                  const cellText = column.getTextValue?.(row) ?? getCellText(content);
                  const cellContent = columnIndex === 0 && onRowClick ? (
                    <span
                      aria-label={getRowActionLabel ? getRowActionLabel(row) : "查看行详情"}
                      className="cost-table-row-trigger"
                      onClick={(event) => {
                        event.stopPropagation();
                        if (!hasSelectedTextWithin(event.currentTarget)) {
                          onRowClick(row);
                        }
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          event.stopPropagation();
                          onRowClick(row);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      {renderedContent}
                    </span>
                  ) : renderedContent;

                  return (
                    <FinanceTableCell
                      key={column.key}
                      className={column.cellClassName}
                      columnRole={getColumnRole(column)}
                      textValue={cellText}
                    >
                      {cellContent}
                    </FinanceTableCell>
                  );
                })}
              </FinanceTableRow>
            );
          })}
        </FinanceTableBody>
      </FinanceTable>
      <footer className="cost-table-pagination-footer">
        <FinanceTablePagination
          compact
          isDisabled={isPageLoading}
          onPageChange={onPageChange}
          page={page}
          pageSize={pageSize}
          total={total}
        />
        <div aria-live="polite" className="cost-table-page-status">
          {pageError ? (
            <>
              <span>{pageError}</span>
              {onRetryPage ? (
                <Button onPress={onRetryPage} size="sm" variant="secondary">重试</Button>
              ) : null}
            </>
          ) : (
            <span>{isPageLoading ? "正在加载下一页" : `第 ${Math.min(Math.max(page, 1), totalPages)} / ${totalPages} 页`}</span>
          )}
        </div>
      </footer>
    </div>
  );
}

function getColumnRole<Row>(column: CostStatisticsTableColumn<Row>): FinanceTableColumnRole {
  if (column.key.toLowerCase().includes("amount")) {
    return "amount";
  }
  if (column.key.toLowerCase().includes("time")) {
    return "date";
  }
  if (column.key.toLowerCase().includes("account")) {
    return "account";
  }
  if (column.key.toLowerCase().includes("count")) {
    return "quantity";
  }
  if (column.key.toLowerCase().includes("direction")) {
    return "direction";
  }
  return "description";
}

function getCellText(content: ReactNode | CostStatisticsAmountCell) {
  if (
    typeof content === "object" &&
    content !== null &&
    "amount" in content
  ) {
    return formatCostAmount((content as { amount: string }).amount);
  }
  if (typeof content === "string" || typeof content === "number") {
    return String(content);
  }
  return "";
}

function renderTableCellContent(content: ReactNode | CostStatisticsAmountCell) {
  if (
    typeof content === "object" &&
    content !== null &&
    "amount" in content &&
    "direction" in content
  ) {
    const amount = formatCostAmount((content as { amount: string }).amount);
    const direction = String((content as { direction: string }).direction ?? "");
    const paymentAccountLabel = String((content as { paymentAccountLabel?: string }).paymentAccountLabel ?? "");
    const toneByDirection = Boolean((content as { toneByDirection?: boolean }).toneByDirection);
    const amountToneClass = toneByDirection
      ? direction === "收入"
        ? "cost-flow-amount--income"
        : "cost-flow-amount--expense"
      : "";
    const shouldShowAccount = paymentAccountLabel !== "" && paymentAccountLabel !== "--" && paymentAccountLabel !== "—";
    return (
      <span className="money-cell-stack">
        <span className={`money-cell-value ${amountToneClass}`.trim()}>
          {direction ? (
            <FinanceDirectionTag direction={direction}>
              {direction === "收入" ? "收" : direction === "支出" ? "支" : direction}
            </FinanceDirectionTag>
          ) : null}
          <span>{amount}</span>
        </span>
        {shouldShowAccount ? (
          <span className="money-cell-meta-row">
            <span className="money-cell-account">
              <Chip className="cost-bank-account-chip" color="default" size="sm" variant="soft">
                <Chip.Label><BankAccountValue value={paymentAccountLabel} /></Chip.Label>
              </Chip>
            </span>
          </span>
        ) : null}
      </span>
    );
  }
  return content;
}
