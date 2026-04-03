import type { TaxCertifiedInvoiceRecord } from "../../features/tax/types";

type CertifiedResultsDrawerProps = {
  matchedRows: TaxCertifiedInvoiceRecord[];
  outsidePlanRows: TaxCertifiedInvoiceRecord[];
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onSelectMatchedRow: (row: TaxCertifiedInvoiceRecord) => void;
};

function DrawerGroup({
  title,
  rows,
  buttonLabelPrefix,
  onSelect,
}: {
  title: string;
  rows: TaxCertifiedInvoiceRecord[];
  buttonLabelPrefix: string;
  onSelect?: (row: TaxCertifiedInvoiceRecord) => void;
}) {
  return (
    <section className="tax-certified-group">
      <header className="tax-certified-group-header">
        <strong>{title}</strong>
        <span>{rows.length} 条</span>
      </header>
      <div className="tax-certified-group-list">
        {rows.length === 0 ? <div className="tax-certified-empty">当前分组暂无记录</div> : null}
        {rows.map((row) => (
          <button
            key={row.id}
            className="tax-certified-item"
            type="button"
            onClick={() => onSelect?.(row)}
            aria-label={`${buttonLabelPrefix} ${row.invoiceNo}`}
          >
            <div className="tax-certified-item-head">
              <strong>{row.invoiceNo}</strong>
              <span>{row.statusLabel ?? "已认证"}</span>
            </div>
            <div className="tax-certified-item-meta">
              <span>{row.counterparty}</span>
              <span>{row.issueDate}</span>
              <span>{row.taxAmount}</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

export default function CertifiedResultsDrawer({
  matchedRows,
  outsidePlanRows,
  isCollapsed,
  onToggleCollapse,
  onSelectMatchedRow,
}: CertifiedResultsDrawerProps) {
  const totalCount = matchedRows.length + outsidePlanRows.length;

  return (
    <aside className={`tax-certified-drawer${isCollapsed ? " collapsed" : ""}`} aria-label="已认证结果" role="complementary">
      <button
        aria-label={`${isCollapsed ? "展开" : "收起"}已认证结果 ${totalCount}`}
        className="tax-certified-drawer-toggle"
        type="button"
        onClick={onToggleCollapse}
      >
        <span>已认证结果</span>
        <strong>{totalCount}</strong>
      </button>

      {!isCollapsed ? (
        <div className="tax-certified-drawer-body">
          <DrawerGroup
            title="已匹配计划"
            rows={matchedRows}
            buttonLabelPrefix="定位已匹配计划发票"
            onSelect={onSelectMatchedRow}
          />
          <DrawerGroup title="已认证但未进入计划" rows={outsidePlanRows} buttonLabelPrefix="查看未进入计划的已认证发票" />
        </div>
      ) : null}
    </aside>
  );
}
