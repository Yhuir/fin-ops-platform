import { Button, Checkbox, Input, ListBox, Select } from "@heroui/react";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import PaymentRuleApplicantSelect from "./PaymentRuleApplicantSelect";
import AppDrawer from "../common/AppDrawer";
import AppDialog from "../common/AppDialog";
import type {
  InputInvoiceUsagePaymentStatusRulesResponse,
  PaymentRuleApplicantOption,
  SaveInputInvoiceUsagePaymentStatusRulesRequest,
} from "../../features/inputInvoiceUsage/types";

export type PaymentStatusRule = {
  id?: string;
  code?: string;
  statusCode?: string;
  label: string;
  description: string;
  reason?: string;
  priority: number;
  enabled?: boolean;
  conditions?: Record<string, unknown>;
};

export type PaymentStatusRulesPayload = {
  version?: number | string | null;
  readOnly?: boolean;
  permissions?: {
    canSave?: boolean;
    can_save?: boolean;
  };
  rules: PaymentStatusRule[];
  applicantOptions: PaymentRuleApplicantOption[];
};

type RuleConditionKey = "hasOa" | "hasBank" | "fullyMatched" | "invoiceOaAmountMatched";

const CONDITION_FIELDS: Array<{
  key: RuleConditionKey;
  label: string;
  trueLabel: string;
  falseLabel: string;
}> = [
  { key: "hasOa", label: "OA", trueLabel: "需要 OA", falseLabel: "无 OA" },
  { key: "hasBank", label: "流水", trueLabel: "需要流水", falseLabel: "无流水" },
  { key: "fullyMatched", label: "完全匹配", trueLabel: "必须完全匹配", falseLabel: "不得完全匹配" },
  { key: "invoiceOaAmountMatched", label: "发票/OA 金额", trueLabel: "金额必须匹配", falseLabel: "金额不得匹配" },
];

const OUTPUT_CLASSES = [
  { id: "paid", label: "发票＝付款" },
  { id: "cash_turnover", label: "现金往来" },
  { id: "offset", label: "冲" },
  { id: "waiting_payment", label: "未关联流水" },
  { id: "invoice_less_payment", label: "发票＜付款" },
  { id: "invoice_greater_payment", label: "发票＞付款" },
];

type PaymentStatusRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<PaymentStatusRulesPayload>;
  saveRules?: (request: SaveInputInvoiceUsagePaymentStatusRulesRequest) => Promise<InputInvoiceUsagePaymentStatusRulesResponse | PaymentStatusRulesPayload>;
  onSaved?: () => Promise<void> | void;
  onClose: () => void;
};

