import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { WorkbenchAccessRole } from "../../features/workbench/types";
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
  return (
    <Paper
      component="section"
      aria-labelledby="settings-section-access-accounts-title"
      className="settings-section-panel"
      id="settings-section-access-accounts"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-access-accounts-title" component="h3" variant="subtitle1">访问账户管理</Typography>
      </Stack>
      <div className="settings-section-body">
        <Alert className="settings-access-admin-note" severity="info">
          <Typography component="strong" variant="body2">权限管理员</Typography>
          <div className="settings-access-admin-list">
            {adminUsernames.map((username) => (
              <span key={username} className="zone-selection-pill">
                {username}
              </span>
            ))}
          </div>
        </Alert>

        <Stack className="settings-bank-mapping-form settings-access-form" direction="row" spacing={1.5} useFlexGap flexWrap="wrap">
          <TextField
            label="新增访问账户"
            size="small"
            value={accessUsernameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeAccessUsernameDraft(event.currentTarget.value)}
          />
          <FormControl size="small" disabled={controlsDisabled} className="settings-select-control">
            <InputLabel id="settings-new-access-role-label">新增账户权限</InputLabel>
            <Select
              native
              labelId="settings-new-access-role-label"
              label="新增账户权限"
              inputProps={{ "aria-label": "新增账户权限" }}
              value={accessRoleDraft}
              onChange={(event) => onChangeAccessRoleDraft(event.target.value as WorkbenchAccessRole)}
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
          >
            新增账户
          </Button>
        </Stack>

        <div className="settings-bank-mapping-list">
          {managedAccessAccounts.length === 0 ? (
            <Alert severity="info">当前没有单独配置的可访问 OA 账户。</Alert>
          ) : null}
          {managedAccessAccounts.map((account) => (
            <Paper key={account.id} className="settings-bank-mapping-row" variant="outlined">
              <TextField
                label="账户"
                size="small"
                value={account.username}
                disabled={controlsDisabled}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  onUpdateManagedAccessAccount(account.id, (current) => ({
                    ...current,
                    username: value,
                  }));
                }}
              />
              <FormControl size="small" disabled={controlsDisabled} className="settings-select-control">
                <InputLabel id={`settings-access-role-${account.id}`}>权限级别</InputLabel>
                <Select
                  native
                  labelId={`settings-access-role-${account.id}`}
                  label="权限级别"
                  inputProps={{ "aria-label": `权限级别-${account.username}` }}
                  value={account.role}
                  onChange={(event) => {
                    const value = event.target.value as WorkbenchAccessRole;
                    onUpdateManagedAccessAccount(account.id, (current) => ({
                      ...current,
                      role: value,
                    }));
                  }}
                >
                  <option value="full_access">所有操作均可</option>
                  <option value="read_export_only">只可看和只可导出</option>
                </Select>
              </FormControl>
              <Button
                color="error"
                size="small"
                type="button"
                variant="outlined"
                disabled={controlsDisabled}
                onClick={() => onDeleteManagedAccessAccount(account.id)}
              >
                删除
              </Button>
            </Paper>
          ))}
        </div>
      </div>
    </Paper>
  );
}
