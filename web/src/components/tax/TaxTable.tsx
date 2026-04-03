import type { TaxInvoiceRecord } from "../../features/tax/types";

type TaxTableProps = {
  title: string;
  rows: TaxInvoiceRecord[];
  selectedIds: string[];
  onToggleRow?: (id: string) => void;
  selectable?: boolean;
  highlightedRowId?: string | null;
};

export default function TaxTable({
  title,
  rows,
  selectedIds,
  onToggleRow,
  selectable = true,
  highlightedRowId = null,
}: TaxTableProps) {
  const showStatusColumn = rows.some((row) => row.statusLabel);

  return (
    <section className="tax-panel">
      <header className="tax-panel-header">
        <span>{title}</span>
        <span>
          {selectable ? `已选 ${selectedIds.length} / ${rows.length}` : `共 ${rows.length} 条`}
        </span>
      </header>
      <div className="table-wrap">
        <table aria-label={title} className="grid-table tax-grid-table">
          <thead>
            <tr>
              {selectable ? <th className="tax-check-column">选择</th> : null}
              <th>发票编号</th>
              <th>发票类型</th>
              <th>对方名称</th>
              <th>开票日期</th>
              {showStatusColumn ? <th>状态</th> : null}
              <th>税率</th>
              <th className="cell-money">金额</th>
              <th className="cell-money">税额</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr className="workbench-empty-row">
                <td className="workbench-empty-cell" colSpan={selectable ? (showStatusColumn ? 9 : 8) : (showStatusColumn ? 8 : 7)}>
                  当前栏暂无记录
                </td>
              </tr>
            ) : null}
            {rows.map((row) => {
              const checked = selectedIds.includes(row.id);
              const isLocked = row.isLocked ?? false;
              const isHighlighted = highlightedRowId === row.id;

              return (
                <tr
                  key={row.id}
                  className={`${checked ? "tax-row-selected" : ""}${isLocked ? " tax-row-locked" : ""}${isHighlighted ? " tax-row-highlighted" : ""}`}
                  data-certified-highlighted={isHighlighted ? "true" : "false"}
                >
                  {selectable ? (
                    <td className="tax-check-column">
                      <input
                        aria-label={`${row.invoiceNo} ${row.counterparty}`}
                        checked={checked}
                        disabled={isLocked || row.isSelectable === false}
                        type="checkbox"
                        onChange={() => onToggleRow?.(row.id)}
                      />
                    </td>
                  ) : null}
                  <td>{row.invoiceNo}</td>
                  <td>{row.invoiceType}</td>
                  <td>{row.counterparty}</td>
                  <td>{row.issueDate}</td>
                  {showStatusColumn ? <td>{row.statusLabel ?? "--"}</td> : null}
                  <td>{row.taxRate}</td>
                  <td className="cell-money">{row.amount}</td>
                  <td className="cell-money">{row.taxAmount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
