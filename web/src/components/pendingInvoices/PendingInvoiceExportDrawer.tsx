import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
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
      open={open}
      title="导出预览"
      subtitle={preview?.scopeLabel}
      closeLabel="关闭导出抽屉"
      onClose={onClose}
      footer={(
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button onClick={onClose} disabled={downloading}>关闭</Button>
          <Button variant="contained" onClick={handleDownload} disabled={!preview || loading || downloading}>
            下载导出
          </Button>
        </Stack>
      )}
    >
      {loading ? (
        <Stack direction="row" spacing={1.25} alignItems="center">
          <CircularProgress aria-label="正在加载导出预览" size={22} />
          <Typography variant="body2" color="text.secondary">正在计算导出范围</Typography>
        </Stack>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {downloadedFileName ? <Alert severity="success">已生成 {downloadedFileName}</Alert> : null}
      {preview ? (
        <>
          <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
            <Typography variant="subtitle2" fontWeight={900}>
              预计导出 {preview.rowCount.toLocaleString("en-US")} 行
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {preview.fileName}
            </Typography>
          </Paper>
          <Paper variant="outlined" sx={{ borderRadius: 1 }}>
            <Table size="small" aria-label="导出样例">
              <TableHead>
                <TableRow>
                  {preview.columns.map((column) => (
                    <TableCell key={column}>{column}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {preview.sampleRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={Math.max(1, preview.columns.length)}>暂无样例。</TableCell>
                  </TableRow>
                ) : preview.sampleRows.map((row, index) => (
                  <TableRow key={index}>
                    {preview.columns.map((column) => (
                      <TableCell key={`${index}-${column}`}>{row[column] ?? row[toCamel(column)] ?? "-"}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </>
      ) : null}
    </PendingInvoiceDrawerFrame>
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
