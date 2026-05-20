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

const groupHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.primary",
  fontWeight: 800,
  textAlign: "center",
};

const subHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.secondary",
  fontSize: "12px",
  fontWeight: 700,
  whiteSpace: "nowrap",
};

const bankGroupSx = {
  bgcolor: "#eaf3ff",
};

const bankSubSx = {
  bgcolor: "#f5f9ff",
};

const invoiceGroupSx = {
  bgcolor: "#edf8f2",
};

const invoiceSubSx = {
  bgcolor: "#f6fbf8",
};

const oaGroupSx = {
  bgcolor: "#f3f4f6",
};

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
  const invoicePartyHeader = direction === "expense" ? "销方名称" : "购方名称";

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", bgcolor: "background.paper", overflowX: "auto" }}>
      <Table aria-label="待找发票流水表" size="small" sx={{ minWidth: 1080, tableLayout: "fixed" }}>
        <TableHead>
          <TableRow>
            <TableCell colSpan={2} scope="colgroup" sx={[groupHeaderSx, bankGroupSx]}>
              {bankHeader}
            </TableCell>
            <TableCell colSpan={3} scope="colgroup" sx={[groupHeaderSx, invoiceGroupSx, { borderLeft: "1px solid", borderLeftColor: "divider" }]}>
              {invoiceHeader}
            </TableCell>
            <TableCell rowSpan={2} scope="col" sx={[groupHeaderSx, oaGroupSx, { width: "12%", borderLeft: "1px solid", borderLeftColor: "divider" }]}>
              OA申请人
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell scope="col" sx={[subHeaderSx, bankSubSx, { width: "22%" }]}>
              对方户名 / 时间
            </TableCell>
            <TableCell scope="col" align="right" sx={[subHeaderSx, bankSubSx, { width: "16%" }]}>
              金额 / 银行账户
            </TableCell>
            <TableCell scope="col" sx={[subHeaderSx, invoiceSubSx, { width: "18%", borderLeft: "1px solid", borderLeftColor: "divider" }]}>
              发票号码 / 开票日期
            </TableCell>
            <TableCell scope="col" align="right" sx={[subHeaderSx, invoiceSubSx, { width: "12%" }]}>
              价税合计
            </TableCell>
            <TableCell scope="col" sx={[subHeaderSx, invoiceSubSx, { width: "20%" }]}>
              {invoicePartyHeader}
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} align="center" sx={{ py: 6, color: "text.secondary" }}>
                当前条件下没有待找发票流水。
              </TableCell>
            </TableRow>
          ) : rows.map((row) => (
            <TableRow key={row.id} hover>
              <TableCell sx={{ verticalAlign: "top" }}>
                <Typography component="div" variant="body2" fontWeight={700} noWrap title={row.bankTransaction.counterpartyName}>
                  {row.bankTransaction.counterpartyName}
                </Typography>
                <Chip label={row.bankTransaction.tradeTime || "时间为空"} size="small" variant="outlined" sx={{ mt: 0.75 }} />
              </TableCell>
              <TableCell align="right" sx={{ verticalAlign: "top" }}>
                <Typography component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {formatMoney(row.bankTransaction.amount)}
                </Typography>
                <Chip
                  label={`${row.bankTransaction.bankName || "银行"} ${row.bankTransaction.accountLast4 || "----"}`}
                  size="small"
                  variant="outlined"
                  sx={{ mt: 0.75 }}
                />
              </TableCell>
              <TableCell sx={{ borderLeft: "1px solid", borderLeftColor: "divider", verticalAlign: "top" }}>
                {row.invoices.length > 0 ? (
                  <Stack spacing={1.25}>
                    {row.invoices.map((invoice) => {
                      const invoiceNumber = invoice.invoiceNo || invoice.digitalInvoiceNo || "号码为空";
                      return (
                        <Box key={invoice.id || invoiceNumber} sx={{ minWidth: 0 }}>
                          <Typography component="div" variant="body2" fontWeight={700} noWrap title={invoiceNumber}>
                            {invoiceNumber}
                          </Typography>
                          <Chip label={invoice.issueDate || "开票日期为空"} size="small" variant="outlined" sx={{ mt: 0.75 }} />
                        </Box>
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
              <TableCell align="right" sx={{ verticalAlign: "top" }}>
                {row.invoices.length > 0 ? (
                  <Stack spacing={1.25}>
                    {row.invoices.map((invoice) => (
                      <Typography key={invoice.id || invoice.invoiceNo || invoice.digitalInvoiceNo} component="div" variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
                        {formatMoney(invoice.totalWithTax)}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  <Typography color="text.secondary">—</Typography>
                )}
              </TableCell>
              <TableCell sx={{ verticalAlign: "top" }}>
                {row.invoices.length > 0 ? (
                  <Stack spacing={1.25}>
                    {row.invoices.map((invoice) => {
                      const partyName = direction === "expense" ? invoice.sellerName || "销方为空" : invoice.buyerName || "购方为空";
                      return (
                        <Typography key={invoice.id || invoice.invoiceNo || invoice.digitalInvoiceNo} component="div" variant="body2" color="text.secondary" noWrap title={partyName}>
                          {partyName}
                        </Typography>
                      );
                    })}
                  </Stack>
                ) : (
                  <Typography color="text.secondary">—</Typography>
                )}
              </TableCell>
              <TableCell sx={{ borderLeft: "1px solid", borderLeftColor: "divider", verticalAlign: "top" }}>{row.oaApplicant || "—"}</TableCell>
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
