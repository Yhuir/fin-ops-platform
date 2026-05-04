import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { TaxCertifiedInvoiceRecord } from "../../features/tax/types";

type CertifiedResultsDrawerProps = {
  matchedRows: TaxCertifiedInvoiceRecord[];
  outsidePlanRows: TaxCertifiedInvoiceRecord[];
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onSelectMatchedRow: (row: TaxCertifiedInvoiceRecord) => void;
};

function DrawerGroup({
  title,
  rows,
  buttonLabelPrefix,
  onSelect,
}: {
  title: string;
  rows: TaxCertifiedInvoiceRecord[];
  buttonLabelPrefix: string;
  onSelect?: (row: TaxCertifiedInvoiceRecord) => void;
}) {
  return (
    <Paper className="tax-certified-group" component="section" variant="outlined">
      <Stack className="tax-certified-group-header" direction="row" justifyContent="space-between" alignItems="center">
        <Typography component="strong" fontWeight={800}>
          {title}
        </Typography>
        <Chip label={`${rows.length} 条`} size="small" variant="outlined" />
      </Stack>
      <Stack className="tax-certified-group-list" spacing={1}>
        {rows.length === 0 ? <Typography className="tax-certified-empty">当前分组暂无记录</Typography> : null}
        {rows.map((row) => (
          <ButtonBase
            key={row.id}
            className="tax-certified-item"
            type="button"
            onClick={() => onSelect?.(row)}
            aria-label={`${buttonLabelPrefix} ${row.invoiceNo}`}
          >
            <Stack spacing={0.75} sx={{ width: "100%" }}>
              <Stack className="tax-certified-item-head" direction="row" justifyContent="space-between" alignItems="center">
                <Typography component="strong" fontWeight={800}>
                  {row.invoiceNo}
                </Typography>
                <Chip color="success" label={row.statusLabel ?? "已认证"} size="small" variant="outlined" />
              </Stack>
              <Stack className="tax-certified-item-meta" direction="row" flexWrap="wrap" gap={1}>
                <Typography component="span">{row.counterparty}</Typography>
                <Typography component="span">{row.issueDate}</Typography>
                <Typography component="span">{row.taxAmount}</Typography>
              </Stack>
            </Stack>
          </ButtonBase>
        ))}
      </Stack>
    </Paper>
  );
}

export default function CertifiedResultsDrawer({
  matchedRows,
  outsidePlanRows,
  isCollapsed,
  onToggleCollapse,
  onSelectMatchedRow,
}: CertifiedResultsDrawerProps) {
  const totalCount = matchedRows.length + outsidePlanRows.length;

  return (
    <Paper
      className={`tax-certified-drawer${isCollapsed ? " collapsed" : ""}`}
      aria-label="已认证结果"
      component="aside"
      role="complementary"
      variant="outlined"
    >
      <Button
        aria-label={`${isCollapsed ? "展开" : "收起"}已认证结果 ${totalCount}`}
        className="tax-certified-drawer-toggle"
        type="button"
        onClick={onToggleCollapse}
        variant="text"
      >
        <span>已认证结果</span>
        <strong>{totalCount}</strong>
      </Button>

      {!isCollapsed ? (
        <Stack className="tax-certified-drawer-body" spacing={1.5}>
          <DrawerGroup
            title="已匹配计划"
            rows={matchedRows}
            buttonLabelPrefix="定位已匹配计划发票"
            onSelect={onSelectMatchedRow}
          />
          <DrawerGroup title="已认证但未进入计划" rows={outsidePlanRows} buttonLabelPrefix="查看未进入计划的已认证发票" />
        </Stack>
      ) : null}
    </Paper>
  );
}
