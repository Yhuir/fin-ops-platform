import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { DataGrid } from "@mui/x-data-grid";
import type { GridColDef, GridRowModel } from "@mui/x-data-grid";

import type { BankAccountMapping } from "../../features/workbench/types";
import { settingsButtonSx, settingsDataGridSx, settingsTokens } from "./settingsDesign";
import type { SettingsBankAccountsSectionProps } from "./types";

const compactTextFieldSx = {
  "& .MuiOutlinedInput-root.Mui-focused fieldset": { borderColor: settingsTokens.primary },
};

const carbonInfoAlertSx = {
  bgcolor: settingsTokens.layer01,
  color: settingsTokens.textPrimary,
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "4px",
  "& .MuiAlert-icon": { color: settingsTokens.primary },
};

export default function SettingsBankAccountsSection({
  controlsDisabled,
  mappings,
  bankNameDraft,
  bankShortNameDraft,
  last4Draft,
  canAddMapping,
  onChangeBankNameDraft,
  onChangeBankShortNameDraft,
  onChangeLast4Draft,
  onAddMapping,
  onUpdateMapping,
  onDeleteMapping,
}: SettingsBankAccountsSectionProps) {
  const processRowUpdate = (newRow: GridRowModel<BankAccountMapping>) => {
    const nextRow = {
      ...newRow,
      bankName: String(newRow.bankName ?? "").trim(),
      last4: String(newRow.last4 ?? "").replace(/\D/g, "").slice(0, 4),
      shortName: String(newRow.shortName ?? "").trim(),
    };
    onUpdateMapping(nextRow.id, (current) => ({
      ...current,
      bankName: nextRow.bankName,
      last4: nextRow.last4,
      shortName: nextRow.shortName,
    }));
    return nextRow;
  };

  const columns: GridColDef<BankAccountMapping>[] = [
    { field: "bankName", headerName: "银行名称", flex: 1, minWidth: 220, editable: !controlsDisabled },
    {
      field: "last4",
      headerName: "后四位",
      width: 140,
      editable: !controlsDisabled,
      valueParser: (value) => String(value ?? "").replace(/\D/g, "").slice(0, 4),
    },
    { field: "shortName", headerName: "简称", flex: 0.8, minWidth: 160, editable: !controlsDisabled },
    {
      field: "actions",
      headerName: "操作",
      width: 80,
      sortable: false,
      filterable: false,
      disableColumnMenu: true,
      renderCell: (params) => (
        <IconButton
          color="error"
          size="small"
          aria-label={`${params.row.bankName} 删除`}
          disabled={controlsDisabled}
          onClick={() => onDeleteMapping(params.row.id)}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Box
      component="section"
      aria-labelledby="settings-section-bank-accounts-title"
      id="settings-section-bank-accounts"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-bank-accounts-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          银行账户映射
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField
            label="银行名称"
            size="small"
            value={bankNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeBankNameDraft(event.currentTarget.value)}
            sx={compactTextFieldSx}
          />
          <TextField
            label="银行卡后四位"
            size="small"
            slotProps={{ htmlInput: { maxLength: 4, inputMode: "numeric" } }}
            value={last4Draft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeLast4Draft(event.currentTarget.value.replace(/\D/g, ""))}
            sx={compactTextFieldSx}
          />
          <TextField
            label="简称"
            size="small"
            value={bankShortNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeBankShortNameDraft(event.currentTarget.value)}
            sx={compactTextFieldSx}
          />
          <Button
            type="button"
            variant="contained"
            disabled={!canAddMapping || controlsDisabled}
            onClick={onAddMapping}
            sx={settingsButtonSx}
          >
            新增映射
          </Button>
        </Stack>

        <Box sx={{ width: "100%", bgcolor: settingsTokens.page }}>
          {mappings.length === 0 ? (
            <Alert severity="info" sx={carbonInfoAlertSx}>
              当前没有银行映射。
            </Alert>
          ) : (
            <Box sx={{ display: "flex", flexDirection: "column", maxHeight: 420, minHeight: 260 }}>
              <DataGrid
                rows={mappings}
                columns={columns}
                rowHeight={44}
                columnHeaderHeight={44}
                hideFooter
                disableRowSelectionOnClick
                processRowUpdate={processRowUpdate}
                onProcessRowUpdateError={() => undefined}
                sx={settingsDataGridSx}
              />
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
