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
  onOpenRules: () => void;
  onOpenExport: () => void;
  onMarkIncomeStatus: (row: PendingInvoiceRow, statusCode: "income_no_invoice_required" | "cash_income") => void;
  direction: PendingInvoiceDirection;
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

function overflowText(expanded: boolean): SxProps<Theme> {
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

function shouldOpenRules(action: PendingInvoicePrimaryAction) {
  return ["view_rules", "open_rules"].includes(action);
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
  onOpenRules,
  onMarkIncomeStatus,
  actionsDisabled = false,
}: Pick<PendingInvoicesTableProps, "onOpenRelation" | "onOpenInvoicePicker" | "onOpenManualInvoice" | "onOpenRules" | "onMarkIncomeStatus" | "actionsDisabled"> & { row: PendingInvoiceRow }) {
  const action = row.invoiceAcquisitionStatus.primaryAction;
  const prefix = row.bankTransaction.counterpartyName;
  const available = new Set(row.availableActions);
  const canAttach = available.has("attach_existing_invoice");
  const canManual = available.has("manual_invoice");
  const canMarkIncome = available.has("mark_income_status");
  const canViewRelation = available.has("view_relation");
  const canViewRules = available.has("view_rules");

  if (action === "mark_income_status" && canMarkIncome) {
    return (
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
        <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onMarkIncomeStatus(row, "income_no_invoice_required")} aria-label={`${prefix} 标记无需开票`}>
          无需开票
        </Button>
        <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onMarkIncomeStatus(row, "cash_income")} aria-label={`${prefix} 标记现金收入`}>
          现金收入
        </Button>
      </Stack>
    );
  }
  if (action === "attach_or_create_invoice" && (canAttach || canManual)) {
    return (
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
        {canAttach ? <Button size="small" variant="contained" disabled={actionsDisabled} onClick={() => onOpenInvoicePicker(row)} aria-label={`${prefix} 选择发票`}>
          选择发票
        </Button> : null}
        {canManual ? <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onOpenManualInvoice(row)} aria-label={`${prefix} 补票`}>
          补票
        </Button> : null}
      </Stack>
    );
  }
  if (shouldOpenRelation(action) && canViewRelation) {
    return (
      <Button size="small" variant="outlined" onClick={() => onOpenRelation(row)} aria-label={`${prefix} 查看支付明细`}>
        查看支付明细
      </Button>
    );
  }
  if (shouldOpenRules(action) && canViewRules) {
    return (
      <Button size="small" variant="outlined" onClick={onOpenRules} aria-label={`${prefix} 打开规则设置`}>
        规则设置
      </Button>
    );
  }
  if (shouldOpenInvoicePicker(action) && canAttach) {
    return (
      <Button size="small" variant="contained" disabled={actionsDisabled} onClick={() => onOpenInvoicePicker(row)} aria-label={`${prefix} 选择发票`}>
        选择发票
      </Button>
    );
  }
  if (shouldOpenManualInvoice(action) && canManual) {
    return (
      <Button size="small" variant="outlined" disabled={actionsDisabled} onClick={() => onOpenManualInvoice(row)} aria-label={`${prefix} 补票`}>
        补票
      </Button>
    );
  }
  return <Typography variant="caption" color="text.secondary">无可用操作</Typography>;
}

