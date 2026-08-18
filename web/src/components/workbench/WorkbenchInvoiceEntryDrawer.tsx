import { Alert, Button } from "@heroui/react";
import { FileText, Trash2, Upload } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import ManualInvoiceBatchEditor from "../imports/ManualInvoiceBatchEditor";
import { resolveImportApiErrorMessage } from "../../features/imports/api";
import {
  confirmWorkbenchManualInvoiceSupplement,
  deleteWorkbenchOaSupportingDocument,
  listWorkbenchOaSupportingDocuments,
  uploadWorkbenchOaSupportingDocuments,
} from "../../features/workbench/api";
import type {
  WorkbenchOaInvoiceSupplementTarget,
  WorkbenchOaSupportingDocument,
} from "../../features/workbench/types";

type WorkbenchInvoiceEntryDrawerProps = {
  open: boolean;
  target: WorkbenchOaInvoiceSupplementTarget | null;
  disabled?: boolean;
  onClose: () => void;
  onCompleted: () => Promise<void> | void;
};

export default function WorkbenchInvoiceEntryDrawer({
  open,
  target,
  disabled = false,
  onClose,
  onCompleted,
}: WorkbenchInvoiceEntryDrawerProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<"upload" | "manual">("upload");
  const [documents, setDocuments] = useState<WorkbenchOaSupportingDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !target) return;
    let active = true;
    setLoading(true);
    setErrorMessage(null);
    void listWorkbenchOaSupportingDocuments(target)
      .then((items) => { if (active) setDocuments(items); })
      .catch((error) => { if (active) setErrorMessage(resolveImportApiErrorMessage(error, "补充凭证加载失败。")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, target]);

  async function upload(files: File[]) {
    if (!target || files.length === 0 || loading) return;
    setLoading(true); setErrorMessage(null);
    try {
      const created = await uploadWorkbenchOaSupportingDocuments(target, files);
      setDocuments((current) => [...current, ...created]);
      await onCompleted();
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "补充凭证上传失败。"));
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function remove(documentId: string) {
    if (loading) return;
    setLoading(true); setErrorMessage(null);
    try {
      await deleteWorkbenchOaSupportingDocument(documentId);
      setDocuments((current) => current.filter((document) => document.id !== documentId));
      await onCompleted();
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "补充凭证删除失败。"));
    } finally { setLoading(false); }
  }

  return (
    <AppDrawer
      ariaBusy={loading}
      className="workbench-invoice-entry-drawer manual-invoice-entry"
      closeDisabled={loading}
      closeLabel="关闭录入发票"
      onClose={onClose}
      open={open}
      title="录入发票"
      width="min(800px, 100vw)"
    >
      <div className="workbench-invoice-entry-drawer__mode-tabs" role="tablist" aria-label="录入方式">
        <button aria-selected={mode === "upload"} data-active={mode === "upload" || undefined} role="tab" type="button" onClick={() => setMode("upload")}>JPG/PDF上传</button>
        <button aria-selected={mode === "manual"} data-active={mode === "manual" || undefined} role="tab" type="button" onClick={() => setMode("manual")}>手工录入</button>
      </div>
      {errorMessage ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}
      {mode === "upload" ? (
        <div className="workbench-supporting-documents">
          <label className="workbench-supporting-documents__upload" htmlFor={inputId}>
            <Upload aria-hidden="true" size={18} />
            <span>{loading ? "处理中..." : "选择 JPG / PDF 文件"}</span>
            <input
              accept=".jpg,.jpeg,.pdf,image/jpeg,application/pdf"
              disabled={disabled || loading}
              id={inputId}
              multiple
              ref={inputRef}
              type="file"
              onChange={(event) => { void upload(Array.from(event.currentTarget.files ?? [])); }}
            />
          </label>
          <p>这些文件作为补充凭证直接关联当前 OA 子付款项，不进入统一发票池。</p>
          <div className="workbench-supporting-documents__list">
            {documents.length === 0 && !loading ? <span>尚未上传补充凭证。</span> : null}
            {documents.map((document) => (
              <div className="workbench-supporting-documents__item" key={document.id}>
                <FileText aria-hidden="true" size={17} />
                <a href={document.contentUrl} rel="noopener noreferrer" target="_blank">{document.fileName}</a>
                <span>{formatFileSize(document.sizeBytes)}</span>
                <Button aria-label={`删除 ${document.fileName}`} isDisabled={disabled || loading} size="sm" variant="ghost" onPress={() => { void remove(document.id); }}><Trash2 aria-hidden="true" size={15} /></Button>
              </div>
            ))}
          </div>
        </div>
      ) : target ? (
        <ManualInvoiceBatchEditor
          disabled={disabled}
          submitLabel="录入发票池并关联"
          onCancel={onClose}
          onSubmit={async (preview) => {
            await confirmWorkbenchManualInvoiceSupplement(target, preview);
            await onCompleted();
            onClose();
          }}
        />
      ) : null}
    </AppDrawer>
  );
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
