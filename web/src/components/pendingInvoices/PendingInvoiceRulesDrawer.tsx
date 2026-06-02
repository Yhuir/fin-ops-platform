import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState } from "react";

import type { PendingInvoiceRuleGroup, PendingInvoiceRuleTag, PendingInvoiceRulesPayload } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PendingInvoiceRulesPayload>;
  saveRules: (payload: PendingInvoiceRulesPayload) => Promise<PendingInvoiceRulesPayload>;
  title?: string;
  refreshToken?: number;
  onSaved: () => void;
  onClose: () => void;
};

type EditableRuleGroupKey = "bankStatementAsInvoice" | "noInvoiceRequired" | "cashIncome";

function editableGroupKeys(payload: PendingInvoiceRulesPayload): EditableRuleGroupKey[] {
  return payload.direction === "income" ? ["noInvoiceRequired", "cashIncome"] : ["bankStatementAsInvoice", "noInvoiceRequired"];
}

export default function PendingInvoiceRulesDrawer({
  open,
  loadRules,
  saveRules,
  title = "待找发票规则设置",
  refreshToken = 0,
  onSaved,
  onClose,
}: PendingInvoiceRulesDrawerProps) {
  const [payload, setPayload] = useState<PendingInvoiceRulesPayload | null>(null);
  const [baselinePayload, setBaselinePayload] = useState<PendingInvoiceRulesPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);
  const payloadRef = useRef<PendingInvoiceRulesPayload | null>(null);
  const baselinePayloadRef = useRef<PendingInvoiceRulesPayload | null>(null);
  const lastHandledRefreshTokenRef = useRef(refreshToken);
  const requiresInvoiceGroup = payload ? derivedRequiresInvoiceGroup(payload) : null;

  useEffect(() => {
    payloadRef.current = payload;
    baselinePayloadRef.current = baselinePayload;
  }, [baselinePayload, payload]);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setBaselinePayload(null);
      setLoading(false);
      setSaving(false);
      setError(null);
      setRefreshNotice(null);
      lastHandledRefreshTokenRef.current = refreshToken;
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
          setBaselinePayload(nextPayload);
          setRefreshNotice(null);
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

  useEffect(() => {
    if (!open) {
      lastHandledRefreshTokenRef.current = refreshToken;
      return undefined;
    }
    if (refreshToken === lastHandledRefreshTokenRef.current) {
      return undefined;
    }
    lastHandledRefreshTokenRef.current = refreshToken;
    if (!payloadRef.current) {
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (!active) {
          return;
        }
        const currentPayload = payloadRef.current;
        const baseline = baselinePayloadRef.current;
        if (currentPayload && hasUnsavedEditableSelections(currentPayload, baseline)) {
          setPayload(mergeRefreshedRulesWithDraft(nextPayload, currentPayload, baseline));
          setRefreshNotice("银行明细自动标签已更新，已刷新标签名称并保留未保存选择。");
          return;
        }
        setPayload(nextPayload);
        setBaselinePayload(nextPayload);
        setRefreshNotice("银行明细自动标签已更新，规则标签已刷新。");
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
  }, [loadRules, open, refreshToken]);

  async function handleSave() {
    if (!payload || saving || !payload.permissions.canSave) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const savedPayload = await saveRules(payload);
      setPayload(savedPayload);
      setBaselinePayload(savedPayload);
      setRefreshNotice(null);
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
      title={title}
      subtitle={payload ? `版本 ${payload.version}` : undefined}
      closeLabel="关闭规则抽屉"
      width={1280}
      contentSx={{ p: 2 }}
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
      {refreshNotice ? <Alert severity="info">{refreshNotice}</Alert> : null}
      {payload && !payload.permissions.canSave ? <Alert severity="info">当前账号只能查看规则，不能保存。</Alert> : null}
      {payload && requiresInvoiceGroup ? (
        <Box
          data-testid="pending-invoice-rules-grid"
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
            gap: 0.85,
            alignItems: "start",
          }}
        >
          {editableGroupKeys(payload).map((key) => (
            <HierarchicalRuleBlock
              key={key}
              group={payload.groups[key]}
              tags={payload.availableTags}
              selectedCodes={new Set(payload.groups[key].tagCodes)}
              assignedElsewhere={assignedElsewhere(payload, key)}
              disabled={!payload.permissions.canSave || saving}
              onToggle={(tagCode) => setPayload(updateRuleGroup(payload, key, tagCode))}
            />
          ))}
          <HierarchicalRuleBlock
            group={requiresInvoiceGroup}
            tags={requiresInvoiceGroup.tags}
            selectedCodes={new Set(requiresInvoiceGroup.tagCodes)}
            assignedElsewhere={new Set()}
            disabled
            readonly
          />
        </Box>
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
  const nextGroups = { ...payload.groups, [key]: nextGroup };
  for (const otherKey of editableGroupKeys(payload)) {
    if (otherKey === key) {
      continue;
    }
    const otherGroup = payload.groups[otherKey];
    const nextOtherCodes = exists ? otherGroup.tagCodes : otherGroup.tagCodes.filter((code) => code !== tagCode);
    nextGroups[otherKey] = {
      ...otherGroup,
      tagCodes: nextOtherCodes,
      tags: nextOtherCodes.map((code) => tagsByCode.get(code) ?? fallbackRuleTag(code)),
    };
  }
  return {
    ...payload,
    groups: nextGroups,
  };
}

function hasUnsavedEditableSelections(
  payload: PendingInvoiceRulesPayload,
  baseline: PendingInvoiceRulesPayload | null,
) {
  if (!baseline) {
    return false;
  }
  return editableGroupKeys(payload).some((key) => !sameTagCodes(payload.groups[key].tagCodes, baseline.groups[key].tagCodes));
}

function sameTagCodes(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((code, index) => code === right[index]);
}

function mergeRefreshedRulesWithDraft(
  refreshed: PendingInvoiceRulesPayload,
  draft: PendingInvoiceRulesPayload,
  baseline: PendingInvoiceRulesPayload | null,
): PendingInvoiceRulesPayload {
  const tagsByCode = new Map(refreshed.availableTags.map((tag) => [tag.code, tag]));
  const nextGroups = { ...refreshed.groups };
  const assigned = new Set<string>();
  for (const key of editableGroupKeys(refreshed)) {
    const drafted = !sameTagCodes(draft.groups[key].tagCodes, baseline?.groups[key].tagCodes ?? []);
    const codes = activeUniqueCodes(
      (drafted ? draft.groups[key].tagCodes : refreshed.groups[key].tagCodes).filter((code) => !assigned.has(code)),
      tagsByCode,
    );
    codes.forEach((code) => assigned.add(code));
    nextGroups[key] = groupWithCodes(refreshed.groups[key], codes, tagsByCode);
  }
  return {
    ...refreshed,
    groups: nextGroups,
  };
}

function activeUniqueCodes(codes: string[], tagsByCode: Map<string, PendingInvoiceRuleTag>) {
  const result: string[] = [];
  const seen = new Set<string>();
  codes.forEach((rawCode) => {
    const code = rawCode.trim();
    if (!code || seen.has(code) || !tagsByCode.has(code)) {
      return;
    }
    seen.add(code);
    result.push(code);
  });
  return result;
}

function groupWithCodes(
  group: PendingInvoiceRuleGroup,
  tagCodes: string[],
  tagsByCode: Map<string, PendingInvoiceRuleTag>,
): PendingInvoiceRuleGroup {
  return {
    ...group,
    tagCodes,
    tags: tagCodes.map((code) => tagsByCode.get(code) ?? fallbackRuleTag(code)),
  };
}

function assignedElsewhere(payload: PendingInvoiceRulesPayload, current: EditableRuleGroupKey) {
  const assigned = new Set<string>();
  editableGroupKeys(payload).forEach((key) => {
    if (key === current) {
      return;
    }
    payload.groups[key].tagCodes.forEach((code) => assigned.add(code));
  });
  return assigned;
}

function derivedRequiresInvoiceGroup(payload: PendingInvoiceRulesPayload): PendingInvoiceRuleGroup {
  const selectedNoInvoiceCodes = new Set<string>([
    ...editableGroupKeys(payload).flatMap((key) => payload.groups[key].tagCodes),
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
    <Paper role="group" aria-label={group.label} variant="outlined" sx={{ borderRadius: 1, p: 0.75, minWidth: 0 }}>
      <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 0.55, fontSize: 13, lineHeight: 1.25 }}>
        {group.label}
      </Typography>
      {tree.length === 0 ? (
        <Typography variant="body2" color="text.secondary">暂无标签。</Typography>
      ) : (
        <Stack data-testid="pending-invoice-rule-list" spacing={0.35} sx={{ overflowY: "visible" }}>
          {tree.map(({ primary, items }) => (
            <Stack key={primary} spacing={0.2}>
              <Typography variant="caption" color="text.secondary" fontWeight={800} sx={{ fontSize: 11, lineHeight: 1.25 }}>
                {primary}
              </Typography>
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))",
                  columnGap: 0.75,
                  rowGap: 0.1,
                  pl: 0.25,
                  alignItems: "center",
                }}
              >
                {items.map((tag) => {
                  const childLabel = tagChildLabel(tag);
                  const checked = selectedCodes.has(tag.code);
                  if (readonly) {
                    return (
                      <Typography key={tag.code} variant="body2" sx={{ fontSize: 12, lineHeight: 1.35, minHeight: 20 }}>
                        {childLabel}
                      </Typography>
                    );
                  }
                  return (
                    <FormControlLabel
                      key={tag.code}
                      sx={{
                        m: 0,
                        minHeight: 21,
                        alignItems: "center",
                        "& .MuiFormControlLabel-label": { fontSize: 12, lineHeight: 1.2 },
                      }}
                      control={(
                        <Checkbox
                          size="small"
                          checked={checked}
                          disabled={disabled || (!checked && assignedElsewhere.has(tag.code))}
                          onChange={() => onToggle?.(tag.code)}
                          sx={{ p: 0.3 }}
                        />
                      )}
                      label={childLabel}
                    />
                  );
                })}
              </Box>
            </Stack>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
