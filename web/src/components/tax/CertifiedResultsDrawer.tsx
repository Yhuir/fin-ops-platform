import { Button, Chip } from "@heroui/react";

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
      <div className="tax-certified-group-header">
        <strong>{title}</strong>
        <Chip size="sm" variant="secondary">{rows.length} 条</Chip>
      </div>
      <div className="tax-certified-group-list">
        {rows.length === 0 ? <p className="tax-certified-empty">当前分组暂无记录</p> : null}
        {rows.map((row) => (
          <button
            key={row.id}
            className="tax-certified-item"
            type="button"
            onClick={() => onSelect?.(row)}
            aria-label={`${buttonLabelPrefix} ${row.invoiceNo}`}
          >
            <span className="tax-certified-item-head">
              <strong>{row.invoiceNo}</strong>
              <Chip color="success" size="sm" variant="secondary">{row.statusLabel ?? "已认证"}</Chip>
            </span>
            <span className="tax-certified-item-meta">
              <span>{row.counterparty}</span>
              <span>{row.issueDate}</span>
              <span>{row.taxAmount}</span>
            </span>
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
    <aside
      className={`tax-certified-drawer${isCollapsed ? " collapsed" : ""}`}
      aria-label="已认证结果"
      role="complementary"
    >
      <Button
        aria-label={`${isCollapsed ? "展开" : "收起"}已认证结果 ${totalCount}`}
        className="tax-certified-drawer-toggle"
        type="button"
        variant="tertiary"
        onPress={onToggleCollapse}
      >
        <span>已认证结果</span>
        <strong>{totalCount}</strong>
      </Button>

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
