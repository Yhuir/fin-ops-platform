import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { OutputInvoiceReceiptSettingsResponse } from "../../features/outputInvoiceCollections/types";

type ReceiptSettingsDrawerProps = {
  open: boolean;
  loadSettings: () => Promise<OutputInvoiceReceiptSettingsResponse>;
  onSave: (payload: { prefix: string; resetPeriod: string }) => Promise<void>;
  onClose: () => void;
};

export default function ReceiptSettingsDrawer({
  open,
  loadSettings,
  onSave,
  onClose,
}: ReceiptSettingsDrawerProps) {
  const [prefix, setPrefix] = useState("SK");
  const [resetPeriod, setResetPeriod] = useState("monthly");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadSettings()
      .then((payload) => {
        if (!active) {
          return;
        }
        setPrefix(payload.settings.prefix || "SK");
        setResetPeriod(payload.settings.resetPeriod || "monthly");
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收据编号设置加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadSettings, open]);

  const handleSave = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSave({ prefix, resetPeriod });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "收据编号设置保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        "aria-label": open ? "收据编号设置" : undefined,
        sx: { width: { xs: "100%", sm: 480 }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <div>
            <Typography component="h2" variant="h6" fontWeight={900}>收据编号设置</Typography>
            <Typography variant="caption" color="text.secondary">正式收据编号规则</Typography>
          </div>
          <IconButton aria-label="关闭收据编号设置" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ p: 2.5 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField
            label="编号前缀"
            size="small"
            value={prefix}
            disabled={loading || submitting}
            onChange={(event) => setPrefix(event.target.value.toUpperCase())}
          />
          <TextField
            select
            label="重置周期"
            size="small"
            value={resetPeriod}
            disabled={loading || submitting}
            onChange={(event) => setResetPeriod(event.target.value)}
          >
            <MenuItem value="monthly">每月重置</MenuItem>
            <MenuItem value="yearly">每年重置</MenuItem>
            <MenuItem value="none">不按日期重置</MenuItem>
          </TextField>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={onClose} disabled={submitting}>取消</Button>
            <Button variant="contained" onClick={handleSave} disabled={loading || submitting || !prefix.trim()}>
              保存收据编号设置
            </Button>
          </Stack>
        </Stack>
      </Stack>
    </Drawer>
  );
}
