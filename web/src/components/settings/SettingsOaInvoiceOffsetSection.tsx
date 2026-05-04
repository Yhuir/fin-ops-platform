import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { SettingsOaInvoiceOffsetSectionProps } from "./types";

export default function SettingsOaInvoiceOffsetSection({
  controlsDisabled,
  applicantsText,
  onChangeApplicantsText,
}: SettingsOaInvoiceOffsetSectionProps) {
  return (
    <Paper
      component="section"
      aria-labelledby="settings-section-oa-invoice-offset-title"
      className="settings-section-panel"
      id="settings-section-oa-invoice-offset"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-oa-invoice-offset-title" component="h3" variant="subtitle1">冲账规则</Typography>
      </Stack>
      <div className="settings-section-body">
        <Stack className="settings-bank-mapping-form" direction="row" spacing={1.5} useFlexGap flexWrap="wrap">
          <TextField
            label="冲账申请人"
            size="small"
            value={applicantsText}
            disabled={controlsDisabled}
            onChange={(event) => onChangeApplicantsText(event.currentTarget.value)}
          />
          <Alert className="settings-access-admin-note" severity="info">
            <Typography component="strong" variant="body2">自动配对规则</Typography>
            <Typography component="p" variant="body2">
              OA 申请人在名单内时，自动配对该 OA 和 OA 附件解析出的发票，并打“冲”标签；该组不计入成本统计。
            </Typography>
          </Alert>
        </Stack>
      </div>
    </Paper>
  );
}
