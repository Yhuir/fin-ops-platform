import { useEffect, useState } from "react";
import type { InputInvoiceUsagePaymentStatusRule, InputInvoiceUsagePaymentStatusRulesResponse, SaveInputInvoiceUsagePaymentStatusRulesRequest } from "./types";

export type PaymentStatusRulesPayload = Omit<InputInvoiceUsagePaymentStatusRulesResponse, "version" | "readOnly" | "permissions"> & {
  version?: number | string | null;
  readOnly?: boolean;
  permissions?: { canSave?: boolean; can_save?: boolean };
};
export type PaymentStatusRulesPorts = {
  open: boolean;
  loadRules: () => Promise<PaymentStatusRulesPayload>;
  saveRules?: (request: SaveInputInvoiceUsagePaymentStatusRulesRequest) => Promise<PaymentStatusRulesPayload>;
  onSaved?: () => Promise<void> | void;
};
const cloneRules = (rules: InputInvoiceUsagePaymentStatusRule[]) => rules.map(rule => ({ ...rule, conditions: { ...rule.conditions } }));
export function usePaymentStatusRules({ open, loadRules, saveRules, onSaved }: PaymentStatusRulesPorts) {
  const [payload, setPayload] = useState<PaymentStatusRulesPayload | null>(null);
  const [rules, setRules] = useState<InputInvoiceUsagePaymentStatusRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) { setPayload(null); setRules([]); setError(""); setRefreshError(""); setFeedback(""); return; }
    let active = true;
    setLoading(true); setError("");
    loadRules().then(next => { if (active) { setPayload(next); setRules(cloneRules(next.rules)); } })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "规则加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, loadRules, revision]);
  const canSave = Boolean(payload && payload.readOnly === false && (payload.permissions?.canSave || payload.permissions?.can_save) && saveRules);
  const dirty = Boolean(payload && JSON.stringify(rules) !== JSON.stringify(cloneRules(payload.rules)));
  const conditionErrors = rules.map(rule => {
    const conditions = rule.conditions ?? {};
    if (typeof conditions.hasBank !== "boolean") return "请选择是否有流水";
    if (conditions.hasBank === false && conditions.paymentComparison != null) return "无流水不能比较付款金额，请修改流水或金额比较条件";
    if (conditions.hasOa === true && Array.isArray(conditions.applicantNames) && conditions.applicantNames.length === 0) return "请选择 OA 申请人";
    if (conditions.hasOa === false && conditions.applicantNames) return "无 OA 不能配置申请人";
    return "";
  });
  const invalid = conditionErrors.some(Boolean) || rules.some(rule => !rule.label.trim());
  async function refresh() {
    setRefreshError("");
    try { await onSaved?.(); }
    catch (reason) { setRefreshError(reason instanceof Error ? reason.message : "规则已保存，列表刷新失败"); }
  }
  async function save() {
    if (!payload || !canSave || !saveRules || loading || saving || invalid) return;
    setSaving(true); setError(""); setFeedback(""); setRefreshError("");
    try {
      const next = await saveRules({ expectedVersion: payload.version ?? null, idempotencyKey: `input-invoice-usage-payment-rules-save:${crypto.randomUUID()}`,
        rules: rules.map(({ id, statusCode, label, enabled, conditions }) => ({ id, statusCode, label: label.trim(), enabled: enabled !== false, conditions })) });
      setPayload({ ...next, applicantOptions: payload.applicantOptions }); setRules(cloneRules(next.rules)); setFeedback("规则已保存。");
      await refresh();
    } catch (reason) {
      const conflict = reason && typeof reason === "object" && "status" in reason && reason.status === 409;
      setError(conflict ? "规则已被其他人更新，请重新加载后再编辑。" : reason instanceof Error ? reason.message : "规则保存失败");
    } finally { setSaving(false); }
  }
  function update(index: number, patch: Partial<InputInvoiceUsagePaymentStatusRule>) { setRules(current => current.map((rule, i) => i === index ? { ...rule, ...patch } : rule)); }
  function condition(index: number, values: Record<string, unknown>) {
    setRules(current => current.map((rule, i) => {
      if (i !== index) return rule;
      const conditions = { ...rule.conditions };
      Object.entries(values).forEach(([key, value]) => { if (value === undefined) delete conditions[key]; else conditions[key] = value; });
      return { ...rule, conditions };
    }));
  }
  function add(hasBank: boolean, statusCode?: string) {
    setRules(current => {
      const existing = current.find(rule => rule.statusCode === statusCode);
      return [...current, { id: `rule_${crypto.randomUUID()}`, statusCode: existing?.statusCode ?? `custom_${crypto.randomUUID().replace(/-/g, "")}`,
        label: existing?.label ?? "", description: "", enabled: true, conditions: { hasBank } }];
    });
  }
  return { payload, rules, setRules, loading, saving, error, refreshError, feedback, canSave, dirty, invalid, conditionErrors, save, refresh, update, condition, add,
    reload: () => { setPayload(null); setRules([]); setFeedback(""); setRevision(value => value + 1); },
    restore: () => { if (payload) setRules(cloneRules(payload.rules)); setError(""); setFeedback(""); },
  };
}
