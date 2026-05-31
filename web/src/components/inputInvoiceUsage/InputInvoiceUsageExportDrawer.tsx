import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { InputInvoiceUsageExportDownload, InputInvoiceUsageExportPreview } from "../../features/inputInvoiceUsage/types";

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

  const refreshing = preview?.readModelStatus === "refreshing";
  return (
    <Drawer
      anchor="right"
      open={open}
      variant="persistent"
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "进项发票使用情况导出" : undefined,
        role: "presentation",
        sx: { width: { xs: "100%", sm: "min(840px, 54vw)" }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>筛选内容导出</Typography>
            <Typography variant="caption" color="text.secondary">{preview?.scopeLabel || "当前筛选"}</Typography>
          </Box>
          <IconButton aria-label="关闭进项发票使用情况导出" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" spacing={1.25} alignItems="center">
              <CircularProgress aria-label="正在加载导出预览" size={22} />
              <Typography variant="body2" color="text.secondary">正在计算导出范围</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {refreshing ? <Alert severity="info">{preview?.message || "读模型正在刷新，请稍后再导出。"}</Alert> : null}
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
                <Table size="small" aria-label="进项发票使用情况导出样例">
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
                          <TableCell key={`${index}-${column}`}>{row[column] ?? "-"}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            </>
          ) : null}
        </Stack>
        <Divider />
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ p: 2 }}>
          <Button onClick={onClose} disabled={downloading}>关闭</Button>
          <Button variant="contained" onClick={handleDownload} disabled={!preview || loading || downloading || refreshing}>
            {downloading ? "下载中..." : "下载导出"}
          </Button>
        </Stack>
      </Stack>
    </Drawer>
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
