import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import AppDrawer from "../common/AppDrawer";
import type {
  InputInvoiceUsagePaymentStatusRulesResponse,
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
  pendingDirections: Array<{ code?: string; label: string }>;
};

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
        reason: String(rule.reason ?? "").trim() || undefined,
        priority: Number(rule.priority),
        enabled: rule.enabled !== false,
      })),
      pendingDirections: draftPendingDirections.map((item) => ({
        ...item,
        label: item.label.trim(),
      })),
    })
      .then(async (nextPayload) => {
        setPayload(nextPayload);
        setDraftRules(cloneRules(nextPayload.rules));
        setDraftPendingDirections(nextPayload.pendingDirections.map((item) => ({ ...item })));
        setFeedback("规则已保存，正在刷新进项发票使用情况。");
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

  const subtitle = canSave
    ? "编辑后保存会校验冲突并触发刷新"
    : "按后端权限展示规则和待处理方向";

  const footer = payload && canSave ? (
    <div className="input-invoice-usage-rules-actions input-invoice-usage-payment-rules-footer">
      <button
        className="input-invoice-usage-button"
        disabled={saving || loading || !dirty}
        onClick={() => {
          setDraftRules(cloneRules(payload.rules));
          setDraftPendingDirections(payload.pendingDirections.map((item) => ({ ...item })));
          setError(null);
          setFeedback(null);
        }}
        type="button"
      >
        还原
      </button>
      <button
        className="input-invoice-usage-button input-invoice-usage-button--primary"
        disabled={saving || loading || !dirty}
        onClick={handleSave}
        type="button"
      >
        {saving ? "保存中..." : "保存并刷新"}
      </button>
    </div>
  ) : null;

  return (
    <AppDrawer
      className="input-invoice-usage-rules-drawer"
      closeLabel="关闭支付状态规则抽屉"
      footer={footer}
      onClose={onClose}
      open={open}
      subtitle={subtitle}
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
              <span className="input-invoice-usage-rules-tag input-invoice-usage-rules-tag--info">保存后刷新进项发票使用情况与发票生命周期</span>
            </div>
            <section className="input-invoice-usage-rules-section">
              <h3>影响预览</h3>
              <p className="input-invoice-usage-rules-empty">
                当前暂未提供命中统计，保存后以刷新后的列表状态为准。
              </p>
            </section>
            <section className="input-invoice-usage-payment-rules-panel">
              <div className="input-invoice-usage-payment-rules-panel__header">
                <h3>支付状态规则</h3>
              </div>
              <div aria-label="Sheet4 支付状态规则" className="input-invoice-usage-payment-rules-list" role="list">
                {draftRules.map((rule, index) => (
                  <article className="input-invoice-usage-payment-rule-row" key={rule.id || rule.code || rule.label} role="listitem">
                    <div className="input-invoice-usage-payment-rule-row__state">
                      {canSave ? (
                        <label className="input-invoice-usage-rules-toggle">
                          <input
                            checked={rule.enabled !== false}
                            onChange={(event) => updateRule(index, { enabled: event.target.checked }, setDraftRules)}
                            type="checkbox"
                          />
                          <span>{rule.enabled === false ? "停用" : "启用"}</span>
                        </label>
                      ) : (
                        <span className={rule.enabled === false ? "input-invoice-usage-rules-tag" : "input-invoice-usage-rules-tag input-invoice-usage-rules-tag--success"}>
                          {rule.enabled === false ? "停用" : "启用"}
                        </span>
                      )}
                      {canSave ? (
                        <label className="input-invoice-usage-rules-field input-invoice-usage-payment-rule-priority">
                          <span>优先级</span>
                          <input
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
                          <input
                            onChange={(event) => updateRule(index, { label: event.target.value }, setDraftRules)}
                            value={rule.label}
                          />
                        </label>
                      ) : (
                        <div className="input-invoice-usage-payment-rule-readonly-field">
                          <span>支付状态</span>
                          <strong>{rule.label}</strong>
                        </div>
                      )}
                      <div className="input-invoice-usage-rules-chip-list input-invoice-usage-payment-rule-chips" aria-label={`${rule.label || "规则"}命中条件`}>
                        {conditionChips(rule).map((chip) => (
                          <span className="input-invoice-usage-rules-tag" key={`${rule.id || rule.label}:${chip}`}>
                            {chip}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="input-invoice-usage-payment-rule-row__reason">
                      {canSave ? (
                        <label className="input-invoice-usage-rules-field">
                          <span>原因文案</span>
                          <textarea
                            onChange={(event) => updateRule(index, { reason: event.target.value, description: event.target.value }, setDraftRules)}
                            rows={2}
                            value={rule.reason ?? rule.description}
                          />
                        </label>
                      ) : (
                        <div className="input-invoice-usage-payment-rule-readonly-field">
                          <span>原因文案</span>
                          <strong>{rule.reason || rule.description}</strong>
                        </div>
                      )}
                    </div>
                  </article>
                ))}
                {draftRules.length === 0 ? (
                  <p className="input-invoice-usage-rules-empty">暂无规则。</p>
                ) : null}
              </div>
            </section>
            <section className="input-invoice-usage-rules-section">
              <h3>待处理发票处理方向</h3>
              <p className="input-invoice-usage-rules-empty">
                当前仅作为待处理方向标签，不影响自动分流。
              </p>
              <div className="input-invoice-usage-rules-directions">
                {draftPendingDirections.length === 0 ? (
                  <span className="input-invoice-usage-rules-empty">暂无待处理方向。</span>
                ) : null}
                {draftPendingDirections.map((option, index) => (
                  canSave ? (
                    <label className="input-invoice-usage-rules-field input-invoice-usage-rules-field--direction" key={option.code || index}>
                      <span>{option.code || `方向 ${index + 1}`}</span>
                      <input
                        onChange={(event) => updatePendingDirection(index, event.target.value, setDraftPendingDirections)}
                        value={option.label}
                      />
                    </label>
                  ) : (
                    <span className="input-invoice-usage-rules-tag" key={option.code || option.label}>
                      {option.label}
                    </span>
                  )
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </AppDrawer>
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
  const applicantName = String(conditions.applicantName ?? "").trim();
  if (applicantName) {
    chips.push(`申请人=${applicantName}`);
  }
  addBooleanChip("hasOa", "有 OA");
  addBooleanChip("hasBank", "有流水");
  if (conditions.fullyMatched === true) {
    chips.push("完全匹配");
  }
  if (conditions.invoiceOaAmountMatched === true) {
    chips.push("发票/OA 金额匹配");
  }
  if (conditions.fallback === true) {
    chips.push("兜底规则");
  }
  return chips.length > 0 ? chips : ["条件由后端规则定义"];
}

function isVersionConflict(reason: unknown) {
  if (!reason || typeof reason !== "object") {
    return false;
  }
  const status = (reason as { status?: unknown }).status;
  const code = String((reason as { code?: unknown }).code ?? "");
  return status === 409 || code.includes("version_conflict") || code.includes("conflict");
}
