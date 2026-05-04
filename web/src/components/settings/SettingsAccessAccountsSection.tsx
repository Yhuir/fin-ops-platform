import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { DataGrid } from "@mui/x-data-grid";
import type { GridColDef, GridRowModel } from "@mui/x-data-grid";

import type { WorkbenchAccessRole } from "../../features/workbench/types";
import { settingsButtonSx, settingsDataGridSx, settingsSectionSx, settingsTokens } from "./settingsDesign";
import type { SettingsAccessAccountsSectionProps } from "./types";

export default function SettingsAccessAccountsSection({
  controlsDisabled,
  adminUsernames,
  managedAccessAccounts,
  accessUsernameDraft,
  accessRoleDraft,
  canAddAccessAccount,
  onChangeAccessUsernameDraft,
  onChangeAccessRoleDraft,
  onAddAccessAccount,
  onUpdateManagedAccessAccount,
  onDeleteManagedAccessAccount,
}: SettingsAccessAccountsSectionProps) {
  const processRowUpdate = (newRow: GridRowModel) => {
    onUpdateManagedAccessAccount(newRow.id as string, (current) => ({
      ...current,
      username: newRow.username,
      role: newRow.role as WorkbenchAccessRole,
    }));
    return newRow;
  };

  const columns: GridColDef[] = [
    { field: "username", headerName: "账户", flex: 1, minWidth: 150, editable: !controlsDisabled },
    {
      field: "role",
      headerName: "权限级别",
      flex: 1,
      minWidth: 200,
      type: "singleSelect",
      valueOptions: [
        { value: "full_access", label: "所有操作均可" },
        { value: "read_export_only", label: "只可看和只可导出" },
      ],
      editable: !controlsDisabled,
    },
    {
      field: "actions",
      headerName: "操作",
      width: 80,
      sortable: false,
      renderCell: (params) => (
        <IconButton
          color="error"
          size="small"
          disabled={controlsDisabled}
          onClick={() => onDeleteManagedAccessAccount(params.row.id as string)}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Box
      component="section"
      aria-labelledby="settings-section-access-accounts-title"
      id="settings-section-access-accounts"
      role="region"
      sx={[settingsSectionSx, { mb: 4 }]}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{
          borderBottom: `1px solid ${settingsTokens.borderSubtle}`,
          px: { xs: 2, md: 3 },
          py: 2,
        }}
      >
        <Typography
          id="settings-section-access-accounts-title"
          component="h3"
          variant="subtitle1"
          sx={{ color: settingsTokens.textPrimary, fontWeight: 400 }}
        >
          访问账户管理
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3, px: { xs: 2, md: 3 }, py: 3 }}>
        <Alert
          severity="info"
          sx={{
            bgcolor: settingsTokens.selected,
            color: settingsTokens.textPrimary,
            border: `1px solid ${settingsTokens.borderSubtle}`,
            borderRadius: "4px",
            "& .MuiAlert-icon": { color: settingsTokens.primary },
          }}
        >
          <Typography component="strong" variant="body2" sx={{ fontWeight: 600, display: "block", mb: 1 }}>
            权限管理员
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {adminUsernames.map((username) => (
              <Box
                key={username}
                component="span"
                sx={{
                  px: 1,
                  py: 0.5,
                  bgcolor: settingsTokens.page,
                  color: settingsTokens.textPrimary,
                  border: `1px solid ${settingsTokens.borderSubtle}`,
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontWeight: 600,
                }}
              >
                {username}
              </Box>
            ))}
          </Stack>
        </Alert>

        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField
            label="新增访问账户"
            size="small"
            value={accessUsernameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeAccessUsernameDraft(event.currentTarget.value)}
            sx={{
              minWidth: { xs: "100%", sm: 220 },
              "& .MuiOutlinedInput-root": { borderRadius: "4px" },
              "& .MuiOutlinedInput-root.Mui-focused fieldset": { borderColor: settingsTokens.primary },
            }}
          />
          <FormControl size="small" disabled={controlsDisabled} sx={{ minWidth: { xs: "100%", sm: 220 } }}>
            <InputLabel id="settings-new-access-role-label">新增账户权限</InputLabel>
            <Select
              native
              labelId="settings-new-access-role-label"
              label="新增账户权限"
              inputProps={{ "aria-label": "新增账户权限" }}
              value={accessRoleDraft}
              onChange={(event) => onChangeAccessRoleDraft(event.target.value as WorkbenchAccessRole)}
              sx={{
                borderRadius: "4px",
                "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: settingsTokens.primary },
              }}
            >
              <option value="full_access">所有操作均可</option>
              <option value="read_export_only">只可看和只可导出</option>
            </Select>
          </FormControl>
          <Button
            type="button"
            variant="contained"
            disabled={!canAddAccessAccount || controlsDisabled}
            onClick={onAddAccessAccount}
            sx={settingsButtonSx}
          >
            新增账户
          </Button>
        </Stack>

        <Box sx={{ width: "100%", bgcolor: settingsTokens.page }}>
          {managedAccessAccounts.length === 0 ? (
            <Alert
              severity="info"
              sx={{
                bgcolor: settingsTokens.layer01,
                color: settingsTokens.textPrimary,
                border: `1px solid ${settingsTokens.borderSubtle}`,
                borderRadius: "4px",
                "& .MuiAlert-icon": { color: settingsTokens.primary },
              }}
            >
              当前没有单独配置的可访问 OA 账户。
            </Alert>
          ) : (
            <DataGrid
              rows={managedAccessAccounts}
              columns={columns}
              rowHeight={48}
              columnHeaderHeight={48}
              hideFooter
              autoHeight
              disableColumnMenu
              processRowUpdate={processRowUpdate}
              sx={settingsDataGridSx}
            />
          )}
        </Box>
      </Box>
    </Box>
  );
}
