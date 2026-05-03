import { type DragEvent, useId, useMemo, useState } from "react";

import {
  confirmImportFiles,
  previewImportFiles,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import { confirmEtcImportSession, previewEtcZipFiles } from "../../features/etc/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportFilePreviewOverride,
  ImportSessionPayload,
} from "../../features/imports/types";
import type { EtcImportItem, EtcImportPreviewResult } from "../../features/etc/types";
import type { BankAccountMapping } from "../../features/workbench/types";

export type WorkbenchImportMode = "bank_transaction" | "invoice" | "etc_invoice";

type WorkbenchImportModalProps = {
  mode: WorkbenchImportMode;
  bankOptions: BankAccountMapping[];
  onClose: () => void;
  onImported: (payload: ImportSessionPayload) => Promise<void> | void;
};

type FileSelectionState = Record<
  string,
  {
    bankMappingId: string;
    bankName: string;
    bankShortName: string;
    last4: string;
    invoiceBatchType: ImportBatchType | "";
  }
>;

const BATCH_TYPE_LABELS: Record<ImportBatchType, string> = {
  input_invoice: "进项发票",
  output_invoice: "销项发票",
  bank_transaction: "银行流水",
};

const STATUS_LABELS: Record<string, string> = {
  preview_ready: "待确认",
  preview_ready_with_errors: "待确认",
  unrecognized_template: "无法识别",
  confirmed: "已确认导入",
  skipped: "已跳过",
  reverted: "已撤销",
};

const ETC_IMPORT_STATUS_LABELS: Record<string, string> = {
  imported: "新增",
  created: "新增",
  duplicate_skipped: "重复跳过",
  attachment_completed: "附件补齐",
  failed: "异常",
};

