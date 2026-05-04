import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMemo, useState } from "react";

import FileDropzone from "../common/FileDropzone";
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

function isExcelFile(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".xls") || normalizedName.endsWith(".xlsx");
}

export default function CertifiedInvoiceImportModal({
  currentMonth,
  onClose,
  onImported,
}: CertifiedInvoiceImportModalProps) {
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

  function updateSelectedFiles(files: File[]) {
    setSelectedFiles(files);
    setPreviewResult(null);
    setErrorMessage(null);
  }

  function applyDroppedFiles(files: File[]) {
    const validFiles = files.filter(isExcelFile);
    const invalidFiles = files.filter((file) => !isExcelFile(file));
    if (validFiles.length > 0) {
      updateSelectedFiles(validFiles);
    }
    if (invalidFiles.length > 0) {
      if (validFiles.length === 0) {
        setPreviewResult(null);
      }
      setErrorMessage("仅支持 .xls/.xlsx");
    }
  }

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
    <Dialog
      aria-labelledby="certified-invoice-import-modal-title"
      fullWidth
      maxWidth="md"
      open
      onClose={() => {
        if (!isConfirming) {
          onClose();
        }
      }}
    >
      <DialogTitle id="certified-invoice-import-modal-title">
        已认证发票导入
      </DialogTitle>

      <DialogContent className="certified-import-body" dividers>
        <Stack spacing={2}>
          <Typography color="text.secondary" variant="body2">
            在税金抵扣页内完成已认证发票预览、确认导入和页面刷新，不跳转到关联台导入界面。
          </Typography>

          <FileDropzone
            accept=".xlsx,.xls"
            disabled={!canMutateData || isPreviewing || isConfirming}
            errorText={errorMessage}
            helperText={fileHint}
            label="选择已认证发票文件"
            multiple
            onFiles={applyDroppedFiles}
          />

          {!canMutateData ? (
            <Alert severity="info">当前账号仅支持查看和导出，不能导入已认证发票。</Alert>
          ) : null}

          {selectedFiles.length > 0 ? (
            <Stack className="certified-import-file-list" aria-label="已选择文件" spacing={1}>
              {selectedFiles.map((file) => (
                <Paper key={`${file.name}-${file.lastModified}-${file.size}`} className="certified-import-file-item" variant="outlined">
                  <Typography component="strong" fontWeight={800}>
                    {file.name}
                  </Typography>
                  <Typography component="span" color="text.secondary">
                    {(file.size / 1024).toFixed(1)} KB
                  </Typography>
                </Paper>
              ))}
            </Stack>
          ) : (
            <Alert severity="info" variant="outlined">
              当前还没有选择文件。
            </Alert>
          )}

          {isPreviewing ? (
            <Box>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                正在识别已认证发票，请稍候...
              </Typography>
              <LinearProgress />
            </Box>
          ) : null}
          {isConfirming ? (
            <Box>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                正在导入已认证结果并刷新税金抵扣页面...
              </Typography>
              <LinearProgress />
            </Box>
          ) : null}

          {previewResult ? (
            <Paper className="export-center-preview" component="section" aria-label="已认证发票预览结果" variant="outlined">
              <Stack className="export-center-preview-header" direction="row" justifyContent="space-between" alignItems="center">
                <Typography component="h3" variant="subtitle1" fontWeight={800}>
                  预览结果
                </Typography>
                <Chip label={`${previewResult.fileCount} 个文件`} size="small" variant="outlined" />
              </Stack>
              <Stack className="export-center-preview-body" spacing={1.5}>
                <Stack className="export-center-preview-summary certified-import-summary" direction="row" flexWrap="wrap" gap={1}>
                  <Chip color="primary" label={`识别记录 ${previewResult.summary.recognizedCount} 条`} />
                  <Chip label={`匹配计划 ${previewResult.summary.matchedPlanCount} 条`} variant="outlined" />
                  <Chip label={`未进入计划 ${previewResult.summary.outsidePlanCount} 条`} variant="outlined" />
                  <Chip label={`无效记录 ${previewResult.summary.invalidCount} 条`} variant="outlined" />
                </Stack>
                <Stack className="certified-import-preview-files" spacing={1}>
                  {previewResult.files.map((file) => (
                    <Paper key={file.id} className="certified-import-preview-file" component="section" variant="outlined">
                      <Stack className="certified-import-preview-file-header" direction="row" justifyContent="space-between" alignItems="center">
                        <Typography component="strong" fontWeight={800}>
                          {file.fileName}
                        </Typography>
                        <Chip label={file.month} size="small" variant="outlined" />
                      </Stack>
                      <Stack className="certified-import-preview-file-meta" direction="row" flexWrap="wrap" gap={1}>
                        <Typography component="span">识别 {file.recognizedCount} 条</Typography>
                        <Typography component="span">匹配计划 {file.matchedPlanCount} 条</Typography>
                        <Typography component="span">未进入计划 {file.outsidePlanCount} 条</Typography>
                        <Typography component="span">无效 {file.invalidCount} 条</Typography>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
              </Stack>
            </Paper>
          ) : null}
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button type="button" onClick={onClose} disabled={isConfirming}>
          取消
        </Button>
        <Button type="button" onClick={handlePreview} disabled={!canPreview} variant="outlined">
          预览识别结果
        </Button>
        <Button type="button" onClick={handleConfirm} disabled={!canConfirm} variant="contained">
          确认导入
        </Button>
      </DialogActions>
    </Dialog>
  );
}
