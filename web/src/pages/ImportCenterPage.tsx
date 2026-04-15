import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  confirmImportFiles,
  fetchImportSession,
  fetchImportTemplates,
  previewImportFiles,
  resolveImportApiErrorMessage,
  retryImportFiles,
  revertImportBatch,
} from "../features/imports/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportSessionPayload,
  ImportTemplate,
  MatchingRunSummary,
} from "../features/imports/types";
import { useImportProgress } from "../contexts/ImportProgressContext";

type FileOverrideState = Record<
  string,
  {
    templateCode: string;
    batchType: ImportBatchType | "";
  }
>;

type ImportIntent = "bank_transaction" | "invoice" | "output_invoice" | "input_invoice" | "etc_invoice" | "certified_invoice";

const TEMPLATE_LABELS: Record<string, string> = {
  invoice_export: "发票导出",
  icbc_historydetail: "工商银行流水",
  pingan_transaction_detail: "平安银行流水",
  cmbc_transaction_detail: "民生银行流水",
  ccb_transaction_detail: "建设银行流水",
  ceb_transaction_detail: "光大银行流水",
};

const STATUS_LABELS: Record<string, string> = {
  preview_ready: "待确认",
  preview_ready_with_errors: "待确认",
  unrecognized_template: "无法识别",
  confirmed: "已确认导入",
  skipped: "已跳过",
  reverted: "已撤销",
};

const DECISION_LABELS: Record<string, string> = {
  created: "新增",
  status_updated: "状态更新",
  duplicate_skipped: "重复跳过",
  suspected_duplicate: "疑似重复",
  error: "异常",
};

