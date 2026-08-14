import {
  Alert,
  Button,
  Input,
  ListBox,
  PopoverContent,
  PopoverDialog,
  PopoverRoot,
  PopoverTrigger,
  Select,
} from "@heroui/react";
import { FileSearch, Upload } from "lucide-react";
import { type DragEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";

import AppDialog from "../common/AppDialog";
import AppDrawer from "../common/AppDrawer";
import {
  confirmImportFiles,
  discardImportSession,
  previewManualInvoice,
  recognizeManualInvoice,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import type {
  ImportSessionPayload,
  ManualInvoiceEntryPreview,
  ManualInvoiceEntryValues,
} from "../../features/imports/types";

const EMPTY_VALUES: ManualInvoiceEntryValues = {
  invoiceDirection: "input",
  invoiceNature: "blue",
  sellerName: "",
  sellerTaxNo: "",
  buyerName: "",
  buyerTaxNo: "",
  invoiceNumber: "",
  invoiceCode: "",
  invoiceDate: "",
  netAmount: "",
  taxRate: "",
  taxAmount: "",
  totalWithTax: "",
};

const FIELD_LABELS: Array<[keyof ManualInvoiceEntryValues, string]> = [
  ["sellerName", "销方名称"],
  ["sellerTaxNo", "销方识别号"],
  ["buyerName", "购方名称"],
  ["buyerTaxNo", "购方识别号"],
  ["invoiceNumber", "发票号码"],
  ["invoiceDate", "开票日期"],
  ["netAmount", "不含税价格"],
  ["taxRate", "税率"],
  ["taxAmount", "税额"],
  ["totalWithTax", "价税合计"],
];

type ManualInvoiceEntryDrawerProps = {
  disabled?: boolean;
  open: boolean;
  onClose: () => void;
  onImportAccepted: (payload: ImportSessionPayload) => void;
};

function isDigitalInvoiceNumber(value: string) {
  return /^\d{20}$/.test(value.trim());
}

function formatPreviewValue(key: keyof ManualInvoiceEntryValues, value: string, nature: string) {
  if (key === "invoiceDirection") return value === "input" ? "进项发票" : "销项发票";
  if (key === "invoiceNature") return value === "red" ? "红字" : "蓝字";
  if (key === "taxRate") return `${value}%`;
  if (["netAmount", "taxAmount", "totalWithTax"].includes(key)) {
    return `${nature === "red" ? "-" : ""}${value}`;
  }
  return value || "—";
}

function Field({ label, required = true, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="manual-invoice-entry__field">
      <span>{label}{required ? <span aria-hidden="true" className="manual-invoice-entry__required"> *</span> : null}</span>
      {children}
    </label>
  );
}

export default function ManualInvoiceEntryDrawer({
  disabled = false,
  open,
  onClose,
  onImportAccepted,
}: ManualInvoiceEntryDrawerProps) {
  const fileInputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [values, setValues] = useState<ManualInvoiceEntryValues>({ ...EMPTY_VALUES });
  const [fileName, setFileName] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [isRecognizing, setIsRecognizing] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const [preview, setPreview] = useState<ManualInvoiceEntryPreview | null>(null);
  const busy = isRecognizing || isPreviewing || isConfirming || isDiscarding;
  const invoiceCodeRequired = !isDigitalInvoiceNumber(values.invoiceNumber);
  const previewRows = useMemo(() => preview ? [
    ["票据方向", "invoiceDirection"],
    ["发票性质", "invoiceNature"],
    ["销方名称", "sellerName"],
    ["销方识别号", "sellerTaxNo"],
    ["购方名称", "buyerName"],
    ["购方识别号", "buyerTaxNo"],
    ["发票号码", "invoiceNumber"],
    ["发票代码", "invoiceCode"],
    ["开票日期", "invoiceDate"],
    ["不含税价格", "netAmount"],
    ["税率", "taxRate"],
    ["税额", "taxAmount"],
    ["价税合计", "totalWithTax"],
  ] as Array<[string, keyof ManualInvoiceEntryValues]> : [], [preview]);

  function updateValue(key: keyof ManualInvoiceEntryValues, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
    setErrorMessage(null);
  }

  function reset() {
    setValues({ ...EMPTY_VALUES });
    setFileName("");
    setStatusMessage(null);
    setErrorMessage(null);
    setUploadOpen(false);
    setPreview(null);
  }

  function handleClose() {
    if (busy || preview) return;
    reset();
    onClose();
  }

  async function handleRecognize(file: File | undefined) {
    if (!file || busy) return;
    const normalizedName = file.name.toLowerCase();
    if (!normalizedName.endsWith(".jpg") && !normalizedName.endsWith(".jpeg") && !normalizedName.endsWith(".pdf")) {
      setErrorMessage("仅支持 JPG、JPEG 或 PDF 发票文件。");
      return;
    }
    setIsRecognizing(true);
    setErrorMessage(null);
    setStatusMessage(null);
    setFileName(file.name);
    try {
      const recognized = await recognizeManualInvoice(file);
      setValues((current) => {
        const next = { ...current };
        Object.entries(recognized).forEach(([key, value]) => {
          if (value !== undefined && String(value).trim()) {
            Object.assign(next, { [key]: String(value) });
          }
        });
        return next;
      });
      const hasRecognizedValue = Object.values(recognized).some((value) => String(value ?? "").trim());
      setStatusMessage(hasRecognizedValue ? "已预填识别结果，请核对。" : "未识别到可预填字段。");
      setUploadOpen(false);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "发票解析失败，请手工录入。"));
    } finally {
      setIsRecognizing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function validateClientValues() {
    for (const [key, label] of FIELD_LABELS) {
      if (!values[key].trim()) return `请填写${label}。`;
    }
    if (invoiceCodeRequired && !values.invoiceCode.trim()) return "传统发票必须填写发票代码。";
    return null;
  }

  async function handlePreview() {
    const validationError = validateClientValues();
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    try {
      const nextPreview = await previewManualInvoice(values);
      setValues(nextPreview.values);
      setPreview(nextPreview);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "发票预览失败，请核对后重试。"));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleReturnToEdit() {
    if (!preview) return;
    setIsDiscarding(true);
    setErrorMessage(null);
    try {
      await discardImportSession(preview.importSession.session.id);
      setPreview(null);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "返回编辑失败，请稍后重试。"));
    } finally {
      setIsDiscarding(false);
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    setIsConfirming(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(preview.importSession.session.id, [preview.fileId]);
      onImportAccepted(payload);
      reset();
      onClose();
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
    } finally {
      setIsConfirming(false);
    }
  }

  const moneyInput = (key: "netAmount" | "taxAmount" | "totalWithTax", label: string) => (
    <Field label={label}>
      <div className="manual-invoice-entry__signed-input" data-negative={values.invoiceNature === "red" || undefined}>
        {values.invoiceNature === "red" ? <span aria-hidden="true">−</span> : null}
        <Input
          aria-label={label}
          inputMode="decimal"
          disabled={busy || disabled}
          onChange={(event) => updateValue(key, event.currentTarget.value.replace(/^-/, ""))}
          value={values[key]}
        />
      </div>
    </Field>
  );

  return (
    <>
      <AppDrawer
        ariaBusy={busy}
        className="manual-invoice-entry"
        closeDisabled={busy || Boolean(preview)}
        closeLabel="关闭发票录入"
        footer={(
          <div className="manual-invoice-entry__footer">
            <Button isDisabled={busy} onPress={handleClose} size="sm" type="button" variant="secondary">取消</Button>
            <Button
              isDisabled={disabled || busy}
              isPending={isPreviewing}
              onPress={() => { void handlePreview(); }}
              size="sm"
              type="button"
              variant="primary"
            >
              {isPreviewing ? "校验中..." : "预览"}
            </Button>
          </div>
        )}
        onClose={handleClose}
        open={open}
        title="发票录入"
        width="min(720px, 100vw)"
      >
        <div className="manual-invoice-entry__body">
          <div className="manual-invoice-entry__toolbar">
            <PopoverRoot
              isOpen={uploadOpen}
              onOpenChange={(nextOpen) => {
                if (!disabled && !busy) setUploadOpen(nextOpen);
              }}
            >
              <PopoverTrigger
                aria-label="上传发票文件"
                className="manual-invoice-entry__upload-trigger"
                aria-disabled={disabled || busy}
                data-disabled={disabled || busy || undefined}
              >
                <Upload aria-hidden="true" size={15} />
                上传
              </PopoverTrigger>
              {uploadOpen ? (
                <PopoverContent className="manual-invoice-entry__upload-popover" placement="bottom start">
                  <PopoverDialog aria-label="上传并识别发票">
                    <label
                      className="manual-invoice-entry__dropzone"
                      htmlFor={fileInputId}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event: DragEvent<HTMLLabelElement>) => {
                        event.preventDefault();
                        void handleRecognize(event.dataTransfer.files[0]);
                      }}
                    >
                      <FileSearch aria-hidden="true" size={22} />
                      <span>{isRecognizing ? "解析中..." : "拖入或选择 JPG / PDF"}</span>
                      <input
                        accept=".jpg,.jpeg,.pdf,image/jpeg,application/pdf"
                        className="manual-invoice-entry__file-input"
                        disabled={busy}
                        id={fileInputId}
                        multiple
                        onChange={(event) => { void handleRecognize(event.currentTarget.files?.[0]); }}
                        ref={fileInputRef}
                        type="file"
                      />
                    </label>
                  </PopoverDialog>
                </PopoverContent>
              ) : null}
            </PopoverRoot>
            {fileName ? <span className="manual-invoice-entry__file-name" title={fileName}>{fileName}</span> : null}
          </div>

          {statusMessage ? <Alert className="manual-invoice-entry__notice">{statusMessage}</Alert> : null}
          {errorMessage ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}

          <div className="manual-invoice-entry__form">
            <Field label="票据方向">
              <Select
                aria-label="票据方向"
                isDisabled={busy || disabled}
                onSelectionChange={(key) => updateValue("invoiceDirection", String(key))}
                selectedKey={values.invoiceDirection}
              >
                <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox>
                  <ListBox.Item id="input" textValue="进项发票">进项发票</ListBox.Item>
                  <ListBox.Item id="output" textValue="销项发票">销项发票</ListBox.Item>
                </ListBox></Select.Popover>
              </Select>
            </Field>
            <Field label="发票性质">
              <Select
                aria-label="发票性质"
                isDisabled={busy || disabled}
                onSelectionChange={(key) => updateValue("invoiceNature", String(key))}
                selectedKey={values.invoiceNature}
              >
                <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
                <Select.Popover><ListBox>
                  <ListBox.Item id="blue" textValue="蓝字">蓝字</ListBox.Item>
                  <ListBox.Item id="red" textValue="红字">红字</ListBox.Item>
                </ListBox></Select.Popover>
              </Select>
            </Field>
            <Field label="销方名称"><Input aria-label="销方名称" disabled={busy || disabled} onChange={(e) => updateValue("sellerName", e.currentTarget.value)} value={values.sellerName} /></Field>
            <Field label="销方识别号"><Input aria-label="销方识别号" disabled={busy || disabled} onChange={(e) => updateValue("sellerTaxNo", e.currentTarget.value)} value={values.sellerTaxNo} /></Field>
            <Field label="购方名称"><Input aria-label="购方名称" disabled={busy || disabled} onChange={(e) => updateValue("buyerName", e.currentTarget.value)} value={values.buyerName} /></Field>
            <Field label="购方识别号"><Input aria-label="购方识别号" disabled={busy || disabled} onChange={(e) => updateValue("buyerTaxNo", e.currentTarget.value)} value={values.buyerTaxNo} /></Field>
            <Field label="发票号码"><Input aria-label="发票号码" disabled={busy || disabled} onChange={(e) => updateValue("invoiceNumber", e.currentTarget.value)} value={values.invoiceNumber} /></Field>
            <Field label="发票代码" required={invoiceCodeRequired}><Input aria-label="发票代码" disabled={busy || disabled} onChange={(e) => updateValue("invoiceCode", e.currentTarget.value)} value={values.invoiceCode} /></Field>
            <Field label="开票日期"><Input aria-label="开票日期" disabled={busy || disabled} onChange={(e) => updateValue("invoiceDate", e.currentTarget.value)} type="date" value={values.invoiceDate} /></Field>
            <Field label="税率 %"><Input aria-label="税率" inputMode="decimal" disabled={busy || disabled} onChange={(e) => updateValue("taxRate", e.currentTarget.value.replace(/%/g, ""))} value={values.taxRate} /></Field>
            {moneyInput("netAmount", "不含税价格")}
            {moneyInput("taxAmount", "税额")}
            {moneyInput("totalWithTax", "价税合计")}
          </div>
        </div>
      </AppDrawer>

      <AppDialog
        actions={(
          <>
            <Button isDisabled={isConfirming || isDiscarding} isPending={isDiscarding} onPress={() => { void handleReturnToEdit(); }} size="sm" variant="secondary">
              {isDiscarding ? "返回中..." : "返回编辑"}
            </Button>
            <Button isDisabled={isConfirming || isDiscarding} isPending={isConfirming} onPress={() => { void handleConfirm(); }} size="sm" variant="primary">
              {isConfirming ? "导入中..." : "确认导入"}
            </Button>
          </>
        )}
        className="manual-invoice-entry__preview-dialog"
        disableEscapeClose
        isDismissable={false}
        maxWidth="lg"
        onClose={() => undefined}
        open={Boolean(preview)}
        title="确认发票信息"
      >
        {preview ? (
          <dl className="manual-invoice-entry__preview-list">
            {previewRows.map(([label, key]) => (
              <div key={key} className="manual-invoice-entry__preview-row">
                <dt>{label}</dt>
                <dd>{formatPreviewValue(key, preview.values[key], preview.values.invoiceNature)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {errorMessage && preview ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}
      </AppDialog>
    </>
  );
}
