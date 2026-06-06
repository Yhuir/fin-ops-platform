import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
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
import type { MutableRefObject, ReactNode } from "react";

import type {
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageRow,
} from "../../features/inputInvoiceUsage/types";
import ExpandableCellText from "./ExpandableCellText";

type InputInvoiceUsageTableProps = {
  rows: InputInvoiceUsageRow[];
  page: number;
  pageSize: number;
  total: number;
  expandedCells: Set<string>;
  onToggleCellExpand: (rowId: string, cellId: string) => void;
  onOpenDetail: (target: InputInvoiceUsageDetailTarget) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  tableWrapRef?: MutableRefObject<HTMLDivElement | null>;
};

const groupHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.primary",
  fontSize: "12px",
  fontWeight: 800,
  py: 0.75,
  textAlign: "center",
  whiteSpace: "nowrap",
};

const subHeaderSx = {
  borderBottom: "1px solid",
  borderColor: "divider",
  color: "text.secondary",
  fontSize: "11px",
  fontWeight: 700,
  lineHeight: 1.25,
  py: 0.75,
  whiteSpace: "nowrap",
};

const bigSeparatorSx = {
  borderLeft: "1px solid",
  borderLeftColor: "divider",
};

const smallSeparatorSx = {
  borderLeft: "1px solid",
  borderLeftColor: "rgba(148, 163, 184, 0.28)",
};

const bodyCellSx = {
  verticalAlign: "top",
  fontSize: "12px",
  lineHeight: 1.35,
  py: 0.8,
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
  align,
  sx,
}: {
  label: ReactNode;
  align?: "left" | "right" | "center";
  sx?: object | object[];
}) {
  const sxList = Array.isArray(sx) ? [subHeaderSx, ...sx] : [subHeaderSx, sx];
  return (
    <TableCell scope="col" align={align} sx={sxList}>
      <Box
        component="span"
        sx={{
          display: "inline-flex",
          flexDirection: "column",
          alignItems: align === "right" ? "flex-end" : align === "center" ? "center" : "flex-start",
          gap: 0.15,
          minWidth: 0,
          maxWidth: "100%",
        }}
      >
        {label}
      </Box>
    </TableCell>
  );
}

function EmptyCell() {
  return <Typography variant="caption" color="text.secondary">—</Typography>;
}

