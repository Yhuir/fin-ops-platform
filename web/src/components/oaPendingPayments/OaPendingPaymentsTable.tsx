import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
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
import type { MutableRefObject } from "react";

import InputInvoiceUsageFilterMenu from "../inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import type { InputInvoiceUsageFilterValue } from "../inputInvoiceUsage/InputInvoiceUsageFilterMenu";
import type {
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFieldConfig,
  OaPendingPaymentFilter,
  OaPendingPaymentFilterOption,
  OaPendingPaymentRow,
  OaPendingPaymentSortDirection,
} from "../../features/oaPendingPayments/types";

type OaPendingPaymentsTableProps = {
  rows: OaPendingPaymentRow[];
  page: number;
  pageSize: number;
  total: number;
  filterConfigs: OaPendingPaymentFieldConfig[];
  filterOptions: Record<string, OaPendingPaymentFilterOption[]>;
  filters: OaPendingPaymentFilter[];
  onFilterApply: (filter: { field: string; operator: string; value?: string | null; values?: string[] }) => void;
  onFilterClear: (field: string) => void;
  onSortChange: (field: string, direction?: OaPendingPaymentSortDirection) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenDetail: (target: OaPendingPaymentDetailTarget) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

type OaPendingPaymentColumn = {
  id: string;
  label: string;
  width: number;
  align?: "left" | "right";
  field?: string;
  filterable?: boolean;
  sortable?: boolean;
};

const columns: OaPendingPaymentColumn[] = [
  { id: "oaApplicant", label: "OA申请人", field: "oa_applicant", width: 170, filterable: true },
  { id: "projectName", label: "项目名称", width: 220 },
  { id: "oaAmount", label: "金额", width: 120, align: "right" },
  { id: "paymentStatus", label: "支付状态", width: 150 },
  { id: "bankCounterparty", label: "对方户名/交易时间", field: "bank_trade_time", width: 230, sortable: true },
  { id: "bankAmountAccount", label: "金额/账户", width: 170, align: "right" },
  { id: "bankSummaryRemark", label: "摘要/备注", width: 300 },
  { id: "invoiceNoParty", label: "发票号码/发票方", width: 240 },
  { id: "invoiceDate", label: "日期", width: 120 },
  { id: "totalWithTax", label: "价税合计", width: 130, align: "right" },
];

const bodyCellSx = {
  verticalAlign: "top",
  fontSize: "12px",
  lineHeight: 1.35,
  py: 0.85,
  minWidth: 0,
  overflowWrap: "anywhere",
};

const denseChipSx = {
  height: 22,
  maxWidth: "100%",
  "& .MuiChip-label": {
    fontSize: "11px",
    px: 0.75,
  },
};

export default function OaPendingPaymentsTable({
  rows,
  page,
  pageSize,
  total,
  filterConfigs,
  filterOptions,
  filters,
  onFilterApply,
  onFilterClear,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onOpenDetail,
  tableWrapRef,
}: OaPendingPaymentsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));

  return (
    <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
      <TableContainer ref={tableWrapRef} sx={{ maxHeight: "calc(100vh - 280px)", minHeight: 360 }}>
        <Table stickyHeader size="small" aria-label="OA待付款核对表格" sx={{ minWidth: 1690, tableLayout: "fixed" }}>
          <TableHead>
            <TableRow>
              <GroupHeader label="OA情况" colSpan={3} />
              <GroupHeader label="支付状态" colSpan={1} />
              <GroupHeader label="支出流水" colSpan={3} />
              <GroupHeader label="发票情况" colSpan={3} />
            </TableRow>
            <TableRow>
              {columns.map((column) => {
                const field = column.field;
                const config = field ? configsByField.get(field) : undefined;
                const currentFilter = field
                  ? filters.find((filter) => filter.field === field) as InputInvoiceUsageFilterValue | undefined
                  : null;
                return (
                  <TableCell
                    key={column.id}
                    align={column.align === "right" ? "right" : "left"}
                    sx={{
                      top: 33,
                      width: column.width,
                      minWidth: column.width,
                      maxWidth: column.width,
                      bgcolor: "background.paper",
                      fontWeight: 900,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {column.filterable && config ? (
                      <InputInvoiceUsageFilterMenu
                        fieldConfig={config}
                        currentFilter={currentFilter}
                        options={field ? filterOptions[field] ?? [] : []}
                        onApply={onFilterApply}
                        onClear={onFilterClear}
                        onSort={(direction) => field && onSortChange(field, direction)}
                      />
                    ) : column.sortable && field ? (
                      <Button
                        aria-label={`${column.id === "bankCounterparty" ? "交易时间" : column.label} 排序`}
                        color="inherit"
                        size="small"
                        startIcon={<SortOutlinedIcon fontSize="small" />}
                        onClick={() => onSortChange(field)}
                        sx={{ justifyContent: "flex-start", minWidth: 0, px: 0.5 }}
                      >
                        <Typography component="span" variant="inherit" noWrap>{column.label}</Typography>
                      </Button>
                    ) : (
                      column.label
                    )}
                  </TableCell>
                );
              })}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id} hover>
                <TableCell sx={bodyCellSx}>
                  <Stack direction="row" spacing={0.25} alignItems="center" sx={{ minWidth: 0 }}>
                    <TextLine value={row.oa.applicantName} strong />
                    <DetailIconButton
                      label={`查看 OA ${row.oa.applicantName} 详情`}
                      disabled={!row.oa.detailAvailable}
                      onClick={() => onOpenDetail({ kind: "oa", id: row.oa.id })}
                    />
                  </Stack>
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.45, flexWrap: "wrap" }}>
                    <Chip label={row.oa.applicationType || "类型为空"} size="small" variant="outlined" sx={denseChipSx} />
                  </Stack>
                </TableCell>
                <TableCell sx={bodyCellSx}>
                  <TextLine value={row.oa.projectName} />
                </TableCell>
                <TableCell align="right" sx={bodyCellSx}>
                  <TextLine value={row.oa.amount} strong numeric />
                </TableCell>
                <TableCell className="oa-pending-payment-status-cell">
                  <Chip
                    label={row.paymentStatus.label}
                    color={statusColor(row.paymentStatus.severity)}
                    size="small"
                    variant={row.paymentStatus.code === "paid" || row.paymentStatus.code === "merged_paid" ? "filled" : "outlined"}
                  />
                </TableCell>
                <TableCell sx={bodyCellSx}>
                  <TextLine value={row.bankTransaction.counterpartyName} strong />
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.45, flexWrap: "wrap" }}>
                    <Chip label={row.bankTransaction.tradeTime || "交易时间为空"} size="small" variant="outlined" sx={denseChipSx} />
                  </Stack>
                </TableCell>
                <TableCell align="right" sx={bodyCellSx}>
                  <Stack direction="row" spacing={0.25} alignItems="center" justifyContent="flex-end" sx={{ minWidth: 0 }}>
                    <TextLine value={bankAmount(row)} strong numeric />
                    <Chip label={row.bankTransaction.directionLabel || "支出"} size="small" variant="outlined" sx={denseChipSx} />
                    <DetailIconButton
                      label={bankDetailLabel(row)}
                      disabled={!bankDetailTarget(row)}
                      onClick={() => {
                        const target = bankDetailTarget(row);
                        if (target) {
                          onOpenDetail(target);
                        }
                      }}
                    />
                  </Stack>
                  <Chip label={bankAccountLabel(row)} size="small" variant="outlined" sx={{ ...denseChipSx, mt: 0.45 }} />
                </TableCell>
                <TableCell sx={bodyCellSx}>
                  <MultiLineValue value={combinedBankSummaryRemark(row)} />
                </TableCell>
                <TableCell sx={bodyCellSx}>
                  <Stack direction="row" spacing={0.25} alignItems="center" sx={{ minWidth: 0 }}>
                    <TextLine value={row.invoice.digitalInvoiceNo} strong />
                    <DetailIconButton
                      label={invoiceDetailLabel(row)}
                      disabled={!invoiceDetailTarget(row)}
                      onClick={() => {
                        const target = invoiceDetailTarget(row);
                        if (target) {
                          onOpenDetail(target);
                        }
                      }}
                    />
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.35 }}>
                    进项发票方名称
                  </Typography>
                  <TextLine value={row.invoice.sellerName} />
                </TableCell>
                <TableCell sx={bodyCellSx}>
                  <TextLine value={row.invoice.invoiceDate} />
                </TableCell>
                <TableCell align="right" sx={bodyCellSx}>
                  <TextLine value={row.invoice.totalWithTax} strong numeric />
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length}>
                  <Box sx={{ py: 6, textAlign: "center" }}>
                    <Typography color="text.secondary">暂无 OA 待付款核对数据</Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={Math.max(page - 1, 0)}
        rowsPerPage={pageSize}
        rowsPerPageOptions={[20, 50, 100]}
        labelRowsPerPage="每页"
        onPageChange={(_event, nextPage) => onPageChange(nextPage + 1)}
        onRowsPerPageChange={(event) => onPageSizeChange(Number(event.target.value))}
      />
    </Paper>
  );
}

