import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select, { type SelectChangeEvent } from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type {
  TurnoverLedgerExtra,
  TurnoverLedgerGroupedRow,
  TurnoverRelationDetail,
} from "../../features/turnoverLedger/types";
import { formatMoney, formatNullable } from "./TurnoverLedgerGroupedTable";

function DetailField({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" fontWeight={800}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.25, wordBreak: "break-word" }}>
        {formatNullable(value)}
      </Typography>
    </Box>
  );
}

export default function TurnoverLedgerExtraDrawer({
  open,
  row,
  detail,
  extra,
  dirty,
  canMutateData,
  loading,
  saving,
  mutating,
  error,
  onClose,
  onExtraChange,
  onSave,
  onConfirm,
  onWithdraw,
}: {
  open: boolean;
  row: TurnoverLedgerGroupedRow | null;
  detail: TurnoverRelationDetail | null;
  extra: TurnoverLedgerExtra;
  dirty: boolean;
  canMutateData: boolean;
  loading: boolean;
  saving: boolean;
  mutating: boolean;
  error: string | null;
  onClose: () => void;
  onExtraChange: (next: TurnoverLedgerExtra) => void;
  onSave: () => void;
  onConfirm: () => void;
  onWithdraw: () => void;
}) {
  const relation = row;
  const canConfirm = canMutateData && relation?.status === "suggested";
  const canWithdraw = canMutateData && relation?.status === "confirmed";
  const handleTextChange = (field: keyof TurnoverLedgerExtra) => (event: React.ChangeEvent<HTMLInputElement>) => {
    onExtraChange({ ...extra, [field]: event.target.value });
  };
  const handleRateTypeChange = (event: SelectChangeEvent) => {
    onExtraChange({ ...extra, interestRateType: event.target.value });
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        "aria-label": "编辑往来补充信息",
        role: "presentation",
        sx: { width: { xs: "100%", sm: 620 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
          <Typography component="h2" variant="h6" fontWeight={900}>
            编辑往来补充信息
          </Typography>
          <Button onClick={onClose}>关闭</Button>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ p: 2, overflow: "auto" }}>
          {loading ? (
            <Alert severity="info">正在加载关系详情和补充信息。</Alert>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {relation ? (
            <>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip label={relation.relationId} variant="outlined" />
                <Chip label={relation.statusLabel || relation.status} />
              </Stack>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
                <DetailField label="对方户名" value={detail?.bankRows[0]?.counterpartyName ?? "-"} />
                <DetailField label="借款金额" value={formatMoney(relation.borrowAmount)} />
                <DetailField label="还款金额" value={formatMoney(relation.repaymentAmount)} />
                <DetailField label="银行流水 ID" value={relation.bankRowIds.join("，")} />
                <DetailField label="借款天数" value={relation.loanDays} />
                <DetailField label="应还利息" value={relation.accruedInterest ? formatMoney(relation.accruedInterest) : "-"} />
              </Box>

              <Divider />
              <Typography variant="subtitle2" fontWeight={900}>
                银行流水明细
              </Typography>
              <Stack spacing={1}>
                {(detail?.bankRows ?? []).map((bankRow) => (
                  <Paper key={bankRow.id} variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                    <Stack spacing={0.75}>
                      <Typography variant="body2" fontWeight={900}>
                        {bankRow.id}
                      </Typography>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        <Chip size="small" label={bankRow.directionLabel || "-"} />
                        <Chip size="small" label={formatMoney(bankRow.amount)} />
                        <Chip size="small" label={bankRow.bankAccountLabel || "-"} variant="outlined" />
                      </Stack>
                      <Typography variant="body2" color="text.secondary">{bankRow.summary || "-"}</Typography>
                    </Stack>
                  </Paper>
                ))}
              </Stack>

              <Divider />
              <Typography variant="subtitle2" fontWeight={900}>
                补充信息
              </Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
                <FormControl size="small" fullWidth>
                  <InputLabel id="turnover-interest-rate-type-label">利率类型</InputLabel>
                  <Select
                    labelId="turnover-interest-rate-type-label"
                    label="利率类型"
                    value={extra.interestRateType}
                    onChange={handleRateTypeChange}
                  >
                    <MenuItem value="none">不计息</MenuItem>
                    <MenuItem value="annual">年息</MenuItem>
                    <MenuItem value="monthly">月息</MenuItem>
                  </Select>
                </FormControl>
                <TextField
                  size="small"
                  label="利率值"
                  value={extra.interestRateValue}
                  onChange={handleTextChange("interestRateValue")}
                />
                <TextField
                  size="small"
                  label="已还利息额"
                  value={extra.interestPaidAmount}
                  onChange={handleTextChange("interestPaidAmount")}
                />
                <TextField
                  size="small"
                  label="还利息日期"
                  value={extra.interestPaidDate ?? ""}
                  onChange={handleTextChange("interestPaidDate")}
                  placeholder="YYYY-MM-DD"
                />
                <TextField
                  size="small"
                  label="还利息方式"
                  value={extra.interestPaymentMethod}
                  onChange={handleTextChange("interestPaymentMethod")}
                />
                <TextField
                  size="small"
                  label="备注"
                  value={extra.note}
                  onChange={handleTextChange("note")}
                  multiline
                  minRows={2}
                />
              </Box>

              <Stack direction="row" spacing={1} justifyContent="space-between" useFlexGap flexWrap="wrap">
                <Stack direction="row" spacing={1}>
                  <Button variant="outlined" disabled={!canConfirm || mutating} onClick={onConfirm}>
                    确认归并
                  </Button>
                  <Button color="warning" variant="outlined" disabled={!canWithdraw || mutating} onClick={onWithdraw}>
                    撤销归并
                  </Button>
                </Stack>
                <Button variant="contained" disabled={!dirty || saving || !canMutateData} onClick={onSave}>
                  保存补充信息
                </Button>
              </Stack>
            </>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}
