import { useEffect, useRef, type ReactNode } from "react";

import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";
import { formatCostAmount } from "../../features/cost-statistics/format";
import {
  EmptyValue,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
  type FinanceTableColumnRole,
} from "../common/FinanceTable";

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
  hasNextPage?: boolean;
  loadingMore?: boolean;
  loadMoreError?: string | null;
  onRequestNextPage?: () => void;
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
  hasNextPage = false,
  loadingMore = false,
  loadMoreError,
  onRequestNextPage,
}: CostStatisticsTableProps<Row>) {
  const minWidth = columns.reduce((total, column) => total + (column.width ?? (column.flex ? 180 : 140)), 0);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const requestNextPageRef = useRef(onRequestNextPage);
  requestNextPageRef.current = onRequestNextPage;

  useEffect(() => {
    const scrollElement = shellRef.current?.querySelector<HTMLDivElement>(".finance-table__scroll");
    if (
      !scrollElement
      || rows.length === 0
      || !hasNextPage
      || loadingMore
      || loadMoreError
    ) {
      return undefined;
    }
    let requested = false;
    const requestIfNearBottom = () => {
      const remaining = scrollElement.scrollHeight
        - scrollElement.scrollTop
        - scrollElement.clientHeight;
      if (!requested && remaining <= 160) {
        requested = true;
        requestNextPageRef.current?.();
      }
    };
    scrollElement.addEventListener("scroll", requestIfNearBottom, { passive: true });
    const frameId = window.requestAnimationFrame(requestIfNearBottom);
    return () => {
      window.cancelAnimationFrame(frameId);
      scrollElement.removeEventListener("scroll", requestIfNearBottom);
    };
  }, [hasNextPage, loadMoreError, loadingMore, rows.length]);

  return (
    <div ref={shellRef} className="cost-table-shell cost-finance-table-shell">
      <FinanceTable
        ariaLabel={ariaLabel}
        className={fitContainer ? "cost-finance-table cost-finance-table--fit" : "cost-finance-table"}
        minWidth={fitContainer ? "100%" : Math.max(720, minWidth)}
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
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                textValue={rowKey}
              >
                {columns.map((column, columnIndex) => {
                  const content = column.render(row);
                  const renderedContent = renderTableCellContent(content);
                  const cellText = column.getTextValue?.(row) ?? getCellText(content);
                  const cellContent = columnIndex === 0 && onRowClick ? (
                    <button
                      aria-label={getRowActionLabel ? getRowActionLabel(row) : "查看行详情"}
                      className="cost-table-row-trigger"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRowClick(row);
                      }}
                      type="button"
                    >
                      {renderedContent}
                    </button>
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
      {loadingMore || loadMoreError ? (
        <div aria-live="polite" className="cost-auto-load-status">
          {loadMoreError ? (
            <>
              <span>{loadMoreError}</span>
              <button onClick={onRequestNextPage} type="button">重试</button>
            </>
          ) : (
            <span>正在加载更多流水…</span>
          )}
        </div>
      ) : null}
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
          <span>{amount}</span>
        </span>
        {direction || shouldShowAccount ? (
          <span className="money-cell-meta-row">
            {direction ? <DirectionTag direction={direction} /> : null}
            {shouldShowAccount ? (
              <span className="money-cell-account">
                <BankAccountValue value={paymentAccountLabel} variant="tag" />
              </span>
            ) : null}
          </span>
        ) : null}
      </span>
    );
  }
  return content;
}
