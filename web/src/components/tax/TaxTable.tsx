import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { ReactNode } from "react";
import { Button, Checkbox } from "@heroui/react";

import type { TaxInvoiceRecord } from "../../features/tax/types";
import {
  AmountCell,
  EmptyValue,
  FinanceStatusTag,
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
  TableCellStack,
} from "../common/FinanceTable";
import WorkbenchColumnFilterMenu from "../workbench/WorkbenchColumnFilterMenu";

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

function TaxTableSearch({
  paneTitle,
  open,
  value,
  onChange,
  onClear,
  onClose,
  onToggle,
}: {
  paneTitle: string;
  open: boolean;
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  onClose: () => void;
  onToggle: () => void;
}) {
  const normalizedValue = value.trim();
  const hasAppliedValue = normalizedValue.length > 0;
  const buttonAriaLabel = open
    ? `收起搜索 ${paneTitle}`
    : hasAppliedValue
      ? `搜索 ${paneTitle}，当前关键词 ${normalizedValue}`
      : `搜索 ${paneTitle}`;

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  return (
    <div className={`pane-search${open ? " open" : ""}${hasAppliedValue ? " has-applied" : ""}`}>
      {open ? (
        <div className={`pane-search-popover${hasAppliedValue ? " active" : ""}`}>
          <input
            aria-label={`搜索 ${paneTitle}`}
            autoComplete="off"
            className="pane-search-field"
            placeholder={`搜索${paneTitle}`}
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
          {value ? (
            <button
              aria-label={`清空搜索 ${paneTitle}`}
              className="pane-search-clear-btn"
              type="button"
              onClick={onClear}
            >
              清空
            </button>
          ) : null}
        </div>
      ) : null}
      <button
        aria-label={buttonAriaLabel}
        className={`pane-tool-btn pane-search-toggle-btn fixed${open || hasAppliedValue ? " active" : ""}${hasAppliedValue && !open ? " summary" : ""}`}
        type="button"
        onClick={onToggle}
      >
        {hasAppliedValue && !open ? (
          <span className="pane-search-summary">{normalizedValue}</span>
        ) : (
          <svg aria-hidden="true" className="pane-tool-icon" viewBox="0 0 20 20">
            <circle cx="9" cy="9" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M13.4 13.4 17 17" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
          </svg>
        )}
      </button>
    </div>
  );
}

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
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [counterpartyFilterOpen, setCounterpartyFilterOpen] = useState(false);
  const [selectedCounterparties, setSelectedCounterparties] = useState<string[]>([]);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc" | null>(null);
  const counterpartyOptions = useMemo(() => collectCounterpartyOptions(rows), [rows]);
  const displayRows = useMemo(
    () => buildDisplayRows(rows, {
      query: searchQuery,
      selectedCounterparties,
      sortDirection,
    }),
    [rows, searchQuery, selectedCounterparties, sortDirection],
  );
  const visibleSelectedCount = displayRows.filter((row) => selectedIds.includes(row.id)).length;
  const hasActiveDisplayFilter = searchQuery.trim().length > 0 || selectedCounterparties.length > 0;

  function getInvoiceFlowMeta(row: TaxInvoiceRecord) {
    if (row.flowType === "output") {
      return { label: "销", className: "invoice-flow-tag invoice-flow-tag-output" };
    }
    if (row.flowType === "input") {
      return { label: "进", className: "invoice-flow-tag invoice-flow-tag-input" };
    }
    if (row.invoiceType.includes("销")) {
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
  }, [activeTableWrapRef, displayRows, selectable, showBottomScrollbar, title]);

  useEffect(() => {
    setSelectedCounterparties((current) =>
      current.filter((counterparty) => counterpartyOptions.includes(counterparty)),
    );
  }, [counterpartyOptions]);

  const handleToggleSort = () => {
    setSortDirection((current) => (current === "desc" ? "asc" : "desc"));
  };

  return (
    <section className="tax-panel">
      <header className="tax-panel-header">
        <div className="tax-panel-header-copy">
          <strong>{title}</strong>
          <span>
            {selectable
              ? `已选 ${visibleSelectedCount} / ${displayRows.length}${displayRows.length === rows.length ? "" : `（共 ${rows.length}）`}`
              : `共 ${displayRows.length}${displayRows.length === rows.length ? "" : ` / ${rows.length}`} 条`}
          </span>
        </div>
        <div className="tax-panel-header-actions">
          <Button
            aria-label={buildTaxTableSortActionLabel(title, sortDirection)}
            className={`pane-tool-btn pane-sort-btn${sortDirection ? " active" : ""}`}
            size="sm"
            type="button"
            variant={sortDirection ? "primary" : "outline"}
            onPress={handleToggleSort}
          >
            <span className="pane-sort-label">{buildTaxTableSortVisualLabel(sortDirection)}</span>
          </Button>
          <TaxTableSearch
            open={searchOpen}
            paneTitle={title}
            value={searchQuery}
            onChange={setSearchQuery}
            onClear={() => setSearchQuery("")}
            onClose={() => setSearchOpen(false)}
            onToggle={() => setSearchOpen((current) => !current)}
          />
          {headerActions}
        </div>
      </header>
      <FinanceTable ariaLabel={title} className="tax-grid-table" minWidth={760} scrollRef={activeTableWrapRef}>
        <FinanceTableHeader>
          {selectable ? <FinanceTableColumn columnRole="selection">选择</FinanceTableColumn> : null}
          <FinanceTableColumn columnRole="identity" isRowHeader>发票编号</FinanceTableColumn>
          <FinanceTableColumn columnRole="amount">税额</FinanceTableColumn>
          <FinanceTableColumn columnRole="account">
            <span className="tax-column-header-with-filter">
              <span>对方名称</span>
              <WorkbenchColumnFilterMenu
                label="对方名称"
                open={counterpartyFilterOpen}
                options={counterpartyOptions}
                selectedValues={selectedCounterparties}
                onChange={setSelectedCounterparties}
                onClose={() => setCounterpartyFilterOpen(false)}
                onToggle={() => setCounterpartyFilterOpen((current) => !current)}
              />
            </span>
          </FinanceTableColumn>
          <FinanceTableColumn columnRole="amount">金额（税率）</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          {displayRows.length === 0 ? (
            <FinanceTableRow id={`${title}-empty`} className="workbench-empty-row" textValue={hasActiveDisplayFilter ? "当前筛选暂无记录" : "当前栏暂无记录"}>
              {selectable ? (
                <FinanceTableCell columnRole="selection" className="workbench-empty-cell">
                  <EmptyValue />
                </FinanceTableCell>
              ) : null}
              <FinanceTableCell columnRole="identity" className="workbench-empty-cell">
                {hasActiveDisplayFilter ? "当前筛选暂无记录" : "当前栏暂无记录"}
              </FinanceTableCell>
              <FinanceTableCell columnRole="amount" className="workbench-empty-cell">
                <EmptyValue />
              </FinanceTableCell>
              <FinanceTableCell columnRole="account" className="workbench-empty-cell">
                <EmptyValue />
              </FinanceTableCell>
              <FinanceTableCell columnRole="amount" className="workbench-empty-cell">
                <EmptyValue />
              </FinanceTableCell>
            </FinanceTableRow>
          ) : null}
          {displayRows.map((row) => {
            const checked = selectedIds.includes(row.id);
            const isLocked = row.isLocked ?? false;
            const isHighlighted = highlightedRowId === row.id;
            const invoiceFlow = getInvoiceFlowMeta(row);
            const statusMeta = getStatusMeta(row.statusLabel);
            const issueDateMeta = getIssueDateMeta(row.issueDate);
            const taxRateMeta = getTaxRateMeta(row.taxRate);

            return (
              <FinanceTableRow
                key={row.id}
                className={`${checked ? "tax-row-selected" : ""}${isLocked ? " tax-row-locked" : ""}${isHighlighted ? " tax-row-highlighted" : ""}`}
                dataCertifiedHighlighted={isHighlighted}
                id={row.id}
                textValue={`${row.invoiceNo} ${row.counterparty} ${invoiceFlow.label} ${row.statusLabel ?? ""} ${row.issueDate} ${row.taxAmount} ${row.amount} ${row.taxRate}`}
              >
                {selectable ? (
                  <FinanceTableCell columnRole="selection" className="tax-check-column" textValue={`${row.invoiceNo} ${row.counterparty}`}>
                    <Checkbox
                      aria-label={`${row.invoiceNo} ${row.counterparty}`}
                      className="tax-row-checkbox"
                      isDisabled={isLocked || row.isSelectable === false}
                      isSelected={checked}
                      onChange={() => onToggleRow?.(row.id)}
                    >
                      <Checkbox.Control>
                        <Checkbox.Indicator />
                      </Checkbox.Control>
                    </Checkbox>
                  </FinanceTableCell>
                ) : null}
                <FinanceTableCell columnRole="identity" className="tax-column-invoice-no" textValue={row.invoiceNo}>
                  <TableCellStack
                    className="tax-invoice-no-value"
                    primary={<span className="tax-invoice-number">{row.invoiceNo}</span>}
                    secondary={(
                      <span className="tax-invoice-meta-row">
                        <span className={invoiceFlow.className}>{invoiceFlow.label}</span>
                        {statusMeta ? <FinanceStatusTag tone={statusMeta.label.includes("已认证") ? "success" : "warning"}>{statusMeta.label}</FinanceStatusTag> : null}
                        {issueDateMeta ? <span className={issueDateMeta.className}>{issueDateMeta.label}</span> : null}
                      </span>
                    )}
                  />
                </FinanceTableCell>
                <FinanceTableCell columnRole="amount" className="tax-column-tax-amount" textValue={row.taxAmount}>
                  {row.taxAmount}
                </FinanceTableCell>
                <FinanceTableCell columnRole="account" className="tax-column-counterparty" textValue={row.counterparty}>
                  {row.counterparty}
                </FinanceTableCell>
                <FinanceTableCell columnRole="amount" className="tax-column-amount-rate" textValue={`${row.amount} ${row.taxRate}`}>
                  <AmountCell
                    amount={row.amount}
                    direction={taxRateMeta ? <span className={taxRateMeta.className}>({taxRateMeta.label})</span> : undefined}
                  />
                </FinanceTableCell>
              </FinanceTableRow>
            );
          })}
        </FinanceTableBody>
      </FinanceTable>
      {showBottomScrollbar ? (
        <div ref={scrollbarRef} className="tax-horizontal-scrollbar" aria-label={`${title}横向滚动`}>
          <div ref={scrollbarInnerRef} className="tax-horizontal-scrollbar-inner" />
        </div>
      ) : null}
    </section>
  );
}

