import {
  Alert, Button, Input, ListBox, PopoverContent, PopoverDialog,
  PopoverRoot, PopoverTrigger, Select,
} from "@heroui/react";
import { FileSearch, Plus, Upload } from "lucide-react";
import { type DragEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";

import {
  previewManualInvoices, recognizeManualInvoice, resolveImportApiErrorMessage,
} from "../../features/imports/api";
import type {
  ManualInvoiceEntryBatchPreview, ManualInvoiceEntryValues,
} from "../../features/imports/types";

export const EMPTY_MANUAL_INVOICE_VALUES: ManualInvoiceEntryValues = {
  invoiceDirection: "input", invoiceNature: "blue", sellerName: "", sellerTaxNo: "",
  buyerName: "", buyerTaxNo: "", invoiceNumber: "", invoiceCode: "", invoiceDate: "",
  netAmount: "", taxRate: "", taxAmount: "", totalWithTax: "",
};

const FIELD_LABELS: Array<[keyof ManualInvoiceEntryValues, string]> = [
  ["sellerName", "销方名称"], ["sellerTaxNo", "销方识别号"],
  ["buyerName", "购方名称"], ["buyerTaxNo", "购方识别号"],
  ["invoiceNumber", "发票号码"], ["invoiceDate", "开票日期"],
  ["netAmount", "不含税价格"], ["taxRate", "税率"],
  ["taxAmount", "税额"], ["totalWithTax", "价税合计"],
];

const PREVIEW_FIELDS: Array<[string, keyof ManualInvoiceEntryValues]> = [
  ["票据方向", "invoiceDirection"], ["发票性质", "invoiceNature"],
  ["销方名称", "sellerName"], ["销方识别号", "sellerTaxNo"],
  ["购方名称", "buyerName"], ["购方识别号", "buyerTaxNo"],
  ["发票号码", "invoiceNumber"], ["发票代码", "invoiceCode"],
  ["开票日期", "invoiceDate"], ["不含税价格", "netAmount"],
  ["税率", "taxRate"], ["税额", "taxAmount"], ["价税合计", "totalWithTax"],
];

type Entry = { id: number; values: ManualInvoiceEntryValues; saved: boolean; fileName: string };

type ManualInvoiceBatchEditorProps = {
  disabled?: boolean;
  submitLabel: string;
  onCancel: () => void;
  onSubmit: (preview: ManualInvoiceEntryBatchPreview) => Promise<void>;
};

function Field({ label, required = true, children }: { label: string; required?: boolean; children: ReactNode }) {
  return <label className="manual-invoice-entry__field"><span>{label}{required ? <span aria-hidden="true" className="manual-invoice-entry__required"> *</span> : null}</span>{children}</label>;
}

function isDigitalInvoiceNumber(value: string) { return /^\d{20}$/.test(value.trim()); }

function formatPreviewValue(key: keyof ManualInvoiceEntryValues, value: string, nature: string) {
  if (key === "invoiceDirection") return value === "input" ? "进项发票" : "销项发票";
  if (key === "invoiceNature") return value === "red" ? "红字" : "蓝字";
  if (key === "taxRate") return `${value}%`;
  if (["netAmount", "taxAmount", "totalWithTax"].includes(key)) return `${nature === "red" ? "-" : ""}${value}`;
  return value || "—";
}

export default function ManualInvoiceBatchEditor({ disabled = false, submitLabel, onCancel, onSubmit }: ManualInvoiceBatchEditorProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [entries, setEntries] = useState<Entry[]>([{ id: 1, values: { ...EMPTY_MANUAL_INVOICE_VALUES }, saved: false, fileName: "" }]);
  const [selectedId, setSelectedId] = useState(1);
  const [page, setPage] = useState<"edit" | "preview" | "overview">("edit");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const current = entries.find((entry) => entry.id === selectedId) ?? entries[0];
  const values = current.values;
  const busy = isRecognizing || isSubmitting;
  const invoiceCodeRequired = !isDigitalInvoiceNumber(values.invoiceNumber);
  const allSaved = entries.every((entry) => entry.saved);
  const summary = useMemo(() => entries.map((entry, index) => ({ ...entry, label: `新发票${index + 1}` })), [entries]);

  function updateCurrent(patch: Partial<Entry>) {
    setEntries((items) => items.map((entry) => entry.id === selectedId ? { ...entry, ...patch } : entry));
  }
  function updateValue(key: keyof ManualInvoiceEntryValues, value: string) {
    updateCurrent({ values: { ...values, [key]: value }, saved: false }); setErrorMessage(null);
  }
  function validate() {
    for (const [key, label] of FIELD_LABELS) if (!values[key].trim()) return `请填写${label}。`;
    if (invoiceCodeRequired && !values.invoiceCode.trim()) return "传统发票必须填写发票代码。";
    return null;
  }
  function addInvoice() {
    const nextId = Math.max(...entries.map((entry) => entry.id)) + 1;
    setEntries((items) => [...items, { id: nextId, values: { ...EMPTY_MANUAL_INVOICE_VALUES }, saved: false, fileName: "" }]);
    setSelectedId(nextId); setPage("edit"); setErrorMessage(null); setStatusMessage(null);
  }
  async function recognize(file: File | undefined) {
    if (!file || busy) return;
    if (!/\.(jpe?g|png|pdf)$/i.test(file.name)) { setErrorMessage("仅支持 JPG、JPEG、PNG 或 PDF 发票文件。"); return; }
    setIsRecognizing(true); setErrorMessage(null);
    try {
      const recognized = await recognizeManualInvoice(file);
      updateCurrent({
        fileName: file.name, saved: false,
        values: Object.entries(recognized).reduce(
          (next, [key, value]) => value && String(value).trim() ? { ...next, [key]: String(value) } : next,
          values,
        ),
      });
      setStatusMessage("已预填识别结果，请核对。"); setUploadOpen(false);
    } catch (error) { setErrorMessage(resolveImportApiErrorMessage(error, "发票解析失败，请手工录入。")); }
    finally { setIsRecognizing(false); if (inputRef.current) inputRef.current.value = ""; }
  }
  async function submitBatch() {
    if (!allSaved || busy) return;
    setIsSubmitting(true); setErrorMessage(null);
    try { await onSubmit(await previewManualInvoices(entries.map((entry) => entry.values))); }
    catch (error) { setErrorMessage(resolveImportApiErrorMessage(error, "整批录入失败，请核对后重试。")); }
    finally { setIsSubmitting(false); }
  }
  const moneyInput = (key: "netAmount" | "taxAmount" | "totalWithTax", label: string) => (
    <Field label={label}><div className="manual-invoice-entry__signed-input" data-negative={values.invoiceNature === "red" || undefined}>{values.invoiceNature === "red" ? <span aria-hidden="true">−</span> : null}<Input aria-label={label} disabled={busy || disabled} inputMode="decimal" value={values[key]} onChange={(event) => updateValue(key, event.currentTarget.value.replace(/^-/, ""))} /></div></Field>
  );

  return <div className="manual-invoice-entry__body">
    <div className="manual-invoice-entry__tabs" role="tablist" aria-label="待录入发票">
      {summary.map((entry) => <button aria-selected={entry.id === selectedId} className="manual-invoice-entry__tab" data-active={entry.id === selectedId || undefined} key={entry.id} role="tab" type="button" onClick={() => { setSelectedId(entry.id); setPage(entry.saved ? "overview" : "edit"); }}>{entry.label}{entry.saved ? " ✓" : ""}</button>)}
      <button aria-label="添加发票" className="manual-invoice-entry__tab manual-invoice-entry__tab--add" disabled={busy || disabled} type="button" onClick={addInvoice}><Plus aria-hidden="true" size={15} /></button>
    </div>
    {statusMessage ? <Alert className="manual-invoice-entry__notice">{statusMessage}</Alert> : null}
    {errorMessage ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}
    {page === "overview" ? <div className="manual-invoice-entry__overview"><strong>{`新发票${entries.findIndex((entry) => entry.id === selectedId) + 1}`}</strong><span>{values.invoiceNumber || "未填写号码"}</span><span>{values.sellerName || "未填写销方"}</span><span>{values.totalWithTax ? `价税合计 ${values.totalWithTax}` : "未填写金额"}</span><Button size="sm" variant="secondary" onPress={() => setPage("edit")}>编辑</Button></div>
      : page === "preview" ? <><dl className="manual-invoice-entry__preview-list">{PREVIEW_FIELDS.map(([label, key]) => <div className="manual-invoice-entry__preview-row" key={key}><dt>{label}</dt><dd>{formatPreviewValue(key, values[key], values.invoiceNature)}</dd></div>)}</dl><div className="manual-invoice-entry__footer"><Button size="sm" variant="secondary" onPress={() => setPage("edit")}>返回编辑</Button><Button size="sm" variant="primary" onPress={() => { updateCurrent({ saved: true }); setPage("overview"); }}>保存信息</Button></div></>
        : <>
          <div className="manual-invoice-entry__toolbar"><PopoverRoot isOpen={uploadOpen} onOpenChange={(open) => !disabled && !busy && setUploadOpen(open)}><PopoverTrigger aria-label="上传发票文件" aria-disabled={disabled || busy} className="manual-invoice-entry__upload-trigger" data-disabled={disabled || busy || undefined}><Upload aria-hidden="true" size={15} />上传识别</PopoverTrigger>{uploadOpen ? <PopoverContent className="manual-invoice-entry__upload-popover" placement="bottom start"><PopoverDialog aria-label="上传并识别发票"><label className="manual-invoice-entry__dropzone" htmlFor={inputId} onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); void recognize(event.dataTransfer.files[0]); }}><FileSearch aria-hidden="true" size={22} /><span>{isRecognizing ? "解析中..." : "拖入或选择 JPG / PNG / PDF"}</span><input accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf" className="manual-invoice-entry__file-input" disabled={busy} id={inputId} onChange={(event) => { void recognize(event.currentTarget.files?.[0]); }} ref={inputRef} type="file" /></label></PopoverDialog></PopoverContent> : null}</PopoverRoot>{current.fileName ? <span className="manual-invoice-entry__file-name">{current.fileName}</span> : null}</div>
          <div className="manual-invoice-entry__form">
            <Field label="票据方向"><Select aria-label="票据方向" isDisabled={busy || disabled} selectedKey={values.invoiceDirection} onSelectionChange={(key) => updateValue("invoiceDirection", String(key))}><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox><ListBox.Item id="input">进项发票</ListBox.Item><ListBox.Item id="output">销项发票</ListBox.Item></ListBox></Select.Popover></Select></Field>
            <Field label="发票性质"><Select aria-label="发票性质" isDisabled={busy || disabled} selectedKey={values.invoiceNature} onSelectionChange={(key) => updateValue("invoiceNature", String(key))}><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox><ListBox.Item id="blue">蓝字</ListBox.Item><ListBox.Item id="red">红字</ListBox.Item></ListBox></Select.Popover></Select></Field>
            <Field label="销方名称"><Input aria-label="销方名称" disabled={busy || disabled} value={values.sellerName} onChange={(event) => updateValue("sellerName", event.currentTarget.value)} /></Field><Field label="销方识别号"><Input aria-label="销方识别号" disabled={busy || disabled} value={values.sellerTaxNo} onChange={(event) => updateValue("sellerTaxNo", event.currentTarget.value)} /></Field>
            <Field label="购方名称"><Input aria-label="购方名称" disabled={busy || disabled} value={values.buyerName} onChange={(event) => updateValue("buyerName", event.currentTarget.value)} /></Field><Field label="购方识别号"><Input aria-label="购方识别号" disabled={busy || disabled} value={values.buyerTaxNo} onChange={(event) => updateValue("buyerTaxNo", event.currentTarget.value)} /></Field>
            <Field label="发票号码"><Input aria-label="发票号码" disabled={busy || disabled} value={values.invoiceNumber} onChange={(event) => updateValue("invoiceNumber", event.currentTarget.value)} /></Field><Field label="发票代码" required={invoiceCodeRequired}><Input aria-label="发票代码" disabled={busy || disabled} value={values.invoiceCode} onChange={(event) => updateValue("invoiceCode", event.currentTarget.value)} /></Field>
            <Field label="开票日期"><Input aria-label="开票日期" disabled={busy || disabled} type="date" value={values.invoiceDate} onChange={(event) => updateValue("invoiceDate", event.currentTarget.value)} /></Field><Field label="税率 %"><Input aria-label="税率" disabled={busy || disabled} inputMode="decimal" value={values.taxRate} onChange={(event) => updateValue("taxRate", event.currentTarget.value.replace(/%/g, ""))} /></Field>
            {moneyInput("netAmount", "不含税价格")}{moneyInput("taxAmount", "税额")}{moneyInput("totalWithTax", "价税合计")}
          </div>
          <div className="manual-invoice-entry__footer"><Button isDisabled={busy} size="sm" variant="secondary" onPress={onCancel}>取消</Button><Button isDisabled={busy || disabled} size="sm" variant="primary" onPress={() => { const error = validate(); if (error) setErrorMessage(error); else setPage("preview"); }}>预览</Button></div>
        </>}
    <div className="manual-invoice-entry__batch-footer"><span>{allSaved ? `已保存 ${entries.length} 张发票` : "请先预览并保存每张发票信息"}</span><Button isDisabled={!allSaved || busy || disabled} isPending={isSubmitting} size="sm" variant="primary" onPress={() => { void submitBatch(); }}>{isSubmitting ? "提交中..." : submitLabel}</Button></div>
  </div>;
}
