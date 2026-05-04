import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { settingsSectionSx, settingsTokens } from "./settingsDesign";
import type { SettingsDataResetSectionProps } from "./types";

export default function SettingsDataResetSection({
  controlsDisabled,
  dataResetStatus,
  dataResetProgress,
  actions,
  onOpenDataResetConfirm,
}: SettingsDataResetSectionProps) {
  return (
    <Box
      component="section"
      aria-labelledby="settings-section-data-reset-title"
      id="settings-section-data-reset"
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
          id="settings-section-data-reset-title"
          component="h3"
          variant="subtitle1"
          sx={{ color: settingsTokens.textPrimary, fontWeight: 400 }}
        >
          数据重置
        </Typography>
      </Stack>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3, px: { xs: 2, md: 3 }, py: 3 }}>
        <Alert
          severity="warning"
          sx={{
            bgcolor: "#fcf4d6",
            color: settingsTokens.textPrimary,
            border: `1px solid ${settingsTokens.warning}`,
            borderRadius: "4px",
            "& .MuiAlert-icon": { color: "#8a3800" },
          }}
        >
          <Typography component="strong" variant="body2" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
            高风险操作
          </Typography>
          <Typography component="p" variant="body2" sx={{ color: settingsTokens.textPrimary }}>
            这些按钮只清理 app 内部数据，不允许触碰 `form_data_db.form_data`。每次执行前都需要二次确认和当前 OA 用户密码复核。
          </Typography>
        </Alert>
        {dataResetStatus ? (
          <Alert
            severity={dataResetStatus.tone === "error" ? "error" : "success"}
            sx={{
              bgcolor: dataResetStatus.tone === "error" ? "#fff1f1" : "#defbe6",
              color: settingsTokens.textPrimary,
              border: `1px solid ${
                dataResetStatus.tone === "error" ? settingsTokens.error : settingsTokens.success
              }`,
              borderRadius: "4px",
              "& .MuiAlert-icon": {
                color: dataResetStatus.tone === "error" ? settingsTokens.error : settingsTokens.success,
              },
            }}
          >
            {dataResetStatus.message}
          </Alert>
        ) : null}
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 3 }}>
          {actions.map((item) => {
            const progress = dataResetProgress?.action === item.action ? dataResetProgress : null;
            const isRunning = dataResetProgress !== null;
            const progressLabel = progress
              ? `${progress.message || "正在清理"} ${progress.percent}%`
              : item.label;
            return (
              <Card
                key={item.action}
                component="article"
                variant="outlined"
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 2,
                  bgcolor: settingsTokens.layer01,
                  borderColor: settingsTokens.borderSubtle,
                  borderRadius: "4px",
                  boxShadow: "none",
                  p: 3,
                }}
              >
                <Box sx={{ flex: 1 }}>
                  <Typography
                    component="strong"
                    variant="body2"
                    sx={{ color: settingsTokens.textPrimary, fontWeight: 600, display: "block", mb: 1 }}
                  >
                    {item.title}
                  </Typography>
                  <Typography component="p" variant="body2" sx={{ color: settingsTokens.textSecondary, mb: 2 }}>
                    {item.description}
                  </Typography>
                  <Box
                    component="ul"
                    sx={{
                      borderTop: `1px solid ${settingsTokens.borderSubtle}`,
                      color: settingsTokens.textSecondary,
                      m: 0,
                      pl: 2,
                      pt: 2,
                      "& li": { mb: 0.5 },
                    }}
                  >
                    {item.impact.map((impactItem, idx) => (
                      <Typography component="li" variant="body2" sx={{ color: settingsTokens.textSecondary }} key={idx}>
                        {impactItem}
                      </Typography>
                    ))}
                  </Box>
                </Box>
                <Box>
                  {progress ? (
                    <LinearProgress
                      aria-label={progressLabel}
                      variant="determinate"
                      value={progress.percent}
                      sx={{
                        bgcolor: settingsTokens.borderSubtle,
                        borderRadius: "2px",
                        height: 4,
                        mb: 2,
                        "& .MuiLinearProgress-bar": { bgcolor: settingsTokens.error },
                      }}
                    />
                  ) : null}
                  <Button
                    color="error"
                    size="small"
                    type="button"
                    variant="contained"
                    disabled={controlsDisabled || isRunning}
                    onClick={() => onOpenDataResetConfirm(item.action)}
                    sx={{
                      bgcolor: settingsTokens.error,
                      borderRadius: 0,
                      boxShadow: "none",
                      color: settingsTokens.page,
                      minHeight: 40,
                      px: 2,
                      "&:hover": {
                        bgcolor: "#a2191f",
                        boxShadow: "none",
                      },
                      "&.Mui-disabled": {
                        bgcolor: settingsTokens.layer02,
                        color: settingsTokens.textMuted,
                      },
                    }}
                  >
                    {progressLabel}
                  </Button>
                </Box>
              </Card>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}
