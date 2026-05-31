import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { PendingInvoiceRuleGroup, PendingInvoiceRuleTag, PendingInvoiceRulesPayload } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PendingInvoiceRulesPayload>;
  saveRules: (payload: PendingInvoiceRulesPayload) => Promise<PendingInvoiceRulesPayload>;
  onSaved: () => void;
  onClose: () => void;
};

type EditableRuleGroupKey = "bankStatementAsInvoice" | "noInvoiceRequired";

const EDITABLE_GROUP_KEYS: EditableRuleGroupKey[] = ["bankStatementAsInvoice", "noInvoiceRequired"];

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
  const requiresInvoiceGroup = payload ? derivedRequiresInvoiceGroup(payload) : null;

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
      width={560}
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
      {payload && requiresInvoiceGroup ? (
        <Stack spacing={1}>
          <HierarchicalRuleBlock
            group={payload.groups.bankStatementAsInvoice}
            tags={payload.availableTags}
            selectedCodes={new Set(payload.groups.bankStatementAsInvoice.tagCodes)}
            assignedElsewhere={assignedElsewhere(payload, "bankStatementAsInvoice")}
            disabled={!payload.permissions.canSave || saving}
            onToggle={(tagCode) => setPayload(updateRuleGroup(payload, "bankStatementAsInvoice", tagCode))}
          />
          <HierarchicalRuleBlock
            group={payload.groups.noInvoiceRequired}
            tags={payload.availableTags}
            selectedCodes={new Set(payload.groups.noInvoiceRequired.tagCodes)}
            assignedElsewhere={assignedElsewhere(payload, "noInvoiceRequired")}
            disabled={!payload.permissions.canSave || saving}
            onToggle={(tagCode) => setPayload(updateRuleGroup(payload, "noInvoiceRequired", tagCode))}
          />
          <HierarchicalRuleBlock
            group={requiresInvoiceGroup}
            tags={requiresInvoiceGroup.tags}
            selectedCodes={new Set(requiresInvoiceGroup.tagCodes)}
            assignedElsewhere={new Set()}
            disabled
            readonly
          />
        </Stack>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function updateRuleGroup(
  payload: PendingInvoiceRulesPayload,
  key: EditableRuleGroupKey,
  tagCode: string,
): PendingInvoiceRulesPayload {
  const current = payload.groups[key];
  const exists = current.tagCodes.includes(tagCode);
  const nextTagCodes = exists
    ? current.tagCodes.filter((code) => code !== tagCode)
    : [...current.tagCodes, tagCode];
  const tagsByCode = new Map(payload.availableTags.map((tag) => [tag.code, tag]));
  const nextGroup = {
    ...current,
    tagCodes: nextTagCodes,
    tags: nextTagCodes.map((code) => tagsByCode.get(code) ?? fallbackRuleTag(code)),
  };
  const otherKey: EditableRuleGroupKey = key === "bankStatementAsInvoice" ? "noInvoiceRequired" : "bankStatementAsInvoice";
  const otherGroup = payload.groups[otherKey];
  const nextOtherCodes = exists ? otherGroup.tagCodes : otherGroup.tagCodes.filter((code) => code !== tagCode);
  return {
    ...payload,
    groups: {
      ...payload.groups,
      [key]: nextGroup,
      [otherKey]: {
        ...otherGroup,
        tagCodes: nextOtherCodes,
        tags: nextOtherCodes.map((code) => tagsByCode.get(code) ?? fallbackRuleTag(code)),
      },
    },
  };
}

function assignedElsewhere(payload: PendingInvoiceRulesPayload, current: EditableRuleGroupKey) {
  const assigned = new Set<string>();
  EDITABLE_GROUP_KEYS.forEach((key) => {
    if (key === current) {
      return;
    }
    payload.groups[key].tagCodes.forEach((code) => assigned.add(code));
  });
  return assigned;
}

function derivedRequiresInvoiceGroup(payload: PendingInvoiceRulesPayload): PendingInvoiceRuleGroup {
  const selectedNoInvoiceCodes = new Set<string>([
    ...payload.groups.bankStatementAsInvoice.tagCodes,
    ...payload.groups.noInvoiceRequired.tagCodes,
  ]);
  const tags = payload.availableTags.filter((tag) => !selectedNoInvoiceCodes.has(tag.code));
  return {
    ...payload.groups.requiresInvoice,
    tagCodes: tags.map((tag) => tag.code),
    tags,
  };
}

function fallbackRuleTag(code: string): PendingInvoiceRuleTag {
  return {
    code,
    label: code,
    outputPrimaryLabel: code,
    outputSubLabel: "",
    status: "active",
  };
}

function tagPrimaryLabel(tag: PendingInvoiceRuleTag) {
  return tag.outputPrimaryLabel.trim() || tag.label.trim() || tag.code;
}

function tagChildLabel(tag: PendingInvoiceRuleTag) {
  return tag.outputSubLabel.trim() || tag.label.trim() || tagPrimaryLabel(tag);
}

function tagTree(tags: PendingInvoiceRuleTag[]) {
  const groups = new Map<string, PendingInvoiceRuleTag[]>();
  tags.forEach((tag) => {
    const primary = tagPrimaryLabel(tag);
    groups.set(primary, [...(groups.get(primary) ?? []), tag]);
  });
  return Array.from(groups.entries()).map(([primary, items]) => ({ primary, items }));
}

function HierarchicalRuleBlock({
  group,
  tags,
  selectedCodes,
  assignedElsewhere,
  disabled,
  readonly = false,
  onToggle,
}: {
  group: PendingInvoiceRuleGroup;
  tags: PendingInvoiceRuleTag[];
  selectedCodes: Set<string>;
  assignedElsewhere: Set<string>;
  disabled: boolean;
  readonly?: boolean;
  onToggle?: (tagCode: string) => void;
}) {
  const tree = tagTree(tags);
  return (
    <Paper role="group" aria-label={group.label} variant="outlined" sx={{ borderRadius: 1, p: 1.25 }}>
      <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 0.75 }}>
        {group.label}
      </Typography>
      {tree.length === 0 ? (
        <Typography variant="body2" color="text.secondary">暂无标签。</Typography>
      ) : (
        <Stack spacing={0.5} sx={{ maxHeight: readonly ? 180 : 220, overflowY: "auto", pr: 0.5 }}>
          {tree.map(({ primary, items }) => (
            <Stack key={primary} spacing={0.25}>
              <Typography variant="caption" color="text.secondary" fontWeight={800}>
                {primary}
              </Typography>
              <Stack spacing={0.15} sx={{ pl: 1.5 }}>
                {items.map((tag) => {
                  const childLabel = tagChildLabel(tag);
                  const checked = selectedCodes.has(tag.code);
                  if (readonly) {
                    return (
                      <Typography key={tag.code} variant="body2" sx={{ lineHeight: 1.65 }}>
                        {childLabel}
                      </Typography>
                    );
                  }
                  return (
                    <FormControlLabel
                      key={tag.code}
                      sx={{
                        m: 0,
                        minHeight: 28,
                        "& .MuiFormControlLabel-label": { fontSize: 13 },
                      }}
                      control={(
                        <Checkbox
                          size="small"
                          checked={checked}
                          disabled={disabled || (!checked && assignedElsewhere.has(tag.code))}
                          onChange={() => onToggle?.(tag.code)}
                          sx={{ p: 0.5 }}
                        />
                      )}
                      label={childLabel}
                    />
                  );
                })}
              </Stack>
            </Stack>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
