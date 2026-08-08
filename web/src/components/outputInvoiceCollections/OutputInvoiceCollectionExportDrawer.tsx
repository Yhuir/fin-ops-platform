import { Button } from "@heroui/react";
import { useEffect, useState } from "react";

import type {
  OutputInvoiceCollectionExportDownload,
  OutputInvoiceCollectionExportPreview,
} from "../../features/outputInvoiceCollections/types";
import AppDrawer from "../common/AppDrawer";

type OutputInvoiceCollectionExportDrawerProps = {
  open: boolean;
  loadPreview: () => Promise<OutputInvoiceCollectionExportPreview>;
  downloadExport: () => Promise<OutputInvoiceCollectionExportDownload>;
  onClose: () => void;
};

export default function OutputInvoiceCollectionExportDrawer({
  open,
  loadPreview,
  downloadExport,
  onClose,
}: OutputInvoiceCollectionExportDrawerProps) {
  const [preview, setPreview] = useState<OutputInvoiceCollectionExportPreview | null>(null);
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
      className="output-invoice-collections-export-drawer"
      closeLabel="关闭销项发票收款情况导出"
      footer={(
        <>
          <Button className="output-invoice-collections-button" isDisabled={downloading} onPress={onClose} size="sm" variant="secondary">
            取消
          </Button>
          <Button
            className="output-invoice-collections-button output-invoice-collections-button--primary"
            isDisabled={!preview || loading || downloading}
            isPending={downloading}
            onPress={handleDownload}
            size="sm"
            variant="primary"
          >
            下载导出
          </Button>
        </>
      )}
      open={open}
      title="筛选内容导出"
      width="min(840px, 100vw)"
      onClose={onClose}
    >
      <div aria-label={open ? "销项发票收款情况导出" : undefined} className="output-invoice-collections-drawer-body">
        {loading ? (
          <div className="output-invoice-collections-drawer-loading" role="status">
            <span aria-label="正在加载导出预览" className="output-invoice-collections-drawer-spinner" role="progressbar" />
            <span>正在计算导出范围</span>
          </div>
        ) : null}
        {error ? <div className="output-invoice-collections-alert" role="alert">{error}</div> : null}
        {downloadedFileName ? <div className="output-invoice-collections-alert" role="status">已生成 {downloadedFileName}</div> : null}
        {preview ? (
          <>
            <section className="output-invoice-collections-export-summary">
              <h3>预计导出 {preview.rowCount.toLocaleString("en-US")} 行</h3>
              <p>{preview.fileName}</p>
            </section>
            <section className="output-invoice-collections-export-sample">
              <table aria-label="销项发票收款情况导出样例" className="output-invoice-collections-simple-table">
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
