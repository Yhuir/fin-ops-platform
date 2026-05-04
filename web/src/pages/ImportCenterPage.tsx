import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import UndoOutlinedIcon from "@mui/icons-material/UndoOutlined";
import Alert from "@mui/material/Alert";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import FileDropzone from "../components/common/FileDropzone";
import PageScaffold from "../components/common/PageScaffold";
import StatePanel from "../components/common/StatePanel";
import {
  confirmImportFiles,
  fetchImportSession,
  fetchImportTemplates,
  previewImportFiles,
  resolveImportApiErrorMessage,
  retryImportFiles,
  revertImportBatch,
} from "../features/imports/api";
import { confirmEtcImportSession, previewEtcZipFiles } from "../features/etc/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportSessionPayload,
  ImportTemplate,
  MatchingRunSummary,
} from "../features/imports/types";
import type { EtcImportConfirmResult, EtcImportItem, EtcImportPreviewResult } from "../features/etc/types";
import { useImportProgress } from "../contexts/ImportProgressContext";

type FileOverrideState = Record<
  string,
  {
    templateCode: string;
    batchType: ImportBatchType | "";
  }
>;

type ImportIntent = "bank_transaction" | "invoice" | "output_invoice" | "input_invoice" | "etc_invoice" | "certified_invoice";

const TEMPLATE_LABELS: Record<string, string> = {
  invoice_export: "发票导出",
  icbc_historydetail: "工商银行流水",
  pingan_transaction_detail: "平安银行流水",
  cmbc_transaction_detail: "民生银行流水",
  ccb_transaction_detail: "建设银行流水",
  ceb_transaction_detail: "光大银行流水",
};

const STATUS_LABELS: Record<string, string> = {
  preview_ready: "待确认",
  preview_ready_with_errors: "待确认",
  unrecognized_template: "无法识别",
  confirmed: "已确认导入",
  skipped: "已跳过",
  reverted: "已撤销",
};

const DECISION_LABELS: Record<string, string> = {
  created: "新增",
  status_updated: "状态更新",
  duplicate_skipped: "重复跳过",
  suspected_duplicate: "疑似重复",
  error: "异常",
};

const ETC_IMPORT_STATUS_LABELS: Record<string, string> = {
  imported: "新增",
  created: "新增",
  duplicate_skipped: "重复跳过",
  attachment_completed: "附件补齐",
  failed: "异常",
};

