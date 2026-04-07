import { useEffect, useRef } from "react";
import type { MutableRefObject } from "react";
import type { ReactNode } from "react";

import type { TaxInvoiceRecord } from "../../features/tax/types";

type TaxTableProps = {
  title: string;
  rows: TaxInvoiceRecord[];
  selectedIds: string[];
  onToggleRow?: (id: string) => void;
  selectable?: boolean;
  highlightedRowId?: string | null;
  showBottomScrollbar?: boolean;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
  headerActions?: ReactNode;
};

export default function TaxTable({
  title,
  rows,
  selectedIds,
  onToggleRow,
  selectable = true,
  highlightedRowId = null,
  showBottomScrollbar = true,
  tableWrapRef,
  headerActions,
}: TaxTableProps) {
  const internalTableWrapRef = useRef<HTMLDivElement | null>(null);
  const scrollbarRef = useRef<HTMLDivElement | null>(null);
  const scrollbarInnerRef = useRef<HTMLDivElement | null>(null);
  const isSyncingScrollRef = useRef(false);
  const activeTableWrapRef = tableWrapRef ?? internalTableWrapRef;

  function getInvoiceFlowMeta(invoiceType: string) {
    if (invoiceType.includes("销")) {
      return { label: "销", className: "invoice-flow-tag invoice-flow-tag-output" };
    }
    return { label: "进", className: "invoice-flow-tag invoice-flow-tag-input" };
  }

  function getStatusMeta(statusLabel?: string) {
    if (!statusLabel || statusLabel === "--") {
      return null;
    }
    if (statusLabel.includes("已认证")) {
      return { label: statusLabel, className: "tax-status-tag tax-status-tag-certified" };
    }
    if (statusLabel.includes("待")) {
      return { label: statusLabel, className: "tax-status-tag tax-status-tag-pending" };
    }
    return { label: statusLabel, className: "tax-status-tag tax-status-tag-default" };
  }

  function getIssueDateMeta(issueDate?: string) {
    if (!issueDate || issueDate === "--") {
      return null;
    }
    return { label: issueDate, className: "tax-date-tag" };
  }

  function getTaxRateMeta(taxRate?: string) {
    if (!taxRate || taxRate === "--" || taxRate === "—") {
      return null;
    }
    return { label: taxRate, className: "tax-rate-tag" };
  }

  useEffect(() => {
    const tableWrap = activeTableWrapRef.current;
    const scrollbar = scrollbarRef.current;
    const scrollbarInner = scrollbarInnerRef.current;
    if (!showBottomScrollbar || !tableWrap || !scrollbar || !scrollbarInner) {
      return undefined;
    }

    const syncDimensions = () => {
      scrollbarInner.style.width = `${tableWrap.scrollWidth}px`;
      scrollbar.scrollLeft = tableWrap.scrollLeft;
    };

    const syncFromTable = () => {
      if (isSyncingScrollRef.current) {
        return;
      }
      isSyncingScrollRef.current = true;
      scrollbar.scrollLeft = tableWrap.scrollLeft;
      requestAnimationFrame(() => {
        isSyncingScrollRef.current = false;
      });
    };

    const syncFromScrollbar = () => {
      if (isSyncingScrollRef.current) {
        return;
      }
      isSyncingScrollRef.current = true;
      tableWrap.scrollLeft = scrollbar.scrollLeft;
      requestAnimationFrame(() => {
        isSyncingScrollRef.current = false;
      });
    };

    syncDimensions();
    tableWrap.addEventListener("scroll", syncFromTable);
    scrollbar.addEventListener("scroll", syncFromScrollbar);
    window.addEventListener("resize", syncDimensions);

    return () => {
      tableWrap.removeEventListener("scroll", syncFromTable);
      scrollbar.removeEventListener("scroll", syncFromScrollbar);
      window.removeEventListener("resize", syncDimensions);
    };
  }, [activeTableWrapRef, rows, selectable, showBottomScrollbar, title]);

  return (
    <section className="tax-panel">
      <header className="tax-panel-header">
        <div className="tax-panel-header-copy">
          <span>{title}</span>
          <span>
            {selectable ? `已选 ${selectedIds.length} / ${rows.length}` : `共 ${rows.length} 条`}
          </span>
        </div>
        {headerActions ? <div className="tax-panel-header-actions">{headerActions}</div> : null}
      </header>
      <div ref={activeTableWrapRef} className="table-wrap tax-table-wrap">
        <table aria-label={title} className="grid-table tax-grid-table">
          <thead>
            <tr>
              {selectable ? <th className="tax-check-column">选择</th> : null}
              <th className="tax-column-invoice-no">发票编号</th>
              <th className="cell-money tax-column-tax-amount">税额</th>
              <th className="tax-column-counterparty">对方名称</th>
              <th className="cell-money tax-column-amount-rate">金额（税率）</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr className="workbench-empty-row">
                <td className="workbench-empty-cell" colSpan={selectable ? 5 : 4}>
                  当前栏暂无记录
                </td>
              </tr>
            ) : null}
            {rows.map((row) => {
              const checked = selectedIds.includes(row.id);
              const isLocked = row.isLocked ?? false;
              const isHighlighted = highlightedRowId === row.id;
              const invoiceFlow = getInvoiceFlowMeta(row.invoiceType);
              const statusMeta = getStatusMeta(row.statusLabel);
              const issueDateMeta = getIssueDateMeta(row.issueDate);
              const taxRateMeta = getTaxRateMeta(row.taxRate);

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
                  <td className="tax-column-invoice-no">
                    <span className="tax-invoice-no-value">
                      <span className="tax-invoice-meta-row">
                        <span className={invoiceFlow.className}>{invoiceFlow.label}</span>
                        {statusMeta ? <span className={statusMeta.className}>{statusMeta.label}</span> : null}
                        {issueDateMeta ? <span className={issueDateMeta.className}>{issueDateMeta.label}</span> : null}
                      </span>
                      <span className="tax-invoice-number">{row.invoiceNo}</span>
                    </span>
                  </td>
                  <td className="cell-money tax-column-tax-amount">{row.taxAmount}</td>
                  <td className="tax-column-counterparty">{row.counterparty}</td>
                  <td className="cell-money tax-column-amount-rate">
                    <span className="tax-amount-rate-value">
                      <span className="tax-amount-rate-primary">{row.amount}</span>
                      {taxRateMeta ? <span className={taxRateMeta.className}>({taxRateMeta.label})</span> : null}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {showBottomScrollbar ? (
        <div ref={scrollbarRef} className="tax-horizontal-scrollbar" aria-label={`${title}横向滚动`}>
          <div ref={scrollbarInnerRef} className="tax-horizontal-scrollbar-inner" />
        </div>
      ) : null}
    </section>
  );
}
