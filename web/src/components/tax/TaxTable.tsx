import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import type { TaxInvoiceRecord } from "../../features/tax/types";
import WorkbenchColumnFilterMenu from "../workbench/WorkbenchColumnFilterMenu";
import WorkbenchPaneSearch from "../workbench/WorkbenchPaneSearch";

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
    <Paper className="tax-panel" component="section" variant="outlined">
      <Stack className="tax-panel-header" component="header" direction="row" justifyContent="space-between" alignItems="center" gap={1}>
        <Stack className="tax-panel-header-copy" spacing={0.25}>
          <Typography component="span" fontWeight={800}>
            {title}
          </Typography>
          <Typography component="span" color="text.secondary">
            {selectable
              ? `已选 ${visibleSelectedCount} / ${displayRows.length}${displayRows.length === rows.length ? "" : `（共 ${rows.length}）`}`
              : `共 ${displayRows.length}${displayRows.length === rows.length ? "" : ` / ${rows.length}`} 条`}
          </Typography>
        </Stack>
        <Stack className="tax-panel-header-actions" direction="row" alignItems="center" gap={0.75}>
          <Button
            aria-label={buildTaxTableSortActionLabel(title, sortDirection)}
            className={`pane-tool-btn pane-sort-btn${sortDirection ? " active" : ""}`}
            type="button"
            onClick={handleToggleSort}
            size="small"
            variant={sortDirection ? "contained" : "outlined"}
          >
            <span className="pane-sort-label">{buildTaxTableSortVisualLabel(sortDirection)}</span>
          </Button>
          <WorkbenchPaneSearch
            open={searchOpen}
            appliedValue={searchQuery}
            draftValue={searchQuery}
            paneTitle={title}
            onChange={setSearchQuery}
            onClear={() => setSearchQuery("")}
            onClose={() => setSearchOpen(false)}
            onToggle={() => setSearchOpen((current) => !current)}
          />
          {headerActions}
        </Stack>
      </Stack>
      <TableContainer ref={activeTableWrapRef} className="table-wrap tax-table-wrap">
        <Table aria-label={title} className="grid-table tax-grid-table" size="small" stickyHeader>
          <TableHead>
            <TableRow>
              {selectable ? <TableCell className="tax-check-column">选择</TableCell> : null}
              <TableCell className="tax-column-invoice-no">发票编号</TableCell>
              <TableCell className="cell-money tax-column-tax-amount">税额</TableCell>
              <TableCell className="tax-column-counterparty">
                <Box className="tax-column-header-with-filter" component="span">
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
                </Box>
              </TableCell>
              <TableCell className="cell-money tax-column-amount-rate">金额（税率）</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {displayRows.length === 0 ? (
              <TableRow className="workbench-empty-row">
                <TableCell className="workbench-empty-cell" colSpan={selectable ? 5 : 4}>
                  {hasActiveDisplayFilter ? "当前筛选暂无记录" : "当前栏暂无记录"}
                </TableCell>
              </TableRow>
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
                <TableRow
                  key={row.id}
                  className={`${checked ? "tax-row-selected" : ""}${isLocked ? " tax-row-locked" : ""}${isHighlighted ? " tax-row-highlighted" : ""}`}
                  data-certified-highlighted={isHighlighted ? "true" : "false"}
                >
                  {selectable ? (
                    <TableCell className="tax-check-column">
                      <Checkbox
                        checked={checked}
                        disabled={isLocked || row.isSelectable === false}
                        inputProps={{ "aria-label": `${row.invoiceNo} ${row.counterparty}` }}
                        onChange={() => onToggleRow?.(row.id)}
                        size="small"
                      />
                    </TableCell>
                  ) : null}
                  <TableCell className="tax-column-invoice-no">
                    <span className="tax-invoice-no-value">
                      <span className="tax-invoice-meta-row">
                        <span className={invoiceFlow.className}>{invoiceFlow.label}</span>
                        {statusMeta ? <span className={statusMeta.className}>{statusMeta.label}</span> : null}
                        {issueDateMeta ? <span className={issueDateMeta.className}>{issueDateMeta.label}</span> : null}
                      </span>
                      <span className="tax-invoice-number">{row.invoiceNo}</span>
                    </span>
                  </TableCell>
                  <TableCell className="cell-money tax-column-tax-amount">{row.taxAmount}</TableCell>
                  <TableCell className="tax-column-counterparty">{row.counterparty}</TableCell>
                  <TableCell className="cell-money tax-column-amount-rate">
                    <span className="tax-amount-rate-value">
                      <span className="tax-amount-rate-primary">{row.amount}</span>
                      {taxRateMeta ? <span className={taxRateMeta.className}>({taxRateMeta.label})</span> : null}
                    </span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      {showBottomScrollbar ? (
        <div ref={scrollbarRef} className="tax-horizontal-scrollbar" aria-label={`${title}横向滚动`}>
          <div ref={scrollbarInnerRef} className="tax-horizontal-scrollbar-inner" />
        </div>
      ) : null}
    </Paper>
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
