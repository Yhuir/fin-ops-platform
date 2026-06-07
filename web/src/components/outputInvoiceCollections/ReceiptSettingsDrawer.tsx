import { useEffect, useState } from "react";

import type { OutputInvoiceReceiptSettingsResponse } from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

type ReceiptSettingsDrawerProps = {
  open: boolean;
  loadSettings: () => Promise<OutputInvoiceReceiptSettingsResponse>;
  onSave: (payload: { prefix: string; resetPeriod: string }) => Promise<void>;
  onClose: () => void;
};

export default function ReceiptSettingsDrawer({
  open,
  loadSettings,
  onSave,
  onClose,
}: ReceiptSettingsDrawerProps) {
  const [prefix, setPrefix] = useState("SK");
  const [resetPeriod, setResetPeriod] = useState("monthly");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadSettings()
      .then((payload) => {
        if (!active) {
          return;
        }
        setPrefix(payload.settings.prefix || "SK");
        setResetPeriod(payload.settings.resetPeriod || "monthly");
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收据编号设置加载失败");
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
  }, [loadSettings, open]);

  const handleSave = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSave({ prefix, resetPeriod });
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "收据编号设置保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭收据编号设置"
      footer={(
        <div className="output-invoice-collection-drawer__footer-actions">
          <button
            className="output-invoice-collection-drawer__button"
            disabled={submitting}
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <button
            className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--primary"
            disabled={loading || submitting || !prefix.trim()}
            onClick={handleSave}
            type="button"
          >
            保存收据编号设置
          </button>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle="正式收据编号规则"
      title="收据编号设置"
      width={480}
    >
      <div className="output-invoice-collection-drawer__body">
        {error ? <StatePanel compact tone="error">{error}</StatePanel> : null}
        <label className="output-invoice-collection-drawer__field">
          <span>编号前缀</span>
          <input
            disabled={loading || submitting}
            onChange={(event) => setPrefix(event.target.value.toUpperCase())}
            value={prefix}
          />
        </label>
        <label className="output-invoice-collection-drawer__field">
          <span>重置周期</span>
          <select
            disabled={loading || submitting}
            onChange={(event) => setResetPeriod(event.target.value)}
            value={resetPeriod}
          >
            <option value="monthly">每月重置</option>
            <option value="yearly">每年重置</option>
            <option value="none">不按日期重置</option>
          </select>
        </label>
      </div>
    </AppDrawer>
  );
}