function GroupHeader({ label, colSpan }: { label: string; colSpan: number }) {
  return (
    <TableCell
      align="center"
      colSpan={colSpan}
      sx={{
        bgcolor: "grey.100",
        borderRight: "1px solid",
        borderColor: "divider",
        fontWeight: 900,
        top: 0,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </TableCell>
  );
}

function TextLine({
  value,
  strong = false,
  numeric = false,
}: {
  value: string | number | null | undefined;
  strong?: boolean;
  numeric?: boolean;
}) {
  const text = value == null || value === "" ? "-" : String(value);
  return (
    <Tooltip title={text === "-" ? "" : text}>
      <Typography
        component="span"
        variant="body2"
        sx={{
          display: "block",
          minWidth: 0,
          fontSize: "12px",
          fontWeight: strong ? 800 : 400,
          fontVariantNumeric: numeric ? "tabular-nums" : undefined,
          lineHeight: 1.35,
          overflowWrap: "anywhere",
        }}
      >
        {text}
      </Typography>
    </Tooltip>
  );
}

function MultiLineValue({ value }: { value: string }) {
  const text = value || "-";
  return (
    <Tooltip title={text === "-" ? "" : text}>
      <Typography
        component="span"
        variant="body2"
        sx={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 4,
          overflow: "hidden",
          fontSize: "12px",
          lineHeight: 1.4,
          overflowWrap: "anywhere",
          whiteSpace: "pre-line",
        }}
      >
        {text}
      </Typography>
    </Tooltip>
  );
}

function DetailIconButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip title={label}>
      <span>
        <IconButton
          aria-label={label}
          disabled={disabled}
          size="small"
          onClick={onClick}
          sx={{ flexShrink: 0, p: 0.25 }}
        >
          <InfoOutlinedIcon fontSize="inherit" />
        </IconButton>
      </span>
    </Tooltip>
  );
}

