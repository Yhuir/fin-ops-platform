import { useId, useMemo, useState } from "react";

import {
  confirmImportFiles,
  previewImportFiles,
} from "../../features/imports/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportFilePreviewOverride,
  ImportSessionPayload,
} from "../../features/imports/types";

export type WorkbenchImportMode = "bank_transaction" | "invoice" | "etc_invoice";

type WorkbenchImportModalProps = {
  mode: WorkbenchImportMode;
  bankOptions: string[];
  onClose: () => void;
  onImported: (payload: ImportSessionPayload) => Promise<void> | void;
};

type FileSelectionState = Record<
  string,
  {
    bankName: string;
    invoiceBatchType: ImportBatchType | "";
  }
>;

const BANK_TEMPLATE_MATCHERS: Array<{ keyword: string; templateCode: string }> = [
  { keyword: "工商", templateCode: "icbc_historydetail" },
  { keyword: "光大", templateCode: "ceb_transaction_detail" },
  { keyword: "建设", templateCode: "ccb_transaction_detail" },
  { keyword: "民生", templateCode: "cmbc_transaction_detail" },
  { keyword: "平安", templateCode: "pingan_transaction_detail" },
];

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

function resolveBankTemplateCode(bankName: string) {
  return BANK_TEMPLATE_MATCHERS.find((matcher) => bankName.includes(matcher.keyword))?.templateCode;
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
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const title = mode === "bank_transaction" ? "银行流水导入" : mode === "etc_invoice" ? "ETC发票导入" : "发票导入";
  const uploadLabel = mode === "bank_transaction" ? "上传银行流水文件" : mode === "etc_invoice" ? "上传ETC发票文件" : "上传发票文件";
  const canUseBankImport = mode !== "bank_transaction" || bankOptions.length > 0;
  const allFilesConfigured = selectedFiles.length > 0 && selectedFiles.every((file) => {
    const selection = fileSelections[buildSelectedFileKey(file)];
    return mode === "bank_transaction" ? Boolean(selection?.bankName) : Boolean(selection?.invoiceBatchType);
  });
  const canPreview = canUseBankImport && allFilesConfigured && !isPreviewing && !isConfirming;
  const confirmableFileIds = useMemo(
    () => previewPayload?.files.filter(canConfirmFile).map((file) => file.id) ?? [],
    [previewPayload],
  );
  const canConfirm = confirmableFileIds.length > 0 && !isPreviewing && !isConfirming;

  function updateFiles(nextFiles: File[]) {
    setSelectedFiles((current) => mergeSelectedFiles(current, nextFiles));
    setPreviewPayload(null);
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function handleSelectionChange(file: File, field: "bankName" | "invoiceBatchType", value: string) {
    const key = buildSelectedFileKey(file);
    setFileSelections((current) => ({
      ...current,
      [key]: field === "bankName"
        ? {
          bankName: value,
          invoiceBatchType: current[key]?.invoiceBatchType ?? "",
        }
        : {
          bankName: current[key]?.bankName ?? "",
          invoiceBatchType: value as ImportBatchType | "",
        },
    }));
    setPreviewPayload(null);
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
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function buildPreviewOverrides(): ImportFilePreviewOverride[] {
    return selectedFiles.map((file) => {
      const selection = fileSelections[buildSelectedFileKey(file)];
      if (mode === "bank_transaction") {
        const bankName = selection?.bankName ?? "";
        return {
          fileName: file.name,
          templateCode: resolveBankTemplateCode(bankName),
          batchType: "bank_transaction",
          bankName,
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
    if (!canUseBankImport) {
      setErrorMessage("设置里还没有银行账户映射，请先在设置中维护银行。");
      return;
    }
    if (!allFilesConfigured) {
      setErrorMessage(mode === "bank_transaction" ? "请为每个文件选择对应银行。" : "请为每个文件选择进项票或销项票。");
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    try {
      const payload = await previewImportFiles(selectedFiles, "web_finance_user", buildPreviewOverrides());
      setPreviewPayload(payload);
      setFeedbackMessage(`已完成 ${payload.files.length} 个文件的预览识别。`);
    } catch {
      setErrorMessage("文件预览失败，请稍后重试。");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleConfirm() {
    if (!previewPayload || confirmableFileIds.length === 0) {
      setErrorMessage("没有可确认导入的文件。");
      return;
    }
    setIsConfirming(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, confirmableFileIds);
      await onImported(payload);
    } catch {
      setErrorMessage("确认导入失败，请稍后重试。");
      setIsConfirming(false);
    }
  }

  return (
    <div className="export-center-modal-layer" role="presentation">
      <button
        aria-label={`关闭${title}`}
        className="export-center-modal-backdrop"
        type="button"
        onClick={onClose}
        disabled={isConfirming}
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
                ? "上传一个或多个银行流水文件，并在预览前为每个文件选择对应银行。"
                : mode === "etc_invoice"
                  ? "上传一个或多个 ETC 发票文件，并在预览前为每个文件选择进项票或销项票。"
                : "上传一个或多个发票文件，并在预览前为每个文件选择进项票或销项票。"}
            </p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isConfirming}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body workbench-import-body">
          <label className="workbench-import-dropzone" htmlFor={inputId} aria-label={uploadLabel}>
            <strong>{uploadLabel}</strong>
            <span>支持一次选择多个 Excel 文件；每个文件完成选择后才能开始预览。</span>
            <input
              id={inputId}
              multiple
              type="file"
              accept=".xlsx,.xls"
              disabled={isPreviewing || isConfirming}
              onChange={(event) => {
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
                const selection = fileSelections[key] ?? { bankName: "", invoiceBatchType: "" };
                return (
                  <article key={key} className="workbench-import-file-item">
                    <div className="workbench-import-file-main">
                      <strong>{file.name}</strong>
                      <span>{(file.size / 1024).toFixed(1)} KB</span>
                    </div>
                    {mode === "bank_transaction" ? (
                      <label className="import-select-field">
                        <span>对应银行</span>
                        <select
                          aria-label={`对应银行 ${file.name}`}
                          value={selection.bankName}
                          disabled={isPreviewing || isConfirming || bankOptions.length === 0}
                          onChange={(event) => handleSelectionChange(file, "bankName", event.currentTarget.value)}
                        >
                          <option value="">请选择银行</option>
                          {bankOptions.map((bankName) => (
                            <option key={bankName} value={bankName}>
                              {bankName}
                            </option>
                          ))}
                        </select>
                      </label>
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
                      {file.selectedBankName ? <span>{file.selectedBankName}</span> : null}
                      <span>{batchTypeLabel(file.batchType)}</span>
                      <span>{file.rowCount} 行</span>
                      <span>新增 {file.successCount}</span>
                      <span>异常 {file.errorCount}</span>
                    </div>
                    <p>{file.message}</p>
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
          <button className="primary-button" type="button" onClick={handleConfirm} disabled={!canConfirm}>
            {isConfirming ? "确认中..." : "确认导入"}
          </button>
        </footer>
      </section>
    </div>
  );
}
