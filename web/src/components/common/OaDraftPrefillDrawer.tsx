import { Button } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchOaDraftPrefill,
  saveOaDraftPrefill,
  type OaDraftPrefillConfiguration,
  type OaDraftPrefillFamily,
  type OaDraftPrefillPayload,
} from "../../features/oaDraftPrefill";
import AppDrawer from "./AppDrawer";

type OaDraftPrefillDrawerProps = {
  family: OaDraftPrefillFamily;
  open: boolean;
  onClose: () => void;
};

export default function OaDraftPrefillDrawer({ family, open, onClose }: OaDraftPrefillDrawerProps) {
  const [payload, setPayload] = useState<OaDraftPrefillPayload | null>(null);
  const [draft, setDraft] = useState<OaDraftPrefillConfiguration | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setDraft(null);
      setError("");
      setFeedback("");
      return undefined;
    }
    let active = true;
    setLoading(true);
    fetchOaDraftPrefill(family)
      .then((result) => {
        if (!active) return;
        setPayload(result);
        setDraft({ ...result.configuration });
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "OA 草稿预填配置加载失败。");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [family, open]);

  const dirty = useMemo(
    () => Boolean(payload && draft && JSON.stringify(payload.configuration) !== JSON.stringify(draft)),
    [draft, payload],
  );
  const update = <K extends keyof OaDraftPrefillConfiguration>(key: K, value: OaDraftPrefillConfiguration[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current);
    setFeedback("");
  };
  const handleSave = async () => {
    if (!payload || !draft || !payload.can_save || !dirty) return;
    setSaving(true);
    setError("");
    setFeedback("");
    try {
      const saved = await saveOaDraftPrefill(family, payload.version, draft);
      setPayload(saved);
      setDraft({ ...saved.configuration });
      setFeedback("已保存。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "OA 草稿预填配置保存失败。");
    } finally {
      setSaving(false);
    }
  };

  const footer = payload?.can_save ? (
    <div className="oa-prefill-drawer__footer">
      <Button
        isDisabled={!dirty || saving}
        onPress={() => setDraft(payload ? { ...payload.configuration } : null)}
        size="sm"
        variant="secondary"
      >
        还原
      </Button>
      <Button isDisabled={!dirty || saving} isPending={saving} onPress={handleSave} size="sm" variant="primary">
        保存
      </Button>
    </div>
  ) : null;

  return (
    <AppDrawer
      ariaBusy={loading || saving}
      className="oa-prefill-drawer"
      footer={footer}
      onClose={onClose}
      open={open}
      title="OA 草稿预填管理"
      width="min(680px, 100vw)"
    >
      <div className="oa-prefill-drawer__body">
        {loading ? <div className="oa-prefill-drawer__state" role="status">正在加载</div> : null}
        {error ? <div className="oa-prefill-drawer__alert" role="alert">{error}</div> : null}
        {feedback ? <div className="oa-prefill-drawer__feedback" role="status">{feedback}</div> : null}
        {payload && draft ? (
          <fieldset className="oa-prefill-form" disabled={!payload.can_save}>
            <ReadonlyField label="申请人" value={family === "etc" ? payload.dynamic_fields.applicant : "目标 OA 申请人"} />
            <ReadonlyField label="申请日期" value={payload.dynamic_fields.application_date} />
            <SelectField
              label="申请类型"
              value={draft.application_type}
              options={payload.options.application_types}
              onChange={(value) => update("application_type", value)}
            />
            <SelectField
              label="支付方式"
              value={draft.payment_method}
              options={payload.options.payment_methods}
              onChange={(value) => update("payment_method", value)}
            />
            <SelectField
              label="发票种类"
              value={draft.invoice_kind}
              options={payload.options.invoice_kinds}
              onChange={(value) => update("invoice_kind", value)}
            />
            <SelectField
              label="项目名称"
              value={draft.project_id}
              options={payload.options.projects}
              onChange={(value) => {
                const project = payload.options.projects.find((option) => option.value === value);
                setDraft((current) => current ? {
                  ...current,
                  project_id: value,
                  project_name: project?.label ?? current.project_name,
                } : current);
              }}
            />
            <ReadonlyField label="金额" value="按当前批次金额自动填充" />
            {family === "etc" ? (
              <TextField label="收款方" value={draft.payee} onChange={(value) => update("payee", value)} required />
            ) : (
              <ReadonlyField label="收款方" value="按所选发票销方自动填充" />
            )}
            <TextField label="开户行" value={draft.bank} onChange={(value) => update("bank", value)} />
            <TextField label="开户账号" value={draft.bank_account} onChange={(value) => update("bank_account", value)} />
            <label className="oa-prefill-field oa-prefill-field--wide">
              <span>申请事由</span>
              <textarea
                maxLength={500}
                onChange={(event) => update("reason_template", event.target.value)}
                rows={3}
                value={draft.reason_template}
              />
            </label>
          </fieldset>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function ReadonlyField({ label, value }: { label: string; value: string }) {
  return (
    <label className="oa-prefill-field">
      <span>{label}</span>
      <input disabled value={value || "生成时自动填充"} readOnly />
    </label>
  );
}

function TextField({
  label,
  value,
  required = false,
  onChange,
}: {
  label: string;
  value: string;
  required?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="oa-prefill-field">
      <span>{label}</span>
      <input maxLength={128} onChange={(event) => onChange(event.target.value)} required={required} value={value} />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="oa-prefill-field">
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}
