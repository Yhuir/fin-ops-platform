import { Alert, Button, Chip, Input, Tabs } from "@heroui/react";
import { FileText, Trash2, Upload } from "lucide-react";
import { type DragEvent, useEffect, useId, useRef, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import ManualInvoiceBatchEditor from "../imports/ManualInvoiceBatchEditor";
import {
  confirmWorkbenchManualInvoiceSupplement,
  listWorkbenchOaSupportingDocuments,
  previewWorkbenchManualInvoices,
  resolveWorkbenchActionErrorMessage,
  saveWorkbenchOaSupportingDocuments,
} from "../../features/workbench/api";
import type {
  WorkbenchOaInvoiceSupplementTarget,
  WorkbenchOaSupportingDocument,
  WorkbenchOaSupportingDocumentSet,
} from "../../features/workbench/types";

type WorkbenchInvoiceEntryDrawerProps = {
  open: boolean;
  initialMode?: "upload" | "manual";
  target: WorkbenchOaInvoiceSupplementTarget | null;
  disabled?: boolean;
  onClose: () => void;
  onCompleted: () => Promise<void> | void;
  onSupportingDocumentsChanged?: (
    target: WorkbenchOaInvoiceSupplementTarget,
    documents: WorkbenchOaSupportingDocument[],
  ) => Promise<void> | void;
};

export default function WorkbenchInvoiceEntryDrawer({
  open,
  initialMode = "manual",
  target,
  disabled = false,
  onClose,
  onCompleted,
  onSupportingDocumentsChanged,
}: WorkbenchInvoiceEntryDrawerProps) {
  const [completion, setCompletion] = useState<string | undefined>();
  const [entryBusy, setEntryBusy] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const targetKey = open && target ? JSON.stringify([target.oaRowId, target.expenseItemId, target.caseId]) : "";
  const [modeSelection, setModeSelection] = useState<{ targetKey: string; mode: "upload" | "manual" } | null>(null);
  const mode = modeSelection?.targetKey === targetKey ? modeSelection.mode : initialMode;
  const [documents, setDocuments] = useState<WorkbenchOaSupportingDocument[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [totalAmount, setTotalAmount] = useState("");
  const [saved, setSaved] = useState<WorkbenchOaSupportingDocumentSet | null>(null);
  const loadedTargetRef = useRef<string | null>(null);
  const activeTargetRef = useRef({ key: targetKey });
  if (activeTargetRef.current.key !== targetKey) activeTargetRef.current = { key: targetKey };
  const requestToken = activeTargetRef.current;
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setModeSelection(null);
    setCompletion(undefined);
    setDocuments([]);
    setFiles([]);
    setTotalAmount("");
    setSaved(null);
    setLoading(false);
    setEntryBusy(false);
    setErrorMessage(null);
    setDragging(false);
    dragDepthRef.current = 0;
    loadedTargetRef.current = null;
  }, [targetKey, initialMode]);

  useEffect(() => {
    if (!targetKey || !target || mode !== "upload" || loadedTargetRef.current === targetKey) return;
    let active = true;
    setLoading(true);
    setErrorMessage(null);
    void listWorkbenchOaSupportingDocuments(target)
      .then((value) => {
        if (!active || activeTargetRef.current !== requestToken) return;
        loadedTargetRef.current = targetKey;
        setSaved(value);
        setDocuments(value.documents);
        setTotalAmount(value.totalAmount ?? "");
      })
      .catch((error) => {
        if (active && activeTargetRef.current === requestToken) setErrorMessage(resolveWorkbenchActionErrorMessage(error, "补充凭证加载失败。"));
      })
      .finally(() => { if (active && activeTargetRef.current === requestToken) setLoading(false); });
    return () => { active = false; };
  }, [mode, targetKey, loadAttempt]);

  const fileCount = documents.length + files.length;
  const amountValid = fileCount === 0 || /^\d{1,18}(?:\.\d{1,2})?$/.test(totalAmount.trim());
  const dirty = saved !== null && (files.length > 0 || totalAmount !== (saved.totalAmount ?? "")
    || documents.length !== saved.documents.length);

  function addFiles(selected: File[]) {
    if (disabled || loading || !saved) return;
    setFiles((current) => [...current, ...selected]);
    setCompletion(undefined);
    setErrorMessage(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function cancelDraft() {
    if (!saved || loading) return;
    setDocuments(saved.documents);
    setTotalAmount(saved.totalAmount ?? "");
    setFiles([]);
    setErrorMessage(null);
    setCompletion(undefined);
  }

  async function save() {
    if (!target || disabled || loading || !saved || !dirty || !amountValid) return;
    const requestKey = requestToken;
    setLoading(true);
    setErrorMessage(null);
    setCompletion(undefined);
    try {
      const value = await saveWorkbenchOaSupportingDocuments(target, {
        retainedDocumentIds: documents.map((document) => document.id),
        files,
        totalAmount: fileCount === 0 ? null : totalAmount.trim(),
        expectedVersion: saved.version,
      });
      if (activeTargetRef.current === requestKey) {
        setSaved(value);
        setDocuments(value.documents);
        setFiles([]);
        setTotalAmount(value.totalAmount ?? "");
        setCompletion("凭证已保存");
      }
      try {
        await onSupportingDocumentsChanged?.(target, value.documents);
      } catch (error) {
        if (activeTargetRef.current === requestKey) {
          setCompletion(`凭证已保存，但页面刷新失败：${resolveWorkbenchActionErrorMessage(error, "请刷新页面查看。")}`);
        }
      }
    } catch (error) {
      if (activeTargetRef.current === requestKey) setErrorMessage(resolveWorkbenchActionErrorMessage(error, "凭证保存失败，编辑内容已保留。"));
    } finally {
      if (activeTargetRef.current === requestKey) setLoading(false);
    }
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
    if (!disabled && !loading) addFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <AppDrawer
      completion={completion}
      closeDisabled={loading || entryBusy}
      ariaBusy={loading}
      className="workbench-invoice-entry-drawer manual-invoice-entry"
      closeLabel="关闭录入发票"
      onClose={onClose}
      open={open}
      title={mode === "upload" ? "管理凭证" : "录入发票"}
      width="min(800px, 100vw)"
    >
      <Tabs selectedKey={mode} onSelectionChange={(key) => { if (!loading && !entryBusy) { setModeSelection({ targetKey, mode: String(key) as "upload" | "manual" }); setCompletion(undefined); } }}>
        <Tabs.ListContainer className="workbench-invoice-entry-drawer__mode-tabs-container">
          <Tabs.List aria-label="录入方式" className="workbench-invoice-entry-drawer__mode-tabs">
            <Tabs.Tab isDisabled={loading || entryBusy} id="manual">发票录入</Tabs.Tab>
            <Tabs.Tab isDisabled={loading || entryBusy} id="upload">补充凭证</Tabs.Tab>
          </Tabs.List>
        </Tabs.ListContainer>
      </Tabs>
      {errorMessage ? <Alert className="manual-invoice-entry__notice manual-invoice-entry__notice--danger">{errorMessage}</Alert> : null}
      {mode === "upload" && !saved && !loading && errorMessage ? <Button variant="secondary" onPress={() => setLoadAttempt((current) => current + 1)}>重新读取凭证</Button> : null}
      {mode === "manual" && target ? (
        <ManualInvoiceBatchEditor
          key={targetKey}
          disabled={disabled}
          previewInvoices={previewWorkbenchManualInvoices}
          submitLabel="确认录入并关联"
          onBusyChange={setEntryBusy}
          onSubmit={async (preview) => {
            await confirmWorkbenchManualInvoiceSupplement(target, preview);
            if (activeTargetRef.current === requestToken) setCompletion("发票已录入");
            try { await onCompleted(); } catch (error) {
              if (activeTargetRef.current === requestToken) setCompletion(`发票已录入，但页面刷新失败：${resolveWorkbenchActionErrorMessage(error, "请刷新页面查看。")}`);
            }
          }}
        />
      ) : mode === "upload" ? (
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
            <strong>{loading ? "处理中..." : dragging ? "松开以添加文件" : "拖拽文件到此处，或点击选择"}</strong>
            <span>支持 JPG、JPEG、PNG、PDF，单个文件不超过 25MB</span>
            <input
              aria-label="上传 JPG、PNG 或 PDF 补充凭证"
              accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
              disabled={disabled || loading || !saved}
              id={inputId}
              multiple
              ref={inputRef}
              type="file"
              onChange={(event) => addFiles(Array.from(event.currentTarget.files ?? []))}
            />
          </label>
          <div className="workbench-supporting-documents__summary">
            <p>补充凭证关联当前 OA 明细，不进入正式发票池。</p>
            {fileCount > 0 ? <Chip color="default" size="sm" variant="soft"><Chip.Label>{fileCount} 个文件</Chip.Label></Chip> : null}
          </div>
          <label className="workbench-supporting-documents__amount">
            <span>凭证总金额（元）</span>
            <Input aria-label="凭证总金额（元）" inputMode="decimal" value={totalAmount}
              disabled={disabled || loading || !saved || fileCount === 0}
              onChange={(event) => { setTotalAmount(event.currentTarget.value); setCompletion(undefined); }}
              placeholder="填写当前 OA 明细全部凭证的总金额" />
            <span>{fileCount === 0 ? "删除全部文件并保存后，凭证金额会一并清空。" : "多份文件只填写一个总金额；允许 0，最多两位小数。"}</span>
            {!amountValid && totalAmount.trim() ? <span role="alert">请输入非负金额，最多两位小数。</span> : null}
          </label>
          <div className="workbench-supporting-documents__list">
            {fileCount === 0 && !loading ? <span>尚未上传补充凭证。</span> : null}
            {documents.map((document) => (
              <div className="workbench-supporting-documents__item" key={document.id}>
                <FileText aria-hidden="true" size={17} />
                <a href={document.contentUrl} rel="noopener noreferrer" target="_blank">{document.fileName}</a>
                <span>{formatFileSize(document.sizeBytes)}</span>
                <Button aria-label={`删除 ${document.fileName}`} isDisabled={disabled || loading} size="sm" variant="ghost" onPress={() => { setDocuments((current) => current.filter((item) => item.id !== document.id)); setCompletion(undefined); }}><Trash2 aria-hidden="true" size={15} /></Button>
              </div>
            ))}
            {files.map((file, index) => (
              <div className="workbench-supporting-documents__item" key={`${index}:${file.name}`}>
                <FileText aria-hidden="true" size={17} />
                <span>{file.name}（待保存）</span>
                <span>{formatFileSize(file.size)}</span>
                <Button aria-label={`移除 ${file.name}`} isDisabled={disabled || loading} size="sm" variant="ghost"
                  onPress={() => setFiles((current) => current.filter((_, candidate) => candidate !== index))}><Trash2 aria-hidden="true" size={15} /></Button>
              </div>
            ))}
          </div>
          <div className="workbench-supporting-documents__actions">
            <Button isDisabled={disabled || loading || !dirty} variant="secondary" onPress={cancelDraft}>取消修改</Button>
            <Button isDisabled={disabled || loading || !dirty || !amountValid} isPending={loading} variant="primary" onPress={save}>保存凭证</Button>
          </div>
        </div>
      ) : null}
    </AppDrawer>
  );
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