function buildSelectedFileKey(file: File) {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function mergeSelectedFiles(currentFiles: File[], nextFiles: File[]) {
  const merged = [...currentFiles];
  const seen = new Set(currentFiles.map(buildSelectedFileKey));
  nextFiles.forEach((file) => {
    const key = buildSelectedFileKey(file);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    merged.push(file);
  });
  return merged;
}

function canConfirmFile(file: ImportFilePreview) {
  return file.status === "preview_ready";
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function batchTypeLabel(batchType?: ImportBatchType | null) {
  if (!batchType) {
    return "待指定";
  }
  return BATCH_TYPE_LABELS[batchType] ?? batchType;
}

function buildBankAccountOptionLabel(bankOption: BankAccountMapping) {
  return `${bankOption.bankName} ${bankOption.last4}`.trim();
}

function isExcelFile(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".xls") || normalizedName.endsWith(".xlsx");
}

function isZipFile(file: File) {
  return file.name.toLowerCase().endsWith(".zip");
}

function etcStatusLabel(status: string) {
  return ETC_IMPORT_STATUS_LABELS[status] ?? status;
}

function formatSelectedBankAccountLabel(file: Pick<ImportFilePreview, "selectedBankName" | "selectedBankLast4">) {
  return `${file.selectedBankName ?? ""} ${file.selectedBankLast4 ?? ""}`.trim();
}

export default function WorkbenchImportModal({
  mode,
  bankOptions,
  onClose,
  onImported,
}: WorkbenchImportModalProps) {
  const inputId = useId();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileSelections, setFileSelections] = useState<FileSelectionState>({});
  const [previewPayload, setPreviewPayload] = useState<ImportSessionPayload | null>(null);
  const [etcPreviewPayload, setEtcPreviewPayload] = useState<EtcImportPreviewResult | null>(null);
  const [etcImported, setEtcImported] = useState(false);
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const title = mode === "bank_transaction" ? "银行流水导入" : mode === "etc_invoice" ? "ETC发票导入" : "发票导入";
  const uploadLabel = mode === "bank_transaction" ? "上传银行流水文件" : mode === "etc_invoice" ? "上传ETC zip" : "上传发票文件";
  const canUseBankImport = mode !== "bank_transaction" || bankOptions.length > 0;
  const bankOptionMap = useMemo(
    () => new Map(bankOptions.map((item) => [item.id, item])),
    [bankOptions],
  );
  const allFilesConfigured = selectedFiles.length > 0 && selectedFiles.every((file) => {
    if (mode === "etc_invoice") {
      return isZipFile(file);
    }
    const selection = fileSelections[buildSelectedFileKey(file)];
    return mode === "bank_transaction" ? Boolean(selection?.bankMappingId) : Boolean(selection?.invoiceBatchType);
  });
  const canPreview = canUseBankImport && allFilesConfigured && !isPreviewing && !isConfirming;
  const confirmableFileIds = useMemo(
    () => previewPayload?.files.filter(canConfirmFile).map((file) => file.id) ?? [],
    [previewPayload],
  );
  const canConfirm = confirmableFileIds.length > 0 && !isPreviewing && !isConfirming;
  const canConfirmEtc = Boolean(etcPreviewPayload?.sessionId) && !etcImported && !isPreviewing && !isConfirming;
  const conflictingPreviewFiles = useMemo(
    () => previewPayload?.files.filter((file) => canConfirmFile(file) && file.bankSelectionConflict) ?? [],
    [previewPayload],
  );
  const conflictConfirmLabel = useMemo(() => {
    const selectedAccountLabel = formatSelectedBankAccountLabel(conflictingPreviewFiles[0] ?? {});
    return selectedAccountLabel
      ? `仍按所选账户 ${selectedAccountLabel} 导入`
      : "仍按所选账户导入";
  }, [conflictingPreviewFiles]);

  function updateFiles(nextFiles: File[]) {
    setSelectedFiles((current) => mergeSelectedFiles(current, nextFiles));
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcImported(false);
    setConflictDialogOpen(false);
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function applyDroppedFiles(files: File[]) {
    const isSupportedFile = mode === "etc_invoice" ? isZipFile : isExcelFile;
    const validFiles = files.filter(isSupportedFile);
    const invalidFiles = files.filter((file) => !isSupportedFile(file));
    if (validFiles.length > 0) {
      updateFiles(validFiles);
    } else if (invalidFiles.length > 0) {
      setPreviewPayload(null);
      setEtcPreviewPayload(null);
      setEtcImported(false);
      setConflictDialogOpen(false);
      setFeedbackMessage(null);
    }
    if (invalidFiles.length > 0) {
      setErrorMessage(mode === "etc_invoice" ? "仅支持 .zip" : "仅支持 .xls/.xlsx");
    }
  }

  function handleDropzoneDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (isPreviewing || isConfirming) {
      return;
    }
    setIsDragActive(true);
  }

  function handleDropzoneDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
      return;
    }
    setIsDragActive(false);
  }

  function handleDropzoneDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
    if (isPreviewing || isConfirming) {
      return;
    }
    const nextFiles = Array.from(event.dataTransfer.files ?? []);
    if (nextFiles.length === 0) {
      return;
    }
    applyDroppedFiles(nextFiles);
  }

  function handleSelectionChange(file: File, field: "bankMappingId" | "invoiceBatchType", value: string) {
    const key = buildSelectedFileKey(file);
    setFileSelections((current) => ({
      ...current,
      [key]: field === "bankMappingId"
        ? (() => {
          const bankOption = bankOptionMap.get(value);
          return {
            bankMappingId: value,
            bankName: bankOption?.bankName ?? "",
            bankShortName: bankOption?.shortName ?? "",
            last4: bankOption?.last4 ?? "",
            invoiceBatchType: current[key]?.invoiceBatchType ?? "",
          };
        })()
        : {
          bankMappingId: current[key]?.bankMappingId ?? "",
          bankName: current[key]?.bankName ?? "",
          bankShortName: current[key]?.bankShortName ?? "",
          last4: current[key]?.last4 ?? "",
          invoiceBatchType: value as ImportBatchType | "",
        },
    }));
    setPreviewPayload(null);
    setConflictDialogOpen(false);
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function handleRemoveFile(file: File) {
    const key = buildSelectedFileKey(file);
    setSelectedFiles((current) => current.filter((item) => buildSelectedFileKey(item) !== key));
    setFileSelections((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcImported(false);
    setConflictDialogOpen(false);
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function buildPreviewOverrides(): ImportFilePreviewOverride[] {
    return selectedFiles.map((file) => {
      const selection = fileSelections[buildSelectedFileKey(file)];
      if (mode === "bank_transaction") {
        const bankMappingId = selection?.bankMappingId ?? "";
        const bankName = selection?.bankName ?? "";
        const bankShortName = selection?.bankShortName ?? "";
        const last4 = selection?.last4 ?? "";
        return {
          fileName: file.name,
          batchType: "bank_transaction",
          bankMappingId,
          bankName,
          bankShortName,
          last4,
        };
      }
      return {
        fileName: file.name,
        templateCode: "invoice_export",
        batchType: selection?.invoiceBatchType || undefined,
      };
    });
  }

  async function handlePreview() {
    if (mode === "etc_invoice") {
      if (selectedFiles.length === 0) {
        setErrorMessage("请先选择至少一个 ETC zip 文件。");
        return;
      }
      if (!selectedFiles.every(isZipFile)) {
        setErrorMessage("ETC发票导入仅支持 zip 文件。");
        return;
      }
      setIsPreviewing(true);
      setErrorMessage(null);
      setFeedbackMessage(null);
      try {
        const payload = await previewEtcZipFiles(selectedFiles);
        setEtcPreviewPayload(payload);
        setEtcImported(false);
        setPreviewPayload(null);
        setFeedbackMessage(`已完成 ${selectedFiles.length} 个 ETC zip 文件预览。`);
      } catch (error) {
        setErrorMessage(resolveImportApiErrorMessage(error, "ETC zip 预览失败，请稍后重试。"));
      } finally {
        setIsPreviewing(false);
      }
      return;
    }
    if (!canUseBankImport) {
      setErrorMessage("设置里还没有银行账户映射，请先在设置中维护银行。");
      return;
    }
    if (!allFilesConfigured) {
      setErrorMessage(mode === "bank_transaction" ? "请为每个文件选择对应账户。" : "请为每个文件选择进项票或销项票。");
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    setConflictDialogOpen(false);
    try {
      const payload = await previewImportFiles(selectedFiles, "web_finance_user", buildPreviewOverrides());
      setPreviewPayload(payload);
      setFeedbackMessage(`已完成 ${payload.files.length} 个文件的预览识别。`);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "文件预览失败，请稍后重试。"));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function submitConfirm() {
    if (mode === "etc_invoice") {
      if (!etcPreviewPayload?.sessionId) {
        setErrorMessage("请先预览 ETC zip 文件。");
        return;
      }
      setIsConfirming(true);
      setErrorMessage(null);
      try {
        const payload = await confirmEtcImportSession(etcPreviewPayload.sessionId);
        setEtcPreviewPayload(payload);
        setEtcImported(true);
        setFeedbackMessage("已导入 ETC票据管理");
      } catch (error) {
        setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
      } finally {
        setIsConfirming(false);
      }
      return;
    }
    if (!previewPayload || confirmableFileIds.length === 0) {
      setErrorMessage("没有可确认导入的文件。");
      return;
    }
    setIsConfirming(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, confirmableFileIds);
      await onImported(payload);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
      setIsConfirming(false);
    }
  }

  async function handleConfirm() {
    if (conflictingPreviewFiles.length > 0) {
      setConflictDialogOpen(true);
      return;
    }
    await submitConfirm();
  }

  return (
    <div className="export-center-modal-layer" role="presentation">
      <div
        aria-hidden="true"
        className="export-center-modal-backdrop"
      />
      <section
        aria-labelledby="workbench-import-modal-title"
        aria-modal="true"
        className="export-center-modal workbench-import-modal"
        role="dialog"
      >
        <header className="export-center-modal-header">
          <div>
            <h2 id="workbench-import-modal-title">{title}</h2>
            <p>
              {mode === "bank_transaction"
                ? "上传一个或多个银行流水文件，并在预览前为每个文件选择对应账户。"
                : mode === "etc_invoice"
                  ? "上传一个或多个 ETC zip 文件，先预览，确认后写入 ETC票据管理。"
                : "上传一个或多个发票文件，并在预览前为每个文件选择进项票或销项票。"}
            </p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isConfirming}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body workbench-import-body">
          <label
            className={`workbench-import-dropzone${isDragActive ? " drag-active" : ""}`}
            htmlFor={inputId}
            aria-label={uploadLabel}
            onDragEnter={handleDropzoneDragOver}
            onDragOver={handleDropzoneDragOver}
            onDragLeave={handleDropzoneDragLeave}
            onDrop={handleDropzoneDrop}
          >
            <strong>{uploadLabel}</strong>
            <span>
              {mode === "etc_invoice"
                ? "支持一次选择多个 zip 文件；确认导入前不会写入 ETC票据管理。"
                : "支持一次选择多个 Excel 文件；每个文件完成选择后才能开始预览。"}
            </span>
            <input
              id={inputId}
              multiple
              type="file"
              accept={mode === "etc_invoice" ? ".zip,application/zip" : ".xlsx,.xls"}
              disabled={isPreviewing || isConfirming}
              onChange={(event) => {
                setIsDragActive(false);
                updateFiles(Array.from(event.currentTarget.files ?? []));
                event.currentTarget.value = "";
              }}
            />
          </label>

          {!canUseBankImport ? <div className="state-panel">设置里还没有银行账户映射，请先在“设置”里维护银行。</div> : null}

          {selectedFiles.length > 0 ? (
            <div className="workbench-import-file-list" aria-label="待导入文件">
              {selectedFiles.map((file) => {
                const key = buildSelectedFileKey(file);
                const selection = fileSelections[key] ?? {
                  bankMappingId: "",
                  bankName: "",
                  bankShortName: "",
                  last4: "",
                  invoiceBatchType: "",
                };
                return (
                  <article key={key} className="workbench-import-file-item">
                    <div className="workbench-import-file-main">
                      <strong>{file.name}</strong>
                      <span>{(file.size / 1024).toFixed(1)} KB</span>
                    </div>
                    {mode === "bank_transaction" ? (
                      <label className="import-select-field">
                        <span>对应账户</span>
                        <select
                          aria-label={`对应账户 ${file.name}`}
                          value={selection.bankMappingId}
                          disabled={isPreviewing || isConfirming || bankOptions.length === 0}
                          onChange={(event) => handleSelectionChange(file, "bankMappingId", event.currentTarget.value)}
                        >
                          <option value="">请选择账户</option>
                          {bankOptions.map((bankOption) => (
                            <option key={bankOption.id} value={bankOption.id}>
                              {buildBankAccountOptionLabel(bankOption)}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : mode === "etc_invoice" ? (
                      <div className="import-file-meta">
                        <span>ETC zip</span>
                        <span>确认后导入 ETC票据管理</span>
                      </div>
                    ) : (
                      <label className="import-select-field">
                        <span>票据方向</span>
                        <select
                          aria-label={`票据方向 ${file.name}`}
                          value={selection.invoiceBatchType}
                          disabled={isPreviewing || isConfirming}
                          onChange={(event) => handleSelectionChange(file, "invoiceBatchType", event.currentTarget.value)}
                        >
                          <option value="">请选择票据方向</option>
                          <option value="input_invoice">进项发票</option>
                          <option value="output_invoice">销项发票</option>
                        </select>
                      </label>
                    )}
                    <button className="secondary-button compact" type="button" onClick={() => handleRemoveFile(file)} disabled={isPreviewing || isConfirming}>
                      移除
                    </button>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="detail-state-panel">当前还没有选择文件。</div>
          )}

          {feedbackMessage ? <div className="page-note page-note-success">{feedbackMessage}</div> : null}
          {isPreviewing ? <div className="detail-state-panel">正在预览识别文件...</div> : null}
          {isConfirming ? <div className="detail-state-panel">正在确认导入并刷新关联台...</div> : null}
          {errorMessage ? <div className="state-panel error">{errorMessage}</div> : null}

          {previewPayload ? (
            <section className="workbench-import-preview" aria-label="导入预览结果">
              <div className="export-center-preview-header">
                <h3>预览结果</h3>
                <span>{previewPayload.files.length} 个文件</span>
              </div>
              <div className="workbench-import-preview-list">
                {previewPayload.files.map((file) => (
                  <article key={file.id} className={`workbench-import-preview-item status-${file.status}`}>
                    <header>
                      <strong>{file.fileName}</strong>
                      <span>{statusLabel(file.status)}</span>
                    </header>
                    <div className="import-file-meta">
                      {file.selectedBankName ? <span>{`${file.selectedBankName}${file.selectedBankLast4 ? ` ${file.selectedBankLast4}` : ""}`}</span> : null}
                      <span>{batchTypeLabel(file.batchType)}</span>
                      <span>{file.rowCount} 行</span>
                      <span>新增 {file.successCount}</span>
                      <span>异常 {file.errorCount}</span>
                    </div>
                    <p>{file.message}</p>
                    {file.bankSelectionConflict && file.conflictMessage ? (
                      <p className="import-conflict-message">{file.conflictMessage}</p>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          {etcPreviewPayload ? (
            <section className="workbench-import-preview" aria-label="ETC导入预览结果">
              <div className="export-center-preview-header">
                <h3>预览结果</h3>
                <span>{selectedFiles.length} 个 zip</span>
              </div>
              <div className="stats-row import-session-stats">
                <div className="stat-card">
                  <span>新增</span>
                  <strong>{etcPreviewPayload.imported}</strong>
                </div>
                <div className="stat-card">
                  <span>重复跳过</span>
                  <strong>{etcPreviewPayload.duplicatesSkipped}</strong>
                </div>
                <div className="stat-card">
                  <span>附件补齐</span>
                  <strong>{etcPreviewPayload.attachmentsCompleted}</strong>
                </div>
                <div className="stat-card warn">
                  <span>异常</span>
                  <strong>{etcPreviewPayload.failed}</strong>
                </div>
              </div>
              <div className="workbench-import-preview-list">
                {etcPreviewPayload.items.map((item: EtcImportItem, index) => (
                  <article key={`${item.invoiceNumber || item.fileName}-${index}`} className={`workbench-import-preview-item status-${item.status}`}>
                    <header>
                      <strong>{item.invoiceNumber || "未识别"}</strong>
                      <span>{etcStatusLabel(item.status)}</span>
                    </header>
                    <div className="import-file-meta">
                      <span>{item.fileName || "未识别文件"}</span>
                    </div>
                    <p>{item.reason || "无"}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <footer className="export-center-modal-footer">
          <button className="secondary-button" type="button" onClick={onClose} disabled={isConfirming}>
            取消
          </button>
          <button className="secondary-button" type="button" onClick={handlePreview} disabled={!canPreview}>
            {isPreviewing ? "预览中..." : "开始预览"}
          </button>
          <button className="primary-button" type="button" onClick={handleConfirm} disabled={mode === "etc_invoice" ? !canConfirmEtc : !canConfirm}>
            {isConfirming ? "确认中..." : "确认导入"}
          </button>
        </footer>
      </section>
      {conflictDialogOpen ? (
        <section aria-labelledby="bank-import-conflict-dialog-title" aria-modal="true" className="detail-modal data-reset-dialog import-conflict-dialog" role="dialog">
          <header className="detail-modal-header">
            <div>
              <h3 id="bank-import-conflict-dialog-title">银行账户冲突确认</h3>
              <p>以下文件的系统识别结果与所选账户项不一致。确认后仍会按你选择的账户导入。</p>
            </div>
          </header>
          <div className="detail-modal-body import-conflict-dialog-body">
            {conflictingPreviewFiles.map((file) => (
              <article key={file.id} className="workbench-import-preview-item status-unrecognized_template">
                <header>
                  <strong>{file.fileName}</strong>
                  <span>存在冲突</span>
                </header>
                <div className="import-file-meta">
                  <span>{`${file.selectedBankName ?? "--"} ${file.selectedBankLast4 ?? "--"}`}</span>
                  <span>{`${file.detectedBankName ?? "--"} ${file.detectedLast4 ?? "--"}`}</span>
                </div>
                {file.conflictMessage ? <p>{file.conflictMessage}</p> : null}
              </article>
            ))}
          </div>
          <footer className="detail-modal-actions">
            <button className="secondary-button" type="button" onClick={() => setConflictDialogOpen(false)} disabled={isConfirming}>
              取消
            </button>
            <button className="primary-button" type="button" onClick={() => { void submitConfirm(); }} disabled={isConfirming}>
              {isConfirming ? "确认中..." : conflictConfirmLabel}
            </button>
          </footer>
        </section>
      ) : null}
    </div>
  );
}
