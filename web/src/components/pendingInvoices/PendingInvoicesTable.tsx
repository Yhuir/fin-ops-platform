import AddIcon from "@mui/icons-material/Add";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import type { PendingInvoiceDirection, PendingInvoiceRow } from "../../features/pendingInvoices/types";

type PendingInvoicesTableProps = {
  direction: PendingInvoiceDirection;
  rows: PendingInvoiceRow[];
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onCreateInvoice: (row: PendingInvoiceRow) => void;
};

function formatMoney(value: string) {
  const parsed = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value || "—";
  }
  return parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function PendingInvoicesTable({
  direction,
  rows,
  page,
  pageSize,
  total,
  onCreateInvoice,
  onPageChange,
  onPageSizeChange,
}: PendingInvoicesTableProps) {
  const bankHeader = direction === "expense" ? "支出流水" : "收入流水";
  const invoiceHeader = direction === "expense" ? "进项发票" : "销项发票";

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
      <Table aria-label="待找发票流水表" size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: "42%", fontWeight: 700 }}>{bankHeader}</TableCell>
            <TableCell sx={{ width: "43%", fontWeight: 700 }}>{invoiceHeader}</TableCell>
            <TableCell sx={{ width: "15%", fontWeight: 700 }}>OA申请人</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={3} align="center" sx={{ py: 6, color: "text.secondary" }}>
                当前条件下没有待找发票流水。
              </TableCell>
            </TableRow>
          ) : rows.map((row) => (
            <TableRow key={row.id} hover>
              <TableCell>
                <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between" sx={{ minWidth: 0 }}>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography component="div" variant="body2" fontWeight={700} noWrap title={row.bankTransaction.counterpartyName}>
                      {row.bankTransaction.counterpartyName}
                    </Typography>
                    <Chip label={row.bankTransaction.tradeTime || "时间为空"} size="small" variant="outlined" sx={{ mt: 0.75 }} />
                  </Box>
                  <Box sx={{ minWidth: 140, textAlign: "right" }}>
                    <Typography component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                      {formatMoney(row.bankTransaction.amount)}
                    </Typography>
                    <Chip
                      label={`${row.bankTransaction.bankName || "银行"} ${row.bankTransaction.accountLast4 || "----"}`}
                      size="small"
                      variant="outlined"
                      sx={{ mt: 0.75 }}
                    />
                  </Box>
                </Stack>
              </TableCell>
              <TableCell>
                {row.invoices.length > 0 ? (
                  <Stack spacing={1.25}>
                    {row.invoices.map((invoice) => {
                      const invoiceNumber = invoice.invoiceNo || invoice.digitalInvoiceNo || "号码为空";
                      return (
                        <Stack
                          key={invoice.id || invoiceNumber}
                          direction="row"
                          spacing={2}
                          alignItems="center"
                          justifyContent="space-between"
                          sx={{ minWidth: 0 }}
                        >
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Typography component="div" variant="body2" fontWeight={700} noWrap title={invoiceNumber}>
                              {invoiceNumber}
                            </Typography>
                            <Chip label={invoice.issueDate || "开票日期为空"} size="small" variant="outlined" sx={{ mt: 0.75 }} />
                          </Box>
                          <Typography component="div" variant="body2" fontWeight={800} sx={{ minWidth: 104, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                            {formatMoney(invoice.totalWithTax)}
                          </Typography>
                          <Typography component="div" variant="body2" color="text.secondary" sx={{ minWidth: 140 }} noWrap title={direction === "expense" ? invoice.sellerName : invoice.buyerName}>
                            {direction === "expense" ? invoice.sellerName || "销方为空" : invoice.buyerName || "购方为空"}
                          </Typography>
                        </Stack>
                      );
                    })}
                  </Stack>
                ) : row.canCreateInvoice ? (
                  <Tooltip title="新增发票">
                    <IconButton
                      aria-label={`${row.bankTransaction.counterpartyName} 新增发票`}
                      color="primary"
                      size="small"
                      onClick={() => onCreateInvoice(row)}
                    >
                      <AddIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                ) : (
                  <Typography color="text.secondary">—</Typography>
                )}
              </TableCell>
              <TableCell>{row.oaApplicant || "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <TablePagination
        component="div"
        count={total}
        page={Math.max(0, page - 1)}
        rowsPerPage={pageSize}
        rowsPerPageOptions={[25, 50, 100]}
        labelRowsPerPage="每页行数"
        labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
        onPageChange={(_event, nextPage) => onPageChange(nextPage + 1)}
        onRowsPerPageChange={(event) => onPageSizeChange(Number(event.target.value))}
      />
    </Box>
  );
}
