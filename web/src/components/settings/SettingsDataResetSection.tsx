import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { SettingsDataResetSectionProps } from "./types";

export default function SettingsDataResetSection({
  controlsDisabled,
  dataResetStatus,
  dataResetProgress,
  actions,
  onOpenDataResetConfirm,
}: SettingsDataResetSectionProps) {
  return (
    <Paper
      component="section"
      aria-labelledby="settings-section-data-reset-title"
      className="settings-section-panel"
      id="settings-section-data-reset"
      role="region"
      variant="outlined"
    >
      <Stack className="settings-section-header" direction="row" alignItems="center" justifyContent="space-between">
        <Typography id="settings-section-data-reset-title" component="h3" variant="subtitle1">数据重置</Typography>
      </Stack>
      <div className="settings-section-body">
        <Alert className="settings-access-admin-note data-reset-warning" severity="warning">
          <Typography component="strong" variant="body2">高风险操作</Typography>
          <Typography component="p" variant="body2">
            这些按钮只清理 app 内部数据，不允许触碰 `form_data_db.form_data`。每次执行前都需要二次确认和当前 OA 用户密码复核。
          </Typography>
        </Alert>
        {dataResetStatus ? (
          <Alert className="data-reset-status" severity={dataResetStatus.tone === "error" ? "error" : "success"}>
            {dataResetStatus.message}
          </Alert>
        ) : null}
        <div className="data-reset-actions">
          {actions.map((item) => {
            const progress = dataResetProgress?.action === item.action ? dataResetProgress : null;
            const isRunning = dataResetProgress !== null;
            const progressLabel = progress
              ? `${progress.message || "正在清理"} ${progress.percent}%`
              : item.label;
            return (
              <Paper key={item.action} component="article" className="data-reset-card" variant="outlined">
                <Box>
                  <Typography component="strong" variant="body2">{item.title}</Typography>
                  <Typography component="p" variant="body2">{item.description}</Typography>
                </Box>
                <Box className="data-reset-action-control">
                  {progress ? (
                    <LinearProgress
                      aria-label={progressLabel}
                      className="data-reset-progress"
                      variant="determinate"
                      value={progress.percent}
                    />
                  ) : null}
                  <Button
                  color="error"
                  size="small"
                  type="button"
                  variant="outlined"
                  disabled={controlsDisabled || isRunning}
                  onClick={() => onOpenDataResetConfirm(item.action)}
                >
                    {progressLabel}
                  </Button>
                </Box>
              </Paper>
            );
          })}
        </div>
      </div>
    </Paper>
  );
}
