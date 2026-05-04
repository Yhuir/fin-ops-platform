import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { DataGrid, type GridColDef, type GridRowParams } from "@mui/x-data-grid";

import BankAccountValue from "../BankAccountValue";
import DirectionTag from "../DirectionTag";

export type CostStatisticsAmountCell = {
  amount: string;
  direction: string;
  paymentAccountLabel?: string;
};

export type CostStatisticsTableColumn<Row> = {
  key: string;
  header: string;
  headerClassName?: string;
  cellClassName?: string;
  width?: number;
  flex?: number;
  render: (row: Row) => ReactNode | CostStatisticsAmountCell;
};

type CostStatisticsTableProps<Row extends object> = {
  ariaLabel: string;
  columns: CostStatisticsTableColumn<Row>[];
  rows: Row[];
  getRowKey: (row: Row) => string;
  emptyLabel?: string;
  onRowClick?: (row: Row) => void;
  getRowActionLabel?: (row: Row) => string;
};

export default function CostStatisticsTable<Row extends object>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  emptyLabel = "当前视图暂无数据。",
  onRowClick,
  getRowActionLabel,
}: CostStatisticsTableProps<Row>) {
  const onRowClickRef = useRef(onRowClick);
  const getRowActionLabelRef = useRef(getRowActionLabel);

  useEffect(() => {
    onRowClickRef.current = onRowClick;
    getRowActionLabelRef.current = getRowActionLabel;
  }, [getRowActionLabel, onRowClick]);

  const dataGridColumns = useMemo<GridColDef<Row>[]>(
    () =>
      columns.map((column, columnIndex) => ({
        field: column.key,
        headerName: column.header,
        width: column.width,
        flex: column.flex ?? (column.width ? undefined : 1),
        minWidth: column.width ? undefined : 140,
        headerClassName: column.headerClassName,
        cellClassName: column.cellClassName,
        sortable: true,
        renderCell: (params) => {
          const renderedContent = renderTableCellContent(column.render(params.row));
          if (columnIndex !== 0) {
            return renderedContent;
          }
          return (
            <button
              className="cost-table-row-trigger"
              type="button"
              aria-label={getRowActionLabelRef.current ? getRowActionLabelRef.current(params.row) : "查看行详情"}
              onClick={(event) => {
                event.stopPropagation();
                onRowClickRef.current?.(params.row);
              }}
            >
              {renderedContent}
            </button>
          );
        },
      })),
    [columns],
  );

  const gridHeight = rows.length === 0 ? 180 : Math.min(520, 112 + rows.length * 58);

  return (
    <div className="cost-table-shell cost-data-grid-shell" style={{ height: gridHeight }}>
      <DataGrid
        aria-label={ariaLabel}
        columns={dataGridColumns}
        rows={rows}
        getRowId={getRowKey}
        disableRowSelectionOnClick
        hideFooter
        localeText={{ noRowsLabel: emptyLabel }}
        onRowClick={(params: GridRowParams<Row>) => onRowClickRef.current?.(params.row)}
        rowHeight={58}
        columnHeaderHeight={42}
        sx={{
          border: 0,
          "& .MuiDataGrid-cell": {
            alignItems: "flex-start",
            py: 1.25,
            lineHeight: 1.5,
          },
        }}
      />
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
