import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { settingsTokens } from "./settingsDesign";
import type { SettingsOaInvoiceOffsetSectionProps } from "./types";

const compactTextFieldSx = {
  maxWidth: 400,
  "& .MuiInputLabel-root": { color: settingsTokens.textSecondary },
  "& .MuiOutlinedInput-root": {
    "&.Mui-focused fieldset": { borderColor: settingsTokens.primary },
  },
};

const carbonInfoAlertSx = {
  mt: 1,
  bgcolor: settingsTokens.layer01,
  color: settingsTokens.textPrimary,
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "4px",
  "& .MuiAlert-icon": { color: settingsTokens.primary },
};

export default function SettingsOaInvoiceOffsetSection({
  controlsDisabled,
  applicantsText,
  onChangeApplicantsText,
}: SettingsOaInvoiceOffsetSectionProps) {
  return (
    <Box
      component="section"
      aria-labelledby="settings-section-oa-invoice-offset-title"
      id="settings-section-oa-invoice-offset"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-oa-invoice-offset-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          冲账规则
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <TextField
          label="冲账申请人"
          size="small"
          variant="outlined"
          value={applicantsText}
          disabled={controlsDisabled}
          onChange={(event) => onChangeApplicantsText(event.currentTarget.value)}
          helperText="多个申请人以逗号或空格分隔"
          FormHelperTextProps={{ sx: { color: settingsTokens.textSecondary, ml: 0 } }}
          sx={compactTextFieldSx}
        />
        <Alert severity="info" sx={carbonInfoAlertSx}>
          <Typography component="strong" variant="body2" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>自动配对规则</Typography>
          <Typography component="p" variant="body2" sx={{ color: settingsTokens.textSecondary }}>
            OA 申请人在名单内时，自动配对该 OA 和 OA 附件解析出的发票，并打“冲”标签；该组不计入成本统计。
          </Typography>
        </Alert>
      </Box>
    </Box>
  );
}
