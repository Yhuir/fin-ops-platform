import type { ReactNode } from "react";

import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";

type CostStatisticsAmountCell = {
  amount: string;
  direction: string;
  paymentAccountLabel?: string;
};

type CostStatisticsTableColumn<Row> = {
  key: string;
  header: string;
  headerClassName?: string;
  cellClassName?: string;
  render: (row: Row) => ReactNode | CostStatisticsAmountCell;
};

type CostStatisticsTableProps<Row> = {
  ariaLabel: string;
  columns: CostStatisticsTableColumn<Row>[];
  rows: Row[];
  getRowKey: (row: Row) => string;
  emptyLabel?: string;
  onRowClick?: (row: Row) => void;
  getRowActionLabel?: (row: Row) => string;
};

export default function CostStatisticsTable<Row>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  emptyLabel = "当前视图暂无数据。",
  onRowClick,
  getRowActionLabel,
}: CostStatisticsTableProps<Row>) {
  return (
    <div className="cost-table-shell">
      <table aria-label={ariaLabel} className="cost-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.headerClassName}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="cost-table-empty" colSpan={columns.length}>
                {emptyLabel}
              </td>
            </tr>
          ) : (
            rows.map((row, rowIndex) => (
              <tr
                key={getRowKey(row)}
                className={onRowClick ? "cost-table-row clickable" : "cost-table-row"}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((column, columnIndex) => {
                  const content = column.render(row);
                  const renderedContent = renderTableCellContent(content);
                  const isInteractive = Boolean(onRowClick) && columnIndex === 0;
                  return (
                    <td key={column.key} className={column.cellClassName}>
                      {isInteractive ? (
                        <button
                          className="cost-table-row-trigger"
                          type="button"
                          aria-label={getRowActionLabel ? getRowActionLabel(row) : `查看第 ${rowIndex + 1} 行`}
                          onClick={(event) => {
                            event.stopPropagation();
                            onRowClick?.(row);
                          }}
                        >
                          {renderedContent}
                        </button>
                      ) : (
                        renderedContent
                      )}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function renderTableCellContent(content: ReactNode | CostStatisticsAmountCell) {
  if (
    typeof content === "object" &&
    content !== null &&
    "amount" in content &&
    "direction" in content
  ) {
    const amount = String((content as { amount: string }).amount ?? "--");
    const direction = String((content as { direction: string }).direction ?? "");
    const paymentAccountLabel = String((content as { paymentAccountLabel?: string }).paymentAccountLabel ?? "");
    const shouldShowAccount = paymentAccountLabel !== "" && paymentAccountLabel !== "--" && paymentAccountLabel !== "—";
    return (
      <span className="money-cell-stack">
        <span className="money-cell-value">
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
