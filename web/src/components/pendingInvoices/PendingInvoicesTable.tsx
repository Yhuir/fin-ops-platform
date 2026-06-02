import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import type { ReactNode } from "react";

import type {
  PendingInvoiceObjectDetailTarget,
  PendingInvoicePrimaryAction,
  PendingInvoiceDirection,
  PendingInvoiceRow,
  PendingInvoiceSortDirection,
  PendingInvoiceSortField,
  PendingInvoiceStatusSeverity,
} from "../../features/pendingInvoices/types";

export type PendingInvoicesTableConfig = {
  sortField: PendingInvoiceSortField;
  sortDirection: PendingInvoiceSortDirection;
};

type PendingInvoicesTableProps = {
  rows: PendingInvoiceRow[];
  config: PendingInvoicesTableConfig;
  onSortChange: (field: PendingInvoiceSortField) => void;
  onOpenRelation: (row: PendingInvoiceRow) => void;
  onOpenInvoicePicker: (row: PendingInvoiceRow) => void;
  onOpenManualInvoice: (row: PendingInvoiceRow) => void;
  onOpenObjectDetail: (target: PendingInvoiceObjectDetailTarget) => void;
  onMarkIncomeStatus: (row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => void;
  direction: PendingInvoiceDirection;
  statusFilterControl: ReactNode;
  actionsDisabled?: boolean;
};

const GROUP_BORDER = "2px solid";
const CELL_BORDER = "1px solid";

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "-";
  }
  return parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function invoiceNumber(row: NonNullable<PendingInvoiceRow["inputInvoices"]["primary"]>) {
  return row.digitalInvoiceNo || [row.invoiceCode, row.invoiceNo].filter(Boolean).join(" ") || row.invoiceNo || "-";
}

function bankAccountLabel(row: PendingInvoiceRow["bankTransaction"]) {
  return [row.bankShortName || row.bankName, row.accountLast4].filter(Boolean).join(" ") || "-";
}

