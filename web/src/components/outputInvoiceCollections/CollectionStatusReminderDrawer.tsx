import { useEffect, useState } from "react";

import type {
  OutputInvoiceCollectionMutationResponse,
  OutputInvoiceCollectionReminderUpdateRequest,
  OutputInvoiceCollectionRow,
  OutputInvoiceCollectionStatusUpdateRequest,
} from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

type CollectionStatusReminderDrawerProps = {
  open: boolean;
  row: OutputInvoiceCollectionRow | null;
  statusOptions: Array<{ code: string; label: string }>;
  onSaveStatus: (rowId: string, payload: OutputInvoiceCollectionStatusUpdateRequest) => Promise<OutputInvoiceCollectionMutationResponse>;
  onSaveReminder: (rowId: string, payload: OutputInvoiceCollectionReminderUpdateRequest) => Promise<OutputInvoiceCollectionMutationResponse>;
  onClearStatus: (rowId: string, expectedVersion: number) => Promise<void>;
  onCancelReminder: (rowId: string, reminderId: string) => Promise<void>;
  onChanged?: (result?: OutputInvoiceCollectionMutationResponse | null) => Promise<void> | void;
  onClose: () => void;
};

export default function CollectionStatusReminderDrawer({
  open,
  row,
  statusOptions,
  onSaveStatus,
  onSaveReminder,
  onClearStatus,
  onCancelReminder,
  onChanged,
  onClose,
}: CollectionStatusReminderDrawerProps) {
  const [statusCode, setStatusCode] = useState("");
  const [expectedCollectionDate, setExpectedCollectionDate] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [remindAt, setRemindAt] = useState("");
  const [reminderNote, setReminderNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedStatusFingerprint, setSavedStatusFingerprint] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !row) {
      return;
    }
    setStatusCode(row.collectionStatus.manualOverride?.statusCode || row.collectionStatus.code || "pending_collection");
    setExpectedCollectionDate(row.collectionStatus.expectedCollectionDate || "");
    setStatusNote(row.collectionStatus.manualOverride?.note || "");
    setRemindAt(toDatetimeLocal(row.collectionStatus.reminder?.remindAt || ""));
    setReminderNote(row.collectionStatus.reminder?.note || "");
    setError(null);
    setSavedStatusFingerprint(null);
  }, [open, row]);

  const handleSubmit = async () => {
    if (!row) {
      return;
    }
    setSubmitting(true);
    setError(null);
    const statusPayload = {
      statusCode,
      expectedCollectionDate: expectedCollectionDate || undefined,
      note: statusNote,
      expectedVersion: row.collectionStatus.manualOverride?.version ?? 0,
    };
    const statusFingerprint = JSON.stringify(statusPayload);
    try {
      let mutationResult: OutputInvoiceCollectionMutationResponse | null = null;
      if (savedStatusFingerprint !== statusFingerprint) {
        mutationResult = await onSaveStatus(row.id, statusPayload);
        setSavedStatusFingerprint(statusFingerprint);
      }
      if (remindAt) {
        mutationResult = await onSaveReminder(row.id, {
          remindAt: new Date(remindAt).toISOString(),
          channel: "oa",
          note: reminderNote,
        });
      }
      await onChanged?.(mutationResult);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleClearStatus = async () => {
    if (!row) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onClearStatus(row.id, row.collectionStatus.manualOverride?.version ?? 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销手动状态失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelReminder = async () => {
    if (!row?.collectionStatus.reminder?.id) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCancelReminder(row.id, row.collectionStatus.reminder.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "取消提醒失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭收款状态抽屉"
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
            disabled={submitting || !statusCode}
            onClick={handleSubmit}
            type="button"
          >
            保存
          </button>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle={row?.invoice.displayNo || row?.invoice.invoiceNo || ""}
      title="收款状态和提醒"
      width={520}
    >
      <div className="output-invoice-collection-drawer__body">
        {error ? <StatePanel compact tone="error">{error}</StatePanel> : null}
        <label className="output-invoice-collection-drawer__field">
          <span>手动状态</span>
          <select value={statusCode} onChange={(event) => setStatusCode(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option.code} value={option.code}>{option.label}</option>
            ))}
          </select>
        </label>
        {row?.collectionStatus.manualOverride ? (
          <button
            className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--warning"
            disabled={submitting}
            onClick={handleClearStatus}
            type="button"
          >
            撤销手动状态
          </button>
        ) : null}
        <label className="output-invoice-collection-drawer__field">
          <span>预计收款日期</span>
          <input
            type="date"
            value={expectedCollectionDate}
            onChange={(event) => setExpectedCollectionDate(event.target.value)}
          />
        </label>
        <label className="output-invoice-collection-drawer__field">
          <span>状态备注</span>
          <textarea rows={3} value={statusNote} onChange={(event) => setStatusNote(event.target.value)} />
        </label>
        <div className="output-invoice-collection-drawer__section-divider" />
        <label className="output-invoice-collection-drawer__field">
          <span>提醒时间</span>
          <input
            type="datetime-local"
            value={remindAt}
            onChange={(event) => setRemindAt(event.target.value)}
          />
        </label>
        <label className="output-invoice-collection-drawer__field">
          <span>提醒备注</span>
          <textarea rows={2} value={reminderNote} onChange={(event) => setReminderNote(event.target.value)} />
        </label>
        {row?.collectionStatus.reminder?.id ? (
          <button
            className="output-invoice-collection-drawer__button output-invoice-collection-drawer__button--warning"
            disabled={submitting}
            onClick={handleCancelReminder}
            type="button"
          >
            取消提醒
          </button>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function toDatetimeLocal(value: string) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