export default function PaymentStatusRulesDrawer({
  open,
  loadRules,
  saveRules,
  onSaved,
  onClose,
}: PaymentStatusRulesDrawerProps) {
  const [payload, setPayload] = useState<PaymentStatusRulesPayload | null>(null);
  const [draftRules, setDraftRules] = useState<PaymentStatusRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setConfirmClose(false);
      setPayload(null);
      setDraftRules([]);
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
    ? JSON.stringify(draftRules)
      !== JSON.stringify(payload.rules)
    : false;

  const outputClasses = [...OUTPUT_CLASSES, ...Array.from(new Map(draftRules.filter(rule => rule.statusCode?.startsWith("custom_")).map(rule => [rule.statusCode!, { id: rule.statusCode!, label: rule.label }])).values())];
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
        id: rule.id,
        statusCode: rule.statusCode,
        conditions: rule.conditions,
        label: rule.label.trim(),
        priority: Number(rule.priority),
        enabled: rule.enabled !== false,
      })),
    })
      .then(async (nextPayload) => {
        setPayload({ ...nextPayload, applicantOptions: payload.applicantOptions });
        setDraftRules(cloneRules(nextPayload.rules));
        setFeedback("规则已保存。");
        await onSaved?.();
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

  const footer = payload && canSave ? (
    <div className="input-invoice-usage-rules-actions input-invoice-usage-payment-rules-footer">
      <Button
        className="input-invoice-usage-button"
        isDisabled={saving || loading || !dirty}
        onPress={() => {
          setDraftRules(cloneRules(payload.rules));
          setError(null);
          setFeedback(null);
        }}
        size="sm"
        variant="secondary"
      >
        还原
      </Button>
      <Button
        className="input-invoice-usage-button input-invoice-usage-button--primary"
        isDisabled={saving || loading || !dirty}
        isPending={saving}
        onPress={handleSave}
        size="sm"
        variant="primary"
      >
        保存
      </Button>
    </div>
  ) : null;

  return (
    <>
    <AppDrawer
      className="input-invoice-usage-rules-drawer"
      closeLabel="关闭支付状态规则抽屉"
      footer={footer}
      closeDisabled={saving}
      onClose={() => dirty ? setConfirmClose(true) : onClose()}
      open={open}
      title="发票与支付状态规则设置"
      width="min(880px, 100vw)"
    >
      <div className="input-invoice-usage-drawer-body input-invoice-usage-payment-rules-body">
        {loading ? (
          <div className="input-invoice-usage-drawer-loading">
            <span aria-label="正在加载支付状态规则" className="input-invoice-usage-drawer-spinner" role="progressbar" />
            <span>正在读取规则</span>
          </div>
        ) : null}
        {error ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">
            {error}
          </div>
        ) : null}
        {feedback ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--success" role="status">
            {feedback}
          </div>
        ) : null}
        {payload ? (
          <>
            <div className="input-invoice-usage-rules-meta" aria-label="支付状态规则状态">
              {payload.readOnly === false && canSave ? <span className="input-invoice-usage-rules-tag input-invoice-usage-rules-tag--success">可编辑</span> : null}
              {payload.readOnly !== false ? <span className="input-invoice-usage-rules-tag">只读</span> : null}
              {payload.readOnly === false && !canSave ? (
                <span className="input-invoice-usage-rules-tag input-invoice-usage-rules-tag--warning">无保存权限</span>
              ) : null}
            </div>
            <section className="input-invoice-usage-payment-rules-panel">
              <div className="input-invoice-usage-payment-rules-panel__header">
                <h3>支付状态规则</h3>
                <span className="input-invoice-usage-payment-rules-panel__meta">
                  {draftRules.length} 条规则{dirty ? " · 未保存" : ""}
                </span>
              </div>
              {canSave ? <Button size="sm" variant="secondary" onPress={() => setDraftRules((current) => [...current, {
                id: `rule_${crypto.randomUUID()}`, statusCode: "paid", label: current.find((rule) => rule.statusCode === "paid")?.label ?? "已付款", description: "",
                priority: Math.max(0, ...current.map((rule) => rule.priority)) + 1, enabled: true,
                conditions: { hasOa: true, hasBank: true, fullyMatched: true },
              }])}>新增规则</Button> : null}
              <div aria-label="支付状态规则" className="input-invoice-usage-payment-rules-list" role="list">
                {draftRules.map((rule, index) => (
                  <article className="input-invoice-usage-payment-rule-row" key={rule.id || rule.code || rule.label} role="listitem">
                    <div className="input-invoice-usage-payment-rule-row__state">
                      {canSave ? (
                        <Checkbox
                          className="input-invoice-usage-rules-toggle"
                          isSelected={rule.enabled !== false}
                          onChange={(selected) => updateRule(index, { enabled: selected }, setDraftRules)}
                        >
                          <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>
                          <span>{rule.enabled === false ? "停用" : "启用"}</span>
                        </Checkbox>
                      ) : (
                        <span className={rule.enabled === false ? "input-invoice-usage-rules-tag" : "input-invoice-usage-rules-tag input-invoice-usage-rules-tag--success"}>
                          {rule.enabled === false ? "停用" : "启用"}
                        </span>
                      )}
                      {canSave ? (
                        <label className="input-invoice-usage-rules-field input-invoice-usage-payment-rule-priority">
                          <span>优先级</span>
                          <Input
                            min={1}
                            onChange={(event) => updateRule(index, { priority: Number(event.target.value) }, setDraftRules)}
                            type="number"
                            value={rule.priority}
                          />
                        </label>
                      ) : (
                        <span className="input-invoice-usage-rules-tag input-invoice-usage-payment-rule-priority-tag">
                          优先级 {rule.priority}
                        </span>
                      )}
                    </div>
                    <div className="input-invoice-usage-payment-rule-row__main">
                      {canSave ? (
                        <label className="input-invoice-usage-rules-field">
                          <span>支付状态</span>
                          <Input
                            onChange={(event) => setDraftRules((current) => current.map((item, itemIndex) => (item.statusCode === rule.statusCode || itemIndex === index ? { ...item, label: event.target.value } : item)))}
                            value={rule.label}
                          />
                        </label>
                      ) : (
                        <div className="input-invoice-usage-payment-rule-readonly-field">
                          <span>支付状态</span>
                          <strong>{rule.label}</strong>
                        </div>
                      )}
                      {canSave ? <Select aria-label={`${rule.label || "规则"} 输出分类`} selectedKey={rule.statusCode} onSelectionChange={(key) => {
                        if (key === "new-category") {
                          updateRule(index, { statusCode: `custom_${crypto.randomUUID().replace(/-/g, "")}`, label: "新分类" }, setDraftRules);
                          return;
                        }
                        const output = outputClasses.find((item) => item.id === key);
                        if (!output) return;
                        const existing = draftRules.find((item) => item.statusCode === key);
                        updateRule(index, { statusCode: output.id, label: existing ? existing.label : output.label }, setDraftRules);
                      }}>
                        <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                        <Select.Popover><ListBox>
                          {outputClasses.map((option) => <ListBox.Item id={option.id} key={option.id} textValue={option.label}>{option.label}</ListBox.Item>)}
                          <ListBox.Item id="new-category" textValue="新增分类">新增分类</ListBox.Item>
                        </ListBox></Select.Popover>
                      </Select> : null}
                      <span className="input-invoice-usage-rules-tag">分类按实际流水关联自动归入已付款或未付款</span>
                      {canSave ? <label className="input-invoice-usage-rules-field"><span>发票／付款金额</span>
                        <select aria-label={`${rule.label} 金额比较条件`} value={String(rule.conditions?.paymentComparison ?? "any")}
                          onChange={event => { const conditions = { ...rule.conditions }; if (event.target.value === "any") delete conditions.paymentComparison; else conditions.paymentComparison = event.target.value; updateRule(index, { conditions }, setDraftRules); }}>
                          <option value="any">不限制</option><option value="equal">发票＝付款</option><option value="less">发票＜付款</option><option value="greater">发票＞付款</option>
                        </select></label> : null}
                      <div className="input-invoice-usage-rules-chip-list input-invoice-usage-payment-rule-chips" aria-label={`${rule.label || "规则"}命中条件`}>
                        {conditionChips(rule).map((chip) => (
                          <span className="input-invoice-usage-rules-tag" key={`${rule.id || rule.label}:${chip}`}>
                            {chip}
                          </span>
                        ))}
                      </div>
                      {canSave ? (
                        <RuleConditionEditor
                          onChange={(key, value) => updateRuleCondition(index, key, value, setDraftRules)}
                          rule={rule}
                          applicantOptions={payload.applicantOptions}
                          onApplicantChange={(names) => {
                            const conditions = { ...rule.conditions };
                            if (!names.length) delete conditions.applicantNames;
                            else conditions.applicantNames = names;
                            updateRule(index, { conditions }, setDraftRules);
                          }}
                        />
                      ) : null}
                    </div>
                    {canSave ? <Button aria-label={`删除规则 ${rule.label}`} size="sm" variant="danger-soft" onPress={() => setDraftRules((current) => current.filter((_, itemIndex) => itemIndex !== index))}>删除</Button> : null}
                  </article>
                ))}
                {draftRules.length === 0 ? (
                  <p className="input-invoice-usage-rules-empty">暂无规则。</p>
                ) : null}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </AppDrawer>
    <AppDialog open={confirmClose} title="放弃未保存的规则？" onClose={() => setConfirmClose(false)} actions={<><Button variant="secondary" onPress={() => setConfirmClose(false)}>继续编辑</Button><Button variant="danger" onPress={() => { setConfirmClose(false); onClose(); }}>放弃修改</Button></>} />
    </>
  );
}

function cloneRules(rules: PaymentStatusRule[]) {
  return rules.map((rule) => ({
    ...rule,
    conditions: rule.conditions ? { ...rule.conditions } : rule.conditions,
  }));
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

function updateRuleCondition(
  index: number,
  key: RuleConditionKey,
  value: "any" | "true" | "false",
  setDraftRules: Dispatch<SetStateAction<PaymentStatusRule[]>>,
) {
  setDraftRules((current) => current.map((item, itemIndex) => {
    if (itemIndex !== index) {
      return item;
    }
    const conditions = { ...(item.conditions ?? {}) };
    if (value === "any") {
      delete conditions[key];
    } else {
      conditions[key] = value === "true";
    }
    return { ...item, conditions };
  }));
}

function createIdempotencyKey(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}:${crypto.randomUUID()}`;
  }
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

function RuleConditionEditor({
  rule,
  onChange,
  applicantOptions,
  onApplicantChange,
}: {
  applicantOptions: PaymentRuleApplicantOption[];
  onApplicantChange: (names: string[]) => void;
  rule: PaymentStatusRule;
  onChange: (key: RuleConditionKey, value: "any" | "true" | "false") => void;
}) {
  const conditions = rule.conditions ?? {};
  const applicantNames = (conditions.applicantNames ?? []) as string[];
  return (
    <div className="input-invoice-usage-payment-rule-condition-editor" aria-label={`${rule.label || "规则"}条件编辑`}>
      <div className="input-invoice-usage-payment-rule-condition">
        <span>OA 申请人</span>
        <PaymentRuleApplicantSelect label={`${rule.label || "规则"} OA 申请人条件`} options={applicantOptions} names={applicantNames} onChange={onApplicantChange} />
      </div>
      {CONDITION_FIELDS.map((field) => (
        <div className="input-invoice-usage-payment-rule-condition" key={field.key}>
          <span>{field.label}</span>
          <Select
            aria-label={`${rule.label || "规则"} ${field.label}条件`}
            onSelectionChange={(key) => onChange(field.key, String(key) as "any" | "true" | "false")}
            selectedKey={conditionSelectValue(conditions, field.key)}
          >
            <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
            <Select.Popover>
              <ListBox>
                <ListBox.Item id="any" textValue="不限制">不限制</ListBox.Item>
                <ListBox.Item id="true" textValue={field.trueLabel}>{field.trueLabel}</ListBox.Item>
                <ListBox.Item id="false" textValue={field.falseLabel}>{field.falseLabel}</ListBox.Item>
              </ListBox>
            </Select.Popover>
          </Select>
        </div>
      ))}
    </div>
  );
}

function conditionSelectValue(conditions: Record<string, unknown>, key: RuleConditionKey) {
  if (!(key in conditions)) {
    return "any";
  }
  return conditions[key] === true ? "true" : "false";
}

function conditionChips(rule: PaymentStatusRule) {
  const conditions = rule.conditions ?? {};
  const chips: string[] = [];
  const addBooleanChip = (key: string, label: string) => {
    if (conditions[key] === true) {
      chips.push(label);
    } else if (conditions[key] === false) {
      chips.push(`无${label.replace(/^有/, "")}`);
    }
  };
  const applicantNames = (conditions.applicantNames ?? []) as string[];
  if (applicantNames.length) {
    chips.push(`申请人（任一）=${applicantNames.join("、")}`);
  }
  addBooleanChip("hasOa", "有 OA");
  addBooleanChip("hasBank", "有流水");
  if (conditions.fullyMatched === true) {
    chips.push("完全匹配");
  }
  if (conditions.invoiceOaAmountMatched === true) {
    chips.push("发票/OA 金额匹配");
  }
  return chips.length > 0 ? chips : ["未设置条件"];
}

function isVersionConflict(reason: unknown) {
  if (!reason || typeof reason !== "object") {
    return false;
  }
  const status = (reason as { status?: unknown }).status;
  const code = String((reason as { code?: unknown }).code ?? "");
  return status === 409 || code.includes("version_conflict") || code.includes("conflict");
}
