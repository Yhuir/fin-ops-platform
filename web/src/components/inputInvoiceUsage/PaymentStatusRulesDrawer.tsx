import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

export type PaymentStatusRule = {
  id?: string;
  code?: string;
  label: string;
  description: string;
  priority: number;
};

export type PaymentStatusRulesPayload = {
  version?: string;
  rules: PaymentStatusRule[];
  pendingDirections: Array<{ code?: string; label: string }>;
};

type PaymentStatusRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PaymentStatusRulesPayload>;
  onClose: () => void;
};

export default function PaymentStatusRulesDrawer({
  open,
  loadRules,
  onClose,
}: PaymentStatusRulesDrawerProps) {
  const [payload, setPayload] = useState<PaymentStatusRulesPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "支付状态规则加载失败");
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
  }, [loadRules, open]);

  return (
    <Drawer
      anchor="right"
      open={open}
      variant="persistent"
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "发票与支付状态规则设置" : undefined,
        role: "presentation",
        sx: { width: { xs: "100%", sm: "min(820px, 52vw)" }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>发票与支付状态规则设置</Typography>
            <Typography variant="caption" color="text.secondary">
              v1 只读展示 Sheet4 规则和待处理下拉方向
            </Typography>
          </Box>
          <IconButton aria-label="关闭支付状态规则抽屉" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载支付状态规则" size={22} />
              <Typography variant="body2" color="text.secondary">正在读取规则</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {payload ? (
            <>
              {payload.version ? <Chip sx={{ alignSelf: "flex-start" }} size="small" variant="outlined" label={`版本 ${payload.version}`} /> : null}
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" aria-label="Sheet4 支付状态规则">
                  <TableHead>
                    <TableRow>
                      <TableCell>支付状态</TableCell>
                      <TableCell>规则</TableCell>
                      <TableCell>优先级</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {payload.rules.map((rule) => (
                      <TableRow key={rule.id || rule.code || rule.label}>
                        <TableCell sx={{ fontWeight: 900 }}>{rule.label}</TableCell>
                        <TableCell>{rule.description}</TableCell>
                        <TableCell>{rule.priority}</TableCell>
                      </TableRow>
                    ))}
                    {payload.rules.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3}>暂无规则。</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </TableContainer>
              <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
                <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>
                  待处理下拉方向
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  {payload.pendingDirections.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">暂无待处理方向。</Typography>
                  ) : null}
                  {payload.pendingDirections.map((option) => (
                    <Chip key={option.code || option.label} label={option.label} variant="outlined" />
                  ))}
                </Stack>
              </Paper>
            </>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}
