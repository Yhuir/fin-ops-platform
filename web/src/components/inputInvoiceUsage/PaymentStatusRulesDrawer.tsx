import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import type {
  InputInvoiceUsagePaymentStatusRulesResponse,
  SaveInputInvoiceUsagePaymentStatusRulesRequest,
} from "../../features/inputInvoiceUsage/types";

export type PaymentStatusRule = {
  id?: string;
  code?: string;
  label: string;
  description: string;
  priority: number;
};

export type PaymentStatusRulesPayload = {
  version?: number | string | null;
  readOnly?: boolean;
  permissions?: {
    canSave?: boolean;
    can_save?: boolean;
  };
  rules: PaymentStatusRule[];
  pendingDirections: Array<{ code?: string; label: string }>;
};

type PaymentStatusRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PaymentStatusRulesPayload>;
  saveRules?: (request: SaveInputInvoiceUsagePaymentStatusRulesRequest) => Promise<InputInvoiceUsagePaymentStatusRulesResponse | PaymentStatusRulesPayload>;
  onClose: () => void;
};

export default function PaymentStatusRulesDrawer({
  open,
  loadRules,
  saveRules,
  onClose,
}: PaymentStatusRulesDrawerProps) {
  const [payload, setPayload] = useState<PaymentStatusRulesPayload | null>(null);
  const [draftRules, setDraftRules] = useState<PaymentStatusRule[]>([]);
  const [draftPendingDirections, setDraftPendingDirections] = useState<Array<{ code?: string; label: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setDraftRules([]);
      setDraftPendingDirections([]);
      setLoading(false);
      setSaving(false);
      setError(null);
      setFeedback(null);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
          setDraftRules(cloneRules(nextPayload.rules));
          setDraftPendingDirections(nextPayload.pendingDirections.map((item) => ({ ...item })));
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

  const canSave = Boolean(
    payload
    && payload.readOnly === false
    && (payload.permissions?.canSave || payload.permissions?.can_save)
    && saveRules,
  );

  const dirty = payload
    ? JSON.stringify({ rules: draftRules, pendingDirections: draftPendingDirections })
      !== JSON.stringify({ rules: payload.rules, pendingDirections: payload.pendingDirections })
    : false;

  const handleSave = () => {
    if (!payload || !saveRules || !canSave) {
      return;
    }
    setSaving(true);
    setError(null);
    setFeedback(null);
    saveRules({
      expectedVersion: payload.version ?? null,
      idempotencyKey: createIdempotencyKey("input-invoice-usage-payment-rules-save"),
      rules: draftRules.map((rule) => ({
        ...rule,
        label: rule.label.trim(),
        description: rule.description.trim(),
        priority: Number(rule.priority),
      })),
      pendingDirections: draftPendingDirections.map((item) => ({
        ...item,
        label: item.label.trim(),
      })),
    })
      .then((nextPayload) => {
        setPayload(nextPayload);
        setDraftRules(cloneRules(nextPayload.rules));
        setDraftPendingDirections(nextPayload.pendingDirections.map((item) => ({ ...item })));
        setFeedback("规则已保存，读模型会按后端返回的刷新状态更新。");
      })
      .catch((caught) => {
        if (isVersionConflict(caught)) {
          setError("规则已被其他人更新，请重新加载后再编辑。");
        } else {
          setError(caught instanceof Error ? caught.message : "支付状态规则保存失败。");
        }
      })
      .finally(() => setSaving(false));
  };

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
              {canSave ? "编辑后保存会带版本和幂等键提交，由后端校验并触发刷新" : "按后端权限展示规则和待处理下拉方向"}
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
          {feedback ? <Alert severity="success">{feedback}</Alert> : null}
          {payload ? (
            <>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                {payload.version !== null && payload.version !== undefined ? (
                  <Chip size="small" variant="outlined" label={`版本 ${payload.version}`} />
                ) : null}
                {payload.readOnly !== false ? <Chip size="small" label="只读" /> : null}
                {payload.readOnly === false && !canSave ? <Chip size="small" label="无保存权限" color="warning" variant="outlined" /> : null}
              </Stack>
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
                    {draftRules.map((rule, index) => (
                      <TableRow key={rule.id || rule.code || rule.label}>
                        <TableCell sx={{ fontWeight: 900 }}>
                          {canSave ? (
                            <TextField
                              label="支付状态"
                              size="small"
                              value={rule.label}
                              onChange={(event) => updateRule(index, { label: event.target.value }, setDraftRules)}
                              fullWidth
                            />
                          ) : rule.label}
                        </TableCell>
                        <TableCell>
                          {canSave ? (
                            <TextField
                              label="规则"
                              size="small"
                              value={rule.description}
                              onChange={(event) => updateRule(index, { description: event.target.value }, setDraftRules)}
                              fullWidth
                              multiline
                              minRows={2}
                            />
                          ) : rule.description}
                        </TableCell>
                        <TableCell sx={{ width: canSave ? 120 : undefined }}>
                          {canSave ? (
                            <TextField
                              label="优先级"
                              size="small"
                              type="number"
                              value={rule.priority}
                              onChange={(event) => updateRule(index, { priority: Number(event.target.value) }, setDraftRules)}
                              inputProps={{ min: 1 }}
                            />
                          ) : rule.priority}
                        </TableCell>
                      </TableRow>
                    ))}
                    {draftRules.length === 0 ? (
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
                  {draftPendingDirections.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">暂无待处理方向。</Typography>
                  ) : null}
                  {draftPendingDirections.map((option, index) => (
                    canSave ? (
                      <TextField
                        key={option.code || index}
                        label={option.code || `方向 ${index + 1}`}
                        size="small"
                        value={option.label}
                        onChange={(event) => updatePendingDirection(index, event.target.value, setDraftPendingDirections)}
                      />
                    ) : (
                      <Chip key={option.code || option.label} label={option.label} variant="outlined" />
                    )
                  ))}
                </Stack>
              </Paper>
              {canSave ? (
                <Stack direction="row" justifyContent="flex-end" spacing={1}>
                  <Button
                    variant="outlined"
                    disabled={saving || loading}
                    onClick={() => {
                      setDraftRules(cloneRules(payload.rules));
                      setDraftPendingDirections(payload.pendingDirections.map((item) => ({ ...item })));
                      setError(null);
                      setFeedback(null);
                    }}
                  >
                    还原
                  </Button>
                  <Button
                    variant="contained"
                    disabled={saving || loading || !dirty}
                    onClick={handleSave}
                  >
                    {saving ? "保存中..." : "保存规则"}
                  </Button>
                </Stack>
              ) : null}
            </>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}

function cloneRules(rules: PaymentStatusRule[]) {
  return rules.map((rule) => ({ ...rule }));
}

function updateRule(
  index: number,
  patch: Partial<PaymentStatusRule>,
  setDraftRules: Dispatch<SetStateAction<PaymentStatusRule[]>>,
) {
  setDraftRules((current) => current.map((item, itemIndex) => (
    itemIndex === index ? { ...item, ...patch } : item
  )));
}

function updatePendingDirection(
  index: number,
  label: string,
  setDraftPendingDirections: Dispatch<SetStateAction<Array<{ code?: string; label: string }>>>,
) {
  setDraftPendingDirections((current) => current.map((item, itemIndex) => (
    itemIndex === index ? { ...item, label } : item
  )));
}

function createIdempotencyKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function isVersionConflict(reason: unknown) {
  if (!reason || typeof reason !== "object") {
    return false;
  }
  const status = (reason as { status?: unknown }).status;
  const code = String((reason as { code?: unknown }).code ?? "");
  return status === 409 || code.includes("version_conflict") || code.includes("conflict");
}
