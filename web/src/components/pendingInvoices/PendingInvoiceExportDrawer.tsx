import { useEffect, useState } from "react";

import type { PendingInvoiceExportDownload, PendingInvoiceExportPreview } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceExportDrawerProps = {
  open: boolean;
  loadPreview: () => Promise<PendingInvoiceExportPreview>;
  downloadExport: () => Promise<PendingInvoiceExportDownload>;
  onClose: () => void;
};

export default function PendingInvoiceExportDrawer({
  open,
  loadPreview,
  downloadExport,
  onClose,
}: PendingInvoiceExportDrawerProps) {
  const [preview, setPreview] = useState<PendingInvoiceExportPreview | null>(null);
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
    <PendingInvoiceDrawerFrame
      closeLabel="关闭导出抽屉"
      footer={(
        <div className="pending-invoice-drawer-actions">
          <button className="pending-invoices-button" disabled={downloading} onClick={onClose} type="button">关闭</button>
          <button
            className="pending-invoices-button pending-invoices-button--primary"
            disabled={!preview || loading || downloading}
            onClick={handleDownload}
            type="button"
          >
            下载导出
          </button>
        </div>
      )}
      onClose={onClose}
      open={open}
      subtitle={preview?.scopeLabel}
      title="导出预览"
    >
      {loading ? <LoadingMessage label="正在加载导出预览" text="正在计算导出范围" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {downloadedFileName ? <StatusMessage tone="success">{`已生成 ${downloadedFileName}`}</StatusMessage> : null}
      {preview ? (
        <>
          <section className="pending-invoice-panel">
            <h3 className="pending-invoice-panel__title">预计导出 {preview.rowCount.toLocaleString("en-US")} 行</h3>
            <p className="pending-invoice-panel__description">{preview.fileName}</p>
          </section>
          <section className="pending-invoice-panel">
            <table aria-label="导出样例" className="pending-invoice-simple-table">
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
                      <td key={`${index}-${column}`}>{row[column] ?? row[toCamel(column)] ?? "-"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function LoadingMessage({ label, text }: { label: string; text: string }) {
  return (
    <div aria-label={label} className="pending-invoice-status-message" role="status">
      <span aria-hidden="true" className="pending-invoice-spinner" />
      <span>{text}</span>
    </div>
  );
}

function StatusMessage({ children, tone }: { children: string; tone: "danger" | "success" | "info" }) {
  return (
    <div className={`pending-invoice-status-message pending-invoice-status-message--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </div>
  );
}

function toCamel(value: string) {
  return value.replace(/_([a-z])/g, (_match, letter: string) => letter.toUpperCase());
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