const BATCH_TYPE_LABELS: Record<ImportBatchType, string> = {
  input_invoice: "进项发票",
  output_invoice: "销项发票",
  bank_transaction: "银行流水",
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

function templateLabel(templateCode?: string | null) {
  if (!templateCode) {
    return "未识别";
  }
  return TEMPLATE_LABELS[templateCode] ?? templateCode;
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

function summarizeSelection(files: ImportFilePreview[], selectedIds: string[]) {
  return files.filter((file) => selectedIds.includes(file.id)).length;
}

function buildOverrideState(payload: ImportSessionPayload): FileOverrideState {
  return Object.fromEntries(
    payload.files.map((file) => [
      file.id,
      {
        templateCode: file.overrideTemplateCode ?? file.templateCode ?? "",
        batchType: file.overrideBatchType ?? file.batchType ?? "",
      },
    ]),
  );
}

function canRetryFile(file: ImportFilePreview) {
  return file.status !== "confirmed";
}

function canSelectFile(file: ImportFilePreview) {
  return file.status === "preview_ready";
}

function isInvoiceTemplate(templateCode: string) {
  return templateCode === "invoice_export";
}

function statusTone(status: string) {
  if (status === "confirmed") {
    return "success";
  }
  if (status === "skipped") {
    return "neutral";
  }
  return "warn";
}

function syncSelection(payload: ImportSessionPayload, currentSelected: string[]) {
  const selectable = new Set(payload.files.filter(canSelectFile).map((file) => file.id));
  return currentSelected.filter((fileId) => selectable.has(fileId));
}

function resolveIntentMeta(intent: string | null) {
  const normalizedIntent = (intent || "").trim() as ImportIntent | "";
  switch (normalizedIntent) {
    case "bank_transaction":
      return {
        title: "银行流水导入",
        description: "批量导入银行流水文件，系统会自动识别模板并进入标准预览、确认导入链路。",
        unsupported: false,
      };
    case "invoice":
      return {
        title: "发票导入",
        description: "导入进项或销项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
      };
    case "output_invoice":
      return {
        title: "销项发票导入",
        description: "导入销项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
      };
    case "input_invoice":
      return {
        title: "进项发票导入",
        description: "导入进项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
      };
    case "etc_invoice":
      return {
        title: "ETC发票导入",
        description: "该入口已预留，后续会接入 ETC 发票的专用识别和导入逻辑。",
        unsupported: true,
      };
    case "certified_invoice":
      return {
        title: "已认证发票导入",
        description: "该入口已预留，后续会接入已认证发票的专用导入逻辑。",
        unsupported: true,
      };
    default:
      return {
        title: "导入中心",
        description: "自动识别发票与银行模板，支持批量上传、逐文件预览、重试改判、确认导入和批次回退。",
        unsupported: false,
      };
  }
}

export default function ImportCenterPage() {
  const [searchParams] = useSearchParams();
  const { setProgress, clearProgress } = useImportProgress();
  const intentMeta = resolveIntentMeta(searchParams.get("intent"));
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewPayload, setPreviewPayload] = useState<ImportSessionPayload | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [expandedFileIds, setExpandedFileIds] = useState<string[]>([]);
  const [fileOverrides, setFileOverrides] = useState<FileOverrideState>({});
  const [templates, setTemplates] = useState<ImportTemplate[]>([]);
  const [matchingRun, setMatchingRun] = useState<MatchingRunSummary | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isConfirmLoading, setIsConfirmLoading] = useState(false);
  const [retryingFileId, setRetryingFileId] = useState<string | null>(null);
  const [revertingBatchId, setRevertingBatchId] = useState<string | null>(null);
  const [isTemplateLoading, setIsTemplateLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [templateErrorMessage, setTemplateErrorMessage] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const headerStatusMessage = errorMessage
    ? null
    : isTemplateLoading
      ? "模板加载中..."
      : isConfirmLoading && previewPayload
        ? `正在确认导入 ${selectedFileIds.length} 个文件...`
        : isPreviewLoading
          ? `正在预览 ${selectedFiles.length} 个文件...`
          : retryingFileId && previewPayload
            ? `正在重新识别 ${previewPayload.files.find((file) => file.id === retryingFileId)?.fileName ?? retryingFileId}...`
            : revertingBatchId
              ? "正在撤销导入批次..."
              : feedbackMessage;

  useEffect(() => {
    let ignore = false;

    async function loadTemplates() {
      setIsTemplateLoading(true);
      try {
        const payload = await fetchImportTemplates();
        if (!ignore) {
          setTemplates(payload);
          setTemplateErrorMessage(null);
        }
      } catch {
        if (!ignore) {
          setTemplateErrorMessage("模板库加载失败，请稍后刷新页面。");
        }
      } finally {
        if (!ignore) {
          setIsTemplateLoading(false);
        }
      }
    }

    void loadTemplates();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (errorMessage) {
      setProgress({ tone: "error", label: errorMessage });
      return;
    }
    if (isConfirmLoading && previewPayload) {
      setProgress({
        tone: "loading",
        label: `正在确认导入 ${selectedFileIds.length} 个文件`,
      });
      return;
    }
    if (isPreviewLoading) {
      setProgress({
        tone: "loading",
        label: `正在预览 ${selectedFiles.length} 个文件`,
      });
      return;
    }
    if (retryingFileId && previewPayload) {
      const currentFile = previewPayload.files.find((file) => file.id === retryingFileId);
      setProgress({
        tone: "loading",
        label: `正在重新识别 ${currentFile?.fileName ?? retryingFileId}`,
      });
      return;
    }
    if (revertingBatchId) {
      setProgress({
        tone: "loading",
        label: "正在撤销导入批次",
      });
      return;
    }
    if (feedbackMessage) {
      setProgress({ tone: "success", label: feedbackMessage });
      return;
    }
    if (selectedFiles.length > 0) {
      setProgress({ tone: "info", label: `已选择 ${selectedFiles.length} 个文件，等待预览` });
      return;
    }
    clearProgress();
  }, [
    clearProgress,
    errorMessage,
    feedbackMessage,
    isConfirmLoading,
    isPreviewLoading,
    previewPayload,
    retryingFileId,
    revertingBatchId,
    selectedFileIds.length,
    selectedFiles.length,
    setProgress,
  ]);

  useEffect(() => () => clearProgress(), [clearProgress]);

  const handleFileChange = (files: FileList | null) => {
    const nextFiles = files ? Array.from(files) : [];
    setSelectedFiles((current) => mergeSelectedFiles(current, nextFiles));
    setFeedbackMessage(null);
    setErrorMessage(null);
  };

  const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    handleFileChange(event.dataTransfer.files);
  };

  const applyPreviewPayload = (payload: ImportSessionPayload, message?: string) => {
    setPreviewPayload(payload);
    setFileOverrides(buildOverrideState(payload));
    setSelectedFileIds((current) => syncSelection(payload, current));
    setExpandedFileIds((current) => {
      if (current.length > 0) {
        return current.filter((fileId) => payload.files.some((file) => file.id === fileId));
      }
      return payload.files.filter((file) => file.rowResults.length > 0).slice(0, 1).map((file) => file.id);
    });
    if (payload.matchingRun) {
      setMatchingRun(payload.matchingRun);
    }
    if (message) {
      setFeedbackMessage(message);
    }
  };

  const handlePreview = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage("请先选择至少一个导入文件。");
      return;
    }
    setIsPreviewLoading(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    try {
      const payload = await previewImportFiles(selectedFiles);
      setSelectedFileIds(payload.files.filter(canSelectFile).map((file) => file.id));
      applyPreviewPayload(payload, `已完成 ${payload.files.length} 个文件的预览识别。`);
      setMatchingRun(null);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "文件预览失败，请稍后重试。"));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!previewPayload || selectedFileIds.length === 0) {
      return;
    }
    setIsConfirmLoading(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, selectedFileIds);
      applyPreviewPayload(
        payload,
        `已确认导入 ${summarizeSelection(payload.files, selectedFileIds)} 个文件，并自动触发匹配闭环。`,
      );
      setSelectedFileIds([]);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
    } finally {
      setIsConfirmLoading(false);
    }
  };

  const handleRetry = async (file: ImportFilePreview) => {
    if (!previewPayload) {
      return;
    }
    setRetryingFileId(file.id);
    setErrorMessage(null);
    try {
      const override = fileOverrides[file.id] ?? {
        templateCode: file.templateCode ?? "",
        batchType: file.batchType ?? "",
      };
      const payload = await retryImportFiles(previewPayload.session.id, [file.id], {
        [file.id]: {
          templateCode: override.templateCode || file.templateCode || undefined,
          batchType:
            isInvoiceTemplate(override.templateCode || file.templateCode || "")
              ? ((override.batchType || file.batchType) as ImportBatchType | undefined)
              : undefined,
        },
      });
      applyPreviewPayload(payload, `已重新识别 ${file.fileName}。`);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "重新识别失败，请稍后重试。"));
    } finally {
      setRetryingFileId(null);
    }
  };

  const handleRevert = async (file: ImportFilePreview) => {
    if (!previewPayload || !file.batchId) {
      return;
    }
    setRevertingBatchId(file.batchId);
    setErrorMessage(null);
    try {
      await revertImportBatch(file.batchId);
      const payload = await fetchImportSession(previewPayload.session.id);
      applyPreviewPayload(payload, `已撤销 ${file.fileName} 对应的导入批次。`);
      if (!payload.files.some((item) => item.status === "confirmed")) {
        setMatchingRun(null);
      }
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "撤销导入失败，请稍后重试。"));
    } finally {
      setRevertingBatchId(null);
    }
  };

  const toggleFileSelection = (fileId: string) => {
    setSelectedFileIds((current) =>
      current.includes(fileId) ? current.filter((item) => item !== fileId) : [...current, fileId],
    );
  };

  const toggleExpanded = (fileId: string) => {
    setExpandedFileIds((current) =>
      current.includes(fileId) ? current.filter((item) => item !== fileId) : [...current, fileId],
    );
  };

  const handleOverrideChange = (
    fileId: string,
    key: "templateCode" | "batchType",
    value: string,
  ) => {
    setFileOverrides((current) => ({
      ...current,
      [fileId]: {
        ...current[fileId],
        [key]: value,
      },
    }));
  };

  return (
    <div className="page-stack import-page">
      <header className="page-header">
        <div>
          <h1>{intentMeta.title}</h1>
          <p>{intentMeta.description}</p>
        </div>
        <div className="page-header-actions">
          {headerStatusMessage ? (
            <div className={feedbackMessage ? "page-note page-note-success" : "page-note page-note-info"}>{headerStatusMessage}</div>
          ) : null}
          <div className="page-note">来源用户：web_finance_user</div>
        </div>
      </header>

      {intentMeta.unsupported ? (
        <div className="state-panel">
          当前入口已保留，但解析与确认导入逻辑尚未接入。后续补齐逻辑后，这里会直接复用同一套预览与批量确认流程。
        </div>
      ) : null}

      <section className="import-template-panel">
        <div className="import-panel-header">
          <div>
            <h2>模板库</h2>
            <p>系统先自动识别；识别失败或票据方向不对时，可在文件卡片里手动改判后重试。</p>
          </div>
          <div className="import-selection-note">
            {isTemplateLoading ? "模板加载中..." : `已加载 ${templates.length} 个模板`}
          </div>
        </div>
        {templateErrorMessage ? <div className="state-panel error">{templateErrorMessage}</div> : null}
        <div className="template-card-grid">
          {templates.map((template) => (
            <article key={template.templateCode} className="template-card">
              <div className="template-card-head">
                <strong>{template.label}</strong>
                <span>{template.recordType === "invoice" ? "发票" : "银行流水"}</span>
              </div>
              <div className="template-card-meta">
                <span>{template.fileExtensions.join(" / ")}</span>
                <span>{template.allowedBatchTypes.map((item) => batchTypeLabel(item)).join(" / ")}</span>
              </div>
              <div className="template-card-hint">
                关键表头：{template.requiredHeaders.slice(0, 4).join("、")}
                {template.requiredHeaders.length > 4 ? "..." : ""}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="import-upload-panel">
        <label
          className="import-dropzone"
          htmlFor="import-file-input"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <span className="import-dropzone-title">拖拽文件到这里，或点击选择文件</span>
          <span className="import-dropzone-meta">支持一次上传多份 `.xlsx / .xls`，系统会自动识别发票与银行模板，并保留原始文件副本。</span>
          <input
            id="import-file-input"
            aria-label="上传文件"
            className="import-file-input"
            multiple
            type="file"
            onChange={(event) => {
              handleFileChange(event.target.files);
              event.currentTarget.value = "";
            }}
          />
        </label>

        <div className="import-toolbar">
          <div className="import-selection-note">
            当前已选择 <strong>{selectedFiles.length}</strong> 个文件
          </div>
          <button
            className="primary-button"
            type="button"
            disabled={intentMeta.unsupported || selectedFiles.length === 0 || isPreviewLoading}
            onClick={handlePreview}
          >
            {isPreviewLoading ? "预览中..." : "开始预览"}
          </button>
        </div>
      </section>

      {errorMessage ? <div className="state-panel error">{errorMessage}</div> : null}

      {matchingRun ? (
        <section className="import-result-panel">
          <div className="import-panel-header">
            <div>
              <h2>导入闭环结果</h2>
              <p>确认导入后已自动触发匹配引擎，工作台回到对应月份会直接刷新导入数据。</p>
            </div>
            <div className="page-note">最近一次触发：{matchingRun.triggeredBy}</div>
          </div>
          <div className="stats-row import-session-stats">
            <div className="stat-card">
              <span>匹配结果</span>
              <strong>{matchingRun.resultCount}</strong>
            </div>
            <div className="stat-card">
              <span>自动匹配</span>
              <strong>{matchingRun.automaticCount}</strong>
            </div>
            <div className="stat-card">
              <span>建议匹配</span>
              <strong>{matchingRun.suggestedCount}</strong>
            </div>
            <div className="stat-card warn">
              <span>人工复核</span>
              <strong>{matchingRun.manualReviewCount}</strong>
            </div>
          </div>
        </section>
      ) : null}

      {previewPayload ? (
        <>
          <section className="stats-row import-session-stats">
            <div className="stat-card">
              <span>会话编号</span>
              <strong>{previewPayload.session.id}</strong>
            </div>
            <div className="stat-card">
              <span>文件数</span>
              <strong>{previewPayload.session.fileCount} 个</strong>
            </div>
            <div className="stat-card warn">
              <span>待确认</span>
              <strong>{summarizeSelection(previewPayload.files, selectedFileIds)} 个</strong>
            </div>
          </section>

          <section className="import-files-panel">
            <div className="import-panel-header">
              <div>
                <h2>文件识别与预览</h2>
                <p>先看模板识别和逐行结果，再决定是否确认入库或手动改判后重试。</p>
              </div>
              <button
                className="primary-button"
                type="button"
                disabled={intentMeta.unsupported || selectedFileIds.length === 0 || isConfirmLoading}
                onClick={handleConfirm}
              >
                {isConfirmLoading ? "确认中..." : "确认导入选中文件"}
              </button>
            </div>

            <div className="import-file-list">
              {previewPayload.files.map((file) => {
                const isExpanded = expandedFileIds.includes(file.id);
                const templateCode = fileOverrides[file.id]?.templateCode || file.templateCode || "";
                const batchType = fileOverrides[file.id]?.batchType || file.batchType || "";

                return (
                  <article key={file.id} className={`import-file-card status-${file.status}`}>
                    <div className="import-file-card-main">
                      <div className="import-file-card-head">
                        <label className="import-checkbox">
                          <input
                            type="checkbox"
                            aria-label={`选择 ${file.fileName}`}
                            checked={selectedFileIds.includes(file.id)}
                            disabled={!canSelectFile(file)}
                            onChange={() => toggleFileSelection(file.id)}
                          />
                          <span>{file.fileName}</span>
                        </label>
                        <span className={`status-chip tone-${statusTone(file.status)}`}>{statusLabel(file.status)}</span>
                      </div>

                      <div className="import-file-meta">
                        <span>{templateLabel(file.templateCode)}</span>
                        <span>{batchTypeLabel(file.batchType)}</span>
                        <span>{file.rowCount} 行</span>
                        <span>新增 {file.successCount}</span>
                        <span>异常 {file.errorCount}</span>
                        {file.batchId ? <span>批次 {file.batchId}</span> : null}
                        {file.storedFilePath ? <span>原文件已留存</span> : null}
                      </div>

                      <div className="import-file-message">{file.message}</div>

                      <div className="import-override-grid">
                        <label className="import-select-field">
                          <span>模板改判</span>
                          <select
                            aria-label={`模板改判 ${file.fileName}`}
                            disabled={!canRetryFile(file)}
                            value={templateCode}
                            onChange={(event) => handleOverrideChange(file.id, "templateCode", event.target.value)}
                          >
                            <option value="">自动识别</option>
                            {templates.map((template) => (
                              <option key={template.templateCode} value={template.templateCode}>
                                {template.label}
                              </option>
                            ))}
                          </select>
                        </label>

                        {isInvoiceTemplate(templateCode) ? (
                          <label className="import-select-field">
                            <span>票据方向</span>
                            <select
                              aria-label={`票据方向 ${file.fileName}`}
                              disabled={!canRetryFile(file)}
                              value={batchType}
                              onChange={(event) => handleOverrideChange(file.id, "batchType", event.target.value)}
                            >
                              <option value="input_invoice">进项发票</option>
                              <option value="output_invoice">销项发票</option>
                            </select>
                          </label>
                        ) : null}
                      </div>

                      <div className="import-file-actions">
                        <button className="secondary-button" type="button" onClick={() => toggleExpanded(file.id)}>
                          {isExpanded ? "收起逐行预览" : "查看逐行预览"}
                        </button>

                        {canRetryFile(file) ? (
                          <button
                            className="secondary-button"
                            type="button"
                            disabled={retryingFileId === file.id}
                            aria-label={`重新识别 ${file.fileName}`}
                            onClick={() => void handleRetry(file)}
                          >
                            {retryingFileId === file.id ? "重试中..." : "重新识别"}
                          </button>
                        ) : null}

                        {file.batchId ? (
                          <a
                            className="secondary-button link-button"
                            href={`/imports/batches/${file.batchId}/download`}
                            download
                            aria-label={`下载批次 ${file.id}`}
                          >
                            下载批次
                          </a>
                        ) : null}

                        {file.batchId && file.status === "confirmed" ? (
                          <button
                            className="secondary-button danger-button"
                            type="button"
                            disabled={revertingBatchId === file.batchId}
                            aria-label={`撤销导入 ${file.id}`}
                            onClick={() => void handleRevert(file)}
                          >
                            {revertingBatchId === file.batchId ? "撤销中..." : "撤销导入"}
                          </button>
                        ) : null}
                      </div>
                    </div>

                    {isExpanded ? (
                      <div className="import-file-details">
                        {file.rowResults.length > 0 ? (
                          <table className="import-row-table">
                            <thead>
                              <tr>
                                <th>行号</th>
                                <th>类型</th>
                                <th>判定</th>
                                <th>原因</th>
                              </tr>
                            </thead>
                            <tbody>
                              {file.rowResults.slice(0, 8).map((row) => (
                                <tr key={row.id}>
                                  <td>{row.rowNo}</td>
                                  <td>{row.sourceRecordType}</td>
                                  <td>{DECISION_LABELS[row.decision] ?? row.decision}</td>
                                  <td>{row.decisionReason}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <div className="empty-subpanel">当前文件没有逐行预览结果。</div>
                        )}
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
