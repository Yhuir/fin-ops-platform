import { useId, useMemo, useState } from "react";

import { useSession } from "../../contexts/SessionContext";
import {
  confirmTaxCertifiedImport,
  previewTaxCertifiedImport,
} from "../../features/tax/api";
import type {
  TaxCertifiedImportConfirmResult,
  TaxCertifiedImportPreviewResult,
} from "../../features/tax/types";

type CertifiedInvoiceImportModalProps = {
  currentMonth: string;
  onClose: () => void;
  onImported: (result: TaxCertifiedImportConfirmResult) => Promise<void> | void;
};

export default function CertifiedInvoiceImportModal({
  currentMonth,
  onClose,
  onImported,
}: CertifiedInvoiceImportModalProps) {
  const inputId = useId();
  const session = useSession();
  const canMutateData =
    session.status === "authenticated" ? session.session.canMutateData : false;
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewResult, setPreviewResult] = useState<TaxCertifiedImportPreviewResult | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canPreview = canMutateData && selectedFiles.length > 0 && !isPreviewing && !isConfirming;
  const canConfirm = canMutateData && previewResult !== null && !isPreviewing && !isConfirming;
  const importedBy =
    session.status === "authenticated" || session.status === "forbidden"
      ? session.session.user.username || session.session.user.displayName || "system"
      : "system";

  const fileHint = useMemo(() => {
    if (selectedFiles.length === 0) {
      return "支持一次选择多个 Excel 文件，先预览识别结果，再确认导入并刷新本页。";
    }
    return `已选择 ${selectedFiles.length} 个文件，当前页面月份为 ${currentMonth}。确认导入后会刷新当前税金抵扣页。`;
  }, [currentMonth, selectedFiles.length]);

  async function handlePreview() {
    if (selectedFiles.length === 0) {
      setErrorMessage("请先选择至少一个已认证发票 Excel 文件。");
      return;
    }
    setErrorMessage(null);
    setIsPreviewing(true);
    try {
      const result = await previewTaxCertifiedImport({
        importedBy,
        files: selectedFiles,
      });
      setPreviewResult(result);
    } catch {
      setErrorMessage("已认证发票预览失败，请稍后重试。");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleConfirm() {
    if (!previewResult) {
      setErrorMessage("请先预览识别结果，再确认导入。");
      return;
    }
    setErrorMessage(null);
    setIsConfirming(true);
    try {
      const result = await confirmTaxCertifiedImport(previewResult.sessionId);
      await onImported(result);
    } catch {
      setErrorMessage("已认证发票导入失败，请稍后重试。");
      setIsConfirming(false);
    }
  }

  return (
    <div className="export-center-modal-layer" role="presentation">
      <button
        aria-label="关闭已认证发票导入"
        className="export-center-modal-backdrop"
        type="button"
        onClick={onClose}
      />
      <section
        aria-labelledby="certified-invoice-import-modal-title"
        aria-modal="true"
        className="export-center-modal certified-import-modal"
        role="dialog"
      >
        <header className="export-center-modal-header">
          <div>
            <h2 id="certified-invoice-import-modal-title">已认证发票导入</h2>
            <p>在税金抵扣页内完成已认证发票预览、确认导入和页面刷新，不跳转到关联台导入界面。</p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose} disabled={isConfirming}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body certified-import-body">
          <label className="certified-import-dropzone" htmlFor={inputId} aria-label="选择已认证发票文件">
            <strong>选择已认证发票文件</strong>
            <span>{fileHint}</span>
            <input
              id={inputId}
              multiple
              type="file"
              accept=".xlsx,.xls"
              disabled={!canMutateData}
              onChange={(event) => {
                setSelectedFiles(Array.from(event.currentTarget.files ?? []));
                setPreviewResult(null);
                setErrorMessage(null);
              }}
            />
          </label>

          {!canMutateData ? <div className="state-panel">当前账号仅支持查看和导出，不能导入已认证发票。</div> : null}

          {selectedFiles.length > 0 ? (
            <div className="certified-import-file-list" aria-label="已选择文件">
              {selectedFiles.map((file) => (
                <div key={`${file.name}-${file.lastModified}-${file.size}`} className="certified-import-file-item">
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024).toFixed(1)} KB</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="detail-state-panel">当前还没有选择文件。</div>
          )}

          {isPreviewing ? <div className="detail-state-panel">正在识别已认证发票，请稍候...</div> : null}
          {isConfirming ? <div className="detail-state-panel">正在导入已认证结果并刷新税金抵扣页面...</div> : null}
          {errorMessage ? <div className="state-panel error">{errorMessage}</div> : null}

          {previewResult ? (
            <section className="export-center-preview" aria-label="已认证发票预览结果">
              <div className="export-center-preview-header">
                <h3>预览结果</h3>
                <span>{previewResult.fileCount} 个文件</span>
              </div>
              <div className="export-center-preview-body">
                <div className="export-center-preview-summary certified-import-summary">
                  <strong>识别记录 {previewResult.summary.recognizedCount} 条</strong>
                  <span>匹配计划 {previewResult.summary.matchedPlanCount} 条</span>
                  <span>未进入计划 {previewResult.summary.outsidePlanCount} 条</span>
                  <span>无效记录 {previewResult.summary.invalidCount} 条</span>
                </div>
                <div className="certified-import-preview-files">
                  {previewResult.files.map((file) => (
                    <section key={file.id} className="certified-import-preview-file">
                      <header className="certified-import-preview-file-header">
                        <strong>{file.fileName}</strong>
                        <span>{file.month}</span>
                      </header>
                      <div className="certified-import-preview-file-meta">
                        <span>识别 {file.recognizedCount} 条</span>
                        <span>匹配计划 {file.matchedPlanCount} 条</span>
                        <span>未进入计划 {file.outsidePlanCount} 条</span>
                        <span>无效 {file.invalidCount} 条</span>
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            </section>
          ) : null}
        </div>

        <footer className="export-center-modal-footer">
          <button className="secondary-button" type="button" onClick={onClose} disabled={isConfirming}>
            取消
          </button>
          <button className="secondary-button" type="button" onClick={handlePreview} disabled={!canPreview}>
            预览识别结果
          </button>
          <button className="primary-button" type="button" onClick={handleConfirm} disabled={!canConfirm}>
            确认导入
          </button>
        </footer>
      </section>
    </div>
  );
}