const BATCH_TYPE_LABELS: Record<ImportBatchType, string> = {
  input_invoice: "进项发票",
  output_invoice: "销项发票",
  bank_transaction: "银行流水",
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

function templateLabel(templateCode?: string | null) {
  if (!templateCode) {
    return "未识别";
  }
  return TEMPLATE_LABELS[templateCode] ?? templateCode;
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

function summarizeSelection(files: ImportFilePreview[], selectedIds: string[]) {
  return files.filter((file) => selectedIds.includes(file.id)).length;
}

function buildOverrideState(payload: ImportSessionPayload): FileOverrideState {
  return Object.fromEntries(
    payload.files.map((file) => [
      file.id,
      {
        templateCode: file.overrideTemplateCode ?? file.templateCode ?? "",
        batchType: file.overrideBatchType ?? file.batchType ?? "",
      },
    ]),
  );
}

function canRetryFile(file: ImportFilePreview) {
  return file.status !== "confirmed";
}

function canSelectFile(file: ImportFilePreview) {
  return file.status === "preview_ready";
}

function isInvoiceTemplate(templateCode: string) {
  return templateCode === "invoice_export";
}

function statusTone(status: string) {
  if (status === "confirmed") {
    return "success";
  }
  if (status === "skipped") {
    return "neutral";
  }
  return "warn";
}

function chipColorFromTone(tone: string): "default" | "success" | "warning" {
  if (tone === "success") {
    return "success";
  }
  if (tone === "warn") {
    return "warning";
  }
  return "default";
}

function syncSelection(payload: ImportSessionPayload, currentSelected: string[]) {
  const selectable = new Set(payload.files.filter(canSelectFile).map((file) => file.id));
  return currentSelected.filter((fileId) => selectable.has(fileId));
}

function resolveIntentMeta(intent: string | null) {
  const normalizedIntent = (intent || "").trim() as ImportIntent | "";
  switch (normalizedIntent) {
    case "bank_transaction":
      return {
        title: "银行流水导入",
        description: "批量导入银行流水文件，系统会自动识别模板并进入标准预览、确认导入链路。",
        unsupported: false,
        isEtcInvoice: false,
      };
    case "invoice":
      return {
        title: "发票导入",
        description: "导入进项或销项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
        isEtcInvoice: false,
      };
    case "output_invoice":
      return {
        title: "销项发票导入",
        description: "导入销项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
        isEtcInvoice: false,
      };
    case "input_invoice":
      return {
        title: "进项发票导入",
        description: "导入进项发票文件。系统会自动识别模板；如果方向识别不对，可在文件卡片中手动改判。",
        unsupported: false,
        isEtcInvoice: false,
      };
    case "etc_invoice":
      return {
        title: "ETC发票导入",
        description: "仅支持 zip，先预览再确认导入 ETC票据管理。",
        unsupported: false,
        isEtcInvoice: true,
      };
    case "certified_invoice":
      return {
        title: "已认证发票导入",
        description: "该入口已预留，后续会接入已认证发票的专用导入逻辑。",
        unsupported: true,
        isEtcInvoice: false,
      };
    default:
      return {
        title: "导入中心",
        description: "自动识别发票与银行模板，支持批量上传、逐文件预览、重试改判、确认导入和批次回退。",
        unsupported: false,
        isEtcInvoice: false,
      };
  }
}

function isZipFile(file: File) {
  return file.name.toLowerCase().endsWith(".zip");
}

function formatEtcRejectedMessage(count: number) {
  return `ETC发票导入仅支持 zip 文件，已拒绝 ${count} 个非 zip 文件。`;
}

function etcStatusLabel(status: string) {
  return ETC_IMPORT_STATUS_LABELS[status] ?? status;
}

function etcStatusTone(status: string) {
  if (status === "imported" || status === "created" || status === "attachment_completed") {
    return "success";
  }
  if (status === "duplicate_skipped") {
    return "neutral";
  }
  return "warn";
}

export default function ImportCenterPage() {
  const [searchParams] = useSearchParams();
  const { setProgress, clearProgress } = useImportProgress();
  const intentMeta = resolveIntentMeta(searchParams.get("intent"));
  const isEtcInvoiceImport = intentMeta.isEtcInvoice;
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewPayload, setPreviewPayload] = useState<ImportSessionPayload | null>(null);
  const [etcPreviewPayload, setEtcPreviewPayload] = useState<EtcImportPreviewResult | null>(null);
  const [etcConfirmPayload, setEtcConfirmPayload] = useState<EtcImportConfirmResult | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [expandedFileIds, setExpandedFileIds] = useState<string[]>([]);
  const [fileOverrides, setFileOverrides] = useState<FileOverrideState>({});
  const [templates, setTemplates] = useState<ImportTemplate[]>([]);
  const [matchingRun, setMatchingRun] = useState<MatchingRunSummary | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isConfirmLoading, setIsConfirmLoading] = useState(false);
  const [retryingFileId, setRetryingFileId] = useState<string | null>(null);
  const [revertingBatchId, setRevertingBatchId] = useState<string | null>(null);
  const [isTemplateLoading, setIsTemplateLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [templateErrorMessage, setTemplateErrorMessage] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const headerStatusMessage = errorMessage
    ? null
    : isTemplateLoading && !isEtcInvoiceImport
      ? "模板加载中..."
      : isConfirmLoading && (previewPayload || etcPreviewPayload)
        ? isEtcInvoiceImport
          ? "正在确认导入 ETC票据管理..."
          : `正在确认导入 ${selectedFileIds.length} 个文件...`
        : isPreviewLoading
          ? `正在预览 ${selectedFiles.length} 个文件...`
          : retryingFileId && previewPayload
            ? `正在重新识别 ${previewPayload.files.find((file) => file.id === retryingFileId)?.fileName ?? retryingFileId}...`
            : revertingBatchId
              ? "正在撤销导入批次..."
              : feedbackMessage;

  useEffect(() => {
    let ignore = false;

    async function loadTemplates() {
      if (isEtcInvoiceImport) {
        setIsTemplateLoading(false);
        setTemplates([]);
        setTemplateErrorMessage(null);
        return;
      }
      setIsTemplateLoading(true);
      try {
        const payload = await fetchImportTemplates();
        if (!ignore) {
          setTemplates(payload);
          setTemplateErrorMessage(null);
        }
      } catch {
        if (!ignore) {
          setTemplateErrorMessage("模板库加载失败，请稍后刷新页面。");
        }
      } finally {
        if (!ignore) {
          setIsTemplateLoading(false);
        }
      }
    }

    void loadTemplates();
    return () => {
      ignore = true;
    };
  }, [isEtcInvoiceImport]);

  useEffect(() => {
    if (errorMessage) {
      setProgress({ tone: "error", label: errorMessage });
      return;
    }
    if (isConfirmLoading && isEtcInvoiceImport && etcPreviewPayload) {
      setProgress({
        tone: "loading",
        label: "正在确认导入 ETC票据管理",
      });
      return;
    }
    if (isConfirmLoading && previewPayload) {
      setProgress({
        tone: "loading",
        label: `正在确认导入 ${selectedFileIds.length} 个文件`,
      });
      return;
    }
    if (isPreviewLoading) {
      setProgress({
        tone: "loading",
        label: `正在预览 ${selectedFiles.length} 个文件`,
      });
      return;
    }
    if (retryingFileId && previewPayload) {
      const currentFile = previewPayload.files.find((file) => file.id === retryingFileId);
      setProgress({
        tone: "loading",
        label: `正在重新识别 ${currentFile?.fileName ?? retryingFileId}`,
      });
      return;
    }
    if (revertingBatchId) {
      setProgress({
        tone: "loading",
        label: "正在撤销导入批次",
      });
      return;
    }
    if (feedbackMessage) {
      setProgress({ tone: "success", label: feedbackMessage });
      return;
    }
    if (selectedFiles.length > 0) {
      setProgress({ tone: "info", label: `已选择 ${selectedFiles.length} 个文件，等待预览` });
      return;
    }
    clearProgress();
  }, [
    clearProgress,
    errorMessage,
    feedbackMessage,
    isConfirmLoading,
    isPreviewLoading,
    etcPreviewPayload,
    isEtcInvoiceImport,
    previewPayload,
    retryingFileId,
    revertingBatchId,
    selectedFileIds.length,
    selectedFiles.length,
    setProgress,
  ]);

  useEffect(() => () => clearProgress(), [clearProgress]);

  const handleFileChange = (files: File[] | FileList | null) => {
    const nextFiles = files ? Array.from(files) : [];
    const acceptedFiles = isEtcInvoiceImport ? nextFiles.filter(isZipFile) : nextFiles;
    const rejectedCount = nextFiles.length - acceptedFiles.length;
    setSelectedFiles((current) => mergeSelectedFiles(current, acceptedFiles));
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcConfirmPayload(null);
    setMatchingRun(null);
    setFeedbackMessage(null);
    setErrorMessage(rejectedCount > 0 ? formatEtcRejectedMessage(rejectedCount) : null);
  };

  const applyPreviewPayload = (payload: ImportSessionPayload, message?: string) => {
    setPreviewPayload(payload);
    setFileOverrides(buildOverrideState(payload));
    setSelectedFileIds((current) => syncSelection(payload, current));
    setExpandedFileIds((current) => {
      if (current.length > 0) {
        return current.filter((fileId) => payload.files.some((file) => file.id === fileId));
      }
      return payload.files.filter((file) => file.rowResults.length > 0).slice(0, 1).map((file) => file.id);
    });
    if (payload.matchingRun) {
      setMatchingRun(payload.matchingRun);
    }
    if (message) {
      setFeedbackMessage(message);
    }
  };

  const handlePreview = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage("请先选择至少一个导入文件。");
      return;
    }
    if (isEtcInvoiceImport && selectedFiles.some((file) => !isZipFile(file))) {
      setErrorMessage("ETC发票导入仅支持 zip 文件。");
      return;
    }
    setIsPreviewLoading(true);
    setErrorMessage(null);
    setFeedbackMessage(null);
    try {
      if (isEtcInvoiceImport) {
        const payload = await previewEtcZipFiles(selectedFiles);
        setEtcPreviewPayload(payload);
        setEtcConfirmPayload(null);
        setPreviewPayload(null);
        setMatchingRun(null);
        setFeedbackMessage(`已完成 ${selectedFiles.length} 个 ETC zip 文件预览。`);
        return;
      }
      const payload = await previewImportFiles(selectedFiles);
      setSelectedFileIds(payload.files.filter(canSelectFile).map((file) => file.id));
      applyPreviewPayload(payload, `已完成 ${payload.files.length} 个文件的预览识别。`);
      setMatchingRun(null);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "文件预览失败，请稍后重试。"));
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (isEtcInvoiceImport) {
      if (!etcPreviewPayload?.sessionId) {
        return;
      }
      setIsConfirmLoading(true);
      setErrorMessage(null);
      try {
        const payload = await confirmEtcImportSession(etcPreviewPayload.sessionId);
        setEtcConfirmPayload(payload);
        setFeedbackMessage(payload.job ? "已开始后台导入" : "已导入 ETC票据管理");
      } catch (error) {
        setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
      } finally {
        setIsConfirmLoading(false);
      }
      return;
    }
    if (!previewPayload || selectedFileIds.length === 0) {
      return;
    }
    setIsConfirmLoading(true);
    setErrorMessage(null);
    try {
      const payload = await confirmImportFiles(previewPayload.session.id, selectedFileIds);
      applyPreviewPayload(
        payload,
        payload.job
          ? `已开始后台导入 ${summarizeSelection(payload.files, selectedFileIds)} 个文件。`
          : `已确认导入 ${summarizeSelection(payload.files, selectedFileIds)} 个文件，并自动触发匹配闭环。`,
      );
      setSelectedFileIds([]);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "确认导入失败，请稍后重试。"));
    } finally {
      setIsConfirmLoading(false);
    }
  };

  const handleRetry = async (file: ImportFilePreview) => {
    if (!previewPayload) {
      return;
    }
    setRetryingFileId(file.id);
    setErrorMessage(null);
    try {
      const override = fileOverrides[file.id] ?? {
        templateCode: file.templateCode ?? "",
        batchType: file.batchType ?? "",
      };
      const payload = await retryImportFiles(previewPayload.session.id, [file.id], {
        [file.id]: {
          templateCode: override.templateCode || file.templateCode || undefined,
          batchType:
            isInvoiceTemplate(override.templateCode || file.templateCode || "")
              ? ((override.batchType || file.batchType) as ImportBatchType | undefined)
              : undefined,
        },
      });
      applyPreviewPayload(payload, `已重新识别 ${file.fileName}。`);
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "重新识别失败，请稍后重试。"));
    } finally {
      setRetryingFileId(null);
    }
  };

  const handleRevert = async (file: ImportFilePreview) => {
    if (!previewPayload || !file.batchId) {
      return;
    }
    setRevertingBatchId(file.batchId);
    setErrorMessage(null);
    try {
      await revertImportBatch(file.batchId);
      const payload = await fetchImportSession(previewPayload.session.id);
      applyPreviewPayload(payload, `已撤销 ${file.fileName} 对应的导入批次。`);
      if (!payload.files.some((item) => item.status === "confirmed")) {
        setMatchingRun(null);
      }
    } catch (error) {
      setErrorMessage(resolveImportApiErrorMessage(error, "撤销导入失败，请稍后重试。"));
    } finally {
      setRevertingBatchId(null);
    }
  };

  const toggleFileSelection = (fileId: string) => {
    setSelectedFileIds((current) =>
      current.includes(fileId) ? current.filter((item) => item !== fileId) : [...current, fileId],
    );
  };

  const toggleExpanded = (fileId: string) => {
    setExpandedFileIds((current) =>
      current.includes(fileId) ? current.filter((item) => item !== fileId) : [...current, fileId],
    );
  };

  const handleOverrideChange = (
    fileId: string,
    key: "templateCode" | "batchType",
    value: string,
  ) => {
    setFileOverrides((current) => ({
      ...current,
      [fileId]: {
        ...current[fileId],
        [key]: value,
      },
    }));
  };

  return (
    <PageScaffold
      className="import-page"
      title={intentMeta.title}
      description={intentMeta.description}
      actions={
        <Stack spacing={1} alignItems={{ xs: "stretch", md: "flex-end" }}>
          {headerStatusMessage ? (
            <Alert severity={feedbackMessage ? "success" : "info"} variant="outlined" sx={{ py: 0.25 }}>
              {headerStatusMessage}
            </Alert>
          ) : null}
          <Chip label="来源用户：web_finance_user" variant="outlined" size="small" />
        </Stack>
      }
    >
      {intentMeta.unsupported ? (
        <StatePanel tone="info">
          当前入口已保留，但解析与确认导入逻辑尚未接入。后续补齐逻辑后，这里会直接复用同一套预览与批量确认流程。
        </StatePanel>
      ) : null}

      {!isEtcInvoiceImport ? (
        <Paper className="import-template-panel" variant="outlined">
          <Stack className="import-panel-header" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} spacing={2}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={800}>
                模板库
              </Typography>
              <Typography color="text.secondary" variant="body2">
                系统先自动识别；识别失败或票据方向不对时，可在文件卡片里手动改判后重试。
              </Typography>
            </Box>
            <Chip label={isTemplateLoading ? "模板加载中..." : `已加载 ${templates.length} 个模板`} size="small" />
          </Stack>
          {templateErrorMessage ? <StatePanel tone="error">{templateErrorMessage}</StatePanel> : null}
          <Box className="template-card-grid">
            {templates.map((template) => (
              <Paper key={template.templateCode} className="template-card" variant="outlined">
                <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                  <Typography fontWeight={800}>{template.label}</Typography>
                  <Chip label={template.recordType === "invoice" ? "发票" : "银行流水"} size="small" />
                </Stack>
                <Stack direction="row" flexWrap="wrap" gap={1}>
                  <Chip label={template.fileExtensions.join(" / ")} size="small" variant="outlined" />
                  <Chip label={template.allowedBatchTypes.map((item) => batchTypeLabel(item)).join(" / ")} size="small" variant="outlined" />
                </Stack>
                <Typography color="text.secondary" variant="caption">
                  关键表头：{template.requiredHeaders.slice(0, 4).join("、")}
                  {template.requiredHeaders.length > 4 ? "..." : ""}
                </Typography>
              </Paper>
            ))}
          </Box>
        </Paper>
      ) : null}

      <Paper className="import-upload-panel" variant="outlined">
        <FileDropzone
          label="上传文件"
          accept={isEtcInvoiceImport ? ".zip,application/zip" : undefined}
          disabled={intentMeta.unsupported}
          helperText={
            isEtcInvoiceImport
              ? "支持一次选择多个 zip 文件；上传后先预览，确认后写入 ETC票据管理。"
              : "支持一次上传多份 .xlsx / .xls，系统会自动识别发票与银行模板，并保留原始文件副本。"
          }
          onFiles={handleFileChange}
        />
        <Stack className="import-toolbar" direction={{ xs: "column", sm: "row" }} alignItems={{ xs: "stretch", sm: "center" }} spacing={2}>
          <Typography className="import-selection-note" color="text.secondary" variant="body2">
            当前已选择 <strong>{selectedFiles.length}</strong> 个文件
          </Typography>
          <Button
            variant="contained"
            type="button"
            disabled={intentMeta.unsupported || selectedFiles.length === 0 || isPreviewLoading}
            onClick={handlePreview}
          >
            {isPreviewLoading ? "预览中..." : "开始预览"}
          </Button>
        </Stack>
      </Paper>

      {errorMessage ? <StatePanel tone="error">{errorMessage}</StatePanel> : null}

      {isEtcInvoiceImport && etcPreviewPayload ? (
        <Paper className="import-files-panel" variant="outlined">
          <Stack className="import-panel-header" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} spacing={2}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={800}>
                ETC导入预览
              </Typography>
              <Typography color="text.secondary" variant="body2">
                确认前请核对摘要和每张发票状态；确认后才会导入 ETC票据管理。
              </Typography>
            </Box>
            <Button
              variant="contained"
              type="button"
              disabled={!etcPreviewPayload.sessionId || isConfirmLoading}
              onClick={handleConfirm}
            >
              {isConfirmLoading ? "确认中..." : "确认导入 ETC票据管理"}
            </Button>
          </Stack>

          {etcConfirmPayload ? (
            <StatePanel tone="success">{etcConfirmPayload.job ? "已开始后台导入" : "已导入 ETC票据管理"}</StatePanel>
          ) : null}

          <Box className="stats-row import-session-stats">
            <Paper className="stat-card" variant="outlined"><span>会话编号</span><strong>{etcPreviewPayload.sessionId}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>新增</span><strong>{etcPreviewPayload.imported}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>重复跳过</span><strong>{etcPreviewPayload.duplicatesSkipped}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>附件补齐</span><strong>{etcPreviewPayload.attachmentsCompleted}</strong></Paper>
            <Paper className="stat-card warn" variant="outlined"><span>异常</span><strong>{etcPreviewPayload.failed}</strong></Paper>
          </Box>

          <TableContainer component={Paper} variant="outlined">
            <Table size="small" aria-label="ETC导入逐行结果">
              <TableHead>
                <TableRow>
                  <TableCell>发票号码</TableCell>
                  <TableCell>文件名</TableCell>
                  <TableCell>状态</TableCell>
                  <TableCell>原因</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {etcPreviewPayload.items.map((item: EtcImportItem, index) => (
                  <TableRow key={`${item.invoiceNumber || item.fileName}-${index}`}>
                    <TableCell>{item.invoiceNumber || "未识别"}</TableCell>
                    <TableCell>{item.fileName || "未识别"}</TableCell>
                    <TableCell>
                      <Chip
                        label={etcStatusLabel(item.status)}
                        size="small"
                        color={chipColorFromTone(etcStatusTone(item.status))}
                        variant={etcStatusTone(item.status) === "neutral" ? "outlined" : "filled"}
                      />
                    </TableCell>
                    <TableCell>{item.reason || "无"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : null}

      {!isEtcInvoiceImport && matchingRun ? (
        <Paper className="import-result-panel" variant="outlined">
          <Stack className="import-panel-header" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} spacing={2}>
            <Box>
              <Typography component="h2" variant="h6" fontWeight={800}>
                导入闭环结果
              </Typography>
              <Typography color="text.secondary" variant="body2">
                确认导入后已自动触发匹配引擎，工作台回到对应月份会直接刷新导入数据。
              </Typography>
            </Box>
            <Chip label={`最近一次触发：${matchingRun.triggeredBy}`} size="small" variant="outlined" />
          </Stack>
          <Box className="stats-row import-session-stats">
            <Paper className="stat-card" variant="outlined"><span>匹配结果</span><strong>{matchingRun.resultCount}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>自动匹配</span><strong>{matchingRun.automaticCount}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>建议匹配</span><strong>{matchingRun.suggestedCount}</strong></Paper>
            <Paper className="stat-card warn" variant="outlined"><span>人工复核</span><strong>{matchingRun.manualReviewCount}</strong></Paper>
          </Box>
        </Paper>
      ) : null}

      {!isEtcInvoiceImport && previewPayload ? (
        <>
          <Box className="stats-row import-session-stats">
            <Paper className="stat-card" variant="outlined"><span>会话编号</span><strong>{previewPayload.session.id}</strong></Paper>
            <Paper className="stat-card" variant="outlined"><span>文件数</span><strong>{previewPayload.session.fileCount} 个</strong></Paper>
            <Paper className="stat-card warn" variant="outlined"><span>待确认</span><strong>{summarizeSelection(previewPayload.files, selectedFileIds)} 个</strong></Paper>
          </Box>

          <Paper className="import-files-panel" variant="outlined">
            <Stack className="import-panel-header" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} spacing={2}>
              <Box>
                <Typography component="h2" variant="h6" fontWeight={800}>
                  文件识别与预览
                </Typography>
                <Typography color="text.secondary" variant="body2">
                  先看模板识别和逐行结果，再决定是否确认入库或手动改判后重试。
                </Typography>
              </Box>
              <Button
                variant="contained"
                type="button"
                disabled={intentMeta.unsupported || selectedFileIds.length === 0 || isConfirmLoading}
                onClick={handleConfirm}
              >
                {isConfirmLoading ? "确认中..." : "确认导入选中文件"}
              </Button>
            </Stack>

            <Stack className="import-file-list" spacing={1.5}>
              {previewPayload.files.map((file) => {
                const isExpanded = expandedFileIds.includes(file.id);
                const templateCode = fileOverrides[file.id]?.templateCode || file.templateCode || "";
                const batchType = fileOverrides[file.id]?.batchType || file.batchType || "";
                const templateSelectId = `template-${file.id}`;
                const batchTypeSelectId = `batch-type-${file.id}`;

                return (
                  <Accordion
                    key={file.id}
                    className={`import-file-card status-${file.status}`}
                    expanded={isExpanded}
                    onChange={() => toggleExpanded(file.id)}
                    disableGutters
                  >
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Stack className="import-file-card-head" direction={{ xs: "column", md: "row" }} alignItems={{ xs: "stretch", md: "center" }} spacing={1.5} sx={{ width: "100%" }}>
                        <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 0 }}>
                          <Checkbox
                            inputProps={{ "aria-label": `选择 ${file.fileName}` }}
                            checked={selectedFileIds.includes(file.id)}
                            disabled={!canSelectFile(file)}
                            onClick={(event) => event.stopPropagation()}
                            onFocus={(event) => event.stopPropagation()}
                            onChange={() => toggleFileSelection(file.id)}
                          />
                          <Typography fontWeight={800} noWrap title={file.fileName}>
                            {file.fileName}
                          </Typography>
                        </Stack>
                        <Chip
                          label={statusLabel(file.status)}
                          size="small"
                          color={chipColorFromTone(statusTone(file.status))}
                          variant={statusTone(file.status) === "neutral" ? "outlined" : "filled"}
                        />
                      </Stack>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={1.5}>
                        <Stack className="import-file-meta" direction="row" flexWrap="wrap" gap={1}>
                          <Chip label={templateLabel(file.templateCode)} size="small" />
                          <Chip label={batchTypeLabel(file.batchType)} size="small" variant="outlined" />
                          <Chip label={`${file.rowCount} 行`} size="small" variant="outlined" />
                          <Chip label={`新增 ${file.successCount}`} size="small" variant="outlined" />
                          <Chip label={`异常 ${file.errorCount}`} size="small" color={file.errorCount > 0 ? "warning" : "default"} variant="outlined" />
                          {file.batchId ? <Chip label={`批次 ${file.batchId}`} size="small" variant="outlined" /> : null}
                          {file.storedFilePath ? <Chip label="原文件已留存" size="small" color="success" variant="outlined" /> : null}
                        </Stack>

                        <Typography color="text.secondary" variant="body2">
                          {file.message}
                        </Typography>

                        <Box className="import-override-grid">
                          <FormControl size="small" fullWidth disabled={!canRetryFile(file)}>
                            <InputLabel htmlFor={templateSelectId}>模板改判 {file.fileName}</InputLabel>
                            <Select
                              native
                              label={`模板改判 ${file.fileName}`}
                              value={templateCode}
                              inputProps={{ id: templateSelectId, "aria-label": `模板改判 ${file.fileName}` }}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => handleOverrideChange(file.id, "templateCode", String(event.target.value))}
                            >
                              <option value="">自动识别</option>
                              {templates.map((template) => (
                                <option key={template.templateCode} value={template.templateCode}>
                                  {template.label}
                                </option>
                              ))}
                            </Select>
                          </FormControl>

                          {isInvoiceTemplate(templateCode) ? (
                            <FormControl size="small" fullWidth disabled={!canRetryFile(file)}>
                              <InputLabel htmlFor={batchTypeSelectId}>票据方向 {file.fileName}</InputLabel>
                              <Select
                                native
                                label={`票据方向 ${file.fileName}`}
                                value={batchType}
                                inputProps={{ id: batchTypeSelectId, "aria-label": `票据方向 ${file.fileName}` }}
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) => handleOverrideChange(file.id, "batchType", String(event.target.value))}
                              >
                                <option value="input_invoice">进项发票</option>
                                <option value="output_invoice">销项发票</option>
                              </Select>
                            </FormControl>
                          ) : null}
                        </Box>

                        <Stack className="import-file-actions" direction="row" flexWrap="wrap" gap={1}>
                          {canRetryFile(file) ? (
                            <Button
                              variant="outlined"
                              type="button"
                              startIcon={<ReplayOutlinedIcon />}
                              disabled={retryingFileId === file.id}
                              aria-label={`重新识别 ${file.fileName}`}
                              onClick={() => void handleRetry(file)}
                            >
                              {retryingFileId === file.id ? "重试中..." : "重新识别"}
                            </Button>
                          ) : null}

                          {file.batchId ? (
                            <Button
                              variant="outlined"
                              component="a"
                              href={`/imports/batches/${file.batchId}/download`}
                              download
                              aria-label={`下载批次 ${file.id}`}
                            >
                              下载批次
                            </Button>
                          ) : null}

                          {file.batchId && file.status === "confirmed" ? (
                            <Button
                              variant="outlined"
                              color="error"
                              type="button"
                              startIcon={<UndoOutlinedIcon />}
                              disabled={revertingBatchId === file.batchId}
                              aria-label={`撤销导入 ${file.id}`}
                              onClick={() => void handleRevert(file)}
                            >
                              {revertingBatchId === file.batchId ? "撤销中..." : "撤销导入"}
                            </Button>
                          ) : null}
                        </Stack>

                        <Divider />

                        {file.rowResults.length > 0 ? (
                          <TableContainer component={Paper} variant="outlined">
                            <Table size="small" aria-label={`逐行预览 ${file.fileName}`}>
                              <TableHead>
                                <TableRow>
                                  <TableCell>行号</TableCell>
                                  <TableCell>类型</TableCell>
                                  <TableCell>判定</TableCell>
                                  <TableCell>原因</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {file.rowResults.slice(0, 8).map((row) => (
                                  <TableRow key={row.id}>
                                    <TableCell>{row.rowNo}</TableCell>
                                    <TableCell>{row.sourceRecordType}</TableCell>
                                    <TableCell>{DECISION_LABELS[row.decision] ?? row.decision}</TableCell>
                                    <TableCell>{row.decisionReason}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        ) : (
                          <StatePanel tone="empty" compact>
                            当前文件没有逐行预览结果。
                          </StatePanel>
                        )}
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Stack>
          </Paper>
        </>
      ) : null}
    </PageScaffold>
  );
}