function normalizeTaxSearchText(value: string) {
  return value.trim().toLowerCase();
}

function buildTaxRowSearchText(row: TaxInvoiceRecord) {
  return [
    row.invoiceNo,
    row.invoiceType,
    row.counterparty,
    row.issueDate,
    row.taxRate,
    row.amount,
    row.taxAmount,
    row.statusLabel ?? "",
  ].join(" ").toLowerCase();
}

function collectCounterpartyOptions(rows: TaxInvoiceRecord[]) {
  return Array.from(
    new Set(rows.map((row) => row.counterparty.trim()).filter(Boolean)),
  ).sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function buildDisplayRows(
  rows: TaxInvoiceRecord[],
  options: {
    query: string;
    selectedCounterparties: string[];
    sortDirection: "asc" | "desc" | null;
  },
) {
  const normalizedQuery = normalizeTaxSearchText(options.query);
  const selectedCounterpartySet = new Set(options.selectedCounterparties);
  const filteredRows = rows.filter((row) => {
    if (normalizedQuery && !buildTaxRowSearchText(row).includes(normalizedQuery)) {
      return false;
    }
    if (selectedCounterpartySet.size > 0 && !selectedCounterpartySet.has(row.counterparty)) {
      return false;
    }
    return true;
  });

  if (!options.sortDirection) {
    return filteredRows;
  }

  return [...filteredRows].sort((left, right) => {
    const dateComparison = left.issueDate.localeCompare(right.issueDate);
    const resolvedComparison = dateComparison === 0 ? left.invoiceNo.localeCompare(right.invoiceNo) : dateComparison;
    return options.sortDirection === "asc" ? resolvedComparison : -resolvedComparison;
  });
}

function buildTaxTableSortActionLabel(title: string, currentDirection: "asc" | "desc" | null) {
  return `${title}按时间${currentDirection === "desc" ? "升序" : "降序"}`;
}

function buildTaxTableSortVisualLabel(currentDirection: "asc" | "desc" | null) {
  return currentDirection === "desc" ? "时间↑" : "时间↓";
}
