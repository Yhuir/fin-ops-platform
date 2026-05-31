import SortOutlinedIcon from "@mui/icons-material/SortOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";

import type {
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterFieldConfig,
  OutputInvoiceCollectionFilterOption,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionWorkflow,
} from "../../features/outputInvoiceCollections/types";
import ExpandableCellText from "./ExpandableCellText";
import OutputInvoiceCollectionFilterMenu, { type OutputInvoiceCollectionFilterValue } from "./OutputInvoiceCollectionFilterMenu";

type OutputInvoiceCollectionsTableProps = {
  rows: OutputInvoiceCollectionRow[];
  page: number;
  pageSize: number;
  total: number;
  sortField: string;
  sortDirection: OutputInvoiceCollectionSortDirection | "";
  filters: OutputInvoiceCollectionFilter[];
  filterConfigs: OutputInvoiceCollectionFilterFieldConfig[];
  filterOptions: Record<string, OutputInvoiceCollectionFilterOption[]>;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: OutputInvoiceCollectionDetailTarget) => void;
  onOpenWorkflow: (target: NonNullable<OutputInvoiceCollectionWorkflow>) => void;
  onFilterApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OutputInvoiceCollectionSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

const defaultFilterConfigs: Record<string, OutputInvoiceCollectionFilterFieldConfig> = {
  invoice_no: { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
  buyer_name: { field: "buyer_name", label: "购方", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  total_with_tax: { field: "total_with_tax", label: "价税合计", mode: "money", sortable: true, operators: ["between", "equals"] },
  tax_amount: { field: "tax_amount", label: "税额/税率", mode: "money", sortable: true, operators: ["between", "equals"] },
  taxable_item_name: { field: "taxable_item_name", label: "业务/货物劳务", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  collection_status: { field: "collection_status", label: "收款状态", mode: "enum_multi", sortable: true, operators: ["in"] },
  bank_counterparty_name: { field: "bank_counterparty_name", label: "付款方/日期", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  bank_amount: { field: "bank_amount", label: "收款金额", mode: "money", sortable: true, operators: ["between", "equals"] },
  bank_summary: { field: "bank_summary", label: "银行/摘要", mode: "text", sortable: true, operators: ["contains"] },
  receipt_status: { field: "receipt_status", label: "收据情况", mode: "enum_multi", sortable: true, operators: ["in"] },
};

const groupHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.primary",
  fontWeight: 800,
  textAlign: "center",
  whiteSpace: "nowrap",
};

const subHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.secondary",
  fontSize: "12px",
  fontWeight: 700,
  py: 1,
  whiteSpace: "nowrap",
};

const bigSeparatorSx = {
  borderLeft: "2px solid",
  borderLeftColor: "divider",
};

const smallSeparatorSx = {
  borderLeft: "1px solid",
  borderLeftColor: "rgba(148, 163, 184, 0.28)",
};

const bodyCellSx = {
  verticalAlign: "top",
  py: 1.25,
  minWidth: 0,
  overflowWrap: "anywhere",
};

function displayInvoiceNo(row: OutputInvoiceCollectionRow) {
  const invoice = row.invoice;
  if (invoice.displayNo) {
    return invoice.displayNo;
  }
  if (invoice.digitalInvoiceNo) {
    return invoice.digitalInvoiceNo;
  }
  return [invoice.invoiceCode, invoice.invoiceNo].filter(Boolean).join(" ") || "—";
}

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "—";
  }
  return parsed.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function dateOnly(value: string) {
  if (!value) {
    return "日期为空";
  }
  return value.includes("T") ? value.split("T")[0] : value;
}

function HeaderCell({
  label,
  field,
  align,
  sx,
  filterConfigs,
  filterOptions,
  currentFilter,
  onFilterApply,
  onFilterClear,
  onSortChange,
}: {
  label: string;
  field?: string;
  align?: "left" | "right" | "center";
  sx?: SxProps<Theme>;
  filterConfigs: OutputInvoiceCollectionFilterFieldConfig[];
  filterOptions: Record<string, OutputInvoiceCollectionFilterOption[]>;
  currentFilter?: OutputInvoiceCollectionFilter | null;
  onFilterApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OutputInvoiceCollectionSortDirection) => void;
}) {
  const sxList = Array.isArray(sx) ? [subHeaderSx, ...sx] : [subHeaderSx, sx];
  const fieldConfig = field
    ? filterConfigs.find((config) => config.field === field) ?? defaultFilterConfigs[field]
    : undefined;
  return (
    <TableCell scope="col" align={align} sx={sxList}>
      <Stack
        direction="row"
        spacing={0.5}
        alignItems="center"
        justifyContent={align === "right" ? "flex-end" : "flex-start"}
        sx={{ minWidth: 0 }}
      >
        {field && fieldConfig ? (
          <OutputInvoiceCollectionFilterMenu
            fieldConfig={{ field: fieldConfig.field, label, mode: fieldConfig.mode, sortable: fieldConfig.sortable }}
            currentFilter={currentFilter as OutputInvoiceCollectionFilterValue | null}
            options={filterOptions[field] ?? []}
            onApply={onFilterApply}
            onClear={onFilterClear}
            onSort={(direction) => onSortChange(field, direction)}
          />
        ) : <span>{label}</span>}
        {field && fieldConfig?.sortable !== false ? (
          <Tooltip title={`${label} 排序`}>
            <IconButton
              aria-label={`${label} 排序`}
              size="small"
              onClick={() => onSortChange(field)}
              sx={{ p: 0.25 }}
            >
              <SortOutlinedIcon fontSize="inherit" />
            </IconButton>
          </Tooltip>
        ) : null}
      </Stack>
    </TableCell>
  );
}

