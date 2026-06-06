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
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { type DragEvent, useEffect, useId, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import PageScaffold from "../common/PageScaffold";
import {
  confirmImportFiles,
  fetchImportSession,
  previewImportFiles,
  resolveImportApiErrorMessage,
} from "../../features/imports/api";
import { confirmEtcImportSession, fetchReadyEtcReconciliationTasks, previewEtcZipFiles } from "../../features/etc/api";
import { fetchWorkbenchSettings, fetchWorkbenchWithProgress } from "../../features/workbench/api";
import type {
  ImportBatchType,
  ImportFilePreview,
  ImportFilePreviewOverride,
  ImportPreviewAuditCounts,
  ImportPreviewDuplicateGroup,
  ImportPreviewDetailRow,
  ImportRowDecision,
  ImportSessionPayload,
} from "../../features/imports/types";
import type {
  EtcImportItem,
  EtcImportPreviewResult,
  EtcReconciliationBlockingIssue,
  EtcReconciliationTaskSummary,
  EtcUnavailableReconciliationTaskSummary,
} from "../../features/etc/types";
import type { BankAccountMapping } from "../../features/workbench/types";
import { useImportWorkflowDraft } from "../../contexts/ImportWorkflowDraftContext";
import type { FileSelectionState } from "../../contexts/ImportWorkflowDraftContext";
import { useImportProgress } from "../../contexts/ImportProgressContext";
import { useAppHealthStatus } from "../../contexts/AppHealthStatusContext";
import type { ImportWorkflowMode } from "../../features/imports/importRoutes";
import {
  useMuiDataGridPageSession,
  useMuiDataGridScrollSession,
} from "../../hooks/useMuiDataGridPageSession";

type ImportWorkflowPageProps = {
  mode: ImportWorkflowMode;
};

type ImportFilePreviewRow = ImportFilePreview & {
  accountLabel: string;
  batchTypeLabel: string;
  auditOriginalCount: number;
  auditUniqueCount: number;
  auditDuplicateInFileCount: number;
  auditDuplicateAcrossFilesCount: number;
  auditExistingDuplicateCount: number;
  auditImportableCount: number;
  auditErrorCount: number;
  auditSuspectedDuplicateCount: number;
  auditSkippedCount: number;
};

type ImportPreviewDetailGridRow = ImportPreviewDetailRow & {
  id: string;
  fileId: string;
  fileName: string;
  rowNo: number;
  duplicateType?: string;
  recordType?: string;
};

type EtcPreviewRow = EtcImportItem & {
  id: string;
  statusLabel: string;
  filterStatusLabel: string;
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

const ETC_FILTER_STATUS_LABELS: Record<string, string> = {
  included: "本次导入",
  excluded_extra_zip_invoice: "不在任务内",
  ambiguous_zip_match: "命中冲突",
  duplicate_requirement_invoice_match: "重复命中",
  not_in_reconciliation_preview: "未筛选",
};

const IMPORT_ROW_DECISION_LABELS: Record<string, string> = {
  created: "可导入",
  status_updated: "状态更新",
  duplicate_skipped: "已存在",
  suspected_duplicate: "需复核",
  error: "异常",
};

const STALE_RECONCILIATION_PREVIEW_MESSAGE = "对账任务已更新，请重新预览 ETC zip 后再确认导入。";

const DUPLICATE_TYPE_LABELS: Record<string, string> = {
  duplicate_in_file: "文件内重复",
  duplicate_across_files: "跨文件重复",
};

const DIRECTION_LABELS: Record<string, string> = {
  inflow: "收入",
  outflow: "支出",
  income: "收入",
  expense: "支出",
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

function etcFilterStatusLabel(status?: string) {
  if (!status) {
    return "--";
  }
  return ETC_FILTER_STATUS_LABELS[status] ?? status;
}

function importRowDecisionLabel(decision?: string | null) {
  if (!decision) {
    return "--";
  }
  return IMPORT_ROW_DECISION_LABELS[decision] ?? decision;
}

function duplicateTypeLabel(type?: string | null) {
  if (!type) {
    return "--";
  }
  return DUPLICATE_TYPE_LABELS[type] ?? type;
}

function directionLabel(direction?: string | null) {
  if (!direction) {
    return "--";
  }
  return DIRECTION_LABELS[direction] ?? direction;
}

function displayValue(value?: string | number | null) {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return String(value);
}

function isMissingEtcRequirementIssue(issue: EtcReconciliationBlockingIssue) {
  return issue.error === "missing_required_etc_invoice";
}

function formatMissingRequirementLine(issue: EtcReconciliationBlockingIssue) {
  const transactionAt = displayValue(issue.transactionAt || issue.transactionDate);
  const amount = displayValue(issue.amount);
  const plate = displayValue(issue.vehiclePlate);
  const invoiceCount = issue.invoiceCount ? ` / ${issue.invoiceCount} 张` : "";
  return `${transactionAt} / ${amount} / ${plate}${invoiceCount}`;
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

function buildEtcTaskOptionLabel(task: EtcReconciliationTaskSummary) {
  const period = task.periodStart && task.periodEnd ? `${task.periodStart} 至 ${task.periodEnd}` : "未设置期间";
  const plates = task.vehiclePlates.length > 0 ? ` / ${task.vehiclePlates.join("、")}` : "";
  const amount = task.oaTotalAmount ? ` / OA ${task.oaTotalAmount}` : "";
  return `${task.title || task.taskId} / ${period} / ETC票 ${task.etcInvoiceCount} + 补充凭证 ${task.supplementCount}${amount}${plates}`;
}

function buildUnavailableEtcTaskReason(task: EtcUnavailableReconciliationTaskSummary) {
  const explicitMessages = task.importBlockers
    .map((blocker) => blocker.message.trim())
    .filter(Boolean);
  if (explicitMessages.length > 0) {
    return explicitMessages.join("；");
  }
  if (task.status === "reviewing" || task.status === "draft") {
    return "任务尚未确认，请先在 ETC 对账页确认对账。";
  }
  if (task.status === "importing") {
    return "任务正在导入中，请等待导入完成。";
  }
  if (task.status === "imported") {
    return "任务已导入 ETC 发票；如需重导，请先在 ETC 对账页移除已导入发票。";
  }
  if (task.status === "closed") {
    return "任务已关闭，不能导入。";
  }
  return "任务当前状态不可导入。";
}

function formatSelectedBankAccountLabel(file: Pick<ImportFilePreview, "selectedBankName" | "selectedBankLast4">) {
  return `${file.selectedBankName ?? ""} ${file.selectedBankLast4 ?? ""}`.trim();
}

function emptyAuditCounts(): ImportPreviewAuditCounts {
  return {
    originalCount: 0,
    uniqueCount: 0,
    duplicateCount: 0,
    duplicateInFileCount: 0,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: 0,
    importableCount: 0,
    updateCount: 0,
    mergeCount: 0,
    suspectedDuplicateCount: 0,
    errorCount: 0,
    confirmableCount: 0,
    skippedCount: 0,
  };
}

function addAuditCounts(left: ImportPreviewAuditCounts, right: ImportPreviewAuditCounts): ImportPreviewAuditCounts {
  return {
    originalCount: left.originalCount + right.originalCount,
    uniqueCount: left.uniqueCount + right.uniqueCount,
    duplicateCount: left.duplicateCount + right.duplicateCount,
    duplicateInFileCount: left.duplicateInFileCount + right.duplicateInFileCount,
    duplicateAcrossFilesCount: left.duplicateAcrossFilesCount + right.duplicateAcrossFilesCount,
    existingDuplicateCount: left.existingDuplicateCount + right.existingDuplicateCount,
    importableCount: left.importableCount + right.importableCount,
    updateCount: left.updateCount + right.updateCount,
    mergeCount: left.mergeCount + right.mergeCount,
    suspectedDuplicateCount: left.suspectedDuplicateCount + right.suspectedDuplicateCount,
    errorCount: left.errorCount + right.errorCount,
    confirmableCount: left.confirmableCount + right.confirmableCount,
    skippedCount: left.skippedCount + right.skippedCount,
  };
}

function legacyFileAudit(file: ImportFilePreview): ImportPreviewAuditCounts {
  const duplicateCount = file.duplicateCount ?? 0;
  const importableCount = file.successCount ?? 0;
  const updateCount = file.updatedCount ?? 0;
  const suspectedDuplicateCount = file.suspectedDuplicateCount ?? 0;
  const errorCount = file.errorCount ?? 0;
  return {
    originalCount: file.rowCount ?? 0,
    uniqueCount: Math.max(0, (file.rowCount ?? 0) - duplicateCount),
    duplicateCount,
    duplicateInFileCount: duplicateCount,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: 0,
    importableCount,
    updateCount,
    mergeCount: 0,
    suspectedDuplicateCount,
    errorCount,
    confirmableCount: importableCount + updateCount,
    skippedCount: duplicateCount + suspectedDuplicateCount + errorCount,
  };
}

function fileAudit(file: ImportFilePreview): ImportPreviewAuditCounts {
  return file.audit ?? legacyFileAudit(file);
}

function importSessionAudit(payload: ImportSessionPayload | null): ImportPreviewAuditCounts | null {
  if (!payload) {
    return null;
  }
  if (payload.session.audit) {
    return payload.session.audit;
  }
  return payload.files.reduce((total, file) => addAuditCounts(total, fileAudit(file)), emptyAuditCounts());
}

function etcAudit(payload: EtcImportPreviewResult | null): ImportPreviewAuditCounts | null {
  if (!payload) {
    return null;
  }
  if (payload.audit) {
    return payload.audit;
  }
  const duplicateCount = payload.duplicatesSkipped ?? 0;
  const importableCount = payload.imported ?? 0;
  const mergeCount = payload.attachmentsCompleted ?? 0;
  const errorCount = payload.failed ?? 0;
  return {
    originalCount: importableCount + duplicateCount + mergeCount + errorCount,
    uniqueCount: importableCount + duplicateCount + mergeCount,
    duplicateCount,
    duplicateInFileCount: duplicateCount,
    duplicateAcrossFilesCount: 0,
    existingDuplicateCount: duplicateCount,
    importableCount,
    updateCount: 0,
    mergeCount,
    suspectedDuplicateCount: 0,
    errorCount,
    confirmableCount: importableCount + mergeCount,
    skippedCount: duplicateCount + errorCount,
  };
}

function formatConfirmAuditMessage(audit: ImportPreviewAuditCounts | null) {
  if (!audit) {
    return null;
  }
  const skippedDuplicateCount = audit.duplicateCount + audit.existingDuplicateCount;
  const reviewCount = audit.suspectedDuplicateCount + audit.errorCount;
  return `将导入 ${audit.importableCount} 条唯一记录，跳过 ${skippedDuplicateCount} 条重复${reviewCount > 0 ? `，${reviewCount} 条需复核` : ""}。`;
}

function isUnimportedDecision(decision: ImportRowDecision | string | null | undefined) {
  return decision === "duplicate_skipped" || decision === "suspected_duplicate" || decision === "error";
}

function buildDuplicateDetailRows(groups: ImportPreviewDuplicateGroup[]): ImportPreviewDetailGridRow[] {
  return groups.flatMap((group, groupIndex) => group.rows.map((row, rowIndex) => ({
    id: `${group.identityKey || groupIndex}-${row.fileId}-${row.rowNo}-${rowIndex}`,
    fileId: row.fileId,
    fileName: row.fileName,
    rowNo: row.rowNo,
    duplicateType: group.duplicateType,
    recordType: group.recordType,
    decision: row.decision,
    decisionReason: row.decisionReason,
    linkedObjectType: row.linkedObjectType,
    linkedObjectId: row.linkedObjectId,
    identityKind: row.identityKind,
    accountNo: row.accountNo,
    tradeTime: row.tradeTime,
    direction: row.direction,
    amount: row.amount,
    counterpartyName: row.counterpartyName,
  })));
}

function buildUnimportedDetailRows(payload: ImportSessionPayload | null): ImportPreviewDetailGridRow[] {
  if (!payload) {
    return [];
  }
  return payload.files.flatMap((file) => file.rowResults
    .filter((row) => isUnimportedDecision(row.decision))
    .map((row) => ({
      id: `${file.id}-${row.id || row.rowNo}`,
      fileId: file.id,
      fileName: file.fileName,
      rowNo: row.rowNo,
      recordType: row.sourceRecordType,
      decision: row.decision,
      decisionReason: row.decisionReason,
      linkedObjectType: row.linkedObjectType,
      linkedObjectId: row.linkedObjectId,
      identityKind: row.identityKind,
      accountNo: row.accountNo,
      tradeTime: row.tradeTime,
      direction: row.direction,
      amount: row.amount,
      counterpartyName: row.counterpartyName,
    })));
}

function AuditSummaryCards({ audit }: { audit: ImportPreviewAuditCounts | null }) {
  if (!audit) {
    return null;
  }
  const items = [
    ["原始", audit.originalCount],
    ["唯一", audit.uniqueCount],
    ["重复", audit.duplicateCount],
    ["已存在", audit.existingDuplicateCount],
    ["可导入", audit.importableCount],
    ["异常", audit.errorCount],
    ["未导入", audit.skippedCount],
  ] as const;
  return (
    <Box
      aria-label="导入预览审计汇总"
      sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(88px, 1fr))",
        gap: 1,
      }}
    >
      {items.map(([label, value]) => (
        <Paper
          key={label}
          variant="outlined"
          aria-label={`审计汇总 ${label} ${value}`}
          sx={{ p: 1, borderColor: "#d5dde8", bgcolor: "#f8fafc" }}
        >
          <Typography variant="caption" color="text.secondary">{label}</Typography>
          <Typography variant="h6" fontWeight={900}>{value}</Typography>
        </Paper>
      ))}
    </Box>
  );
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
  "& .MuiDataGrid-columnHeader": {
    backgroundColor: "#14263f",
    color: "#f8fafc",
  },
  "& .MuiDataGrid-columnHeaderTitle": {
    color: "#f8fafc",
    fontWeight: 800,
  },
  "& .MuiDataGrid-sortIcon, & .MuiDataGrid-menuIconButton, & .MuiDataGrid-iconButtonContainer": {
    color: "#f8fafc",
  },
  "& .MuiDataGrid-columnSeparator": {
    color: "rgba(248, 250, 252, 0.38)",
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
  const {
    draft,
    updateDraft,
    resetDraft,
    clearPersistedSession,
    readPersistedSessionId,
    persistSessionId,
    setSelectedFiles,
    setFileSelections,
    setPreviewPayload,
    setEtcPreviewPayload,
    setSelectedEtcTaskId,
    setEtcImported,
    setFeedbackMessage,
    setErrorMessage,
    setIsPreviewing,
    setIsConfirming,
  } = useImportWorkflowDraft(mode);
  const healthStatus = useAppHealthStatus();
  const {
    selectedFiles,
    fileSelections,
    previewPayload,
    etcPreviewPayload,
    selectedEtcTaskId,
    etcImported,
    feedbackMessage,
    errorMessage,
    isPreviewing,
    isConfirming,
  } = draft;
  const [bankOptions, setBankOptions] = useState<BankAccountMapping[]>([]);
  const [readyEtcTasks, setReadyEtcTasks] = useState<EtcReconciliationTaskSummary[]>([]);
  const [unavailableEtcTasks, setUnavailableEtcTasks] = useState<EtcUnavailableReconciliationTaskSummary[]>([]);
  const [readyEtcTasksLoading, setReadyEtcTasksLoading] = useState(mode === "etc_invoice");
  const [settingsLoading, setSettingsLoading] = useState(mode === "bank_transaction");
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [previewDetailTab, setPreviewDetailTab] = useState<"duplicates" | "unimported">("duplicates");

  const title = TITLES[mode];
  const uploadLabel = UPLOAD_LABELS[mode];
  const importPageKey = `imports.${mode}`;
  const previewGridSession = useMuiDataGridPageSession({
    pageKey: importPageKey,
    gridKey: "preview-main",
    columnsVersion: 1,
  });
  const previewGridScrollSession = useMuiDataGridScrollSession(previewGridSession);
  const previewDetailGridSession = useMuiDataGridPageSession({
    pageKey: importPageKey,
    gridKey: "preview-detail",
    columnsVersion: 1,
  });
  const previewDetailGridScrollSession = useMuiDataGridScrollSession(previewDetailGridSession);
  const etcPreviewGridSession = useMuiDataGridPageSession({
    pageKey: importPageKey,
    gridKey: "etc-preview",
    columnsVersion: 1,
  });
  const etcPreviewGridScrollSession = useMuiDataGridScrollSession(etcPreviewGridSession);

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

  useEffect(() => {
    const controller = new AbortController();
    if (mode !== "etc_invoice") {
      setReadyEtcTasks([]);
      setUnavailableEtcTasks([]);
      setReadyEtcTasksLoading(false);
      return () => controller.abort();
    }

    setReadyEtcTasksLoading(true);
    fetchReadyEtcReconciliationTasks(controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) {
          return;
        }
        setReadyEtcTasks(payload.items);
        setUnavailableEtcTasks(payload.unavailableItems);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setErrorMessage(resolveImportApiErrorMessage(error, "ETC 对账任务加载失败，请稍后重试。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setReadyEtcTasksLoading(false);
        }
      });

    return () => controller.abort();
  }, [mode]);

  useEffect(() => {
    if (mode === "etc_invoice" || selectedFiles.length > 0 || previewPayload) {
      return undefined;
    }
    const sessionId = readPersistedSessionId();
    if (!sessionId) {
      return undefined;
    }

    let active = true;
    setIsPreviewing(true);
    setErrorMessage(null);
    fetchImportSession(sessionId)
      .then((payload) => {
        if (!active) {
          return;
        }
        setIsPreviewing(false);
        setPreviewPayload(payload);
        setFeedbackMessage(`已恢复上次 ${payload.files.length} 个文件的预览识别。`);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setIsPreviewing(false);
        clearPersistedSession();
        resetDraft();
        setErrorMessage("上次预览会话已失效，请重新选择文件。");
      });

    return () => {
      active = false;
    };
  }, [
    clearPersistedSession,
    mode,
    previewPayload,
    readPersistedSessionId,
    resetDraft,
    selectedFiles.length,
    setErrorMessage,
    setFeedbackMessage,
    setIsPreviewing,
    setPreviewPayload,
  ]);

  const bankOptionMap = useMemo(
    () => new Map(bankOptions.map((item) => [item.id, item])),
    [bankOptions],
  );
  const selectedEtcTask = useMemo(
    () => readyEtcTasks.find((task) => task.taskId === selectedEtcTaskId) ?? null,
    [readyEtcTasks, selectedEtcTaskId],
  );
  const hasSelectedEtcTask = mode !== "etc_invoice" || Boolean(selectedEtcTask);

  const canUseBankImport = mode !== "bank_transaction" || bankOptions.length > 0;
  const allFilesConfigured = selectedFiles.length > 0 && selectedFiles.every((file) => {
    if (mode === "etc_invoice") {
      return isZipFile(file);
    }
    const selection = fileSelections[buildSelectedFileKey(file)];
    return mode === "bank_transaction" ? Boolean(selection?.bankMappingId) : Boolean(selection?.invoiceBatchType);
  });
  const canPreview = canUseBankImport
    && hasSelectedEtcTask
    && allFilesConfigured
    && !isPreviewing
    && !isConfirming
    && !settingsLoading
    && !readyEtcTasksLoading;
  const confirmableFileIds = useMemo(
    () => previewPayload?.files.filter(canConfirmFile).map((file) => file.id) ?? [],
    [previewPayload],
  );
  const etcBlockingIssues = useMemo(
    () => etcPreviewPayload?.reconciliationFilter?.blockingIssues ?? [],
    [etcPreviewPayload],
  );
  const missingEtcRequirementIssues = useMemo(
    () => etcBlockingIssues.filter(isMissingEtcRequirementIssue),
    [etcBlockingIssues],
  );
  const canConfirm = confirmableFileIds.length > 0 && !isPreviewing && !isConfirming;
  const canConfirmEtc = Boolean(etcPreviewPayload?.sessionId)
    && Boolean(selectedEtcTaskId)
    && Boolean(selectedEtcTask)
    && etcBlockingIssues.length === 0
    && !etcImported
    && !isPreviewing
    && !isConfirming;
  const hasDraftContent = selectedFiles.length > 0
    || Boolean(previewPayload)
    || Boolean(etcPreviewPayload)
    || Boolean(selectedEtcTaskId)
    || Object.keys(fileSelections).length > 0
    || Boolean(feedbackMessage)
    || Boolean(errorMessage);
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
  const previewAudit = useMemo(() => importSessionAudit(previewPayload), [previewPayload]);
  const etcPreviewAudit = useMemo(() => etcAudit(etcPreviewPayload), [etcPreviewPayload]);
  const confirmAuditMessage = useMemo(
    () => formatConfirmAuditMessage(mode === "etc_invoice" ? (etcPreviewPayload?.importAudit ?? etcPreviewAudit) : previewAudit),
    [etcPreviewAudit, etcPreviewPayload?.importAudit, mode, previewAudit],
  );

  const previewRows = useMemo<ImportFilePreviewRow[]>(() => (
    previewPayload?.files.map((file) => {
      const audit = fileAudit(file);
      return {
        ...file,
        accountLabel: formatSelectedBankAccountLabel(file) || "--",
        batchTypeLabel: batchTypeLabel(file.batchType),
        auditOriginalCount: audit.originalCount,
        auditUniqueCount: audit.uniqueCount,
        auditDuplicateInFileCount: audit.duplicateInFileCount,
        auditDuplicateAcrossFilesCount: audit.duplicateAcrossFilesCount,
        auditExistingDuplicateCount: audit.existingDuplicateCount,
        auditImportableCount: audit.importableCount,
        auditErrorCount: audit.errorCount,
        auditSuspectedDuplicateCount: audit.suspectedDuplicateCount,
        auditSkippedCount: audit.skippedCount,
      };
    }) ?? []
  ), [previewPayload]);

  const duplicateDetailRows = useMemo(
    () => buildDuplicateDetailRows(previewPayload?.duplicateGroups ?? []),
    [previewPayload],
  );
  const unimportedDetailRows = useMemo(
    () => buildUnimportedDetailRows(previewPayload),
    [previewPayload],
  );

  const etcRows = useMemo<EtcPreviewRow[]>(() => (
    etcPreviewPayload?.items.map((item, index) => ({
      ...item,
      id: `${item.invoiceNumber || item.fileName || "etc"}-${index}`,
      statusLabel: etcStatusLabel(item.status),
      filterStatusLabel: etcFilterStatusLabel(item.filterStatus),
    })) ?? []
  ), [etcPreviewPayload]);

  const previewColumns = useMemo<GridColDef<ImportFilePreviewRow>[]>(() => [
    { field: "fileName", headerName: "文件", flex: 1.4, minWidth: 220 },
    { field: "status", headerName: "状态", width: 110, valueFormatter: (value) => statusLabel(String(value)) },
    { field: "batchTypeLabel", headerName: "类型", width: 120 },
    { field: "accountLabel", headerName: "账户", width: 160 },
    { field: "auditOriginalCount", headerName: "原始", type: "number", width: 90 },
    { field: "auditUniqueCount", headerName: "唯一", type: "number", width: 90 },
    { field: "auditDuplicateInFileCount", headerName: "文件内重复", type: "number", width: 120 },
    { field: "auditDuplicateAcrossFilesCount", headerName: "跨文件重复", type: "number", width: 120 },
    { field: "auditExistingDuplicateCount", headerName: "已存在", type: "number", width: 100 },
    { field: "auditImportableCount", headerName: "可导入", type: "number", width: 100 },
    { field: "auditSuspectedDuplicateCount", headerName: "需复核", type: "number", width: 100 },
    { field: "auditErrorCount", headerName: "异常", type: "number", width: 90 },
    { field: "auditSkippedCount", headerName: "未导入", type: "number", width: 100 },
    { field: "rowCount", headerName: "行数", type: "number", width: 90 },
    { field: "successCount", headerName: "新增", type: "number", width: 90 },
    { field: "message", headerName: "消息", flex: 1.6, minWidth: 240 },
  ], []);

  const detailColumns = useMemo<GridColDef<ImportPreviewDetailGridRow>[]>(() => [
    { field: "fileName", headerName: "文件", flex: 1.1, minWidth: 180 },
    { field: "rowNo", headerName: "行号", type: "number", width: 80 },
    { field: "accountNo", headerName: "账户", minWidth: 140, valueFormatter: (value) => displayValue(value) },
    { field: "tradeTime", headerName: "交易时间", minWidth: 170, valueFormatter: (value) => displayValue(value) },
    { field: "direction", headerName: "方向", width: 90, valueFormatter: (value) => directionLabel(String(value ?? "")) },
    { field: "amount", headerName: "金额", minWidth: 110, valueFormatter: (value) => displayValue(value) },
    { field: "counterpartyName", headerName: "对方户名", flex: 1, minWidth: 180, valueFormatter: (value) => displayValue(value) },
    { field: "duplicateType", headerName: "类型", minWidth: 120, valueFormatter: (value) => duplicateTypeLabel(String(value ?? "")) },
    { field: "decision", headerName: "决策", minWidth: 110, valueFormatter: (value) => importRowDecisionLabel(String(value ?? "")) },
    { field: "decisionReason", headerName: "原因", flex: 1.3, minWidth: 220, valueFormatter: (value) => displayValue(value) },
  ], []);

  const etcColumns = useMemo<GridColDef<EtcPreviewRow>[]>(() => [
    { field: "invoiceNumber", headerName: "发票号", flex: 1, minWidth: 180 },
    { field: "fileName", headerName: "文件", flex: 1.2, minWidth: 220 },
    { field: "statusLabel", headerName: "状态", width: 120 },
    { field: "filterStatusLabel", headerName: "对账筛选", width: 130 },
    { field: "reason", headerName: "原因", flex: 1.6, minWidth: 260 },
  ], []);

  function resetPreviewState() {
    setPreviewPayload(null);
    setEtcPreviewPayload(null);
    setEtcImported(false);
    setConflictDialogOpen(false);
    setFeedbackMessage(null);
    setErrorMessage(null);
    clearPersistedSession();
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

  function handleEtcTaskChange(taskId: string) {
    setSelectedEtcTaskId(taskId);
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
      if (!selectedEtcTask) {
        setErrorMessage("请选择已确认的 ETC 对账任务后再预览 ETC zip。");
        return;
      }
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
        const payload = await previewEtcZipFiles(selectedFiles, selectedEtcTask.taskId);
        updateDraft((current) => ({
          ...current,
          etcPreviewPayload: payload,
          etcImported: false,
          previewPayload: null,
          feedbackMessage: `已完成 ${selectedFiles.length} 个 ETC zip 文件预览。`,
          errorMessage: null,
        }));
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
      persistSessionId(payload.session.id);
      updateDraft((current) => ({
        ...current,
        previewPayload: payload,
        feedbackMessage: `已完成 ${payload.files.length} 个文件的预览识别。`,
        errorMessage: null,
      }));
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
    if (healthStatus.blocksMutations) {
      setErrorMessage("登录已失效或系统不可用，请返回 OA 系统重新进入。");
      return;
    }
    if (mode === "etc_invoice") {
      if (!selectedEtcTask) {
        setErrorMessage("请选择已确认的 ETC 对账任务后再预览 ETC zip。");
        return;
      }
      if (!etcPreviewPayload?.sessionId) {
        setErrorMessage("请先预览 ETC zip 文件。");
        return;
      }
      setIsConfirming(true);
      setErrorMessage(null);
      try {
        const payload = await confirmEtcImportSession(etcPreviewPayload.sessionId, selectedEtcTask.taskId);
        setEtcImported(true);
        setFeedbackMessage(payload.job ? "已开始后台导入" : "已导入 ETC票据管理");
      } catch (error) {
        if (error instanceof Error && error.message === STALE_RECONCILIATION_PREVIEW_MESSAGE) {
          setEtcPreviewPayload(null);
          setEtcImported(false);
        }
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
        resetDraft();
        setFeedbackMessage("已开始后台导入");
        return;
      }
      resetDraft();
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
            <Button type="button" variant="outlined" onClick={handleClearFiles} disabled={!hasDraftContent || isPreviewing || isConfirming}>
              清空
            </Button>
            <Button type="button" variant="outlined" onClick={handlePreview} disabled={!canPreview}>
              {isPreviewing ? "预览中..." : "开始预览"}
            </Button>
            <Button
              type="button"
              variant="contained"
              onClick={handleConfirm}
              disabled={healthStatus.blocksMutations || (mode === "etc_invoice" ? !canConfirmEtc : !canConfirm)}
            >
              {isConfirming ? "确认中..." : "确认导入"}
            </Button>
          </Stack>
        }
      >
        <Stack spacing={2.5}>
          {feedbackMessage ? <Alert severity="success">{feedbackMessage}</Alert> : null}
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          {confirmAuditMessage ? <Alert severity="info">{confirmAuditMessage}</Alert> : null}
          {settingsLoading ? <Alert severity="info">正在加载银行账户映射...</Alert> : null}
          {!settingsLoading && !canUseBankImport ? <Alert severity="warning">设置里还没有银行账户映射，请先在设置中维护银行。</Alert> : null}
          {mode === "etc_invoice" && readyEtcTasksLoading ? <Alert severity="info">正在加载可导入的 ETC 对账任务...</Alert> : null}
          {mode === "etc_invoice" && !readyEtcTasksLoading && readyEtcTasks.length === 0 ? (
            <Alert severity="warning">
              <Stack spacing={1}>
                <Typography variant="body2" fontWeight={700}>
                  当前没有已确认且可导入的 ETC 对账任务。导入页不能新建任务，请先在 ETC 对账页完成确认。
                </Typography>
                {unavailableEtcTasks.length > 0 ? (
                  <Stack spacing={0.75}>
                    <Typography variant="caption" color="text.secondary">
                      已找到 {unavailableEtcTasks.length} 个 ETC 对账任务，但当前不可导入：
                    </Typography>
                    {unavailableEtcTasks.slice(0, 5).map((task) => (
                      <Stack
                        key={task.taskId}
                        direction={{ xs: "column", sm: "row" }}
                        spacing={0.75}
                        sx={{ alignItems: { xs: "flex-start", sm: "center" } }}
                      >
                        <Chip size="small" label={`${task.title || task.taskId} / ${task.status}`} />
                        <Typography variant="caption">{buildUnavailableEtcTaskReason(task)}</Typography>
                      </Stack>
                    ))}
                    {unavailableEtcTasks.length > 5 ? (
                      <Typography variant="caption" color="text.secondary">
                        还有 {unavailableEtcTasks.length - 5} 个不可导入任务，请到 ETC 对账页处理。
                      </Typography>
                    ) : null}
                  </Stack>
                ) : null}
              </Stack>
            </Alert>
          ) : null}
          {mode === "etc_invoice" && !readyEtcTasksLoading && readyEtcTasks.length > 0 && !selectedEtcTask ? (
            <Alert severity="warning">请选择已确认的 ETC 对账任务后再预览 ETC zip。</Alert>
          ) : null}

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

                {mode === "etc_invoice" ? (
                  <Stack spacing={1}>
                    <FormControl size="small" fullWidth>
                      <InputLabel id="etc-reconciliation-task-label">ETC对账任务</InputLabel>
                      <Select
                        native
                        labelId="etc-reconciliation-task-label"
                        label="ETC对账任务"
                        value={selectedEtcTaskId}
                        disabled={isPreviewing || isConfirming || readyEtcTasksLoading || readyEtcTasks.length === 0}
                        inputProps={{ "aria-label": "ETC对账任务" }}
                        onChange={(event) => handleEtcTaskChange(event.target.value)}
                      >
                        <option aria-label="未选择ETC对账任务" value="" />
                        {readyEtcTasks.map((task) => (
                          <option key={task.taskId} value={task.taskId}>
                            {buildEtcTaskOptionLabel(task)}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                    {selectedEtcTask ? (
                      <Stack direction="row" flexWrap="wrap" gap={1} aria-label="已选ETC对账任务">
                        <Chip size="small" label={`任务 ${selectedEtcTask.title || selectedEtcTask.taskId}`} />
                        <Chip size="small" label={`版本 ${selectedEtcTask.version}`} />
                        <Chip size="small" label={`ETC票 ${selectedEtcTask.etcInvoiceCount}`} />
                        <Chip size="small" label={`补充凭证 ${selectedEtcTask.supplementCount}`} />
                      </Stack>
                    ) : null}
                  </Stack>
                ) : null}

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
                    <AuditSummaryCards audit={etcPreviewAudit} />
                    {etcPreviewPayload ? (
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip color="success" label={`本次导入新增 ${etcPreviewPayload.imported}`} />
                        <Chip label={`本次重复跳过 ${etcPreviewPayload.duplicatesSkipped}`} />
                        <Chip color="info" label={`本次附件补齐 ${etcPreviewPayload.attachmentsCompleted}`} />
                        <Chip color={etcPreviewPayload.failed > 0 ? "warning" : "default"} label={`异常 ${etcPreviewPayload.failed}`} />
                      </Stack>
                    ) : null}
                    {missingEtcRequirementIssues.length > 0 ? (
                      <Alert severity="warning" aria-label="ETC对账任务缺失项">
                        <Stack spacing={1}>
                          <Typography fontWeight={800}>ETC对账任务缺失项</Typography>
                          <Stack spacing={0.75}>
                            {missingEtcRequirementIssues.map((issue) => (
                              <Paper
                                key={issue.requirementId || formatMissingRequirementLine(issue)}
                                variant="outlined"
                                sx={{ p: 1, borderColor: "#f59e0b", bgcolor: "#fff7ed" }}
                              >
                                <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center">
                                  <Chip size="small" color="warning" label={displayValue(issue.transactionAt || issue.transactionDate)} />
                                  <Chip size="small" label={displayValue(issue.amount)} />
                                  <Chip size="small" label={displayValue(issue.vehiclePlate)} />
                                  {issue.invoiceCount ? <Chip size="small" label={`${issue.invoiceCount} 张`} /> : null}
                                  <Typography variant="body2" color="text.secondary">
                                    {issue.requirementId}
                                  </Typography>
                                </Stack>
                              </Paper>
                            ))}
                          </Stack>
                        </Stack>
                      </Alert>
                    ) : null}
                    {etcBlockingIssues.length > 0 && missingEtcRequirementIssues.length === 0 ? (
                      <Alert severity="warning">ETC 对账任务仍有 {etcBlockingIssues.length} 个阻塞项，请处理后重新预览。</Alert>
                    ) : null}
                    <Box ref={etcPreviewGridScrollSession.rootRef} sx={{ height: 420, width: "100%" }}>
                      <DataGrid
                        aria-label="ETC导入预览结果"
                        apiRef={etcPreviewGridScrollSession.apiRef}
                        columns={etcColumns}
                        rows={etcRows}
                        loading={isPreviewing}
                        disableRowSelectionOnClick
                        hideFooter
                        initialState={etcPreviewGridScrollSession.initialState}
                        showToolbar
                        sx={importGridSx}
                      />
                    </Box>
                  </Stack>
                ) : (
                  <Stack spacing={1.5}>
                    <AuditSummaryCards audit={previewAudit} />
                    <Box ref={previewGridScrollSession.rootRef} sx={{ height: 480, width: "100%" }}>
                      <DataGrid
                        aria-label="导入预览结果"
                        apiRef={previewGridScrollSession.apiRef}
                        columns={previewColumns}
                        rows={previewRows}
                        loading={isPreviewing}
                        disableRowSelectionOnClick
                        hideFooter
                        initialState={previewGridScrollSession.initialState}
                        showToolbar
                        sx={importGridSx}
                      />
                    </Box>
                    <Box sx={{ border: "1px solid #d5dde8", borderRadius: 1, overflow: "hidden" }}>
                      <Tabs
                        value={previewDetailTab}
                        onChange={(_, value: "duplicates" | "unimported") => setPreviewDetailTab(value)}
                        aria-label="导入预览明细"
                        sx={{ minHeight: 42, px: 1, bgcolor: "#f8fafc", borderBottom: "1px solid #d5dde8" }}
                      >
                        <Tab value="duplicates" label={`重复项 ${duplicateDetailRows.length}`} sx={{ minHeight: 42 }} />
                        <Tab value="unimported" label={`未导入项 ${unimportedDetailRows.length}`} sx={{ minHeight: 42 }} />
                      </Tabs>
                      <Box ref={previewDetailGridScrollSession.rootRef} sx={{ height: 360, width: "100%" }}>
                        <DataGrid
                          aria-label={previewDetailTab === "duplicates" ? "重复项明细" : "未导入项明细"}
                          apiRef={previewDetailGridScrollSession.apiRef}
                          columns={detailColumns}
                          rows={previewDetailTab === "duplicates" ? duplicateDetailRows : unimportedDetailRows}
                          loading={isPreviewing}
                          disableRowSelectionOnClick
                          hideFooter
                          initialState={previewDetailGridScrollSession.initialState}
                          showToolbar
                          sx={{
                            ...importGridSx,
                            border: 0,
                          }}
                        />
                      </Box>
                    </Box>
                  </Stack>
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
          <Button type="button" variant="contained" onClick={() => { void submitConfirm(); }} disabled={isConfirming || healthStatus.blocksMutations}>
            {isConfirming ? "确认中..." : conflictConfirmLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
