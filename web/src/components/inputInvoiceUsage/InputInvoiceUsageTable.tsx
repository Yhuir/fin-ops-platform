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
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageFilterFieldConfig,
  InputInvoiceUsageFilterOption,
  InputInvoiceUsageRow,
  InputInvoiceUsageSortDirection,
} from "../../features/inputInvoiceUsage/types";
import ExpandableCellText from "./ExpandableCellText";
import InputInvoiceUsageFilterMenu, { type InputInvoiceUsageFilterValue } from "./InputInvoiceUsageFilterMenu";

type InputInvoiceUsageTableProps = {
  rows: InputInvoiceUsageRow[];
  page: number;
  pageSize: number;
  total: number;
  sortField: string;
  sortDirection: InputInvoiceUsageSortDirection | "";
  filters: InputInvoiceUsageFilter[];
  filterConfigs: InputInvoiceUsageFilterFieldConfig[];
  filterOptions: Record<string, InputInvoiceUsageFilterOption[]>;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: InputInvoiceUsageDetailTarget) => void;
  onFilterApply: (filter: InputInvoiceUsageFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: InputInvoiceUsageSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

const defaultFilterConfigs: Record<string, InputInvoiceUsageFilterFieldConfig> = {
  invoice_no: { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
  seller_name: { field: "seller_name", label: "销方", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  total_with_tax: { field: "total_with_tax", label: "价税合计", mode: "money", sortable: true, operators: ["between", "equals"] },
  amount: { field: "amount", label: "不含税金额", mode: "money", sortable: true, operators: ["between", "equals"] },
  taxable_item_name: { field: "taxable_item_name", label: "业务/货物劳务", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  payment_status: { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
  oa_applicant: { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
  oa_project_name: { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  bank_counterparty_name: { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
  bank_amount: { field: "bank_amount", label: "流水金额", mode: "money", sortable: true, operators: ["between", "equals"] },
  bank_summary: { field: "bank_summary", label: "摘要/备注", mode: "text", sortable: true, operators: ["contains"] },
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

function displayInvoiceNo(row: InputInvoiceUsageRow) {
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
  filterConfigs: InputInvoiceUsageFilterFieldConfig[];
  filterOptions: Record<string, InputInvoiceUsageFilterOption[]>;
  currentFilter?: InputInvoiceUsageFilter | null;
  onFilterApply: (filter: InputInvoiceUsageFilterValue) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: InputInvoiceUsageSortDirection) => void;
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
          <InputInvoiceUsageFilterMenu
            fieldConfig={{ field: fieldConfig.field, label, mode: fieldConfig.mode, sortable: fieldConfig.sortable }}
            currentFilter={currentFilter as InputInvoiceUsageFilterValue | null}
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

export default function InputInvoiceUsageTable({
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
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
}: InputInvoiceUsageTableProps) {
  const activeSortLabel = sortField && sortDirection ? `${sortField} ${sortDirection}` : "";

  return (
    <Paper variant="outlined" sx={{ width: "100%", minWidth: 0, overflow: "hidden" }}>
      <TableContainer sx={{ width: "100%", overflowX: "hidden" }}>
        <Table
          aria-label="进项发票使用情况表"
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
            <col style={{ width: "12%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "9%" }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell colSpan={5} scope="colgroup" sx={[groupHeaderSx, { bgcolor: "#f6fbf8" }]}>
                进项发票
              </TableCell>
              <TableCell colSpan={1} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "rgba(255, 193, 7, 0.16)" }]}>
                支付状态
              </TableCell>
              <TableCell colSpan={2} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "#f8fafc" }]}>
                OA
              </TableCell>
              <TableCell colSpan={3} scope="colgroup" sx={[groupHeaderSx, bigSeparatorSx, { bgcolor: "#f5f9ff" }]}>
                流水
              </TableCell>
            </TableRow>
            <TableRow aria-label={activeSortLabel || undefined}>
              <HeaderCell label="发票号码" field="invoice_no" filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "invoice_no")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="销方" field="seller_name" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "seller_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="价税合计" field="total_with_tax" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "total_with_tax")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="不含税/税率税额" field="amount" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "amount")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="业务/货物劳务" field="taxable_item_name" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "taxable_item_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="支付状态" field="payment_status" sx={[bigSeparatorSx, { bgcolor: "rgba(255, 193, 7, 0.12)" }]} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "payment_status")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="OA申请人" field="oa_applicant" sx={bigSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "oa_applicant")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="项目名称" field="oa_project_name" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "oa_project_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="对方户名" field="bank_counterparty_name" sx={bigSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_counterparty_name")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="金额" field="bank_amount" align="right" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_amount")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
              <HeaderCell label="摘要/备注" field="bank_summary" sx={smallSeparatorSx} filterConfigs={filterConfigs} filterOptions={filterOptions} currentFilter={filters.find((filter) => filter.field === "bank_summary")} onFilterApply={onFilterApply} onFilterClear={onFilterClear} onSortChange={onSortChange} />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={11} align="center" sx={{ py: 6, color: "text.secondary" }}>
                  当前条件下没有进项发票使用记录。
                </TableCell>
              </TableRow>
            ) : rows.map((row) => {
              const invoiceNo = displayInvoiceNo(row);
              const invoiceCellExpanded = expandedCells.has(`${row.id}:invoice-business`);
              const paymentCellExpanded = expandedCells.has(`${row.id}:payment-status`);
              const projectCellExpanded = expandedCells.has(`${row.id}:oa-project`);
              const bankNameCellExpanded = expandedCells.has(`${row.id}:bank-name`);
              const bankRemarkCellExpanded = expandedCells.has(`${row.id}:bank-remark`);
              const oa = row.oa.primary;
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
                      {row.invoice.sellerName || "—"}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
                      {row.invoice.sellerTaxNo || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx, { fontVariantNumeric: "tabular-nums", fontWeight: 800 }]}>
                    {formatMoney(row.invoice.totalWithTax)}
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                      {formatMoney(row.invoice.amountWithoutTax)}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary">
                      {row.invoice.taxRate || "—"} ({formatMoney(row.invoice.taxAmount)})
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
                    />
                  </TableCell>
                  <TableCell
                    className="input-invoice-usage-payment-cell"
                    sx={[bodyCellSx, bigSeparatorSx, { bgcolor: "rgba(255, 193, 7, 0.14)" }]}
                  >
                    <Chip color="warning" label={row.paymentStatus.label || "待处理"} size="small" />
                    <Box sx={{ mt: 0.75 }}>
                      <ExpandableCellText
                        text={row.paymentStatus.reason}
                        expanded={paymentCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "payment-status")}
                        threshold={22}
                      />
                    </Box>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, bigSeparatorSx]}>
                    {oa ? (
                      <>
                        <Typography component="div" variant="body2" fontWeight={800}>
                          {oa.applicant || "—"}
                        </Typography>
                        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.75, flexWrap: "wrap" }}>
                          <Chip label={oa.applicationType || "类型为空"} size="small" variant="outlined" />
                          {oa.detailAvailable ? (
                            <Button
                              size="small"
                              variant="text"
                              aria-label={`查看OA ${oa.applicant || oa.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "oa", id: oa.id, rowId: row.id })}
                              sx={{ minWidth: 0, px: 0.75 }}
                            >
                              详情
                            </Button>
                          ) : null}
                        </Stack>
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    {oa ? (
                      <ExpandableCellText
                        text={oa.projectName}
                        expanded={projectCellExpanded}
                        onToggle={() => onToggleCellExpand(row.id, "oa-project")}
                      />
                    ) : <EmptyCell />}
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
                          <Chip label={bank.tradeTime || "交易日期为空"} size="small" variant="outlined" />
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
                          {formatMoney(bank.amount)}
                        </Typography>
                        <Chip
                          label={`${bank.directionLabel || "收/支"} ${bank.bankName || "银行"} ${bank.accountLast4 || "----"}`}
                          size="small"
                          variant="outlined"
                          sx={{ mt: 0.75 }}
                        />
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    {bank ? (
                      <>
                        <Typography component="div" variant="body2" fontWeight={700}>
                          {bank.summary || "—"}
                        </Typography>
                        <ExpandableCellText
                          text={bank.remark}
                          expanded={bankRemarkCellExpanded}
                          onToggle={() => onToggleCellExpand(row.id, "bank-remark")}
                        />
                      </>
                    ) : <EmptyCell />}
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
