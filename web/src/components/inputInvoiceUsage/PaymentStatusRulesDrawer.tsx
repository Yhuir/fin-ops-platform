import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

import AppDrawer from "../common/AppDrawer";
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
  onSaved?: () => void;
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
        onSaved?.();
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
    ? "编辑后保存会带版本和幂等键提交，由后端校验并触发刷新"
    : "按后端权限展示规则和待处理下拉方向";

  return (
    <AppDrawer
      className="input-invoice-usage-rules-drawer"
      closeLabel="关闭支付状态规则抽屉"
      onClose={onClose}
      open={open}
      subtitle={subtitle}
      title="发票与支付状态规则设置"
      width="min(820px, 100vw)"
    >
      <div className="input-invoice-usage-drawer-body">
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
              {payload.version !== null && payload.version !== undefined ? (
                <span className="input-invoice-usage-rules-tag">版本 {payload.version}</span>
              ) : null}
              {payload.readOnly !== false ? <span className="input-invoice-usage-rules-tag">只读</span> : null}
              {payload.readOnly === false && !canSave ? (
                <span className="input-invoice-usage-rules-tag input-invoice-usage-rules-tag--warning">无保存权限</span>
              ) : null}
            </div>
            <div className="input-invoice-usage-rules-table-shell">
              <table aria-label="Sheet4 支付状态规则" className="input-invoice-usage-rules-table">
                <thead>
                  <tr>
                    <th scope="col">支付状态</th>
                    <th scope="col">规则</th>
                    <th scope="col">优先级</th>
                  </tr>
                </thead>
                <tbody>
                  {draftRules.map((rule, index) => (
                    <tr key={rule.id || rule.code || rule.label}>
                      <td className="input-invoice-usage-rules-table__status">
                        {canSave ? (
                          <label className="input-invoice-usage-rules-field">
                            <span>支付状态</span>
                            <input
                              onChange={(event) => updateRule(index, { label: event.target.value }, setDraftRules)}
                              value={rule.label}
                            />
                          </label>
                        ) : rule.label}
                      </td>
                      <td>
                        {canSave ? (
                          <label className="input-invoice-usage-rules-field">
                            <span>规则</span>
                            <textarea
                              onChange={(event) => updateRule(index, { description: event.target.value }, setDraftRules)}
                              rows={2}
                              value={rule.description}
                            />
                          </label>
                        ) : rule.description}
                      </td>
                      <td className="input-invoice-usage-rules-table__priority">
                        {canSave ? (
                          <label className="input-invoice-usage-rules-field">
                            <span>优先级</span>
                            <input
                              min={1}
                              onChange={(event) => updateRule(index, { priority: Number(event.target.value) }, setDraftRules)}
                              type="number"
                              value={rule.priority}
                            />
                          </label>
                        ) : rule.priority}
                      </td>
                    </tr>
                  ))}
                  {draftRules.length === 0 ? (
                    <tr>
                      <td colSpan={3}>暂无规则。</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <section className="input-invoice-usage-rules-section">
              <h3>待处理下拉方向</h3>
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
            {canSave ? (
              <div className="input-invoice-usage-rules-actions">
                <button
                  className="input-invoice-usage-button"
                  disabled={saving || loading}
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
                  {saving ? "保存中..." : "保存规则"}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </AppDrawer>
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
