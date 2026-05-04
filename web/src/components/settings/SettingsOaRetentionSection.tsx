import Alert from "@mui/material/Alert";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { SettingsOaRetentionSectionProps } from "./types";

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
    <Paper
      component="section"
      aria-labelledby="settings-section-oa-retention-title"
      className="settings-section-panel"
      id="settings-section-oa-retention"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-oa-retention-title" component="h3" variant="subtitle1">OA导入设置</Typography>
      </Stack>
      <div className="settings-section-body">
        <div className="settings-oa-import-layout">
          <TextField
            label="OA导入起始日期"
            type="date"
            size="small"
            value={cutoffDate}
            disabled={controlsDisabled}
            onChange={(event) => onChangeCutoffDate(event.currentTarget.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <FormControl className="settings-checkbox-group" component="fieldset" disabled={controlsDisabled}>
            <FormLabel component="legend">表单类型</FormLabel>
            <FormGroup className="settings-checkbox-list">
              {formTypeOptions.map((option) => (
                <FormControlLabel
                  key={option.value}
                  control={(
                    <Checkbox
                      size="small"
                      checked={oaImport.formTypes.includes(option.value)}
                      onChange={() => onToggleFormType(option.value)}
                    />
                  )}
                  label={option.label}
                />
              ))}
            </FormGroup>
          </FormControl>
          <FormControl className="settings-checkbox-group" component="fieldset" disabled={controlsDisabled}>
            <FormLabel component="legend">流程状态</FormLabel>
            <FormGroup className="settings-checkbox-list">
              {statusOptions.map((option) => (
                <FormControlLabel
                  key={option.value}
                  control={(
                    <Checkbox
                      size="small"
                      checked={oaImport.statuses.includes(option.value)}
                      onChange={() => onToggleStatus(option.value)}
                    />
                  )}
                  label={option.label}
                />
              ))}
            </FormGroup>
          </FormControl>
          <Alert className="settings-access-admin-note" severity="info">
            <Typography component="strong" variant="body2">保留规则</Typography>
            <Typography component="p" variant="body2">
              保留该日期及之后的 OA；保留与这些 OA 同组的流水和发票；如果旧 OA 与该日期及之后的流水同组，也会重新保留。
            </Typography>
          </Alert>
        </div>
      </div>
    </Paper>
  );
}
