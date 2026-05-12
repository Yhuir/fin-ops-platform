import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type {
  TurnoverLedgerExportPreview,
  TurnoverLedgerExportRow,
  TurnoverLedgerFamily,
} from "../../features/turnoverLedger/types";
import { formatMoney, formatNullable } from "./TurnoverLedgerGroupedTable";

const FAMILY_OPTIONS: Array<{ value: TurnoverLedgerFamily; label: string }> = [
  { value: "all", label: "全部" },
  { value: "personal", label: "个人往来" },
  { value: "company", label: "公司往来" },
  { value: "bank", label: "银行往来" },
  { value: "business", label: "业务往来" },
];

const PREVIEW_COLUMNS: Array<{ key: keyof TurnoverLedgerExportRow; label: string; money?: boolean }> = [
  { key: "sequenceNo", label: "序号" },
  { key: "rowType", label: "行类型" },
  { key: "lotId", label: "批次 ID" },
  { key: "familyLabel", label: "往来大类" },
  { key: "counterpartyName", label: "对方户名" },
  { key: "pendingRepaymentAmount", label: "待还款金额", money: true },
  { key: "pendingCollectionAmount", label: "待收款金额", money: true },
  { key: "balanceAmount", label: "余额", money: true },
  { key: "borrowAmount", label: "借款金额", money: true },
  { key: "borrowDate", label: "借款日" },
  { key: "repaymentAmount", label: "还款金额", money: true },
  { key: "repaymentDate", label: "还款日" },
  { key: "counterpartyBankName", label: "对方开户机构" },
  { key: "repaymentRemark", label: "还款备注" },
  { key: "interestRateType", label: "利率类型" },
  { key: "interestRateValue", label: "利率值" },
  { key: "interestPaidAmount", label: "已还利息额", money: true },
  { key: "loanDays", label: "借款天数" },
  { key: "accruedInterest", label: "应还利息", money: true },
  { key: "interestPaidDate", label: "还利息日期" },
  { key: "interestPaymentMethod", label: "还利息方式" },
  { key: "note", label: "备注" },
  { key: "statusLabel", label: "关系状态" },
];

function formatPreviewValue(row: TurnoverLedgerExportRow, column: { key: keyof TurnoverLedgerExportRow; money?: boolean }) {
  const rawValue = row[column.key];
  if (column.key === "rowType") {
    if (rawValue === "summary") {
      return "合计";
    }
    if (rawValue === "lot") {
      return "明细";
    }
  }
  return column.money ? formatMoney(String(rawValue ?? "")) : formatNullable(rawValue);
}

export default function TurnoverLedgerExportDialog({
  open,
  family,
  preview,
  loading,
  downloading,
  error,
  onClose,
  onFamilyChange,
  onDownload,
}: {
  open: boolean;
  family: TurnoverLedgerFamily;
  preview: TurnoverLedgerExportPreview | null;
  loading: boolean;
  downloading: boolean;
  error: string | null;
  onClose: () => void;
  onFamilyChange: (family: TurnoverLedgerFamily) => void;
  onDownload: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xl" fullWidth>
      <DialogTitle>下载往来款台账</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            select
            size="small"
            label="下载范围"
            value={family}
            onChange={(event) => onFamilyChange(event.target.value as TurnoverLedgerFamily)}
            sx={{ width: { xs: "100%", sm: 220 } }}
          >
            {FAMILY_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </TextField>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Typography variant="subtitle2" fontWeight={900}>
            正式字段预览
          </Typography>
          <TableContainer sx={{ maxHeight: 420, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
            <Table stickyHeader size="small" aria-label="往来款导出预览">
              <TableHead>
                <TableRow>
                  {PREVIEW_COLUMNS.map((column) => (
                    <TableCell key={column.key} sx={{ whiteSpace: "nowrap", fontWeight: 900 }}>
                      {column.label}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={PREVIEW_COLUMNS.length} align="center" sx={{ py: 6 }}>
                      正在加载导出预览
                    </TableCell>
                  </TableRow>
                ) : null}
                {!loading && (preview?.rows.length ?? 0) === 0 ? (
                  <TableRow>
                    <TableCell colSpan={PREVIEW_COLUMNS.length} align="center" sx={{ py: 6 }}>
                      当前范围没有可导出的台账行
                    </TableCell>
                  </TableRow>
                ) : null}
                {!loading
                  ? (preview?.rows ?? []).map((row) => (
                      <TableRow key={`${row.sequenceNo}-${row.rowType}-${row.lotId}-${row.counterpartyName}`}>
                        {PREVIEW_COLUMNS.map((column) => {
                          const value = formatPreviewValue(row, column);
                          return <TableCell key={column.key}>{value}</TableCell>;
                        })}
                      </TableRow>
                    ))
                  : null}
              </TableBody>
            </Table>
          </TableContainer>
          {preview ? (
            <Typography variant="caption" color="text.secondary">
              合计：待还款 {formatMoney(preview.summary.pendingRepaymentAmount)}，待收款{" "}
              {formatMoney(preview.summary.pendingCollectionAmount)}，应还利息{" "}
              {formatMoney(preview.summary.accruedInterest)}
            </Typography>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button variant="contained" disabled={loading || downloading} onClick={onDownload}>
          确认下载
        </Button>
      </DialogActions>
    </Dialog>
  );
}
