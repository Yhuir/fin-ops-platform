import { useEffect, useState } from "react";

import type { InputInvoiceUsageExportDownload, InputInvoiceUsageExportPreview } from "../../features/inputInvoiceUsage/types";
import AppDrawer from "../common/AppDrawer";

type InputInvoiceUsageExportDrawerProps = {
  open: boolean;
  loadPreview: () => Promise<InputInvoiceUsageExportPreview>;
  downloadExport: () => Promise<InputInvoiceUsageExportDownload>;
  onClose: () => void;
};

export default function InputInvoiceUsageExportDrawer({
  open,
  loadPreview,
  downloadExport,
  onClose,
}: InputInvoiceUsageExportDrawerProps) {
  const [preview, setPreview] = useState<InputInvoiceUsageExportPreview | null>(null);
  const [downloadedFileName, setDownloadedFileName] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setDownloadedFileName("");
      setLoading(false);
      setDownloading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadPreview()
      .then((payload) => {
        if (active) {
          setPreview(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "导出预览加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadPreview, open]);

  async function handleDownload() {
    if (downloading) {
      return;
    }
    setDownloading(true);
    setError(null);
    try {
      const result = await downloadExport();
      triggerDownload(result.blob, result.fileName);
      setDownloadedFileName(result.fileName);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出下载失败");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <AppDrawer
      className="input-invoice-usage-export-drawer"
      closeLabel="关闭进项发票使用情况导出"
      footer={(
        <>
          <button className="input-invoice-usage-button" disabled={downloading} onClick={onClose} type="button">
            关闭
          </button>
          <button
            className="input-invoice-usage-button input-invoice-usage-button--primary"
            disabled={!preview || loading || downloading}
            onClick={handleDownload}
            type="button"
          >
            {downloading ? "下载中..." : "下载导出"}
          </button>
        </>
      )}
      open={open}
      subtitle={preview?.scopeLabel || "当前筛选"}
      title="筛选内容导出"
      width="min(840px, 100vw)"
      onClose={onClose}
    >
      <div aria-label={open ? "进项发票使用情况导出" : undefined} className="input-invoice-usage-drawer-body">
        {loading ? (
          <div className="input-invoice-usage-drawer-loading">
            <span aria-label="正在加载导出预览" className="input-invoice-usage-drawer-spinner" role="progressbar" />
            <span>正在计算导出范围</span>
          </div>
        ) : null}
        {error ? <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">{error}</div> : null}
        {downloadedFileName ? <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--success" role="status">已生成 {downloadedFileName}</div> : null}
        {preview ? (
          <>
            <section className="input-invoice-usage-export-summary">
              <h3>预计导出 {preview.rowCount.toLocaleString("en-US")} 行</h3>
              <p>{preview.fileName}</p>
            </section>
            <section className="input-invoice-usage-export-sample">
              <table aria-label="进项发票使用情况导出样例" className="input-invoice-usage-export-table">
                <thead>
                  <tr>
                    {preview.columns.map((column) => (
                      <th key={column} scope="col">{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.sampleRows.length === 0 ? (
                    <tr>
                      <td colSpan={Math.max(1, preview.columns.length)}>暂无样例。</td>
                    </tr>
                  ) : preview.sampleRows.map((row, index) => (
                    <tr key={index}>
                      {preview.columns.map((column) => (
                        <td key={`${index}-${column}`}>{row[column] ?? "-"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function triggerDownload(blob: Blob, fileName: string) {
  if (typeof URL.createObjectURL !== "function") {
    return;
  }
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