function bankAmount(row: OaPendingPaymentRow): string {
  return row.bankTransaction.amount || row.bankTransaction.paidTotal || row.bankTransaction.debitAmount || row.bankTransaction.creditAmount || "";
}

function bankAccountLabel(row: OaPendingPaymentRow): string {
  const bankName = row.bankTransaction.bankName || "银行";
  const last4 = row.bankTransaction.accountLast4 || accountLast4(row.bankTransaction.accountNo);
  return [bankName, last4].filter(Boolean).join(" ") || "-";
}

function accountLast4(value: string | undefined): string {
  const text = String(value || "").trim();
  return text.length >= 4 ? text.slice(-4) : "";
}

function combinedBankSummaryRemark(row: OaPendingPaymentRow): string {
  const summaries = row.bankTransaction.summaries?.length
    ? row.bankTransaction.summaries
    : [{
      summary: row.bankTransaction.summary,
      remark: row.bankTransaction.remark,
    }];
  const seen = new Set<string>();
  const lines: string[] = [];
  summaries.forEach((summary) => {
    [summary.summary, summary.remark].forEach((part) => {
      const text = String(part || "").trim();
      if (!text || seen.has(text)) {
        return;
      }
      seen.add(text);
      lines.push(text);
    });
  });
  return lines.join("\n");
}

function bankDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.bankTransaction.detailMode === "single" && row.bankTransaction.primaryBankTransactionId) {
    return { kind: "bank", id: row.bankTransaction.primaryBankTransactionId };
  }
  if (row.bankTransaction.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "bank" };
  }
  return null;
}

function invoiceDetailTarget(row: OaPendingPaymentRow): OaPendingPaymentDetailTarget | null {
  if (row.invoice.detailMode === "single" && row.invoice.primaryInvoiceId) {
    return { kind: "invoice", id: row.invoice.primaryInvoiceId };
  }
  if (row.invoice.detailMode === "list") {
    return { kind: "relationList", id: row.id, rowId: row.id, relationKind: "invoice" };
  }
  return null;
}

function bankDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.bankTransaction.detailMode === "list") {
    return `查看${applicant}关联流水 ${row.bankTransaction.relationCount} 条`;
  }
  return `查看流水 ${applicant} 详情`;
}

function invoiceDetailLabel(row: OaPendingPaymentRow): string {
  const applicant = row.oa.applicantName || "该OA";
  if (row.invoice.detailMode === "list") {
    return `查看${applicant}关联发票 ${row.invoice.relationCount} 张`;
  }
  return `查看发票 ${applicant} 详情`;
}

function statusColor(severity: string | undefined) {
  if (severity === "success") {
    return "success";
  }
  if (severity === "error") {
    return "error";
  }
  if (severity === "warning") {
    return "warning";
  }
  return "default";
}
