import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { settingsTokens } from "./settingsDesign";
import type { DataResetActionConfig } from "./types";

type SettingsDataResetDialogsProps = {
  config: DataResetActionConfig;
  isBusy: boolean;
  password: string;
  step: "confirm" | "password";
  onCancel: () => void;
  onContinue: () => void;
  onPasswordChange: (value: string) => void;
  onSubmit: () => void;
};

export default function SettingsDataResetDialogs({
  config,
  isBusy,
  password,
  step,
  onCancel,
  onContinue,
  onPasswordChange,
  onSubmit,
}: SettingsDataResetDialogsProps) {
  const dialogPaperProps = {
    sx: {
      border: `1px solid ${settingsTokens.borderSubtle}`,
      borderRadius: "4px",
      boxShadow: "none",
    },
  };

  if (step === "confirm") {
    return (
      <Dialog
        open
        onClose={onCancel}
        aria-labelledby="data-reset-confirm-title"
        maxWidth="sm"
        fullWidth
        PaperProps={dialogPaperProps}
      >
        <DialogTitle id="data-reset-confirm-title" sx={{ color: settingsTokens.textPrimary }}>
          确认数据重置
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" sx={{ color: settingsTokens.textPrimary }}>
              {config.description}
            </Typography>
            <Box component="ul" sx={{ pl: 2, m: 0, "& li": { mb: 0.5 } }}>
              {config.impact.map((item) => (
                <Typography component="li" variant="body2" color="text.secondary" key={item}>
                  {item}
                </Typography>
              ))}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 2, px: 3 }}>
          <Button type="button" onClick={onCancel} sx={{ color: settingsTokens.textSecondary }}>
            取消
          </Button>
          <Button
            color="error"
            type="button"
            variant="contained"
            onClick={onContinue}
            disableElevation
            sx={{ borderRadius: "4px" }}
          >
            继续
          </Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      onClose={isBusy ? undefined : onCancel}
      aria-labelledby="data-reset-password-title"
      maxWidth="sm"
      fullWidth
      PaperProps={dialogPaperProps}
    >
      <DialogTitle id="data-reset-password-title" sx={{ color: settingsTokens.textPrimary }}>
        OA 密码复核
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" sx={{ color: settingsTokens.textPrimary }}>
            请输入当前 OA 用户密码以确认本次高风险操作。
          </Typography>
          <TextField
            autoComplete="current-password"
            autoFocus
            fullWidth
            label="当前 OA 用户密码"
            size="small"
            type="password"
            value={password}
            disabled={isBusy}
            onChange={(event) => onPasswordChange(event.currentTarget.value)}
            sx={{
              "& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline": {
                borderColor: settingsTokens.primary,
              },
              "& .MuiInputLabel-root.Mui-focused": {
                color: settingsTokens.primary,
              },
            }}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ p: 2, px: 3 }}>
        <Button type="button" disabled={isBusy} onClick={onCancel} sx={{ color: settingsTokens.textSecondary }}>
          取消
        </Button>
        <Button
          color="error"
          type="button"
          variant="contained"
          disabled={isBusy || !password}
          onClick={onSubmit}
          disableElevation
          sx={{ borderRadius: "4px" }}
          startIcon={isBusy ? <CircularProgress size={16} color="inherit" /> : null}
        >
          {isBusy ? "清理中..." : "确认清理"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