export default function PendingInvoicesTable({
  rows,
  config,
  onSortChange,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onOpenRules,
  onOpenExport,
  onMarkIncomeStatus,
  direction,
  actionsDisabled = false,
}: PendingInvoicesTableProps) {
  const bankGroupLabel = direction === "income" ? "收入流水" : direction === "all" ? "流水" : "支出流水";
  const invoiceGroupLabel = direction === "income" ? "销项发票" : direction === "all" ? "发票" : "进项发票";
  return (
    <Box sx={{ border: CELL_BORDER, borderColor: "divider", bgcolor: "background.paper" }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} justifyContent="space-between" sx={{ px: 1.5, py: 1 }}>
        <Stack direction="row" spacing={1}>
          {direction !== "all" ? <Button size="small" variant="outlined" onClick={onOpenRules}>待找发票规则设置</Button> : null}
          <Button size="small" variant="contained" disabled={actionsDisabled} onClick={onOpenExport}>筛选内容导出</Button>
        </Stack>
      </Stack>
      <Box
        data-testid="pending-invoices-table-shell"
        sx={{
          overflowX: "hidden",
          overflowY: "auto",
          maxHeight: { xs: "calc(100vh - 300px)", md: "calc(100vh - 260px)" },
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
                {sortableLabel("状态 / 依据 / 主操作", "status_code", config, onSortChange)}
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
              config,
              onOpenRelation,
              onOpenInvoicePicker,
              onOpenManualInvoice,
              onOpenObjectDetail,
              onOpenRules,
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
    p: 1,
    ...(leftBorder ? { borderLeft: GROUP_BORDER, borderLeftColor: "divider" } : {}),
  };
}

function renderRow({
  row,
  config,
  onOpenRelation,
  onOpenInvoicePicker,
  onOpenManualInvoice,
  onOpenObjectDetail,
  onOpenRules,
  onMarkIncomeStatus,
  actionsDisabled = false,
}: Omit<PendingInvoicesTableProps, "rows" | "onSortChange" | "onOpenExport" | "direction"> & { row: PendingInvoiceRow }) {
  const primaryInvoice = row.inputInvoices.primary;
  const primaryOa = row.oa.primary;
  const invoiceExtraCount = Math.max(0, row.inputInvoices.relationCount - 1);
  const oaExtraCount = Math.max(0, row.oa.relationCount - 1);
  const oaDetailAvailable = canOpenOaDetail(row);

  return (
    <TableRow key={row.id} hover>
      <TableCell sx={dataCellSx()}>
        <Stack spacing={0.75} sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
            <Typography component="div" variant="body2" fontWeight={900} noWrap title={row.bankTransaction.counterpartyName}>
              {row.bankTransaction.counterpartyName}
            </Typography>
            <Tooltip title="流水详情">
              <IconButton
                size="small"
                aria-label={`流水详情 ${row.bankTransaction.counterpartyName}`}
                onClick={() => onOpenObjectDetail({ kind: "bankTransaction", id: row.bankTransaction.id, rowId: row.id })}
              >
                <InfoOutlinedIcon fontSize="inherit" />
              </IconButton>
            </Tooltip>
          </Stack>
          <Typography variant="caption" color="text.secondary">{row.bankTransaction.tradeTime || "-"}</Typography>
          {row.bankTransaction.effectiveTagLabel ? (
            <Chip
              size="small"
              variant="outlined"
              label={row.bankTransaction.effectiveTagLabel}
              sx={{ alignSelf: "flex-start", maxWidth: "100%" }}
            />
          ) : null}
          {row.bankTransaction.counterpartyAccountNo ? (
            <Typography variant="caption" color="text.secondary" noWrap title={row.bankTransaction.counterpartyAccountNo}>
              对方尾号 {row.bankTransaction.counterpartyAccountNo.slice(-4)}
            </Typography>
          ) : null}
        </Stack>
      </TableCell>
      <TableCell align="right" sx={dataCellSx()}>
        <Typography component="div" variant="body2" fontWeight={900} sx={{ fontVariantNumeric: "tabular-nums" }}>
          {formatMoney(row.bankTransaction.amount)}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
          {bankAccountLabel(row.bankTransaction)}
        </Typography>
      </TableCell>
      <TableCell sx={dataCellSx()}>
        <Stack spacing={0.5}>
          <Typography variant="body2" sx={overflowText(false)}>
            {row.bankTransaction.summary || "-"}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={overflowText(false)}>
            {row.bankTransaction.remark || row.bankTransaction.voucherNo || "-"}
          </Typography>
        </Stack>
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        <Stack spacing={0.8} alignItems="flex-start">
          <Chip
            size="small"
            color={chipColor(row.invoiceAcquisitionStatus.severity)}
            variant={row.invoiceAcquisitionStatus.severity === "default" ? "outlined" : "filled"}
            label={row.invoiceAcquisitionStatus.label}
          />
          <Typography variant="caption" color="text.secondary" sx={overflowText(false)}>
            {row.invoiceAcquisitionStatus.reason || row.invoiceAcquisitionStatus.matchedRule?.tagLabel || "-"}
          </Typography>
          <ActionButtons
            row={row}
            onOpenRelation={onOpenRelation}
            onOpenInvoicePicker={onOpenInvoicePicker}
            onOpenManualInvoice={onOpenManualInvoice}
            onOpenRules={onOpenRules}
            onMarkIncomeStatus={onMarkIncomeStatus}
            actionsDisabled={actionsDisabled}
          />
        </Stack>
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        {primaryInvoice ? (
          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
            <Typography variant="body2" fontWeight={900} noWrap title={invoiceNumber(primaryInvoice)}>
              {invoiceNumber(primaryInvoice)}
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Typography variant="caption" color="text.secondary">{primaryInvoice.issueDate || "-"}</Typography>
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
          <Stack spacing={0.5}>
            <Typography variant="body2" fontWeight={800} sx={overflowText(false)}>
              {primaryInvoice.sellerName || "-"}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={overflowText(false)}>
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
            <Typography variant="body2" fontWeight={900} sx={{ fontVariantNumeric: "tabular-nums" }}>
              {formatMoney(primaryInvoice.totalWithTax)}
            </Typography>
            {row.inputInvoices.paymentSummary ? (
              <>
                <Typography variant="caption" color="text.secondary">已付 {formatMoney(row.inputInvoices.paymentSummary.paidTotal)}</Typography>
                <Typography variant="caption" color="text.secondary">待付 {formatMoney(row.inputInvoices.paymentSummary.remainingAmount)}</Typography>
              </>
            ) : null}
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell sx={dataCellSx(true)}>
        {primaryOa ? (
          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
            <Typography variant="body2" fontWeight={900} noWrap title={primaryOa.applicant}>{primaryOa.applicant || "-"}</Typography>
            <Typography variant="caption" color="text.secondary">{primaryOa.applicationType || "-"}</Typography>
          </Stack>
        ) : (
          <Typography color="text.secondary">-</Typography>
        )}
      </TableCell>
      <TableCell sx={dataCellSx()}>
        {primaryOa ? (
          <Stack spacing={0.5} alignItems="flex-start" sx={{ minWidth: 0 }}>
            <Typography variant="body2" fontWeight={800} sx={overflowText(false)}>
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
