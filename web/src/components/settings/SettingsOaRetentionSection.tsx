import Alert from "@mui/material/Alert";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { settingsTokens } from "./settingsDesign";
import type { SettingsOaRetentionSectionProps } from "./types";

const compactTextFieldSx = {
  maxWidth: 240,
  "& .MuiInputLabel-root": { color: settingsTokens.textSecondary },
  "& .MuiOutlinedInput-root": {
    "&.Mui-focused fieldset": { borderColor: settingsTokens.primary },
  },
};

const formLabelSx = {
  color: settingsTokens.textSecondary,
  fontSize: "14px",
  fontWeight: 400,
  mb: 1,
  "&.Mui-focused": { color: settingsTokens.primary },
};

const checkboxSx = {
  color: settingsTokens.textSecondary,
  "&.Mui-checked": { color: settingsTokens.primary },
};

const carbonInfoAlertSx = {
  mt: 1,
  bgcolor: settingsTokens.layer01,
  color: settingsTokens.textPrimary,
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "4px",
  "& .MuiAlert-icon": { color: settingsTokens.primary },
};

export default function SettingsOaRetentionSection({
  controlsDisabled,
  cutoffDate,
  oaImport,
  onChangeCutoffDate,
  onToggleFormType,
  onToggleStatus,
}: SettingsOaRetentionSectionProps) {
  const formTypeOptions = oaImport.availableFormTypes.filter((option) =>
    ["支付申请", "日常报销"].includes(option.label),
  );
  const statusOptions = oaImport.availableStatuses.filter((option) =>
    ["已完成", "进行中"].includes(option.label),
  );

  return (
    <Box
      component="section"
      aria-labelledby="settings-section-oa-retention-title"
      id="settings-section-oa-retention"
      role="region"
      sx={{ mb: 4 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Typography id="settings-section-oa-retention-title" component="h3" variant="h6" sx={{ color: settingsTokens.textPrimary, fontWeight: 400, fontSize: "16px" }}>
          OA导入设置
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <TextField
          label="OA导入起始日期"
          type="date"
          size="small"
          variant="outlined"
          value={cutoffDate}
          disabled={controlsDisabled}
          onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={compactTextFieldSx}
        />

        <Stack direction={{ xs: "column", sm: "row" }} spacing={3}>
          <FormControl component="fieldset" disabled={controlsDisabled}>
            <FormLabel component="legend" sx={formLabelSx}>表单类型</FormLabel>
            <FormGroup>
              {formTypeOptions.map((option) => (
                <FormControlLabel
                  key={option.value}
                  control={(
                    <Checkbox
                      size="small"
                      checked={oaImport.formTypes.includes(option.value)}
                      onChange={() => onToggleFormType(option.value)}
                      sx={checkboxSx}
                    />
                  )}
                  label={<Typography sx={{ fontSize: "14px", color: settingsTokens.textPrimary }}>{option.label}</Typography>}
                />
              ))}
            </FormGroup>
          </FormControl>
          <FormControl component="fieldset" disabled={controlsDisabled}>
            <FormLabel component="legend" sx={formLabelSx}>流程状态</FormLabel>
            <FormGroup>
              {statusOptions.map((option) => (
                <FormControlLabel
                  key={option.value}
                  control={(
                    <Checkbox
                      size="small"
                      checked={oaImport.statuses.includes(option.value)}
                      onChange={() => onToggleStatus(option.value)}
                      sx={checkboxSx}
                    />
                  )}
                  label={<Typography sx={{ fontSize: "14px", color: settingsTokens.textPrimary }}>{option.label}</Typography>}
                />
              ))}
            </FormGroup>
          </FormControl>
        </Stack>

        <Alert severity="info" sx={carbonInfoAlertSx}>
          <Typography component="strong" variant="body2" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>保留规则</Typography>
          <Typography component="p" variant="body2" sx={{ color: settingsTokens.textSecondary }}>
            保留该日期及之后的 OA；保留与这些 OA 同组的流水和发票；如果旧 OA 与该日期及之后的流水同组，也会重新保留。
          </Typography>
        </Alert>
      </Box>
    </Box>
  );
}
