import ArrowBackOutlinedIcon from "@mui/icons-material/ArrowBackOutlined";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { type DragEvent, useEffect, useId, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import PageScaffold from "../common/PageScaffold";
import {
  confirmImportFiles,
  previewImportFiles,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import { confirmEtcImportSession, previewEtcZipFiles } from "../../features/etc/api";
import { fetchWorkbenchSettings, fetchWorkbenchWithProgress } from "../../features/workbench/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportFilePreviewOverride,
  ImportSessionPayload,
} from "../../features/imports/types";
import type { EtcImportItem, EtcImportPreviewResult } from "../../features/etc/types";
import type { BankAccountMapping } from "../../features/workbench/types";
import { useImportProgress } from "../../contexts/ImportProgressContext";
import type { ImportWorkflowMode } from "../../features/imports/importRoutes";

type ImportWorkflowPageProps = {
  mode: ImportWorkflowMode;
};

type FileSelectionState = Record<
  string,
  {
    bankMappingId: string;
    bankName: string;
    bankShortName: string;
    last4: string;
    invoiceBatchType: ImportBatchType | "";
  }
>;

type ImportFilePreviewRow = ImportFilePreview & {
  accountLabel: string;
  batchTypeLabel: string;
};

type EtcPreviewRow = EtcImportItem & {
  id: string;
  statusLabel: string;
};

const WORKBENCH_VIEW_MONTH = "all";

const BATCH_TYPE_LABELS: Record<ImportBatchType, string> = {
  input_invoice: "进项发票",
  output_invoice: "销项发票",
  bank_transaction: "银行流水",
};

const STATUS_LABELS: Record<string, string> = {
  preview_ready: "待确认",
  preview_ready_with_errors: "待确认",
  unrecognized_template: "无法识别",
  confirmed: "已确认导入",
  skipped: "已跳过",
  reverted: "已撤销",
};

const ETC_IMPORT_STATUS_LABELS: Record<string, string> = {
  imported: "新增",
  created: "新增",
  duplicate_skipped: "重复跳过",
  attachment_completed: "附件补齐",
  failed: "异常",
};

const TITLES: Record<ImportWorkflowMode, string> = {
  bank_transaction: "银行流水导入",
  invoice: "发票导入",
  etc_invoice: "ETC发票导入",
};

const UPLOAD_LABELS: Record<ImportWorkflowMode, string> = {
  bank_transaction: "上传银行流水文件",
  invoice: "上传发票文件",
  etc_invoice: "上传ETC zip",
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

function isExcelFile(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".xls") || normalizedName.endsWith(".xlsx");
}

function isZipFile(file: File) {
  return file.name.toLowerCase().endsWith(".zip");
}

function canConfirmFile(file: ImportFilePreview) {
  return file.status === "preview_ready";
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

function etcStatusLabel(status: string) {
  return ETC_IMPORT_STATUS_LABELS[status] ?? status;
}

function formatEtcRejectedMessage(count: number) {
  return `ETC发票导入仅支持 zip 文件，已拒绝 ${count} 个非 zip 文件。`;
}

function formatFileSize(file: File) {
  if (file.size >= 1024 * 1024) {
    return `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(file.size / 1024).toFixed(1)} KB`;
}

function buildBankAccountOptionLabel(bankOption: BankAccountMapping) {
  return `${bankOption.bankName} ${bankOption.last4}`.trim();
}

function formatSelectedBankAccountLabel(file: Pick<ImportFilePreview, "selectedBankName" | "selectedBankLast4">) {
  return `${file.selectedBankName ?? ""} ${file.selectedBankLast4 ?? ""}`.trim();
}

const importGridSx = {
  border: "1px solid #d5dde8",
  color: "#1f2937",
  "--DataGrid-overlayHeight": "220px",
  "& .MuiDataGrid-columnHeaders": {
    backgroundColor: "#14263f",
    color: "#f8fafc",
    borderBottom: "1px solid #d5dde8",
  },
  "& .MuiDataGrid-columnHeaderTitle": {
    fontWeight: 800,
  },
  "& .MuiDataGrid-cell": {
    alignItems: "center",
    borderColor: "#e5eaf2",
  },
  "& .MuiDataGrid-row:hover": {
    backgroundColor: "#f7fafc",
  },
} as const;

export default function ImportWorkflowPage({ mode }: ImportWorkflowPageProps) {
  const inputId = useId();
  const { setProgress, clearProgress } = useImportProgress();
  const [bankOptions, setBankOptions] = useState<BankAccountMapping[]>([]);
  const [settingsLoading, setSettingsLoading] = useState(mode === "bank_transaction");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileSelections, setFileSelections] = useState<FileSelectionState>({});
  const [previewPayload, setPreviewPayload] = useState<ImportSessionPayload | null>(null);
  const [etcPreviewPayload, setEtcPreviewPayload] = useState<EtcImportPreviewResult | null>(null);
  const [etcImported, setEtcImported] = useState(false);
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const title = TITLES[mode];
  const uploadLabel = UPLOAD_LABELS[mode];

  useEffect(() => {
    const controller = new AbortController();
    if (mode !== "bank_transaction") {
      setSettingsLoading(false);
      setBankOptions([]);
      return () => controller.abort();
    }

    setSettingsLoading(true);
    fetchWorkbenchSettings(controller.signal)
      .then((settings) => {
        setBankOptions(
          [...settings.bankAccountMappings].sort((left, right) => (
            buildBankAccountOptionLabel(left).localeCompare(buildBankAccountOptionLabel(right), "zh-Hans-CN")
          )),
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(resolveImportApiErrorMessage(error, "银行账户映射加载失败。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSettingsLoading(false);
        }
      });

    return () => controller.abort();
  }, [mode]);

  const bankOptionMap = useMemo(
    () => new Map(bankOptions.map((item) => [item.id, item])),
    [bankOptions],
  );

  const canUseBankImport = mode !== "bank_transaction" || bankOptions.length > 0;
  const allFilesConfigured = selectedFiles.length > 0 && selectedFiles.every((file) => {
    if (mode === "etc_invoice") {
      return isZipFile(file);
    }
    const selection = fileSelections[buildSelectedFileKey(file)];
    return mode === "bank_transaction" ? Boolean(selection?.bankMappingId) : Boolean(selection?.invoiceBatchType);
  });
  const canPreview = canUseBankImport && allFilesConfigured && !isPreviewing && !isConfirming && !settingsLoading;
  const confirmableFileIds = useMemo(
    () => previewPayload?.files.filter(canConfirmFile).map((file) => file.id) ?? [],
    [previewPayload],
  );
  const canConfirm = confirmableFileIds.length > 0 && !isPreviewing && !isConfirming;
  const canConfirmEtc = Boolean(etcPreviewPayload?.sessionId) && !etcImported && !isPreviewing && !isConfirming;
  const conflictingPreviewFiles = useMemo(
    () => previewPayload?.files.filter((file) => canConfirmFile(file) && file.bankSelectionConflict) ?? [],
    [previewPayload],
  );
  const conflictConfirmLabel = useMemo(() => {
    const selectedAccountLabel = formatSelectedBankAccountLabel(conflictingPreviewFiles[0] ?? {});
    return selectedAccountLabel
      ? `仍按所选账户 ${selectedAccountLabel} 导入`
      : "仍按所选账户导入";
  }, [conflictingPreviewFiles]);

  const previewRows = useMemo<ImportFilePreviewRow[]>(() => (
    previewPayload?.files.map((file) => ({
      ...file,
      accountLabel: formatSelectedBankAccountLabel(file) || "--",
      batchTypeLabel: batchTypeLabel(file.batchType),
    })) ?? []
  ), [previewPayload]);

  const etcRows = useMemo<EtcPreviewRow[]>(() => (
    etcPreviewPayload?.items.map((item, index) => ({
      ...item,
      id: `${item.invoiceNumber || item.fileName || "etc"}-${index}`,
      statusLabel: etcStatusLabel(item.status),
    })) ?? []
  ), [etcPreviewPayload]);

  const previewColumns = useMemo<GridColDef<ImportFilePreviewRow>[]>(() => [
    { field: "fileName", headerName: "文件", flex: 1.4, minWidth: 220 },
    { field: "status", headerName: "状态", width: 110, valueFormatter: (value) => statusLabel(String(value)) },
    { field: "batchTypeLabel", headerName: "类型", width: 120 },
    { field: "accountLabel", headerName: "账户", width: 160 },
    { field: "rowCount", headerName: "行数", type: "number", width: 90 },
    { field: "successCount", headerName: "新增", type: "number", width: 90 },
    { field: "errorCount", headerName: "异常", type: "number", width: 90 },
    { field: "message", headerName: "消息", flex: 1.6, minWidth: 240 },
  ], []);

  const etcColumns = useMemo<GridColDef<EtcPreviewRow>[]>(() => [
    { field: "invoiceNumber", headerName: "发票号", flex: 1, minWidth: 180 },
    { field: "fileName", headerName: "文件", flex: 1.2, minWidth: 220 },
    { field: "statusLabel", headerName: "状态", width: 120 },
    { field: "reason", headerName: "原因", flex: 1.6, minWidth: 260 },
  ], []);

  function resetPreviewState() {
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcImported(false);
    setConflictDialogOpen(false);
    setFeedbackMessage(null);
    setErrorMessage(null);
  }

  function updateFiles(nextFiles: File[]) {
    setSelectedFiles((current) => mergeSelectedFiles(current, nextFiles));
    resetPreviewState();
  }

  function applyDroppedFiles(files: File[]) {
    const isSupportedFile = mode === "etc_invoice" ? isZipFile : isExcelFile;
    const validFiles = files.filter(isSupportedFile);
    const invalidFiles = files.filter((file) => !isSupportedFile(file));
    if (validFiles.length > 0) {
      updateFiles(validFiles);
    } else if (invalidFiles.length > 0) {
      resetPreviewState();
    }
    if (invalidFiles.length > 0) {
      setErrorMessage(mode === "etc_invoice" ? formatEtcRejectedMessage(invalidFiles.length) : "仅支持 .xls/.xlsx");
    }
  }

  function handleDropzoneDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!isPreviewing && !isConfirming) {
      setIsDragActive(true);
    }
  }

  function handleDropzoneDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setIsDragActive(false);
    }
  }

  function handleDropzoneDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
    if (isPreviewing || isConfirming) {
      return;
    }
    const nextFiles = Array.from(event.dataTransfer.files ?? []);
    if (nextFiles.length > 0) {
      applyDroppedFiles(nextFiles);
    }
  }

  function handleSelectionChange(file: File, field: "bankMappingId" | "invoiceBatchType", value: string) {
    const key = buildSelectedFileKey(file);
    setFileSelections((current) => ({
      ...current,
      [key]: field === "bankMappingId"
        ? (() => {
          const bankOption = bankOptionMap.get(value);
          return {
            bankMappingId: value,
            bankName: bankOption?.bankName ?? "",
            bankShortName: bankOption?.shortName ?? "",
            last4: bankOption?.last4 ?? "",
            invoiceBatchType: current[key]?.invoiceBatchType ?? "",
          };
        })()
        : {
          bankMappingId: current[key]?.bankMappingId ?? "",
          bankName: current[key]?.bankName ?? "",
          bankShortName: current[key]?.bankShortName ?? "",
          last4: current[key]?.last4 ?? "",
          invoiceBatchType: value as ImportBatchType | "",
        },
    }));
    resetPreviewState();
  }

  function handleRemoveFile(file: File) {
    const key = buildSelectedFileKey(file);
    setSelectedFiles((current) => current.filter((item) => buildSelectedFileKey(item) !== key));
    setFileSelections((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    resetPreviewState();
  }

  function handleClearFiles() {
    setSelectedFiles([]);
    setFileSelections({});
    resetPreviewState();
  }

  function buildPreviewOverrides(): ImportFilePreviewOverride[] {
    return selectedFiles.map((file) => {
      const selection = fileSelections[buildSelectedFileKey(file)];
      if (mode === "bank_transaction") {
        return {
          fileName: file.name,
          batchType: "bank_transaction",
          bankMappingId: selection?.bankMappingId ?? "",
          bankName: selection?.bankName ?? "",
          bankShortName: selection?.bankShortName ?? "",
          last4: selection?.last4 ?? "",
        };
      }
      return {
        fileName: file.name,
        templateCode: "invoice_export",
        batchType: selection?.invoiceBatchType || undefined,
      };
    });
  }

  async function handlePreview() {
    if (mode === "etc_invoice") {
      if (selectedFiles.length === 0) {
        setErrorMessage("请先选择至少一个 ETC zip 文件。");
        return;
      }
      if (!selectedFiles.every(isZipFile)) {
        setErrorMessage("ETC发票导入仅支持 zip 文件。");
        return;
      }
      setIsPreviewing(true);
      setErrorMessage(null);
      setFeedbackMessage(null);
      try {
        const payload = await previewEtcZipFiles(selectedFiles);
        setEtcPreviewPayload(payload);
        setEtcImported(false);
        setPreviewPayload(null);
        setFeedbackMessage(`已完成 ${selectedFiles.length} 个 ETC zip 文件预览。`);
      } catch (error) {
        setErrorMessage(resolveImportApiErrorMessage(error, "ETC zip 预览失败，请稍后重试。"));
      } finally {
        setIsPreviewing(false);
      }
      return;
    }

    if (!canUseBankImport) {
      setErrorMessage("设置里还没有银行账户映射，请先在设置中维护银行。");
      return;
    }
    if (!allFilesConfigured) {
      setErrorMessage(mode === "bank_transaction" ? "请为每个文件选择对应账户。" : "请为每个文件选择进项票或销项票。");
      return;
    }
    setIsPreviewing(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    setConflictDialogOpen(false);
    try {
      const payload = await previewImportFiles(selectedFiles, "web_finance_user", buildPreviewOverrides());
      setPreviewPayload(payload);
      setFeedbackMessage(`已完成 ${payload.files.length} 个文件的预览识别。`);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "文件预览失败，请稍后重试。"));
    } finally {
      setIsPreviewing(false);
    }
  }

  async function refreshWorkbenchStatus(payload: ImportSessionPayload) {
    const confirmedCount = payload.files.filter((file) => file.status === "confirmed").length;
    setProgress({ tone: "loading", label: `已导入 ${confirmedCount} 个文件，正在刷新关联台。` });
    try {
      await fetchWorkbenchWithProgress(WORKBENCH_VIEW_MONTH);
      setProgress({ tone: "success", label: `已导入 ${confirmedCount} 个文件。` });
    } catch {
      setProgress({ tone: "error", label: "导入已提交，关联台刷新失败。" });
    }
  }

  async function submitConfirm() {
    if (mode === "etc_invoice") {
      if (!etcPreviewPayload?.sessionId) {
        setErrorMessage("请先预览 ETC zip 文件。");
        return;
      }
      setIsConfirming(true);
      setErrorMessage(null);
      try {
        const payload = await confirmEtcImportSession(etcPreviewPayload.sessionId);
        setEtcImported(true);
        setFeedbackMessage(payload.job ? "已开始后台导入" : "已导入 ETC票据管理");
      } catch (error) {
        setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
      } finally {
        setIsConfirming(false);
      }
      return;
    }

    if (!previewPayload || confirmableFileIds.length === 0) {
      setErrorMessage("没有可确认导入的文件。");
      return;
    }
    setIsConfirming(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, confirmableFileIds);
      if (payload.job) {
        setFeedbackMessage("已开始后台导入");
        return;
      }
      setFeedbackMessage("已确认导入");
      void refreshWorkbenchStatus(payload);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
    } finally {
      setIsConfirming(false);
    }
  }

  async function handleConfirm() {
    if (conflictingPreviewFiles.length > 0) {
      setConflictDialogOpen(true);
      return;
    }
    await submitConfirm();
  }

  return (
    <Box data-testid="import-workflow-page">
      <PageScaffold
        title={title}
        actions={
          <Stack direction="row" spacing={1}>
            <Button component={RouterLink} to="/" variant="outlined" startIcon={<ArrowBackOutlinedIcon />}>
              返回关联台
            </Button>
            <Button type="button" variant="outlined" onClick={handleClearFiles} disabled={selectedFiles.length === 0 || isPreviewing || isConfirming}>
              清空
            </Button>
            <Button type="button" variant="outlined" onClick={handlePreview} disabled={!canPreview}>
              {isPreviewing ? "预览中..." : "开始预览"}
            </Button>
            <Button type="button" variant="contained" onClick={handleConfirm} disabled={mode === "etc_invoice" ? !canConfirmEtc : !canConfirm}>
              {isConfirming ? "确认中..." : "确认导入"}
            </Button>
          </Stack>
        }
      >
        <Stack spacing={2.5}>
          {feedbackMessage ? <Alert severity="success">{feedbackMessage}</Alert> : null}
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          {settingsLoading ? <Alert severity="info">正在加载银行账户映射...</Alert> : null}
          {!settingsLoading && !canUseBankImport ? <Alert severity="warning">设置里还没有银行账户映射，请先在设置中维护银行。</Alert> : null}

          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", lg: "minmax(360px, 0.9fr) minmax(520px, 1.3fr)" },
              gap: 2,
              alignItems: "start",
            }}
          >
            <Paper variant="outlined" sx={{ p: 2, borderColor: "#d5dde8" }}>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography component="h2" variant="h6" fontWeight={800}>文件</Typography>
                  <Chip size="small" label={`已选 ${selectedFiles.length}`} />
                </Stack>

                <Box
                  component="label"
                  htmlFor={inputId}
                  aria-label={uploadLabel}
                  onDragEnter={handleDropzoneDragOver}
                  onDragOver={handleDropzoneDragOver}
                  onDragLeave={handleDropzoneDragLeave}
                  onDrop={handleDropzoneDrop}
                  sx={{
                    display: "grid",
                    placeItems: "center",
                    gap: 1,
                    minHeight: 150,
                    px: 2,
                    py: 3,
                    cursor: isPreviewing || isConfirming ? "not-allowed" : "pointer",
                    border: "1px dashed",
                    borderColor: isDragActive ? "#2563eb" : "#b8c4d5",
                    borderRadius: 2,
                    bgcolor: isDragActive ? "#eff6ff" : "#f8fafc",
                    color: "#334155",
                    textAlign: "center",
                  }}
                >
                  <FileUploadOutlinedIcon />
                  <Typography fontWeight={800}>{uploadLabel}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {mode === "etc_invoice" ? "支持 .zip" : "支持 .xls / .xlsx"}
                  </Typography>
                  <Box
                    id={inputId}
                    component="input"
                    multiple
                    type="file"
                    accept={mode === "etc_invoice" ? ".zip,application/zip" : ".xlsx,.xls"}
                    disabled={isPreviewing || isConfirming}
                    onChange={(event) => {
                      setIsDragActive(false);
                      applyDroppedFiles(Array.from(event.currentTarget.files ?? []));
                      event.currentTarget.value = "";
                    }}
                    sx={{ display: "none" }}
                  />
                </Box>

                {selectedFiles.length > 0 ? (
                  <Stack spacing={1.25} aria-label="待导入文件">
                    {selectedFiles.map((file) => {
                      const key = buildSelectedFileKey(file);
                      const selection = fileSelections[key] ?? {
                        bankMappingId: "",
                        bankName: "",
                        bankShortName: "",
                        last4: "",
                        invoiceBatchType: "",
                      };

                      return (
                        <Paper key={key} variant="outlined" sx={{ p: 1.25, borderColor: "#e1e7ef" }}>
                          <Stack spacing={1.25}>
                            <Stack direction="row" justifyContent="space-between" gap={1}>
                              <Box sx={{ minWidth: 0 }}>
                                <Typography fontWeight={800} noWrap title={file.name}>{file.name}</Typography>
                                <Typography variant="caption" color="text.secondary">{formatFileSize(file)}</Typography>
                              </Box>
                              <Button
                                type="button"
                                size="small"
                                color="error"
                                variant="text"
                                startIcon={<DeleteOutlineOutlinedIcon />}
                                onClick={() => handleRemoveFile(file)}
                                disabled={isPreviewing || isConfirming}
                              >
                                移除
                              </Button>
                            </Stack>

                            {mode === "bank_transaction" ? (
                              <FormControl size="small" fullWidth>
                                <InputLabel id={`${key}-bank-label`}>对应账户</InputLabel>
                                <Select
                                  native
                                  labelId={`${key}-bank-label`}
                                  label="对应账户"
                                  value={selection.bankMappingId}
                                  disabled={isPreviewing || isConfirming || bankOptions.length === 0}
                                  inputProps={{ "aria-label": `对应账户 ${file.name}` }}
                                  onChange={(event) => handleSelectionChange(file, "bankMappingId", event.target.value)}
                                >
                                  <option aria-label="未选择账户" value="" />
                                  {bankOptions.map((bankOption) => (
                                    <option key={bankOption.id} value={bankOption.id}>
                                      {buildBankAccountOptionLabel(bankOption)}
                                    </option>
                                  ))}
                                </Select>
                              </FormControl>
                            ) : mode === "invoice" ? (
                              <FormControl size="small" fullWidth>
                                <InputLabel id={`${key}-invoice-label`}>票据方向</InputLabel>
                                <Select
                                  native
                                  labelId={`${key}-invoice-label`}
                                  label="票据方向"
                                  value={selection.invoiceBatchType}
                                  disabled={isPreviewing || isConfirming}
                                  inputProps={{ "aria-label": `票据方向 ${file.name}` }}
                                  onChange={(event) => handleSelectionChange(file, "invoiceBatchType", event.target.value)}
                                >
                                  <option aria-label="未选择票据方向" value="" />
                                  <option value="input_invoice">进项发票</option>
                                  <option value="output_invoice">销项发票</option>
                                </Select>
                              </FormControl>
                            ) : (
                              <Chip label="ETC zip" size="small" sx={{ alignSelf: "flex-start" }} />
                            )}
                          </Stack>
                        </Paper>
                      );
                    })}
                  </Stack>
                ) : (
                  <Alert severity="info">当前还没有选择文件。</Alert>
                )}
              </Stack>
            </Paper>

            <Paper variant="outlined" sx={{ p: 2, borderColor: "#d5dde8" }}>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography component="h2" variant="h6" fontWeight={800}>预览</Typography>
                  {isPreviewing || isConfirming ? (
                    <Chip size="small" color="primary" label={isPreviewing ? "预览中" : "确认中"} />
                  ) : null}
                </Stack>

                {mode === "etc_invoice" ? (
                  <Stack spacing={1.5}>
                    {etcPreviewPayload ? (
                      <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                        <Typography component="h3" variant="subtitle1" fontWeight={800}>ETC导入预览</Typography>
                        <Chip size="small" label={etcPreviewPayload.sessionId} />
                      </Stack>
                    ) : null}
                    {etcPreviewPayload ? (
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip color="success" label={`新增 ${etcPreviewPayload.imported}`} />
                        <Chip label={`重复跳过 ${etcPreviewPayload.duplicatesSkipped}`} />
                        <Chip color="info" label={`附件补齐 ${etcPreviewPayload.attachmentsCompleted}`} />
                        <Chip color={etcPreviewPayload.failed > 0 ? "warning" : "default"} label={`异常 ${etcPreviewPayload.failed}`} />
                      </Stack>
                    ) : null}
                    <Box sx={{ height: 420, width: "100%" }}>
                      <DataGrid
                        aria-label="ETC导入预览结果"
                        columns={etcColumns}
                        rows={etcRows}
                        loading={isPreviewing}
                        disableRowSelectionOnClick
                        hideFooter
                        showToolbar
                        sx={importGridSx}
                      />
                    </Box>
                  </Stack>
                ) : (
                  <Box sx={{ height: 480, width: "100%" }}>
                    <DataGrid
                      aria-label="导入预览结果"
                      columns={previewColumns}
                      rows={previewRows}
                      loading={isPreviewing}
                      disableRowSelectionOnClick
                      hideFooter
                      showToolbar
                      sx={importGridSx}
                    />
                  </Box>
                )}
              </Stack>
            </Paper>
          </Box>
        </Stack>
      </PageScaffold>

      <Dialog open={conflictDialogOpen} onClose={() => setConflictDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>银行账户冲突确认</DialogTitle>
        <DialogContent>
          <Stack spacing={1.25}>
            <Alert severity="warning">以下文件的系统识别结果与所选账户不一致，确认后仍会按你选择的账户导入。</Alert>
            {conflictingPreviewFiles.map((file) => (
              <Paper key={file.id} variant="outlined" sx={{ p: 1.25 }}>
                <Typography fontWeight={800}>{file.fileName}</Typography>
                <Typography variant="body2" color="text.secondary">
                  所选：{`${file.selectedBankName ?? "--"} ${file.selectedBankLast4 ?? "--"}`} / 识别：{`${file.detectedBankName ?? "--"} ${file.detectedLast4 ?? "--"}`}
                </Typography>
                {file.conflictMessage ? <Typography variant="body2">{file.conflictMessage}</Typography> : null}
              </Paper>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button type="button" onClick={() => setConflictDialogOpen(false)} disabled={isConfirming}>取消</Button>
          <Button type="button" variant="contained" onClick={() => { void submitConfirm(); }} disabled={isConfirming}>
            {isConfirming ? "确认中..." : conflictConfirmLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
