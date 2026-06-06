import Alert from "@mui/material/Alert";
import type { ChangeEvent, ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
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

function cleanText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function flowDate(row: TurnoverLedgerGroupedRow | null) {
  return cleanText(row?.transactionAt) || cleanText(row?.borrowDate) || cleanText(row?.repaymentDate) || "";
}

function flowDirectionLabel(row: TurnoverLedgerGroupedRow | null) {
  const direction = cleanText(row?.flowDirection);
  if (direction === "income") {
    return "收";
  }
  if (direction === "expense") {
    return "支";
  }
  const borrowAmount = Number(String(row?.borrowAmount ?? "0").replace(/,/g, ""));
  const repaymentAmount = Number(String(row?.repaymentAmount ?? "0").replace(/,/g, ""));
  if (borrowAmount > 0 && repaymentAmount <= 0) {
    return cleanText(row?.borrowDirection) === "expense" ? "支" : "收";
  }
  if (repaymentAmount > 0 && borrowAmount <= 0) {
    return cleanText(row?.repaymentDirection) === "income" ? "收" : "支";
  }
  return "流水";
}

function flowAmount(row: TurnoverLedgerGroupedRow | null) {
  const amount = cleanText(row?.flowAmount);
  if (amount && amount !== "0.00") {
    return amount;
  }
  const borrowAmount = Number(String(row?.borrowAmount ?? "0").replace(/,/g, ""));
  if (borrowAmount > 0) {
    return row?.borrowAmount ?? "0.00";
  }
  return row?.repaymentAmount ?? "0.00";
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <Typography variant="subtitle2" fontWeight={900} sx={{ color: "text.primary" }}>
      {children}
    </Typography>
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
  const counterpartyName = cleanText(row?.counterpartyName) || cleanText(detail?.bankRows[0]?.counterpartyName) || "-";
  const familyLabel = cleanText(row?.familyLabel) || "-";
  const dateText = flowDate(row);
  const subtitle = [counterpartyName, familyLabel, dateText].filter(Boolean).join(" / ");
  const bankAccountLabels = row?.bankAccountLabels?.length ? row.bankAccountLabels : (
    detail?.bankRows.map((bankRow) => bankRow.bankAccountLabel).filter(Boolean) ?? []
  );
  const primaryBankRowId = cleanText(row?.sourceBankRowId) || cleanText(row?.bankRowIds?.[0]) || cleanText(detail?.bankRows[0]?.id);
  const handleTextChange = (field: keyof TurnoverLedgerExtra) => (event: ChangeEvent<HTMLInputElement>) => {
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
        "aria-label": "编辑流水补充信息",
        role: "dialog",
        sx: { width: { xs: "100%", sm: 640 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={2} sx={{ px: 2, py: 1.5 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="h2" variant="h6" fontWeight={900}>
              编辑流水补充信息
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, wordBreak: "break-word" }}>
              {subtitle || "未选择流水"}
            </Typography>
          </Box>
          <Button onClick={onClose}>关闭</Button>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ p: 2, overflow: "auto", flex: 1 }}>
          {loading ? (
            <Alert severity="info">正在加载关系详情和补充信息。</Alert>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {relation ? (
            <>
              <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                <Chip size="small" label={relation.statusLabel || relation.status || "-"} />
                <Chip size="small" label={flowDirectionLabel(row)} color={flowDirectionLabel(row) === "支" ? "warning" : "success"} variant="outlined" />
                <Chip size="small" label={formatMoney(flowAmount(row))} variant="outlined" />
                {bankAccountLabels.map((label) => (
                  <Chip key={label} size="small" label={label} variant="outlined" />
                ))}
              </Stack>

              <Divider />
              <Stack spacing={1.25}>
                <SectionTitle>流水概览</SectionTitle>
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1.5 }}>
                  <DetailField label="对方户名" value={counterpartyName} />
                  <DetailField label="往来类别" value={familyLabel} />
                  <DetailField label="流水编号" value={primaryBankRowId} />
                  <DetailField label="流水日期" value={dateText} />
                  <DetailField label="往来发生" value={formatMoney(relation.borrowAmount)} />
                  <DetailField label="结清发生" value={formatMoney(relation.repaymentAmount)} />
                  <DetailField label="借款天数" value={relation.loanDays} />
                  <DetailField label="应还利息" value={relation.accruedInterest ? formatMoney(relation.accruedInterest) : "-"} />
                </Box>
                {(detail?.bankRows ?? []).length > 0 ? (
                  <Stack spacing={0.75}>
                    {detail?.bankRows.map((bankRow) => (
                      <Box
                        key={bankRow.id}
                        sx={{
                          p: 1,
                          border: "1px solid",
                          borderColor: "divider",
                          borderRadius: 1,
                          backgroundColor: "background.default",
                        }}
                      >
                        <Stack spacing={0.65}>
                          <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" alignItems="center">
                            <Typography variant="body2" fontWeight={900}>{bankRow.id}</Typography>
                            <Chip size="small" label={bankRow.directionLabel || "-"} />
                            <Chip size="small" label={formatMoney(bankRow.amount)} variant="outlined" />
                            <Chip size="small" label={bankRow.bankAccountLabel || "-"} variant="outlined" />
                          </Stack>
                          <Typography variant="body2" color="text.secondary">{bankRow.summary || "-"}</Typography>
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                ) : null}
              </Stack>

              <Divider />
              <Stack spacing={1.25}>
                <SectionTitle>补充信息</SectionTitle>
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
                    sx={{ gridColumn: { sm: "1 / -1" } }}
                  />
                </Box>
              </Stack>

              <Divider />
              <Stack spacing={1.25}>
                <SectionTitle>操作记录 / 关系操作</SectionTitle>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip size="small" variant="outlined" label={`审计记录 ${detail?.auditHistory.length ?? 0} 条`} />
                  {extra.updatedAt ? <Chip size="small" variant="outlined" label={`更新于 ${extra.updatedAt}`} /> : null}
                  {extra.updatedBy ? <Chip size="small" variant="outlined" label={`更新人 ${extra.updatedBy}`} /> : null}
                </Stack>
              </Stack>
            </>
          ) : null}
        </Stack>
        <Divider />
        <Stack direction="row" spacing={1} justifyContent="space-between" useFlexGap flexWrap="wrap" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" disabled={!canConfirm || mutating || Boolean(error)} onClick={onConfirm}>
              确认归并
            </Button>
            <Button color="warning" variant="outlined" disabled={!canWithdraw || mutating || Boolean(error)} onClick={onWithdraw}>
              撤销归并
            </Button>
          </Stack>
          <Button variant="contained" disabled={!dirty || saving || !canMutateData || Boolean(error)} onClick={onSave}>
            保存补充信息
          </Button>
        </Stack>
      </Stack>
    </Drawer>
  );
}