function numericAmount(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function rowMoneyDirection(row: PendingInvoiceRow, direction: PendingInvoiceDirection) {
  if (direction === "income") {
    return "income";
  }
  if (direction === "expense") {
    return "expense";
  }
  return numericAmount(row.bankTransaction.creditAmount) > 0 && numericAmount(row.bankTransaction.debitAmount) <= 0 ? "income" : "expense";
}

function tagPathLabel(row: PendingInvoiceRow["bankTransaction"]) {
  const path = row.effectiveTagLabelPath.map((item) => item.trim()).filter(Boolean);
  if (path.length > 0) {
    return path.join(" / ");
  }
  return [row.effectiveTagPrimaryLabel, row.effectiveTagSubLabel]
    .map((item) => item?.trim())
    .filter(Boolean)
    .join(" / ") || row.effectiveTagLabel || row.effectiveTagCode || "未标注";
}

function overflowText(expanded: boolean): Record<string, string | number> {
  return expanded ? {
    whiteSpace: "normal",
    wordBreak: "break-word",
  } : {
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
    wordBreak: "break-word",
  };
}

function chipColor(severity: PendingInvoiceStatusSeverity): "default" | "primary" | "success" | "warning" | "error" | "info" {
  switch (severity) {
    case "success":
      return "success";
    case "warning":
      return "warning";
    case "error":
      return "error";
    case "info":
      return "info";
    default:
      return "default";
  }
}

function sortableLabel(
  label: string,
  field: PendingInvoiceSortField,
  config: PendingInvoicesTableConfig,
  onSortChange: (field: PendingInvoiceSortField) => void,
) {
  return (
    <TableSortLabel
      active={config.sortField === field}
      direction={config.sortField === field ? config.sortDirection : "asc"}
      onClick={() => onSortChange(field)}
    >
      {label}
    </TableSortLabel>
  );
}

function shouldOpenRelation(action: PendingInvoicePrimaryAction) {
  return ["view_relation", "view_payment_detail", "view_accumulated", "view_payment_history"].includes(action);
}

function shouldOpenInvoicePicker(action: PendingInvoicePrimaryAction) {
  return ["attach_existing_invoice", "choose_invoice", "select_invoice"].includes(action);
}

function shouldOpenManualInvoice(action: PendingInvoicePrimaryAction) {
  return ["manual_invoice", "create_invoice"].includes(action);
}

function canOpenOaDetail(row: PendingInvoiceRow) {
  const primaryOa = row.oa.primary;
  return Boolean(primaryOa?.id?.startsWith("oa-") && primaryOa.detailAvailable && row.oa.detailAvailable);
}

function ActionButtons({
  row,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onMarkIncomeStatus,
  actionsDisabled = false,
}: Pick<PendingInvoicesTableProps, "onOpenRelation" | "onOpenInvoicePicker" | "onOpenManualInvoice" | "onMarkIncomeStatus" | "actionsDisabled"> & { row: PendingInvoiceRow }) {
  const action = row.invoiceAcquisitionStatus.primaryAction;
  const prefix = row.bankTransaction.counterpartyName;
  const available = new Set(row.availableActions);
  const canAttach = available.has("attach_existing_invoice");
  const canManual = available.has("manual_invoice");
  const canMarkIncome = available.has("mark_income_status");
  const canViewRelation = available.has("view_relation");

  if (action === "mark_income_status" && canMarkIncome) {
    return (
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
        <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onMarkIncomeStatus(row, "income_no_invoice_required")} aria-label={`${prefix} 标记无需开票`} sx={compactActionButtonSx}>
          无需开票
        </Button>
        <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onMarkIncomeStatus(row, "cash_income")} aria-label={`${prefix} 标记现金收入`} sx={compactActionButtonSx}>
          现金收入
        </Button>
      </Stack>
    );
  }
  if (action === "attach_or_create_invoice" && (canAttach || canManual)) {
    return (
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
        {canAttach ? <Button size="small" variant="contained" disabled={actionsDisabled} onClick={() => onOpenInvoicePicker(row)} aria-label={`${prefix} 选择发票`} sx={compactActionButtonSx}>
          选择发票
        </Button> : null}
        {canManual ? <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onOpenManualInvoice(row)} aria-label={`${prefix} 补票`} sx={compactActionButtonSx}>
          补票
        </Button> : null}
      </Stack>
    );
  }
  if (shouldOpenRelation(action) && canViewRelation) {
    return (
      <Button size="small" variant="outlined" onClick={() => onOpenRelation(row)} aria-label={`${prefix} 查看支付明细`} sx={compactActionButtonSx}>
        查看支付明细
      </Button>
    );
  }
  if (shouldOpenInvoicePicker(action) && canAttach) {
    return (
      <Button size="small" variant="contained" disabled={actionsDisabled} onClick={() => onOpenInvoicePicker(row)} aria-label={`${prefix} 选择发票`} sx={compactActionButtonSx}>
        选择发票
      </Button>
    );
  }
  if (shouldOpenManualInvoice(action) && canManual) {
    return (
      <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onOpenManualInvoice(row)} aria-label={`${prefix} 补票`} sx={compactActionButtonSx}>
        补票
      </Button>
    );
  }
  return null;
}

