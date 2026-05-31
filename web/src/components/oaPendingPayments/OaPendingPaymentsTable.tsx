import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import SortOutlinedIcon from "@mui/icons-material/SortOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

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
  { id: "accountDetailNo", label: "账户明细编号-交易流水号", width: 190 },
  { id: "enterpriseSerialNo", label: "企业流水号", width: 130 },
  { id: "voucherKind", label: "凭证种类", width: 130 },
  { id: "voucherNo", label: "凭证号", width: 130 },
  { id: "oaApplicant", label: "OA申请人", field: "oa_applicant", width: 130, filterable: true },
  { id: "applicationType", label: "类型", width: 95 },
  { id: "projectName", label: "项目名称", width: 220 },
  { id: "oaAmount", label: "金额", width: 105, align: "right" },
  { id: "oaDetail", label: "OA详情", width: 92 },
  { id: "paymentStatus", label: "支付状态", width: 150 },
  { id: "bankName", label: "支出银行", width: 115 },
  { id: "accountName", label: "账户名称", width: 170 },
  { id: "tradeTime", label: "交易时间", field: "bank_trade_time", width: 165, sortable: true },
  { id: "debitAmount", label: "借方发生额（支取）", width: 150, align: "right" },
  { id: "creditAmount", label: "贷方发生额（收入）", width: 150, align: "right" },
  { id: "balance", label: "余额", width: 120, align: "right" },
  { id: "currency", label: "币种", width: 90 },
  { id: "counterpartyName", label: "对方户名", width: 190 },
  { id: "counterpartyAccountNo", label: "对方账号", width: 170 },
  { id: "counterpartyBankName", label: "对方开户机构", width: 220 },
  { id: "bookedDate", label: "记账日期", width: 110 },
  { id: "summary", label: "摘要", width: 150 },
  { id: "remark", label: "备注", width: 240 },
  { id: "digitalInvoiceNo", label: "数电发票号码", width: 185 },
  { id: "sellerName", label: "销方名称", width: 190 },
  { id: "invoiceDate", label: "开票日期", width: 115 },
  { id: "totalWithTax", label: "价税合计", width: 120, align: "right" },
];

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
}: OaPendingPaymentsTableProps) {
  const configsByField = new Map(filterConfigs.map((config) => [config.field, config]));

  return (
    <Paper variant="outlined" sx={{ borderRadius: 1, overflow: "hidden" }}>
      <TableContainer sx={{ maxHeight: "calc(100vh - 280px)", minHeight: 360 }}>
        <Table stickyHeader size="small" aria-label="OA待付款核对表格" sx={{ minWidth: 3480, tableLayout: "fixed" }}>
          <TableHead>
            <TableRow>
              <GroupHeader label="凭证信息" colSpan={4} />
              <GroupHeader label="OA情况" colSpan={5} />
              <GroupHeader label="支付状态" colSpan={1} />
              <GroupHeader label="支出流水" colSpan={13} />
              <GroupHeader label="发票情况" colSpan={4} />
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
                        aria-label={`${column.label} 排序`}
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
                <ClipCell value={row.bankTransaction.accountDetailNo} />
                <ClipCell value={row.bankTransaction.enterpriseSerialNo} />
                <ClipCell value={row.bankTransaction.voucherKind} />
                <ClipCell value={row.bankTransaction.voucherNo} />
                <ClipCell value={row.oa.applicantName} />
                <ClipCell value={row.oa.applicationType} />
                <ClipCell value={row.oa.projectName} />
                <ClipCell value={row.oa.amount} align="right" />
                <TableCell>
                  <Tooltip title="查看OA详情">
                    <span>
                      <Button
                        aria-label={`查看 OA ${row.oa.applicantName} 详情`}
                        disabled={!row.oa.detailAvailable}
                        size="small"
                        startIcon={<OpenInNewOutlinedIcon fontSize="small" />}
                        onClick={() => onOpenDetail({ kind: "oa", id: row.oa.id })}
                      >
                        详情
                      </Button>
                    </span>
                  </Tooltip>
                </TableCell>
                <TableCell className="oa-pending-payment-status-cell">
                  <Chip
                    label={row.paymentStatus.label}
                    color={statusColor(row.paymentStatus.severity)}
                    size="small"
                    variant={row.paymentStatus.code === "paid" || row.paymentStatus.code === "merged_paid" ? "filled" : "outlined"}
                  />
                </TableCell>
                <DetailCell
                  value={row.bankTransaction.bankName}
                  label={bankDetailLabel(row)}
                  disabled={!bankDetailTarget(row)}
                  onClick={() => {
                    const target = bankDetailTarget(row);
                    if (target) {
                      onOpenDetail(target);
                    }
                  }}
                />
                <ClipCell value={row.bankTransaction.accountName} />
                <ClipCell value={row.bankTransaction.tradeTime} />
                <ClipCell value={row.bankTransaction.debitAmount} align="right" />
                <ClipCell value={row.bankTransaction.creditAmount} align="right" />
                <ClipCell value={row.bankTransaction.balance} align="right" />
                <ClipCell value={row.bankTransaction.currency} />
                <ClipCell value={row.bankTransaction.counterpartyName} />
                <ClipCell value={row.bankTransaction.counterpartyAccountNo} />
                <ClipCell value={row.bankTransaction.counterpartyBankName} />
                <ClipCell value={row.bankTransaction.bookedDate} />
                <ClipCell value={row.bankTransaction.summary} />
                <ClipCell value={row.bankTransaction.remark} />
                <DetailCell
                  value={row.invoice.digitalInvoiceNo}
                  label={invoiceDetailLabel(row)}
                  disabled={!invoiceDetailTarget(row)}
                  onClick={() => {
                    const target = invoiceDetailTarget(row);
                    if (target) {
                      onOpenDetail(target);
                    }
                  }}
                />
                <ClipCell value={row.invoice.sellerName} />
                <ClipCell value={row.invoice.invoiceDate} />
                <ClipCell value={row.invoice.totalWithTax} align="right" />
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

function ClipCell({ value, align }: { value: string | number | null | undefined; align?: "right" | "left" }) {
  const text = value == null || value === "" ? "-" : String(value);
  return (
    <TableCell align={align}>
      <Tooltip title={text === "-" ? "" : text}>
        <Typography component="span" variant="body2" noWrap sx={{ display: "block" }}>
          {text}
        </Typography>
      </Tooltip>
    </TableCell>
  );
}

function DetailCell({
  value,
  label,
  disabled,
  onClick,
}: {
  value: string | number | null | undefined;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  const text = value == null || value === "" ? "-" : String(value);
  return (
    <TableCell>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
        <Tooltip title={text === "-" ? "" : text}>
          <Typography component="span" variant="body2" noWrap sx={{ display: "block", minWidth: 0, flex: 1 }}>
            {text}
          </Typography>
        </Tooltip>
        <Tooltip title={label}>
          <span>
            <Button
              aria-label={label}
              disabled={disabled}
              size="small"
              onClick={onClick}
              sx={{ minWidth: 32, px: 0.75 }}
            >
              详情
            </Button>
          </span>
        </Tooltip>
      </Box>
    </TableCell>
  );
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
