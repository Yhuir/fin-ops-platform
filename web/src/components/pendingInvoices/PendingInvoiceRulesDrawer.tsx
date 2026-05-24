import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { PendingInvoiceRuleGroup, PendingInvoiceRulesPayload } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PendingInvoiceRulesPayload>;
  saveRules: (payload: PendingInvoiceRulesPayload) => Promise<PendingInvoiceRulesPayload>;
  onSaved: () => void;
  onClose: () => void;
};

export default function PendingInvoiceRulesDrawer({
  open,
  loadRules,
  saveRules,
  onSaved,
  onClose,
}: PendingInvoiceRulesDrawerProps) {
  const [payload, setPayload] = useState<PendingInvoiceRulesPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setLoading(false);
      setSaving(false);
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
          setError(reason instanceof Error ? reason.message : "规则加载失败");
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

  async function handleSave() {
    if (!payload || saving || !payload.permissions.canSave) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setPayload(await saveRules(payload));
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "规则保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title="待找发票规则设置"
      subtitle={payload ? `版本 ${payload.version}` : undefined}
      closeLabel="关闭规则抽屉"
      onClose={onClose}
      footer={(
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button onClick={onClose} disabled={saving}>关闭</Button>
          <Button variant="contained" onClick={handleSave} disabled={!payload?.permissions.canSave || loading || saving}>
            保存规则
          </Button>
        </Stack>
      )}
    >
      {loading ? (
        <Stack direction="row" spacing={1.25} alignItems="center">
          <CircularProgress aria-label="正在加载待找发票规则" size={22} />
          <Typography variant="body2" color="text.secondary">正在读取规则</Typography>
        </Stack>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {payload && !payload.permissions.canSave ? <Alert severity="info">当前账号只能查看规则，不能保存。</Alert> : null}
      {payload ? (
        <Stack spacing={1.5}>
          <RuleGroup
            group={payload.groups.requiresInvoice}
            availableTags={payload.availableTags}
            assignedElsewhere={assignedElsewhere(payload, "requiresInvoice")}
            disabled={!payload.permissions.canSave || saving}
            onToggle={(tagCode) => setPayload(updateRuleGroup(payload, "requiresInvoice", tagCode))}
          />
          <RuleGroup
            group={payload.groups.bankStatementAsInvoice}
            availableTags={payload.availableTags}
            assignedElsewhere={assignedElsewhere(payload, "bankStatementAsInvoice")}
            disabled={!payload.permissions.canSave || saving}
            onToggle={(tagCode) => setPayload(updateRuleGroup(payload, "bankStatementAsInvoice", tagCode))}
          />
          <RuleGroup
            group={payload.groups.noInvoiceRequired}
            availableTags={payload.availableTags}
            assignedElsewhere={assignedElsewhere(payload, "noInvoiceRequired")}
            disabled={!payload.permissions.canSave || saving}
            onToggle={(tagCode) => setPayload(updateRuleGroup(payload, "noInvoiceRequired", tagCode))}
          />
        </Stack>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function updateRuleGroup(
  payload: PendingInvoiceRulesPayload,
  key: keyof PendingInvoiceRulesPayload["groups"],
  tagCode: string,
): PendingInvoiceRulesPayload {
  const current = payload.groups[key];
  const exists = current.tagCodes.includes(tagCode);
  const nextTagCodes = exists
    ? current.tagCodes.filter((code) => code !== tagCode)
    : [...current.tagCodes, tagCode];
  const tagsByCode = new Map(payload.availableTags.map((tag) => [tag.code, tag]));
  return {
    ...payload,
    groups: {
      ...payload.groups,
      [key]: {
        ...current,
        tagCodes: nextTagCodes,
        tags: nextTagCodes.map((code) => tagsByCode.get(code) ?? { code, label: code, status: "active" }),
      },
    },
  };
}

function assignedElsewhere(payload: PendingInvoiceRulesPayload, current: keyof PendingInvoiceRulesPayload["groups"]) {
  const assigned = new Set<string>();
  (Object.keys(payload.groups) as Array<keyof PendingInvoiceRulesPayload["groups"]>).forEach((key) => {
    if (key === current) {
      return;
    }
    payload.groups[key].tagCodes.forEach((code) => assigned.add(code));
  });
  return assigned;
}

function RuleGroup({
  group,
  availableTags,
  assignedElsewhere,
  disabled,
  onToggle,
}: {
  group: PendingInvoiceRuleGroup;
  availableTags: PendingInvoiceRulesPayload["availableTags"];
  assignedElsewhere: Set<string>;
  disabled: boolean;
  onToggle: (tagCode: string) => void;
}) {
  const selected = new Set(group.tagCodes);
  return (
    <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
      <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>
        {group.label}
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        {group.tags.length === 0 && group.tagCodes.length === 0 ? (
          <Typography variant="body2" color="text.secondary">暂无标签。</Typography>
        ) : null}
        {group.tags.length > 0 ? group.tags.map((tag) => (
          <Chip key={tag.code} label={tag.label || tag.code} variant="outlined" />
        )) : group.tagCodes.map((code) => (
          <Chip key={code} label={code} variant="outlined" />
        ))}
      </Stack>
      {availableTags.length > 0 ? (
        <Stack sx={{ mt: 1.5, maxHeight: 210, overflowY: "auto", pr: 0.5 }}>
          {availableTags.map((tag) => (
            <FormControlLabel
              key={tag.code}
              control={(
                <Checkbox
                  size="small"
                  checked={selected.has(tag.code)}
                  disabled={disabled || (!selected.has(tag.code) && assignedElsewhere.has(tag.code))}
                  onChange={() => onToggle(tag.code)}
                />
              )}
              label={tag.label || tag.code}
            />
          ))}
        </Stack>
      ) : null}
    </Paper>
  );
}
