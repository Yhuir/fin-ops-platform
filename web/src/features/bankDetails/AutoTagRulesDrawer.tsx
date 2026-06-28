import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Plus, RefreshCw, RotateCcw, Save, Trash2 } from "lucide-react";

import AppDialog from "../../components/common/AppDialog";
import AppDrawer from "../../components/common/AppDrawer";
import { fetchBankAutoTagRules, reapplyBankAutoTagRules, saveBankAutoTagRules } from "./api";
import type {
  BankAutoTagDirection,
  BankAutoTagEditableRule,
  BankAutoTagRuleConditions,
  BankAutoTagRefreshScope,
  BankAutoTagRulesResponse,
  BankAutoTagSystemRule,
  SaveBankAutoTagRule,
  SaveBankAutoTagRulesRequest,
} from "./types";

type AutoTagRulesDrawerProps = {
  open: boolean;
  onClose: () => void;
  onSaved?: (payload: BankAutoTagRulesResponse) => void;
  canMutateData?: boolean;
  refreshScope?: BankAutoTagRefreshScope;
  saveAutoTagRules?: (payload: SaveBankAutoTagRulesRequest) => Promise<BankAutoTagRulesResponse>;
  reapplyAutoTagRules?: () => Promise<BankAutoTagRulesResponse>;
};

type DraftRule = Omit<BankAutoTagEditableRule, "priority"> & { localId: string; priority: number | "" };
type RuleConditionKey = "containsAny" | "containsAll" | "exactAny" | "noneOf";
type RuleGroup = {
  key: string;
  primaryLabel: string;
  colorClass: string;
  rules: DraftRule[];
};

const EMPTY_RULES: BankAutoTagRuleConditions = {
  matchFields: ["all_text"],
  exactAny: [],
  containsAny: [],
  containsAll: [],
  noneOf: [],
  regexAny: [],
};

const DIRECTION_OPTIONS: { value: BankAutoTagDirection; label: string }[] = [
  { value: "any", label: "不限" },
  { value: "income", label: "收入" },
  { value: "expense", label: "支出" },
];

const HIDDEN_MATCH_FIELDS = new Set(["all_text"]);
const GROUP_COLOR_CLASSES = [
  "bank-auto-tag-group-blue",
  "bank-auto-tag-group-teal",
  "bank-auto-tag-group-green",
  "bank-auto-tag-group-amber",
  "bank-auto-tag-group-violet",
  "bank-auto-tag-group-rose",
];
const EXTERNAL_TURNOVER_ROLE = "external_turnover";
const EXTERNAL_TURNOVER_PRIMARY_LABELS = new Set(["外部往来款付款", "外部往来款收款", "往来款付款", "往来款收款"]);
const FALLBACK_TURNOVER_ACTION_TYPE_OPTIONS = [
  { value: "pending_collection", label: "待收款" },
  { value: "collected", label: "已收款" },
  { value: "pending_repayment", label: "待还款" },
  { value: "repaid", label: "已还款" },
];

function isExternalTurnoverPrimaryLabel(value: string | null | undefined) {
  return EXTERNAL_TURNOVER_PRIMARY_LABELS.has(String(value ?? "").trim());
}

function isExternalTurnoverRule(rule: Pick<DraftRule, "outputPrimaryLabel" | "turnoverRole" | "turnoverActionType">) {
  return (
    isExternalTurnoverPrimaryLabel(rule.outputPrimaryLabel)
    || rule.turnoverRole === EXTERNAL_TURNOVER_ROLE
    || Boolean(rule.turnoverActionType?.trim())
  );
}

function inferTurnoverActionType(rule: Pick<DraftRule, "outputPrimaryLabel" | "outputSubLabel" | "direction">) {
  const primary = rule.outputPrimaryLabel.trim();
  const sub = rule.outputSubLabel.trim();
  if (primary === "外部往来款付款" || primary === "往来款付款") {
    return /归还|还借款|还暂借款|偿还|还款/.test(sub) ? "repaid" : "pending_collection";
  }
  if (primary === "外部往来款收款" || primary === "往来款收款") {
    return /收回|退|退款|返还/.test(sub) ? "collected" : "pending_repayment";
  }
  if (rule.direction === "expense") {
    return "pending_collection";
  }
  if (rule.direction === "income") {
    return "pending_repayment";
  }
  return "";
}

