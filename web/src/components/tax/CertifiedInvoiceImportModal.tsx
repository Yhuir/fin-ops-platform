import { useId, useState } from "react";

type CertifiedInvoiceImportModalProps = {
  onClose: () => void;
};

export default function CertifiedInvoiceImportModal({ onClose }: CertifiedInvoiceImportModalProps) {
  const inputId = useId();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  return (
    <div className="export-center-modal-layer" role="presentation">
      <button aria-label="关闭已认证发票导入" className="export-center-modal-backdrop" type="button" onClick={onClose} />
      <section
        aria-labelledby="certified-invoice-import-modal-title"
        aria-modal="true"
        className="export-center-modal certified-import-modal"
        role="dialog"
      >
        <header className="export-center-modal-header">
          <div>
            <h2 id="certified-invoice-import-modal-title">已认证发票导入</h2>
            <p>税金抵扣页内的专用导入窗口。后续真实识别与回写逻辑会直接接在这里，不再跳转到关联台导入界面。</p>
          </div>
          <button className="secondary-button" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="export-center-modal-body certified-import-body">
          <label className="certified-import-dropzone" htmlFor={inputId}>
            <strong>选择已认证发票文件</strong>
            <span>支持一次选择多个 Excel 文件，当前先保留页内入口与文件清单展示。</span>
            <input
              id={inputId}
              multiple
              type="file"
              accept=".xlsx,.xls"
              onChange={(event) => setSelectedFiles(Array.from(event.currentTarget.files ?? []))}
            />
          </label>

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

          <div className="detail-state-panel">
            当前版本先把已认证发票导入收口到税金抵扣页内。后续接入专用解析逻辑后，会在这里完成识别、匹配和页面刷新。
          </div>
        </div>
      </section>
    </div>
  );
}