function EmptyCell() {
  return <Typography color="text.secondary">—</Typography>;
}

export default function OutputInvoiceCollectionsTable({
  rows,
  page,
  pageSize,
  total,
  sortField,
  sortDirection,
  filters,
  filterConfigs,
  filterOptions,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onOpenWorkflow,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
}: OutputInvoiceCollectionsTableProps) {
  const activeSortLabel = sortField && sortDirection ? `${sortField} ${sortDirection}` : "";

  return (
    <Paper variant="outlined" sx={{ width: "100%", minWidth: 0, overflow: "hidden" }}>
      <TableContainer sx={{ width: "100%", overflowX: "hidden" }}>
        <Table
          aria-label="销项发票收款情况表"
          size="small"
          sx={{
            width: "100%",
            tableLayout: "fixed",
            "& th, & td": {
              boxSizing: "border-box",
            },
          }}
        >
          <colgroup>
            <col style={{ width: "13%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "6%" }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell colSpan={5} scope="colgroup" sx={[groupHeaderSx, { bgcolor: "#f6fbf8" }]}>
                销项发票
              </TableCell>
              <TableCell colSpan={1} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "rgba(14, 165, 233, 0.12)" }]}>
                收款状态
              </TableCell>
              <TableCell colSpan={3} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "#f5f9ff" }]}>
                收入流水
              </TableCell>
              <TableCell colSpan={1} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "#f8fafc" }]}>
                收据
              </TableCell>
            </TableRow>
            <TableRow aria-label={activeSortLabel || undefined}>
              <HeaderCell label="发票号码" field="invoice_no" filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "invoice_no")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="购方" field="buyer_name" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "buyer_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="价税合计" field="total_with_tax" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "total_with_tax")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="税额/税率" field="tax_amount" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "tax_amount")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="业务/货物劳务" field="taxable_item_name" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "taxable_item_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="收款状态" field="collection_status" sx={[bigSeparatorSx, { bgcolor: "rgba(14, 165, 233, 0.10)" }]} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "collection_status")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="付款方/日期" field="bank_counterparty_name" sx={bigSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_counterparty_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="收款金额" field="bank_amount" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_amount")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="银行/摘要" field="bank_summary" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_summary")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="收据情况" field="receipt_status" sx={bigSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "receipt_status")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} align="center" sx={{ py: 6, color: "text.secondary" }}>
                  当前条件下没有销项发票收款记录。
                </TableCell>
              </TableRow>
            ) : rows.map((row) => {
              const invoiceNo = displayInvoiceNo(row);
              const invoiceCellExpanded = expandedCells.has(`${row.id}:invoice-business`);
              const statusCellExpanded = expandedCells.has(`${row.id}:collection-status`);
              const bankNameCellExpanded = expandedCells.has(`${row.id}:bank-name`);
              const bankSummaryCellExpanded = expandedCells.has(`${row.id}:bank-summary`);
              const bank = row.bank.primary;
              return (
                <TableRow key={row.id} hover>
                  <TableCell sx={bodyCellSx}>
                    <Typography component="div" variant="body2" fontWeight={800} title={invoiceNo}>
                      {invoiceNo}
                    </Typography>
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.75, flexWrap: "wrap" }}>
                      <Chip label={dateOnly(row.invoice.issueDate)} size="small" variant="outlined" />
                      <Button
                        size="small"
                        variant="text"
                        aria-label={`查看发票 ${invoiceNo} 详情`}
                        onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
                        sx={{ minWidth: 0, px: 0.75 }}
                      >
                        详情
                      </Button>
                    </Stack>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={700}>
                      {row.invoice.buyerName || "—"}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
                      {row.invoice.buyerTaxNo || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx, { fontVariantNumeric: "tabular-nums", fontWeight: 800 }]}>
                    {formatMoney(row.invoice.totalWithTax)}
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                      {formatMoney(row.invoice.taxAmount)}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary">
                      {row.invoice.taxRate || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={700}>
                      {row.invoice.specificBusinessType || "—"}
                    </Typography>
                    <ExpandableCellText
                      text={row.invoice.taxableItemName}
                      expanded={invoiceCellExpanded}
                      onToggle={() => onToggleCellExpand(row.id, "invoice-business")}
                      threshold={18}
                    />
                  </TableCell>
                  <TableCell
                    className="output-invoice-collection-status-cell"
                    sx={[bodyCellSx, bigSeparatorSx, { bgcolor: "rgba(14, 165, 233, 0.12)" }]}
                  >
                    <Chip color="info" label={row.collectionStatus.label || "待处理"} size="small" />
                    <Stack spacing={0.5} sx={{ mt: 0.75 }}>
                      <Typography component="div" variant="caption" color="text.secondary">
                        已收 {formatMoney(row.collectionStatus.collectedAmount)} / 待收 {formatMoney(row.collectionStatus.pendingAmount)}
                      </Typography>
                      <ExpandableCellText
                        text={row.collectionStatus.reason}
                        expanded={statusCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "collection-status")}
                        threshold={24}
                      />
                      <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => onOpenWorkflow({ kind: "collectionStatus", rowId: row.id })}
                          sx={{ minWidth: 0, px: 0.75 }}
                        >
                          状态/提醒
                        </Button>
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => onOpenWorkflow({ kind: "redRelation", rowId: row.id })}
                          sx={{ minWidth: 0, px: 0.75 }}
                        >
                          红蓝票
                        </Button>
                      </Stack>
                    </Stack>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, bigSeparatorSx]}>
                    {bank ? (
                      <>
                        <ExpandableCellText
                          text={bank.counterpartyName}
                          expanded={bankNameCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-name")}
                        />
                        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.75, flexWrap: "wrap" }}>
                          <Chip label={bank.tradeTime || "收款日期为空"} size="small" variant="outlined" />
                          {bank.detailAvailable ? (
                            <Button
                              size="small"
                              variant="text"
                              aria-label={`查看流水 ${bank.counterpartyName || bank.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "bank", id: bank.id, rowId: row.id })}
                              sx={{ minWidth: 0, px: 0.75 }}
                            >
                              详情
                            </Button>
                          ) : null}
                        </Stack>
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx]}>
                    {bank ? (
                      <>
                        <Typography component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                          {formatMoney(row.bank.hasMultiple && row.bank.receivedTotal ? row.bank.receivedTotal : bank.amount)}
                        </Typography>
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end" sx={{ mt: 0.75, flexWrap: "wrap" }}>
                          {row.bank.hasMultiple ? (
                            <Chip label="多笔" size="small" color="info" variant="outlined" />
                          ) : null}
                          <Chip label={bank.directionLabel || "收入"} size="small" variant="outlined" />
                        </Stack>
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    {bank ? (
                      <>
                        <Typography component="div" variant="body2" fontWeight={800}>
                          {bank.bankName || "—"} {bank.accountLast4 || ""}
                        </Typography>
                        <ExpandableCellText
                          text={bank.summary || bank.remark}
                          expanded={bankSummaryCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-summary")}
                        />
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell sx={[bodyCellSx, bigSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={800}>
                      {row.receipt.label || "—"}
                    </Typography>
                    <Stack spacing={0.5} sx={{ mt: 0.75 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => onOpenWorkflow({ kind: "receiptHistory", invoiceId: row.invoice.id, rowId: row.id })}
                      >
                        已出收据
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        disabled={!row.receipt.previewAvailable}
                        onClick={() => onOpenWorkflow({ kind: "receiptPreview", rowId: row.id })}
                      >
                        待出收据
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={Math.max(0, page - 1)}
        rowsPerPage={pageSize}
        rowsPerPageOptions={[20, 50, 100]}
        labelRowsPerPage="每页行数"
        labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
        onPageChange={(_event, nextPage) => onPageChange(nextPage + 1)}
        onRowsPerPageChange={(event) => onPageSizeChange(Number(event.target.value))}
      />
    </Paper>
  );
}