function normalizeExternalFields(rule: DraftRule): DraftRule {
  if (!isExternalTurnoverPrimaryLabel(rule.outputPrimaryLabel)) {
    return {
      ...rule,
      outputThirdLabel: "",
      turnoverRole: "",
      turnoverActionType: "",
      turnoverFamily: "",
    };
  }
  return {
    ...rule,
    outputThirdLabel: "",
    turnoverRole: EXTERNAL_TURNOVER_ROLE,
    turnoverActionType: rule.turnoverActionType || inferTurnoverActionType(rule),
  };
}

function cloneRule(rule: BankAutoTagEditableRule, index: number): DraftRule {
  const sortOrder = typeof rule.sortOrder === "number" ? rule.sortOrder : index + 1;
  return {
    ...rule,
    outputThirdLabel: "",
    priority: normalizeRulePriority(rule.priority),
    sortOrder,
    localId: rule.code || `new-${index}`,
    accountScope: { type: "any", values: [] },
    rules: {
      matchFields: [...rule.rules.matchFields],
      exactAny: [...rule.rules.exactAny],
      containsAny: [...rule.rules.containsAny],
      containsAll: [...rule.rules.containsAll],
      noneOf: [...rule.rules.noneOf],
      regexAny: [],
    },
  };
}

function linesToValues(value: string) {
  const seen = new Set<string>();
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

function valuesToLines(values: string[]) {
  return values.join("\n");
}

function serializeRule(rule: DraftRule): SaveBankAutoTagRule {
  const externalRule = isExternalTurnoverRule(rule);
  const turnoverActionType = externalRule ? rule.turnoverActionType || inferTurnoverActionType(rule) : "";
  const outputPrimaryLabel = rule.outputPrimaryLabel.trim();
  const outputSubLabel = rule.outputSubLabel.trim();
  const label = outputSubLabel || outputPrimaryLabel;
  return {
    ...(rule.code ? { code: rule.code } : {}),
    label,
    priority: normalizeRulePriority(rule.priority),
    ...(typeof rule.sortOrder === "number" ? { sortOrder: rule.sortOrder } : {}),
    outputPrimaryLabel,
    outputSubLabel,
    ...(turnoverActionType ? { turnoverActionType } : {}),
    direction: rule.direction,
    accountScope: { type: "any", values: [] },
    rules: {
      matchFields: [...rule.rules.matchFields],
      exactAny: [...rule.rules.exactAny],
      containsAny: [...rule.rules.containsAny],
      containsAll: [...rule.rules.containsAll],
      noneOf: [...rule.rules.noneOf],
      regexAny: [],
    },
  };
}

function normalizedDraft(activeRules: DraftRule[], archivedRules: DraftRule[]) {
  return JSON.stringify({
    activeRules: activeRules.map(serializeRule),
    archivedRules: archivedRules.map(serializeRule),
  });
}

function normalizeRulePriority(value: unknown) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 2 ? parsed : 2;
}

function ruleHasPositiveCondition(rule: DraftRule) {
  return rule.rules.exactAny.length > 0 || rule.rules.containsAny.length > 0 || rule.rules.containsAll.length > 0;
}

