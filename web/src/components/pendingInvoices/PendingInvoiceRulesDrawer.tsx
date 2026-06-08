import { useEffect, useRef, useState } from "react";

import type { PendingInvoiceRuleGroup, PendingInvoiceRuleTag, PendingInvoiceRulesPayload } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PendingInvoiceRulesPayload>;
  saveRules: (payload: PendingInvoiceRulesPayload) => Promise<PendingInvoiceRulesPayload>;
  title?: string;
  refreshToken?: number;
  onSaved: (payload: PendingInvoiceRulesPayload) => void;
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
      setRefreshNotice(savedPayload.readModelStatus === "refreshing" ? "规则已保存，相关数据正在刷新。" : "规则已保存。");
      onSaved(savedPayload);
    } catch (reason) {
      setError(resolveRuleSaveErrorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <PendingInvoiceDrawerFrame
      open={open}
      title={title}
      closeLabel="关闭规则抽屉"
      width={1280}
      contentSx={{ p: 2 }}
      onClose={onClose}
      footer={(
        <div className="pending-invoice-drawer-actions">
          <button className="pending-invoices-button" disabled={saving} onClick={onClose} type="button">关闭</button>
          <button
            className="pending-invoices-button pending-invoices-button--primary"
            disabled={!payload?.permissions.canSave || loading || saving}
            onClick={handleSave}
            type="button"
          >
            保存规则
          </button>
        </div>
      )}
    >
      {loading ? <LoadingMessage label="正在加载待找发票规则" text="正在读取规则" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {refreshNotice ? <StatusMessage tone="info">{refreshNotice}</StatusMessage> : null}
      {payload && !payload.permissions.canSave ? <StatusMessage tone="info">当前账号只能查看规则，不能保存。</StatusMessage> : null}
      {payload && requiresInvoiceGroup ? (
        <div
          className="pending-invoice-rules-grid"
          data-testid="pending-invoice-rules-grid"
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
        </div>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function LoadingMessage({ label, text }: { label: string; text: string }) {
  return (
    <div aria-label={label} className="pending-invoice-status-message" role="status">
      <span aria-hidden="true" className="pending-invoice-spinner" />
      <span>{text}</span>
    </div>
  );
}

function StatusMessage({ children, tone }: { children: string; tone: "danger" | "success" | "info" }) {
  return (
    <div className={`pending-invoice-status-message pending-invoice-status-message--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </div>
  );
}

function resolveRuleSaveErrorMessage(reason: unknown) {
  const status = reason && typeof reason === "object" ? Number((reason as { status?: unknown }).status) : 0;
  const code = reason && typeof reason === "object" ? String((reason as { code?: unknown }).code ?? "") : "";
  if (
    status === 409
    && (
      code === "pending_invoice_tag_groups_version_conflict"
      || code === "pending_output_invoice_tag_groups_version_conflict"
    )
  ) {
    return "规则已被其他人更新。请刷新规则后再保存，当前勾选内容已保留。";
  }
  return reason instanceof Error ? reason.message : "规则保存失败";
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
    <section aria-label={group.label} className="pending-invoice-rule-block" role="group">
      <div className="pending-invoice-rule-block__header">
        <h3 className="pending-invoice-rule-block__title">{group.label}</h3>
        {readonly ? <span className="pending-invoice-rule-block__badge">自动归类</span> : null}
      </div>
      {tree.length === 0 ? (
        <p className="pending-invoice-empty">暂无标签。</p>
      ) : (
        <div className="pending-invoice-rule-list" data-testid="pending-invoice-rule-list">
          {tree.map(({ primary, items }) => (
            <div className="pending-invoice-rule-primary" key={primary}>
              <div
                className={`pending-invoice-rule-primary__label${readonly ? " pending-invoice-rule-primary__label--readonly" : ""}`}
                data-testid="pending-invoice-rule-primary-label"
              >
                {primary}
              </div>
              <div className={`pending-invoice-rule-tags${readonly ? " pending-invoice-rule-tags--readonly" : ""}`}>
                {items.map((tag) => {
                  const childLabel = tagChildLabel(tag);
                  const checked = selectedCodes.has(tag.code);
                  if (readonly) {
                    return (
                      <span
                        className="pending-invoice-rule-readonly-tag"
                        key={tag.code}
                        data-testid="pending-invoice-rule-readonly-tag"
                      >
                        <span aria-hidden="true" className="pending-invoice-rule-readonly-tag__dot" />
                        <span className="pending-invoice-rule-readonly-tag__label">{childLabel}</span>
                      </span>
                    );
                  }
                  return (
                    <label
                      className="pending-invoice-rule-checkbox"
                      key={tag.code}
                    >
                      <input
                        checked={checked}
                        disabled={disabled || (!checked && assignedElsewhere.has(tag.code))}
                        onChange={() => onToggle?.(tag.code)}
                        type="checkbox"
                      />
                      <span>{childLabel}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
