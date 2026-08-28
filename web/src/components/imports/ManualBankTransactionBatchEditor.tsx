import { Alert, Button, Chip, Input, ListBox, Select, TextArea } from "@heroui/react";
import { Plus, Trash2 } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import {
  discardImportSession,
  previewManualBankTransactions,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import type {
  ManualBankTransactionEntryBatchPreview,
  ManualBankTransactionEntryValues,
} from "../../features/imports/types";
import type { BankAccountMapping } from "../../features/workbench/types";

const MAX_ENTRIES = 50;

export const EMPTY_MANUAL_BANK_TRANSACTION_VALUES: ManualBankTransactionEntryValues = {
  bankMappingId: "",
  bankName: "",
  bankShortName: "",
  last4: "",
  accountNo: "",
  accountName: "",
  direction: "outflow",
  amount: "",
  balance: "",
  tradeTime: "",
  currency: "CNY",
  counterpartyName: "",
  counterpartyAccountNo: "",
  counterpartyBankName: "",
  summary: "",
  remark: "",
};

type Entry = { id: number; values: ManualBankTransactionEntryValues };

type ManualBankTransactionBatchEditorProps = {
  bankAccounts: BankAccountMapping[];
  disabled?: boolean;
  onCancel: () => void;
  onPreviewSessionChange: (sessionId: string | null) => void;
  onSubmit: (preview: ManualBankTransactionEntryBatchPreview) => Promise<void>;
  previewTransactions?: (
    values: ManualBankTransactionEntryValues[],
  ) => Promise<ManualBankTransactionEntryBatchPreview>;
};

function Field({
  children,
  label,
  required = false,
}: {
  children: ReactNode;
  label: string;
  required?: boolean;
}) {
  return (
    <label className="manual-bank-entry__field">
      <span>{label}{required ? <span aria-hidden="true" className="manual-bank-entry__required"> *</span> : null}</span>
      {children}
    </label>
  );
}

function bankLabel(account: BankAccountMapping) {
  const shortName = account.shortName.trim();
  return `${shortName || account.bankName} ${account.last4}`;
}

function normalizeTradeTimeInput(value: string) {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) ? `${value}:00` : value;
}

function validateEntry(values: ManualBankTransactionEntryValues, index: number) {
  const label = `流水 ${index + 1}`;
  if (!values.bankMappingId) return `${label}：请选择银行账户。`;
  if (!/^\d+$/.test(values.accountNo.trim())) return `${label}：请填写完整的本方账号。`;
  if (!values.accountNo.trim().endsWith(values.last4)) return `${label}：本方账号尾号与所选账户不一致。`;
  if (!values.amount.trim() || Number(values.amount) <= 0) return `${label}：金额必须大于 0。`;
  if (!values.balance.trim() || !Number.isFinite(Number(values.balance))) return `${label}：请填写有效余额。`;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(values.tradeTime)) return `${label}：交易时间必须精确到秒。`;
  if (!values.counterpartyName.trim()) return `${label}：请填写对方户名。`;
  if (!/^[A-Za-z]{3}$/.test(values.currency.trim())) return `${label}：币种必须为三位英文代码。`;
  return null;
}

function previewTone(decision: string | null | undefined) {
  if (decision === "created") return { label: "可录入", color: "success" as const };
  if (decision === "duplicate_skipped") return { label: "已存在", color: "default" as const };
  if (decision === "suspected_duplicate") return { label: "疑似重复", color: "warning" as const };
  return { label: "不可录入", color: "danger" as const };
}