function validateDraft(activeRules: DraftRule[]) {
  const seenLabelPaths = new Map<string, number>();
  for (const [index, rule] of activeRules.entries()) {
    const outputPrimaryLabel = rule.outputPrimaryLabel.trim();
    const outputSubLabel = rule.outputSubLabel.trim();
    if (!outputPrimaryLabel) {
      return `第 ${index + 1} 条规则的主标签名称不能为空。`;
    }
    if (!Number.isInteger(rule.priority) || Number(rule.priority) < 2) {
      return `${outputPrimaryLabel} 的普通规则优先级必须是大于等于 2 的整数。`;
    }
    const externalRule = isExternalTurnoverRule(rule);
    const labelPathKey = `${outputPrimaryLabel}\u0000${outputSubLabel}`;
    if (seenLabelPaths.has(labelPathKey)) {
      return `${ruleDisplayLabel(rule)} 的标签组合不能重复。`;
    }
    seenLabelPaths.set(labelPathKey, index);
    if (externalRule && !(rule.turnoverActionType || inferTurnoverActionType(rule))) {
      return `${ruleDisplayLabel(rule)} 必须选择台账动作类型。`;
    }
    if (rule.rules.matchFields.length === 0) {
      return `${outputPrimaryLabel} 至少选择一个匹配字段。`;
    }
    if (!ruleHasPositiveCondition(rule)) {
      return `${outputPrimaryLabel} 需要填写精准命中、包含或必须同时包含。`;
    }
  }
  return "";
}

function ruleDisplayLabel(rule: Pick<DraftRule, "label" | "outputPrimaryLabel" | "outputSubLabel">) {
  const primary = rule.outputPrimaryLabel.trim();
  const sub = rule.outputSubLabel.trim();
  const path = [primary, sub].filter(Boolean);
  if (path.length > 0) {
    return path.join(" / ");
  }
  return primary || rule.label.trim() || "未命名标签";
}

function conditionDisplay(values: string[]) {
  return values.length ? values : ["无"];
}

function fieldLabels(values: string[], fieldOptions: BankAutoTagRulesResponse["fieldOptions"]) {
  const labels = values
    .filter((value) => !HIDDEN_MATCH_FIELDS.has(value))
    .map((value) => fieldOptions.find((option) => option.value === value)?.label ?? value);
  return labels.length ? labels.join("、") : "未选择";
}

function groupRules(rules: DraftRule[]): RuleGroup[] {
  const groups: RuleGroup[] = [];
  const byKey = new Map<string, RuleGroup>();
  const sortedRules = [...rules].sort((left, right) => (
    normalizeRulePriority(left.priority) - normalizeRulePriority(right.priority)
    || Number(left.sortOrder ?? 10_000) - Number(right.sortOrder ?? 10_000)
    || String(left.code ?? left.localId).localeCompare(String(right.code ?? right.localId), "zh-Hans-CN")
  ));
  for (const rule of sortedRules) {
    const primaryLabel = rule.outputPrimaryLabel.trim() || "未命名主标签";
    const key = primaryLabel;
    let group = byKey.get(key);
    if (!group) {
      group = {
        key,
        primaryLabel,
        colorClass: GROUP_COLOR_CLASSES[groups.length % GROUP_COLOR_CLASSES.length],
        rules: [],
      };
      byKey.set(key, group);
      groups.push(group);
    }
    group.rules.push(rule);
  }
  return groups;
}

