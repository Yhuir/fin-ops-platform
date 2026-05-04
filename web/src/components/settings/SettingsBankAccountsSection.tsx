import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { SettingsBankAccountsSectionProps } from "./types";

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
  return (
    <Paper
      component="section"
      aria-labelledby="settings-section-bank-accounts-title"
      className="settings-section-panel"
      id="settings-section-bank-accounts"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-bank-accounts-title" component="h3" variant="subtitle1">银行账户映射</Typography>
      </Stack>
      <div className="settings-section-body">
        <Stack className="settings-bank-mapping-form" direction="row" spacing={1.5} useFlexGap flexWrap="wrap">
          <TextField
            label="银行名称"
            size="small"
            value={bankNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeBankNameDraft(event.currentTarget.value)}
          />
          <TextField
            label="银行卡后四位"
            size="small"
            slotProps={{ htmlInput: { maxLength: 4, inputMode: "numeric" } }}
            value={last4Draft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeLast4Draft(event.currentTarget.value.replace(/\D/g, ""))}
          />
          <TextField
            label="简称"
            size="small"
            value={bankShortNameDraft}
            disabled={controlsDisabled}
            onChange={(event) => onChangeBankShortNameDraft(event.currentTarget.value)}
          />
          <Button
            type="button"
            variant="contained"
            disabled={!canAddMapping || controlsDisabled}
            onClick={onAddMapping}
          >
            新增映射
          </Button>
        </Stack>

        <div className="settings-bank-mapping-list">
          {mappings.length === 0 ? <Alert severity="info">当前没有银行映射。</Alert> : null}
          {mappings.map((mapping) => (
            <Paper key={mapping.id} className="settings-bank-mapping-row" variant="outlined">
              <TextField
                label="银行名称"
                size="small"
                value={mapping.bankName}
                disabled={controlsDisabled}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  onUpdateMapping(mapping.id, (current) => ({ ...current, bankName: value }));
                }}
              />
              <TextField
                label="后四位"
                size="small"
                slotProps={{ htmlInput: { maxLength: 4, inputMode: "numeric" } }}
                value={mapping.last4}
                disabled={controlsDisabled}
                onChange={(event) => {
                  const value = event.currentTarget.value.replace(/\D/g, "").slice(0, 4);
                  onUpdateMapping(mapping.id, (current) => ({
                    ...current,
                    last4: value,
                  }));
                }}
              />
              <TextField
                label="简称"
                size="small"
                value={mapping.shortName}
                disabled={controlsDisabled}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  onUpdateMapping(mapping.id, (current) => ({ ...current, shortName: value }));
                }}
              />
              <Button
                color="error"
                size="small"
                type="button"
                variant="outlined"
                disabled={controlsDisabled}
                onClick={() => onDeleteMapping(mapping.id)}
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