export default function ManualBankTransactionBatchEditor({
  bankAccounts,
  disabled = false,
  onCancel,
  onPreviewSessionChange,
  onSubmit,
  previewTransactions = previewManualBankTransactions,
}: ManualBankTransactionBatchEditorProps) {
  const [entries, setEntries] = useState<Entry[]>([
    { id: 1, values: { ...EMPTY_MANUAL_BANK_TRANSACTION_VALUES } },
  ]);
  const [selectedId, setSelectedId] = useState(1);
  const [preview, setPreview] = useState<ManualBankTransactionEntryBatchPreview | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const current = entries.find((entry) => entry.id === selectedId) ?? entries[0];
  const busy = isPreviewing || isDiscarding || isSubmitting;
  const bankAccountMap = useMemo(
    () => new Map(bankAccounts.map((account) => [account.id, account])),
    [bankAccounts],
  );

  function updateCurrent(patch: Partial<ManualBankTransactionEntryValues>) {
    setEntries((items) => items.map((entry) => (
      entry.id === selectedId ? { ...entry, values: { ...entry.values, ...patch } } : entry
    )));
    setErrorMessage(null);
  }

  function selectBank(mappingId: string) {
    const account = bankAccountMap.get(mappingId);
    if (!account) return;
    updateCurrent({
      bankMappingId: account.id,
      bankName: account.bankName,
      bankShortName: account.shortName,
      last4: account.last4,
      accountNo: "",
    });
  }

  function addEntry() {
    if (entries.length >= MAX_ENTRIES) return;
    const nextId = Math.max(...entries.map((entry) => entry.id)) + 1;
    setEntries((items) => [
      ...items,
      { id: nextId, values: { ...EMPTY_MANUAL_BANK_TRANSACTION_VALUES } },
    ]);
    setSelectedId(nextId);
    setErrorMessage(null);
  }

  function removeEntry(id: number) {
    if (entries.length === 1) return;
    const nextEntries = entries.filter((entry) => entry.id !== id);
    setEntries(nextEntries);
    if (id === selectedId) setSelectedId(nextEntries[0].id);
    setErrorMessage(null);
  }

  async function createPreview() {
    const error = entries.map((entry, index) => validateEntry(entry.values, index)).find(Boolean);
    if (error) {
      setErrorMessage(error);
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    try {
      const result = await previewTransactions(entries.map((entry) => entry.values));
      setPreview(result);
      onPreviewSessionChange(result.importSession.session.id);
    } catch (caught) {
      setErrorMessage(resolveImportApiErrorMessage(caught, "流水预览失败，请核对后重试。"));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function returnToEdit() {
    if (!preview || busy) return;
    setIsDiscarding(true);
    setErrorMessage(null);
    try {
      await discardImportSession(preview.importSession.session.id);
      setPreview(null);
      onPreviewSessionChange(null);
    } catch (caught) {
      setErrorMessage(resolveImportApiErrorMessage(caught, "放弃预览失败，当前预览已保留。"));
    } finally {
      setIsDiscarding(false);
    }
  }

  async function submit() {
    if (!preview || preview.fileIds.length === 0 || busy) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onSubmit(preview);
    } catch (caught) {
      setErrorMessage(resolveImportApiErrorMessage(caught, "流水录入失败，请核对后重试。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="manual-bank-entry__body">
      {bankAccounts.length === 0 ? (
        <Alert className="manual-bank-entry__notice manual-bank-entry__notice--danger">
          当前没有可用银行账户，请先到 App 设置中配置银行账户。
        </Alert>
      ) : null}
      {errorMessage ? (
        <Alert className="manual-bank-entry__notice manual-bank-entry__notice--danger">{errorMessage}</Alert>
      ) : null}

      {preview ? (
        <>
          <div className="manual-bank-entry__preview-summary">
            <div><span>本次填写</span><strong>{entries.length} 笔</strong></div>
            <div><span>可录入</span><strong>{preview.fileIds.length} 笔</strong></div>
            <div><span>不可录入</span><strong>{entries.length - preview.fileIds.length} 笔</strong></div>
          </div>
          <div className="manual-bank-entry__preview-list">
            {preview.importSession.files.map((file, index) => {
              const values = preview.values[index];
              const decision = file.rowResults[0]?.decision;
              const tone = previewTone(decision);
              return (
                <section className="manual-bank-entry__preview-item" key={file.id}>
                  <header>
                    <strong>流水 {index + 1}</strong>
                    <Chip color={tone.color} size="sm" variant="soft"><Chip.Label>{tone.label}</Chip.Label></Chip>
                  </header>
                  <dl>
                    <div><dt>银行账户</dt><dd>{values ? `${values.bankShortName || values.bankName} ${values.last4}` : "—"}</dd></div>
                    <div><dt>交易时间</dt><dd>{values?.tradeTime.replace("T", " ") || "—"}</dd></div>
                    <div><dt>收支金额</dt><dd>{values ? `${values.direction === "outflow" ? "支出" : "收入"} ${values.amount}` : "—"}</dd></div>
                    <div><dt>对方户名</dt><dd>{values?.counterpartyName || "—"}</dd></div>
                    <div><dt>结果</dt><dd>{file.rowResults[0]?.decisionReason || file.message || "—"}</dd></div>
                  </dl>
                </section>
              );
            })}
          </div>
          <div className="manual-bank-entry__footer">
            <Button isDisabled={busy} size="sm" variant="secondary" onPress={() => { void returnToEdit(); }}>
              返回修改
            </Button>
            <Button
              isDisabled={disabled || busy || preview.fileIds.length === 0}
              isPending={isSubmitting}
              size="sm"
              variant="primary"
              onPress={() => { void submit(); }}
            >
              {isSubmitting ? "录入中..." : `录入 ${preview.fileIds.length} 笔流水`}
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="manual-bank-entry__tabs" role="tablist" aria-label="待录入流水">
            {entries.map((entry, index) => (
              <button
                aria-selected={entry.id === selectedId}
                className="manual-bank-entry__tab"
                data-active={entry.id === selectedId || undefined}
                key={entry.id}
                role="tab"
                type="button"
                onClick={() => setSelectedId(entry.id)}
              >
                流水 {index + 1}
              </button>
            ))}
            <button
              aria-label="添加流水"
              className="manual-bank-entry__tab manual-bank-entry__tab--icon"
              disabled={disabled || busy || entries.length >= MAX_ENTRIES}
              type="button"
              onClick={addEntry}
            >
              <Plus aria-hidden="true" size={15} />
            </button>
            {entries.length > 1 ? (
              <button
                aria-label="删除当前流水"
                className="manual-bank-entry__tab manual-bank-entry__tab--icon manual-bank-entry__tab--danger"
                disabled={disabled || busy}
                type="button"
                onClick={() => removeEntry(selectedId)}
              >
                <Trash2 aria-hidden="true" size={15} />
              </button>
            ) : null}
          </div>

          <div className="manual-bank-entry__section-heading">
            <div><strong>流水 {entries.findIndex((entry) => entry.id === selectedId) + 1}</strong><span>银行账户信息</span></div>
            <span>{entries.length} / {MAX_ENTRIES}</span>
          </div>
          <div className="manual-bank-entry__form">
            <Field label="银行账户" required>
              <Select
                aria-label="银行账户"
                isDisabled={disabled || busy}
                selectedKey={current.values.bankMappingId}
                onSelectionChange={(key) => selectBank(String(key))}
              >
                <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox>{bankAccounts.map((account) => (
                  <ListBox.Item id={account.id} key={account.id} textValue={bankLabel(account)}>
                    {bankLabel(account)}
                  </ListBox.Item>
                ))}</ListBox></Select.Popover>
              </Select>
            </Field>
            <Field label="本方完整账号" required>
              <Input
                aria-label="本方完整账号"
                disabled={disabled || busy}
                inputMode="numeric"
                placeholder={current.values.last4 ? `尾号 ${current.values.last4}` : "先选择银行账户"}
                value={current.values.accountNo}
                onChange={(event) => updateCurrent({ accountNo: event.currentTarget.value.replace(/[\s-]/g, "") })}
              />
            </Field>
            <Field label="本方户名">
              <Input aria-label="本方户名" disabled={disabled || busy} value={current.values.accountName} onChange={(event) => updateCurrent({ accountName: event.currentTarget.value })} />
            </Field>
          </div>

          <div className="manual-bank-entry__section-heading"><div><strong>交易信息</strong><span>金额、时间与对方信息</span></div></div>
          <div className="manual-bank-entry__form">
            <Field label="收支方向" required>
              <Select aria-label="收支方向" isDisabled={disabled || busy} selectedKey={current.values.direction} onSelectionChange={(key) => updateCurrent({ direction: String(key) as "inflow" | "outflow" })}>
                <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox><ListBox.Item id="outflow">支出</ListBox.Item><ListBox.Item id="inflow">收入</ListBox.Item></ListBox></Select.Popover>
              </Select>
            </Field>
            <Field label="金额" required>
              <Input aria-label="金额" disabled={disabled || busy} inputMode="decimal" value={current.values.amount} onChange={(event) => updateCurrent({ amount: event.currentTarget.value })} />
            </Field>
            <Field label="余额" required>
              <Input aria-label="余额" disabled={disabled || busy} inputMode="decimal" value={current.values.balance} onChange={(event) => updateCurrent({ balance: event.currentTarget.value })} />
            </Field>
            <Field label="交易时间" required>
              <Input aria-label="交易时间" disabled={disabled || busy} step="1" type="datetime-local" value={current.values.tradeTime} onChange={(event) => updateCurrent({ tradeTime: normalizeTradeTimeInput(event.currentTarget.value) })} />
            </Field>
            <Field label="币种" required>
              <Input aria-label="币种" disabled={disabled || busy} maxLength={3} value={current.values.currency} onChange={(event) => updateCurrent({ currency: event.currentTarget.value.toUpperCase() })} />
            </Field>
            <Field label="对方户名" required>
              <Input aria-label="对方户名" disabled={disabled || busy} value={current.values.counterpartyName} onChange={(event) => updateCurrent({ counterpartyName: event.currentTarget.value })} />
            </Field>
            <Field label="对方账号">
              <Input aria-label="对方账号" disabled={disabled || busy} inputMode="numeric" value={current.values.counterpartyAccountNo} onChange={(event) => updateCurrent({ counterpartyAccountNo: event.currentTarget.value.replace(/[\s-]/g, "") })} />
            </Field>
            <Field label="对方银行">
              <Input aria-label="对方银行" disabled={disabled || busy} value={current.values.counterpartyBankName} onChange={(event) => updateCurrent({ counterpartyBankName: event.currentTarget.value })} />
            </Field>
            <Field label="摘要">
              <Input aria-label="摘要" disabled={disabled || busy} value={current.values.summary} onChange={(event) => updateCurrent({ summary: event.currentTarget.value })} />
            </Field>
            <Field label="备注">
              <TextArea aria-label="备注" disabled={disabled || busy} rows={2} value={current.values.remark} onChange={(event) => updateCurrent({ remark: event.currentTarget.value })} />
            </Field>
          </div>
          <div className="manual-bank-entry__footer">
            <Button isDisabled={busy} size="sm" variant="secondary" onPress={onCancel}>取消</Button>
            <Button isDisabled={disabled || busy || bankAccounts.length === 0} isPending={isPreviewing} size="sm" variant="primary" onPress={() => { void createPreview(); }}>
              {isPreviewing ? "预览中..." : `预览 ${entries.length} 笔流水`}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