export default function PendingInvoicesTable({
  rows,
  config,
  onSortChange,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onMarkIncomeStatus,
  direction,
  statusFilterControl,
  actionsDisabled = false,
}: PendingInvoicesTableProps) {
  const bankGroupLabel = direction === "income" ? "收入流水" : direction === "all" ? "流水" : "支出流水";
  const invoiceGroupLabel = direction === "income" ? "销项发票" : direction === "all" ? "发票" : "进项发票";
  return (
    <Box sx={{ border: CELL_BORDER, borderColor: "divider", bgcolor: "background.paper" }}>
      <Box
        data-testid="pending-invoices-table-shell"
        sx={{
          overflowX: "hidden",
          overflowY: "auto",
          maxHeight: { xs: "calc(100vh - 255px)", md: "calc(100vh - 220px)" },
          minHeight: 280,
          overscrollBehavior: "contain",
        }}
      >
        <Table stickyHeader aria-label="待找发票四区表" size="small" sx={{ width: "100%", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "16%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "14%" }} />
            <col style={{ width: "13%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "9%" }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell colSpan={3} scope="colgroup" sx={groupHeaderSx("#edf5ff")}>{bankGroupLabel}</TableCell>
              <TableCell scope="colgroup" sx={groupHeaderSx("#fff7e6", true)}>发票获取状态</TableCell>
              <TableCell colSpan={3} scope="colgroup" sx={groupHeaderSx("#eefaf3", true)}>{invoiceGroupLabel}</TableCell>
              <TableCell colSpan={2} scope="colgroup" sx={groupHeaderSx("#f4f4f5", true)}>OA</TableCell>
            </TableRow>
            <TableRow>
              <TableCell scope="col" sx={subHeaderSx("#f6faff")}>
                {sortableLabel("对方 / 时间", "counterparty_name", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" align="right" sx={subHeaderSx("#f6faff")}>
                {sortableLabel("金额 / 银行账户", "amount", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" sx={subHeaderSx("#f6faff")}>摘要 / 凭证</TableCell>
              <TableCell scope="col" sx={subHeaderSx("#fffaf0", true)}>
                <Stack direction="row" spacing={0.75} alignItems="center" justifyContent="space-between" sx={{ minWidth: 0 }}>
                  {sortableLabel("状态", "status_code", config, onSortChange)}
                  {statusFilterControl}
                </Stack>
              </TableCell>
              <TableCell scope="col" sx={subHeaderSx("#f7fcf9", true)}>
                {sortableLabel("发票号码 / 开票日期", "trade_date", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" sx={subHeaderSx("#f7fcf9")}>
                {sortableLabel("销方 / 识别号", "seller_name", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" align="right" sx={subHeaderSx("#f7fcf9")}>
                {sortableLabel("金额 / 支付差额", "invoice_total", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" sx={subHeaderSx("#fafafa", true)}>
                {sortableLabel("申请人 / 类型", "oa_applicant", config, onSortChange)}
              </TableCell>
              <TableCell scope="col" sx={subHeaderSx("#fafafa")}>
                {sortableLabel("项目 / 详情", "project_name", config, onSortChange)}
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center" sx={{ py: 6, color: "text.secondary" }}>
                  当前条件下没有待找发票流水。
                </TableCell>
              </TableRow>
            ) : rows.map((row) => renderRow({
              row,
              direction,
              onOpenRelation,
              onOpenInvoicePicker,
              onOpenManualInvoice,
              onOpenObjectDetail,
              onMarkIncomeStatus,
              actionsDisabled,
            }))}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}

function groupHeaderSx(bgcolor: string, leftBorder = false): SxProps<Theme> {
  return {
    bgcolor,
    borderBottom: CELL_BORDER,
    borderColor: "divider",
    color: "text.primary",
    fontWeight: 900,
    position: "sticky",
    top: 0,
    zIndex: 4,
    textAlign: "center",
    ...(leftBorder ? { borderLeft: GROUP_BORDER, borderLeftColor: "divider" } : {}),
  };
}

function subHeaderSx(bgcolor: string, leftBorder = false): SxProps<Theme> {
  return {
    bgcolor,
    borderBottom: CELL_BORDER,
    borderColor: "divider",
    color: "text.secondary",
    fontSize: 12,
    fontWeight: 800,
    lineHeight: 1.2,
    position: "sticky",
    top: 33,
    zIndex: 3,
    whiteSpace: "normal",
    ...(leftBorder ? { borderLeft: GROUP_BORDER, borderLeftColor: "divider" } : {}),
  };
}

function dataCellSx(leftBorder = false): SxProps<Theme> {
  return {
    verticalAlign: "top",
    px: 0.8,
    py: 0.55,
    fontSize: 12,
    lineHeight: 1.3,
    ...(leftBorder ? { borderLeft: GROUP_BORDER, borderLeftColor: "divider" } : {}),
  };
}

const compactActionButtonSx: SxProps<Theme> = {
  minHeight: 24,
  height: 24,
  px: 0.85,
  py: 0,
  fontSize: 11,
  lineHeight: 1,
  borderRadius: 1,
  boxShadow: "none",
  whiteSpace: "nowrap",
};

const denseChipSx: SxProps<Theme> = {
  height: 20,
  maxWidth: "100%",
  "& .MuiChip-label": {
    px: 0.6,
    fontSize: 11,
    lineHeight: 1.2,
  },
};

const directionChipSx: SxProps<Theme> = {
  height: 20,
  maxWidth: "100%",
  minWidth: 24,
  fontWeight: 900,
  "& .MuiChip-label": {
    px: 0.6,
    fontSize: 11,
    lineHeight: 1.2,
  },
};

function renderRow({
  row,
  direction,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onMarkIncomeStatus,
  actionsDisabled = false,
}: Omit<PendingInvoicesTableProps, "rows" | "config" | "onSortChange" | "statusFilterControl"> & { row: PendingInvoiceRow }) {
  const primaryInvoice = row.inputInvoices.primary;
  const primaryOa = row.oa.primary;
  const invoiceExtraCount = Math.max(0, row.inputInvoices.relationCount - 1);
  const oaExtraCount = Math.max(0, row.oa.relationCount - 1);
  const oaDetailAvailable = canOpenOaDetail(row);
  const moneyDirection = rowMoneyDirection(row, direction);

  return (
    <TableRow key={row.id} hover>
      <TableCell sx={dataCellSx()}>
        <Stack spacing={0.4} sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
            <Typography component="div" fontWeight={900} noWrap title={row.bankTransaction.counterpartyName} sx={{ fontSize: 12, lineHeight: 1.3 }}>
              {row.bankTransaction.counterpartyName}
            </Typography>
            <Tooltip title="流水详情">
              <IconButton
                size="small"
                aria-label={`流水详情 ${row.bankTransaction.counterpartyName}`}
                onClick={() => onOpenObjectDetail({ kind: "bankTransaction", id: row.bankTransaction.id, rowId: row.id })}
                sx={{ width: 24, height: 24 }}
              >
                <InfoOutlinedIcon fontSize="inherit" />
              </IconButton>
            </Tooltip>
          </Stack>
          <Typography color="text.secondary" sx={{ fontSize: 11, lineHeight: 1.25 }}>{row.bankTransaction.tradeTime || "-"}</Typography>
          <Chip
            size="small"
            variant="outlined"
            label={tagPathLabel(row.bankTransaction)}
            sx={{ ...denseChipSx, alignSelf: "flex-start" }}
          />
        </Stack>
      </TableCell>
      <TableCell align="right" sx={dataCellSx()}>
        <Stack direction="row" spacing={0.5} justifyContent="flex-end" alignItems="center">
          <Chip
            size="small"
            label={moneyDirection === "income" ? "收" : "支"}
            color={moneyDirection === "income" ? "success" : "error"}
            variant="outlined"
            sx={directionChipSx}
          />
          <Typography component="div" fontWeight={900} sx={{ fontSize: 12, lineHeight: 1.3, fontVariantNumeric: "tabular-nums" }}>
            {formatMoney(row.bankTransaction.amount)}
          </Typography>
        </Stack>
        <Typography color="text.secondary" component="div" sx={{ mt: 0.3, fontSize: 11, lineHeight: 1.25 }}>
          {bankAccountLabel(row.bankTransaction)}
        </Typography>
      </TableCell>
      <TableCell sx={dataCellSx()}>
        <Stack spacing={0.35}>
          <Typography sx={[overflowText(false), { fontSize: 12, lineHeight: 1.3 }]}>
            {row.bankTransaction.summary || "-"}
          </Typography>
          <Typography color="text.secondary" sx={[overflowText(false), { fontSize: 11, lineHeight: 1.25 }]}>
            {row.bankTransaction.remark || row.bankTransaction.voucherNo || "-"}
          </Typography>
        </Stack>
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        <Stack spacing={0.4} alignItems="flex-start">
          <Chip
            size="small"
            color={chipColor(row.invoiceAcquisitionStatus.severity)}
            variant={row.invoiceAcquisitionStatus.severity === "default" ? "outlined" : "filled"}
            label={row.invoiceAcquisitionStatus.label}
            sx={denseChipSx}
          />
          <ActionButtons
            row={row}
            onOpenRelation={onOpenRelation}
            onOpenInvoicePicker={onOpenInvoicePicker}
            onOpenManualInvoice={onOpenManualInvoice}
            onMarkIncomeStatus={onMarkIncomeStatus}
            actionsDisabled={actionsDisabled}
          />
        </Stack>
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        {primaryInvoice ? (
          <Stack spacing={0.35} sx={{ minWidth: 0 }}>
            <Typography fontWeight={900} noWrap title={invoiceNumber(primaryInvoice)} sx={{ fontSize: 12, lineHeight: 1.3 }}>
              {invoiceNumber(primaryInvoice)}
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Typography color="text.secondary" sx={{ fontSize: 11, lineHeight: 1.25 }}>{primaryInvoice.issueDate || "-"}</Typography>
              <Button
                size="small"
                variant="text"
                aria-label={`发票详情 ${invoiceNumber(primaryInvoice)}`}
                onClick={() => onOpenObjectDetail({ kind: "invoice", id: primaryInvoice.id, rowId: row.id })}
              >
                详情
              </Button>
              {invoiceExtraCount > 0 ? (
                <Button size="small" variant="outlined" onClick={() => onOpenRelation(row)} aria-label={`${row.bankTransaction.counterpartyName} 查看全部发票关系`}>
                  +{invoiceExtraCount}
                </Button>
              ) : null}
            </Stack>
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell sx={dataCellSx()}>
        {primaryInvoice ? (
          <Stack spacing={0.35}>
            <Typography fontWeight={800} sx={[overflowText(false), { fontSize: 12, lineHeight: 1.3 }]}>
              {primaryInvoice.sellerName || "-"}
            </Typography>
            <Typography color="text.secondary" sx={[overflowText(false), { fontSize: 11, lineHeight: 1.25 }]}>
              {primaryInvoice.sellerTaxNo || "-"}
            </Typography>
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell align="right" sx={dataCellSx()}>
        {primaryInvoice ? (
          <Stack spacing={0.35}>
            <Typography fontWeight={900} sx={{ fontSize: 12, lineHeight: 1.3, fontVariantNumeric: "tabular-nums" }}>
              {formatMoney(primaryInvoice.totalWithTax)}
            </Typography>
            {row.inputInvoices.paymentSummary ? (
              <>
                <Typography color="text.secondary" sx={{ fontSize: 11, lineHeight: 1.25 }}>已付 {formatMoney(row.inputInvoices.paymentSummary.paidTotal)}</Typography>
                <Typography color="text.secondary" sx={{ fontSize: 11, lineHeight: 1.25 }}>待付 {formatMoney(row.inputInvoices.paymentSummary.remainingAmount)}</Typography>
              </>
            ) : null}
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        {primaryOa ? (
          <Stack spacing={0.35} sx={{ minWidth: 0 }}>
            <Typography fontWeight={900} noWrap title={primaryOa.applicant} sx={{ fontSize: 12, lineHeight: 1.3 }}>{primaryOa.applicant || "-"}</Typography>
            <Typography color="text.secondary" sx={{ fontSize: 11, lineHeight: 1.25 }}>{primaryOa.applicationType || "-"}</Typography>
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell sx={dataCellSx()}>
        {primaryOa ? (
          <Stack spacing={0.35} alignItems="flex-start" sx={{ minWidth: 0 }}>
            <Typography fontWeight={800} sx={[overflowText(false), { fontSize: 12, lineHeight: 1.3 }]}>
              {primaryOa.projectName || "-"}
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Button
                size="small"
                variant="text"
                disabled={!oaDetailAvailable}
                aria-label={`OA详情 ${primaryOa.applicant || primaryOa.id}`}
                onClick={() => onOpenObjectDetail({ kind: "oa", id: primaryOa.id, rowId: row.id })}
              >
                详情
              </Button>
              {oaExtraCount > 0 ? (
                <Button size="small" variant="outlined" onClick={() => onOpenRelation(row)} aria-label={`${row.bankTransaction.counterpartyName} 查看全部 OA 关系`}>
                  +{oaExtraCount}
                </Button>
              ) : null}
            </Stack>
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
    </TableRow>
  );
}
