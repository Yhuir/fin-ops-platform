import { Alert, Button, Chip, Tabs } from "@heroui/react";
import { FileText, Trash2, Upload } from "lucide-react";
import { type DragEvent, useEffect, useId, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import ManualInvoiceBatchEditor from "../imports/ManualInvoiceBatchEditor";
import {
  confirmWorkbenchManualInvoiceSupplement,
  deleteWorkbenchOaSupportingDocument,
  listWorkbenchOaSupportingDocuments,
  resolveWorkbenchActionErrorMessage,
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
  onSupportingDocumentsChanged?: (
    target: WorkbenchOaInvoiceSupplementTarget,
    documents: WorkbenchOaSupportingDocument[],
  ) => void;
};

export default function WorkbenchInvoiceEntryDrawer({
  open,
  target,
  disabled = false,
  onClose,
  onCompleted,
  onSupportingDocumentsChanged,
}: WorkbenchInvoiceEntryDrawerProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const [mode, setMode] = useState<"upload" | "manual">("upload");
  const [documents, setDocuments] = useState<WorkbenchOaSupportingDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !target) return;
    let active = true;
    setDocuments([]);
    setLoading(true);
    setErrorMessage(null);
    void listWorkbenchOaSupportingDocuments(target)
      .then((items) => { if (active) setDocuments(items); })
      .catch((error) => { if (active) setErrorMessage(resolveWorkbenchActionErrorMessage(error, "补充凭证加载失败。")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, target]);

  async function upload(files: File[]) {
    if (!target || files.length === 0 || loading) return;
    setLoading(true); setErrorMessage(null);
    try {
      const created = await uploadWorkbenchOaSupportingDocuments(target, files);
      const byId = new Map(documents.map((document) => [document.id, document]));
      created.forEach((document) => byId.set(document.id, document));
      const nextDocuments = Array.from(byId.values());
      setDocuments(nextDocuments);
      onSupportingDocumentsChanged?.(target, nextDocuments);
    } catch (error) {
      setErrorMessage(resolveWorkbenchActionErrorMessage(error, "补充凭证上传失败。"));
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
      const nextDocuments = documents.filter((document) => document.id !== documentId);
      setDocuments(nextDocuments);
      if (target) onSupportingDocumentsChanged?.(target, nextDocuments);
    } catch (error) {
      setErrorMessage(resolveWorkbenchActionErrorMessage(error, "补充凭证删除失败。"));
    } finally { setLoading(false); }
  }

  function handleDragEnter(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (disabled || loading) return;
    dragDepthRef.current += 1;
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);
    if (!disabled && !loading) void upload(Array.from(event.dataTransfer.files));
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
      <Tabs selectedKey={mode} onSelectionChange={(key) => setMode(String(key) as "upload" | "manual")}>
        <Tabs.ListContainer className="workbench-invoice-entry-drawer__mode-tabs-container">
          <Tabs.List aria-label="录入方式" className="workbench-invoice-entry-drawer__mode-tabs">
            <Tabs.Tab id="upload">上传凭证</Tabs.Tab>
            <Tabs.Tab id="manual">手工录入</Tabs.Tab>
          </Tabs.List>
        </Tabs.ListContainer>
      </Tabs>
      {errorMessage ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}
      {mode === "upload" ? (
        <div className="workbench-supporting-documents">
          <label
            className="workbench-supporting-documents__upload"
            data-dragging={dragging || undefined}
            htmlFor={inputId}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <Upload aria-hidden="true" size={18} />
            <strong>{loading ? "处理中..." : dragging ? "松开以上传文件" : "拖拽文件到此处，或点击选择"}</strong>
            <span>支持 JPG、JPEG、PNG、PDF，单个文件不超过 25MB</span>
            <input
              aria-label="上传 JPG、PNG 或 PDF 补充凭证"
              accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
              disabled={disabled || loading}
              id={inputId}
              multiple
              ref={inputRef}
              type="file"
              onChange={(event) => { void upload(Array.from(event.currentTarget.files ?? [])); }}
            />
          </label>
          <div className="workbench-supporting-documents__summary">
            <p>补充凭证直接关联当前 OA 子付款项，不进入统一发票池。</p>
            {documents.length > 0 ? <Chip color="default" size="sm" variant="soft"><Chip.Label>{documents.length} 个文件</Chip.Label></Chip> : null}
          </div>
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