export default function InputInvoiceUsageTable({
  rows,
  page,
  pageSize,
  total,
  expandedCells,
  onToggleCellExpand,
  onOpenDetail,
  onPageChange,
  onPageSizeChange,
  tableWrapRef,
}: InputInvoiceUsageTableProps) {
  return (
    <Paper variant="outlined" sx={{ width: "100%", minWidth: 0, overflow: "hidden" }}>
      <TableContainer ref={tableWrapRef} sx={{ width: "100%", overflowX: "hidden" }}>
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
            <col style={{ width: "11%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "7%" }} />
            <col style={{ width: "12%" }} />
          </colgroup>
          <TableHead>
            <TableRow>
              <TableCell colSpan={4} scope="colgroup" sx={[groupHeaderSx, { bgcolor: "#f6fbf8" }]}>
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
            <TableRow>
              <HeaderCell label="发票号码" />
              <HeaderCell label="销方" sx={smallSeparatorSx} />
              <HeaderCell
                label={(
                  <>
                    <span>价税合计</span>
                    <span>不含税/税率税额</span>
                  </>
                )}
                align="right"
                sx={smallSeparatorSx}
              />
              <HeaderCell label="货物或应税劳务名称" sx={smallSeparatorSx} />
              <HeaderCell label="支付状态" sx={[bigSeparatorSx, { bgcolor: "rgba(255, 193, 7, 0.12)" }]} />
              <HeaderCell label="OA申请人" sx={bigSeparatorSx} />
              <HeaderCell label="项目名称" sx={smallSeparatorSx} />
              <HeaderCell label="对方户名" sx={bigSeparatorSx} />
              <HeaderCell label="金额" align="right" sx={smallSeparatorSx} />
              <HeaderCell label="摘要/备注" sx={smallSeparatorSx} />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} align="center" sx={{ py: 6, color: "text.secondary" }}>
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
                    <Stack direction="row" spacing={0.25} alignItems="center" sx={{ minWidth: 0 }}>
                      <Typography component="div" variant="body2" fontWeight={800} title={invoiceNo} sx={{ minWidth: 0, fontSize: "12px", lineHeight: 1.35 }}>
                        {invoiceNo}
                      </Typography>
                      <Tooltip title="查看发票详情">
                        <IconButton
                          aria-label={`查看发票 ${invoiceNo} 详情`}
                          size="small"
                          onClick={() => onOpenDetail({ kind: "invoice", id: row.invoice.id, rowId: row.id })}
                          sx={{ flexShrink: 0, p: 0.25 }}
                        >
                          <InfoOutlinedIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.4, flexWrap: "wrap" }}>
                      <Chip label={dateOnly(row.invoice.issueDate)} size="small" variant="outlined" sx={denseChipSx} />
                    </Stack>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={700} sx={{ fontSize: "12px", lineHeight: 1.35 }}>
                      {row.invoice.sellerName || "—"}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere", fontSize: "11px", lineHeight: 1.3 }}>
                      {row.invoice.sellerTaxNo || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" sx={[bodyCellSx, smallSeparatorSx]}>
                    <Typography component="div" variant="body2" fontWeight={800} sx={{ fontSize: "12px", lineHeight: 1.35, fontVariantNumeric: "tabular-nums" }}>
                      {formatMoney(row.invoice.totalWithTax)}
                    </Typography>
                    <Typography component="div" variant="caption" color="text.secondary" sx={{ fontSize: "11px", lineHeight: 1.3, fontVariantNumeric: "tabular-nums" }}>
                      {`${formatMoney(row.invoice.amountWithoutTax)} ${row.invoice.taxRate || "—"} (${formatMoney(row.invoice.taxAmount)})`}
                    </Typography>
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
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
                    <Chip color="warning" label={row.paymentStatus.label || "待处理"} size="small" sx={denseChipSx} />
                    <Box sx={{ mt: 0.45 }}>
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
                        <Typography component="div" variant="body2" fontWeight={800} sx={{ fontSize: "12px", lineHeight: 1.35 }}>
                          {oa.applicant || "—"}
                        </Typography>
                        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.45, flexWrap: "wrap" }}>
                          <Chip label={oa.applicationType || "类型为空"} size="small" variant="outlined" sx={denseChipSx} />
                          {oa.detailAvailable ? (
                            <Button
                              size="small"
                              variant="text"
                              aria-label={`查看OA ${oa.applicant || oa.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "oa", id: oa.id, rowId: row.id })}
                              sx={{ minWidth: 0, px: 0.5, py: 0, fontSize: "11px" }}
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
                        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.45, flexWrap: "wrap" }}>
                          <Chip label={bank.tradeTime || "交易日期为空"} size="small" variant="outlined" sx={denseChipSx} />
                          {bank.detailAvailable ? (
                            <Button
                              size="small"
                              variant="text"
                              aria-label={`查看流水 ${bank.counterpartyName || bank.id} 详情`}
                              onClick={() => onOpenDetail({ kind: "bank", id: bank.id, rowId: row.id })}
                              sx={{ minWidth: 0, px: 0.5, py: 0, fontSize: "11px" }}
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
                        <Typography component="div" variant="body2" fontWeight={800} sx={{ fontSize: "12px", lineHeight: 1.35, fontVariantNumeric: "tabular-nums" }}>
                          {formatMoney(bank.amount)}
                        </Typography>
                        <Chip
                          label={`${bank.directionLabel || "收/支"} ${bank.bankName || "银行"} ${bank.accountLast4 || "----"}`}
                          size="small"
                          variant="outlined"
                          sx={{ ...denseChipSx, mt: 0.45 }}
                        />
                      </>
                    ) : <EmptyCell />}
                  </TableCell>
                  <TableCell sx={[bodyCellSx, smallSeparatorSx]}>
                    {bank ? (
                      <>
                        <Typography component="div" variant="body2" fontWeight={700} sx={{ fontSize: "12px", lineHeight: 1.35 }}>
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
        sx={{
          minHeight: 42,
          ".MuiTablePagination-toolbar": {
            minHeight: 42,
            px: 1.5,
          },
          ".MuiTablePagination-selectLabel, .MuiTablePagination-displayedRows": {
            fontSize: "12px",
          },
        }}
      />
    </Paper>
  );
}