export default function AutoTagRulesDrawer({
  open,
  onClose,
  onSaved,
  canMutateData = true,
  refreshScope,
  saveAutoTagRules = saveBankAutoTagRules,
  reapplyAutoTagRules = reapplyBankAutoTagRules,
}: AutoTagRulesDrawerProps) {
  const [tab, setTab] = useState<"active" | "archived">("active");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reapplying, setReapplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [lastRefreshAction, setLastRefreshAction] = useState<"save" | "reapply">("save");
  const [version, setVersion] = useState(1);
  const [systemRule, setSystemRule] = useState<BankAutoTagSystemRule | null>(null);
  const [fieldOptions, setFieldOptions] = useState<BankAutoTagRulesResponse["fieldOptions"]>([]);
  const [, setTurnoverThirdLabelOptions] = useState<BankAutoTagRulesResponse["turnoverThirdLabelOptions"]>([]);
  const [turnoverActionTypeOptions, setTurnoverActionTypeOptions] = useState<BankAutoTagRulesResponse["turnoverActionTypeOptions"]>([]);
  const [canSave, setCanSave] = useState(true);
  const [activeRules, setActiveRules] = useState<DraftRule[]>([]);
  const [archivedRules, setArchivedRules] = useState<DraftRule[]>([]);
  const [baseline, setBaseline] = useState("");
  const [conditionEditor, setConditionEditor] = useState<{
    localId: string;
    key: RuleConditionKey;
    label: string;
    values: string[];
  } | null>(null);
  const [pendingArchiveRule, setPendingArchiveRule] = useState<DraftRule | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setFeedback(null);
    setTab("active");
    fetchBankAutoTagRules({ signal: controller.signal })
      .then((payload) => {
        const nextActive = payload.activeRules.map(cloneRule);
        const nextArchived = payload.archivedRules.map(cloneRule);
        setVersion(payload.version);
        setSystemRule(payload.systemRule);
        setFieldOptions(payload.fieldOptions);
        setTurnoverThirdLabelOptions(payload.turnoverThirdLabelOptions);
        setTurnoverActionTypeOptions(payload.turnoverActionTypeOptions);
        setCanSave(payload.permissions.canSave);
        setActiveRules(nextActive);
        setArchivedRules(nextArchived);
        setBaseline(normalizedDraft(nextActive, nextArchived));
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "自动标签规则加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [open]);

  const dirty = useMemo(() => normalizedDraft(activeRules, archivedRules) !== baseline, [activeRules, archivedRules, baseline]);
  const readonly = !canMutateData || !canSave || saving || reapplying || loading;
  const reapplyDisabled = readonly || dirty;
  const visibleFieldOptions = fieldOptions.filter((option) => !HIDDEN_MATCH_FIELDS.has(option.value));
  const visibleTurnoverActionTypeOptions = turnoverActionTypeOptions.length ? turnoverActionTypeOptions : FALLBACK_TURNOVER_ACTION_TYPE_OPTIONS;
  const activeRuleGroups = useMemo(() => groupRules(activeRules), [activeRules]);

  const requestClose = () => {
    if (dirty && !window.confirm("自动标签规则有未保存修改，确定关闭吗？")) {
      return;
    }
    onClose();
  };

  const updateActiveRule = (localId: string, updater: (rule: DraftRule) => DraftRule) => {
    setActiveRules((current) => current.map((rule) => (rule.localId === localId ? updater(rule) : rule)));
  };

  const updateGroupPrimaryLabel = (group: RuleGroup, value: string) => {
    const localIds = new Set(group.rules.map((rule) => rule.localId));
    setActiveRules((current) => current.map((rule) => (
      localIds.has(rule.localId) ? normalizeExternalFields({ ...rule, outputPrimaryLabel: value }) : rule
    )));
  };

  const addRule = () => {
    const createdAt = Date.now();
    setActiveRules((current) => [
      ...current,
      {
        localId: `new-${createdAt}`,
        label: "",
        outputPrimaryLabel: "",
        outputSubLabel: "",
        status: "active",
        source: "custom",
        priority: 2,
        priorityLabel: "优先级 2",
        sortOrder: current.length + archivedRules.length + 1,
        direction: "any",
        accountScope: { type: "any", values: [] },
        rules: { ...EMPTY_RULES, matchFields: ["purpose_text", "summary_text", "note_text", "detail_text"] },
        ruleSummary: "",
        editable: true,
        archivable: true,
        sortable: true,
      },
    ]);
    setTab("active");
  };

  const archiveRule = (localId: string) => {
    setActiveRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      if (target.code) {
        setArchivedRules((archived) => [
          ...archived.filter((rule) => rule.code !== target.code),
          { ...target, status: "archived" },
        ]);
      }
      return current.filter((rule) => rule.localId !== localId);
    });
  };

  const restoreRule = (localId: string) => {
    setArchivedRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      setActiveRules((active) => [...active, { ...target, status: "active", priority: 2 }]);
      return current.filter((rule) => rule.localId !== localId);
    });
    setTab("active");
  };

  const saveRules = () => {
    const validation = validateDraft(activeRules);
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError(null);
    setLastRefreshAction("save");
    saveAutoTagRules({
      expectedVersion: version,
      refreshScope,
      activeRules: activeRules.map(serializeRule),
      archivedRules: archivedRules.filter((rule) => rule.code).map(serializeRule),
    })
      .then((payload) => {
        const nextActive = payload.activeRules.map(cloneRule);
        const nextArchived = payload.archivedRules.map(cloneRule);
        setVersion(payload.version);
        setSystemRule(payload.systemRule);
        setFieldOptions(payload.fieldOptions);
        setTurnoverThirdLabelOptions(payload.turnoverThirdLabelOptions);
        setTurnoverActionTypeOptions(payload.turnoverActionTypeOptions);
        setCanSave(payload.permissions.canSave);
        setActiveRules(nextActive);
        setArchivedRules(nextArchived);
        setBaseline(normalizedDraft(nextActive, nextArchived));
        setFeedback("规则已保存，银行明细已刷新。");
        onSaved?.(payload);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "自动标签规则保存失败。");
      })
      .finally(() => setSaving(false));
  };

  const reapplyRules = () => {
    if (dirty) {
      setError("请先保存规则后再重新应用。");
      return;
    }
    setReapplying(true);
    setError(null);
    setLastRefreshAction("reapply");
    reapplyAutoTagRules()
      .then((payload) => {
        const nextActive = payload.activeRules.map(cloneRule);
        const nextArchived = payload.archivedRules.map(cloneRule);
        setVersion(payload.version);
        setSystemRule(payload.systemRule);
        setFieldOptions(payload.fieldOptions);
        setTurnoverThirdLabelOptions(payload.turnoverThirdLabelOptions);
        setTurnoverActionTypeOptions(payload.turnoverActionTypeOptions);
        setCanSave(payload.permissions.canSave);
        setActiveRules(nextActive);
        setArchivedRules(nextArchived);
        setBaseline(normalizedDraft(nextActive, nextArchived));
        setFeedback("重新应用已完成，银行明细已刷新。");
        onSaved?.(payload);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "自动标签规则重新应用失败。");
      })
      .finally(() => setReapplying(false));
  };

  const commitConditionEditor = () => {
    if (!conditionEditor) {
      return;
    }
    const values = conditionEditor.values;
    updateActiveRule(conditionEditor.localId, (rule) => ({
      ...rule,
      rules: { ...rule.rules, [conditionEditor.key]: values },
    }));
    setConditionEditor(null);
  };

  return (
    <AppDrawer
      className="bank-auto-tag-drawer-paper"
      closeLabel="关闭自动标签规则抽屉"
      open={open}
      title="自动标签规则"
      width="80vw"
      onClose={requestClose}
    >
      <div className="bank-auto-tag-drawer">
        <div className="bank-auto-tag-drawer-toolbar">
          <div className="bank-auto-tag-status-tabs" role="group" aria-label="自动标签规则状态">
            <button
              type="button"
              className={`bank-auto-tag-tab${tab === "active" ? " is-active" : ""}`}
              aria-pressed={tab === "active"}
              onClick={() => setTab("active")}
            >
              可用
            </button>
            <button
              type="button"
              className={`bank-auto-tag-tab${tab === "archived" ? " is-active" : ""}`}
              aria-pressed={tab === "archived"}
              onClick={() => setTab("archived")}
            >
              停用
            </button>
          </div>
          <div className="bank-auto-tag-toolbar-actions">
            <ActionButton disabled={readonly} icon={<Plus aria-hidden="true" size={14} />} label="新增标签" onClick={addRule} />
            <ActionButton
              disabled={reapplyDisabled}
              icon={<RefreshCw aria-hidden="true" size={14} />}
              label="重新应用规则"
              title={dirty ? "请先保存规则后再重新应用" : undefined}
              onClick={reapplyRules}
            />
            <ActionButton
              className="bank-auto-tag-action-primary"
              disabled={readonly || !dirty}
              icon={<Save aria-hidden="true" size={14} />}
              label="保存"
              onClick={saveRules}
            />
          </div>
        </div>
        <div className="bank-auto-tag-table-shell">
          {loading ? (
            <div className="bank-auto-tag-loading" role="status">
              <span className="bank-auto-tag-spinner" aria-hidden="true" />
              <span>正在读取规则</span>
            </div>
          ) : null}
          {error ? <div className="bank-auto-tag-alert bank-auto-tag-alert--error" role="alert">{error}</div> : null}
          {feedback ? <div className="bank-auto-tag-alert bank-auto-tag-alert--success" role="status">{feedback}</div> : null}
          {tab === "active" ? (
            <div className="bank-auto-tag-table-container">
              <table className="bank-auto-tag-rule-table" aria-label="自动标签规则表格">
                <colgroup>
                  <col className="bank-auto-tag-col-primary" />
                  <col className="bank-auto-tag-col-sub" />
                  <col className="bank-auto-tag-col-direction" />
                  <col className="bank-auto-tag-col-fields" />
                  <col className="bank-auto-tag-col-contains" />
                  <col className="bank-auto-tag-col-contains-all" />
                  <col className="bank-auto-tag-col-exact" />
                  <col className="bank-auto-tag-col-none" />
                  <col className="bank-auto-tag-col-priority" />
                  <col className="bank-auto-tag-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th className="finance-table__column" scope="col">主标签</th>
                    <th className="finance-table__column" scope="col">子标签</th>
                    <th className="finance-table__column" scope="col">流水类型</th>
                    <th className="finance-table__column" scope="col">查询项</th>
                    <th className="finance-table__column" scope="col">包含</th>
                    <th className="finance-table__column" scope="col">必须同时包含</th>
                    <th className="finance-table__column" scope="col">精准命中</th>
                    <th className="finance-table__column" scope="col">不包含字样</th>
                    <th className="finance-table__column" scope="col">优先级</th>
                    <th className="finance-table__column bank-auto-tag-actions-column" scope="col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {systemRule ? (
                    <tr className="bank-auto-tag-system-row">
                      <td className="finance-table__cell">{systemRule.label}</td>
                      <td className="finance-table__cell">系统规则</td>
                      <td className="finance-table__cell">不限</td>
                      <td className="finance-table__cell">-</td>
                      <td className="finance-table__cell">-</td>
                      <td className="finance-table__cell">-</td>
                      <td className="finance-table__cell">-</td>
                      <td className="finance-table__cell">-</td>
                      <td className="finance-table__cell">1</td>
                      <td className="finance-table__cell bank-auto-tag-actions-cell">-</td>
                    </tr>
                  ) : null}
                  {activeRuleGroups.flatMap((group) => group.rules.map((rule, rowIndex) => (
                    <tr key={rule.localId} className={`bank-auto-tag-rule-row ${group.colorClass}`}>
                      {rowIndex === 0 ? (
                        <td
                          rowSpan={group.rules.length}
                          className={`finance-table__cell bank-auto-tag-primary-cell ${group.colorClass}`}
                        >
                          <input
                            className="bank-auto-tag-input"
                            placeholder="主标签名称"
                            value={group.primaryLabel === "未命名主标签" ? "" : group.primaryLabel}
                            disabled={readonly}
                            aria-label={`${group.primaryLabel} 主标签`}
                            onChange={(event) => updateGroupPrimaryLabel(group, event.target.value)}
                          />
                        </td>
                      ) : null}
                      <td className="finance-table__cell">
                        <div className="bank-auto-tag-cell-stack">
                          <input
                            className="bank-auto-tag-input"
                            placeholder="子标签名称"
                            value={rule.outputSubLabel}
                            disabled={readonly}
                            aria-label={`${ruleDisplayLabel(rule)} 子标签`}
                            onChange={(event) => updateActiveRule(rule.localId, (current) => normalizeExternalFields({
                              ...current,
                              outputSubLabel: event.target.value,
                            }))}
                          />
                          {isExternalTurnoverRule(rule) ? (
                            <span
                              className="bank-auto-tag-select-trigger is-disabled"
                              role="combobox"
                              aria-disabled="true"
                              aria-label={`${ruleDisplayLabel(rule)} 子子标签`}
                            >
                              匹配后待确认
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="finance-table__cell">
                        <div className="bank-auto-tag-cell-stack">
                          <SingleSelect
                            ariaLabel={`${ruleDisplayLabel(rule)} 流水类型`}
                            disabled={readonly}
                            options={DIRECTION_OPTIONS}
                            value={rule.direction}
                            onChange={(value) => updateActiveRule(rule.localId, (current) => normalizeExternalFields({
                              ...current,
                              direction: value as BankAutoTagDirection,
                            }))}
                          />
                          {isExternalTurnoverRule(rule) ? (
                            <SingleSelect
                              ariaLabel={`${ruleDisplayLabel(rule)} 台账动作类型`}
                              disabled={readonly}
                              options={visibleTurnoverActionTypeOptions}
                              value={rule.turnoverActionType || inferTurnoverActionType(rule)}
                              onChange={(value) => updateActiveRule(rule.localId, (current) => ({
                                ...current,
                                turnoverRole: EXTERNAL_TURNOVER_ROLE,
                                turnoverActionType: value,
                              }))}
                            />
                          ) : null}
                        </div>
                      </td>
                      <td className="finance-table__cell">
                        <MatchFieldPicker
                          ariaLabel={`${ruleDisplayLabel(rule)} 查询项`}
                          disabled={readonly}
                          fieldOptions={visibleFieldOptions}
                          labels={fieldLabels(rule.rules.matchFields, fieldOptions)}
                          selectedValues={rule.rules.matchFields.filter((field) => !HIDDEN_MATCH_FIELDS.has(field))}
                          onChange={(selectedValues) => updateActiveRule(rule.localId, (current) => ({
                            ...current,
                            rules: { ...current.rules, matchFields: selectedValues },
                          }))}
                        />
                      </td>
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="包含"
                        values={rule.rules.containsAny}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "containsAny", label: "包含", values: rule.rules.containsAny })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="必须同时包含"
                        values={rule.rules.containsAll}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "containsAll", label: "必须同时包含", values: rule.rules.containsAll })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="精准命中"
                        values={rule.rules.exactAny}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "exactAny", label: "精准命中", values: rule.rules.exactAny })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="不包含字样"
                        values={rule.rules.noneOf}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "noneOf", label: "不包含字样", values: rule.rules.noneOf })}
                      />
                      <td className="finance-table__cell bank-auto-tag-priority-cell">
                        <input
                          className="bank-auto-tag-input bank-auto-tag-priority-value"
                          type="number"
                          value={rule.priority}
                          disabled={readonly}
                          aria-label={`${ruleDisplayLabel(rule)} 优先级`}
                          min={2}
                          step={1}
                          onChange={(event) => updateActiveRule(rule.localId, (current) => ({
                            ...current,
                            priority: event.target.value === "" ? "" : Number(event.target.value),
                          }))}
                        />
                      </td>
                      <td className="finance-table__cell bank-auto-tag-actions-cell">
                        <button
                          type="button"
                          className="bank-auto-tag-icon-button"
                          aria-label={`停用 ${ruleDisplayLabel(rule)}`}
                          disabled={readonly}
                          title="停用"
                          onClick={() => setPendingArchiveRule(rule)}
                        >
                          <Trash2 aria-hidden="true" size={14} />
                        </button>
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bank-auto-tag-archived-list">
              {archivedRules.length === 0 ? <div className="bank-auto-tag-alert bank-auto-tag-alert--info">暂无停用标签。</div> : null}
              {archivedRules.map((rule) => (
                <div key={rule.localId} className="bank-auto-tag-archived-item">
                  <div className="bank-auto-tag-archived-label">
                    <span className="bank-auto-tag-archived-chip">已停用</span>
                    <strong>{ruleDisplayLabel(rule)}</strong>
                  </div>
                  <ActionButton
                    disabled={readonly}
                    icon={<RotateCcw aria-hidden="true" size={14} />}
                    label="重新启用"
                    onClick={() => restoreRule(rule.localId)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <AppDialog
        open={conditionEditor !== null}
        title={conditionEditor?.label ?? ""}
        maxWidth="sm"
        onClose={() => setConditionEditor(null)}
        actions={(
          <>
            <button type="button" className="bank-auto-tag-dialog-button" onClick={() => setConditionEditor(null)}>取消</button>
            <button type="button" className="bank-auto-tag-dialog-button bank-auto-tag-dialog-button-primary" onClick={commitConditionEditor}>确定</button>
          </>
        )}
      >
        <textarea
          className="bank-auto-tag-condition-textarea"
          autoFocus
          rows={10}
          value={valuesToLines(conditionEditor?.values ?? [])}
          onChange={(event) => setConditionEditor((current) => current ? {
            ...current,
            values: linesToValues(event.target.value),
          } : current)}
        />
      </AppDialog>
      <AppDialog
        open={pendingArchiveRule !== null}
        title="确认停用标签"
        description={pendingArchiveRule ? `确定停用「${ruleDisplayLabel(pendingArchiveRule)}」吗？` : ""}
        onClose={() => setPendingArchiveRule(null)}
        actions={(
          <>
            <button type="button" className="bank-auto-tag-dialog-button" onClick={() => setPendingArchiveRule(null)}>取消</button>
            <button
              type="button"
              className="bank-auto-tag-dialog-button bank-auto-tag-dialog-button-danger"
              onClick={() => {
                if (pendingArchiveRule) {
                  archiveRule(pendingArchiveRule.localId);
                }
                setPendingArchiveRule(null);
              }}
            >
              确认停用
            </button>
          </>
        )}
      />
    </AppDrawer>
  );
}

function ActionButton({
  className = "",
  disabled,
  icon,
  label,
  title,
  onClick,
}: {
  className?: string;
  disabled?: boolean;
  icon: ReactNode;
  label: string;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`bank-auto-tag-action-button${className ? ` ${className}` : ""}`}
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function SingleSelect({
  ariaLabel,
  disabled,
  options,
  value,
  onChange,
}: {
  ariaLabel: string;
  disabled: boolean;
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div
      className="bank-auto-tag-select"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="bank-auto-tag-select-trigger"
        role="combobox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {selected?.label ?? "未选择"}
      </button>
      {open ? (
        <div className="bank-auto-tag-select-listbox" role="listbox">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className="bank-auto-tag-select-option"
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MatchFieldPicker({
  ariaLabel,
  disabled,
  fieldOptions,
  labels,
  selectedValues,
  onChange,
}: {
  ariaLabel: string;
  disabled: boolean;
  fieldOptions: BankAutoTagRulesResponse["fieldOptions"];
  labels: string;
  selectedValues: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = new Set(selectedValues);

  return (
    <div
      className="bank-auto-tag-select"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="bank-auto-tag-select-trigger"
        role="combobox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {labels}
      </button>
      {open ? (
        <div className="bank-auto-tag-select-listbox bank-auto-tag-field-listbox" role="listbox">
          <div className="bank-auto-tag-field-menu-actions">
            <button type="button" disabled={disabled} onClick={() => onChange(fieldOptions.map((option) => option.value))}>
              全选
            </button>
            <button type="button" disabled={disabled} onClick={() => onChange([])}>
              清空
            </button>
          </div>
          {fieldOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={selected.has(option.value)}
              className="bank-auto-tag-select-option"
              onClick={() => {
                const next = selected.has(option.value)
                  ? selectedValues.filter((item) => item !== option.value)
                  : [...selectedValues, option.value];
                onChange(next);
              }}
            >
              <span className="bank-auto-tag-option-check" aria-hidden="true">{selected.has(option.value) ? "✓" : ""}</span>
              <span>{option.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ConditionCell({
  ruleLabel,
  label,
  values,
  disabled,
  onEdit,
}: {
  ruleLabel: string;
  label: string;
  values: string[];
  disabled: boolean;
  onEdit: () => void;
}) {
  return (
    <td className="finance-table__cell">
      <button
        type="button"
        className="bank-auto-tag-condition-field-button"
        aria-label={`编辑${ruleLabel}${label}`}
        disabled={disabled}
        onClick={onEdit}
      >
        <span className="bank-auto-tag-condition-preview">
          {conditionDisplay(values).map((value) => (
            <span key={value} className={value === "无" ? "is-empty" : undefined}>
              {value}
            </span>
          ))}
        </span>
      </button>
    </td>
  );
}
