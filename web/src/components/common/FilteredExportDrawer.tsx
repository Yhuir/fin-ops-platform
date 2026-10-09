import { Button } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { validateExportCount, type ExportDownload, type ExportSummary } from "../../features/exports/types";
import AppDrawer from "./AppDrawer";
import "./filtered-export.css";

type Props = {
  title: string;
  unit: string;
  onClose: () => void;
  loadSummary: (signal: AbortSignal) => Promise<ExportSummary>;
  download: () => Promise<ExportDownload>;
};

export default function FilteredExportDrawer({ title, unit, onClose, loadSummary, download }: Props) {
  const [count, setCount] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [completedCount, setCompletedCount] = useState<number | null>(null);
  const downloadingRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setCount(null); setError("");
    loadSummary(controller.signal).then(summary => {
      if (!controller.signal.aborted) setCount(validateExportCount(summary.rowCount));
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "导出数量查询失败");
    });
    return () => controller.abort();
  }, [loadSummary, attempt]);

  async function handleExport() {
    if (downloadingRef.current) return;
    if (count === null) {
      if (error) setAttempt(current => current + 1);
      return;
    }
    if (count === 0) return;
    downloadingRef.current = true;
    setDownloading(true); setError(""); setCompletedCount(null);
    try {
      const result = await download();
      const actualCount = validateExportCount(result.count);
      if (!mountedRef.current) return;
      const url = URL.createObjectURL(result.blob);
      try {
        const link = document.createElement("a");
        link.href = url; link.download = result.fileName; link.rel = "noopener";
        document.body.appendChild(link); link.click(); link.remove();
      } finally {
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      setCount(actualCount);
      setCompletedCount(actualCount);
    } catch (reason) {
      if (mountedRef.current) setError(reason instanceof Error ? reason.message : "导出失败");
    } finally {
      downloadingRef.current = false;
      if (mountedRef.current) setDownloading(false);
    }
  }

  return <AppDrawer open title={title} closeLabel={`关闭${title}`} width="min(440px, 100vw)"
    closeDisabled={downloading} ariaBusy={downloading || (count === null && !error)} onClose={onClose} className="filtered-export-drawer"
    footer={<div className="filtered-export-footer"><Button variant="primary" isPending={downloading}
      isDisabled={downloading || count === 0 || (count === null && !error)} onPress={handleExport}>
      {downloading ? "正在导出…" : error ? "重试" : "导出"}
    </Button></div>}>
    <div className="filtered-export-content">
      <p className="filtered-export-count" role="status">
        {completedCount !== null ? `已导出 ${completedCount.toLocaleString()} ${unit}`
          : count === null ? error ? "导出数量暂不可用" : "正在统计…"
          : count === 0 ? "当前筛选范围没有可导出的数据" : `即将导出 ${count.toLocaleString()} ${unit}`}
      </p>
      {error ? <div role="alert">{error}</div> : null}
    </div>
  </AppDrawer>;
}
